"""The input path: one named export in, one document record out.

Reading a file means mapping names onto roles, never onto positions in a
line. The delimiter is determined by the header; the decimal separator is
the named assumption ``default-numeric-reading-v1`` recorded on the result.
Run-level violations (undecodable bytes, a delimiter colliding with the
assumed separator) stop the run instead of refusing one scan. Every other
violation is per scan, and each failing row carries exactly one reason.
"""

from __future__ import annotations

from collections import Counter
import math
import re
from typing import TYPE_CHECKING, Literal, NamedTuple

from groundscan_analyzer import (
    background,
    descriptors,
    dialect,
    document,
    frames,
    hierarchy,
    input_contract,
    perturbation,
    positions,
    registration,
    scale,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

SECTION_RE = re.compile(r"^\+\+\+\s*(.+?)\s*\+\+\+$")
DECORATED_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(m|%)?$")
MEASURING_KEY = input_contract.normalise("Measuring Values")

MIN_SERIES_COUNT = 2

_UNKNOWN_COLUMN: document.RefusalReason = "unknown-column-name"
_DUPLICATE_NAME: document.RefusalReason = "duplicate-normalised-name"
_MISSING_REQUIRED: document.RefusalReason = "missing-required-column"
_UNPARSEABLE_ROW: document.RefusalReason = "unparseable-row"
_INVALID_INDEX: document.RefusalReason = "invalid-index-value"
_DUPLICATE_COORDINATE: document.RefusalReason = "duplicate-coordinate"
_ASSUMED_READING: document.RefusalReason = "unparseable-under-assumed-reading"

SOIL_NUMERIC_KEYS = (
    "dielectric constant",
    "relative permeability",
    "mineralization",
    "humidity",
    "homogeneity",
)


class RunLevelError(ValueError):
    """A failure that stops the run instead of refusing one scan."""


class UndecodableInputError(RunLevelError):
    """The file cannot be decoded at all."""


class DelimiterCollisionError(RunLevelError):
    """The determined delimiter collides with the assumed decimal separator."""


class _RefusalError(Exception):
    """A per-scan refusal travelling back to its scan record."""

    def __init__(
        self,
        reason: document.RefusalReason,
        detail: str,
        rows: tuple[document.RowIssue, ...] = (),
    ) -> None:
        """Carry a scan-level reason with its per-row breakdown.

        Args:
            reason: The closed-vocabulary reason the scan is refused.
            detail: Content-derived context naming the failing name or count.
            rows: The failing rows, each carrying exactly one reason.
        """
        super().__init__(reason, detail)
        self.reason = reason
        self.detail = detail
        self.rows = rows


class _Block(NamedTuple):
    """One section's non-blank content lines with their file line numbers."""

    name: str
    lines: list[tuple[int, str]]


class _Layout(NamedTuple):
    """Column positions by role, None where the optional column is absent."""

    impulse: int
    scan_line: int
    response: int
    metric_x: int | None
    metric_y: int | None
    depth: int | None
    latitude: int | None
    longitude: int | None


class _Row(NamedTuple):
    """One evaluated row: lattice position, response, depth and echo values."""

    lineno: int
    impulse: int
    scan_line: int
    response: float | None
    depth: float | None
    metric_x: float | None
    metric_y: float | None
    metric_x_raw: str
    metric_y_raw: str


class _Table(NamedTuple):
    """An evaluated measuring block with its row-level findings."""

    rows: list[_Row]
    short_lines: list[int]
    issues: list[document.RowIssue]
    latitude_value: bool
    longitude_value: bool


def _collect_sections(lines: list[str]) -> dict[str, _Block]:
    """Group raw lines into the closed section registry.

    Args:
        lines: The file split into lines, still carrying blank lines.

    Returns:
        The present sections keyed by normalised name.

    Raises:
        _RefusalError: On content outside any section, an unknown or
            repeated section, or a missing measuring block.
    """
    blocks: dict[str, _Block] = {}
    current: str | None = None
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        match = SECTION_RE.match(raw.strip())
        if match is not None:
            _open_section(blocks, match.group(1))
            current = input_contract.normalise(match.group(1))
            continue
        if current is None:
            issue = document.RowIssue(line=number, reason="unparseable-row")
            detail = "content outside any section"
            raise _RefusalError(_UNPARSEABLE_ROW, detail, (issue,))
        blocks[current].lines.append((number, raw))
    if MEASURING_KEY not in blocks:
        detail = "Measuring Values is required"
        raise _RefusalError(_MISSING_REQUIRED, detail, ())
    return blocks


def _open_section(blocks: dict[str, _Block], name: str) -> None:
    """Open one section header, refusing repeats and unknown names.

    An unknown section shares the header-level unknown-name reason, since
    the violation vocabulary is closed and section names are matched by
    the same rule as column names.

    Args:
        blocks: The sections opened so far, keyed by normalised name.
        name: The raw section name as written between the +++ markers.

    Raises:
        _RefusalError: On a repeated or unregistered section name.
    """
    key = input_contract.normalise(name)
    if key in blocks:
        detail = f"section {name!r} appears twice"
        raise _RefusalError(_DUPLICATE_NAME, detail, ())
    if input_contract.find_section(name) is None:
        detail = f"unknown section {name!r}"
        raise _RefusalError(_UNKNOWN_COLUMN, detail, ())
    blocks[key] = _Block(name=name, lines=[])


def _is_registered_column(cell: str) -> bool:
    """Report whether a raw header cell names a registered column.

    Args:
        cell: The raw header cell as written in the file.

    Returns:
        True when the cell matches a registry entry.
    """
    return input_contract.find_column(cell) is not None


def _fallback_delimiter(header_line: str) -> str:
    """Pick the most informative delimiter for a header nothing splits cleanly.

    The header is refused downstream with its precise per-cell reason; this
    only decides which reading reports it.

    Args:
        header_line: The raw header line of the measuring block.

    Returns:
        The candidate with the most registered cells, ties to the first.
    """
    best = dialect.DELIMITER_CANDIDATES[0]
    best_count = -1
    for candidate in dialect.DELIMITER_CANDIDATES:
        count = sum(1 for cell in header_line.split(candidate) if _is_registered_column(cell))
        if count > best_count:
            best = candidate
            best_count = count
    return best


def _choose_delimiter(header_line: str) -> str:
    """Determine the one delimiter splitting the header into known names.

    Args:
        header_line: The raw header line of the measuring block.

    Returns:
        The determined delimiter character.

    Raises:
        DelimiterCollisionError: When the delimiter collides, stopping
            the run instead of refusing one scan.
    """
    fitting = dialect.candidate_delimiters(header_line, _is_registered_column)
    chosen = fitting[0] if fitting else _fallback_delimiter(header_line)
    if chosen == dialect.DECIMAL_SEPARATOR:
        msg = "delimiter collides with the assumed decimal separator"
        raise DelimiterCollisionError(msg)
    return chosen


def _map_columns(cells: list[str]) -> list[input_contract.ColumnEntry]:
    """Map header cells onto registry entries, refusing header violations.

    Unknown is checked before missing, so a misspelled required column
    reads as unknown rather than missing.

    Args:
        cells: The header cells in file order.

    Returns:
        The registry entry per cell, in file order.

    Raises:
        _RefusalError: On a duplicate, unknown or missing-required header.
    """
    seen: set[str] = set()
    entries: list[input_contract.ColumnEntry] = []
    for cell in cells:
        key = input_contract.normalise(cell)
        if key in seen:
            detail = f"column {cell!r} appears twice"
            raise _RefusalError(_DUPLICATE_NAME, detail, ())
        seen.add(key)
        entry = input_contract.find_column(cell)
        if entry is None:
            detail = f"unknown column {cell!r}"
            raise _RefusalError(_UNKNOWN_COLUMN, detail, ())
        entries.append(entry)
    roles = {entry.role for entry in entries}
    for role in input_contract.REQUIRED_ROLES:
        if role not in roles:
            detail = f"required role {role!r} is absent"
            raise _RefusalError(_MISSING_REQUIRED, detail, ())
    return entries


def _column_index(entries: list[input_contract.ColumnEntry], name: str) -> int | None:
    """Locate an optional column by its canonical name.

    Args:
        entries: The mapped header entries in file order.
        name: The canonical registry name to find.

    Returns:
        The position, or None when the optional column is absent.
    """
    for position, entry in enumerate(entries):
        if input_contract.normalise(entry.name) == input_contract.normalise(name):
            return position
    return None


def _layout(entries: list[input_contract.ColumnEntry]) -> _Layout:
    """Fix the column positions by role for the row pass.

    Args:
        entries: The mapped header entries in file order.

    Returns:
        The required positions with None for each absent optional column.
    """
    required: dict[str, int] = {}
    for position, entry in enumerate(entries):
        if entry.role in {"impulse", "scan-line", "response"}:
            required[entry.role] = position
    return _Layout(
        impulse=required["impulse"],
        scan_line=required["scan-line"],
        response=required["response"],
        metric_x=_column_index(entries, "Impulse X [m]"),
        metric_y=_column_index(entries, "Scan Line Y [m]"),
        depth=_column_index(entries, "Depth Z [m]"),
        latitude=_column_index(entries, "Latitude"),
        longitude=_column_index(entries, "Longitude"),
    )


def _keyed_values(lines: list[tuple[int, str]]) -> dict[str, str]:
    """Read a non-measuring block as normalised key to raw value.

    Lines without a colon are free text and never parsed. A repeated key
    keeps its first value; later ones cannot contradict it silently.

    Args:
        lines: The block content with file line numbers.

    Returns:
        The first value per normalised key.
    """
    values: dict[str, str] = {}
    for _, raw in lines:
        key, separator, value = raw.partition(":")
        if not separator:
            continue
        normalised = input_contract.normalise(key)
        if normalised not in values:
            values[normalised] = value
    return values


def _parse_decorated(value: str, owner: str) -> float | None:
    """Parse an operator-typed value such as ``3.00 m`` or ``30 %``.

    Args:
        value: The raw value after the colon.
        owner: The key being parsed, for the refusal detail.

    Returns:
        The numeric value, or None when the operator left it blank.

    Raises:
        _RefusalError: When the value does not parse under the assumed
            reading, refusing the whole scan.
    """
    text = value.strip()
    if not text:
        return None
    if dialect.carries_other_separator(text):
        detail = f"{owner} carries the other separator"
        raise _RefusalError(_ASSUMED_READING, detail, ())
    match = DECORATED_RE.match(text)
    if match is None:
        detail = f"{owner} does not parse"
        raise _RefusalError(_ASSUMED_READING, detail, ())
    parsed = dialect.parse_numeral(match.group(1))
    if parsed is None:
        detail = f"{owner} does not parse"
        raise _RefusalError(_ASSUMED_READING, detail, ())
    return parsed


def _read_extent(blocks: dict[str, _Block]) -> document.Extent:
    """Read the declared extent from the extent-carrying section.

    Args:
        blocks: The present sections keyed by normalised name.

    Returns:
        The declared lengths, each absent where never declared.
    """
    key = input_contract.normalise("Characteristics")
    if key not in blocks:
        return document.Extent()
    values = _keyed_values(blocks[key].lines)
    length_key = input_contract.normalise("Field Length")
    width_key = input_contract.normalise("Field Width")
    return document.Extent(
        field_length=_parse_decorated(values.get(length_key, ""), "Field Length"),
        field_width=_parse_decorated(values.get(width_key, ""), "Field Width"),
    )


def _check_soil(blocks: dict[str, _Block]) -> None:
    """Parse the soil numerics and discard them, refusing on failure.

    A field that is not load-bearing still bears on the parse.

    Args:
        blocks: The present sections keyed by normalised name.
    """
    key = input_contract.normalise("Soil Type")
    if key not in blocks:
        return
    values = _keyed_values(blocks[key].lines)
    for name in SOIL_NUMERIC_KEYS:
        _parse_decorated(values.get(name, ""), name)


def _modal_length(data: list[tuple[int, str]], delimiter: str) -> int:
    """Find the file's own modal row length for the short-line rule.

    Args:
        data: The measuring data lines with file line numbers.
        delimiter: The determined delimiter character.

    Returns:
        The most common field count, breaking ties towards the longer row.
    """
    counts = Counter(len(raw.split(delimiter)) for _, raw in data)
    return max(counts, key=lambda count: (counts[count], count))


def _check_row_commas(data: list[tuple[int, str]], delimiter: str, layout: _Layout) -> None:
    """Refuse the scan when any numeric token carries the other separator.

    The dialect is established before any row is evaluated, so a
    dialect-level failure means the row rules never run.

    Args:
        data: The measuring data lines with file line numbers.
        delimiter: The determined delimiter character.
        layout: The column positions by role.

    Raises:
        _RefusalError: Carrying the assumed-reading reason with no rows.
    """
    for _, raw in data:
        fields = raw.split(delimiter)
        for index in _numeric_positions(layout):
            token = fields[index] if index < len(fields) else ""
            if token.strip() and dialect.carries_other_separator(token):
                detail = "a numeric token carries the other separator"
                raise _RefusalError(_ASSUMED_READING, detail, ())


def _numeric_positions(layout: _Layout) -> list[int]:
    """List the numeric-role column positions for the row parse.

    Args:
        layout: The column positions by role.

    Returns:
        The required positions followed by each present echo position.
    """
    positions = [layout.impulse, layout.scan_line, layout.response]
    positions.extend(
        index for index in (layout.metric_x, layout.metric_y, layout.depth) if index is not None
    )
    return positions


def _evaluate_rows(
    data: list[tuple[int, str]], delimiter: str, header_len: int, layout: _Layout
) -> _Table:
    """Evaluate every row with exactly one reason per failing row.

    A row failing an earlier rule is never evaluated against a later one:
    overlong first, then unparseable, then index validity, then duplicates.

    Args:
        data: The measuring data lines with file line numbers.
        delimiter: The determined delimiter character.
        header_len: The header field count.
        layout: The column positions by role.

    Returns:
        The accepted rows, short lines, row issues and presence flags.
    """
    modal = _modal_length(data, delimiter) if data else header_len
    rows: list[_Row] = []
    short_lines: list[int] = []
    issues: list[document.RowIssue] = []
    seen: set[tuple[int, int]] = set()
    latitude_value = False
    longitude_value = False
    for lineno, raw in data:
        fields = raw.split(delimiter)
        if len(fields) > header_len:
            issues.append(document.RowIssue(line=lineno, reason="unparseable-row"))
            continue
        if len(fields) < modal:
            short_lines.append(lineno)
        outcome = _evaluate_row(fields, lineno, header_len, layout, seen)
        if isinstance(outcome, document.RowIssue):
            issues.append(outcome)
        else:
            rows.append(outcome)
        latitude_value, longitude_value = _track_presence(
            fields, layout, latitude_value=latitude_value, longitude_value=longitude_value
        )
    return _Table(rows, short_lines, issues, latitude_value, longitude_value)


def _track_presence(
    fields: list[str], layout: _Layout, *, latitude_value: bool, longitude_value: bool
) -> tuple[bool, bool]:
    """Fold one row's discarded coordinate cells into presence flags.

    Values are never parsed here, only noticed.

    Args:
        fields: The row fields as split by the delimiter.
        layout: The column positions by role.
        latitude_value: Whether any earlier row carried a latitude value.
        longitude_value: Whether any earlier row carried a longitude value.

    Returns:
        The updated flags.
    """
    if layout.latitude is not None and layout.latitude < len(fields):
        latitude_value = latitude_value or bool(fields[layout.latitude].strip())
    if layout.longitude is not None and layout.longitude < len(fields):
        longitude_value = longitude_value or bool(fields[layout.longitude].strip())
    return latitude_value, longitude_value


def _evaluate_row(
    fields: list[str],
    lineno: int,
    header_len: int,
    layout: _Layout,
    seen: set[tuple[int, int]],
) -> _Row | document.RowIssue:
    """Evaluate one row against the ordered row rules.

    Args:
        fields: The row fields as split by the delimiter.
        lineno: The file line number for the issue record.
        header_len: The header field count for missing-cell padding.
        layout: The column positions by role.
        seen: The lattice positions already claimed by earlier rows.

    Returns:
        The accepted row, or the row's single issue.
    """
    padded = fields + [""] * (header_len - len(fields))
    parsed = _parse_row_tokens(padded, layout)
    if parsed is None:
        return document.RowIssue(line=lineno, reason="unparseable-row")
    impulse, scan_line, response, depth, metric_x, metric_y = parsed
    if impulse is None or scan_line is None:
        return document.RowIssue(line=lineno, reason="invalid-index-value")
    key = (impulse, scan_line)
    if key in seen:
        return document.RowIssue(line=lineno, reason="duplicate-coordinate")
    seen.add(key)
    return _Row(
        lineno=lineno,
        impulse=impulse,
        scan_line=scan_line,
        response=response,
        depth=depth,
        metric_x=metric_x[0],
        metric_y=metric_y[0],
        metric_x_raw=metric_x[1],
        metric_y_raw=metric_y[1],
    )


def _parse_row_tokens(
    padded: list[str], layout: _Layout
) -> (
    tuple[
        int | None,
        int | None,
        float | None,
        float | None,
        tuple[float | None, str],
        tuple[float | None, str],
    ]
    | None
):
    """Parse one row's numeric tokens, failing on any unparseable one.

    An empty index cell is not unparseable here; the index rule owns it.
    Depth travels for the interval, never as a spatial input.

    Args:
        padded: The row fields padded to the header length with empties.
        layout: The column positions by role.

    Returns:
        The impulse, scan line, response, depth and echo pairs, or None
        when any non-empty numeric token falls outside the numeral
        grammar.
    """
    for index in _numeric_positions(layout):
        token = padded[index].strip()
        if token and dialect.parse_numeral(token) is None:
            return None
    impulse = _parse_index(padded[layout.impulse])
    scan_line = _parse_index(padded[layout.scan_line])
    response = _parse_optional(padded[layout.response])
    depth = _parse_optional(padded[layout.depth]) if layout.depth is not None else None
    metric_x = _parse_echo(padded, layout.metric_x)
    metric_y = _parse_echo(padded, layout.metric_y)
    return impulse, scan_line, response, depth, metric_x, metric_y


def _parse_index(token: str) -> int | None:
    """Parse an index cell to its ordinal, None where the index rule fires.

    Args:
        token: The raw index cell.

    Returns:
        The integer ordinal, or None for an empty, non-integral or
        negative cell.
    """
    text = token.strip()
    if not text:
        return None
    value = dialect.parse_numeral(text)
    if value is None or not value.is_integer() or value < 0:
        return None
    return int(value)


def _parse_optional(token: str) -> float | None:
    """Parse a response cell, None where empty or padding.

    Unparseable tokens are refused upstream, so None here means padding.

    Args:
        token: The raw response cell.

    Returns:
        The value, or None for an empty cell.
    """
    text = token.strip()
    if not text:
        return None
    return dialect.parse_numeral(text)


def _parse_echo(padded: list[str], index: int | None) -> tuple[float | None, str]:
    """Parse a vendor echo cell without ever reading it as an input.

    Args:
        padded: The row fields padded to the header length with empties.
        index: The echo column position, or None when absent.

    Returns:
        The value with its raw text for the tolerance derivation.
    """
    if index is None:
        return None, ""
    text = padded[index].strip()
    if not text:
        return None, ""
    return dialect.parse_numeral(text), text


def _fraction_digits(token: str) -> int:
    """Count the printed fractional digits behind a metric token.

    Args:
        token: The raw metric token as written in the file.

    Returns:
        The digits after the dot, or zero where the token is integral.
    """
    head = token.strip().split("e")[0].split("E")[0]
    _, dot, fraction = head.partition(".")
    return len(fraction) if dot else 0


def _check_metrics(rows: list[_Row], extent: document.Extent) -> document.MetricCheck:
    """Cross-check the vendor echo against the derived series.

    Each axis is checked independently where its span is declared and its
    observed count defines a series, so one absent echo never silences the
    other. The expected series is the engine's own ``(index - 1) * span /
    (count - 1)`` per axis, compared at half a unit of the coarsest
    printed place. The echo is never read as an input: substituting it
    moves only this check.

    Args:
        rows: The accepted rows in file order.
        extent: The declared extent, absent where never declared.

    Returns:
        The check with its recorded tolerance and disagreements.
    """
    raw_x = [row.metric_x_raw for row in rows if row.metric_x_raw]
    raw_y = [row.metric_y_raw for row in rows if row.metric_y_raw]
    impulses = sorted({row.impulse for row in rows})
    scan_lines = sorted({row.scan_line for row in rows})
    check_x = bool(raw_x) and extent.field_length is not None and len(impulses) >= MIN_SERIES_COUNT
    check_y = bool(raw_y) and extent.field_width is not None and len(scan_lines) >= MIN_SERIES_COUNT
    if not check_x and not check_y:
        return document.MetricCheck(checked=False)
    digits = max(_fraction_digits(token) for token in raw_x + raw_y)
    tolerance = 0.5 * 10.0**-digits
    mismatches = _collect_mismatches(rows, impulses, scan_lines, extent, tolerance)
    return document.MetricCheck(checked=True, tolerance=tolerance, mismatches=mismatches)


def _collect_mismatches(
    rows: list[_Row],
    impulses: list[int],
    scan_lines: list[int],
    extent: document.Extent,
    tolerance: float,
) -> list[document.MetricMismatch]:
    """List the echo values disagreeing with the derived series.

    An axis without a declared span or with a single observed index is
    skipped, since no series can be derived for it.

    Args:
        rows: The accepted rows in file order.
        impulses: The observed impulse indices in order.
        scan_lines: The observed scan-line indices in order.
        extent: The declared extent behind the checkable axes.
        tolerance: The recorded comparison tolerance.

    Returns:
        The mismatches in file order, impulse axis before scan-line axis.
    """
    mismatches: list[document.MetricMismatch] = []
    mismatches.extend(_axis_mismatches(rows, "impulse", impulses, extent.field_length, tolerance))
    mismatches.extend(
        _axis_mismatches(rows, "scan-line", scan_lines, extent.field_width, tolerance)
    )
    return mismatches


def _axis_mismatches(
    rows: list[_Row],
    axis: Literal["impulse", "scan-line"],
    indices: list[int],
    span: float | None,
    tolerance: float,
) -> list[document.MetricMismatch]:
    """List one axis's echo values disagreeing with its derived series.

    The series is the engine's own, with position zero at index one, so
    no observed minimum is ever subtracted away.

    Args:
        rows: The accepted rows in file order.
        axis: The lattice axis under comparison.
        indices: The observed indices along the axis in order.
        span: The declared span, or None where never declared.
        tolerance: The recorded comparison tolerance.

    Returns:
        The axis mismatches in file order.
    """
    found: list[document.MetricMismatch] = []
    if span is None or len(indices) < MIN_SERIES_COUNT:
        return found
    for row in rows:
        observed = row.metric_x if axis == "impulse" else row.metric_y
        position = row.impulse if axis == "impulse" else row.scan_line
        if observed is None:
            continue
        expected = positions.field_coordinate(position, span, len(indices))
        if abs(observed - expected) > tolerance:
            found.append(
                document.MetricMismatch(
                    axis=axis,
                    impulse=row.impulse,
                    scan_line=row.scan_line,
                    expected=expected,
                    observed=observed,
                )
            )
    return found


def _discrepancies(
    impulses: list[int],
    scan_lines: list[int],
    rows: list[_Row],
    short_lines: list[int],
) -> list[document.Discrepancy]:
    """Record the observed facts the engine carries without repairing.

    Positions travel exactly as exported. The observed corpus base is 1 on
    every real export, so a minimum other than 1 is recorded as evidence
    this export was produced differently, and a non-zero metric origin is
    recorded rather than subtracted away. A short line is never filled.

    Args:
        impulses: The observed impulse indices in order.
        scan_lines: The observed scan-line indices in order.
        rows: The accepted rows in file order.
        short_lines: The short data lines by file line number.

    Returns:
        The discrepancies in a fixed kind order.
    """
    found: list[document.Discrepancy] = []
    if impulses and impulses[0] != 1:
        detail = f"impulse minimum is {impulses[0]}, carried as exported"
        found.append(document.Discrepancy(kind="index-origin", detail=detail))
    if scan_lines and scan_lines[0] != 1:
        detail = f"scan-line minimum is {scan_lines[0]}, carried as exported"
        found.append(document.Discrepancy(kind="index-origin", detail=detail))
    metric_x = [row.metric_x for row in rows if row.metric_x is not None]
    metric_y = [row.metric_y for row in rows if row.metric_y is not None]
    if metric_x and dialect.is_nonzero(min(metric_x)):
        detail = "impulse echo minimum is non-zero"
        found.append(document.Discrepancy(kind="metric-origin", detail=detail))
    if metric_y and dialect.is_nonzero(min(metric_y)):
        detail = "scan-line echo minimum is non-zero"
        found.append(document.Discrepancy(kind="metric-origin", detail=detail))
    found.extend(
        document.Discrepancy(
            kind="short-line", detail=f"line {lineno} carries fewer fields than the modal length"
        )
        for lineno in short_lines
    )
    return found


def _presence(column: int | None, *, has_value: bool) -> document.PresenceState:
    """Fold a discarded column into its presence state.

    Args:
        column: The column position, or None when the export omits it.
        has_value: Whether any row carried a non-empty cell.

    Returns:
        Absent, present-but-empty, or present-with-value.
    """
    if column is None:
        return "absent"
    if has_value:
        return "present-with-value"
    return "present-but-empty"


def _measured_responses(rows: list[_Row]) -> dict[tuple[int, int], float]:
    """Collect measured responses keyed by lattice coordinate.

    Args:
        rows: The accepted rows in file order.

    Returns:
        Responses over measured cells only, padding excluded.
    """
    measured: dict[tuple[int, int], float] = {}
    for row in rows:
        if row.response is not None:
            measured[row.impulse, row.scan_line] = row.response
    return measured


def _residual_map(rows: list[_Row]) -> dict[tuple[int, int], float]:
    """Reduce the measured responses to residuals under the pinned background.

    Args:
        rows: The accepted rows in file order.

    Returns:
        The residual per measured coordinate, in original units.
    """
    return background.residuals(_measured_responses(rows))


def _read_cells(rows: list[_Row], remaining: dict[tuple[int, int], float]) -> list[document.Cell]:
    """Build the cell records with residuals in file order.

    Args:
        rows: The accepted rows in file order.
        remaining: The residual per measured coordinate, in original units.

    Returns:
        One cell per row, carrying a null residual where padding.
    """
    return [
        document.Cell(
            impulse=row.impulse,
            scan_line=row.scan_line,
            response=row.response,
            residual=None if row.response is None else remaining[row.impulse, row.scan_line],
        )
        for row in rows
    ]


class _DetectionContext(NamedTuple):
    """Per-scan facts behind one detection's descriptors and tallies."""

    depths: dict[tuple[int, int], float | None]
    field_length: float | None
    field_width: float | None
    impulse_count: int
    scan_line_count: int
    bounds: tuple[int, int, int, int]
    unmeasured: frozenset[tuple[int, int]]
    payload_hash: str


def _sample_depths(
    depths: dict[tuple[int, int], float | None], coords: list[tuple[int, int]]
) -> list[float]:
    """Collect one detection's carried depth values, skipping gaps.

    Args:
        depths: Device values over measured cells, None where unvalued.
        coords: The detection's lattice coordinates in lattice order.

    Returns:
        The carried values, empty where no sample carries one.
    """
    found: list[float] = []
    for key in coords:
        value = depths.get(key)
        if value is not None:
            found.append(value)
    return found


def _to_cells(coords: Sequence[tuple[int, int]]) -> list[document.DetectionCell]:
    """Record lattice coordinates in lattice order.

    Args:
        coords: Impulse and scan-line pairs in lattice order.

    Returns:
        One record cell per coordinate.
    """
    return [
        document.DetectionCell(impulse=impulse, scan_line=scan_line)
        for impulse, scan_line in coords
    ]


def _field_position(
    representative: tuple[int, int], context: _DetectionContext
) -> tuple[document.FieldPosition | None, document.WithheldReason | None]:
    """Express one detection in the operator-declared extent, or withhold.

    Each axis is index-minus-one times its own pitch, inhomogeneity
    aside: the two axes stay meaningful alone, and only their product
    needs one unit.

    Args:
        representative: The detection's lattice-first coordinates.
        context: The scan's depths, geometry and boundary facts.

    Returns:
        The field position with no reason, or no position with the
        named cause.
    """
    if context.field_length is None or context.field_width is None:
        return None, "requires-declared-extent"
    if (
        context.impulse_count < positions.MIN_PITCH_COUNT
        or context.scan_line_count < positions.MIN_PITCH_COUNT
    ):
        return None, "requires-homogeneous-axes"
    impulse, scan_line = representative
    pitch_x = positions.pitch_span(context.field_length, context.impulse_count)
    pitch_y = positions.pitch_span(context.field_width, context.scan_line_count)
    return document.FieldPosition(
        frame="scan-local",
        origin="operator-marked-starting-point",
        origin_limitation="origin-unverifiable-and-unlocatable",
        along_line=document.FieldAxis(
            name="along-line",
            coordinate=positions.field_coordinate(
                impulse, context.field_length, context.impulse_count
            ),
            scale=document.Scale(
                span=context.field_length,
                count=context.impulse_count,
                quotient=pitch_x,
            ),
        ),
        across_lines=document.FieldAxis(
            name="across-lines",
            coordinate=positions.field_coordinate(
                scan_line, context.field_width, context.scan_line_count
            ),
            scale=document.Scale(
                span=context.field_width,
                count=context.scan_line_count,
                quotient=pitch_y,
            ),
        ),
    ), None


def _read_detection(
    item: hierarchy.DetectionData, context: _DetectionContext
) -> document.Detection:
    """Record one hierarchy node with its descriptors and tallies.

    Args:
        item: The node's identity, number, polarity, birth and cells.
        context: The scan's depths, geometry and boundary facts.

    Returns:
        The detection carrying positions, solidity, compactness, field
        area, depth interval, boundary facts and size in cells.

    Raises:
        ValueError: When a withheld position names no cause, which the
            pairing contract forbids.
    """
    coords = list(item.cells)
    representative = coords[0]
    scan_local = document.ScanLocalPosition(
        frame="scan-local",
        origin="operator-marked-starting-point",
        origin_limitation="origin-unverifiable-and-unlocatable",
        along_line=document.ScanLocalAxis(name="along-line", index=representative[0]),
        across_lines=document.ScanLocalAxis(name="across-lines", index=representative[1]),
    )
    field_position, no_reason = _field_position(representative, context)
    if field_position is None:
        if no_reason is None:
            msg = "a withheld position names its cause"
            raise ValueError(msg)
        area = descriptors.AreaResult(None, no_reason)
    else:
        area = descriptors.field_area(
            len(coords),
            field_position.along_line.scale.quotient,
            field_position.across_lines.scale.quotient,
        )
    interval = descriptors.depth_interval(_sample_depths(context.depths, coords))
    boundary, adjacent = descriptors.split_boundary(coords, context.bounds, context.unmeasured)
    return document.Detection(
        identity=item.identity,
        number=item.number,
        polarity=item.polarity,
        birth_level=item.birth,
        cells=_to_cells(coords),
        cell_count=len(coords),
        scan_local_position=scan_local,
        field_position=field_position,
        no_field_position_reason=no_reason,
        solidity=descriptors.solidity(coords),
        compactness=descriptors.compactness(coords),
        field_area=area.value,
        field_area_withheld=area.withheld,
        depth=(
            document.DepthInterval(minimum=interval[0], maximum=interval[1])
            if interval is not None
            else None
        ),
        lattice_boundary_cells=_to_cells(boundary),
        padding_adjacent_cells=_to_cells(adjacent),
        scan_payload_hash=context.payload_hash,
        shared_frame_position=None,
        no_shared_position_reason="missing-orientation-path",
    )


def _detection_context(
    rows: list[_Row],
    extent: document.Extent,
    impulses: list[int],
    scan_lines: list[int],
) -> _DetectionContext:
    """Gather the per-scan facts behind detection descriptors.

    Args:
        rows: The accepted rows in file order.
        extent: The declared extent, absent where never declared.
        impulses: The observed impulse indices in order.
        scan_lines: The observed scan-line indices in order.

    Returns:
        Depths over measured cells with geometry and boundary facts.
    """
    depths: dict[tuple[int, int], float | None] = {}
    for row in rows:
        if row.response is not None:
            depths[row.impulse, row.scan_line] = row.depth
    box = frozenset((impulse, scan_line) for impulse in impulses for scan_line in scan_lines)
    if impulses and scan_lines:
        bounds = (impulses[0], impulses[-1], scan_lines[0], scan_lines[-1])
    else:
        bounds = (0, 0, 0, 0)
    return _DetectionContext(
        depths=depths,
        field_length=extent.field_length,
        field_width=extent.field_width,
        impulse_count=len(impulses),
        scan_line_count=len(scan_lines),
        bounds=bounds,
        unmeasured=box - frozenset(depths),
        payload_hash=frames.payload_hash(_measured_responses(rows)),
    )


def _read_hierarchy(
    tree: hierarchy.HierarchyData, context: _DetectionContext
) -> document.Hierarchy:
    """Build the threshold-free hierarchy over one scan's residuals.

    Args:
        tree: The built tree with its tallies.
        context: The scan's depths, geometry and boundary facts.

    Returns:
        The component hierarchy with its detections and parent map.
    """
    detections = [_read_detection(item, context) for item in tree.detections]
    return document.Hierarchy(
        measured_cells=tree.measured_cells,
        cells_in_hierarchy=tree.cells_in_hierarchy,
        levels_positive=list(tree.levels_positive),
        levels_negative=list(tree.levels_negative),
        detections=detections,
        parents=list(tree.parents),
        detection_counts=[
            document.DetectionCount(
                polarity=tally.polarity, count=tally.total, denominator=tree.measured_cells
            )
            for tally in tree.detection_counts
        ],
        component_counts=[
            document.ComponentCount(
                polarity=tally.polarity,
                level=tally.level,
                count=tally.total,
                denominator=tree.measured_cells,
            )
            for tally in tree.component_counts
        ],
    )


def _read_robust_scale(remaining: dict[tuple[int, int], float]) -> document.RobustScale:
    """Estimate the robust scale of one scan residual field.

    The scale comes from the residual field per scan, never per
    detection, so a level never depends on a detection. Both estimators
    target sigma from one shared calibration, the atom fraction travels
    exact, and a tie stays a tie rather than triggering a fallback.

    Args:
        remaining: The residual per measured coordinate, in original units.

    Returns:
        The scale record with both estimates and its verdict.
    """
    result = scale.estimate(list(remaining.values()))
    return document.RobustScale(
        status=result.status,
        sigma_mad=result.sigma_mad,
        sigma_iqr=result.sigma_iqr,
        disagreement=result.disagreement,
        tolerance=result.tolerance,
        median_atom_numerator=result.median_atom_numerator,
        median_atom_denominator=result.median_atom_denominator,
    )


def _normalised_or_none(levels: tuple[float, ...], agreed: float) -> list[float] | None:
    """Normalise one polarity levels, None where unrepresentable.

    Args:
        levels: The raw residual magnitudes of one polarity.
        agreed: The agreed positive finite scale.

    Returns:
        The levels in sigma units, or None when any quotient is not
        finite, so no non-finite value is ever representable.
    """
    normalised = [level / agreed for level in levels]
    if all(math.isfinite(value) for value in normalised):
        return normalised
    return None


def _tie_view(
    tree: hierarchy.HierarchyData, sigma_mad: float | None, sigma_iqr: float | None
) -> document.ScaleNormalisedView:
    """Emit the view on a tie, or withhold where it cannot be performed.

    Args:
        tree: The built tree with its raw residual levels.
        sigma_mad: The median estimate, possibly undefined.
        sigma_iqr: The interquartile estimate, possibly undefined.

    Returns:
        The emitted view with normalised levels, or the not-emitted
        view where no positive finite scale exists to divide by.
    """
    if sigma_mad is None or sigma_iqr is None:
        return document.ScaleNormalisedView(
            status="not-emitted", reason="scale-not-positive-finite"
        )
    agreed = max(sigma_mad, sigma_iqr)
    if not (agreed > 0.0 and math.isfinite(agreed)):
        return document.ScaleNormalisedView(
            status="not-emitted", reason="scale-not-positive-finite"
        )
    positive = _normalised_or_none(tuple(tree.levels_positive), agreed)
    negative = _normalised_or_none(tuple(tree.levels_negative), agreed)
    if positive is None or negative is None:
        return document.ScaleNormalisedView(
            status="not-emitted", reason="scale-not-positive-finite"
        )
    return document.ScaleNormalisedView(
        status="emitted",
        scale=agreed,
        levels_positive=positive,
        levels_negative=negative,
    )


def _withheld_view(status: scale.ScaleStatus) -> document.ScaleNormalisedView:
    """Return the withheld view for a non-tie scale status.

    Args:
        status: The scale verdict deciding the reason.

    Returns:
        The not-emitted view where the scale is zero or undefined, and
        the indeterminate view where positive estimates disagree, since
        what failed there is a warrant and not a computation.
    """
    if status in {"no-finite-residual-values", "constant-field", "median-atom-zero-scale"}:
        return document.ScaleNormalisedView(
            status="not-emitted", reason="scale-not-positive-finite"
        )
    return document.ScaleNormalisedView(status="indeterminate", reason="scale-not-warranted")


def _read_scale_view(
    tree: hierarchy.HierarchyData, result: scale.ScaleResult
) -> document.ScaleNormalisedView:
    """Withhold or emit the scale-normalised view for one scan.

    Zero or undefined scale makes it not-emitted with its computation
    reason; positive but disagreeing estimates make it indeterminate
    with its warrant reason, since what failed there is a warrant and
    not a computation. Only a tie emits, and agreement is never recorded
    as evidence of convergence. Nothing else depends on the scale.

    Args:
        tree: The built tree with its raw residual levels.
        result: The scale record deciding the view.

    Returns:
        The view, emitted with normalised levels or withheld with its
        named reason.
    """
    if result.status == "tie":
        return _tie_view(tree, result.sigma_mad, result.sigma_iqr)
    return _withheld_view(result.status)


def _read_guard(
    remaining: dict[tuple[int, int], float],
    tree: hierarchy.HierarchyData,
    declared: document.PerturbationBound | None,
) -> document.MaskInvariance:
    """Decide the mask-invariance guard for one scan from its own field.

    Compared levels are every hierarchy level of both polarities, and the
    domain is finite measured cells only. A birth cell sits exactly at its
    threshold, so any field with a nonzero cell reads not-guaranteed with
    no special case; with nothing compared, nothing is established either.

    Args:
        remaining: The residual per measured coordinate, in original units.
        tree: The built tree carrying every compared level.
        declared: The scan's perturbation bound, or None where undeclared.

    Returns:
        The guard with its state, both conventions, and both corollaries.
    """
    cells = [value for value in remaining.values() if math.isfinite(value)]
    thresholds = list(tree.levels_positive) + list(tree.levels_negative)
    bound = (
        perturbation.Bound(
            amplitude=declared.amplitude,
            boundedness=declared.boundedness,
            anchor=declared.anchor,
        )
        if declared is not None
        else None
    )
    decided = perturbation.decide(cells, thresholds, bound)
    return document.MaskInvariance(
        status=decided.status,
        reason=decided.reason,
        ordering_invariance=decided.ordering_invariance,
        magnitude_invariance=decided.magnitude_invariance,
    )


def _chance_shifts() -> tuple[tuple[int, int], ...]:
    """Return the chance window: candidates shifted by the fixed vector.

    The chance baseline displaces by ``(1, 0)``, larger than the zero-cell
    match tolerance, so realigning that displacement reads the shifted
    window. One construction serves both registration drift and the
    recurrence contract.

    Returns:
        The shifted shifts in deterministic sorted order.
    """
    dy, dx = registration.CHANCE_DISPLACEMENT
    return tuple(
        sorted(
            (shift_dy - dy, shift_dx - dx) for shift_dy, shift_dx in registration.CANDIDATE_SHIFTS
        )
    )


def _best_of(
    responses: dict[tuple[int, int], float], shifts: Sequence[tuple[int, int]]
) -> float | None:
    """Return the best defined correlation over one shift window.

    Args:
        responses: Measured responses keyed by lattice coordinate.
        shifts: The shifts to consider, in deterministic order.

    Returns:
        The maximal correlation, or None where fewer than two define one.
    """
    summary = registration.summarise(registration.score_shifts(responses, shifts))
    return summary.best if summary is not None else None


def _perturbed_window(bound: document.DisplacementBound) -> tuple[tuple[int, int], ...]:
    """Return the perturbed shift window for one recorded displacement.

    Candidate positions are integers, so the float amplitude perturbs them
    by its integer truncation along the chance axis. Every perturbed shift
    stays integral, so no interpolation ever occurs.

    Args:
        bound: The recorded bounded displacement bound.

    Returns:
        The union of shifts with their perturbed positions, deduplicated
        in deterministic sorted order.
    """
    vector = registration.perturbation_vector(bound.amplitude)
    return registration.shifted_union(registration.CANDIDATE_SHIFTS, vector)


def _stability_of(
    summary: registration.Summary | None, perturbed: registration.Summary | None
) -> bool | None:
    """Decide argmax stability between two summaries.

    Args:
        summary: The summary over the original shifts, if scorable.
        perturbed: The summary over the perturbed window, if scorable.

    Returns:
        True where both define the same absolute winners, False where
        they differ, and None where either side is not scorable.
    """
    if summary is None or perturbed is None:
        return None
    first = {(item.dy, item.dx) for item in summary.winners}
    second = {(item.dy, item.dx) for item in perturbed.winners}
    return first == second


def _drift_of(
    summary: registration.Summary | None, perturbed: registration.Summary | None
) -> float | None:
    """Return the margin drift between two summaries.

    Args:
        summary: The summary over the original shifts, if scorable.
        perturbed: The summary over the perturbed window, if scorable.

    Returns:
        The absolute margin change, or None where either margin is missing.
    """
    if summary is None or perturbed is None:
        return None
    return abs((summary.best - summary.second) - (perturbed.best - perturbed.second))


def _registration_verdict(
    summary: registration.Summary | None,
    tolerance: float,
    bound: document.DisplacementBound | None,
    *,
    stable: bool | None,
) -> tuple[
    registration.RegistrationStatus,
    registration.RegistrationReason | None,
    float | None,
    float | None,
]:
    """Decide the registration status with its margin and correlation.

    Precedence is fixed: scorable shifts first, then the non-unique
    argmax, then the tie within the recorded bound, then the missing or
    unbounded displacement, and finally the instability under the recorded
    perturbation. Each names which check failed.

    Args:
        summary: The summary over the original shifts, if scorable.
        tolerance: The derived floating-point bound for the scan.
        bound: The recorded displacement bound, or None where undeclared.
        stable: The stability decision, or None where not scorable.

    Returns:
        The status with its reason, margin and correlation, the latter
        two reported wherever computable.
    """
    margin: float | None = None
    correlation: float | None = None
    status: registration.RegistrationStatus = "not-emitted"
    reason: registration.RegistrationReason | None = "requires-scorable-shifts"
    if summary is not None:
        margin = summary.best - summary.second
        correlation = summary.best
        status, reason = _verdict_defined(summary, margin, tolerance, bound, stable=stable)
    return status, reason, margin, correlation


def _verdict_defined(
    summary: registration.Summary,
    margin: float,
    tolerance: float,
    bound: document.DisplacementBound | None,
    *,
    stable: bool | None,
) -> tuple[registration.RegistrationStatus, registration.RegistrationReason | None]:
    """Decide the verdict where at least two shifts define a correlation.

    Args:
        summary: The summary over the original shifts.
        margin: The best minus second-best correlation.
        tolerance: The derived floating-point bound for the scan.
        bound: The recorded displacement bound, or None where undeclared.
        stable: The stability decision, or None where not scorable.

    Returns:
        The status with its reason, None where emitted.
    """
    reason: registration.RegistrationReason | None = None
    if len(summary.winners) > 1:
        reason = "non-unique-argmax"
    elif margin <= tolerance:
        reason = "tied-within-recorded-bound"
    elif bound is None:
        reason = "requires-recorded-displacement-bound"
    elif bound.boundedness == "unbounded":
        reason = "requires-bounded-displacement"
    elif stable is False:
        reason = "unstable-under-recorded-perturbation"
    elif stable is None:
        reason = "requires-scorable-shifts"
    status: registration.RegistrationStatus = (
        "emitted"
        if reason is None
        else (
            "indeterminate"
            if reason
            in {
                "non-unique-argmax",
                "tied-within-recorded-bound",
                "unstable-under-recorded-perturbation",
            }
            else "not-emitted"
        )
    )
    return status, reason


def _read_registration(
    responses: dict[tuple[int, int], float],
    bound: document.DisplacementBound | None,
) -> document.RegistrationEvidence:
    """Build self-alignment evidence for one scan from its responses.

    Margin, correlation, stability and drift travel separately with no
    composite anywhere. Shifts report in deterministic order, which fixes
    report order only. The scope is self-alignment only on every result,
    passing means well-defined and stable under the recorded bound rather
    than physically real, the separation criterion stays provisional, and
    the chance baseline measures chance correspondence. The accumulation
    length is the whole-scan measured count, which is the identity shift
    overlap behind the best correlation.

    Args:
        responses: Measured responses keyed by lattice coordinate.
        bound: The recorded displacement bound, or None where undeclared.

    Returns:
        The registration evidence with its four quantities and checks.
    """
    accumulation = len(responses)
    tolerance = registration.exact_tie_tolerance(accumulation)
    scores = registration.score_shifts(responses, registration.CANDIDATE_SHIFTS)
    summary = registration.summarise(scores)
    chance = _best_of(responses, _chance_shifts())
    perturbed = _perturbed_summary(responses, bound)
    stable = _stability_of(summary, perturbed)
    drift = _drift_of(summary, perturbed)
    status, reason, margin, correlation = _registration_verdict(
        summary, tolerance, bound, stable=stable
    )
    winner = _winner_of(summary)
    return document.RegistrationEvidence(
        status=status,
        reason=reason,
        margin=margin,
        correlation=correlation,
        argmax_dy=winner[0] if winner is not None else None,
        argmax_dx=winner[1] if winner is not None else None,
        argmax_stable=stable,
        margin_drift=drift,
        shift_count=len(registration.CANDIDATE_SHIFTS),
        scored_count=len(summary.defined) if summary is not None else 0,
        accumulation_length=accumulation,
        exact_tie_tolerance=tolerance,
        chance_dy=registration.CHANCE_DISPLACEMENT[0],
        chance_dx=registration.CHANCE_DISPLACEMENT[1],
        chance_correlation=chance,
        shifts=[
            document.RegistrationShift(
                dy=item.dy, dx=item.dx, correlation=item.correlation, overlap=item.overlap
            )
            for item in scores
        ],
    )


def _perturbed_summary(
    responses: dict[tuple[int, int], float],
    bound: document.DisplacementBound | None,
) -> registration.Summary | None:
    """Summarise the perturbed window, or nothing where undeclared.

    Args:
        responses: Measured responses keyed by lattice coordinate.
        bound: The recorded displacement bound, or None where undeclared.

    Returns:
        The perturbed summary where bounded, else None.
    """
    if bound is None or bound.boundedness == "unbounded":
        return None
    return registration.summarise(registration.score_shifts(responses, _perturbed_window(bound)))


def _winner_of(summary: registration.Summary | None) -> tuple[int, int] | None:
    """Return the single winner shift, or nothing where ambiguous.

    Args:
        summary: The summary over the original shifts, if scorable.

    Returns:
        The winner coordinates where exactly one shift wins, else None.
    """
    if summary is None or len(summary.winners) != 1:
        return None
    only = summary.winners[0]
    return (only.dy, only.dx)


def _raise_on_issues(table: _Table) -> None:
    """Refuse the scan where any row fails, naming the first failure.

    Args:
        table: The evaluated measuring block with its row issues.

    Raises:
        _RefusalError: Carrying the first failing reason with the full
            row breakdown, so one defect never arrives as a pile.
    """
    if table.issues:
        first = table.issues[0]
        detail = f"{len(table.issues)} failing rows, first at line {first.line}"
        raise _RefusalError(first.reason, detail, tuple(table.issues))


def _header_line(measuring: _Block) -> str:
    """Return the measuring header line, refusing an empty block.

    Args:
        measuring: The measuring section with its content lines.

    Returns:
        The raw header line.

    Raises:
        _RefusalError: When the block carries no header at all.
    """
    if not measuring.lines:
        detail = "Measuring Values carries no header"
        raise _RefusalError(_MISSING_REQUIRED, detail, ())
    return measuring.lines[0][1]


def _read_scan_inner(
    text: str,
    position: int,
    field_bound: document.PerturbationBound | None,
    registration_bound: document.DisplacementBound | None,
) -> document.ScanRead | document.ScanRefused:
    """Read one decoded export through both registries to its record.

    Args:
        text: The decoded export text.
        position: The intake position identifying the scan without a path.
        field_bound: The scan's perturbation bound, or None where undeclared.
        registration_bound: The scan's displacement bound, or None where
            undeclared.

    Returns:
        The read record, or the refusal with its reason and row breakdown.
    """
    blocks = _collect_sections(text.splitlines())
    measuring = blocks[MEASURING_KEY]
    header_line = _header_line(measuring)
    delimiter = _choose_delimiter(header_line)
    header_cells = header_line.split(delimiter)
    entries = _map_columns(header_cells)
    layout = _layout(entries)
    extent = _read_extent(blocks)
    _check_soil(blocks)
    _check_row_commas(measuring.lines[1:], delimiter, layout)
    table = _evaluate_rows(measuring.lines[1:], delimiter, len(header_cells), layout)
    _raise_on_issues(table)
    impulses = sorted({row.impulse for row in table.rows})
    scan_lines = sorted({row.scan_line for row in table.rows})
    remaining = _residual_map(table.rows)
    context = _detection_context(table.rows, extent, impulses, scan_lines)
    built = hierarchy.build(remaining)
    shape = scale.estimate(list(remaining.values()))
    return document.ScanRead(
        status="read",
        position=position,
        sections=sorted(entry.name for entry in _present_sections(blocks)),
        columns=sorted(entry.name for entry in entries),
        lattice=document.Lattice(impulses=impulses, scan_lines=scan_lines),
        cells=_read_cells(table.rows, remaining),
        background_model=document.BackgroundModel(),
        robust_scale=_read_robust_scale(remaining),
        scale_normalised_view=_read_scale_view(built, shape),
        perturbation_bound=field_bound,
        displacement_bound=registration_bound,
        mask_invariance=_read_guard(remaining, built, field_bound),
        registration=_read_registration(_measured_responses(table.rows), registration_bound),
        hierarchy=_read_hierarchy(built, context),
        extent=extent,
        latitude_presence=_presence(layout.latitude, has_value=table.latitude_value),
        longitude_presence=_presence(layout.longitude, has_value=table.longitude_value),
        payload_hash=context.payload_hash,
        metric_check=_check_metrics(table.rows, extent),
        discrepancies=_discrepancies(impulses, scan_lines, table.rows, table.short_lines),
    )


def _present_sections(blocks: dict[str, _Block]) -> list[input_contract.SectionEntry]:
    """List the registry entries behind the present sections.

    Args:
        blocks: The present sections keyed by normalised name.

    Returns:
        One registry entry per present section.
    """
    return [
        entry for entry in input_contract.SECTIONS if input_contract.normalise(entry.name) in blocks
    ]


def _read_scan(
    text: str,
    position: int,
    field_bound: document.PerturbationBound | None,
    registration_bound: document.DisplacementBound | None,
) -> document.ScanRead | document.ScanRefused:
    """Read one scan, converting its refusal into a record.

    Args:
        text: The decoded export text.
        position: The intake position identifying the scan without a path.
        field_bound: The scan's perturbation bound, or None where undeclared.
        registration_bound: The scan's displacement bound, or None where
            undeclared.

    Returns:
        The read record or the refusal record.
    """
    try:
        return _read_scan_inner(text, position, field_bound, registration_bound)
    except _RefusalError as refusal:
        return document.ScanRefused(
            position=position, reason=refusal.reason, detail=refusal.detail, rows=list(refusal.rows)
        )


def _scan_center(scan: document.ScanRead) -> tuple[float, float]:
    """Return one lattice center as index halves, exact in binary64.

    Args:
        scan: The read scan record.

    Returns:
        The impulse and scan-line midpoints.
    """
    impulses = scan.lattice.impulses
    lines = scan.lattice.scan_lines
    return frames.center_of_bounds(impulses[0], impulses[-1], lines[0], lines[-1])


def _shared_pitches(scan: document.ScanRead) -> tuple[float | None, float | None]:
    """Read one scan's pitches where definable, else absence per axis.

    Args:
        scan: The read scan record.

    Returns:
        Along-line with across-lines pitch, None where indefinable.
    """
    length = scan.extent.field_length
    width = scan.extent.field_width
    impulse_count = len(scan.lattice.impulses)
    line_count = len(scan.lattice.scan_lines)
    pitch_x = (
        positions.pitch_span(length, impulse_count)
        if length is not None and impulse_count >= positions.MIN_PITCH_COUNT
        else None
    )
    pitch_y = (
        positions.pitch_span(width, line_count)
        if width is not None and line_count >= positions.MIN_PITCH_COUNT
        else None
    )
    return pitch_x, pitch_y


def _shared_position(
    detection: document.Detection,
    scan: document.ScanRead,
    state: frames.ScanState,
    centers: dict[str, tuple[float, float]],
) -> tuple[document.SharedFramePosition | None, document.NoSharedReason | None]:
    """Express one detection in its shared frame, or name the cause.

    Scales come from the contributing scan's own declaration, swapped
    across odd relations, each recording which declaration supplied it.

    Args:
        detection: The detection with its scan-local position.
        scan: The contributing read scan record.
        state: The scan's frame outcome with its class.
        centers: Lattice centers keyed by frame name.

    Returns:
        The shared position with no reason, or no position with the
        missing-path or withdrawn-component cause.
    """
    if state.kind == "withdrawn":
        return None, "withdrawn-component"
    if state.frame is None or state.relation_class is None:
        return None, "missing-orientation-path"
    cell = detection.cells[0]
    along, across = frames.express(
        state.relation_class,
        _scan_center(scan),
        centers[state.frame],
        cell.impulse,
        cell.scan_line,
    )
    pitch_x, pitch_y = _shared_pitches(scan)
    spans: tuple[
        tuple[float | None, Literal["Field Length", "Field Width"]],
        tuple[float | None, Literal["Field Length", "Field Width"]],
    ]
    if frames.is_even_class(state.relation_class):
        spans = ((pitch_x, "Field Length"), (pitch_y, "Field Width"))
    else:
        spans = ((pitch_y, "Field Width"), (pitch_x, "Field Length"))
    (first, first_span), (second, second_span) = spans
    return document.SharedFramePosition(
        frame=state.frame,
        origin="operator-marked-starting-point",
        origin_limitation="origin-unverifiable-and-unlocatable",
        scan_local=detection.scan_local_position,
        along_line=document.SharedFrameAxis(
            name="along-line",
            index=along,
            scale=(
                document.SharedScale(
                    quotient=first,
                    declaration_scan=scan.payload_hash,
                    declaration_span=first_span,
                )
                if first is not None
                else None
            ),
        ),
        across_lines=document.SharedFrameAxis(
            name="across-lines",
            index=across,
            scale=(
                document.SharedScale(
                    quotient=second,
                    declaration_scan=scan.payload_hash,
                    declaration_span=second_span,
                )
                if second is not None
                else None
            ),
        ),
        homogeneous=(
            positions.same_pitch(first, second)
            if first is not None and second is not None
            else None
        ),
    ), None


def _frame_inputs(
    scans: list[document.ScanRead | document.ScanRefused],
) -> list[frames.ScanFrame | None]:
    """Collect frame inputs per intake position, None where refused.

    Args:
        scans: The read or refused scan records in intake order.

    Returns:
        Frame inputs aligned with intake positions.
    """
    inputs: list[frames.ScanFrame | None] = []
    for scan in scans:
        if scan.status != "read":
            inputs.append(None)
            continue
        impulses = scan.lattice.impulses
        lines = scan.lattice.scan_lines
        if impulses and lines:
            bounds = (impulses[0], impulses[-1], lines[0], lines[-1])
        else:
            bounds = (0, 0, 0, 0)
        inputs.append(
            frames.ScanFrame(
                scan.payload_hash,
                bounds[0],
                bounds[1],
                bounds[2],
                bounds[3],
                len(impulses),
                len(lines),
            )
        )
    return inputs


def _rebuild_detection(
    detection: document.Detection,
    scan: document.ScanRead,
    tree: frames.FramesData,
) -> document.Detection:
    """Rebuild one detection carrying its shared-frame expression.

    Args:
        detection: The phase-one detection with local facts only.
        scan: The contributing read scan record.
        tree: The built frames with per-scan states.

    Returns:
        The detection with its shared position or its named cause.
    """
    state = tree.states[scan.position]
    shared, reason = _shared_position(detection, scan, state, tree.centers)
    return document.Detection(**{
        **detection.model_dump(),
        "shared_frame_position": shared,
        "no_shared_position_reason": reason,
    })


def _rebuild_scan(
    scan: document.ScanRead | document.ScanRefused,
    tree: frames.FramesData,
) -> document.ScanRead | document.ScanRefused:
    """Rebuild one scan carrying shared positions and aspect verdicts.

    Args:
        scan: The read or refused scan record.
        tree: The built frames with per-scan states.

    Returns:
        The scan with frame branches attached, refusals untouched.
    """
    if scan.status != "read":
        return scan
    detections = [_rebuild_detection(item, scan, tree) for item in scan.hierarchy.detections]
    aspects = [
        document.AspectVerdict(
            first=verdict.first,
            second=verdict.second,
            relation=verdict.word,  # type: ignore[arg-type]
            verdict=verdict.verdict,
        )
        for verdict in tree.aspects
        if scan.position in {verdict.first, verdict.second}
    ]
    hierarchy = document.Hierarchy(**{**scan.hierarchy.model_dump(), "detections": detections})
    return document.ScanRead(**{
        **scan.model_dump(),
        "hierarchy": hierarchy,
        "aspect_checks": aspects,
    })


def _pair_dims(scan: document.ScanRead | document.ScanRefused) -> tuple[int, int] | None:
    """Return one scan lattice dimensions, or nothing where not read.

    Args:
        scan: The read or refused scan record.

    Returns:
        The impulse and scan-line counts, or None where refused.
    """
    if scan.status != "read":
        return None
    return (len(scan.lattice.impulses), len(scan.lattice.scan_lines))


def _has_direct_relation(tree: frames.FramesData, first: int, second: int) -> bool:
    """Report whether a declared edge directly connects one pair.

    Args:
        tree: The built frames with verbatim declared edges.
        first: One intake position.
        second: The other intake position.

    Returns:
        True where an edge names exactly those endpoints.
    """
    return any({edge.first, edge.second} == {first, second} for edge in tree.declared)


def _same_viable_frame(tree: frames.FramesData, first: int, second: int) -> bool:
    """Report whether two scans share one viable frame.

    Args:
        tree: The built frames with per-scan states.
        first: One intake position.
        second: The other intake position.

    Returns:
        True where both hold the same non-missing frame name.
    """
    first_state = tree.states[first]
    second_state = tree.states[second]
    return first_state.frame is not None and first_state.frame == second_state.frame


def _is_tainted(tree: frames.FramesData, position: int) -> bool:
    """Report whether one scan sits in a withdrawn component.

    Args:
        tree: The built frames with per-scan states.
        position: The intake position to inspect.

    Returns:
        True where contradictions withdrew its component.
    """
    return tree.states[position].kind == "withdrawn"


def _recurrence_pair(
    scans: Sequence[document.ScanRead | document.ScanRefused],
    tree: frames.FramesData,
    first: int,
    second: int,
) -> document.RecurrencePair:
    """Decide one pair with its indeterminate verdict and no match rate.

    Args:
        scans: The read or refused scan records in intake order.
        tree: The built frames with per-scan states.
        first: One intake position.
        second: The other intake position.

    Returns:
        The pair with decidable eligibility and its named reason.
    """
    eligibility, reason = registration.decide_recurrence(
        _pair_dims(scans[first]),
        _pair_dims(scans[second]),
        has_relation=_has_direct_relation(tree, first, second),
        contradictory=_is_tainted(tree, first) or _is_tainted(tree, second),
        same_frame=_same_viable_frame(tree, first, second),
    )
    status: Literal["indeterminate", "not-emitted"] = (
        "indeterminate" if eligibility == "eligible" else "not-emitted"
    )
    return document.RecurrencePair(
        first=first,
        second=second,
        eligibility=eligibility,
        reason=reason,
        status=status,
    )


def _recurrence_pairs(
    scans: Sequence[document.ScanRead | document.ScanRefused],
    tree: frames.FramesData,
) -> list[document.RecurrencePair]:
    """Decide every unordered pair in deterministic pair order.

    Args:
        scans: The read or refused scan records in intake order.
        tree: The built frames with per-scan states.

    Returns:
        One record per pair, first below second, with no match rate.
    """
    return [
        _recurrence_pair(scans, tree, first, second)
        for first in range(len(scans))
        for second in range(first + 1, len(scans))
    ]


def _attach_frames(
    scans: list[document.ScanRead | document.ScanRefused],
    relations: Sequence[frames.Relation],
) -> document.Document:
    """Relate whole lattices into shared frames without merging any.

    Args:
        scans: The read or refused scan records in intake order.
        relations: Declared relations over intake positions.

    Returns:
        The survey document with frames, echoes and contradictions.
    """
    tree = frames.build_frames(_frame_inputs(scans), relations)
    return document.Document(
        scans=[_rebuild_scan(scan, tree) for scan in scans],
        declared_relations=[
            document.DeclaredRelation(first=edge.first, second=edge.second, relation=edge.word)  # type: ignore[arg-type]
            for edge in tree.declared
        ],
        frames=[
            document.Frame(
                name=frame.name,
                label=frame.label,
                members=list(frame.members),
                relations=[
                    document.FrameRelation(scan=member.scan, relation_class=member.relation_class)
                    for member in frame.relations
                ],
            )
            for frame in tree.frames
        ],
        contradictions=[
            document.Contradiction(
                first=found.first,
                second=found.second,
                relation=found.word,  # type: ignore[arg-type]
                expected_class=found.expected_class,
                declared_class=found.declared_class,
            )
            for found in tree.contradictions
        ],
        recurrences=_recurrence_pairs(scans, tree),
    )


def read_document(
    contents: Sequence[bytes],
    relations: Sequence[frames.Relation] = (),
    perturbation_bounds: Sequence[document.PerturbationBound | None] = (),
    displacement_bounds: Sequence[document.DisplacementBound | None] = (),
) -> document.Document:
    """Read named exports in intake order to one survey document.

    One bad scan among several refuses only that scan. A file that cannot
    be decoded at all, or whose delimiter collides with the assumed decimal
    separator, stops the run instead. Declared relations over sorted
    intake positions relate whole lattices into shared frames. Positions
    index the sorted intake from zero with exact words, never repaired
    into a neighbour; a self-loop constrains uniformly like any edge.
    Declared bounds align with intake positions in the same order, one per
    scan with None where nothing was declared; a misaligned list stops the
    run rather than shifting a declaration onto the wrong scan.

    Args:
        contents: The raw export bytes in sorted intake order.
        relations: Declared relations over intake positions.
        perturbation_bounds: Declared field perturbation bounds in intake
            order, None per scan where undeclared.
        displacement_bounds: Declared registration displacement bounds in
            intake order, None per scan where undeclared.

    Returns:
        The survey document recording what was read and what was refused.

    Raises:
        UndecodableInputError: When a file cannot be decoded at all.
        ValueError: On an out-of-range position, an unknown word, or a
            misaligned bound list.
    """
    for relation in relations:
        frames.word_to_class(relation.word)
        if not 0 <= relation.first < len(contents) or not 0 <= relation.second < len(contents):
            msg = f"relation names no scan: {relation!r}"
            raise ValueError(msg)
    perturbations: list[document.PerturbationBound | None] = list(perturbation_bounds) or [
        None
    ] * len(contents)
    displacements: list[document.DisplacementBound | None] = list(displacement_bounds) or [
        None
    ] * len(contents)
    if len(perturbations) != len(contents):
        msg = f"perturbation bounds name no scan: {len(perturbations)} for {len(contents)}"
        raise ValueError(msg)
    if len(displacements) != len(contents):
        msg = f"displacement bounds name no scan: {len(displacements)} for {len(contents)}"
        raise ValueError(msg)
    scans: list[document.ScanRead | document.ScanRefused] = []
    for position, content in enumerate(contents):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            msg = f"scan {position} cannot be decoded as text"
            raise UndecodableInputError(msg) from exc
        scans.append(_read_scan(text, position, perturbations[position], displacements[position]))
    return _attach_frames(scans, relations)

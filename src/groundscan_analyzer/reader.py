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
import re
from typing import TYPE_CHECKING, Literal, NamedTuple

from groundscan_analyzer import dialect, document, input_contract

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
    """One evaluated row: lattice position, response and echo values."""

    lineno: int
    impulse: int
    scan_line: int
    response: float | None
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
    impulse, scan_line, response, metric_x, metric_y = parsed
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
        tuple[float | None, str],
        tuple[float | None, str],
    ]
    | None
):
    """Parse one row's numeric tokens, failing on any unparseable one.

    An empty index cell is not unparseable here; the index rule owns it.

    Args:
        padded: The row fields padded to the header length with empties.
        layout: The column positions by role.

    Returns:
        The impulse, scan line, response and echo pairs, or None when any
        non-empty numeric token falls outside the numeral grammar.
    """
    for index in _numeric_positions(layout):
        token = padded[index].strip()
        if token and dialect.parse_numeral(token) is None:
            return None
    impulse = _parse_index(padded[layout.impulse])
    scan_line = _parse_index(padded[layout.scan_line])
    response = _parse_optional(padded[layout.response])
    metric_x = _parse_echo(padded, layout.metric_x)
    metric_y = _parse_echo(padded, layout.metric_y)
    return impulse, scan_line, response, metric_x, metric_y


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
    other. The expected series is ``(index - minimum) * span / (count - 1)``
    per axis, compared at half a unit of the coarsest printed place. The
    echo is never read as an input: substituting it moves only this check.

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
    step = span / (len(indices) - 1)
    base = indices[0]
    for row in rows:
        observed = row.metric_x if axis == "impulse" else row.metric_y
        position = row.impulse if axis == "impulse" else row.scan_line
        if observed is None:
            continue
        expected = (position - base) * step
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


def _read_scan_inner(text: str, position: int) -> document.ScanRead | document.ScanRefused:
    """Read one decoded export through both registries to its record.

    Args:
        text: The decoded export text.
        position: The intake position identifying the scan without a path.

    Returns:
        The read record, or the refusal with its reason and row breakdown.

    Raises:
        _RefusalError: Any per-scan violation, converted by the caller.
    """
    blocks = _collect_sections(text.splitlines())
    measuring = blocks[MEASURING_KEY]
    if not measuring.lines:
        detail = "Measuring Values carries no header"
        raise _RefusalError(_MISSING_REQUIRED, detail, ())
    header_line = measuring.lines[0][1]
    delimiter = _choose_delimiter(header_line)
    header_cells = header_line.split(delimiter)
    entries = _map_columns(header_cells)
    layout = _layout(entries)
    extent = _read_extent(blocks)
    _check_soil(blocks)
    data = measuring.lines[1:]
    _check_row_commas(data, delimiter, layout)
    table = _evaluate_rows(data, delimiter, len(header_cells), layout)
    if table.issues:
        first = table.issues[0]
        detail = f"{len(table.issues)} failing rows, first at line {first.line}"
        raise _RefusalError(first.reason, detail, tuple(table.issues))
    metric_check = _check_metrics(table.rows, extent)
    impulses = sorted({row.impulse for row in table.rows})
    scan_lines = sorted({row.scan_line for row in table.rows})
    return document.ScanRead(
        status="read",
        position=position,
        sections=sorted(entry.name for entry in _present_sections(blocks)),
        columns=sorted(entry.name for entry in entries),
        lattice=document.Lattice(impulses=impulses, scan_lines=scan_lines),
        cells=[
            document.Cell(impulse=row.impulse, scan_line=row.scan_line, response=row.response)
            for row in table.rows
        ],
        extent=extent,
        latitude_presence=_presence(layout.latitude, has_value=table.latitude_value),
        longitude_presence=_presence(layout.longitude, has_value=table.longitude_value),
        metric_check=metric_check,
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


def _read_scan(text: str, position: int) -> document.ScanRead | document.ScanRefused:
    """Read one scan, converting its refusal into a record.

    Args:
        text: The decoded export text.
        position: The intake position identifying the scan without a path.

    Returns:
        The read record or the refusal record.
    """
    try:
        return _read_scan_inner(text, position)
    except _RefusalError as refusal:
        return document.ScanRefused(
            position=position, reason=refusal.reason, detail=refusal.detail, rows=list(refusal.rows)
        )


def read_document(contents: Sequence[bytes]) -> document.Document:
    """Read named exports in intake order to one survey document.

    One bad scan among several refuses only that scan. A file that cannot
    be decoded at all, or whose delimiter collides with the assumed decimal
    separator, stops the run instead.

    Args:
        contents: The raw export bytes in sorted intake order.

    Returns:
        The survey document recording what was read and what was refused.

    Raises:
        UndecodableInputError: When a file cannot be decoded at all.
    """
    scans: list[document.ScanRead | document.ScanRefused] = []
    for position, content in enumerate(contents):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            msg = f"scan {position} cannot be decoded as text"
            raise UndecodableInputError(msg) from exc
        scans.append(_read_scan(text, position))
    return document.Document(scans=scans)

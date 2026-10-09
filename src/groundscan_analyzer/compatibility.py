"""The compatibility gate: conformance with the contract, not correctness.

The nine real exports are read where the provenance set is present, and
what that proves is compatibility rather than correctness. The gate is
mostly a conformance check, and saying so plainly is the finding: eight of nine
real exports carry no defensible expectation and the ninth carries a negative,
so the gate re-derives the contract rules at run
time rather than pinning recorded magnitudes, which means no recorded
magnitude and no golden files and no drift when a convention is
declared. The rules are checked against the contract that is shipping,
not against a snapshot of it.

What the gate does assert is real: the definitional bounds, computed in
exact arithmetic where they can be. Solidity is bounded above by one
because occupied cells lie inside a hull that contains them, with the
hull computed from cell corners in integer arithmetic so no tolerance is
needed. Exactly 1.0 for convex sets is deliberately not asserted, since
it has earned its place on evidence rather than definition. Compactness
is bounded above by pi over four, which is sharper than one. Dominance
is at least one by definition, and at equality the numeric-tie rule
applies so the state carries rather than naming a strongest component.
Polarity well-formedness is asserted as the two classes being disjoint
and exhaustive over component cells, with no polarity value asserted
anywhere, because polarity is structurally exact by construction and
that exactness is a tempting reason to trust it.

Repeatability stays as a precondition check: two fresh processes,
byte-identical output. Survey order is owned elsewhere and is never
re-checked here; the four bounds this gate asserts each have exactly one
owner, stated in ``BOUND_OWNERS``, while field-area, detection-count,
component-count and the scale pair stay owned by their quantity registry
entries and are never re-checked here either.

The provenance set lives outside the repository. The gate names an
explicit path and per-file manifest hashes, because the files are vendor
educational material with their own manifest declaring they are not
independent ground truth, and a file a reader may not have is a
traceability fact rather than a reproducibility one. A missing file
reads as incomplete; a present file with the wrong bytes reads as a
distinct integrity failure. Nothing here is ever covered by synthetic
material.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
import sys
from typing import TYPE_CHECKING, Literal, NamedTuple

from groundscan_analyzer import descriptors, dialect, document, input_contract, oracles, reader
from groundscan_analyzer import property_registry as registry
from groundscan_analyzer import quantity_registry as quantities

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

__all__ = [
    "BOUND_OWNERS",
    "CORPUS_COUNT",
    "CORPUS_ENV_VAR",
    "CORPUS_HASHES",
    "DOMINANCE_WITHHELD",
    "CompatibilityReport",
    "DominanceOutcome",
    "check_files",
    "compactness_ok",
    "corpus_root",
    "describe_files",
    "dominance_for_peaks",
    "dominance_ok",
    "index_base_ok",
    "manifest_ok",
    "metric_tolerance_ok",
    "polarity_ok",
    "presence_ok",
    "repeatability_ok",
    "sha256_of",
    "solidity_ok",
    "sorted_corpus_files",
    "structure_ok",
    "two_fresh_runs",
]

CORPUS_ENV_VAR: Final[str] = "GROUNDSCAN_CORPUS_ROOT"

CORPUS_COUNT: Final[int] = 9

CORPUS_HASHES: Final[tuple[str, ...]] = (
    "7e368f435411a0214e06fc0055266fbe99809cac7f55c4fa2b09d9c270813c99",
    "244ab486eb6822528cfc3e19790d43e3a835c02d7a881bc9bbc6146fd6ef91f2",
    "ccfed788d30bf06582e82b09caec80d3dbb65ecccfb2261dc72b023359a2b9a5",
    "0a63220160b0dfda9d9f3c63d01aee6a0d968dceafa9923a68bda9a36e21e9df",
    "ce92779900cf735742fc4670223a658bc50031af0ff799b934f57e1818a4fdaa",
    "2164f6a133d2d47613ac5862793447a308fa5f631cbf73b67498ff2789d05359",
    "a34160df0e022823aaae5af4797031dccb8d4b99e911b0a4ae45e2c13b871b71",
    "65892b30b7fc9cee94898b56f9a2789f99e048a8bfe75777a796a1c02f5e51e8",
    "e035bcf589113160a1b5c24002213257d444a5be8b16378360c9b70d4f698823",
)

DOMINANCE_WITHHELD: Final[str] = "requires-two-components"

BOUND_OWNERS: Final[dict[str, str]] = {
    "solidity": "groundscan_analyzer.descriptors",
    "compactness": "groundscan_analyzer.descriptors",
    "dominance": "groundscan_analyzer.compatibility",
    "polarity": "groundscan_analyzer.compatibility",
}

_MIN_PEAKS: Final[int] = 2
_TIE_VALUE: Final[float] = 1.0

DominanceState = Literal["emitted", "tie-carries", "withheld-requires-two-components"]


class DominanceOutcome(NamedTuple):
    """One dominance reading with its state and optional ratio."""

    state: DominanceState
    value: float | None


class CompatibilityReport(NamedTuple):
    """Whether one file set passed every gate check."""

    files_checked: int
    solidity_ok: bool
    compactness_ok: bool
    dominance_ok: bool
    polarity_ok: bool
    contract_rules_ok: bool


def _bits(value: float) -> int:
    """Expose binary64 bits for exact comparison without a tolerance.

    Args:
        value: The float to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def _exact_equal(first: float, second: float) -> bool:
    """Report whether two floats are bitwise identical.

    A tolerance here would be a threshold wearing a gate's clothes, so
    ties are decided by identity, never by closeness.

    Args:
        first: One float under comparison.
        second: The other float under comparison.

    Returns:
        True exactly where both bit patterns match.
    """
    return _bits(first) == _bits(second)


def corpus_root() -> Path:
    """Return the explicit provenance-set path.

    Returns:
        The directory from the environment, or the local archaeology
        directory where a reader keeps their own copy.
    """
    override = os.environ.get(CORPUS_ENV_VAR)
    if override:
        return Path(override)
    repo = Path(__file__).resolve().parents[2]
    return repo / "docs" / "legacy" / "scans" / "vendor_demo"


def sorted_corpus_files(root: Path) -> tuple[Path, ...]:
    """List the provenance-set files in a fixed order.

    Args:
        root: The explicit directory holding the nine exports.

    Returns:
        The export paths sorted by name, empty where none are present.
    """
    try:
        found = sorted(root.glob("*.csv"))
    except OSError:
        return ()
    return tuple(found)


def sha256_of(path: Path) -> str:
    """Digest one file for the manifest comparison.

    Args:
        path: The file to digest.

    Returns:
        The hex digest of the file bytes.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_ok(files: Sequence[Path]) -> bool:
    """Report whether nine files match the manifest in order.

    Args:
        files: The sorted export paths.

    Returns:
        True exactly where nine digests match the nine recorded ones.
    """
    if len(files) != CORPUS_COUNT:
        return False
    try:
        digests = tuple(sha256_of(path) for path in files)
    except OSError:
        return False
    return digests == CORPUS_HASHES


def describe_files(files: Sequence[Path]) -> str:
    """Name the condition of a file set without reading its content.

    Args:
        files: The sorted export paths, possibly empty.

    Returns:
        Incomplete where files are missing, complete where the bytes
        match, else a distinct integrity note.
    """
    if len(files) != CORPUS_COUNT:
        return "incomplete"
    return "complete" if manifest_ok(files) else "integrity-failure"


def _quantity_upper(name: str) -> float | None:
    """Read one quantity bound from the shipping registry.

    Args:
        name: The quantity name as the registry carries it.

    Returns:
        The upper bound, or None where the registry leaves it open.
    """
    for entry in quantities.QUANTITIES:
        if entry.name == name:
            return entry.upper
    return None


def solidity_ok(cells: Sequence[tuple[int, int]], value: float) -> bool:
    """Report whether one solidity respects its definitional bound.

    The hull is recomputed in integer arithmetic through two independent
    walks, so no tolerance enters anywhere.

    Args:
        cells: The detection cells in lattice coordinates.
        value: The emitted solidity under check.

    Returns:
        True where the value sits in (0, 1] and both hull walks agree.
    """
    if not cells:
        return False
    upper = _quantity_upper("solidity")
    meets = upper is not None and 0.0 < value <= upper
    if not meets:
        return False
    oracle_area = oracles.oracle_hull_area8(cells)
    product_area = descriptors.hull_shoelace8(list(cells))
    same_walk = oracle_area == product_area
    inside = oracle_area >= 8 * len(list(cells))
    return same_walk and inside


def _perimeters_agree(cells: Sequence[tuple[int, int]]) -> bool:
    """Report whether two independent perimeter walks agree.

    Args:
        cells: The detection cells in lattice coordinates.

    Returns:
        True where the oracle and production perimeters match.
    """
    return oracles.oracle_perimeter(cells) == descriptors.exposed_perimeter(list(cells))


def compactness_ok(cells: Sequence[tuple[int, int]], value: float) -> bool:
    """Report whether one compactness respects pi over four.

    The perimeter counts exposed lattice edges including hole
    boundaries, and the inequality is exact integer arithmetic.

    Args:
        cells: The detection cells in lattice coordinates.
        value: The emitted compactness under check.

    Returns:
        True where the value sits in (0, pi/4] and both perimeters agree.
    """
    upper = _quantity_upper("compactness")
    meets = bool(cells) and upper is not None and 0.0 < value <= upper
    finite = math.isfinite(value)
    return bool(meets and finite and _perimeters_agree(cells)) and bool(
        oracles.perimeter_inequality_holds(cells)
    )


def dominance_for_peaks(peaks: Sequence[float]) -> DominanceOutcome:
    """Reduce peak magnitudes to a dominance reading with its state.

    At equality the numeric-tie rule applies: bitwise identity carries
    the tie state rather than naming a strongest component. Below two
    components the reading withholds with its named reason.

    Args:
        peaks: Absolute residual peaks per component, any order.

    Returns:
        The emitted ratio at or above one, the tie at exactly one, or
        the withheld state with no value.
    """
    ordered = sorted(peaks, reverse=True)
    if len(ordered) < _MIN_PEAKS:
        return DominanceOutcome("withheld-requires-two-components", None)
    first, second = ordered[0], ordered[1]
    if _exact_equal(first, second):
        return DominanceOutcome("tie-carries", _TIE_VALUE)
    if not second > 0.0:
        return DominanceOutcome("withheld-requires-two-components", None)
    return DominanceOutcome("emitted", first / second)


def _detection_peaks(scan: document.ScanRead, polarity: str) -> list[float]:
    """Collect absolute births for one polarity in document order.

    Args:
        scan: The read scan carrying the hierarchy.
        polarity: The polarity side to collect.

    Returns:
        The absolute birth magnitudes of that side.
    """
    return [
        abs(item.birth_level) for item in scan.hierarchy.detections if item.polarity == polarity
    ]


def _polarity_side_ok(scan: document.ScanRead, polarity: str) -> bool:
    """Report whether one polarity side respects its dominance rule.

    Args:
        scan: The read scan carrying the hierarchy.
        polarity: The polarity side under check.

    Returns:
        True where an emitted ratio reaches one, a tie carries one, or
        a short side withholds with no value.
    """
    outcome = dominance_for_peaks(_detection_peaks(scan, polarity))
    if outcome.state == "emitted":
        return outcome.value is not None and outcome.value >= _TIE_VALUE
    if outcome.state == "tie-carries":
        return outcome.value is not None and _exact_equal(outcome.value, _TIE_VALUE)
    return outcome.value is None


def dominance_ok(scan: document.ScanRead) -> bool:
    """Report whether both polarities respect dominance at or above one.

    Args:
        scan: The read scan carrying the hierarchy.

    Returns:
        True where every emitted ratio reaches one and every tie
        carries rather than naming a winner.
    """
    return _polarity_side_ok(scan, "positive") and _polarity_side_ok(scan, "negative")


def polarity_ok(scan: document.ScanRead) -> bool:
    """Report whether polarity partitions the component cells.

    The two classes are disjoint and exhaustive over component cells by
    construction, so exactness here is structural and no polarity value
    of any one detection is asserted.

    Args:
        scan: The read scan carrying the hierarchy.

    Returns:
        True where positive and negative cell sets are disjoint and
        their union is every detection cell.
    """
    positive: set[tuple[int, int]] = set()
    negative: set[tuple[int, int]] = set()
    every: set[tuple[int, int]] = set()
    for item in scan.hierarchy.detections:
        cells = {(cell.impulse, cell.scan_line) for cell in item.cells}
        every |= cells
        if item.polarity == "positive":
            positive |= cells
        else:
            negative |= cells
    return positive.isdisjoint(negative) and positive | negative == every


def _measuring_text(raw: bytes) -> str:
    """Decode raw export bytes the way the input path does.

    Args:
        raw: The raw export bytes.

    Returns:
        The decoded text with line endings normalised.
    """
    text = raw.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _is_registered(cell: str) -> bool:
    """Report whether one header cell names a registered column.

    Args:
        cell: The raw header cell as written in the file.

    Returns:
        True where the registry holds the name.
    """
    return input_contract.find_column(cell) is not None


def _measuring_block(raw: bytes) -> tuple[str, list[str], list[str]]:
    """Split one export into its measuring delimiter, header and data lines.

    The section is located through the shipping section registry and the
    delimiter through the shipping column registry, so both are
    re-derived at run time rather than pinned.

    Args:
        raw: The raw export bytes.

    Returns:
        The determined delimiter with the header cells and the data
        lines in file order, all empty where no measuring block reads.
    """
    lines = _measuring_text(raw).splitlines()
    start = _measuring_start(lines)
    if start is None:
        return ",", [], []
    header, header_at = _header_after(lines, start)
    if not header or header_at is None:
        return ",", [], []
    fitting = dialect.candidate_delimiters(header, _is_registered)
    chosen = fitting[0] if fitting else ","
    return chosen, header.split(chosen), _data_after(lines, header_at)


def _measuring_start(lines: list[str]) -> int | None:
    """Locate the measuring section through the shipping registry.

    Args:
        lines: The decoded export lines.

    Returns:
        The section line position, or None where none reads.
    """
    wanted = input_contract.normalise("Measuring Values")
    for position, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("+++") and stripped.endswith("+++"):
            inner = stripped.strip("+").strip()
            if input_contract.normalise(inner) == wanted:
                return position
    return None


def _header_after(lines: list[str], start: int) -> tuple[str, int | None]:
    """Return the header line after one section position.

    Args:
        lines: The decoded export lines.
        start: The section line position.

    Returns:
        The header line with its position, empty and None where absent.
    """
    for position in range(start + 1, len(lines)):
        if lines[position].strip():
            return lines[position], position
    return "", None


def _data_after(lines: list[str], header_at: int) -> list[str]:
    """Collect data lines after one header position.

    Args:
        lines: The decoded export lines.
        header_at: The header line position.

    Returns:
        The non-blank data lines before the next section.
    """
    data: list[str] = []
    for line in lines[header_at + 1 :]:
        if line.strip().startswith("+++"):
            break
        if line.strip():
            data.append(line)
    return data


def _role_at(header_cells: list[str], role: str) -> int | None:
    """Locate one required role in header cells through the registry.

    Args:
        header_cells: The header cells in file order.
        role: The registry role to locate.

    Returns:
        The column position, or None where the role is absent.
    """
    for position, cell in enumerate(header_cells):
        entry = input_contract.find_column(cell)
        if entry is not None and entry.role == role:
            return position
    return None


def _observed_indices(raw: bytes) -> tuple[list[int], list[int]]:
    """Collect observed lattice indices from raw export bytes.

    Args:
        raw: The raw export bytes behind the scan.

    Returns:
        The sorted impulse indices with the sorted scan-line indices.
    """
    delimiter, header_cells, data = _measuring_block(raw)
    impulse_at = _role_at(header_cells, "impulse")
    line_at = _role_at(header_cells, "scan-line")
    if impulse_at is None or line_at is None:
        return [], []
    impulses: set[int] = set()
    scan_lines: set[int] = set()
    for line in data:
        fields = line.split(delimiter)
        if impulse_at >= len(fields) or line_at >= len(fields):
            continue
        impulse = _parse_index_cell(fields[impulse_at])
        scan_line = _parse_index_cell(fields[line_at])
        if impulse is None or scan_line is None:
            continue
        impulses.add(impulse)
        scan_lines.add(scan_line)
    return sorted(impulses), sorted(scan_lines)


def _parse_index_cell(token: str) -> int | None:
    """Parse one index cell to its ordinal through the numeral grammar.

    Args:
        token: The raw index cell.

    Returns:
        The integer ordinal, or None where the index rule fires.
    """
    value = dialect.parse_numeral(token)
    if value is None or not value.is_integer() or value < 0:
        return None
    return int(value)


def index_base_ok(scan: document.ScanRead, raw: bytes) -> bool:
    """Report whether lattice indices travel exactly as exported.

    Positions are never re-based: the lattice carries the observed
    indices read from the file bytes through the shipping registries,
    and a minimum away from one is recorded rather than moved.

    Args:
        scan: The read scan carrying the lattice and discrepancies.
        raw: The raw export bytes behind the scan.

    Returns:
        True where the lattice matches the observed indices and the
        origin notes match the observed minima.
    """
    impulses, scan_lines = _observed_indices(raw)
    if scan.lattice.impulses != impulses or scan.lattice.scan_lines != scan_lines:
        return False
    low_impulse = bool(impulses and impulses[0] != 1)
    low_line = bool(scan_lines and scan_lines[0] != 1)
    wants_origin = low_impulse or low_line
    has_origin = any(item.kind == "index-origin" for item in scan.discrepancies)
    return wants_origin == has_origin


def _fraction_digits(token: str) -> int:
    """Count printed fractional digits behind one echo token.

    Args:
        token: The raw echo token as written in the file.

    Returns:
        Digits after the dot, or zero where the token is integral.
    """
    head = token.strip().split("e")[0].split("E")[0]
    _, dot, fraction = head.partition(".")
    return len(fraction) if dot else 0


def _echo_positions(header_cells: list[str]) -> tuple[int | None, int | None]:
    """Locate the vendor echo columns through the shipping registry.

    Args:
        header_cells: The header cells in file order.

    Returns:
        The impulse-echo position with the scan-line-echo position.
    """
    impulse_echo: int | None = None
    line_echo: int | None = None
    for position, cell in enumerate(header_cells):
        entry = input_contract.find_column(cell)
        if entry is None:
            continue
        if entry.role == "impulse-metric":
            impulse_echo = position
        elif entry.role == "scan-line-metric":
            line_echo = position
    return impulse_echo, line_echo


def _echo_tokens(raw: bytes) -> list[str]:
    """Collect raw echo tokens from one export for the tolerance walk.

    Args:
        raw: The raw export bytes behind the scan.

    Returns:
        The echo tokens in file order.
    """
    delimiter, header_cells, data = _measuring_block(raw)
    impulse_echo, line_echo = _echo_positions(header_cells)
    if impulse_echo is None and line_echo is None:
        return []
    tokens: list[str] = []
    for line in data:
        parts = line.split(delimiter)
        if impulse_echo is not None and impulse_echo < len(parts):
            tokens.append(parts[impulse_echo].strip())
        if line_echo is not None and line_echo < len(parts):
            tokens.append(parts[line_echo].strip())
    return tokens


def metric_tolerance_ok(scan: document.ScanRead, raw: bytes) -> bool:
    """Report whether the echo tolerance is derived from the file.

    The expected series is the engine's own index-minus-one times span
    over count-minus-one per axis, compared at half a unit of the
    coarsest printed place. The echo is never read as an input.

    Args:
        scan: The read scan carrying the cross-check.
        raw: The raw export bytes behind the scan.

    Returns:
        True where the recorded tolerance matches the derived one.
    """
    tokens = [token for token in _echo_tokens(raw) if token]
    if not tokens:
        return scan.metric_check.checked is False
    if scan.extent.field_length is None and scan.extent.field_width is None:
        return scan.metric_check.checked is False
    wanted = 0.5 * 10.0 ** -max(_fraction_digits(token) for token in tokens)
    recorded = scan.metric_check.tolerance
    if recorded is None:
        return False
    return _exact_equal(recorded, wanted)


def _header_of(raw: bytes) -> tuple[str, str]:
    """Return the discarded-coordinate header with its delimiter.

    Args:
        raw: The raw export bytes behind the scan.

    Returns:
        The delimiter with the header line naming both discarded
        columns, both empty where no such header reads.
    """
    delimiter, header_cells, _ = _measuring_block(raw)
    joined = delimiter.join(header_cells)
    if "Latitude" in joined and "Longitude" in joined:
        return delimiter, joined
    return "", ""


def _column_at(header: str, delimiter: str, name: str) -> int | None:
    """Locate one discarded column by its registry name.

    Args:
        header: The header line naming the discarded columns.
        delimiter: The determined delimiter splitting the header.
        name: The registry name to locate.

    Returns:
        The column position, or None where the registry lacks it.
    """
    cells = header.split(delimiter) if delimiter else header.split(",")
    for position, cell in enumerate(cells):
        if input_contract.normalise(cell) == name:
            return position
    return None


def _valued_flags(
    raw: bytes, header: str, delimiter: str, lat_at: int, lon_at: int
) -> tuple[bool, bool]:
    """Fold rows into valued flags for the discarded columns.

    Args:
        raw: The raw export bytes behind the scan.
        header: The header line naming the discarded columns.
        delimiter: The determined delimiter splitting each row.
        lat_at: The latitude column position.
        lon_at: The longitude column position.

    Returns:
        Whether any row valued latitude with longitude.
    """
    lat_valued = False
    lon_valued = False
    seen_header = False
    for line in _measuring_text(raw).splitlines():
        if not line.strip():
            continue
        if line == header and not seen_header:
            seen_header = True
            continue
        if not seen_header or line.strip().startswith("+++") or ":" in line:
            continue
        fields = line.split(delimiter)
        lat_valued = lat_valued or (lat_at < len(fields) and bool(fields[lat_at].strip()))
        lon_valued = lon_valued or (lon_at < len(fields) and bool(fields[lon_at].strip()))
    return lat_valued, lon_valued


def presence_ok(scan: document.ScanRead, raw: bytes) -> bool:
    """Report whether discarded presence states track the file.

    Only the state travels while the values themselves are dropped, so
    an absent column, an empty column and a valued column are three
    distinct facts.

    Args:
        scan: The read scan carrying the presence states.
        raw: The raw export bytes behind the scan.

    Returns:
        True where both presence states match the observed columns.
    """
    delimiter, header = _header_of(raw)
    if not header:
        no_lat = scan.latitude_presence == "absent"
        no_lon = scan.longitude_presence == "absent"
        return no_lat and no_lon
    lat_at = _column_at(header, delimiter, "latitude")
    lon_at = _column_at(header, delimiter, "longitude")
    if lat_at is None or lon_at is None:
        return False
    lat_valued, lon_valued = _valued_flags(raw, header, delimiter, lat_at, lon_at)
    want_lat = "present-with-value" if lat_valued else "present-but-empty"
    want_lon = "present-with-value" if lon_valued else "present-but-empty"
    return scan.latitude_presence == want_lat and scan.longitude_presence == want_lon


def _versions_match(doc: document.Document) -> bool:
    """Report whether versions match the shipping contract at run time.

    Args:
        doc: The survey document under check.

    Returns:
        True where every version travels beside the contract version.
    """
    same_contract = doc.contract_version == registry.CONTRACT_VERSION
    same_registry = doc.registry_version == registry.REGISTRY_VERSION
    same_quantities = doc.quantity_registry_version == quantities.QUANTITY_REGISTRY_VERSION
    same_separator = doc.decimal_separator == dialect.DECIMAL_SEPARATOR
    same_convention = doc.convention == dialect.CONVENTION
    return (
        same_contract and same_registry and same_quantities and same_separator and same_convention
    )


def _read_detections(entry: object) -> list[object]:
    """Return detection mappings of one read scan entry.

    Args:
        entry: One dumped scan mapping.

    Returns:
        The detection mappings, empty where the entry is not a read scan.
    """
    if not isinstance(entry, dict) or entry.get("status") != "read":
        return []
    hierarchy = entry.get("hierarchy", {})
    if not isinstance(hierarchy, dict):
        return [None]
    detections = hierarchy.get("detections", [])
    if not isinstance(detections, list):
        return [None]
    return detections


def _detections_carry_limitations(payload: dict[str, object]) -> bool:
    """Report whether every detection carries its limitations field.

    Args:
        payload: The dumped document mapping.

    Returns:
        True where the field is present even when empty.
    """
    scans = payload.get("scans", [])
    if not isinstance(scans, list):
        return False
    items = [item for entry in scans for item in _read_detections(entry)]
    return all(isinstance(item, dict) and "limitations" in item for item in items)


def _frames_carry_limitations(payload: dict[str, object]) -> bool:
    """Report whether every frame carries its limitations field.

    Args:
        payload: The dumped document mapping.

    Returns:
        True where the field is present even when empty.
    """
    frames = payload.get("frames", [])
    if not isinstance(frames, list):
        return False
    return all(isinstance(frame, dict) and "limitations" in frame for frame in frames)


def structure_ok(doc: document.Document) -> bool:
    """Check record structure through an independent schema walk.

    Versions are read from the shipping contract at run time, never
    pinned, and the limitations fields must be present even when empty.

    Args:
        doc: The survey document under check.

    Returns:
        True where versions match the shipping contract and every
        claim carries its limitations field, empty or not.
    """
    if not _versions_match(doc):
        return False
    payload = doc.model_dump(mode="json")
    if set(payload.keys()) != set(document.Document.model_fields.keys()):
        return False
    return _detections_carry_limitations(payload) and _frames_carry_limitations(payload)


def two_fresh_runs(path: Path) -> tuple[str, str]:
    """Run the scan subcommand in two fresh processes.

    Args:
        path: The export file the two processes both read.

    Returns:
        The two stdout payloads in run order.

    Raises:
        RuntimeError: When either fresh process exits non-zero.
    """
    code = (
        "import sys; from groundscan_analyzer.cli import main; "
        f"sys.exit(main(['scan', {str(path)!r}]))"
    )
    first = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv, no shell
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    second = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv, no shell
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    if first.returncode != 0 or second.returncode != 0:
        msg = "fresh processes must exit zero on a readable export"
        raise RuntimeError(msg)
    return first.stdout, second.stdout


def repeatability_ok(path: Path) -> bool:
    """Report whether two fresh processes emit byte-identical output.

    Args:
        path: The export file the two processes both read.

    Returns:
        True where both payloads are non-empty and identical.
    """
    first, second = two_fresh_runs(path)
    return bool(first) and first == second


def _scan_bounds_ok(scan: document.ScanRead) -> bool:
    """Report whether every detection respects solidity and compactness.

    Args:
        scan: The read scan under check.

    Returns:
        True where every detection sits inside both definitional bounds.
    """
    result = True
    for item in scan.hierarchy.detections:
        cells = [(cell.impulse, cell.scan_line) for cell in item.cells]
        result = result and solidity_ok(cells, item.solidity)
        result = result and compactness_ok(cells, item.compactness)
    return result


def _scan_rules_ok(scan: document.ScanRead, raw: bytes) -> bool:
    """Report whether re-derived contract rules hold for one scan.

    Args:
        scan: The read scan under check.
        raw: The raw export bytes behind the scan.

    Returns:
        True where index base, echo tolerance and presence all track.
    """
    base = index_base_ok(scan, raw)
    tolerance = metric_tolerance_ok(scan, raw)
    presence = presence_ok(scan, raw)
    return base and tolerance and presence


def check_scan(scan: document.ScanRead, raw: bytes) -> bool:
    """Report whether one scan passes every per-scan gate check.

    Args:
        scan: The read scan under check.
        raw: The raw export bytes behind the scan.

    Returns:
        True where bounds, polarity and re-derived rules all hold.
    """
    bounds = _scan_bounds_ok(scan)
    claims_hold = dominance_ok(scan) and polarity_ok(scan)
    return bounds and claims_hold and _scan_rules_ok(scan, raw)


def _failed_report(count: int) -> CompatibilityReport:
    """Return the all-false report for a refused file set.

    Args:
        count: The file count the report carries.

    Returns:
        The report with every check reading false.
    """
    return CompatibilityReport(
        files_checked=count,
        solidity_ok=False,
        compactness_ok=False,
        dominance_ok=False,
        polarity_ok=False,
        contract_rules_ok=False,
    )


def check_files(files: Sequence[Path]) -> CompatibilityReport:
    """Check a file set for compatibility with the contract.

    Args:
        files: The sorted export paths.

    Returns:
        The report over the nine files, all checks combined.
    """
    raws = [path.read_bytes() for path in files]
    doc = reader.read_document(raws)
    if any(scan.status != "read" for scan in doc.scans):
        return _failed_report(len(files))
    return _combine_scans(doc, raws, len(files))


def _combine_scans(doc: document.Document, raws: list[bytes], count: int) -> CompatibilityReport:
    """Combine per-scan checks into one file-set report.

    Args:
        doc: The survey document over the file set.
        raws: The raw export bytes in document order.
        count: The file count the report carries.

    Returns:
        The report with every check combined across scans.
    """
    solidity = True
    compactness = True
    dominance = True
    polarity = True
    rules = structure_ok(doc)
    for scan, raw in zip(doc.scans, raws, strict=True):
        if scan.status != "read":
            continue
        for item in scan.hierarchy.detections:
            cells = [(cell.impulse, cell.scan_line) for cell in item.cells]
            solidity = solidity and solidity_ok(cells, item.solidity)
            compactness = compactness and compactness_ok(cells, item.compactness)
        dominance = dominance and dominance_ok(scan)
        polarity = polarity and polarity_ok(scan)
        rules = rules and check_scan(scan, raw)
    return CompatibilityReport(
        files_checked=count,
        solidity_ok=solidity,
        compactness_ok=compactness,
        dominance_ok=dominance,
        polarity_ok=polarity,
        contract_rules_ok=rules,
    )

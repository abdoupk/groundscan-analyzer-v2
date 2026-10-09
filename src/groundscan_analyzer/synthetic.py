"""The synthetic scenario arm: manufactured surveys for the perpendicular case.

A manufactured survey, used where no real one exists, chiefly to exercise
the perpendicular case, which no real data ever will. It has no vendor
provenance and no operator. Every assertion in it is ``fixture-asserted``,
and it is ``synthetic-only`` evidence: not real data, and never a
substitute for it.

What it asserts is mechanics, never ground. Manufactured responses exist
so that detections exist, and the arm says nothing about what the engine
finds in them: count, location, size and polarity are out of scope, and a
change in how many detections a case yields is not a case failure. A
carefully designed ground would invite reading the case as validation, and
is treated with suspicion.

Two consequences follow. Cases are built in exact integers and rationals
with explicit bytes, so frozen bytes are reproducible by construction
rather than by luck, and that guarantee is about the generator, never
about the engine's platform invariance, which is declined. And a case
cannot check itself: where the thing under test is the operator's
declaration, the case supplies that declaration and then asserts the
engine honoured it, so it proves composition and preservation and never
repairs, and proves nothing about whether anyone declared a real walk
correctly.

Provenance follows the entry point rather than the individual
declaration: the real loader (:func:`groundscan_analyzer.cli.main`)
asserts the operator source explicitly,
:func:`read_synthetic_document` fixes the fixture source for the whole
survey, and the engine (:func:`groundscan_analyzer.reader.read_document`)
carries either without deriving one from file content, so a file cannot
claim one. Intake ordinals below are named ``position`` after
``document.ScanRead.position`` and the reader's intake-position
convention; they never denote spatial positions. The arm fails in the
safe direction, over-caveating rather than under-caveating: every
detection and frame resting on a fixture-asserted declaration carries
:data:`FIXTURE_LIMITATION`, checked by exact set equality.

Coverage of this arm closes no part of the declaration gap, stated once
at :data:`COVERAGE_STATEMENT`.
"""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, NamedTuple

from groundscan_analyzer import document as document_module
from groundscan_analyzer import frames, reader

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

__all__ = [
    "ASSERTION_SOURCES",
    "COVERAGE_STATEMENT",
    "FIXTURE_LIMITATION",
    "FIXTURE_SOURCE",
    "GENERATOR_VERSION",
    "OPERATOR_SOURCE",
    "REQUIRED_CASE_NAMES",
    "AssertionSource",
    "CoordinatePresence",
    "ScanSpec",
    "SyntheticCase",
    "VacuousCaseError",
    "build_required_cases",
    "case_limitations",
    "center_of_scan",
    "coincident_under_both_turns",
    "exports_of",
    "format_extent",
    "format_response",
    "hash_bytes",
    "is_fixed_point",
    "make_export",
    "oracle_express",
    "pitch_fraction",
    "read_synthetic_document",
    "require_detections_away_from_fixed_points",
]

AssertionSource = document_module.AssertionSource

CoordinatePresence = Literal["absent", "present-but-empty", "present-with-value"]

FIXTURE_SOURCE = document_module.FIXTURE_SOURCE

OPERATOR_SOURCE = document_module.OPERATOR_SOURCE

ASSERTION_SOURCES = document_module.ASSERTION_SOURCES

GENERATOR_VERSION: str = "synthetic-generator-v1"

FIXTURE_LIMITATION = document_module.FIXTURE_LIMITATION

COVERAGE_STATEMENT: str = (
    "the synthetic arm cannot prove an operator declared a real walk correctly, "
    "and it closes no part of that gap: it proves the engine composes, preserves, "
    "withholds and withdraws over fixture-asserted declarations only"
)

REQUIRED_CASE_NAMES: tuple[str, ...] = (
    "perp-equal",
    "perp-unequal",
    "missing",
    "contradictory",
    "contradictory-mirror",
    "closing",
    "closing-signed-cw",
    "closing-signed-ccw",
    "reversal",
    "single-empty",
    "presence-absent",
    "presence-empty",
    "presence-value-a",
    "presence-value-b",
)

MIN_PITCH_TOTAL: Final[int] = 2

ODD_CLASSES: Final[tuple[int, int]] = (1, 3)


class VacuousCaseError(ValueError):
    """A synthetic case with no detection away from a fixed point."""


class ScanSpec(NamedTuple):
    """One manufactured scan: integer lattice, integer responses, integer extents.

    Extents ride as integer hundredths of the declared unit, so ``300``
    means ``3.00`` in that unit. Responses ride as integers printed at
    four places, so ``10`` means ``10.0000``. The spike cell carries the
    spike response and every other cell carries the base response, so
    detections exist without asserting anything about the ground.
    """

    impulse_total: int
    line_total: int
    length_hundredths: int
    width_hundredths: int
    base_response: int
    spike_impulse: int
    spike_line: int
    spike_response: int
    latitude_state: CoordinatePresence
    longitude_state: CoordinatePresence
    latitude_value: int
    longitude_value: int


class SyntheticCase(NamedTuple):
    """One manufactured survey with its fixture-asserted declarations."""

    name: str
    specs: tuple[ScanSpec, ...]
    relations: tuple[frames.Relation, ...]
    sources: tuple[AssertionSource, ...]
    limitations: tuple[str, ...]


def format_extent(hundredths: int) -> str:
    """Format an integer-hundredths extent with no floating-point arithmetic.

    Args:
        hundredths: The extent in hundredths of the declared unit.

    Returns:
        The extent as ``D.CC m`` with exactly two decimals.
    """
    whole = hundredths // 100
    rest = hundredths % 100
    tens = rest // 10
    ones = rest % 10
    return f"{whole}.{tens}{ones} m"


def format_response(response: int) -> str:
    """Format an integer response at four printed places without floats.

    Args:
        response: The integer response.

    Returns:
        The response as ``V.0000``.
    """
    return f"{response}.0000"


def pitch_fraction(span_hundredths: int, observed_total: int) -> Fraction:
    """Return one axis pitch as an exact rational.

    The spacing, recoverable only from the declared span and the observed
    total together: ``span / (total - 1)`` with the span in hundredths.

    Args:
        span_hundredths: The declared span in hundredths of the unit.
        observed_total: The observed index total along the axis.

    Returns:
        The exact pitch as a rational in hundredths over intervals.

    Raises:
        ValueError: When fewer than two indices define no spacing at all.
    """
    if observed_total < MIN_PITCH_TOTAL:
        msg = f"no pitch over {observed_total} indices"
        raise ValueError(msg)
    return Fraction(span_hundredths, 100 * (observed_total - 1))


def hash_bytes(payload: bytes) -> str:
    """Hash frozen bytes for the manifest.

    Args:
        payload: The explicit export bytes.

    Returns:
        The SHA-256 hex digest.
    """
    return sha256(payload).hexdigest()


def _header_for(spec: ScanSpec) -> str:
    """Build one measuring header from the discarded-column presence states.

    Args:
        spec: The scan specification carrying both presence states.

    Returns:
        The header line with latitude and longitude columns exactly where
        the states say they belong.
    """
    header = "Impulse X,Scan Line Y,Scan Value"
    if spec.latitude_state != "absent":
        header += ",Latitude"
    if spec.longitude_state != "absent":
        header += ",Longitude"
    return header


def _cell_text(unframed: int, state: CoordinatePresence) -> str:
    """Render one discarded-column cell from its presence state.

    Args:
        unframed: The integer unframed number, printed only where a number
            is present. The engine discards it; only presence travels.
        state: Whether the column is absent, empty, or valued.

    Returns:
        The empty string except where the state carries a number.
    """
    if state != "present-with-value":
        return ""
    return format_response(unframed)


def _row_line(impulse: int, scan_line: int, response: int, spec: ScanSpec) -> str:
    """Render one measuring row with explicit separators.

    Args:
        impulse: The one-based impulse ordinal.
        scan_line: The one-based scan-line ordinal.
        response: The integer response at this lattice cell.
        spec: The scan specification carrying presence states.

    Returns:
        The comma-separated row with a trailing newline.
    """
    parts = [format_response(impulse), format_response(scan_line), format_response(response)]
    if spec.latitude_state != "absent":
        parts.append(_cell_text(spec.latitude_value, spec.latitude_state))
    if spec.longitude_state != "absent":
        parts.append(_cell_text(spec.longitude_value, spec.longitude_state))
    return ",".join(parts) + "\n"


def make_export(spec: ScanSpec) -> bytes:
    """Build one synthetic export in explicit bytes with integer arithmetic.

    The generator performs no floating-point arithmetic: indices,
    responses and extents are integers throughout, pitches are rationals
    held by the caller, and the text is joined with explicit newlines and
    encoded once as UTF-8.

    Args:
        spec: The scan specification.

    Returns:
        The explicit export bytes.
    """
    lines = [
        "+++ Characteristics +++\n",
        f"Field Length: {format_extent(spec.length_hundredths)}\n",
        f"Field Width: {format_extent(spec.width_hundredths)}\n",
        "\n",
        "+++ Measuring Values +++\n",
        _header_for(spec) + "\n",
    ]
    for scan_line in range(1, spec.line_total + 1):
        for impulse in range(1, spec.impulse_total + 1):
            response = spec.base_response
            if impulse == spec.spike_impulse and scan_line == spec.spike_line:
                response = spec.spike_response
            lines.append(_row_line(impulse, scan_line, response, spec))
    return "".join(lines).encode("utf-8")


def exports_of(case: SyntheticCase) -> tuple[bytes, ...]:
    """Render one synthetic case to its explicit export bytes.

    Args:
        case: The manufactured survey.

    Returns:
        One export per spec, in order.
    """
    return tuple(make_export(spec) for spec in case.specs)


def case_limitations(case: SyntheticCase) -> tuple[str, ...]:
    """Return one case limitations, naming the fixture source.

    Args:
        case: The manufactured survey.

    Returns:
        The limitations travelling with every claim resting on a
        fixture-asserted declaration.
    """
    return case.limitations


def center_of_scan(spec: ScanSpec) -> tuple[Fraction, Fraction]:
    """Return one lattice center as exact rationals.

    Args:
        spec: The scan specification.

    Returns:
        The impulse and scan-line midpoints as rationals.
    """
    first = Fraction(1, 1)
    last_impulse = Fraction(spec.impulse_total, 1)
    last_line = Fraction(spec.line_total, 1)
    return ((first + last_impulse) / 2, (first + last_line) / 2)


def oracle_express(
    relation_class: int,
    scan_center: tuple[Fraction, Fraction],
    ref_center: tuple[Fraction, Fraction],
    impulse: int,
    scan_line: int,
) -> tuple[Fraction, Fraction]:
    """Re-express one lattice position by reading the contract mapping table.

    The oracle reads :data:`groundscan_analyzer.frames.TURN_TABLE` rather
    than prose formulas, including the coincidence behaviour that follows
    from it: a centred cell maps identically under both quarter turns
    because the table says so. A future contributor misreading
    "clockwise" misreads the table identically here, so the engine fails
    rather than agreeing quietly.

    Args:
        relation_class: The scan class from the canonical reference.
        scan_center: The scan lattice center as exact rationals.
        ref_center: The reference lattice center as exact rationals.
        impulse: The lattice impulse ordinal.
        scan_line: The lattice scan-line ordinal.

    Returns:
        The frame position as exact rationals.

    Raises:
        ValueError: When the class names no quarter turn.
    """
    if relation_class not in frames.TURN_TABLE:
        msg = f"unknown relation class: {relation_class!r}"
        raise ValueError(msg)
    row = frames.TURN_TABLE[relation_class]
    dx = Fraction(impulse, 1) - scan_center[0]
    dy = Fraction(scan_line, 1) - scan_center[1]
    ordered = (dx, dy) if not row.swap else (dy, dx)
    return (
        ordered[0] * row.signs[0] + ref_center[0],
        ordered[1] * row.signs[1] + ref_center[1],
    )


def coincident_under_both_turns(
    scan_center: tuple[Fraction, Fraction],
    impulse: int,
    scan_line: int,
) -> bool:
    """Report whether both quarter turns agree at one cell, from the table.

    The coincidence set is read from :data:`frames.TURN_TABLE` via the
    oracle: agreement of the two odd classes at a point, which is the
    table's zero set rather than prose about centred detections.

    Args:
        scan_center: The scan lattice center as exact rationals.
        impulse: The lattice impulse ordinal.
        scan_line: The lattice scan-line ordinal.

    Returns:
        True where the two odd classes re-express identically.

    Raises:
        ValueError: When the contract table holds no odd classes at all.
    """
    for odd in ODD_CLASSES:
        if odd not in frames.TURN_TABLE:
            msg = "contract table holds no coincidence set"
            raise ValueError(msg)
    first_class, second_class = ODD_CLASSES
    ref = scan_center
    first = oracle_express(first_class, scan_center, ref, impulse, scan_line)
    second = oracle_express(second_class, scan_center, ref, impulse, scan_line)
    return first == second


def is_fixed_point(
    scan_center: tuple[Fraction, Fraction],
    relation_class: int,
    impulse: int,
    scan_line: int,
) -> bool:
    """Report whether one cell is fixed under one declared class for vacuity.

    Only the odd classes carry a vacuity fixed point: a centred detection
    maps identically under both quarter turns, so it cannot distinguish
    them. Even classes carry none here, since identity fixing all would
    make every same-declared case vacuous by definition, which is not the
    gap the check guards.

    Args:
        scan_center: The scan lattice center as exact rationals.
        relation_class: The declared class.
        impulse: The lattice impulse ordinal.
        scan_line: The lattice scan-line ordinal.

    Returns:
        True where an odd class leaves the cell in place.
    """
    if relation_class % 2 == 0:
        return False
    found = oracle_express(relation_class, scan_center, scan_center, impulse, scan_line)
    return found == (Fraction(impulse, 1), Fraction(scan_line, 1))


def _away_from_fixed(
    spec: ScanSpec, relation_classes: Sequence[int], impulse: int, scan_line: int
) -> bool:
    """Report whether one cell avoids every fixed point of its classes.

    Args:
        spec: The scan specification.
        relation_classes: The classes touching this scan.
        impulse: The lattice impulse ordinal.
        scan_line: The lattice scan-line ordinal.

    Returns:
        True where no touching class fixes the cell.
    """
    center = center_of_scan(spec)
    for relation_class in relation_classes:
        if is_fixed_point(center, relation_class, impulse, scan_line):
            return False
    return True


def _classes_touching(case: SyntheticCase, position: int) -> list[int]:
    """Collect the declared classes touching one intake position.

    Args:
        case: The manufactured survey.
        position: The intake position.

    Returns:
        The classes of edges incident to the position.
    """
    return [
        frames.word_to_class(relation.word)
        for relation in case.relations
        if position in {relation.first, relation.second}
    ]


def require_detections_away_from_fixed_points(
    doc: document_module.Document, case: SyntheticCase
) -> None:
    """Require one emitted detection per scan away from any fixed point.

    The check proves composition and preservation, never the ground:
    count, location, size and polarity are out of scope, and only
    existence away from coincidence matters, so a centred detection that
    cannot distinguish the turns does not satisfy it.

    Args:
        doc: The survey document over the synthetic exports.
        case: The manufactured survey behind the document.

    Raises:
        VacuousCaseError: With the vacuity vocabulary where any scan has
            no detection away from every fixed point of its relations.
    """
    for position, spec in enumerate(case.specs):
        scan = doc.scans[position]
        if scan.status != "read":
            msg = f"vacuous: scan {position} of {case.name} is not read"
            raise VacuousCaseError(msg)
        touched = _classes_touching(case, position)
        found = False
        for detection in scan.hierarchy.detections:
            if not touched or any(
                _away_from_fixed(spec, touched, cell.impulse, cell.scan_line)
                for cell in detection.cells
            ):
                found = True
                break
        if not found:
            first = f"vacuous: scan {position} of {case.name}"
            msg = f"{first} has no detection away from a fixed point"
            raise VacuousCaseError(msg)


def read_synthetic_document(case: SyntheticCase) -> document_module.Document:
    """Read one manufactured survey, fixing the assertion source at entry.

    The source is established here and traced into the record: every
    declaration in the case is ``fixture-asserted``, and the engine
    carries it onto each scale, relation, detection and frame without
    deriving one from file content. No operator-facing entry point
    accepts this source, and the engine never sets it itself.

    Args:
        case: The manufactured survey with fixture sources.

    Returns:
        The survey document over the synthetic exports, carrying the
        fixture source and limitation on every resting claim.

    Raises:
        ValueError: When any source is not the fixture source, or the
            limitations do not name it exactly.
    """
    for source in case.sources:
        if source != FIXTURE_SOURCE:
            msg = f"synthetic entry accepts the fixture source only, found {source!r}"
            raise ValueError(msg)
    if set(case.limitations) != {FIXTURE_LIMITATION}:
        msg = "synthetic limitations name the fixture source exactly"
        raise ValueError(msg)
    return reader.read_document(
        exports_of(case),
        list(case.relations),
        assertion_sources=list(case.sources),
    )


def _square_at(corner: tuple[int, int]) -> ScanSpec:
    """Build one square scan with a corner spike and no discarded columns.

    Args:
        corner: The spike impulse and scan-line ordinals.

    Returns:
        The four-by-four scan at three metres square.
    """
    impulse, scan_line = corner
    return ScanSpec(
        impulse_total=4,
        line_total=4,
        length_hundredths=300,
        width_hundredths=300,
        base_response=10,
        spike_impulse=impulse,
        spike_line=scan_line,
        spike_response=310,
        latitude_state="absent",
        longitude_state="absent",
        latitude_value=0,
        longitude_value=0,
    )


def _wrap(
    name: str, specs: tuple[ScanSpec, ...], relations: tuple[frames.Relation, ...]
) -> SyntheticCase:
    """Wrap specs and relations with fixture sources and limitations.

    Args:
        name: The required case name.
        specs: The scan specifications in intake order.
        relations: The fixture-asserted declarations.

    Returns:
        The synthetic case carrying fixture sources exactly.
    """
    return SyntheticCase(
        name=name,
        specs=specs,
        relations=relations,
        sources=tuple(FIXTURE_SOURCE for _ in specs),
        limitations=(FIXTURE_LIMITATION,),
    )


def _perp_equal() -> SyntheticCase:
    """Build the equal-pitch perpendicular case, clockwise.

    Returns:
        Two transposed scans at one-metre pitches under a clockwise turn.
    """
    first = ScanSpec(4, 3, 300, 200, 10, 4, 1, 310, "absent", "absent", 0, 0)
    second = ScanSpec(3, 4, 200, 300, 10, 1, 4, 310, "absent", "absent", 0, 0)
    return _wrap("perp-equal", (first, second), (frames.Relation(0, 1, "90-clockwise"),))


def _perp_unequal() -> SyntheticCase:
    """Build the unequal-pitch perpendicular case, counter-clockwise.

    Returns:
        Two transposed scans at fractional pitches under the other turn.
    """
    first = ScanSpec(4, 3, 500, 200, 10, 4, 1, 310, "absent", "absent", 0, 0)
    second = ScanSpec(3, 4, 200, 700, 10, 1, 4, 310, "absent", "absent", 0, 0)
    return _wrap("perp-unequal", (first, second), (frames.Relation(0, 1, "90-counter-clockwise"),))


def _missing() -> SyntheticCase:
    """Build the missing-relationship case with an untouched framed pair.

    Returns:
        Three scans where the first pair shares a frame and the third is
        isolated, so the missing path withholds only its own position.
    """
    specs = (_square_at((4, 1)), _square_at((1, 4)), _square_at((4, 4)))
    return _wrap("missing", specs, (frames.Relation(0, 1, "same"),))


def _contradictory() -> SyntheticCase:
    """Build the contradictory cycle with an untouched clean pair.

    Returns:
        Five scans where the first triple disagrees and withdraws while
        the remaining pair stays framed.
    """
    specs = (
        _square_at((4, 1)),
        _square_at((1, 4)),
        _square_at((4, 4)),
        _square_at((1, 1)),
        _square_at((4, 1)),
    )
    relations = (
        frames.Relation(0, 1, "same"),
        frames.Relation(1, 2, "same"),
        frames.Relation(0, 2, "opposite"),
        frames.Relation(3, 4, "same"),
    )
    return _wrap("contradictory", specs, relations)


def _contradictory_mirror() -> SyntheticCase:
    """Build the mirror contradictory cycle with an untouched clean pair.

    The odd-class mirror of the even contradictory cycle: two clockwise
    declarations disagreeing with a same edge, while the remaining pair
    stays framed. Both mirrors withdraw their triangle and spare the
    pair; only the declared words differ.

    Returns:
        Five scans where the turn-based triple disagrees and withdraws
        while the remaining pair stays framed.
    """
    specs = (
        _square_at((4, 1)),
        _square_at((1, 4)),
        _square_at((4, 4)),
        _square_at((1, 1)),
        _square_at((4, 1)),
    )
    relations = (
        frames.Relation(0, 1, "90-clockwise"),
        frames.Relation(1, 2, "90-clockwise"),
        frames.Relation(0, 2, "same"),
        frames.Relation(3, 4, "same"),
    )
    return _wrap("contradictory-mirror", specs, relations)


def _closing() -> SyntheticCase:
    """Build the closing even cycle.

    Returns:
        Three scans whose same and opposite declarations compose exactly.
    """
    specs = (_square_at((4, 1)), _square_at((1, 4)), _square_at((4, 4)))
    relations = (
        frames.Relation(0, 1, "same"),
        frames.Relation(1, 2, "opposite"),
        frames.Relation(0, 2, "opposite"),
    )
    return _wrap("closing", specs, relations)


def _signed_cw() -> SyntheticCase:
    """Build the signed closing cycle under clockwise turns.

    Returns:
        Two clockwise declarations closing through one opposite edge.
    """
    specs = (_square_at((4, 1)), _square_at((1, 4)), _square_at((4, 4)))
    relations = (
        frames.Relation(0, 1, "90-clockwise"),
        frames.Relation(1, 2, "90-clockwise"),
        frames.Relation(0, 2, "opposite"),
    )
    return _wrap("closing-signed-cw", specs, relations)


def _signed_ccw() -> SyntheticCase:
    """Build the mirror signed closing cycle under counter-clockwise turns.

    Returns:
        The mirror of the clockwise closing cycle, closing identically.
    """
    specs = (_square_at((4, 1)), _square_at((1, 4)), _square_at((4, 4)))
    relations = (
        frames.Relation(0, 1, "90-counter-clockwise"),
        frames.Relation(1, 2, "90-counter-clockwise"),
        frames.Relation(0, 2, "opposite"),
    )
    return _wrap("closing-signed-ccw", specs, relations)


def _reversal() -> SyntheticCase:
    """Build the edge-reversal case under one clockwise declaration.

    Returns:
        Two scans whose reversed inverse declaration is asserted by test.
    """
    specs = (_square_at((4, 1)), _square_at((1, 4)))
    return _wrap("reversal", specs, (frames.Relation(0, 1, "90-clockwise"),))


def _single_empty() -> SyntheticCase:
    """Build the single scan with an empty declaration set.

    Returns:
        One scan with no relations, synthesising no implicit relation.
    """
    return _wrap("single-empty", (_square_at((4, 1)),), ())


def _presence_absent() -> SyntheticCase:
    """Build the absent discarded-column case.

    Returns:
        One scan omitting both discarded coordinate columns.
    """
    spec = ScanSpec(4, 4, 300, 300, 10, 4, 1, 310, "absent", "absent", 0, 0)
    return _wrap("presence-absent", (spec,), ())


def _presence_empty() -> SyntheticCase:
    """Build the present-but-empty discarded-column case.

    Returns:
        One scan carrying both columns with no values.
    """
    spec = ScanSpec(4, 4, 300, 300, 10, 4, 1, 310, "present-but-empty", "present-but-empty", 0, 0)
    return _wrap("presence-empty", (spec,), ())


def _presence_value(latitude: int, longitude: int, name: str) -> SyntheticCase:
    """Build one present-with-value discarded-column case.

    Args:
        latitude: The integer latitude value, discarded by the engine.
        longitude: The integer longitude value, discarded by the engine.
        name: The required case name.

    Returns:
        One scan carrying both columns with values.
    """
    spec = ScanSpec(
        4,
        4,
        300,
        300,
        10,
        4,
        1,
        310,
        "present-with-value",
        "present-with-value",
        latitude,
        longitude,
    )
    return _wrap(name, (spec,), ())


def build_required_cases() -> dict[str, SyntheticCase]:
    """Return every required frozen case keyed by its manifest name.

    Returns:
        The fourteen required cases covering perpendicular turns, faults
        with mirrors, closures, reversals, emptiness and presence states.
    """
    cases = (
        _perp_equal(),
        _perp_unequal(),
        _missing(),
        _contradictory(),
        _contradictory_mirror(),
        _closing(),
        _signed_cw(),
        _signed_ccw(),
        _reversal(),
        _single_empty(),
        _presence_absent(),
        _presence_empty(),
        _presence_value(11, 22, "presence-value-a"),
        _presence_value(33, 44, "presence-value-b"),
    )
    return {case.name: case for case in cases}

"""Independent oracles for the definitional bounds.

Seams: the contract document (engine over input bytes to the document it
emits), the property registry (imported as data, never restated), and
static lint over committed artefacts (the oracle module against the
production modules it checks, and the derivations against
``docs/contract.md``).

Every test names its failing input in its docstring.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from itertools import combinations
import math
from pathlib import Path
import struct
import typing

import pytest

from groundscan_analyzer import (
    descriptors,
    document,
    hierarchy,
    oracles,
    quantity_registry,
    reader,
    synthetic,
)
from groundscan_analyzer import property_registry as registry
from groundscan_analyzer import scale as scale_module

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "docs" / "contract.md"
ORACLE_PATH = REPO / "src" / "groundscan_analyzer" / "oracles.py"

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
"""

TWO_BY_TWO = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
)

#: Definitional bounds under test: every one owes validity, witness and
#: agreement. Names read from the quantity registry where a bound exists,
#: with per-record bounds (field-area, counts) covered by construction.
DEFINITIONAL = (
    "solidity",
    "compactness",
    "field-area",
    "detection-count",
    "component-count",
    "scale-disagreement",
    "median-atom-fraction",
)


def bits(value: float) -> int:
    """Expose the binary64 bits for exact comparison.

    Args:
        value: The float to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def oracle_source() -> str:
    """Read the oracle module source for static checks.

    Returns:
        The oracle source text.
    """
    return ORACLE_PATH.read_text(encoding="utf-8")


def oracle_imports() -> set[str]:
    """Collect imported module names from the oracle source.

    Returns:
        Imported module names.
    """
    tree = ast.parse(oracle_source())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def read_scan(export: str) -> document.ScanRead:
    """Read one export to its read scan record.

    Args:
        export: The full export text.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    doc = reader.read_document([export.encode()])
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert isinstance(scan, document.ScanRead)
    return scan


def test_every_definitional_bound_has_three_checks() -> None:
    """All seven bounds carry validity, witness and agreement checks.

    Failing input: a bound with only a validity test and no witness.
    """
    for name in DEFINITIONAL:
        assert name in oracles.BOUND_DERIVATIONS, name
        assert oracles.BOUND_DERIVATIONS[name], name
        assert name in oracles.BOUND_WITNESS_KIND, name


def test_solidity_table_matches_oracle_exactly() -> None:
    """Hand-derived rationals equal the oracle with no tolerance.

    Failing input: a table row copying the legacy 4.0 block score.
    """
    assert oracles.SOLIDITY_REFERENCE != ()
    for case in oracles.SOLIDITY_REFERENCE:
        assert isinstance(case.solidity, Fraction)
        assert case.reason
        assert oracles.oracle_solidity(case.cells) == case.solidity


def test_solidity_witness_attains_one_exactly() -> None:
    """Convex witnesses score exactly 1.0 through oracle and production.

    Failing input: an erosion-based perimeter scoring a domino at 6.28.
    """
    for cells in (
        ((0, 0),),
        ((0, 0), (1, 0)),
        tuple((x, y) for x in range(2) for y in range(2)),
        tuple((x, 0) for x in range(5)),
    ):
        assert oracles.oracle_solidity(cells) == Fraction(1, 1)
        assert descriptors.hull_shoelace8(list(cells)) == oracles.oracle_hull_area8(cells)
        assert bits(descriptors.solidity(list(cells))) == bits(1.0)


def test_solidity_production_agrees_exhaustive() -> None:
    """Gift-wrapping agrees with monotone chain on every small cell set.

    Failing input: a centre-based hull scoring a solid 2x2 block at 4.0.
    """
    base = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1)]
    seen: set[frozenset[tuple[int, int]]] = set()
    for size in (1, 2, 3, 4, 5, 6):
        for combo in combinations(base, size):
            key = frozenset(combo)
            if key in seen:
                continue
            seen.add(key)
            cells = list(combo)
            assert oracles.oracle_hull_area8(cells) == descriptors.hull_shoelace8(cells)
            solidity = oracles.oracle_solidity(cells)
            assert solidity > 0
            assert solidity <= 1
            production = descriptors.solidity(cells)
            assert production > 0.0
            assert production <= 1.0
    assert len(seen) == 63


def test_solidity_oracle_shares_no_code() -> None:
    """The oracle imports no production module it checks.

    Failing input: an oracle importing descriptors for its hull.
    """
    imports = oracle_imports()
    for banned in (
        "groundscan_analyzer.descriptors",
        "groundscan_analyzer.hierarchy",
        "groundscan_analyzer.positions",
        "groundscan_analyzer.quantity_registry",
        "groundscan_analyzer.document",
        "groundscan_analyzer.property_registry",
        "groundscan_analyzer.scale",
    ):
        assert banned not in imports, banned
    source = oracle_source()
    assert "from groundscan_analyzer import descriptors" not in source
    assert "import descriptors" not in source


def test_solidity_uses_no_tolerance() -> None:
    """Exact integer arithmetic carries no tolerance constant.

    Failing input: a FLOAT_TOLERANCE clamping a ratio just above 1.0.
    """
    source = oracle_source()
    assert "FLOAT_TOLERANCE" not in source
    assert "pytest.approx" not in source
    assert "1e-9" not in source


def test_compactness_validity_from_perimeter_inequality() -> None:
    """P squared reaches sixteen areas on every probed cell set.

    Failing input: an erosion perimeter scoring a domino above pi/4.
    """
    shapes = [
        [(0, 0)],
        [(0, 0), (1, 0)],
        [(x, y) for x in range(2) for y in range(2)],
        [(x, 0) for x in range(50)],
        [(x, y) for x in range(5) for y in range(5)],
        [(0, 0), (1, 0), (2, 0), (1, 1), (1, -1)],
    ]
    entry = next(e for e in quantity_registry.QUANTITIES if e.name == "compactness")
    assert entry.upper is not None
    assert bits(entry.upper) == bits(math.pi / 4)
    for cells in shapes:
        assert oracles.perimeter_inequality_holds(cells)
        assert oracles.oracle_perimeter(cells) == descriptors.exposed_perimeter(cells)
        value = descriptors.compactness(cells)
        assert value > 0.0
        assert value <= math.pi / 4


def test_compactness_witness_single_cell() -> None:
    """One cell attains pi over four bit-for-bit.

    Failing input: a 5x5 block claimed as the pi/4 witness.
    """
    assert oracles.COMPACTNESS_WITNESS == ((0, 0),)
    assert oracles.oracle_perimeter(oracles.COMPACTNESS_WITNESS) == 4
    assert oracles.perimeter_inequality_holds(oracles.COMPACTNESS_WITNESS)
    assert bits(descriptors.compactness(list(oracles.COMPACTNESS_WITNESS))) == bits(math.pi / 4)


def test_compactness_proof_in_artefact() -> None:
    """The perimeter inequality proof is stated where a reader finds it.

    Failing input: a bound asserted as measured without its derivation.
    """
    text = ARTEFACT.read_text(encoding="utf-8")
    assert "perimeter inequality" in text
    assert "P >= 4" in text or "P**2 >= 16" in text or "P*P >= 16" in text
    assert "pi/4" in text


def test_field_area_bounds_built_from_inventory() -> None:
    """Ends follow cell count and pitches, owing no second implementation.

    Failing input: a second hull-based area read off the corpus.
    """
    imports = oracle_imports()
    assert "groundscan_analyzer.descriptors" not in imports
    assert "groundscan_analyzer.positions" not in imports
    lower = oracles.field_area_lower(Fraction(3, 1), Fraction(3, 1))
    assert lower == Fraction(9, 1)
    upper = oracles.field_area_upper(4, Fraction(3, 1), Fraction(3, 1))
    assert upper == Fraction(36, 1)
    assert lower <= upper


def test_field_area_witnesses_attain_ends() -> None:
    """One cell reaches the floor; full coverage reaches the ceiling.

    Failing input: a hull-based area claimed as the upper witness.
    """
    assert oracles.FIELD_AREA_LOWER_CELLS == 1
    assert oracles.field_area_lower(Fraction(1, 1), Fraction(1, 1)) == Fraction(1, 1)
    assert oracles.field_area_upper(4, Fraction(1, 1), Fraction(1, 1)) == Fraction(4, 1)


def test_field_area_production_agrees() -> None:
    """Emitted areas sit inside built ends on the two-by-two scan.

    Failing input: an area computed from the hull instead of cells.
    """
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        assert detection.field_position is not None
        assert detection.field_area is not None
        along = detection.field_position.along_line.scale.quotient
        across = detection.field_position.across_lines.scale.quotient
        assert along > 0.0
        assert across > 0.0
        lower = oracles.field_area_lower(Fraction(str(along)), Fraction(str(across)))
        upper = oracles.field_area_upper(
            scan.hierarchy.measured_cells, Fraction(str(along)), Fraction(str(across))
        )
        assert float(lower) <= detection.field_area
        assert detection.field_area <= float(upper)
        assert bits(detection.field_area) == bits(len(detection.cells) * along * across)


def test_detection_count_validity_charging() -> None:
    """Per-polarity counts sit between components and entering cells.

    Failing input: a cross-polarity total exceeding entering cells.
    """
    residuals = {(0, 0): 3.0, (1, 0): 2.0, (0, 1): 1.0, (5, 5): -1.0}
    tree = hierarchy.build(residuals)
    positives = {key for key, value in residuals.items() if value > 0.0}
    negatives = {key for key, value in residuals.items() if value < 0.0}
    totals: dict[str, int] = {tally.polarity: tally.total for tally in tree.detection_counts}
    for polarity in ("positive", "negative"):
        cells = positives if polarity == "positive" else negatives
        entering = len(cells)
        components = oracles.connected_components_4(set(cells))
        total = totals[polarity]
        assert components <= total
        assert total <= entering


def test_detection_count_witness_attains_both_ends() -> None:
    """Isolated distinct cells reach n; one block reaches c1.

    Failing input: connected distinct cells claimed to reach n.
    """
    upper_cells = {(0, 0): 4.0, (2, 0): 3.0, (0, 2): 2.0, (2, 2): 1.0}
    upper_tree = hierarchy.build(upper_cells)
    assert len(upper_tree.detections) == 4
    assert oracles.connected_components_4(set(upper_cells)) == 4
    lower_tree = hierarchy.build({(0, 0): 1.0, (1, 0): 1.0, (0, 1): 1.0, (1, 1): 1.0})
    assert len(lower_tree.detections) == 1
    assert oracles.connected_components_4({(0, 0), (1, 0), (0, 1), (1, 1)}) == 1


def test_detection_count_production_agrees() -> None:
    """Emitted tallies obey c1 <= N <= n with the named denominator.

    Failing input: a tally whose denominator is not measured cells.
    """
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.measured_cells == 4
    for tally in scan.hierarchy.detection_counts:
        assert tally.denominator == scan.hierarchy.measured_cells
        assert 0 <= tally.count <= scan.hierarchy.measured_cells
    assert oracles.detection_count_upper(4) == 4
    assert oracles.detection_count_lower(1) == 1


def test_component_count_validity_independence_number() -> None:
    """Alive counts never exceed the checkerboard ceiling on rectangles.

    Failing input: a count above ceil(L*W/2) on a 3x3 rectangle.
    """
    assert oracles.component_count_max_4conn(3, 3) == 5
    assert oracles.component_count_max_4conn(2, 2) == 2
    cells = {(x, y): 1.0 for x in range(3) for y in range(3) if (x + y) % 2 == 0}
    tree = hierarchy.build(cells)
    assert tree.component_counts[0].total == 5
    assert tree.component_counts[0].total <= oracles.component_count_max_4conn(3, 3)


def test_component_witness_rectangular_only() -> None:
    """The checkerboard witness is claimed only on full rectangles.

    Failing input: a checkerboard witness claimed over a gappy lattice.
    """
    assert oracles.is_rectangular_fully_measured(3, 3, 9)
    assert not oracles.is_rectangular_fully_measured(3, 3, 8)
    assert not oracles.is_rectangular_fully_measured(1, 1, 0)
    assert oracles.COMPONENT_WITNESS_REQUIRES_RECTANGULAR


def test_scale_bounds_validity_and_witnesses() -> None:
    """Disagreement and atom fraction stay in [0, 1] with witnesses.

    Failing input: a disagreement of 1.51 from a wrong calibration table.
    """
    by_name = {entry.name: entry for entry in quantity_registry.QUANTITIES}
    for name in ("scale-disagreement", "median-atom-fraction"):
        entry = by_name[name]
        assert entry.lower is not None
        assert entry.upper is not None
        assert bits(entry.lower) == bits(0.0)
        assert bits(entry.upper) == bits(1.0)
    assert oracles.scale_disagreement_oracle(5.0, 10.0) == Fraction(0, 1)
    assert oracles.scale_disagreement_oracle(0.0, 5.0) == Fraction(1, 1)
    assert oracles.scale_disagreement_oracle(0.0, 0.0) == Fraction(0, 1)
    gap = scale_module.estimate([-15.0, -5.0, 5.0, 15.0]).disagreement
    assert gap is not None
    assert 0.0 <= gap <= 1.0
    assert oracles.median_atom_oracle(0, 4) == Fraction(0, 1)
    assert oracles.median_atom_oracle(3, 3) == Fraction(1, 1)
    assert oracles.median_atom_oracle(0, 0) == Fraction(0, 1)


def test_oracle_helpers_reject_degenerate_input() -> None:
    """Error branches with no record equivalent fail loudly.

    Failing input: gift-wrapping asked for a next vertex with no candidate.
    """
    with pytest.raises(ValueError, match="no corner differs"):
        oracles._pick_next((0, 0), {(0, 0)})


def test_bounds_carry_derivation_in_artefact() -> None:
    """No bound without derivation; no derivation outside the artefact.

    Failing input: a quantity whose derivation string is empty.
    """
    for entry in quantity_registry.QUANTITIES:
        assert entry.derivation, entry.name
    text = ARTEFACT.read_text(encoding="utf-8")
    for name in DEFINITIONAL:
        assert f"`{name}`" in text, name
        assert oracles.BOUND_DERIVATIONS[name] in text, name


def test_measured_agreement_never_moves_grade_or_bound() -> None:
    """Coverage supports; grades and bounds stand without it.

    Failing input: a grade strengthened by a corpus agreement figure.
    """
    before_grades = {entry.grade for entry in registry.PROPERTY_ENTRIES}
    before_bounds = {
        (entry.name, entry.lower, entry.upper) for entry in quantity_registry.QUANTITIES
    }
    for entry in registry.PROPERTY_ENTRIES:
        swapped = entry._replace(
            evidence_coverage="real-data"
            if entry.evidence_coverage != "real-data"
            else "unexercised",
        )
        assert swapped.grade == entry.grade
    assert {entry.grade for entry in registry.PROPERTY_ENTRIES} == before_grades
    assert {(entry.name, entry.lower, entry.upper) for entry in quantity_registry.QUANTITIES} == (
        before_bounds
    )
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        assert 0.0 < detection.solidity <= 1.0


def test_corpus_partition_is_evidence_never_property() -> None:
    """Scale-state partition is recorded prose, not a registry property.

    Failing input: a property entry governing the corpus partition.
    """
    text = (REPO / "CONTEXT.md").read_text(encoding="utf-8")
    assert "median-atom" in text
    assert "disagreement" in text
    for entry in registry.PROPERTY_ENTRIES:
        assert typing.cast("str", entry.transform) != "corpus-partition"
    assert "corpus-partition" not in typing.cast("tuple[str, ...]", registry.TRANSFORMS)
    assert "corpus-partition" not in [line.output for line in registry.OUTPUT_CENSUS]


def test_oracle_loads_no_contract_data() -> None:
    """An oracle reading the checked contract is unexercised, not passing.

    Failing input: an oracle importing TURN_TABLE from the checked table.
    """
    assert synthetic.oracle_express.__doc__ is not None
    assert "TURN_TABLE" in synthetic.oracle_express.__doc__
    source = oracle_source()
    assert "TURN_TABLE" not in source
    assert "QUANTITIES" not in source
    assert "OUTPUT_CENSUS" not in source
    frame_entries = [
        entry for entry in registry.PROPERTY_ENTRIES if entry.scope == "frame-relation"
    ]
    assert frame_entries
    for entry in frame_entries:
        assert entry.evidence_coverage == "unexercised"

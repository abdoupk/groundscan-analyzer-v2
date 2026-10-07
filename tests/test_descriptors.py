"""Descriptors: solidity, compactness, area, depth and boundary contact.

Seam: the contract document. Behavioural tests run the engine over input
bytes and assert on the document it emits. Bound checks use independent
oracles sharing no code with production, as the testing decisions require.
"""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING

from groundscan_analyzer import descriptors, quantity_registry, reader

if TYPE_CHECKING:
    from groundscan_analyzer import document

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

THREE_BY_THREE = (
    HEAD
    + "1.0000,1.0000,20.0000\n2.0000,1.0000,0.0000\n3.0000,1.0000,40.0000\n"
    + "1.0000,2.0000,20.0000\n2.0000,2.0000,10.0000\n3.0000,2.0000,0.0000\n"
    + "1.0000,3.0000,30.0000\n2.0000,3.0000,20.0000\n3.0000,3.0000,40.0000\n"
)

DEPTH_HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Depth Z [m],Scan Value
"""

DEPTH_TWO_BY_TWO = (
    DEPTH_HEAD
    + "1.0000,1.0000,0.1000,10.0000\n2.0000,1.0000,0.2000,20.0000\n"
    + "1.0000,2.0000,0.3000,30.0000\n2.0000,2.0000,0.4000,40.0000\n"
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


def read(export: str) -> document.ScanRead:
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
    return scan


def by_identity(scan: document.ScanRead) -> dict[str, document.Detection]:
    """Index detections by their birth identity.

    Args:
        scan: The read scan record.

    Returns:
        Detections keyed by identity string.
    """
    return {detection.identity: detection for detection in scan.hierarchy.detections}


def test_domino_detections_carry_exact_solidity() -> None:
    """A convex domino scores exactly 1.0, not the legacy 4.0."""
    scan = read(TWO_BY_TWO)
    assert len(scan.hierarchy.detections) == 2
    for detection in scan.hierarchy.detections:
        assert detection.cell_count == 2
        assert bits(detection.solidity) == bits(1.0)


def test_convex_shapes_score_exactly_one() -> None:
    """Every convex cell set reaches the solidity upper bound exactly."""
    single = {(0, 0)}
    domino = {(0, 0), (1, 0)}
    block = {(x, y) for x in range(3) for y in range(3)}
    line = {(x, 0) for x in range(50)}
    rectangle = {(x, y) for x in range(2) for y in range(3)}
    for cells in (single, domino, block, line, rectangle):
        assert bits(descriptors.solidity(list(cells))) == bits(1.0)


def test_oracle_agrees_with_production_hull() -> None:
    """Gift-wrapping reaches the same doubled shoelace sum as production."""
    shapes = [
        {(0, 0)},
        {(0, 0), (1, 0)},
        {(0, 0), (1, 0), (0, 1)},
        {(x, y) for x in range(2) for y in range(2)},
        {(x, y) for x in range(5) for y in range(5)},
        {(x, 0) for x in range(50)},
        {(0, 0), (1, 0), (2, 0), (1, 1), (1, -1)},
        {(x, y) for x in range(4) for y in range(4)} - {(1, 1)},
    ]
    for cells in shapes:
        assert gift_wrap_area8(cells) == descriptors.hull_shoelace8(list(cells))


def gift_wrap_area8(cells: set[tuple[int, int]]) -> int:
    """Return eight times the corner-hull area via gift wrapping.

    An oracle sharing no code with production's monotone chain.

    Args:
        cells: The lattice coordinates of one component.

    Returns:
        Eight times the hull area of the cell corners, as an integer.
    """
    corners = {
        (2 * impulse + dx, 2 * scan_line + dy)
        for impulse, scan_line in cells
        for dx in (-1, 1)
        for dy in (-1, 1)
    }
    start = min(corners)
    hull = [start]
    current = start
    while True:
        best = None
        for candidate in corners:
            if candidate == current:
                continue
            if best is None:
                best = candidate
                continue
            cross = (best[0] - current[0]) * (candidate[1] - current[1]) - (
                best[1] - current[1]
            ) * (candidate[0] - current[0])
            if cross < 0 or (
                cross == 0
                and (candidate[0] - current[0]) ** 2 + (candidate[1] - current[1]) ** 2
                > (best[0] - current[0]) ** 2 + (best[1] - current[1]) ** 2
            ):
                best = candidate
        assert best is not None
        if best == start:
            break
        hull.append(best)
        current = best
    total = 0
    for (x1, y1), (x2, y2) in zip(hull, hull[1:] + hull[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total)


def test_compactness_bounds_and_legacy_defects() -> None:
    """Compactness stays in (0, pi/4] and never repeats the legacy scores."""
    entry = next(e for e in quantity_registry.QUANTITIES if e.name == "compactness")
    assert entry.upper is not None
    assert entry.upper_inclusive
    assert bits(descriptors.compactness([(0, 0)])) == bits(math.pi / 4)
    domino = descriptors.compactness([(0, 0), (1, 0)])
    assert 0.69 < domino < 0.71
    # The legacy erosion-based perimeter scored this domino at 6.28.
    assert domino < 1.0
    line = descriptors.compactness([(x, 0) for x in range(50)])
    assert 0.06 < line < 0.07
    block = descriptors.compactness([(x, y) for x in range(5) for y in range(5)])
    assert 0.78 < block < 0.80
    assert line < block


def test_record_values_respect_registry_bounds() -> None:
    """Every emitted descriptor lies inside its registry bound."""
    by_name = {entry.name: entry for entry in quantity_registry.QUANTITIES}
    for export in (TWO_BY_TWO, THREE_BY_THREE):
        for detection in read(export).hierarchy.detections:
            solidity = by_name["solidity"]
            assert solidity.lower is not None
            assert not solidity.lower_inclusive
            assert detection.solidity > solidity.lower
            assert solidity.upper is not None
            assert solidity.upper_inclusive
            assert detection.solidity <= solidity.upper
            compactness = by_name["compactness"]
            assert compactness.lower is not None
            assert not compactness.lower_inclusive
            assert detection.compactness > compactness.lower
            assert compactness.upper is not None
            assert compactness.upper_inclusive
            assert detection.compactness <= compactness.upper


def test_l_shaped_detection_is_not_solid() -> None:
    """A re-entrant corner leaves hull area empty, so solidity drops."""
    scan = read(THREE_BY_THREE)
    found = [
        detection
        for detection in scan.hierarchy.detections
        if detection.polarity == "negative" and bits(abs(detection.birth_level)) == bits(10.0)
    ]
    assert len(found) == 1
    assert 0.85 < found[0].solidity < 0.87


def test_field_area_reads_pitches_not_hull() -> None:
    """Area is cells times pitches: two domino cells at 3 m pitch are 18."""
    scan = read(TWO_BY_TWO)
    for detection in scan.hierarchy.detections:
        assert detection.field_area is not None
        assert bits(detection.field_area) == bits(18.0)
        assert detection.field_area_withheld is None


def test_field_area_withheld_without_extent() -> None:
    """No declared extent names its own cause and carries no second caveat."""
    lines = [line for line in TWO_BY_TWO.splitlines(keepends=True) if "Field Length" not in line]
    lines = [line for line in lines if "Field Width" not in line]
    scan = read("".join(lines))
    for detection in scan.hierarchy.detections:
        assert detection.field_area is None
        assert detection.field_area_withheld == "requires-declared-extent"


def test_field_area_withheld_across_incomparable_pitches() -> None:
    """A 3 m by 6 m declaration over 2 by 2 indices is not one unit."""
    export = TWO_BY_TWO.replace("Field Width: 3.00 m", "Field Width: 6.00 m")
    scan = read(export)
    for detection in scan.hierarchy.detections:
        assert detection.field_area is None
        assert detection.field_area_withheld == "requires-homogeneous-axes"


def test_field_area_withheld_where_no_pitch_exists() -> None:
    """One observed impulse defines no along-line pitch at all."""
    export = HEAD + "1.0000,1.0000,10.0000\n1.0000,2.0000,30.0000\n"
    scan = read(export)
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        assert detection.field_area is None
        assert detection.field_area_withheld == "requires-homogeneous-axes"


def test_depth_interval_spans_covered_samples() -> None:
    """Depth is a device-reported interval, never a point or a zero."""
    scan = read(DEPTH_TWO_BY_TWO)
    detections = by_identity(scan)
    assert len(detections) == 2
    for detection in detections.values():
        assert detection.depth is not None
        assert detection.depth.kind == "device-reported"
    intervals = sorted(
        (detection.depth.minimum, detection.depth.maximum)
        for detection in detections.values()
        if detection.depth is not None
    )
    wanted = [(bits(0.1), bits(0.2)), (bits(0.3), bits(0.4))]
    assert [(bits(low), bits(high)) for low, high in intervals] == wanted


def test_depth_absent_reads_as_absent() -> None:
    """No depth column means no interval anywhere, never a zero."""
    scan = read(TWO_BY_TWO)
    for detection in scan.hierarchy.detections:
        assert detection.depth is None


def test_single_valued_sample_spans_itself() -> None:
    """One sample spans the degenerate pair, which is coverage, not aggregation."""
    span = descriptors.depth_interval([0.5])
    assert span is not None
    assert (bits(span[0]), bits(span[1])) == (bits(0.5), bits(0.5))
    assert descriptors.depth_interval([]) is None


def coords(cells: list[document.DetectionCell]) -> list[tuple[int, int]]:
    """Project detection cells onto lattice coordinates in record order.

    Args:
        cells: The detection's cells as carried on the record.

    Returns:
        Impulse and scan-line pairs in record order.
    """
    return [(cell.impulse, cell.scan_line) for cell in cells]


def test_boundary_facts_are_distinct() -> None:
    """Lattice-edge clipping and padding flanking travel as two facts."""
    scan = read(TWO_BY_TWO + "3.0000,3.0000,\n")
    detections = by_identity(scan)
    assert len(detections) == 2
    positive = next(d for d in detections.values() if d.polarity == "positive")
    negative = next(d for d in detections.values() if d.polarity == "negative")
    assert coords(positive.lattice_boundary_cells) == [(1, 2)]
    assert coords(positive.padding_adjacent_cells) == [(1, 2), (2, 2)]
    assert coords(negative.lattice_boundary_cells) == [(1, 1), (2, 1)]
    assert coords(negative.padding_adjacent_cells) == [(2, 1)]


def test_tallies_carry_population_and_convention() -> None:
    """Counts state numerator, named denominator and connectivity each."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    assert hierarchy.measured_cells == 4
    for tally in hierarchy.detection_counts:
        assert tally.denominator == hierarchy.measured_cells
        assert tally.connectivity == "4-connectivity"
    counts = {tally.polarity: tally.count for tally in hierarchy.detection_counts}
    assert counts == {"positive": 1, "negative": 1}
    for level_tally in hierarchy.component_counts:
        assert level_tally.denominator == hierarchy.measured_cells
        assert level_tally.connectivity == "4-connectivity"
        assert level_tally.count >= 1
    assert not [t for t in hierarchy.detection_counts if t.polarity not in {"positive", "negative"}]


def test_header_only_export_reads_with_empty_hierarchy() -> None:
    """A measuring block with no rows is an empty scan, never a crash."""
    scan = read(HEAD)
    assert scan.cells == []
    assert scan.hierarchy.detections == []
    assert scan.hierarchy.measured_cells == 0
    assert scan.hierarchy.cells_in_hierarchy == 0
    assert [t.count for t in scan.hierarchy.detection_counts] == [0, 0]

"""Component hierarchy and detections: the threshold-free tree.

Seam: the contract document. Every test runs the engine over input bytes
and asserts on the document it emits. No test reaches inside the reader.
"""

from __future__ import annotations

import inspect
import struct

from groundscan_analyzer import document, reader
from groundscan_analyzer import hierarchy as tree

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


def cells_by_id(scan: document.ScanRead) -> dict[str, document.Detection]:
    """Index detections by their birth identity.

    Args:
        scan: The read scan record.

    Returns:
        Detections keyed by identity string.
    """
    return {detection.identity: detection for detection in scan.hierarchy.detections}


def test_document_carries_hierarchy_and_detections() -> None:
    """Every node of the hierarchy is a detection carrying its birth level."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    assert hierarchy.detections
    assert len(hierarchy.parents) == len(hierarchy.detections)
    for detection in hierarchy.detections:
        assert bits(detection.birth_level) != bits(0.0)
        if detection.polarity == "positive":
            assert detection.birth_level > 0.0
            assert detection.birth_level in list(hierarchy.levels_positive)
        else:
            assert detection.birth_level < 0.0
            assert detection.birth_level in list(hierarchy.levels_negative)


def test_no_level_enters_the_engine_as_input() -> None:
    """The detection path takes residuals only; no threshold exists."""
    params = list(inspect.signature(tree.build).parameters)
    assert params == ["residuals"]
    for name in params:
        assert "level" not in name
        assert "threshold" not in name
        assert "cutoff" not in name
        assert "cut" not in name
    assert not hasattr(tree, "DEFAULT_THRESHOLD")
    assert not hasattr(tree, "THRESHOLD")
    reader_params = list(inspect.signature(reader.read_document).parameters)
    # Relations are operator assertions, never levels or thresholds.
    assert reader_params == ["contents", "relations"]


def test_levels_partition_polarity() -> None:
    """A magnitude on both sides of the background is two levels, not one."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    assert [bits(v) for v in hierarchy.levels_positive] == [bits(15.0), bits(5.0)]
    assert [bits(v) for v in hierarchy.levels_negative] == [bits(-15.0), bits(-5.0)]
    positives = {bits(v) for v in hierarchy.levels_positive}
    negatives = {bits(v) for v in hierarchy.levels_negative}
    assert positives.isdisjoint({-bits(v) for v in hierarchy.levels_negative})
    assert negatives.isdisjoint({-bits(v) for v in hierarchy.levels_positive})


def test_simultaneous_entry_has_no_tie_rule() -> None:
    """Cells sharing a magnitude enter as siblings; no intermediate exists."""
    assert not hasattr(tree, "TIE_RULE")
    assert not hasattr(tree, "TIE_BREAK")
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    for detection in hierarchy.detections:
        levels = (
            hierarchy.levels_positive
            if detection.polarity == "positive"
            else hierarchy.levels_negative
        )
        assert detection.birth_level in list(levels)


def test_identity_is_birth_never_cell_set() -> None:
    """Ids encode birth; two nodes never share one even with equal cells."""
    scan = read(TWO_BY_TWO)
    by_id = cells_by_id(scan)
    assert len(by_id) == len(scan.hierarchy.detections)
    for identity, detection in by_id.items():
        assert identity.startswith(detection.polarity + "@")
        assert str(detection.birth_level) in identity


def test_parent_map_is_total_and_composes() -> None:
    """Every higher component lies inside exactly one lower one; chains close."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    detections = hierarchy.detections
    cell_sets = [
        {(cell.impulse, cell.scan_line) for cell in detection.cells} for detection in detections
    ]
    for index, parent in enumerate(hierarchy.parents):
        if parent is None:
            continue
        assert 0 <= parent < len(detections)
        assert detections[parent].polarity == detections[index].polarity
        assert abs(detections[parent].birth_level) < abs(detections[index].birth_level)
        assert cell_sets[index] < cell_sets[parent]
    seen: set[int] = set()
    for index in range(len(detections)):
        chain: set[int] = set()
        current: int | None = index
        while current is not None:
            assert current not in chain
            chain.add(current)
            parent = hierarchy.parents[current]
            current = parent
        seen.update(chain)
    assert seen == set(range(len(detections)))


def test_numbering_follows_lattice_order_and_excludes_padding() -> None:
    """Numbers are presentation in lattice order; padding never numbers."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    numbers = [detection.number for detection in hierarchy.detections]
    assert sorted(numbers) == list(range(1, len(numbers) + 1))
    lattice_keys = [
        (min(cell.scan_line for cell in d.cells), min(cell.impulse for cell in d.cells))
        for d in hierarchy.detections
    ]
    ordered = [d.number for _, d in sorted(zip(lattice_keys, hierarchy.detections, strict=True))]
    assert ordered == sorted(ordered)
    for detection in hierarchy.detections:
        assert detection.cells


def test_adding_padding_renumbers_nothing() -> None:
    """Padding preserves the hierarchy exactly and moves no number."""
    base = read(TWO_BY_TWO)
    padded_export = TWO_BY_TWO + "3.0000,3.0000,\n"
    padded = read(padded_export)
    assert [d.identity for d in padded.hierarchy.detections] == [
        d.identity for d in base.hierarchy.detections
    ]
    assert [d.number for d in padded.hierarchy.detections] == [
        d.number for d in base.hierarchy.detections
    ]
    assert list(padded.hierarchy.parents) == list(base.hierarchy.parents)


def test_connectivity_is_fixed_and_recorded() -> None:
    """Connectivity is contract data, never configuration."""
    scan = read(TWO_BY_TWO)
    assert scan.hierarchy.connectivity == "4-connectivity"
    assert scan.hierarchy.connectivity == tree.CONNECTIVITY
    params = list(inspect.signature(tree.build).parameters)
    assert "connectivity" not in params


def test_levels_are_raw_residuals_without_scale() -> None:
    """The tree needs no scale; levels are raw residuals from the cells."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    assert hierarchy.level_kind == "raw-residual"
    residuals = {cell.residual for cell in scan.cells if cell.residual is not None}
    assert set(hierarchy.levels_positive) | set(hierarchy.levels_negative) <= residuals


def test_both_populations_are_stated() -> None:
    """Measured cells and hierarchy cells travel together, zeros excluded."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    measured = sum(1 for cell in scan.cells if cell.response is not None)
    assert hierarchy.measured_cells == measured
    assert hierarchy.cells_in_hierarchy == measured
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert single.hierarchy.measured_cells == 1
    assert single.hierarchy.cells_in_hierarchy == 0
    assert single.hierarchy.detections == []
    assert single.hierarchy.parents == []


def test_cut_moves_no_engine_output() -> None:
    """Cutting is a consumer read; the guarantee travels on the artefact."""
    scan = read(TWO_BY_TWO)
    hierarchy = scan.hierarchy
    assert hierarchy.cut_guarantee == "you may cut anywhere and lose nothing the engine computed"
    before = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    level = hierarchy.levels_positive[0]
    alive = [
        detection
        for detection in hierarchy.detections
        if detection.polarity == "positive" and abs(detection.birth_level) >= abs(level)
    ]
    assert alive
    after = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert before == after


def test_simultaneous_siblings_share_a_birth_and_a_parent() -> None:
    """Two disconnected cells at one magnitude are born together, then merge."""
    scan = read(THREE_BY_THREE)
    hierarchy = scan.hierarchy
    siblings = [
        (position, detection)
        for position, detection in enumerate(hierarchy.detections)
        if detection.polarity == "negative" and bits(detection.birth_level) == bits(-20.0)
    ]
    assert len(siblings) == 2
    (first_pos, first), (second_pos, second) = siblings
    first_cells = {(cell.impulse, cell.scan_line) for cell in first.cells}
    second_cells = {(cell.impulse, cell.scan_line) for cell in second.cells}
    assert first_cells.isdisjoint(second_cells)
    assert hierarchy.parents[first_pos] is not None
    assert hierarchy.parents[first_pos] == hierarchy.parents[second_pos]
    parent_pos = hierarchy.parents[first_pos]
    assert parent_pos is not None
    parent = hierarchy.detections[parent_pos]
    assert bits(parent.birth_level) == bits(-10.0)
    parent_cells = {(cell.impulse, cell.scan_line) for cell in parent.cells}
    assert first_cells < parent_cells
    assert second_cells < parent_cells


def test_numbering_is_presentation_not_identity() -> None:
    """Birth order groups by polarity; numbers follow the lattice instead."""
    scan = read(TWO_BY_TWO)
    detections = scan.hierarchy.detections
    assert [detection.polarity for detection in detections] == ["positive", "negative"]
    assert [detection.number for detection in detections] == [2, 1]


def threshold_component_count(
    residuals: dict[tuple[int, int], float], polarity: str, magnitude: float
) -> int:
    """Count thresholded components with breadth-first search.

    A second implementation sharing no code with production's union-find,
    over the same residual field the document carries.

    Args:
        residuals: Residuals keyed by lattice coordinate.
        polarity: The polarity under the cut.
        magnitude: The cut magnitude as an absolute value.

    Returns:
        The connected component count at the cut.
    """
    if polarity == "positive":
        held = {key for key, value in residuals.items() if value > 0.0 and abs(value) >= magnitude}
    else:
        held = {key for key, value in residuals.items() if value < 0.0 and abs(value) >= magnitude}
    seen: set[tuple[int, int]] = set()
    count = 0
    for start in sorted(held):
        if start in seen:
            continue
        count += 1
        queue = [start]
        seen.add(start)
        while queue:
            current = queue.pop()
            impulse, scan_line = current
            neighbours = (
                (impulse - 1, scan_line),
                (impulse + 1, scan_line),
                (impulse, scan_line - 1),
                (impulse, scan_line + 1),
            )
            for neighbour in neighbours:
                if neighbour in held and neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
    return count


def alive_count(hierarchy: document.Hierarchy, polarity: str, magnitude: float) -> int:
    """Count the tree nodes alive at one cut of one polarity.

    A node is alive exactly while the cut lies at or below its birth and
    strictly above its parent's birth.

    Args:
        hierarchy: The scan's component hierarchy.
        polarity: The polarity under the cut.
        magnitude: The cut magnitude as an absolute value.

    Returns:
        The alive node count at the cut.
    """
    births = [detection.birth_level for detection in hierarchy.detections]
    total = 0
    for position, detection in enumerate(hierarchy.detections):
        if detection.polarity != polarity:
            continue
        if abs(detection.birth_level) < magnitude:
            continue
        parent = hierarchy.parents[position]
        if parent is not None and abs(births[parent]) >= magnitude:
            continue
        total += 1
    return total


def check_cuts(export: str) -> None:
    """Assert alive counts match thresholded components at every level.

    Args:
        export: The full export text to read and check.
    """
    scan = read(export)
    residuals = {
        (cell.impulse, cell.scan_line): cell.residual
        for cell in scan.cells
        if cell.residual is not None
    }
    for polarity, levels in (
        ("positive", scan.hierarchy.levels_positive),
        ("negative", scan.hierarchy.levels_negative),
    ):
        for level in levels:
            magnitude = abs(level)
            assert alive_count(scan.hierarchy, polarity, magnitude) == (
                threshold_component_count(residuals, polarity, magnitude)
            )


def test_alive_count_matches_thresholded_components_at_every_cut() -> None:
    """Cuts served from birth-plus-parent lifespans lose no component."""
    check_cuts(TWO_BY_TWO)
    check_cuts(THREE_BY_THREE)
    check_cuts(HEAD + "1.0000,1.0000,7.5000\n")

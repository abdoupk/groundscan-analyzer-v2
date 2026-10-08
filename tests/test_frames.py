"""Shared frames: relations over whole lattices, never merged grids.

Seam: the contract document. Behavioural tests run the engine over input
bytes with declared relations and assert on the document it emits. Kernel
checks cover the payload identity and the turn table directly, where the
record cannot isolate reflections from background interference.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest

from groundscan_analyzer import document, frames, reader
from groundscan_analyzer.cli import main

if TYPE_CHECKING:
    from pathlib import Path

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
"""

SCAN_A = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
)

SCAN_B = (
    HEAD
    + "1.0000,1.0000,11.0000\n2.0000,1.0000,21.0000\n"
    + "1.0000,2.0000,31.0000\n2.0000,2.0000,41.0000\n"
)

SHIFTED_A = (
    HEAD
    + "6.0000,6.0000,10.0000\n7.0000,6.0000,20.0000\n"
    + "6.0000,7.0000,30.0000\n7.0000,7.0000,40.0000\n"
)

RECT_A = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n3.0000,1.0000,30.0000\n"
    + "1.0000,2.0000,40.0000\n2.0000,2.0000,50.0000\n3.0000,2.0000,60.0000\n"
)

RECT_B = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
    + "1.0000,3.0000,50.0000\n2.0000,3.0000,60.0000\n"
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


def read_one(export: str) -> document.ScanRead:
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


def read_survey(
    exports: list[str], relations: list[frames.Relation] | None = None
) -> document.Document:
    """Read named exports with declared relations to one document.

    Args:
        exports: The export texts in intake order.
        relations: Declared relations over sorted intake positions.

    Returns:
        The survey document.
    """
    return reader.read_document([export.encode() for export in exports], relations or [])


def read_scan(doc: document.Document, position: int) -> document.ScanRead:
    """Read one survey scan record by intake position.

    Args:
        doc: The survey document.
        position: The intake position.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    scan = doc.scans[position]
    assert scan.status == "read"
    return scan


def test_payload_ignores_relabelling() -> None:
    """Adding one constant to every index changes no identity."""
    assert read_one(SCAN_A).payload_hash == read_one(SHIFTED_A).payload_hash


def test_payload_ignores_padding_and_operator_values() -> None:
    """Padding, absent rows and operator typing never enter identity."""
    base = read_one(SCAN_A)
    assert base.payload_hash == read_one(SCAN_A + "3.0000,3.0000,\n").payload_hash
    assert base.payload_hash == read_one(SCAN_A.replace("3.00 m", "5.00 m")).payload_hash
    assert base.payload_hash == read_one(SCAN_A.replace("10.0000", "10.00")).payload_hash


def test_payload_moves_with_measurements() -> None:
    """Different responses are different scans."""
    assert read_one(SCAN_A).payload_hash != read_one(SCAN_B).payload_hash


def test_payload_reflection_orbit() -> None:
    """One reflection of the measured set is the same scan."""
    left = {(0, 0): 10.0, (1, 0): 20.0, (0, 1): 30.0}
    right = {(1, 0): 10.0, (0, 0): 20.0, (1, 1): 30.0}
    assert frames.payload_hash(left) == frames.payload_hash(right)
    assert frames.payload_hash(left) != frames.payload_hash({(0, 0): 10.0})


def test_turn_table_coincidence_and_asymmetry() -> None:
    """The versioned table fixes centered content and splits the turns."""
    assert frames.TURN_TABLE_VERSION == "relative-turn-v1"
    center = (2.0, 2.0)
    assert frames.express(1, center, center, 2, 2) == frames.express(3, center, center, 2, 2)
    assert frames.express(1, center, center, 1, 2) != frames.express(3, center, center, 1, 2)


def test_detections_retain_contributing_scan_identity() -> None:
    """Every detection carries its own scan's hash inside any frame."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "same")])
    assert len(doc.frames) == 1
    hashes = set()
    for scan in doc.scans:
        assert scan.status == "read"
        hashes.add(scan.payload_hash)
        for detection in scan.hierarchy.detections:
            assert detection.scan_payload_hash == scan.payload_hash
    assert len(hashes) == 2


def test_reference_is_min_hash_not_name_or_order() -> None:
    """The frame answers to the smallest payload hash, nothing else."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "same")])
    assert len(doc.frames) == 1
    frame = doc.frames[0]
    hashes = [read_one(SCAN_A).payload_hash, read_one(SCAN_B).payload_hash]
    assert frame.name == min(hashes)
    assert frame.label != frame.name
    assert frame.label.startswith("frame-")


def test_classes_compose_and_difference() -> None:
    """Triangle closes over same and opposite with differences exact."""
    doc = read_survey(
        [SCAN_A, SCAN_B, SCAN_A],
        [
            frames.Relation(0, 1, "same"),
            frames.Relation(1, 2, "opposite"),
            frames.Relation(0, 2, "opposite"),
        ],
    )
    assert doc.contradictions == []
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [0, 1, 2]
    by_scan = {entry.scan: entry.relation_class for entry in doc.frames[0].relations}
    assert (by_scan[2] - by_scan[0]) % 4 == 2
    assert (by_scan[1] - by_scan[0]) % 4 == 0


def test_self_loop_contradiction_names_its_edge() -> None:
    """A scan turned opposite itself closes at two, never zero."""
    doc = read_survey([SCAN_A], [frames.Relation(0, 0, "opposite")])
    assert len(doc.contradictions) == 1
    edge = doc.contradictions[0]
    assert (edge.first, edge.second, edge.relation) == (0, 0, "opposite")
    assert edge.declared_class == 2
    assert edge.expected_class == 0
    assert doc.frames == []


def test_contradiction_withdraws_component_only() -> None:
    """A non-closing triangle falls back locally and spares the rest."""
    doc = read_survey(
        [SCAN_A, SCAN_B, SCAN_A, SCAN_B, SCAN_A],
        [
            frames.Relation(0, 1, "same"),
            frames.Relation(1, 2, "same"),
            frames.Relation(0, 2, "opposite"),
            frames.Relation(3, 4, "same"),
        ],
    )
    assert len(doc.contradictions) == 1
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [3, 4]
    for position in (0, 1, 2):
        scan = read_scan(doc, position)
        for detection in scan.hierarchy.detections:
            assert detection.shared_frame_position is None
            assert detection.no_shared_position_reason == "withdrawn-component"
    for position in (3, 4):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.no_shared_position_reason is None
            assert detection.shared_frame_position is not None


def test_missing_path_withholds_only_the_position() -> None:
    """An unlinked scan keeps every per-scan result with positions local."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 0, "same")])
    assert doc.contradictions == []
    assert doc.frames == []
    for scan in doc.scans:
        assert scan.status == "read"
        for detection in scan.hierarchy.detections:
            assert detection.shared_frame_position is None
            assert detection.no_shared_position_reason == "missing-orientation-path"
            assert detection.scan_local_position is not None


def test_independent_components_root_independently() -> None:
    """Two pairs anchor two frames at their own minima with own labels."""
    doc = read_survey(
        [SCAN_A, SCAN_B, SCAN_A, SCAN_B],
        [frames.Relation(0, 1, "same"), frames.Relation(2, 3, "same")],
    )
    assert doc.contradictions == []
    assert len(doc.frames) == 2
    assert sorted(frame.label for frame in doc.frames) == ["frame-1", "frame-2"]
    for frame in doc.frames:
        assert frame.name == min(read_one(SCAN_A).payload_hash, read_one(SCAN_B).payload_hash)


def test_shared_positions_derive_without_replacing() -> None:
    """Same-declared twins re-express identically beside the canonical."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "same")])
    assert len(doc.frames) == 1
    name = doc.frames[0].name
    for scan in doc.scans:
        assert scan.status == "read"
        for detection in scan.hierarchy.detections:
            assert detection.no_shared_position_reason is None
            shared = detection.shared_frame_position
            assert shared is not None
            assert shared.frame == name
            assert (
                shared.scan_local.along_line.index == detection.scan_local_position.along_line.index
            )
            assert shared.homogeneous is True


def test_declared_words_survive_verbatim_in_canonical_order() -> None:
    """Clockwise is never repaired into its mirror, order is canonical."""
    doc = read_survey(
        [SCAN_A, SCAN_B], [frames.Relation(1, 0, "90-clockwise"), frames.Relation(0, 1, "same")]
    )
    words = [(edge.first, edge.second, edge.relation) for edge in doc.declared_relations]
    assert (1, 0, "90-clockwise") in words
    assert (0, 1, "same") in words
    assert words == sorted(
        words,
        key=lambda edge: (
            min(
                read_scan(doc, edge[0]).payload_hash,
                read_scan(doc, edge[1]).payload_hash,
            ),
            max(
                read_scan(doc, edge[0]).payload_hash,
                read_scan(doc, edge[1]).payload_hash,
            ),
            edge[2],
        ),
    )


def test_permutation_leaves_no_byte_moved() -> None:
    """Shuffled declarations emit identical bytes on the same survey."""
    relations = [
        frames.Relation(0, 1, "same"),
        frames.Relation(1, 2, "opposite"),
        frames.Relation(0, 2, "opposite"),
    ]
    first = read_survey([SCAN_A, SCAN_B, SCAN_A], relations)
    second = read_survey([SCAN_A, SCAN_B, SCAN_A], list(reversed(relations)))
    assert document.dumps(first) == document.dumps(second)
    tied = read_survey(
        [SCAN_A, SCAN_B, SCAN_A],
        [frames.Relation(0, 1, "same"), frames.Relation(2, 1, "same")],
    )
    swapped = read_survey(
        [SCAN_A, SCAN_B, SCAN_A],
        [frames.Relation(2, 1, "same"), frames.Relation(0, 1, "same")],
    )
    assert document.dumps(tied) == document.dumps(swapped)


def test_relations_move_expression_never_detections() -> None:
    """Declaring relations adds branches without touching any detection."""
    bare = read_survey([SCAN_A, SCAN_B])
    linked = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "opposite")])
    assert bare.frames == []
    assert len(linked.frames) == 1
    for plain, framed in zip(bare.scans, linked.scans, strict=True):
        assert plain.status == framed.status == "read"
        assert [d.identity for d in plain.hierarchy.detections] == [
            d.identity for d in framed.hierarchy.detections
        ]
        assert [d.cells for d in plain.hierarchy.detections] == [
            d.cells for d in framed.hierarchy.detections
        ]
        assert plain.hierarchy.component_counts == framed.hierarchy.component_counts


def test_no_cross_scan_counting_or_lattices() -> None:
    """Lattices stay whole, tallies stay per scan, totals stay absent."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "same")])
    assert read_scan(doc, 0).lattice == read_one(SCAN_A).lattice
    assert read_scan(doc, 1).lattice == read_one(SCAN_B).lattice
    text = document.dumps(doc)
    assert '"total"' not in text
    for scan in doc.scans:
        assert scan.status == "read"
        for tally in scan.hierarchy.detection_counts:
            assert tally.denominator == scan.hierarchy.measured_cells


def test_aspect_reports_per_scan_without_gating() -> None:
    """Square is not-informative, matched roles consistent, the rest noted."""
    doc = read_survey([SCAN_A, SCAN_B], [frames.Relation(0, 1, "same")])
    for scan in doc.scans:
        assert scan.status == "read"
        assert len(scan.aspect_checks) == 1
        verdict = scan.aspect_checks[0]
        assert verdict.verdict == "not-informative"
        assert verdict.note == "cannot-distinguish-clockwise-from-counter-clockwise"


def test_aspect_reads_roles_not_lengths() -> None:
    """Same roles under same, swapped roles under a quarter turn."""
    same = read_survey([RECT_A, RECT_A], [frames.Relation(0, 1, "same")])
    assert [v.verdict for v in read_scan(same, 0).aspect_checks] == ["consistent"]
    turned = read_survey([RECT_A, RECT_A], [frames.Relation(0, 1, "90-clockwise")])
    assert [v.verdict for v in read_scan(turned, 0).aspect_checks] == ["contradictory"]
    crossed = read_survey([RECT_A, RECT_B], [frames.Relation(0, 1, "90-clockwise")])
    assert [v.verdict for v in read_scan(crossed, 0).aspect_checks] == ["consistent"]


def test_half_indices_ship_with_homogeneous_true() -> None:
    """Center halves are positions, never a unit violation."""
    rows = "".join(f"{i}.0000,{j}.0000,{10 * i + j}.0000\n" for j in (1, 2, 3) for i in (1, 2, 3))
    doc = read_survey([SCAN_A, HEAD + rows], [frames.Relation(0, 1, "same")])
    assert len(doc.frames) == 1
    name = doc.frames[0].name
    nonroot = next(p for p in (0, 1) if read_scan(doc, p).payload_hash != name)
    halves = False
    for detection in read_scan(doc, nonroot).hierarchy.detections:
        shared = detection.shared_frame_position
        assert shared is not None
        assert shared.homogeneous is True
        for axis in (shared.along_line, shared.across_lines):
            halves = halves or not axis.index.is_integer()
    assert halves


def test_encoding_version_travels_at_root() -> None:
    """The payload encoding version is declared beside the contract."""
    doc = read_survey([SCAN_A])
    assert doc.payload_encoding_version == "payload-encoding-v1"


def test_relate_reaches_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Survey relations declare over sorted positions from the command line."""
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text(SCAN_A, encoding="utf-8")
    second.write_text(SCAN_B, encoding="utf-8")
    assert main(["survey", str(first), str(second), "--relate", "0,1,same"]) == 0
    assert '"relation": "same"' in capsys.readouterr().out
    with pytest.raises(SystemExit) as malformed:
        main(["survey", str(first), str(second), "--relate", "0,1,sideways"])
    assert malformed.value.code != 0
    with pytest.raises(SystemExit) as shapeless:
        main(["survey", str(first), str(second), "--relate", "0,1"])
    assert shapeless.value.code != 0
    with pytest.raises(SystemExit) as unnumbered:
        main(["survey", str(first), str(second), "--relate", "a,b,same"])
    assert unnumbered.value.code != 0
    assert main(["survey", str(first), str(second), "--relate", "0,5,same"]) == 2
    with pytest.raises(SystemExit) as misplaced:
        main(["scan", str(first), "--relate", "0,1,same"])
    assert misplaced.value.code != 0


def test_engine_refuses_bad_declarations() -> None:
    """Out-of-range positions and unknown words fail before any reading."""
    with pytest.raises(ValueError, match="no scan"):
        reader.read_document([SCAN_A.encode()], [frames.Relation(0, 5, "same")])
    with pytest.raises(ValueError, match="unknown relation word"):
        reader.read_document([SCAN_A.encode()], [frames.Relation(0, 0, "sideways")])


def test_dangling_edges_drop_leaving_echo() -> None:
    """A relation naming a refused scan constrains nothing, echoes kept."""
    refused = SCAN_A.replace("Impulse X,Scan Line Y,Scan Value", "Impulse X,Scan Line Y,Foo Bar")
    doc = reader.read_document([SCAN_A.encode(), refused.encode()], [frames.Relation(0, 1, "same")])
    assert [scan.status for scan in doc.scans] == ["read", "refused"]
    assert [(edge.first, edge.second, edge.relation) for edge in doc.declared_relations] == [
        (0, 1, "same")
    ]
    assert doc.frames == []
    assert doc.contradictions == []
    scan = read_scan(doc, 0)
    assert scan.aspect_checks == []
    for detection in scan.hierarchy.detections:
        assert detection.no_shared_position_reason == "missing-orientation-path"

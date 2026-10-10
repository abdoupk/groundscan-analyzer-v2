"""The presentation model: what the record projects into, and what it refuses."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundscan_analyzer import document as document_module
from groundscan_analyzer import frames, reader, synthetic
from groundscan_tui.model import (
    CLASS_WORDS,
    RefusalView,
    ScanView,
    _class_word,
    build_detections,
    build_grid,
    build_view,
)

from .support import document_view, first_refusal, first_scan

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"


def _single() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8")
    )


def _refused() -> document_module.Document:
    contents = (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()
    return reader.read_document([contents])


HEADER = """+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Depth Z [m],Scan Value,Latitude,Longitude
1.0000,1.0000,0.0000,0.0000,0.1000,10.0000,,
2.0000,1.0000,3.0000,0.0000,0.2000,not-a-number,,
"""


def _row_refused() -> document_module.Document:
    return reader.read_document([HEADER.encode()])


def _survey() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_survey.json").read_text(encoding="utf-8")
    )


def _campaign() -> document_module.Document:
    return reader.read_document(
        [
            (ENGINE_DATA / "acceptance_single_export.txt").read_bytes(),
            (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes(),
        ],
    )


def _read() -> document_module.ScanRead:
    scan = _single().scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return scan


def _large() -> document_module.ScanRead:
    return _synthetic_scan(30, 80)


def _synthetic_scan(impulses: int, lines: int) -> document_module.ScanRead:
    spec = synthetic.ScanSpec(
        impulse_total=impulses,
        line_total=lines,
        length_hundredths=300,
        width_hundredths=300,
        base_response=10,
        spike_impulse=3,
        spike_line=4,
        spike_response=310,
        latitude_state="absent",
        longitude_state="absent",
        latitude_value=0,
        longitude_value=0,
    )
    document = reader.read_document([synthetic.make_export(spec)])
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return scan


def test_one_export_yields_one_view() -> None:
    view = document_view(_single())
    assert len(view.scans) == 1
    assert len(first_scan(_single()).detections) == 2


def test_a_document_view_carries_document_level_facts() -> None:
    labels = dict(document_view(_single()).facts)
    assert labels["contract version"] == "1"
    assert labels["registry version"] == "3"
    assert labels["quantity registry version"] == "4"
    assert labels["numeric reading"] == "default-numeric-reading-v1"


def test_field_is_a_lattice_over_the_observed_span() -> None:
    grid = build_grid(_read())
    assert grid.impulses == (1, 2)
    assert grid.scan_lines == (1, 2)
    assert len(grid.cells) == 4


def test_each_cell_lands_in_exactly_one_class() -> None:
    grid = build_grid(_read())
    kinds = {cell.kind for cell in grid.cells.values()}
    assert kinds == {"positive", "negative"}


def test_a_cell_outside_both_polarities_is_zero_not_a_detection() -> None:
    scan = _large()
    grid = build_grid(scan)
    zero = [c for c in grid.cells.values() if c.kind == "zero"]
    assert zero
    assert all(cell.residual == pytest.approx(0.0) for cell in zero)
    assert len(zero) == scan.hierarchy.measured_cells - scan.hierarchy.cells_in_hierarchy


def test_padding_is_a_structural_null_and_never_zero() -> None:
    grid = build_grid(_read())
    assert all(cell.residual is None for cell in grid.cells.values() if cell.kind == "padding")


def test_rank_reads_the_levels_rather_than_the_residual_size() -> None:
    scan = _read()
    grid = build_grid(scan)
    for cell in grid.cells.values():
        if cell.residual is None:
            continue
        levels = (
            scan.hierarchy.levels_positive
            if cell.kind == "positive"
            else scan.hierarchy.levels_negative
        )
        assert cell.rank == levels.index(cell.residual)


def test_every_level_gets_a_rung() -> None:
    scan = _read()
    grid = build_grid(scan)
    positives = sorted(
        c.rank for c in grid.cells.values() if c.kind == "positive" and c.rank is not None
    )
    negatives = sorted(
        c.rank for c in grid.cells.values() if c.kind == "negative" and c.rank is not None
    )
    assert positives == list(range(len(scan.hierarchy.levels_positive)))
    assert negatives == list(range(len(scan.hierarchy.levels_negative)))


def test_an_index_the_export_lacks_reads_as_absent() -> None:
    grid = build_grid(_read())
    missing = grid.at(9, 9)
    assert missing.kind == "absent"
    assert missing.residual is None
    assert missing.rank is None


def test_gaps_widen_the_span_rather_than_closing_up() -> None:
    grid = build_grid(_read())
    assert grid.impulses == tuple(range(min(grid.impulses), max(grid.impulses) + 1))


def test_a_large_field_exceeds_a_default_terminal() -> None:
    grid = build_grid(_large())
    assert len(grid.impulses) == 30
    assert len(grid.scan_lines) == 80
    assert len(grid.scan_lines) > 24


def test_detections_come_in_the_records_own_order() -> None:
    scan = _read()
    rows = build_detections(scan.hierarchy)
    assert [row.detection.number for row in rows] == [d.number for d in scan.hierarchy.detections]


def test_the_hierarchys_order_is_not_its_numbering() -> None:
    """The record orders the hierarchy by birth, and numbers in lattice order."""
    rows = build_detections(_read().hierarchy)
    assert [row.detection.number for row in rows] != sorted(row.detection.number for row in rows)


def test_a_detection_carries_its_own_mask() -> None:
    scan = _read()
    for row in build_detections(scan.hierarchy):
        assert row.keys == {(c.impulse, c.scan_line) for c in row.detection.cells}


def test_roots_have_no_parent_and_their_depth_is_zero() -> None:
    rows = build_detections(_read().hierarchy)
    assert all(row.parent is None for row in rows)
    assert all(row.depth == 0 for row in rows)


def test_facts_carry_named_fields_only() -> None:
    labels = dict(first_scan(_single()).facts)
    assert labels["payload hash"] == _read().payload_hash
    assert labels["measured cells"] == str(_read().hierarchy.measured_cells)


def test_a_declared_extent_is_stated_and_its_absence_too() -> None:
    single = dict(first_scan(_single()).facts)
    assert single["declared field length"] != "not declared"
    assert single["background combination"] == "median"


def test_every_result_state_travels_with_its_reason() -> None:
    states = {output.name: output for output in first_scan(_single()).outputs}
    assert states["scale-normalised view"].status == "indeterminate"
    assert states["scale-normalised view"].reason == "scale-not-warranted"
    assert states["mask invariance"].status == "not-emitted"
    assert states["registration"].reason == "non-unique-argmax"
    assert states["robust scale"].reason is None


def test_a_refusal_is_its_own_shape_not_a_broken_scan() -> None:
    view = first_refusal(_refused())
    assert view.reason == "missing-required-column"
    assert view.detail
    assert view.rows == ()


def test_a_refusal_names_the_offending_rows_where_it_has_them() -> None:
    view = first_refusal(_row_refused())
    assert view.rows
    assert all(row.startswith("line ") for row in view.rows)
    assert all(":" in row for row in view.rows)


def test_every_scan_carries_its_intake_position() -> None:
    view = document_view(_single())
    assert view.scans[0].position == 0


def test_a_document_with_no_scan_record_is_a_defect() -> None:
    doc = _single().model_copy(update={"scans": []})
    with pytest.raises(ValueError, match="no scan record"):
        build_view(doc)


def test_the_relation_class_table_round_trips_against_the_engine() -> None:
    """The view restates a table the engine does not publish; prove it agrees."""
    for index, word in enumerate(CLASS_WORDS):
        assert frames.word_to_class(word) == index


def test_an_out_of_range_relation_class_is_named_not_guessed() -> None:
    assert _class_word(0) == "same"
    assert _class_word(3) == "90-counter-clockwise"
    assert _class_word(9) == "class-9"


def test_a_survey_without_relations_carries_no_frames() -> None:
    view = document_view(_survey())
    assert view.survey.relations == ()
    assert view.survey.frames == ()
    assert view.survey.contradictions == ()
    assert view.survey.recurrences
    assert view.is_survey


def test_a_campaign_keeps_every_scan_in_intake_order() -> None:
    view = document_view(_campaign())
    assert [scan.position for scan in view.scans] == [0, 1]
    assert isinstance(view.scans[0], ScanView)
    assert isinstance(view.scans[1], RefusalView)

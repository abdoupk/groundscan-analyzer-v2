"""The edges: the branches the ordinary fixtures never reach.

Every case here is a shape the record can genuinely be in -- an undeclared
extent, a component hierarchy that nests, a survey sharing a frame -- rather
than a mock. A view that only ever sees the 2x2 acceptance fixture would
pass without rendering half of what it claims to.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual.widgets import Footer

from groundscan_analyzer import document as document_module
from groundscan_analyzer import reader, synthetic
from groundscan_tui import cli
from groundscan_tui.app import BINDINGS, FieldBrowser, RefusalApp
from groundscan_tui.grid import field_text
from groundscan_tui.model import (
    RefusalView,
    ScanView,
    _index_span,
    _span,
    build_detections,
    build_view,
)
from groundscan_tui.panes import (
    ABSENT,
    DetailPane,
    DetectionPane,
    _depth,
    _field_position,
    _shared_position,
    detail_text,
)

if TYPE_CHECKING:
    import pytest
    from textual.content import Content
    from textual.widgets import Static

    from groundscan_tui.model import DetectionRow


def _plain(widget: Static) -> str:
    return cast("Content", widget.render()).plain


ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"

# No extent declared and no depth column, so the record must withhold the
# figures that need them rather than substitute a zero.
BARE = """+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Scan Value,Latitude,Longitude
1.0000,1.0000,0.0000,0.0000,10.0000,,
2.0000,1.0000,3.0000,0.0000,20.0000,,
2.0000,2.0000,3.0000,3.0000,40.0000,,
"""

# Two strong cells far apart, joined by a weak ridge: the strong cells are two
# components at the strong level and merge into one at the weak level, which
# is the only shape that makes the hierarchy a tree rather than a list.
NESTED_STRONG = {(4, 4): 8.0, (9, 9): 8.0}
NESTED_RIDGE = {(4, j): 2.0 for j in range(5, 10)}
NESTED_RIDGE.update({(i, 9): 2.0 for i in range(5, 9)})


HEADER = (
    "Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Depth Z [m],Scan Value,Latitude,Longitude"
)


def _lattice(cells: dict[tuple[int, int], float], n: int = 12, m: int = 12) -> bytes:
    lines = ["+++ Measuring Values +++", HEADER]
    lines.extend(
        f"{i}.0000,{j}.0000,0.0000,0.0000,0.1000,{10.0 + cells.get((i, j), 0.0):.4f},,"
        for j in range(1, m + 1)
        for i in range(1, n + 1)
    )
    return ("\n".join(lines) + "\n").encode()


def _nested_rows() -> tuple[DetectionRow, ...]:
    document = reader.read_document([_lattice({**NESTED_STRONG, **NESTED_RIDGE})])
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return build_detections(scan.hierarchy)


def _bare_rows() -> tuple[DetectionRow, ...]:
    document = reader.read_document([BARE.encode()])
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return build_detections(scan.hierarchy)


def _survey_rows() -> tuple[DetectionRow, ...]:
    cases = synthetic.build_required_cases()
    document = synthetic.read_synthetic_document(cases["closing"])
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return build_detections(scan.hierarchy)


def test_an_empty_index_list_spans_nothing() -> None:
    assert _span([]) == ()
    assert _index_span([]) == "none observed"


def test_a_nested_hierarchy_gives_its_children_a_parent_and_a_depth() -> None:
    rows = _nested_rows()
    parented = [row for row in rows if row.parent is not None]
    assert parented
    for row in parented:
        assert row.depth == 1
        assert row.detection.number in _nested_children_numbers(rows)


def _nested_children_numbers(rows: tuple[DetectionRow, ...]) -> set[int]:
    return {number for row in rows for number in row.children}


def test_the_parent_of_a_merge_carries_both_children() -> None:
    rows = _nested_rows()
    merge = next(row for row in rows if len(row.children) == 2)
    assert merge.parent is None
    assert merge.depth == 0
    assert set(merge.children) == {
        row.detection.number for row in rows if row.parent == merge.detection.number
    }


def test_an_undeclared_extent_withholds_the_field_position_by_name() -> None:
    row = _bare_rows()[0]
    assert row.detection.field_position is None
    assert _field_position(row.detection.field_position) == ABSENT
    assert "requires-declared-extent" in detail_text(row).plain


def test_an_absent_depth_is_stated_rather_than_shown_as_zero() -> None:
    row = _bare_rows()[0]
    assert row.detection.depth is None
    assert _depth(row) == ABSENT
    assert f"depth: {ABSENT}" in detail_text(row).plain


def test_a_shared_frame_position_is_stated_with_its_homogeneity() -> None:
    rows = [row for row in _survey_rows() if row.detection.shared_frame_position is not None]
    assert rows
    text = _shared_position(rows[0])
    assert "homogeneous" in text
    assert "withdrawn:" not in text


def test_no_selection_reads_as_none_rather_than_a_wrong_row() -> None:
    async def scenario() -> None:
        document = document_module.loads(
            (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
        )
        view = build_view(document)
        assert isinstance(view, ScanView)
        app = FieldBrowser(view)
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.query_one(DetectionPane)
            pane.index = None
            await pilot.pause()
            assert pane.current_row is None
            assert "no detection selected" in _plain(app.query_one(DetailPane))

    asyncio.run(scenario())


def test_the_bindings_are_the_footer_s_own() -> None:
    async def scenario() -> None:
        document = document_module.loads(
            (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
        )
        view = build_view(document)
        assert isinstance(view, ScanView)
        app = FieldBrowser(view)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query(Footer)
            keys = {
                binding[0] if isinstance(binding, tuple) else binding.key for binding in BINDINGS
            }
            assert "q" in keys
            assert "tab" in keys

    asyncio.run(scenario())


def test_the_refusal_view_closes_on_q_too() -> None:
    contents = (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()
    view = build_view(reader.read_document([contents]))
    assert isinstance(view, RefusalView)

    async def scenario() -> None:
        app = RefusalApp(view)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(scenario())


def test_the_projection_chooses_which_application_opens() -> None:
    document = document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )
    refused = reader.read_document(
        [(ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()],
    )
    assert isinstance(cli._view(build_view(document)), FieldBrowser)
    assert isinstance(cli._view(build_view(refused)), RefusalApp)


def test_a_successful_read_launches_the_view_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export = tmp_path / "case.txt"
    export.write_bytes(_lattice({**NESTED_STRONG, **NESTED_RIDGE}))
    launched: list[bool] = []
    refusal = RefusalApp(RefusalView(reason="r", detail="d", rows=()))

    def _record_run() -> None:
        launched.append(True)

    monkeypatch.setattr(refusal, "run", _record_run)
    monkeypatch.setattr(cli, "_view", lambda _projection: refusal)
    assert cli.run([str(export)]) == 0
    assert launched == [True]


def test_a_nested_field_draws_every_level() -> None:
    document = reader.read_document([_lattice({**NESTED_STRONG, **NESTED_RIDGE})])
    view = build_view(document)
    assert isinstance(view, ScanView)
    text = field_text(view.grid, frozenset()).plain
    assert len(text.splitlines()) == len(view.grid.scan_lines)
    assert len(text.splitlines()[0]) == len(view.grid.impulses)

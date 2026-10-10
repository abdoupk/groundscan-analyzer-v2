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
from groundscan_tui.app import BINDINGS, CampaignApp, CampaignBrowser
from groundscan_tui.grid import field_text
from groundscan_tui.model import (
    _index_span,
    _span,
    build_detections,
)
from groundscan_tui.panes import (
    ABSENT,
    DetailPane,
    DetectionPane,
    RefusalPane,
    ScanPane,
    _depth,
    _field_position,
    _shared_position,
    detail_text,
)

from .support import document_view, first_scan

if TYPE_CHECKING:
    import pytest
    from textual.content import Content
    from textual.widgets import Static

    from groundscan_tui.model import DetectionRow


def _plain(widget: Static) -> str:
    return cast("Content", widget.render()).plain


ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"


def _document() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )


def _refused_document() -> document_module.Document:
    return reader.read_document(
        [(ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()],
    )


def _campaign() -> document_module.Document:
    return reader.read_document(
        [
            (ENGINE_DATA / "acceptance_single_export.txt").read_bytes(),
            (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes(),
        ],
    )


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
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(DetectionPane)
            pane.index = None
            await pilot.pause()
            assert pane.current_row is None
            assert "no detection selected" in _plain(app.screen.query_one(DetailPane))

    asyncio.run(scenario())


def test_the_bindings_are_the_footer_s_own() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen.query(Footer)
            keys = {
                binding[0] if isinstance(binding, tuple) else binding.key for binding in BINDINGS
            }
            assert "q" in keys
            assert "tab" in keys

    asyncio.run(scenario())


def test_a_single_scan_document_hides_the_scan_pane() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert not app.query(ScanPane)

    asyncio.run(scenario())


def test_a_campaign_shows_the_scan_pane_with_one_row_per_scan() -> None:
    async def scenario() -> None:
        app = CampaignApp(
            browser=CampaignBrowser(_campaign(), document_view(_campaign()), ["one.csv", "two.csv"])
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(ScanPane)
            assert len(pane.query("ListItem")) == 2

    asyncio.run(scenario())


def test_stepping_to_a_refused_scan_shows_it_in_the_field_place() -> None:
    async def scenario() -> None:
        app = CampaignApp(
            browser=CampaignBrowser(_campaign(), document_view(_campaign()), ["one.csv", "two.csv"])
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one(ScanPane).index = 1
            await pilot.pause()
            refusal = app.screen.query_one(RefusalPane)
            assert refusal.display
            assert not app.screen.query_one(DetectionPane).display
            assert "missing-required-column" in _plain(refusal)

    asyncio.run(scenario())


def test_stepping_back_to_a_read_scan_shows_its_field() -> None:
    async def scenario() -> None:
        app = CampaignApp(
            browser=CampaignBrowser(_campaign(), document_view(_campaign()), ["one.csv", "two.csv"])
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(ScanPane)
            pane.index = 1
            await pilot.pause()
            pane.index = 0
            await pilot.pause()
            assert app.screen.query_one(DetectionPane).display
            assert not app.screen.query_one(RefusalPane).display

    asyncio.run(scenario())


def test_a_survey_document_shows_the_cross_scan_section() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_campaign(), document_view(_campaign())))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen.query(".Survey")

    asyncio.run(scenario())


def test_the_refusal_view_closes_on_q_too() -> None:
    async def scenario() -> None:
        app = CampaignApp(
            browser=CampaignBrowser(_refused_document(), document_view(_refused_document()))
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(scenario())


def test_a_successful_read_launches_the_view_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export = tmp_path / "case.txt"
    export.write_bytes(_lattice({**NESTED_STRONG, **NESTED_RIDGE}))
    launched: list[bool] = []

    def _record_run(_self: CampaignApp) -> None:
        launched.append(True)

    monkeypatch.setattr(CampaignApp, "run", _record_run)
    assert cli.run([str(export)]) == 0
    assert launched == [True]


def test_a_nested_field_draws_every_level() -> None:
    document = reader.read_document([_lattice({**NESTED_STRONG, **NESTED_RIDGE})])
    view = first_scan(document)
    text = field_text(view.grid, frozenset()).plain
    assert len(text.splitlines()) == len(view.grid.scan_lines)
    assert len(text.splitlines()[0]) == len(view.grid.impulses)

"""The panes: the figures on screen, and the doubts filed beside them."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from textual.widgets import Static

from groundscan_analyzer import document as document_module
from groundscan_analyzer import reader
from groundscan_tui.app import CampaignApp, CampaignBrowser
from groundscan_tui.model import RefusalView
from groundscan_tui.panes import (
    DetailPane,
    DetectionPane,
    FieldPane,
    _figure,
    detail_text,
    header_text,
    refusal_text,
    survey_text,
)

from .support import document_view, first_refusal, first_scan
from .support import plain as _plain

if TYPE_CHECKING:
    from groundscan_tui.model import ScanView

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"


def _campaign() -> document_module.Document:
    return reader.read_document(
        [
            (ENGINE_DATA / "acceptance_single_export.txt").read_bytes(),
            (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes(),
        ],
    )


def _view() -> ScanView:
    document = document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )
    return first_scan(document)


def _refusal() -> RefusalView:
    contents = (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()
    return first_refusal(reader.read_document([contents]))


def test_the_detail_panel_states_the_figures_the_record_carries() -> None:
    text = detail_text(_view().detections[0]).plain
    assert "solidity" in text
    assert "compactness" in text
    assert "birth level" in text
    assert "raw residual" in text


def test_a_withheld_figure_names_the_reason_and_never_shows_a_zero() -> None:
    assert _figure(None, "requires-declared-extent", noun="field area") == (
        "withheld: requires-declared-extent"
    )
    assert "0" not in _figure(None, "requires-declared-extent", noun="field area")


def test_an_absent_figure_says_it_is_absent_rather_than_withheld() -> None:
    assert _figure(None, None, noun="depth") == "depth not carried"


def test_an_emitted_figure_is_just_the_figure() -> None:
    assert _figure(1.5, None, noun="field area") == "1.5"


def test_the_detail_panel_states_a_named_reason_beside_its_headline() -> None:
    text = detail_text(_view().detections[0]).plain
    assert "missing-orientation-path" in text
    assert "withdrawn:" in text


def test_the_detail_panel_carries_the_scan_local_position_always() -> None:
    text = detail_text(_view().detections[0]).plain
    assert "scan-local" in text
    assert "device-index" in text


def test_the_detail_panel_states_empty_limitations_as_a_fact() -> None:
    text = detail_text(_view().detections[0]).plain
    assert "none stated" in text


def test_the_detail_panel_places_a_detection_in_the_tree() -> None:
    text = detail_text(_view().detections[0]).plain
    assert "a root" in text
    assert "depth 0" in text


def test_no_selection_says_so_rather_than_rendering_an_empty_panel() -> None:
    assert "no detection selected" in detail_text(None).plain


def _header() -> str:
    return header_text(document_view(_document()), _view()).plain


def _document() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )


def test_the_header_shows_every_result_state_with_its_reason() -> None:
    text = _header()
    assert "scale-not-warranted" in text
    assert "non-unique-argmax" in text
    assert "requires-recorded-perturbation-bound" in text


def test_the_header_shows_the_population_beside_the_count() -> None:
    text = _header()
    assert "measured cells" in text
    assert "cells in the hierarchy" in text


def test_the_header_states_the_document_facts_once() -> None:
    text = _header()
    assert text.count("contract version") == 1
    assert "contract version: 1" in text


def test_the_header_states_a_refused_scan_without_a_field() -> None:
    document = reader.read_document(
        [(ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()],
    )
    view = document_view(document)
    text = header_text(view, view.scans[0]).plain
    assert "refused (missing-required-column)" in text
    assert "measured cells" not in text


def test_neither_pane_states_a_verdict() -> None:
    combined = (_header() + detail_text(_view().detections[0]).plain).lower()
    for word in ("readiness", "fitness", "confidence", "grade", "total score"):
        assert word not in combined


def test_the_survey_section_is_absent_when_there_is_no_survey() -> None:
    assert not document_view(_document()).is_survey


def test_the_survey_section_names_each_entry_and_its_reason() -> None:
    survey = document_view(_campaign()).survey
    assert survey.recurrences
    text = survey_text(survey).plain
    assert "recurrence 0 to 1" in text
    assert "ineligible" in text
    assert "missing-orientation-path" in text


def test_the_survey_section_never_tallies_across_scans() -> None:
    text = survey_text(document_view(_campaign()).survey).plain.lower()
    for word in ("total", "average", "agreement rate", "readiness"):
        assert word not in text


def test_the_refusal_names_its_reason_and_states_its_rows() -> None:
    refusal = _refusal()
    assert refusal.reason == "missing-required-column"
    assert "missing-required-column" in refusal_text(refusal)


def test_a_refusal_with_no_rows_says_so_rather_than_showing_nothing() -> None:
    text = refusal_text(_refusal())
    assert "no offending row was recorded" in text


def test_a_refusal_with_rows_lists_them() -> None:
    text = refusal_text(
        RefusalView(
            position=0,
            reason="unparseable-row",
            detail="d",
            rows=("line 2: unparseable-row",),
        )
    )
    assert "line 2: unparseable-row" in text
    assert "no offending row was recorded" not in text


def test_the_browser_opens_on_the_first_detection_with_every_pane_drawn() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(DetectionPane)
            assert pane.current_row is not None
            assert "solidity" in _plain(app.screen.query_one(DetailPane))
            assert _plain(app.screen.query_one(FieldPane)).strip()

    asyncio.run(scenario())


def test_stepping_changes_the_drawing_and_not_the_order() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(DetectionPane)
            first = pane.current_row
            assert first is not None
            before = _plain(app.screen.query_one(DetailPane))
            await pilot.press("down")
            await pilot.pause()
            second = pane.current_row
            assert second is not None
            assert second.detection.number != first.detection.number
            assert _plain(app.screen.query_one(DetailPane)) != before

    asyncio.run(scenario())


def test_the_list_carries_one_item_per_detection_in_record_order() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.screen.query_one(DetectionPane)
            assert len(pane.query("ListItem")) == len(_view().detections)

    asyncio.run(scenario())


def test_tab_moves_focus_so_the_field_can_be_panned() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.focused, DetectionPane)
            await pilot.press("tab")
            await pilot.pause()
            assert not isinstance(app.focused, DetectionPane)

    asyncio.run(scenario())


def test_q_closes_the_browser() -> None:
    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(_document(), document_view(_document())))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(scenario())


def test_the_refusal_app_renders_its_reason_and_rows() -> None:
    document = reader.read_document(
        [(ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()],
    )

    async def scenario() -> None:
        app = CampaignApp(browser=CampaignBrowser(document, document_view(document)))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "refused" in _plain(app.screen.query_one(Static))

    asyncio.run(scenario())

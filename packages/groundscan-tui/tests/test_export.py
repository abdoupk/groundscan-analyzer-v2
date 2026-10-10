"""Exporting: the readable record, the lossless one, and overwriting neither."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest

from groundscan_analyzer import document as document_module
from groundscan_tui.app import BINDINGS, CampaignApp, CampaignBrowser
from groundscan_tui.export import (
    ExportError,
    campaign_stem,
    destination,
    write_html,
    write_json,
)
from groundscan_tui.model import build_view

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"


def _document() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )


def _campaign() -> document_module.Document:
    return document_module.loads(
        (ENGINE_DATA / "acceptance_survey.json").read_text(encoding="utf-8"),
    )


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "export": None,
        "folder": None,
        "out": None,
        "force": False,
        "perturbation": None,
        "displacement": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_an_export_is_named_after_the_campaign(tmp_path: Path) -> None:
    assert destination(tmp_path, "field", ".html") == tmp_path / "field.html"


def test_one_export_names_the_campaign_after_itself() -> None:
    assert campaign_stem([Path("a/b/scan.csv")]) == "scan"


def test_a_folder_names_the_campaign_after_the_folder() -> None:
    assert campaign_stem([Path("a/b/one.csv"), Path("a/b/two.csv")]) == "b"


def test_the_html_record_is_written_and_is_the_records_own() -> None:
    written = write_html(_document(), ENGINE_DATA, "record", force=True)
    assert written.exists()
    assert "Field acceptance record" in written.read_text(encoding="utf-8")
    written.unlink()


def test_the_document_is_written_byte_for_byte(tmp_path: Path) -> None:
    document = _document()
    written = write_json(document, tmp_path, "doc")
    assert written.read_text(encoding="utf-8") == document_module.dumps(document)


def test_a_written_document_reads_back_as_the_same_document(tmp_path: Path) -> None:
    document = _campaign()
    written = write_json(document, tmp_path, "survey")
    reloaded = document_module.loads(written.read_text(encoding="utf-8"))
    assert document_module.dumps(reloaded) == document_module.dumps(document)


def test_two_exports_of_one_record_are_byte_identical(tmp_path: Path) -> None:
    document = _campaign()
    first = write_json(document, tmp_path, "one")
    second = write_json(document, tmp_path, "two")
    assert first.read_bytes() == second.read_bytes()


def test_an_existing_record_is_not_silently_replaced(tmp_path: Path) -> None:
    write_json(_document(), tmp_path, "doc")
    with pytest.raises(ExportError, match="--force"):
        write_json(_document(), tmp_path, "doc")


def test_forcing_replaces_the_record(tmp_path: Path) -> None:
    write_json(_document(), tmp_path, "doc")
    assert write_json(_document(), tmp_path, "doc", force=True).exists()


def test_the_html_record_refuses_to_overwrite_too(tmp_path: Path) -> None:
    write_html(_document(), tmp_path, "doc")
    with pytest.raises(ExportError, match="--force"):
        write_html(_document(), tmp_path, "doc")


def test_the_html_record_carries_the_campaign_s_cross_scan_sections() -> None:
    written = write_html(_campaign(), ENGINE_DATA, "campaign", force=True)
    text = written.read_text(encoding="utf-8")
    written.unlink()
    assert "Recurrence" in text or "recurrence" in text
    assert "missing-orientation-path" in text


def test_the_export_key_is_bound() -> None:
    keys = {binding[0] if isinstance(binding, tuple) else binding.key for binding in BINDINGS}
    assert "h" in keys
    assert "j" in keys


def test_pressing_h_writes_the_record_where_the_intake_lives(tmp_path: Path) -> None:
    export = tmp_path / "case.csv"
    export.write_bytes((ENGINE_DATA / "acceptance_single_export.txt").read_bytes())

    async def scenario() -> None:
        document = _document()
        browser = CampaignBrowser(
            document,
            build_view(document),
            [str(export)],
            _args(),
        )
        app = CampaignApp(browser=browser)
        async with app.run_test() as pilot:
            await pilot.pause()
            browser.action_export_html()
            await pilot.pause()
        assert (tmp_path / "case.html").exists()

    asyncio.run(scenario())
    (tmp_path / "case.html").unlink()


def test_an_export_with_no_intake_says_so_rather_than_guessing() -> None:
    document = _document()
    browser = CampaignBrowser(document, build_view(document))

    async def scenario() -> None:
        app = CampaignApp(browser=browser)
        async with app.run_test() as pilot:
            await pilot.pause()
            browser.action_export_json()
            await pilot.pause()

    asyncio.run(scenario())


def test_an_export_states_no_readiness_figure() -> None:
    written = write_html(_document(), ENGINE_DATA, "readiness", force=True)
    lowered = written.read_text(encoding="utf-8").lower()
    written.unlink()
    for word in ("readiness", "fitness", "confidence"):
        assert word not in lowered

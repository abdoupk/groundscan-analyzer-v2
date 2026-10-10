"""The intake: enumerating a folder, confirming it, and binding positions.

The risk this file exists to catch is a silent one. `_run_survey` sorts the
names it is given and indexes `--relate` and every bound by that position, so
a view that enumerated or displayed in any other order would bind a bound to
the wrong scan and produce a plausible record rather than an error. Every
test here that touches ordering asserts it against `sorted()` directly.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import cast

import pytest
from textual.widgets import SelectionList

from groundscan_analyzer import document as document_module
from groundscan_tui import cli
from groundscan_tui.app import CampaignApp, CampaignBrowser, IntakeScreen
from groundscan_tui.engine import EngineSession, IntakeError, intake, survey_argv
from groundscan_tui.model import build_view

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"
NAMES = ("Error Signal.csv", "Iron Box.csv", "Pipeline.csv", "notes.txt")


def _args(**overrides: object) -> argparse.Namespace:
    """Build the parsed command line the intake screen reads its bound from.

    Returns:
        A namespace carrying the command line's own defaults, overridden.
    """
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


def _folder(tmp_path: Path) -> Path:
    """A folder holding several scan exports and something that is not one.

    Returns:
        The folder, created and populated.
    """
    for name in NAMES:
        (tmp_path / name).write_text("not a real export", encoding="utf-8")
    return tmp_path


def test_a_folder_offers_only_csv_exports(tmp_path: Path) -> None:
    found = intake(_folder(tmp_path))
    assert [path.name for path in found] == [
        "Error Signal.csv",
        "Iron Box.csv",
        "Pipeline.csv",
    ]


def test_the_offered_order_is_the_engine_s_own(tmp_path: Path) -> None:
    """The engine sorts its intake; enumerating in any other order would bind
    a bound to the wrong scan, so this asserts against `sorted()` itself."""
    folder = _folder(tmp_path)
    assert [str(path) for path in intake(folder)] == [
        str(path) for path in sorted(folder.glob("*.csv"))
    ]


def test_enumeration_is_stable_across_calls(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert intake(folder) == intake(folder)


def test_a_path_that_is_not_a_folder_is_refused(tmp_path: Path) -> None:
    export = tmp_path / "one.csv"
    export.write_text("x", encoding="utf-8")
    with pytest.raises(IntakeError, match="is not a folder"):
        intake(export)


def test_a_folder_with_no_export_is_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(IntakeError, match=r"no \.csv export"):
        intake(tmp_path)


def test_a_survey_names_every_file_in_order() -> None:
    paths = [Path("a.csv"), Path("b.csv"), Path("c.csv")]
    assert survey_argv(paths, None) == [
        "groundscan-analyzer",
        "survey",
        "a.csv",
        "b.csv",
        "c.csv",
    ]


def test_a_declared_bound_becomes_one_flag_per_position() -> None:
    """Survey bounds are positional, so one declared value is expanded."""
    argv = survey_argv([Path("a.csv"), Path("b.csv")], "1.0,residual,bounded")
    assert argv == [
        "groundscan-analyzer",
        "survey",
        "a.csv",
        "b.csv",
        "--perturbation",
        "0,1.0,residual,bounded",
        "--perturbation",
        "1,1.0,residual,bounded",
    ]


def test_naming_both_an_export_and_a_folder_is_a_mistake(tmp_path: Path) -> None:
    args = _args(export=tmp_path / "a.csv", folder=tmp_path)
    with pytest.raises(IntakeError, match="not both"):
        cli.intake_from(args)


def test_naming_neither_is_a_mistake() -> None:
    with pytest.raises(IntakeError, match="one export or one folder"):
        cli.intake_from(_args())


def test_a_named_folder_becomes_its_own_intake(tmp_path: Path) -> None:
    found = cli.intake_from(_args(folder=_folder(tmp_path)))
    assert len(found) == 3


def test_a_named_export_becomes_a_one_file_intake(tmp_path: Path) -> None:
    assert cli.intake_from(_args(export=tmp_path / "a.csv")) == (tmp_path / "a.csv",)


def test_a_session_reads_a_command_line_once() -> None:
    """Re-rendering a campaign must not go back to the engine."""
    session = EngineSession()
    argv = ["groundscan-analyzer", "scan", str(ENGINE_DATA / "acceptance_single_export.txt")]
    first = session.read(argv)
    second = session.read(argv)
    assert first is second
    assert session.reads == 1
    assert session.cache_hits == 1


def test_a_changed_bound_is_a_different_read() -> None:
    session = EngineSession()
    session.read_export(ENGINE_DATA / "acceptance_single_export.txt", {"perturbation": None})
    session.read_export(
        ENGINE_DATA / "acceptance_single_export.txt",
        {"perturbation": "1.0,residual,bounded"},
    )
    assert session.reads == 2


def test_a_session_reads_a_folder_as_one_survey(tmp_path: Path) -> None:
    folder = tmp_path / "campaign"
    folder.mkdir()
    (folder / "one.csv").write_bytes(
        (ENGINE_DATA / "acceptance_single_export.txt").read_bytes(),
    )
    (folder / "two.csv").write_bytes((ENGINE_DATA / "acceptance_refused_export.txt").read_bytes())
    document = EngineSession().read_folder(intake(folder), None)
    assert len(document.scans) == 2
    assert [scan.position for scan in document.scans] == [0, 1]


def test_the_intake_screen_ticks_every_file(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = intake(_folder(tmp_path))
        app = CampaignApp.for_intake(EngineSession(), paths, _args())
        async with app.run_test() as pilot:
            await pilot.pause()
            picker = app.screen.query_one(SelectionList)
            assert set(picker.selected) == {0, 1, 2}

    asyncio.run(scenario())


def test_confirming_reads_only_the_ticked_files(tmp_path: Path) -> None:
    """Deselecting a file must change the intake, not just the display."""
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    real = (ENGINE_DATA / "acceptance_single_export.txt").read_bytes()
    (campaign / "a.csv").write_bytes(real)
    (campaign / "b.csv").write_bytes(real)

    async def scenario() -> None:
        app = CampaignApp.for_intake(EngineSession(), intake(campaign), _args())
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = cast("IntakeScreen", app.screen)
            picker = screen.query_one(SelectionList)
            picker.deselect_all()
            picker.select(0)
            await screen.action_confirm()
            await pilot.pause()
            assert isinstance(app.screen, CampaignBrowser)
            assert len(app.screen.view.scans) == 1

    asyncio.run(scenario())


def test_confirming_with_nothing_ticked_reads_nothing(tmp_path: Path) -> None:
    """An empty intake is refused rather than handed to the engine as zero scans."""

    async def scenario() -> None:
        app = CampaignApp.for_intake(EngineSession(), intake(_folder(tmp_path)), _args())
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = cast("IntakeScreen", app.screen)
            screen.query_one(SelectionList).deselect_all()
            await screen.action_confirm()
            await pilot.pause()
            assert isinstance(app.screen, IntakeScreen)
            assert screen.frozen == ()

    asyncio.run(scenario())

    asyncio.run(scenario())


def test_a_folder_of_unreadable_files_yields_refusals_not_a_crash(tmp_path: Path) -> None:
    """The input contract declines a file it cannot read; that is a result,
    not a failure, so a folder of them still opens."""
    document = EngineSession().read_folder(intake(_folder(tmp_path)), None)
    assert len(document.scans) == 3
    assert all(scan.status == "refused" for scan in document.scans)


def test_a_browser_over_a_campaign_names_its_files(tmp_path: Path) -> None:
    """The record carries no filename, so the viewer supplies its own."""
    document = document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )

    async def scenario() -> None:
        browser = CampaignBrowser(
            document,
            build_view(document),
            [str(path) for path in intake(_folder(tmp_path))],
        )
        app = CampaignApp(browser=browser)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert browser.view.scans[0].position == 0

    asyncio.run(scenario())

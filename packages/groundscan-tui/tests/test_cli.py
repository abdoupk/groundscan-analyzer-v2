"""The entry point: one parser, in the engine, reached through the shipped CLI."""

from __future__ import annotations

from pathlib import Path
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
import sys

import pytest

from groundscan_analyzer import document as document_module
import groundscan_tui
from groundscan_tui.cli import build_parser, main, run
from groundscan_tui.engine import ENGINE, EngineError, engine_argv, read_document
from groundscan_tui.model import RefusalView, ScanView

from .support import first_refusal, first_scan

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"
EXPORT = ENGINE_DATA / "acceptance_single_export.txt"
REFUSED = ENGINE_DATA / "acceptance_refused_export.txt"


def test_the_engine_is_the_only_reader() -> None:
    assert ENGINE == "groundscan-analyzer"


def test_the_command_is_the_engines_own() -> None:
    argv = engine_argv(EXPORT, {"perturbation": None, "displacement": None})
    assert argv == [ENGINE, "scan", str(EXPORT)]


def test_a_supplied_bound_is_forwarded_verbatim() -> None:
    argv = engine_argv(EXPORT, {"perturbation": "anchor=bounded:0.5", "displacement": None})
    assert argv == [ENGINE, "scan", "--perturbation", "anchor=bounded:0.5", str(EXPORT)]


def test_the_parser_owns_where_the_export_is_and_not_what_a_bound_means() -> None:
    parser = build_parser()
    assert parser.prog == "groundscan-tui"
    help_text = parser.format_help()
    assert "verbatim" in help_text
    assert "anchor" not in help_text
    assert "amplitude" not in help_text


def test_the_engine_reads_the_export_and_the_record_round_trips() -> None:
    document = read_document(EXPORT, {"perturbation": None, "displacement": None})
    assert isinstance(document, document_module.Document)
    assert document.contract_version == 1
    assert len(document.scans) == 1


def test_the_view_is_the_field_browser_where_the_contract_read() -> None:
    document = read_document(EXPORT, {"perturbation": None, "displacement": None})
    assert isinstance(first_scan(document), ScanView)


def test_a_refused_export_still_exits_zero_but_views_as_a_refusal() -> None:
    """The engine declines without failing, and the reason survives."""
    document = read_document(REFUSED, {"perturbation": None, "displacement": None})
    assert isinstance(first_refusal(document), RefusalView)


def _scan(export: Path, bounds: dict[str, str | None] | None = None) -> document_module.ScanRead:
    document = read_document(export, bounds or {"perturbation": None, "displacement": None})
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return scan


def test_a_bound_changes_what_the_record_carries() -> None:
    without = _scan(EXPORT).mask_invariance
    with_bound = _scan(EXPORT, {"perturbation": "1.0,residual,bounded", "displacement": None})
    unbounded = _scan(EXPORT, {"perturbation": "1.0,residual,unbounded", "displacement": None})
    assert without.reason == "requires-recorded-perturbation-bound"
    assert with_bound.mask_invariance.status == "not-guaranteed"
    assert unbounded.mask_invariance.reason == "requires-bounded-perturbation"


def test_a_malformed_bound_surfaces_the_engines_own_words() -> None:
    """The grammar is the engine's, so its complaint is what the reader sees."""
    with pytest.raises(EngineError, match="AMPLITUDE,ANCHOR,BOUNDEDNESS"):
        read_document(EXPORT, {"perturbation": "anchor=bounded:1.0", "displacement": None})


def test_a_missing_export_is_reported_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run([str(tmp_path / "absent.txt")]) == 1
    assert "cannot read scan export" in capsys.readouterr().err


def test_an_absent_engine_is_reported_not_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("groundscan_tui.engine.shutil.which", lambda _name: None)
    with pytest.raises(EngineError, match="not on PATH"):
        read_document(EXPORT, {"perturbation": None, "displacement": None})


def test_a_refused_run_level_read_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "run-level refusal\n")

    monkeypatch.setattr("groundscan_tui.engine.subprocess.run", refuse)
    assert run([str(EXPORT)]) == 1
    assert "run-level refusal" in capsys.readouterr().err


def test_the_entry_point_is_reexported_and_callable() -> None:
    assert groundscan_tui.main is main
    assert callable(main)


def test_help_is_written_without_starting_an_app(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "groundscan-tui" in capsys.readouterr().out


def test_the_console_script_is_installed() -> None:
    """The package is reachable as a command, which is how it is meant to run."""
    completed = subprocess.run(
        [sys.executable, "-c", "import groundscan_tui; print(groundscan_tui.main.__module__)"],
        capture_output=True,
        check=True,
        text=True,
    )
    assert "groundscan_tui.cli" in completed.stdout

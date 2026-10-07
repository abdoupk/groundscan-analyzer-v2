"""Tests for the command-line entry point."""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

import pytest

import groundscan_analyzer
from groundscan_analyzer.cli import main

if TYPE_CHECKING:
    from pathlib import Path

_RETIRED_NOUNS = (
    "acquisition",
    "anomaly",
    "benchmark",
    "blob",
    "candidate",
    "cluster",
    "confidence",
    "coordinate",
    "evidence",
    "fragment",
    "gate",
    "grid",
    "harness",
    "object",
    "score",
    "site",
    "target",
    "threshold",
)


def test_main_is_reexported() -> None:
    """The package must re-export the CLI entry point."""
    assert groundscan_analyzer.main is main


def test_top_level_help_lists_the_subcommand_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The console script names its fixed subcommand set and exits zero."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "scan" in out
    assert "survey" in out


@pytest.mark.parametrize("subcommand", ["scan", "survey"])
def test_each_subcommand_answers_help_with_its_inputs(
    subcommand: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every subcommand describes its inputs in plain text and exits zero."""
    with pytest.raises(SystemExit) as excinfo:
        main([subcommand, "--help"])
    assert excinfo.value.code == 0
    assert "scan" in capsys.readouterr().out


def test_no_arguments_prints_usage_listing_the_subcommand_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bare invocation prints the usage note rather than failing silently."""
    assert main([]) == 2
    out = capsys.readouterr().out
    assert "scan" in out
    assert "survey" in out


def test_bare_entry_point_reads_the_process_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting argv falls back to the process arguments."""
    monkeypatch.setattr(sys, "argv", ["groundscan-analyzer"])
    assert main() == 2
    assert "survey" in capsys.readouterr().out


def test_unknown_subcommand_exits_nonzero_with_usage_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown subcommand is misuse: non-zero exit, usage on stderr."""
    with pytest.raises(SystemExit) as excinfo:
        main(["nope"])
    assert excinfo.value.code != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_missing_required_input_exits_nonzero_with_usage_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A subcommand without its required inputs is misuse."""
    with pytest.raises(SystemExit) as excinfo:
        main(["scan"])
    assert excinfo.value.code != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_scan_accepts_one_named_scan(capsys: pytest.CaptureFixture[str]) -> None:
    """The scan subcommand takes one explicitly named scan export."""
    assert main(["scan", "first-export"]) == 0
    assert "first-export" in capsys.readouterr().out


def test_survey_accepts_explicitly_named_scans(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The survey subcommand takes explicitly named scan exports."""
    assert main(["survey", "first-export", "second-export"]) == 0
    out = capsys.readouterr().out
    assert "first-export" in out
    assert "second-export" in out


@pytest.mark.parametrize("argv", [["--help"], ["scan", "--help"], ["survey", "--help"]])
def test_help_output_carries_no_presentational_markup(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Help text is plain text: no colour codes or pager behaviour."""
    with pytest.raises(SystemExit):
        main(argv)
    assert "\x1b" not in capsys.readouterr().out


def test_valid_output_carries_no_presentational_markup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful output is plain text: no colour codes or pager behaviour."""
    assert main(["survey", "first-export"]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_survey_processes_scans_in_deterministic_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Multi-scan intake runs in sorted order regardless of argument order."""
    assert main(["survey", "charlie-export", "alpha-export", "bravo-export"]) == 0
    assert capsys.readouterr().out == "survey: alpha-export bravo-export charlie-export\n"


def test_survey_order_is_independent_of_argument_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Shuffled intake spellings yield the same output line."""
    assert main(["survey", "second-export", "first-export"]) == 0
    first = capsys.readouterr().out
    assert main(["survey", "first-export", "second-export"]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert first == "survey: first-export second-export\n"


def test_odd_scan_names_change_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """No scan relation is inferred from a filename: odd names echo back sorted."""
    assert main(["survey", "scan_Same_01", "scan_90-clockwise_02"]) == 0
    assert capsys.readouterr().out == "survey: scan_90-clockwise_02 scan_Same_01\n"


def test_survey_without_named_scans_is_misuse(capsys: pytest.CaptureFixture[str]) -> None:
    """A survey with no explicitly named scans is misuse."""
    with pytest.raises(SystemExit) as excinfo:
        main(["survey"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "usage" in err.lower()
    assert "\x1b" not in err


def test_intake_tokens_are_never_expanded(capsys: pytest.CaptureFixture[str]) -> None:
    """Glob characters stay literal intake names: nothing is expanded."""
    assert main(["survey", "b-export", "*"]) == 0
    assert capsys.readouterr().out == "survey: * b-export\n"


def test_unnamed_neighbours_are_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scans present beside the invocation are ignored unless explicitly named."""
    (tmp_path / "aaa-export").touch()
    (tmp_path / "zzz-export").touch()
    monkeypatch.chdir(tmp_path)
    assert main(["survey", "zzz-export"]) == 0
    assert capsys.readouterr().out == "survey: zzz-export\n"


@pytest.mark.parametrize("argv", [["--help"], ["scan", "--help"], ["survey", "--help"]])
def test_help_text_uses_glossary_nouns(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """Help text uses glossary nouns and no retired vocabulary."""
    with pytest.raises(SystemExit):
        main(argv)
    text = capsys.readouterr().out
    for noun in _RETIRED_NOUNS:
        assert re.search(rf"\b{noun}\b", text, re.IGNORECASE) is None


@pytest.mark.parametrize("argv", [["nope"], ["scan"], ["survey"]])
def test_diagnostic_text_uses_glossary_nouns(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Misuse diagnostics use glossary nouns and no retired vocabulary."""
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "usage" in err.lower()
    for noun in _RETIRED_NOUNS:
        assert re.search(rf"\b{noun}\b", err, re.IGNORECASE) is None


@pytest.mark.parametrize("argv", [["--help"], ["scan", "--help"], ["survey", "--help"]])
def test_help_text_carries_no_reporting_wiring(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI layer carries no reporting, structured-output, or harness wiring."""
    with pytest.raises(SystemExit):
        main(argv)
    text = capsys.readouterr().out.lower()
    for token in ("report", "markdown", "json", "harness", "orchestrat", "structured"):
        assert token not in text

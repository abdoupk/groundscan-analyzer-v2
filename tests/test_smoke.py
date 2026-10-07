"""Tests for the command-line entry point."""

import sys

import pytest

import groundscan_analyzer
from groundscan_analyzer.cli import main


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

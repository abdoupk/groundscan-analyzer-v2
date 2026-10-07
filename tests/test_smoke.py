"""Tests for the command-line entry point."""

from __future__ import annotations

import argparse
import re
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
import sys
from typing import TYPE_CHECKING

import pytest

import groundscan_analyzer
from groundscan_analyzer import document
from groundscan_analyzer.cli import main

if TYPE_CHECKING:
    from pathlib import Path

#: One minimal scan export: two impulses on two lines with a declared extent.
SCAN_EXPORT = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
1.0000,1.0000,10.0000
2.0000,1.0000,20.0000
1.0000,2.0000,30.0000
2.0000,2.0000,40.0000
"""

#: A scan export the contract declines: the response role is absent.
REFUSED_EXPORT = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y
1.0000,1.0000
2.0000,1.0000
"""


def write_export(path: Path, text: str = SCAN_EXPORT) -> str:
    """Write an export file, returning its intake token.

    Args:
        path: The directory receiving the export file.
        text: The export text to write.

    Returns:
        The file token to hand to the command line.
    """
    target = path / "scan-export.txt"
    target.write_text(text, encoding="utf-8")
    return str(target)


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


def test_missing_dispatch_prints_usage_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dispatch-less parse prints usage instead of failing."""

    def _parse_without_dispatch(
        _self: argparse.ArgumentParser, *_args: object, **_kwargs: object
    ) -> argparse.Namespace:
        return argparse.Namespace()

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", _parse_without_dispatch)
    assert main(["scan", "first-export"]) == 2
    out = capsys.readouterr().out
    assert "scan" in out
    assert "survey" in out


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


def test_scan_reads_one_named_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The scan subcommand reads its named export into a document."""
    token = write_export(tmp_path)
    assert main(["scan", token]) == 0
    out = capsys.readouterr().out
    scan = document.loads(out).scans[0]
    assert scan.status == "read"
    assert token not in out
    assert "scan-export.txt" not in out


def test_scan_missing_export_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    """A name that reads nothing is an error, never an expansion."""
    assert main(["scan", "no-such-export"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err


def test_scan_refused_export_still_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused scan is a record on stdout, not a failed run."""
    target = tmp_path / "bad-export.txt"
    target.write_text(REFUSED_EXPORT, encoding="utf-8")
    assert main(["scan", str(target)]) == 0
    scan = document.loads(capsys.readouterr().out).scans[0]
    assert scan.status == "refused"


def test_scan_undecodable_export_stops_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bytes that decode as nothing stop the run with no document."""
    target = tmp_path / "bad-export.txt"
    target.write_bytes(b"\xff\xfe\x00bad")
    assert main(["scan", str(target)]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err


def test_survey_reads_named_exports_in_sorted_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Survey intake runs in sorted order regardless of argument order."""
    first = tmp_path / "alpha-export.txt"
    second = tmp_path / "bravo-export.txt"
    first.write_text(SCAN_EXPORT, encoding="utf-8")
    second.write_text(SCAN_EXPORT.replace("10.0000", "99.0000"), encoding="utf-8")
    assert main(["survey", str(second), str(first)]) == 0
    forward = capsys.readouterr().out
    assert main(["survey", str(first), str(second)]) == 0
    assert capsys.readouterr().out == forward
    doc = document.loads(forward)
    assert len(doc.scans) == 2
    assert doc.scans[0].status == "read"
    assert doc.scans[1].status == "read"


def test_survey_refusal_isolated_to_its_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One bad scan among several refuses only that scan."""
    good = tmp_path / "good-export.txt"
    bad = tmp_path / "bad-export.txt"
    good.write_text(SCAN_EXPORT, encoding="utf-8")
    bad.write_text(REFUSED_EXPORT, encoding="utf-8")
    assert main(["survey", str(good), str(bad)]) == 0
    doc = document.loads(capsys.readouterr().out)
    assert sorted(scan.status for scan in doc.scans) == ["read", "refused"]


def test_survey_run_failure_stops_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An undecodable file stops the survey instead of refusing one scan."""
    good = tmp_path / "good-export.txt"
    bad = tmp_path / "bad-export.txt"
    good.write_text(SCAN_EXPORT, encoding="utf-8")
    bad.write_bytes(b"\xff\xfe\x00bad")
    assert main(["survey", str(good), str(bad)]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err


def test_two_fresh_processes_emit_identical_bytes(tmp_path: Path) -> None:
    """The same export gives the same bytes across two fresh processes."""
    token = write_export(tmp_path)
    code = (
        f"import sys; from groundscan_analyzer.cli import main; sys.exit(main(['scan', {token!r}]))"
    )
    first = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    second = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stdout


@pytest.mark.parametrize("argv", [["--help"], ["scan", "--help"], ["survey", "--help"]])
def test_help_output_carries_no_presentational_markup(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Help text is plain text: no colour codes or pager behaviour."""
    with pytest.raises(SystemExit):
        main(argv)
    assert "\x1b" not in capsys.readouterr().out


def test_valid_output_carries_no_presentational_markup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Successful output is plain text: no colour codes or pager behaviour."""
    token = write_export(tmp_path)
    assert main(["scan", token]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_odd_scan_names_change_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No scan relation is inferred from a filename: odd names still read."""
    first = tmp_path / "scan_Same_01.txt"
    second = tmp_path / "scan_90-clockwise_02.txt"
    first.write_text(SCAN_EXPORT, encoding="utf-8")
    second.write_text(SCAN_EXPORT, encoding="utf-8")
    assert main(["survey", str(first), str(second)]) == 0
    doc = document.loads(capsys.readouterr().out)
    assert [scan.status for scan in doc.scans] == ["read", "read"]


def test_survey_without_named_scans_is_misuse(capsys: pytest.CaptureFixture[str]) -> None:
    """A survey with no explicitly named scans is misuse."""
    with pytest.raises(SystemExit) as excinfo:
        main(["survey"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "usage" in err.lower()
    assert "\x1b" not in err


def test_intake_tokens_are_never_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Glob characters stay literal intake names: nothing is expanded."""
    monkeypatch.chdir(tmp_path)
    assert main(["survey", "*"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err


def test_unnamed_neighbours_are_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scans present beside the invocation are ignored unless explicitly named."""
    (tmp_path / "aaa-export.txt").write_text(SCAN_EXPORT, encoding="utf-8")
    named = tmp_path / "zzz-export.txt"
    named.write_text(SCAN_EXPORT.replace("10.0000", "77.0000"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["survey", "zzz-export.txt"]) == 0
    doc = document.loads(capsys.readouterr().out)
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert scan.cells[0].response is not None
    assert bits(scan.cells[0].response) == bits(77.0)


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

"""Acceptance bytes: the committed document shape with its drift test.

A convention bump that moves shipped contract data moves these bytes with
it, deliberately: the drift test is left whole, never exempted.
"""

from __future__ import annotations

from pathlib import Path

from groundscan_analyzer import document, reader

DATA = Path(__file__).resolve().parent / "data"


def test_single_scan_acceptance_bytes_do_not_drift() -> None:
    """The frozen single-scan document matches the engine byte for byte."""
    export = (DATA / "acceptance_single_export.txt").read_bytes()
    frozen = (DATA / "acceptance_single.json").read_text(encoding="utf-8")
    assert document.dumps(reader.read_document([export])) == frozen


def test_survey_acceptance_bytes_do_not_drift() -> None:
    """The frozen survey document records its refusal byte for byte."""
    first = (DATA / "acceptance_single_export.txt").read_bytes()
    second = (DATA / "acceptance_refused_export.txt").read_bytes()
    frozen = (DATA / "acceptance_survey.json").read_text(encoding="utf-8")
    assert document.dumps(reader.read_document([first, second])) == frozen

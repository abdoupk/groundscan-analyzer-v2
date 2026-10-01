"""Tests for the command-line entry point."""

import pytest

import groundscan_analyzer
from groundscan_analyzer.cli import main


def test_main_is_reexported() -> None:
    """The package must re-export the CLI entry point."""
    assert groundscan_analyzer.main is main


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    """Running the entry point prints the greeting."""
    main()
    assert "Hello from groundscan-analyzer!" in capsys.readouterr().out

"""Reaching the engine: intake, command lines, and the session that reads once.

The engine is never reopened to serve this. Its parsers for the perturbation
and displacement bounds are private, and there are three ways to reach the
same values -- duplicate the parsers here, export them from the engine, or
read through the CLI the engine already ships. Only the third keeps one
parser for one contract, leaves every module in `src/groundscan_analyzer/`
untouched, and makes the thing on screen the thing `groundscan-analyzer scan`
actually emits.

The bound strings are forwarded verbatim. This module decides where an
export is and how a folder is read; what a bound means belongs to the engine,
so its grammar is not restated here.
"""

from __future__ import annotations

import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
from typing import TYPE_CHECKING

from groundscan_analyzer import document as document_module

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

ENGINE: str = "groundscan-analyzer"

EXIT_OK: int = 0
EXIT_FAILED: int = 1


class EngineError(RuntimeError):
    """The engine could not be run, or declined to read."""


class IntakeError(RuntimeError):
    """A folder could not be offered as an intake."""


def intake(directory: Path) -> tuple[Path, ...]:
    """Enumerate the scan-shaped files in a folder, in the engine's own order.

    The engine never discovers files -- `survey *` stays literal and unnamed
    neighbours are never read -- so this is the viewer's discovery, and the
    operator confirms it before anything runs. The order is the engine's:
    `_run_survey` sorts the names it is given, and every relation and bound is
    indexed by that position, so enumerating in any other order would bind
    them to the wrong scans.

    Args:
        directory: The folder to enumerate.

    Returns:
        Every `.csv` in the folder, name-sorted.

    Raises:
        IntakeError: Where the path is not a folder, or holds no `.csv`.
    """
    if not directory.is_dir():
        message = f"{directory} is not a folder"
        raise IntakeError(message)
    found = tuple(sorted(directory.glob("*.csv")))
    if not found:
        message = f"{directory} holds no .csv export to read"
        raise IntakeError(message)
    return found


def engine_argv(export: Path, bounds: dict[str, str | None]) -> list[str]:
    """Build the engine's `scan` command line, program name first.

    Args:
        export: The export to read.
        bounds: Bound flags to forward, each absent or a value.

    Returns:
        The argv the engine is run with.
    """
    argv = [ENGINE, "scan"]
    for flag, value in bounds.items():
        if value is not None:
            argv += [f"--{flag}", value]
    argv.append(str(export))
    return argv


def survey_argv(paths: Sequence[Path], bound: str | None) -> list[str]:
    """Build the engine's `survey` command line from a frozen intake.

    A bound declared here is the engine's `AMPLITUDE,ANCHOR,BOUNDEDNESS` and
    is expanded to every intake position, because in survey mode a bound is
    positional and the operator is declaring one value for the campaign.

    Args:
        paths: The frozen intake, in the order the engine will index it.
        bound: The engine's bound grammar, or None to declare no bound.

    Returns:
        The argv the engine is run with.
    """
    argv = [ENGINE, "survey", *(str(path) for path in paths)]
    if bound is not None:
        for position in range(len(paths)):
            argv += ["--perturbation", f"{position},{bound}"]
    return argv


def _resolve(argv: Sequence[str]) -> list[str]:
    """Replace the engine's own name with the executable actually on PATH.

    Args:
        argv: The engine's command line, program name first.

    Returns:
        The argv with its program resolved.

    Raises:
        EngineError: Where the engine is not on PATH.
    """
    executable = shutil.which(argv[0])
    if executable is None:
        message = f"{ENGINE} is not on PATH; the engine is the only reader of an export"
        raise EngineError(message)
    return [executable, *argv[1:]]


def _run(argv: Sequence[str]) -> document_module.Document:
    """Run the engine once and return the record it emits.

    Args:
        argv: The engine's command line, program name first.

    Returns:
        The document the engine emitted.

    Raises:
        EngineError: Where the engine is absent, or declined to read.
    """
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv, no shell
        _resolve(argv),
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != EXIT_OK:
        message = completed.stderr.strip() or f"{ENGINE} exited {completed.returncode}"
        raise EngineError(message)
    return document_module.loads(completed.stdout)


def read_document(export: Path, bounds: dict[str, str | None]) -> document_module.Document:
    """Read one export through the engine and return the record it emits.

    Args:
        export: The export to read.
        bounds: Bound flags to forward, each absent or a value.

    Returns:
        The document the engine emitted.
    """
    return _run(engine_argv(export, bounds))


class EngineSession:
    """The engine, reached once per distinct command line.

    Re-rendering a campaign must not re-read nine exports, so the record is
    kept for the life of the session and keyed by the exact argv that
    produced it. A changed bound is a different argv and therefore a
    different read.

    Attributes:
        cache_hits: How many reads a cached record answered, which is how a
            test shows that a redraw did not go back to the engine.
    """

    def __init__(self) -> None:
        """Open a session with nothing read yet."""
        self._records: dict[tuple[str, ...], document_module.Document] = {}
        self.cache_hits = 0

    @property
    def reads(self) -> int:
        """How many command lines this session has actually run."""
        return len(self._records)

    def read(self, argv: Sequence[str]) -> document_module.Document:
        """Return the record for an argv, reading through if it is new.

        Args:
            argv: The engine's command line, program name first.

        Returns:
            The document the engine emitted.
        """
        key = tuple(argv)
        if key in self._records:
            self.cache_hits += 1
            return self._records[key]
        record = _run(key)
        self._records[key] = record
        return record

    def read_export(self, export: Path, bounds: dict[str, str | None]) -> document_module.Document:
        """Read one export, the way `scan` does.

        Args:
            export: The export to read.
            bounds: Bound flags to forward, each absent or a value.

        Returns:
            The document the engine emitted.
        """
        return self.read(engine_argv(export, bounds))

    def read_folder(self, paths: Sequence[Path], bound: str | None) -> document_module.Document:
        """Read a frozen intake as one survey.

        Args:
            paths: The frozen intake, in intake order.
            bound: The engine's bound grammar, or None to declare no bound.

        Returns:
            The document the engine emitted.
        """
        return self.read(survey_argv(paths, bound))

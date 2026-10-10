"""The entry point: read one export through the engine, then view it.

The engine is not reopened to serve this. Its parsers for the perturbation
and displacement bounds are private, and there are three ways to reach the
same values -- duplicate the parsers here, export them from the engine, or
read through the CLI the engine already ships. Only the third keeps one
parser for one contract, leaves every module in `src/groundscan_analyzer/`
untouched, and makes the thing on screen the thing `groundscan-analyzer
scan` actually emits.

The bound arguments are forwarded verbatim. This entry point decides where
an export is and how it is viewed; what a bound means belongs to the engine,
so its grammar is not restated here.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
import sys
from typing import TYPE_CHECKING

from groundscan_analyzer import document as document_module
from groundscan_tui.app import FieldBrowser, RefusalApp
from groundscan_tui.model import RefusalView, build_view

if TYPE_CHECKING:
    from collections.abc import Sequence

    from groundscan_tui.model import ScanView

ENGINE: str = "groundscan-analyzer"

EXIT_OK: int = 0
EXIT_FAILED: int = 1


class EngineError(RuntimeError):
    """The engine could not be run, or declined to read the export."""


def build_parser() -> argparse.ArgumentParser:
    """Describe the one command this entry point has.

    Returns:
        The argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="groundscan-tui",
        description="View one GroundScan export as a field and its detections.",
    )
    parser.add_argument("export", type=Path, metavar="EXPORT", help="The export to view.")
    parser.add_argument(
        "--perturbation",
        metavar="BOUND",
        default=None,
        help="Field perturbation bound, forwarded to the engine verbatim.",
    )
    parser.add_argument(
        "--displacement",
        metavar="BOUND",
        default=None,
        help="Displacement bound, forwarded to the engine verbatim.",
    )
    return parser


def engine_argv(export: Path, bounds: dict[str, str | None]) -> list[str]:
    """Build the engine's own command line, program name first.

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


def read_document(export: Path, bounds: dict[str, str | None]) -> document_module.Document:
    """Read one export through the engine and return the record it emits.

    Args:
        export: The export to read.
        bounds: Bound flags to forward, each absent or a value.

    Returns:
        The document the engine emitted.

    Raises:
        EngineError: Where the engine is absent, or declined to read.
    """
    argv = engine_argv(export, bounds)
    executable = shutil.which(argv[0])
    if executable is None:
        message = f"{ENGINE} is not on PATH; the engine is the only reader of an export"
        raise EngineError(message)
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv, no shell
        [executable, *argv[1:]],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != EXIT_OK:
        message = completed.stderr.strip() or f"{ENGINE} exited {completed.returncode}"
        raise EngineError(message)
    return document_module.loads(completed.stdout)


def _view(view: ScanView | RefusalView) -> FieldBrowser | RefusalApp:
    """Choose the application the projection calls for.

    Args:
        view: The projection of one document.

    Returns:
        The refusal view where the contract declined, else the browser.
    """
    return RefusalApp(view) if isinstance(view, RefusalView) else FieldBrowser(view)


def run(argv: Sequence[str] | None = None) -> int:
    """Read an export and open the view over it.

    Args:
        argv: The command line, or None to read the process's own.

    Returns:
        Zero on success, one where the engine could not be read through.
    """
    args = build_parser().parse_args(argv)
    bounds = {"perturbation": args.perturbation, "displacement": args.displacement}
    try:
        document = read_document(args.export, bounds)
    except EngineError as error:
        print(str(error), file=sys.stderr)
        return EXIT_FAILED
    _view(build_view(document)).run()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the entry point.

    Args:
        argv: The command line, or None to read the process's own.

    Returns:
        The process exit code.
    """
    return run(argv)

"""The entry point: decide an intake, read it, and open the view over it.

Naming one export and naming a folder are different claims about the
intake, so both are stated plainly and neither is inferred from the other.
A single export reads through the engine's `scan`; a folder reads through
`survey` after the operator has agreed the file list, because the engine
indexes every bound and every relation by a position in that list and never
discovers files itself.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from groundscan_tui.app import CampaignApp, CampaignBrowser
from groundscan_tui.engine import (
    EXIT_FAILED,
    EXIT_OK,
    EngineError,
    EngineSession,
    IntakeError,
    intake,
)
from groundscan_tui.model import build_view

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path as PathType


def build_parser() -> argparse.ArgumentParser:
    """Describe the one command this entry point has.

    Returns:
        The argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="groundscan-tui",
        description="View one GroundScan export, or a folder of them, as a field.",
    )
    parser.add_argument(
        "export",
        type=Path,
        metavar="EXPORT",
        nargs="?",
        help="The export to view.",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        metavar="DIR",
        default=None,
        help="A folder of exports to read as one campaign.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        metavar="DIR",
        default=None,
        help="Where to write exported records; defaults to the intake folder.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an exported file that already exists.",
    )
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


def _bounds(args: argparse.Namespace) -> dict[str, str | None]:
    """Collect the bound flags the single-export path forwards.

    Returns:
        Each flag's value, absent or a value to forward.
    """
    return {"perturbation": args.perturbation, "displacement": args.displacement}


def intake_from(args: argparse.Namespace) -> tuple[Path, ...]:
    """Decide what the command line is asking to read.

    Naming a file and naming a folder are different claims about the intake,
    so both together is a mistake rather than a precedence rule.

    Args:
        args: The parsed command line.

    Returns:
        The one export, or the folder's scan-shaped files.

    Raises:
        IntakeError: Where neither or both were named, or a folder is empty.
    """
    if args.export is not None and args.folder is not None:
        message = "name one export or one folder, not both"
        raise IntakeError(message)
    if args.folder is not None:
        return intake(args.folder)
    if args.export is not None:
        return (args.export,)
    message = "name one export or one folder"
    raise IntakeError(message)


def _single(
    paths: Sequence[PathType], session: EngineSession, args: argparse.Namespace
) -> CampaignApp:
    """Read one export and wrap it in the browser.

    Args:
        paths: The one export.
        session: The engine session to read through.
        args: The parsed command line.

    Returns:
        The application opening on the browser for that export.
    """
    document = session.read_export(paths[0], _bounds(args))
    return CampaignApp(
        browser=CampaignBrowser(
            document,
            build_view(document),
            tuple(str(path) for path in paths),
            args,
        ),
    )


def _campaign(
    paths: Sequence[PathType], session: EngineSession, args: argparse.Namespace
) -> CampaignApp:
    """Open on the intake screen so the operator confirms the file list.

    Args:
        paths: The enumerated intake, name-sorted.
        session: The engine session to read through.
        args: The parsed command line.

    Returns:
        The application, opening on the intake screen.
    """
    return CampaignApp.for_intake(session, paths, args)


def run(argv: Sequence[str] | None = None) -> int:
    """Read an intake and open the view over it.

    Args:
        argv: The command line, or None to read the process's own.

    Returns:
        Zero on success, one where the intake or the engine could not be read.
    """
    args = build_parser().parse_args(argv)
    try:
        paths = intake_from(args)
    except IntakeError as error:
        print(str(error), file=sys.stderr)
        return EXIT_FAILED
    session = EngineSession()
    try:
        campaign = (
            _single(paths, session, args)
            if len(paths) == 1 and args.folder is None
            else _campaign(paths, session, args)
        )
    except EngineError as error:
        print(str(error), file=sys.stderr)
        return EXIT_FAILED
    campaign.run()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the entry point.

    Args:
        argv: The command line, or None to read the process's own.

    Returns:
        The process exit code.
    """
    return run(argv)

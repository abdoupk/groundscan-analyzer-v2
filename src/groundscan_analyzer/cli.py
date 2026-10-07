"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _run_scan(args: argparse.Namespace) -> int:
    """Analyse one scan from its named export.

    Args:
        args: The parsed arguments, carrying the named scan export.

    Returns:
        The process exit code: zero on success.
    """
    print(f"scan: {args.scan}")
    return 0


def _run_survey(args: argparse.Namespace) -> int:
    """Analyse a survey of explicitly named scans.

    The named scans are handled in sorted order so the same survey reads
    the same way regardless of argument or filesystem order. Names are
    opaque intake tokens: no scan relation is inferred from them.

    Args:
        args: The parsed arguments, carrying the named scan exports.

    Returns:
        The process exit code: zero on success.
    """
    print(f"survey: {' '.join(sorted(args.scans))}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the parser behind the fixed subcommand set.

    Returns:
        The parser: ``scan`` for one named scan, ``survey`` for named scans.
    """
    parser = argparse.ArgumentParser(
        prog="groundscan-analyzer",
        description="Read a survey of scan exports and emit detections.",
    )
    subcommands = parser.add_subparsers(title="subcommands", dest="command", required=True)
    scan = subcommands.add_parser("scan", help="Analyse one scan from its named export.")
    scan.add_argument("scan", metavar="SCAN", help="Path of the scan export to analyse.")
    scan.set_defaults(func=_run_scan)
    survey = subcommands.add_parser("survey", help="Analyse a survey of explicitly named scans.")
    survey.add_argument(
        "scans", metavar="SCAN", nargs="+", help="Paths of the scan exports in the survey."
    )
    survey.set_defaults(func=_run_survey)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the groundscan-analyzer command-line interface.

    Bare invocation prints usage on stdout with exit 2; parse failures print
    usage on stderr with exit 2.

    Args:
        argv: The command-line arguments without the program name. The process
            arguments are read when omitted.

    Returns:
        The process exit code: zero on success, non-zero on misuse.
    """
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        _build_parser().print_help()
        return 2
    args = _build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], int] | None = getattr(args, "func", None)
    if handler is None:
        _build_parser().print_help()
        return 2
    return handler(args)

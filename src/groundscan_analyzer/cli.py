"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from groundscan_analyzer import document, frames, reader

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _read_export(name: str) -> bytes | None:
    """Read one named export, reporting an unreadable file on stderr.

    Args:
        name: The intake token naming the scan export.

    Returns:
        The raw export bytes, or None when the file cannot be read.
    """
    try:
        return Path(name).read_bytes()
    except OSError:
        print(f"cannot read scan export: {name}", file=sys.stderr)
        return None


def _emit(doc: document.Document) -> int:
    """Write one survey document to stdout.

    Args:
        doc: The validated survey document.

    Returns:
        The process exit code: zero on success.
    """
    print(document.dumps(doc), end="")
    return 0


def _run_scan(args: argparse.Namespace) -> int:
    """Analyse one scan from its named export.

    Args:
        args: The parsed arguments, carrying the named scan export.

    Returns:
        The process exit code: zero on success, one when the file cannot
        be read or stops the run.
    """
    content = _read_export(args.scan)
    if content is None:
        return 1
    try:
        return _emit(reader.read_document([content]))
    except reader.RunLevelError as exc:
        print(f"scan export cannot be read: {exc}", file=sys.stderr)
        return 1


def _parse_relation(token: str) -> frames.Relation:
    """Parse one relation declaration over sorted intake positions.

    Positions index the ordered intake names from zero; words name one
    of the four declared relations exactly, never repaired into a
    neighbour. Filenames never participate: no relation is inferred from
    them, and positions never quote them.

    Args:
        token: The declaration as ``A,B,WORD``.

    Returns:
        The declared relation.

    Raises:
        argparse.ArgumentTypeError: When the shape, positions or word
            fall outside the declared vocabulary.
    """
    parts = [part.strip() for part in token.split(",")]
    try:
        first_text, second_text, word = parts
    except ValueError:
        msg = f"relation must read A,B,WORD: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    try:
        first, second = int(first_text), int(second_text)
    except ValueError:
        msg = f"relation positions must be integers: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if word not in frames.RELATION_WORDS:
        msg = f"relation word must be one of {', '.join(frames.RELATION_WORDS)}: {token!r}"
        raise argparse.ArgumentTypeError(msg)
    return frames.Relation(first, second, word)


def _run_survey(args: argparse.Namespace) -> int:
    """Analyse a survey of explicitly named scans.

    The named scans are handled in sorted order so the same survey reads
    the same way regardless of argument or filesystem order. Names are
    opaque intake tokens: no scan relation is inferred from them. One bad
    scan among several refuses only that scan; a run-level failure stops
    the run instead.

    Args:
        args: The parsed arguments, carrying the named scan exports.

    Returns:
        The process exit code: zero on success, one when a file cannot
        be read or stops the run, two on a relation naming no scan.
    """
    names = sorted(args.scans)
    contents: list[bytes] = []
    for name in names:
        content = _read_export(name)
        if content is None:
            return 1
        contents.append(content)
    for relation in args.relate:
        if not 0 <= relation.first < len(names) or not 0 <= relation.second < len(names):
            _build_parser().print_usage(sys.stderr)
            print(f"survey: relation names no scan: {relation!r}", file=sys.stderr)
            return 2
    try:
        return _emit(reader.read_document(contents, args.relate))
    except reader.RunLevelError as exc:
        print(f"survey cannot be read: {exc}", file=sys.stderr)
        return 1


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
    survey.add_argument(
        "--relate",
        action="append",
        default=[],
        metavar="A,B,WORD",
        type=_parse_relation,
        help=(
            "Declare how two scans relate, over positions into the ordered "
            "intake from zero with one of same, opposite, 90-clockwise, "
            "90-counter-clockwise; repeatable. Words are exact."
        ),
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

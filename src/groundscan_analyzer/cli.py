"""Command-line entry point."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from groundscan_analyzer import document, frames, reader

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from groundscan_analyzer import perturbation as perturbation_module


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

    The real loader asserts the operator source: no flag accepts the
    fixture label, so a synthetic declaration can never enter here.

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
        return _emit(
            reader.read_document(
                [content],
                perturbation_bounds=[args.perturbation],
                displacement_bounds=[args.displacement],
                assertion_sources=[document.OPERATOR_SOURCE],
            )
        )
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


def _parse_amplitude(text: str) -> float:
    """Parse one declared amplitude to a finite non-negative float.

    Args:
        text: The amplitude as written in the declaration.

    Returns:
        The amplitude, with negative zero canonicalised to positive zero.

    Raises:
        argparse.ArgumentTypeError: When the text is not a number, or the
            number is non-finite or negative.
    """
    try:
        value = float(text.strip())
    except ValueError:
        msg = f"amplitude must be a number: {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if not math.isfinite(value) or value < 0:
        msg = f"amplitude must be finite and non-negative: {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    return 0.0 if value == 0 else value


def _parse_anchor(word: str, token: str) -> perturbation_module.Anchor:
    """Parse one anchor word to its closed vocabulary value.

    Args:
        word: The anchor as written in the declaration.
        token: The whole declaration, for the misuse note.

    Returns:
        The residual anchor or the payload anchor.

    Raises:
        argparse.ArgumentTypeError: When the word names neither anchor.
    """
    if word == "residual":
        return "residual"
    if word == "payload":
        return "payload"
    msg = f"anchor must be residual or payload: {token!r}"
    raise argparse.ArgumentTypeError(msg)


def _parse_boundedness(word: str, token: str) -> perturbation_module.Boundedness:
    """Parse one boundedness word to its closed vocabulary value.

    Args:
        word: The boundedness as written in the declaration.
        token: The whole declaration, for the misuse note.

    Returns:
        The bounded class or the unbounded class.

    Raises:
        argparse.ArgumentTypeError: When the word names neither class.
    """
    if word == "bounded":
        return "bounded"
    if word == "unbounded":
        return "unbounded"
    msg = f"boundedness must be bounded or unbounded: {token!r}"
    raise argparse.ArgumentTypeError(msg)


def _perturbation_from_parts(
    amplitude_text: str, anchor_word: str, boundedness_word: str, token: str
) -> document.PerturbationBound:
    """Build one field perturbation bound from its declared parts.

    Args:
        amplitude_text: The amplitude as written in the declaration.
        anchor_word: The anchor as written in the declaration.
        boundedness_word: The boundedness as written in the declaration.
        token: The whole declaration, for the misuse note.

    Returns:
        The bound as the record carries it.
    """
    return document.PerturbationBound(
        amplitude=_parse_amplitude(amplitude_text),
        anchor=_parse_anchor(anchor_word, token),
        boundedness=_parse_boundedness(boundedness_word, token),
    )


def _displacement_from_parts(
    amplitude_text: str, boundedness_word: str, token: str
) -> document.DisplacementBound:
    """Build one registration displacement bound from its declared parts.

    Args:
        amplitude_text: The amplitude as written in the declaration.
        boundedness_word: The boundedness as written in the declaration.
        token: The whole declaration, for the misuse note.

    Returns:
        The bound as the record carries it.
    """
    return document.DisplacementBound(
        amplitude=_parse_amplitude(amplitude_text),
        boundedness=_parse_boundedness(boundedness_word, token),
    )


def _parse_scan_perturbation(token: str) -> document.PerturbationBound:
    """Parse one single-scan field perturbation declaration.

    Args:
        token: The declaration as ``AMPLITUDE,ANCHOR,BOUNDEDNESS``.

    Returns:
        The bound as the record carries it.

    Raises:
        argparse.ArgumentTypeError: When the shape or any part falls
            outside the declared vocabulary.
    """
    parts = [part.strip() for part in token.split(",")]
    try:
        amplitude_text, anchor_word, boundedness_word = parts
    except ValueError:
        msg = f"perturbation must read AMPLITUDE,ANCHOR,BOUNDEDNESS: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    return _perturbation_from_parts(amplitude_text, anchor_word, boundedness_word, token)


def _parse_scan_displacement(token: str) -> document.DisplacementBound:
    """Parse one single-scan registration displacement declaration.

    Args:
        token: The declaration as ``AMPLITUDE,BOUNDEDNESS``.

    Returns:
        The bound as the record carries it.

    Raises:
        argparse.ArgumentTypeError: When the shape or any part falls
            outside the declared vocabulary.
    """
    parts = [part.strip() for part in token.split(",")]
    try:
        amplitude_text, boundedness_word = parts
    except ValueError:
        msg = f"displacement must read AMPLITUDE,BOUNDEDNESS: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    return _displacement_from_parts(amplitude_text, boundedness_word, token)


def _parse_position(text: str, token: str) -> int:
    """Parse one intake position to its integer.

    Args:
        text: The position as written in the declaration.
        token: The whole declaration, for the misuse note.

    Returns:
        The intake position.

    Raises:
        argparse.ArgumentTypeError: When the position is not an integer.
    """
    try:
        return int(text.strip())
    except ValueError:
        msg = f"bound positions must be integers: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None


def _parse_survey_perturbation(token: str) -> tuple[int, document.PerturbationBound]:
    """Parse one survey field perturbation declaration over sorted intake positions.

    Positions index the ordered intake names from zero, exactly as declared
    relations do.

    Args:
        token: The declaration as ``POSITION,AMPLITUDE,ANCHOR,BOUNDEDNESS``.

    Returns:
        The intake position with the bound as the record carries it.

    Raises:
        argparse.ArgumentTypeError: When the shape, the position or any
            part falls outside the declared vocabulary.
    """
    parts = [part.strip() for part in token.split(",")]
    try:
        position_text, amplitude_text, anchor_word, boundedness_word = parts
    except ValueError:
        msg = f"perturbation must read POSITION,AMPLITUDE,ANCHOR,BOUNDEDNESS: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    bound = _perturbation_from_parts(amplitude_text, anchor_word, boundedness_word, token)
    return _parse_position(position_text, token), bound


def _parse_survey_displacement(token: str) -> tuple[int, document.DisplacementBound]:
    """Parse one survey displacement declaration over sorted intake positions.

    Positions index the ordered intake names from zero, exactly as declared
    relations do.

    Args:
        token: The declaration as ``POSITION,AMPLITUDE,BOUNDEDNESS``.

    Returns:
        The intake position with the bound as the record carries it.

    Raises:
        argparse.ArgumentTypeError: When the shape, the position or any
            part falls outside the declared vocabulary.
    """
    parts = [part.strip() for part in token.split(",")]
    try:
        position_text, amplitude_text, boundedness_word = parts
    except ValueError:
        msg = f"displacement must read POSITION,AMPLITUDE,BOUNDEDNESS: {token!r}"
        raise argparse.ArgumentTypeError(msg) from None
    bound = _displacement_from_parts(amplitude_text, boundedness_word, token)
    return _parse_position(position_text, token), bound


def _indexed_bounds[BoundT](
    declared: Sequence[tuple[int, BoundT]], count: int, kind: str
) -> tuple[list[BoundT | None], str | None]:
    """Index declared bounds by intake position, noting misuse without printing.

    A position naming no scan stops the run rather than shifting a
    declaration onto the wrong scan, and two declarations for one scan stop
    it rather than letting one silently win.

    Args:
        declared: The parsed position and bound pairs in argument order.
        count: The ordered intake size the positions index into.
        kind: The declaration kind naming the misuse note.

    Returns:
        The bounds aligned with intake, None where undeclared, with the
        misuse note or None where every declaration placed.
    """
    placed: dict[int, BoundT] = {}
    for position, bound in declared:
        if not 0 <= position < count:
            return [], f"survey: {kind} names no scan: {position!r}"
        if position in placed:
            return [], f"survey: {kind} names one scan twice: {position!r}"
        placed[position] = bound
    return [placed.get(index) for index in range(count)], None


def _survey_bounds(
    args: argparse.Namespace, count: int
) -> tuple[list[document.PerturbationBound | None], list[document.DisplacementBound | None]] | None:
    """Align declared bounds with intake, printing misuse and giving up as None.

    Args:
        args: The parsed arguments, carrying the declared bounds.
        count: The ordered intake size the positions index into.

    Returns:
        The aligned bounds, or None after printing usage where a
        declaration names no scan or names one twice.
    """
    perturbation_bounds, note = _indexed_bounds(args.perturbation, count, "perturbation")
    if note is not None:
        _build_parser().print_usage(sys.stderr)
        print(note, file=sys.stderr)
        return None
    displacement_bounds, note = _indexed_bounds(args.displacement, count, "displacement")
    if note is not None:
        _build_parser().print_usage(sys.stderr)
        print(note, file=sys.stderr)
        return None
    return perturbation_bounds, displacement_bounds


def _survey_ready(
    args: argparse.Namespace, contents: list[bytes]
) -> tuple[list[document.PerturbationBound | None], list[document.DisplacementBound | None]] | None:
    """Validate survey declarations, printing misuse and giving up as None.

    Relations must name scans of the ordered intake, bounds must align
    with it with at most one declaration per scan.

    Args:
        args: The parsed arguments, carrying relations and declared bounds.
        contents: The raw export bytes in sorted intake order.

    Returns:
        The aligned bounds, or None after printing usage where any
        declaration names no scan or names one twice.
    """
    for relation in args.relate:
        if not 0 <= relation.first < len(contents) or not 0 <= relation.second < len(contents):
            _build_parser().print_usage(sys.stderr)
            print(f"survey: relation names no scan: {relation!r}", file=sys.stderr)
            return None
    return _survey_bounds(args, len(contents))


def _run_survey(args: argparse.Namespace) -> int:
    """Analyse a survey of explicitly named scans.

    The named scans are handled in sorted order so the same survey reads
    the same way regardless of argument or filesystem order. Names are
    opaque intake tokens: no scan relation is inferred from them. The
    real loader asserts the operator source for every scan. One bad
    scan among several refuses only that scan; a run-level failure stops
    the run instead.

    Args:
        args: The parsed arguments, carrying the named scan exports.

    Returns:
        The process exit code: zero on success, one when a file cannot
        be read or stops the run, two on a relation or bound naming no
        scan, or two bounds declared for one scan.
    """
    names = sorted(args.scans)
    contents: list[bytes] = []
    for name in names:
        content = _read_export(name)
        if content is None:
            return 1
        contents.append(content)
    ready = _survey_ready(args, contents)
    if ready is None:
        return 2
    perturbation_bounds, displacement_bounds = ready
    try:
        return _emit(
            reader.read_document(
                contents,
                args.relate,
                perturbation_bounds=perturbation_bounds,
                displacement_bounds=displacement_bounds,
                assertion_sources=[document.OPERATOR_SOURCE for _ in contents],
            )
        )
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
    scan.add_argument(
        "--perturbation",
        default=None,
        metavar="AMPLITUDE,ANCHOR,BOUNDEDNESS",
        type=_parse_scan_perturbation,
        help=(
            "Declare the field perturbation bound for the scan as amplitude, "
            "anchor and boundedness with anchor residual or payload and "
            "boundedness bounded or unbounded. The guard reads it; an "
            "unbounded draw withholds the guard."
        ),
    )
    scan.add_argument(
        "--displacement",
        default=None,
        metavar="AMPLITUDE,BOUNDEDNESS",
        type=_parse_scan_displacement,
        help=(
            "Declare the registration displacement bound for the scan as "
            "amplitude and boundedness with boundedness bounded or "
            "unbounded. It never substitutes for the field perturbation bound."
        ),
    )
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
    survey.add_argument(
        "--perturbation",
        action="append",
        default=[],
        metavar="POSITION,AMPLITUDE,ANCHOR,BOUNDEDNESS",
        type=_parse_survey_perturbation,
        help=(
            "Declare the field perturbation bound for one scan, over "
            "positions into the ordered intake from zero with amplitude, "
            "anchor and boundedness with anchor residual or payload and "
            "boundedness bounded or unbounded; repeatable. The guard reads "
            "it; an unbounded draw withholds the guard."
        ),
    )
    survey.add_argument(
        "--displacement",
        action="append",
        default=[],
        metavar="POSITION,AMPLITUDE,BOUNDEDNESS",
        type=_parse_survey_displacement,
        help=(
            "Declare the registration displacement bound for one scan, over "
            "positions into the ordered intake from zero with amplitude and "
            "boundedness with boundedness bounded or unbounded; repeatable. "
            "It never substitutes for the field perturbation bound."
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

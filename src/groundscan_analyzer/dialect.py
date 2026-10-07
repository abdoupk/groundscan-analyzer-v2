"""The file dialect: delimiter determination and the assumed numeric reading.

The delimiter is determined by the header: exactly one candidate character
splits it into registered column names. The decimal separator is determined
nowhere, so it is a named assumption the engine states rather than a guess
it hides: ``default-numeric-reading-v1`` assumes ``.`` on every supported
export, and the assumption is recorded on the result.

The numeral grammar is the computation's input language, applied after
separator normalisation: an optional sign, digits with an optional
fractional part in either arrangement, and an optional exponent. No
underscores, no hexadecimal, no spelled non-finites, no thousands separator.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Final

DECIMAL_SEPARATOR: Final[str] = "."
OTHER_SEPARATOR: Final[str] = ","
CONVENTION: Final[str] = "default-numeric-reading-v1"

DELIMITER_CANDIDATES: Final[tuple[str, ...]] = (",", ";", "\t", "|", ".")

_NUMERAL_PATTERN: Final[str] = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NUMERAL_RE: Final[re.Pattern[str]] = re.compile(f"^{_NUMERAL_PATTERN}$")


def candidate_delimiters(header_line: str, is_registered: Callable[[str], bool]) -> list[str]:
    """List the candidates that split the header into registered names.

    Args:
        header_line: The raw header line of the measuring block.
        is_registered: A predicate over a raw header cell.

    Returns:
        Every candidate character under which each cell is registered.
    """
    fitting = []
    for candidate in DELIMITER_CANDIDATES:
        cells = header_line.split(candidate)
        if all(is_registered(cell) for cell in cells):
            fitting.append(candidate)
    return fitting


def _canonical_zero(value: float) -> float:
    """Canonicalise negative zero to positive zero at parse.

    Args:
        value: The finite parsed value.

    Returns:
        The value, with either zero reading as positive zero.
    """
    if is_nonzero(value):
        return value
    return 0.0


def is_nonzero(value: float) -> bool:
    """Report whether a parsed value differs from zero, exactly.

    Parsed decimals carry no arithmetic, so an ordering comparison is
    exact here where an equality comparison would mislead a reader.

    Args:
        value: The parsed value to test.

    Returns:
        True for any value above or below zero.
    """
    return value > 0.0 or value < 0.0


def parse_numeral(token: str) -> float | None:
    """Parse one token under the assumed decimal separator.

    Args:
        token: The raw token with surrounding whitespace still attached.

    Returns:
        The binary64 value with negative zero canonicalised away, or None
        when the token is outside the numeral grammar or not finite.
    """
    text = token.strip()
    if NUMERAL_RE.match(text) is None:
        return None
    value = float(text)
    if not math.isfinite(value):
        return None
    return _canonical_zero(value)


def carries_other_separator(token: str) -> bool:
    """Report whether a token carries the non-assumed separator character.

    Args:
        token: The raw token as written in the file.

    Returns:
        True when the token contains a comma, which under the assumed
        dot reading marks a file written under the other separator.
    """
    return OTHER_SEPARATOR in token

"""The vocabulary lint's declared lists: mechanical bans and reviewed category.

The mechanical rule checks the shipped contract surface, its enumeration
values, and its limitation and error strings against :data:`BANNED_STEMS`
and :data:`BANNED_PHRASES`. Tokenisation splits on hyphens and
underscores, so a forbidden phrase re-spelled with a hyphen still fails.
The reviewed semantic category in :data:`SEMANTIC_STEMS` and
:data:`SEMANTIC_PHRASES` catches synonyms the word list misses.

The glossary is inside the overall lint for equality and avoidance checks,
while the excluded corpora stay outside precisely because they exist to
quote the forbidden vocabulary. An ``_Avoid_`` line is where the glossary
records that vocabulary as forbidden, so such a line is declaration
rather than use. Registry non-output markers are likewise declarations
of absence rather than claims.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from typing import Final

__all__ = [
    "BANNED_PHRASES",
    "BANNED_STEMS",
    "SEMANTIC_CATEGORY",
    "SEMANTIC_PHRASES",
    "SEMANTIC_STEMS",
    "STANDINGS",
    "Standing",
    "mechanical_hits",
    "semantic_hits",
    "tokens",
]

Standing = Literal["recorded", "swept", "unpinned", "unrecoverable"]

STANDINGS: Final[tuple[Standing, ...]] = (
    "recorded",
    "swept",
    "unpinned",
    "unrecoverable",
)

BANNED_STEMS: Final[tuple[str, ...]] = (
    "metal",
    "metallic",
    "tunnel",
    "tunnels",
    "cavity",
    "cavities",
    "target",
    "targets",
    "object",
    "objects",
    "buried",
    "treasure",
    "gold",
    "silver",
    "iron",
    "pipe",
    "tomb",
    "validated",
    "validation",
    "verified",
    "corrected",
    "adjusted",
    "calibrated",
    "dereferenced",
    "compensated",
    "east",
    "north",
    "red",
    "green",
    "readiness",
    "confidence",
    "benchmark",
)

BANNED_PHRASES: Final[tuple[str, ...]] = (
    "x-axis",
    "y-axis",
    "support-score",
    "ground-truth",
    "ground truth",
    "training-data",
    "training data",
    "field-validated",
    "field validated",
)

SEMANTIC_CATEGORY: Final[str] = "material, object or ground-class claim, however worded"

SEMANTIC_STEMS: Final[tuple[str, ...]] = (
    "hollow",
    "confirmed",
    "dipolar",
    "lobe",
    "lobed",
)

SEMANTIC_PHRASES: Final[tuple[str, ...]] = (
    "linear-response",
    "linear response",
    "two-lobe",
    "two lobe",
    "ground-truthed",
    "ground truthed",
)

_TOKEN_SPLIT: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def tokens(text: str) -> tuple[str, ...]:
    """Split text into lowercase alphanumeric tokens.

    Args:
        text: The surface string to tokenise.

    Returns:
        The non-empty tokens in order.
    """
    return tuple(part for part in _TOKEN_SPLIT.split(text.lower()) if part)


def _phrase_hit(text: str, phrase: str) -> bool:
    """Check one banned phrase against normalised text.

    Args:
        text: The already lowercased surface string.
        phrase: The banned phrase in its canonical hyphenated form.

    Returns:
        True where the phrase occurs with hyphens, underscores or spaces.
    """
    canonical = re.sub(r"[-_\\s]+", " ", phrase.lower()).strip()
    normalised = re.sub(r"[-_\\s]+", " ", text.lower())
    return canonical in normalised


def _collect(text: str, stems: tuple[str, ...], phrases: tuple[str, ...]) -> tuple[str, ...]:
    """Collect stem and phrase hits in one surface string.

    Args:
        text: The surface string to check.
        stems: The token stems to match whole tokens against.
        phrases: The phrases to match with hyphen, underscore or space forms.

    Returns:
        The stems and phrases found, in first-seen order.
    """
    found: list[str] = []
    seen: set[str] = set()
    token_set = set(tokens(text))
    for stem in stems:
        if stem in token_set and stem not in seen:
            seen.add(stem)
            found.append(stem)
    lowered = text.lower()
    for phrase in phrases:
        if _phrase_hit(lowered, phrase) and phrase not in seen:
            seen.add(phrase)
            found.append(phrase)
    return tuple(found)


def mechanical_hits(text: str) -> tuple[str, ...]:
    """Collect mechanical-rule hits in one surface string.

    Args:
        text: The surface string to check.

    Returns:
        The banned stems and phrases found, in first-seen order.
    """
    return _collect(text, BANNED_STEMS, BANNED_PHRASES)


def semantic_hits(text: str) -> tuple[str, ...]:
    """Collect reviewed-category hits the word list misses.

    Args:
        text: The surface string to check.

    Returns:
        The semantic stems and phrases found, in first-seen order.
    """
    return _collect(text, SEMANTIC_STEMS, SEMANTIC_PHRASES)

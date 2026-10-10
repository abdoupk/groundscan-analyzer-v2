"""The field's encoding: one glyph per cell, every property traceable.

A glyph's *character* says which of five classes the coordinate is in, so
the field is legible with colour switched off. A glyph's *style* says where
the cell sits among its polarity's levels, which is a rank read from
`Hierarchy.levels_positive` or `levels_negative` rather than an
interpolation between measured values: a continuous ramp would invent
magnitudes the record does not carry, and the levels beside the field are
what the ramp is drawn from.

Selection is a style layer over whatever the cell already says. The
character is never swapped, so marking a detection cannot destroy the
polarity or the padding class of the cell underneath it.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from groundscan_tui.model import Cell, CellKind, Grid

GLYPHS: Final[Mapping[CellKind, str]] = MappingProxyType(
    {
        "positive": "▓",
        "negative": "░",
        "zero": "·",
        "padding": "~",
        "absent": " ",
    },
)

# Cyan against yellow is the one hue pair that survives both dichromacies, so
# polarity does not depend on a colour the reader may not distinguish. The two
# ends of the warm/cool axis are separately barred by the engine's declared
# vocabulary, which is an independent reason to reach for this pair.
POLARITY_STYLES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "positive": ("dim cyan", "cyan", "bright_cyan", "bold bright_cyan"),
        "negative": ("dim yellow", "yellow", "bright_yellow", "bold bright_yellow"),
    },
)

# A measured cell in neither polarity, a padded one, and an index the export
# never carried are three different statements and stay three different glyphs.
PLAIN_STYLES: Final[Mapping[str, str]] = MappingProxyType(
    {"zero": "dim", "padding": "dim magenta", "absent": ""},
)

SELECTION_STYLE: Final[str] = "reverse"

LEGEND: Final[tuple[tuple[str, str], ...]] = (
    (GLYPHS["positive"], "a cell in a positive detection"),
    (GLYPHS["negative"], "a cell in a negative detection"),
    (GLYPHS["zero"], "a measured cell outside both polarities"),
    (GLYPHS["padding"], "a padded cell, carrying no measurement"),
    (GLYPHS["absent"], "an index the export does not carry"),
)


def _ladder_style(ladder: Sequence[str], rank: int, levels: int) -> str:
    """Pick the rung for a cell's place among its polarity's levels.

    Returns:
        The style at that rung.
    """
    span = max(levels - 1, 1)
    return ladder[min(rank * len(ladder) // (span + 1), len(ladder) - 1)]


def style_for(cell: Cell) -> str:
    """Return the style carrying a cell's level rank.

    A cell the record does not rank falls back to its class's plain style
    rather than being given an invented rank.

    Args:
        cell: The coordinate to style.

    Returns:
        A rich style name.
    """
    ladder = POLARITY_STYLES.get(cell.kind)
    if ladder is None or cell.rank is None:
        return PLAIN_STYLES.get(cell.kind, "")
    return _ladder_style(ladder, cell.rank, cell.levels or 1)


def _styled(cell: Cell, selected: frozenset[tuple[int, int]]) -> str:
    """Layer the selection over a cell's own style.

    Returns:
        The cell's style, with the selection appended where it is selected.
    """
    if (cell.impulse, cell.scan_line) not in selected:
        return style_for(cell)
    return f"{style_for(cell)} {SELECTION_STYLE}".strip()


def field_text(grid: Grid, selected: frozenset[tuple[int, int]]) -> Text:
    """Draw the field, one glyph per index, in record order.

    Absent indices are drawn as their own glyph at their own position, so a
    gap is visible as a gap and never closed up into a false alignment.

    Args:
        grid: The field to draw.
        selected: The coordinates the selection marker is layered over.

    Returns:
        The field as styled text, one line per scan-line index.
    """
    text = Text(no_wrap=True)
    for scan_line in grid.scan_lines:
        for impulse in grid.impulses:
            cell = grid.at(impulse, scan_line)
            text.append(GLYPHS[cell.kind], _styled(cell, selected))
        text.append("\n")
    return text


def legend_text() -> Text:
    """Draw what each glyph means, so the field is readable alone.

    Each glyph is bracketed, because one of the five is a space and would
    otherwise be invisible in the legend while being the only thing that
    distinguishes an index the export never carried from a measured cell.

    Returns:
        The legend as styled text, one line per glyph.
    """
    text = Text(no_wrap=True)
    for glyph, meaning in LEGEND:
        text.append(f"[{glyph}] ", "bold")
        text.append(f"{meaning}\n")
    return text

"""The encoding: one glyph per cell, every property traceable to a field."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from groundscan_analyzer import document as document_module
from groundscan_analyzer import reader, vocabulary
from groundscan_tui.grid import (
    GLYPHS,
    LEGEND,
    PLAIN_STYLES,
    POLARITY_STYLES,
    SELECTION_STYLE,
    field_text,
    legend_text,
    style_for,
)
from groundscan_tui.model import Cell, build_grid

if TYPE_CHECKING:
    from groundscan_tui.model import Grid

ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"


def _grid() -> Grid:
    document = document_module.loads(
        (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8"),
    )
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRead)
    return build_grid(scan)


def _cell(kind: str, rank: int | None = 0, levels: int | None = 1) -> Cell:
    return Cell(impulse=1, scan_line=1, kind=kind, residual=1.0, rank=rank, levels=levels)  # type: ignore[arg-type]


def test_the_five_classes_have_five_distinct_glyphs() -> None:
    assert len(set(GLYPHS.values())) == 5
    assert set(GLYPHS) == {"positive", "negative", "zero", "padding", "absent"}


def test_padding_and_absent_are_distinguishable_in_glyph_and_style() -> None:
    assert GLYPHS["padding"] != GLYPHS["absent"]
    assert PLAIN_STYLES["padding"] != PLAIN_STYLES["absent"]


def test_shape_carries_polarity_so_the_field_survives_no_colour() -> None:
    assert GLYPHS["positive"] != GLYPHS["negative"]


def test_no_polarity_uses_a_colour_the_engine_declares_banned() -> None:
    for ladder in POLARITY_STYLES.values():
        for style in ladder:
            assert not vocabulary.mechanical_hits(style)


def test_a_cell_with_no_rank_falls_back_to_its_class_plain_style() -> None:
    for kind in ("zero", "padding", "absent"):
        assert style_for(_cell(kind)) == PLAIN_STYLES[kind]


def test_an_unranked_polarity_cell_does_not_get_an_invented_rank() -> None:
    assert not style_for(_cell("positive", rank=None))


def test_higher_rank_lands_on_a_later_rung() -> None:
    bottom = style_for(_cell("positive", rank=0, levels=4))
    middle = style_for(_cell("positive", rank=2, levels=4))
    top = style_for(_cell("positive", rank=3, levels=4))
    ladder = POLARITY_STYLES["positive"]
    assert ladder.index(bottom) < ladder.index(middle) <= ladder.index(top)


def test_a_single_level_field_still_renders() -> None:
    assert style_for(_cell("negative", rank=0, levels=1)) in POLARITY_STYLES["negative"]


def test_the_field_is_one_line_per_scan_line_and_one_glyph_per_index() -> None:
    grid = _grid()
    lines = field_text(grid, frozenset()).plain.splitlines()
    assert len(lines) == len(grid.scan_lines)
    assert all(len(line) == len(grid.impulses) for line in lines)


def test_selection_changes_style_and_never_the_character() -> None:
    grid = _grid()
    target = next(iter(grid.cells))
    plain = field_text(grid, frozenset()).plain
    marked = field_text(grid, frozenset({target})).plain
    assert plain == marked
    assert SELECTION_STYLE in " ".join(
        str(s.style) for s in field_text(grid, frozenset({target})).spans
    )


def test_an_absent_index_draws_its_own_glyph_at_its_own_place() -> None:
    grid = _grid()
    text = field_text(grid, frozenset()).plain
    assert len(text.splitlines()[0]) == len(grid.impulses)


def test_the_legend_names_every_glyph_the_field_can_draw() -> None:
    assert {glyph for glyph, _ in LEGEND} == set(GLYPHS.values())
    assert len(legend_text().plain.splitlines()) == len(LEGEND)


def test_the_legend_explains_each_class_without_a_verdict() -> None:
    lowered = legend_text().plain.lower()
    for word in ("readiness", "fitness", "confidence", "target"):
        assert word not in lowered


def test_two_renders_are_byte_identical() -> None:
    grid = _grid()
    assert field_text(grid, frozenset()).plain == field_text(grid, frozenset()).plain


def test_a_refused_document_never_reaches_the_field() -> None:
    contents = (ENGINE_DATA / "acceptance_refused_export.txt").read_bytes()
    document = reader.read_document([contents])
    scan = document.scans[0]
    assert isinstance(scan, document_module.ScanRefused)

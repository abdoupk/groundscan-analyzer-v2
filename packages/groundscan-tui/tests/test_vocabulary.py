"""This package lints its own shipped vocabulary, inheriting the engine's lists.

Nothing lints `packages/`. The engine's own lint walks `src/`, and the
other sibling package has shipped unlinted labels since it landed. A field
viewer is the surface most likely to reach for a forbidden word -- the
display is a picture of somewhere, and pictures invite naming -- so the
declared lists are imported rather than restated, and applied here.
"""

from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from groundscan_analyzer import vocabulary

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src" / "groundscan_tui"
ENGINE_SRC = Path(__file__).resolve().parents[3] / "src" / "groundscan_analyzer"


def _surfaces() -> list[Path]:
    return sorted(PACKAGE_SRC.rglob("*.py"))


def test_the_surface_is_not_empty() -> None:
    assert _surfaces()


@pytest.mark.parametrize("path", _surfaces(), ids=lambda p: p.name)
def test_no_surface_ships_a_banned_word(path: Path) -> None:
    assert vocabulary.mechanical_hits(path.read_text(encoding="utf-8")) == ()


@pytest.mark.parametrize("path", _surfaces(), ids=lambda p: p.name)
def test_no_surface_ships_a_semantic_claim(path: Path) -> None:
    assert vocabulary.semantic_hits(path.read_text(encoding="utf-8")) == ()


def test_the_engine_lists_are_inherited_not_restated() -> None:
    own = PACKAGE_SRC / "grid.py"
    assert "BANNED_STEMS" not in own.read_text(encoding="utf-8")
    assert vocabulary.BANNED_STEMS


def test_the_lint_would_catch_a_forbidden_word() -> None:
    """A lint that cannot fail is not a gate."""
    assert vocabulary.mechanical_hits("a buried metal target")
    assert vocabulary.semantic_hits("a confirmed hollow lobe")


def test_the_import_direction_holds() -> None:
    for path in sorted(ENGINE_SRC.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "groundscan_tui" not in text
        assert "groundscan-tui" not in text
    assert "groundscan_analyzer" in (PACKAGE_SRC / "model.py").read_text(encoding="utf-8")


def test_the_engine_dependencies_are_untouched_by_this_package() -> None:
    root = Path(__file__).resolve().parents[3] / "pyproject.toml"
    declared = tomllib.loads(root.read_text(encoding="utf-8"))["project"]["dependencies"]
    assert declared == ["numpy>=2.5.3", "pydantic>=2.13.5", "scipy>=1.18.1"]
    assert not {"textual", "rich", "jinja2"} & set(declared)

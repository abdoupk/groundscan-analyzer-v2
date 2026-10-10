"""Shared helpers for the test suite.

The projection returns a document view holding many scans; most of these
tests are about one scan at a time, so unwrapping the first is written once
here rather than in every file.

- `document_view` projects a document the way the application does.
- `first_scan` / `first_refusal` unwrap the scan at intake position zero.
- `plain` reads a static's rendered text without its render union type.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from groundscan_tui.model import RefusalView, ScanView, build_view

if TYPE_CHECKING:
    from textual.content import Content
    from textual.widgets import Static

    from groundscan_analyzer import document as document_module
    from groundscan_tui.model import DocumentView

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_DATA = REPO_ROOT / "tests" / "data"


def document_view(doc: document_module.Document) -> DocumentView:
    return build_view(doc)


def first_scan(doc: document_module.Document) -> ScanView:
    view = build_view(doc)
    scan = view.scans[0]
    assert isinstance(scan, ScanView)
    return scan


def first_refusal(doc: document_module.Document) -> RefusalView:
    view = build_view(doc)
    scan = view.scans[0]
    assert isinstance(scan, RefusalView)
    return scan


def plain(widget: Static) -> str:
    return cast("Content", widget.render()).plain

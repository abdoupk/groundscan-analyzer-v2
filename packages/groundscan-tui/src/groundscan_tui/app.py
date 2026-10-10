"""The two applications: the field browser and the refusal view.

They are separate because they answer different questions. The browser
shows what the record states about an export it read. The refusal view
shows why the input contract declined to produce a result at all, which is
not a result state and not a failure to be summarised into an exit code.

Keys are context-sensitive by tab: whichever pane holds focus owns the
arrows. The field is often larger than the terminal -- the largest vendor
export is thirty impulses by eighty scan lines -- so the field pane sits in
a scroll view that takes focus when the reader asks for it and gives it up
when they tab away.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from textual.app import App
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Static

from groundscan_tui.grid import legend_text
from groundscan_tui.panes import ABSENT, DetailPane, DetectionPane, FieldPane, header_text

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.events import Key
    from textual.widgets import ListView

    from groundscan_tui.model import RefusalView, ScanView

BINDINGS: list[Binding | tuple[str, str] | tuple[str, str, str]] = [
    ("q", "quit", "Quit"),
    ("tab", "focus_next", "Next pane"),
    ("shift+tab", "focus_previous", "Previous pane"),
]


class FieldBrowser(App[None]):
    """One export as a field, a list of its detections, and their limits."""

    CSS = """
    Screen { layout: vertical; }
    Provenance { height: auto; max-height: 45%; overflow-y: auto; }
    Middle { height: 1fr; }
    DetectionPane { width: 40; border: round $primary; }
    Detail { height: 14; border: round $secondary; overflow-y: auto; }
    FieldPane { padding: 0 1; }
    """

    BINDINGS = BINDINGS

    def __init__(self, view: ScanView) -> None:
        """Open on one scan view.

        Args:
            view: The scan to browse.
        """
        super().__init__()
        self.view = view

    @override
    def compose(self) -> ComposeResult:
        """Lay out the provenance, the spine, the field and the detail.

        Yields:
            The header, the detection list, the field, and the detail pane.
        """
        yield Static(header_text(self.view), classes="Provenance")
        with Horizontal(classes="Middle"):
            yield DetectionPane(self.view.detections)
            with VerticalScroll():
                yield FieldPane()
                yield Static(legend_text())
        yield DetailPane(classes="Detail")
        yield Footer()

    def on_mount(self) -> None:
        """Select the first detection and draw every pane around it."""
        self.query_one(DetectionPane).index = 0
        self._draw()

    def _draw(self) -> None:
        """Redraw the field and the detail around the highlighted detection."""
        row = self.query_one(DetectionPane).current_row
        selected = frozenset() if row is None else row.keys
        self.query_one(FieldPane).show(self.view.grid, selected)
        self.query_one(DetailPane).show(row)

    def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
        """Redraw when the reader steps to another detection.

        Args:
            _event: The new highlight; the pane already holds the state.
        """
        self._draw()

    def on_key(self, event: Key) -> None:
        """Quit on `q`, so a reader never has to reach for a chord.

        Args:
            event: The key pressed.
        """
        if event.key == "q":
            self.exit()


class RefusalApp(App[None]):
    """The input contract's refusal, as the whole screen."""

    CSS = """
    Screen { align: center middle; }
    Refusal { width: 80%; height: auto; max-height: 80%; border: round $error; padding: 1 2; }
    """

    BINDINGS = BINDINGS

    def __init__(self, refusal: RefusalView) -> None:
        """Open on one refusal.

        Args:
            refusal: The refusal to show.
        """
        super().__init__()
        self.refusal = refusal

    @override
    def compose(self) -> ComposeResult:
        """Lay out the refusal and the rows behind it.

        Yields:
            The refusal pane and the footer.
        """
        yield Static(refusal_text(self.refusal), classes="Refusal")
        yield Footer()

    def on_key(self, event: Key) -> None:
        """Quit on `q`.

        Args:
            event: The key pressed.
        """
        if event.key == "q":
            self.exit()


def refusal_text(refusal: RefusalView) -> str:
    """Draw a refusal with its reason, its detail and its rows.

    Args:
        refusal: The refusal to draw.

    Returns:
        The refusal's text.
    """
    lines = [
        "This export was refused by the input contract.",
        "",
        f"reason: {refusal.reason}",
        "",
        refusal.detail,
        "",
    ]
    if refusal.rows:
        lines.append("rows:")
        lines.extend(f"  {row}" for row in refusal.rows)
    else:
        lines.append(f"no offending row was recorded; {ABSENT}")
    return "\n".join(lines)

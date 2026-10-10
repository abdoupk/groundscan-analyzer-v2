"""The campaign application: choose an intake, then browse it.

Two screens under one application. The intake screen appears only where a
folder was named, and it exists because the engine never discovers files:
`survey *` stays literal and unnamed neighbours are never read, so the list
of files is the viewer's discovery and an operator confirms it before
anything runs. What survives this screen is frozen at that moment, because every
relation and every bound the engine accepts is indexed by a position in it.

The browser handles one document with one layout whether it holds one scan
or a folder's worth. The scan pane appears only where there is more than one
scan to choose between, which leaves the single-export case exactly as it
was. A refused scan takes its place in the same selection rather than
launching a second application, because a refusal is the state of one scan.

The survey section appears only when the record carries frames, contradictions
or recurrences. A folder of unrelated exports has none, and the view does not
manufacture a heading to fill the space.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override

from textual.app import App
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, SelectionList, Static

from groundscan_tui.export import (
    ExportError,
    campaign_stem,
    write_html,
    write_json,
)
from groundscan_tui.grid import legend_text
from groundscan_tui.model import RefusalView, build_view
from groundscan_tui.panes import (
    DetailPane,
    DetectionPane,
    FieldPane,
    RefusalPane,
    ScanPane,
    header_text,
    refusal_text,
    survey_text,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.events import Key
    from textual.widgets import ListView

    from groundscan_analyzer import document as document_module
    from groundscan_tui.engine import EngineSession
    from groundscan_tui.model import DocumentView, ScanView

BINDINGS: list[Binding | tuple[str, str] | tuple[str, str, str]] = [
    ("q", "quit", "Quit"),
    ("tab", "focus_next", "Next pane"),
    ("shift+tab", "focus_previous", "Previous pane"),
    ("h", "export_html", "Write the acceptance record"),
    ("j", "export_json", "Write the document"),
]

BROWSE_CSS = """
    Provenance { height: auto; max-height: 40%; overflow-y: auto; }
    Middle { height: 1fr; }
    ScanPane { width: 34; border: round $primary; }
    DetectionPane { width: 38; border: round $primary; }
    RefusalPane { width: 2fr; border: round $error; padding: 1 2; }
    Detail { height: 14; border: round $secondary; overflow-y: auto; }
    Survey { height: auto; max-height: 30%; overflow-y: auto; }
    FieldPane { padding: 0 1; }
"""

INTAKE_CSS = """
    Intake { height: auto; max-height: 80%; border: round $primary; padding: 1 2; }
    Note { height: auto; }
"""


class CampaignBrowser(Screen[None]):
    """One document's scans, their detections, and the evidence across them.

    Attributes:
        view: The document this browser was opened on.
        names: The intake names, indexed by position, where the caller knows
            them. The record deliberately carries no filename, so a name here
            is the viewer's own knowledge and never the engine's.
        args: The command line, kept so the export actions know where to write.
    """

    DEFAULT_CSS = BROWSE_CSS

    def __init__(
        self,
        document: document_module.Document,
        view: DocumentView,
        names: Sequence[str] = (),
        args: argparse.Namespace | None = None,
    ) -> None:
        """Open on one document.

        Args:
            document: The record itself, kept so an export can write it
                without being projected again.
            view: The document to browse.
            names: The intake names by position, where the caller knows them.
            args: The command line, for the export actions.
        """
        super().__init__()
        self.document = document
        self.view = view
        self.names = tuple(names)
        self.args = args

    @property
    def scan(self) -> ScanView | RefusalView:
        """The scan currently selected, which is the first until stepped to."""
        if not self._many():
            return self.view.scans[0]
        index = self.query_one(ScanPane).index
        if index is None:
            return self.view.scans[0]
        return self.view.scans[index]

    def _many(self) -> bool:
        return len(self.view.scans) > 1

    @override
    def compose(self) -> ComposeResult:
        """Lay out the provenance, the panes, the detail and the survey.

        Yields:
            The provenance, the optional scan pane, the detections or the
            refusal, the field, the detail, the optional survey, and the footer.
        """
        yield Static(header_text(self.view, self.view.scans[0]), id="Provenance")
        with Horizontal(classes="Middle"):
            if self._many():
                yield ScanPane(_scan_labels(self.view, self.names))
            yield DetectionPane()
            yield RefusalPane()
            with VerticalScroll():
                yield FieldPane()
                yield Static(legend_text())
        yield DetailPane(classes="Detail")
        if self.view.is_survey:
            yield Static(survey_text(self.view.survey), classes="Survey")
        yield Footer()

    async def on_mount(self) -> None:
        """Select the first scan and draw every pane around it."""
        if self._many():
            self.query_one(ScanPane).index = 0
        await self._draw()

    async def _draw(self) -> None:
        """Redraw every pane around the selected scan and detection."""
        scan = self.scan
        refusal = self.query_one(RefusalPane)
        detections = self.query_one(DetectionPane)
        detail = self.query_one(DetailPane)
        field = self.query_one(FieldPane)
        self.query_one("#Provenance", Static).update(header_text(self.view, scan))
        if isinstance(scan, RefusalView):
            refusal.show(scan)
            refusal.display = True
            detections.display = False
            field.display = False
            detail.show(None)
            return
        refusal.display = False
        detections.display = True
        field.display = True
        await detections.load(scan.detections)
        row = detections.current_row
        field.show(scan.grid, row.keys if row is not None else frozenset())
        detail.show(row)

    async def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
        """Redraw when the reader steps to a detection or to a scan.

        Args:
            _event: The new highlight; the pane already holds the state.
        """
        await self._draw()

    @property
    def _out_dir(self) -> Path | None:
        """Where an export would go, or None where no intake is known."""
        if not self.names:
            return None
        return Path(self.names[0]).parent

    def _export(self, format_name: str) -> None:
        """Write one record, or say plainly why it could not be written.

        Args:
            format_name: `html` for the acceptance record, `json` for the
                document itself.
        """
        directory = self._out_dir
        force = bool(getattr(self.args, "force", False))
        declared = getattr(self.args, "out", None)
        if directory is None:
            self.notify("No intake is known, so there is nowhere to write.")
            return
        chosen = Path(declared) if declared is not None else directory
        writer = write_html if format_name == "html" else write_json
        try:
            written = writer(
                self.document,
                chosen,
                campaign_stem([Path(name) for name in self.names]),
                force=force,
            )
        except (ExportError, OSError) as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"wrote {written}", severity="information")

    def action_export_html(self) -> None:
        """Write the field acceptance record for this document."""
        self._export("html")

    def action_export_json(self) -> None:
        """Write the document itself, as the engine emitted it."""
        self._export("json")


class IntakeScreen(Screen[None]):
    """The folder's files, ticked by default, for the operator to confirm.

    The engine will be handed exactly what survives this screen, in exactly
    the order shown, because the position of every bound is an index into it.

    Attributes:
        paths: The enumerated intake, in the order the engine will index it.
        session: The engine, read through on confirmation.
        args: The command line, for the survey bound and where to write.
        frozen: The intake, once the operator has agreed what to read.
    """

    DEFAULT_CSS = INTAKE_CSS

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("r", "confirm", "Read the selected"),
        ("q", "cancel", "Quit without reading"),
    ]

    def __init__(
        self,
        paths: Sequence[Path],
        session: EngineSession,
        args: argparse.Namespace,
    ) -> None:
        """Open on one folder's files.

        Args:
            paths: The enumerated intake, name-sorted.
            session: The engine session to read through.
            args: The command line, for the bound and where to write.
        """
        super().__init__()
        self.paths = tuple(paths)
        self.session = session
        self.args = args
        self.frozen: tuple[Path, ...] = ()

    @override
    def compose(self) -> ComposeResult:
        """Lay out the note, the file list and the footer.

        Yields:
            The note explaining the intake, the ticked file list, the footer.
        """
        yield Static(
            f"{len(self.paths)} .csv files, in the order the engine will index them."
            " Every bound and every relation is a position in this list.",
            classes="Note",
        )
        yield SelectionList(
            *[
                (f"{position:>3}  {path.name}", position)
                for position, path in enumerate(self.paths)
            ],
            classes="Intake",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Tick every file, because an unticked list is an empty campaign."""
        picker = self.query_one(SelectionList)
        picker.select_all()

    def action_cancel(self) -> None:
        """Leave without reading anything."""
        self.app.exit()

    async def action_confirm(self) -> None:
        """Freeze the ticked list and read it as one campaign."""
        chosen = self.query_one(SelectionList).selected
        self.frozen = tuple(path for position, path in enumerate(self.paths) if position in chosen)
        if not self.frozen:
            self.notify("No files are ticked; there is nothing to read.")
            return
        document = self.session.read_folder(self.frozen, self.args.perturbation)
        await self.app.pop_screen()
        await self.app.push_screen(
            CampaignBrowser(
                document,
                build_view(document),
                tuple(str(path) for path in self.frozen),
                self.args,
            ),
        )


class CampaignApp(App[None]):
    """The application: an intake screen where a folder was named, then a browser."""

    CSS = ""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = list(BINDINGS)

    def __init__(
        self,
        browser: CampaignBrowser | None = None,
        intake_screen: IntakeScreen | None = None,
    ) -> None:
        """Open over a document, or over an intake to choose one.

        Args:
            browser: The browser to open directly, for a single export.
            intake_screen: The intake screen to open first, for a folder.
        """
        super().__init__()
        self._browser = browser
        self._intake = intake_screen

    @classmethod
    def for_intake(
        cls, session: EngineSession, paths: Sequence[Path], args: argparse.Namespace
    ) -> CampaignApp:
        """Open on the intake screen, to choose what to read.

        Args:
            session: The engine session to read through.
            paths: The enumerated intake, name-sorted.
            args: The parsed command line.

        Returns:
            The application, opening on the intake screen.
        """
        return cls(intake_screen=IntakeScreen(paths, session, args))

    async def on_mount(self) -> None:
        """Show the intake screen for a folder, or the browser for one export.

        The screen is pushed asynchronously because Textual mounts it off the
        current frame, so the await is what waits for it to exist.
        """
        if self._intake is not None:
            await self.push_screen(self._intake)
        elif self._browser is not None:
            await self.push_screen(self._browser)

    def on_key(self, event: Key) -> None:
        """Quit on `q` once there is something to quit away from.

        The intake screen binds `q` itself so it can say it is quitting
        without reading, which is a different thing from closing a browser.

        Args:
            event: The key pressed.
        """
        if event.key == "q" and isinstance(self.screen, CampaignBrowser):
            self.exit()


def _scan_labels(view: DocumentView, names: Sequence[str]) -> tuple[tuple[int, str], ...]:
    """Name each scan for the scan pane.

    The record carries no filename, so where the viewer knows the intake it
    supplies the name, and where it does not the payload hash stands in.

    Returns:
        One label per scan, in intake order.
    """
    labels: list[tuple[int, str]] = []
    for scan in view.scans:
        name = names[scan.position] if scan.position < len(names) else ""
        if isinstance(scan, RefusalView):
            labels.append((scan.position, f"{name or 'scan'} refused ({scan.reason})"))
        else:
            labels.append((scan.position, f"{scan.position}  {name or scan.payload_hash[:12]}"))
    return tuple(labels)


__all__ = [
    "BINDINGS",
    "CampaignApp",
    "CampaignBrowser",
    "IntakeScreen",
    "build_view",
    "refusal_text",
]

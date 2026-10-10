"""The panes: what is on screen, and the text each one carries.

Three panes and a header. The detection list is the navigation spine and
carries the order the record chose; the field shows where a detection sits;
the detail panel carries every figure the record states about it beside
every limitation and withheld reason that qualifies it. The header carries
the scan's provenance and every result state, so a doubt is never filed
away from the headline it qualifies.

Nothing here measures. Each function reads a projection or a fold over a
listed set, and the set is on the same screen as the figure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Label, ListItem, ListView, Static

from groundscan_tui.grid import field_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from groundscan_analyzer import document as document_module
    from groundscan_tui.model import DetectionRow, Grid, ScanView

ABSENT: str = "not carried"


def _figure(value: float | None, reason: str | None, *, noun: str) -> str:
    """State a figure, or the reason the record withheld it.

    Args:
        value: The figure where the record emits one.
        reason: The closed reason where it withholds one.
        noun: What is being stated, used where neither is present.

    Returns:
        The figure, the withheld reason, or a plain statement of absence.
    """
    if value is not None:
        return f"{value:g}"
    return f"withheld: {reason}" if reason else f"{noun} {ABSENT}"


def _scan_local(position: document_module.ScanLocalPosition) -> str:
    """State a scan-local position with each axis's own provenance.

    Returns:
        Both axes with their indices and provenance, and the frame.
    """
    return (
        f"{position.along_line.name} index {position.along_line.index}"
        f" ({position.along_line.provenance});"
        f" {position.across_lines.name} index {position.across_lines.index}"
        f" ({position.across_lines.provenance});"
        f" frame {position.frame}, origin {position.origin_limitation}"
    )


def _field_axis(axis: document_module.FieldAxis) -> str:
    """State a derived axis with both of its scale's inputs named.

    Returns:
        The coordinate, and the span and count it was divided into.
    """
    return (
        f"{axis.name} {axis.coordinate:g}"
        f" (span {axis.scale.span:g} {axis.scale.span_provenance}"
        f" / count {axis.scale.count} {axis.scale.count_provenance})"
    )


def _field_position(position: document_module.FieldPosition | None) -> str:
    """State a field position, or why the record withholds one.

    Returns:
        Both derived axes, or a plain statement of absence.
    """
    if position is None:
        return ABSENT
    return (
        f"{_field_axis(position.along_line)};"
        f" {_field_axis(position.across_lines)};"
        f" origin {position.origin_limitation}"
    )


def _shared_position(row: DetectionRow) -> str:
    """State a shared-frame position, or why the record withdraws one.

    Returns:
        The frame and its homogeneity, or the reason it was withdrawn.
    """
    position = row.detection.shared_frame_position
    if position is None:
        reason = row.detection.no_shared_position_reason
        return f"withdrawn: {reason}" if reason else ABSENT
    return (
        f"frame {position.frame}, homogeneous {position.homogeneous},"
        f" origin {position.origin_limitation}"
    )


def _depth(row: DetectionRow) -> str:
    """State a depth interval as device-reported evidence, or its absence.

    Returns:
        The interval and its kind, or a plain statement of absence.
    """
    depth = row.detection.depth
    if depth is None:
        return ABSENT
    return f"{depth.minimum:g} to {depth.maximum:g} ({depth.kind})"


def _counts(row: DetectionRow) -> str:
    """State the two contact populations, each over its named cells.

    Returns:
        The cell count and both contact counts.
    """
    detection = row.detection
    return (
        f"{detection.cell_count} cells;"
        f" {len(detection.lattice_boundary_cells)} on the lattice boundary;"
        f" {len(detection.padding_adjacent_cells)} beside padding"
    )


def _tree(row: DetectionRow) -> str:
    """State a detection's place in the component hierarchy.

    Returns:
        Its depth, its parent, and its children.
    """
    children = ", ".join(str(number) for number in row.children) or "none"
    parent = "a root" if row.parent is None else f"{row.parent}"
    return f"depth {row.depth}; parent {parent}; children {children}"


def _limitations(row: DetectionRow) -> str:
    """State the limitations travelling with this claim.

    An empty tuple is a stated fact of no limitations, which is not the same
    as limitations having gone unrecorded.

    Returns:
        The limitations stated, or a plain statement that none were.
    """
    return ", ".join(row.detection.limitations) or "none stated"


def _heading(text: Text, title: str) -> None:
    """Open a section."""
    text.append(f"{title}\n", "bold")


def _line(text: Text, label: str, value: str) -> None:
    """Write one labelled figure."""
    text.append(f"  {label}: ", "dim")
    text.append(f"{value}\n")


def detail_text(row: DetectionRow | None) -> Text:
    """Draw one detection with every limit beside its figures.

    Args:
        row: The selected detection, or None where none is selected.

    Returns:
        The detail panel's text.
    """
    text = Text()
    if row is None:
        text.append("no detection selected\n")
        return text
    detection = row.detection
    _heading(text, f"Detection {detection.number} ({detection.identity})")
    _line(text, "polarity", detection.polarity)
    _line(text, "birth level", f"{detection.birth_level:g} (raw residual)")
    _line(text, "cells", _counts(row))
    _line(text, "solidity", f"{detection.solidity:g}")
    _line(text, "compactness", f"{detection.compactness:g}")
    _line(
        text,
        "field area",
        _figure(detection.field_area, detection.field_area_withheld, noun="field area"),
    )
    _line(text, "depth", _depth(row))
    _heading(text, "Position")
    _line(text, "scan-local", _scan_local(detection.scan_local_position))
    _line(
        text,
        "field",
        _field_position(detection.field_position)
        if detection.field_position is not None
        else _figure(None, detection.no_field_position_reason, noun="field position"),
    )
    _line(text, "shared frame", _shared_position(row))
    _heading(text, "Place in the hierarchy")
    _line(text, "component", _tree(row))
    _line(text, "limitations", _limitations(row))
    return text


def header_text(view: ScanView) -> Text:
    """Draw the scan's provenance, populations and every result state.

    Args:
        view: The scan the header describes.

    Returns:
        The header's text.
    """
    text = Text()
    _heading(text, "Scan record")
    for label, value in view.facts:
        _line(text, label, value)
    _heading(text, "Result states")
    for output in view.outputs:
        state = output.status if output.reason is None else f"{output.status} ({output.reason})"
        _line(text, output.name, state)
    return text


class FieldPane(Static):
    """The residual field, one glyph per index."""

    def show(self, grid: Grid, selected: frozenset[tuple[int, int]]) -> None:
        """Draw the field with the selection layered over it.

        Args:
            grid: The field to draw.
            selected: The coordinates the selection marker covers.
        """
        self.update(field_text(grid, selected))


class DetailPane(Static):
    """The selected detection, its figures and its limits together."""

    def show(self, row: DetectionRow | None) -> None:
        """Draw one detection, or the absence of a selection.

        Args:
            row: The selected detection, or None.
        """
        self.update(detail_text(row))


class DetectionPane(ListView):
    """Every detection, in the order the record numbered them.

    The list is never re-sorted: an ordering this view chose would read as
    a selection the engine never made, and the majority of detections are
    single cells, so any size-based order would promote the wrong ones.
    """

    def __init__(self, rows: Sequence[DetectionRow]) -> None:
        """Open the list on the rows the record carries.

        Args:
            rows: The detections, in record order.
        """
        super().__init__(*self._items(rows))
        self._rows = tuple(rows)

    @staticmethod
    def _items(rows: Sequence[DetectionRow]) -> tuple[ListItem, ...]:
        """Write one list line per detection, from named fields only.

        Returns:
            One item per detection, in the order the record numbered them.
        """
        return tuple(
            ListItem(
                Label(
                    f"{row.detection.number:>4}  {row.detection.polarity:<8}"
                    f" {row.detection.cell_count:>4} cells"
                    f"  birth {row.detection.birth_level:+g}",
                ),
                id=f"d-{row.detection.number}",
            )
            for row in rows
        )

    @property
    def current_row(self) -> DetectionRow | None:
        """The highlighted detection, or None where none is."""
        index = self.index
        if index is None or not 0 <= index < len(self._rows):
            return None
        return self._rows[index]

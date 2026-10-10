"""The presentation model: one engine Document shaped for viewing.

Every value here is a projection of a named record field, or a fold over a
listed set whose members the view also shows. Nothing in this module
measures, ranks, weighs, or judges: the record is the only source, and the
record does not assert that a field is fit to dig.

Two shapes come out of one Document. A :class:`ScanView` when the input
contract read the export, and a :class:`RefusalView` when it declined —
which is a different kind of statement with its own reason vocabulary, not a
result state and not an error to be swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from groundscan_analyzer import document as document_module

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

CellKind = Literal["positive", "negative", "zero", "padding", "absent"]


@dataclass(frozen=True, slots=True)
class Cell:
    """One lattice coordinate as the field draws it.

    Attributes:
        impulse: The device-reported impulse index.
        scan_line: The device-reported scan-line index.
        kind: Which of the five drawable classes this coordinate is in.
        residual: The residual the record carries, or None where padding.
        rank: This cell's place among its polarity's levels, or None where
            the record does not place it.
        levels: How many levels its polarity has, or None where it has none.
    """

    impulse: int
    scan_line: int
    kind: CellKind
    residual: float | None
    rank: int | None
    levels: int | None


@dataclass(frozen=True, slots=True)
class Grid:
    """The field as a lattice spanning the observed indices, gaps included.

    The spans run from the lowest observed index to the highest, so an index
    the export never carried occupies a position rather than being closed
    up. Field position depends on index alignment, and closing a gap would
    move every coordinate after it.

    Attributes:
        impulses: Every impulse index in span, ascending.
        scan_lines: Every scan-line index in span, ascending.
        cells: The observed coordinates only; absent indices are not keys.
    """

    impulses: tuple[int, ...]
    scan_lines: tuple[int, ...]
    cells: Mapping[tuple[int, int], Cell]

    def at(self, impulse: int, scan_line: int) -> Cell:
        """Return the cell at a coordinate, absent where the index is missing.

        Args:
            impulse: The impulse index to read.
            scan_line: The scan-line index to read.

        Returns:
            The observed cell, or an absent one standing for the gap.
        """
        found = self.cells.get((impulse, scan_line))
        return _absent(impulse, scan_line) if found is None else found


@dataclass(frozen=True, slots=True)
class DetectionRow:
    """One detection with its mask and its place in the component hierarchy.

    Attributes:
        detection: The record's own detection, carried whole.
        keys: Its cells as lattice coordinates.
        parent: Its parent's record number, or None where it is a root.
        children: Its children's record numbers, in record order.
        depth: Hops from a root of the tree.
    """

    detection: document_module.Detection
    keys: frozenset[tuple[int, int]]
    parent: int | None
    children: tuple[int, ...]
    depth: int


@dataclass(frozen=True, slots=True)
class OutputState:
    """One result state with the reason it holds, beside its name.

    Attributes:
        name: The output's own name.
        status: Its result state, or its own closed status vocabulary.
        reason: Why it holds where the record names why.
    """

    name: str
    status: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class ScanView:
    """Everything the field browser draws for a read export.

    Attributes:
        grid: The residual field as a lattice.
        detections: Every detection, in the record's own order.
        facts: Provenance and population facts, each a named field's value.
        outputs: Every result state, each beside the reason it holds.
    """

    grid: Grid
    detections: tuple[DetectionRow, ...]
    facts: tuple[tuple[str, str], ...]
    outputs: tuple[OutputState, ...]


@dataclass(frozen=True, slots=True)
class RefusalView:
    """What the input contract declined, and the evidence for it.

    Attributes:
        reason: The closed refusal reason.
        detail: The engine's own words for it.
        rows: The offending rows, each naming its line and its reason.
    """

    reason: str
    detail: str
    rows: tuple[str, ...]


def _absent(impulse: int, scan_line: int) -> Cell:
    return Cell(
        impulse=impulse,
        scan_line=scan_line,
        kind="absent",
        residual=None,
        rank=None,
        levels=None,
    )


def _span(indices: Sequence[int]) -> tuple[int, ...]:
    """Widen an index list to every integer it spans, gaps included.

    Returns:
        Every index from the lowest observed to the highest.
    """
    if not indices:
        return ()
    return tuple(range(min(indices), max(indices) + 1))


def _membership(
    hierarchy: document_module.Hierarchy,
) -> Mapping[tuple[int, int], CellKind]:
    """Map each cell the component hierarchy covers to its polarity.

    Returns:
        Each covered coordinate, mapped to the polarity covering it.
    """
    table: dict[tuple[int, int], CellKind] = {}
    for detection in hierarchy.detections:
        for cell in detection.cells:
            table[cell.impulse, cell.scan_line] = detection.polarity
    return MappingProxyType(table)


def _ranked(
    residual: float | None,
    table: Mapping[float, int] | None,
) -> tuple[int | None, int | None]:
    """Place a residual among the levels of its polarity.

    Returns:
        The rank and the level count, or None and None where there is no
        polarity to place the residual among.
    """
    if residual is None or table is None:
        return None, None
    return table.get(residual), len(table)


def _cell_at(
    doc_cell: document_module.Cell,
    membership: Mapping[tuple[int, int], CellKind],
    tables: Mapping[str, Mapping[float, int]],
) -> Cell:
    """Classify one observed coordinate.

    Returns:
        The cell, its class, and its rank where the record places it.
    """
    key = (doc_cell.impulse, doc_cell.scan_line)
    polarity = membership.get(key)
    # The component hierarchy is built over every cell whose residual is
    # non-zero, so a measured cell in neither polarity has residual zero by
    # the record's own construction and is drawn as such.
    kind: CellKind = "padding" if doc_cell.residual is None else "zero"
    if polarity is not None:
        kind = polarity
    rank, levels = _ranked(doc_cell.residual, tables.get(polarity) if polarity else None)
    return Cell(
        impulse=doc_cell.impulse,
        scan_line=doc_cell.scan_line,
        kind=kind,
        residual=doc_cell.residual,
        rank=rank,
        levels=levels,
    )


def build_grid(scan: document_module.ScanRead) -> Grid:
    """Project one read export into the lattice the field draws.

    Args:
        scan: The read scan record.

    Returns:
        The field, spanning the observed indices with gaps preserved.
    """
    hierarchy = scan.hierarchy
    tables: dict[str, Mapping[float, int]] = {
        "positive": MappingProxyType(
            dict(zip(hierarchy.levels_positive, range(len(hierarchy.levels_positive)), strict=True))
        ),
        "negative": MappingProxyType(
            dict(zip(hierarchy.levels_negative, range(len(hierarchy.levels_negative)), strict=True))
        ),
    }
    membership = _membership(hierarchy)
    cells = {
        (doc_cell.impulse, doc_cell.scan_line): _cell_at(doc_cell, membership, tables)
        for doc_cell in scan.cells
    }
    return Grid(
        impulses=_span(scan.lattice.impulses),
        scan_lines=_span(scan.lattice.scan_lines),
        cells=MappingProxyType(cells),
    )


def _depth(parents: Sequence[int | None], index: int) -> int:
    """Count hops from a root, whichever order the parents are numbered in.

    Returns:
        The detection's depth in the component hierarchy.
    """
    parent = parents[index]
    return 0 if parent is None else _depth(parents, parent) + 1


def _numbers(hierarchy: document_module.Hierarchy) -> Mapping[int, int]:
    """Map a detection's position in the list to the number it carries.

    Returns:
        Each list position, mapped to that detection's own number.
    """
    return MappingProxyType(
        dict(
            zip(
                range(len(hierarchy.detections)),
                (d.number for d in hierarchy.detections),
                strict=True,
            )
        ),
    )


def build_detections(hierarchy: document_module.Hierarchy) -> tuple[DetectionRow, ...]:
    """Project every detection with its mask and its place in the tree.

    The order is the record's own: numbering is presentation in lattice
    order, and reordering the list would be a rank this view has no warrant
    for.

    Args:
        hierarchy: The record's component hierarchy.

    Returns:
        One row per detection, in record order.
    """
    numbers = _numbers(hierarchy)
    children: dict[int, list[int]] = {}
    for index, parent in enumerate(hierarchy.parents):
        if parent is not None:
            children.setdefault(parent, []).append(index)
    rows = []
    for index, detection in enumerate(hierarchy.detections):
        parent = hierarchy.parents[index]
        rows.append(
            DetectionRow(
                detection=detection,
                keys=frozenset((c.impulse, c.scan_line) for c in detection.cells),
                parent=None if parent is None else numbers[parent],
                children=tuple(numbers[c] for c in children.get(index, ())),
                depth=_depth(hierarchy.parents, index),
            ),
        )
    return tuple(rows)


def _index_span(indices: Sequence[int]) -> str:
    """State an index list as a span and its observed count.

    Returns:
        The span written out, or a plain statement that none was observed.
    """
    if not indices:
        return "none observed"
    return f"{min(indices)}-{max(indices)} ({len(indices)} observed)"


def _declared(value: float | None) -> str:
    """State a declared extent, or that the operator declared nothing.

    Returns:
        The declared figure, or the fact that nothing was declared.
    """
    return "not declared" if value is None else f"{value:g}"


def _facts(
    doc: document_module.Document, scan: document_module.ScanRead
) -> tuple[tuple[str, str], ...]:
    """Collect the provenance and population facts the header shows.

    Every entry is one named field's own value, so a reader can find the
    same figure in the record the engine emits.

    Returns:
        Each fact as a label and the value of the field behind it.
    """
    return (
        ("contract version", str(doc.contract_version)),
        ("registry version", str(doc.registry_version)),
        ("quantity registry version", str(doc.quantity_registry_version)),
        ("numeric reading", doc.convention),
        ("payload hash", scan.payload_hash),
        ("impulse indices", _index_span(scan.lattice.impulses)),
        ("scan-line indices", _index_span(scan.lattice.scan_lines)),
        ("measured cells", str(scan.hierarchy.measured_cells)),
        ("cells in the hierarchy", str(scan.hierarchy.cells_in_hierarchy)),
        ("declared field length", _declared(scan.extent.field_length)),
        ("declared field width", _declared(scan.extent.field_width)),
        ("background convention", scan.background_model.convention),
        ("background windows", ",".join(str(w) for w in scan.background_model.windows)),
        ("background combination", scan.background_model.combination),
    )


def _outputs(scan: document_module.ScanRead) -> tuple[OutputState, ...]:
    """Collect every result state, each beside the reason it holds.

    A state whose reason the record leaves empty stays empty: "no reason
    recorded" and "no reason needed" are different claims.

    Returns:
        One entry per output, with its status and its reason.
    """
    return (
        OutputState("robust scale", scan.robust_scale.status, None),
        OutputState(
            "scale-normalised view",
            scan.scale_normalised_view.status,
            scan.scale_normalised_view.reason,
        ),
        OutputState("mask invariance", scan.mask_invariance.status, scan.mask_invariance.reason),
        OutputState("registration", scan.registration.status, scan.registration.reason),
    )


def build_view(doc: document_module.Document) -> ScanView | RefusalView:
    """Project one Document into whichever shape it turned out to be.

    Args:
        doc: The document the engine emitted for one export.

    Returns:
        A ScanView where the contract read the export, or a RefusalView
        where it declined.

    Raises:
        ValueError: Where one export produced other than one scan record.
    """
    if len(doc.scans) != 1:
        message = f"one export yields one scan record, not {len(doc.scans)}"
        raise ValueError(message)
    scan = doc.scans[0]
    if isinstance(scan, document_module.ScanRefused):
        rows = tuple(f"line {issue.line}: {issue.reason}" for issue in scan.rows)
        return RefusalView(reason=scan.reason, detail=scan.detail, rows=rows)
    return ScanView(
        grid=build_grid(scan),
        detections=build_detections(scan.hierarchy),
        facts=_facts(doc, scan),
        outputs=_outputs(scan),
    )

"""Independent geometric reference for **solidity** (S02 oracle).

Solidity is defined here from physical geometry alone:

```
A_object = area of the union of the occupied grid cells   (= N_cells * dx * dy)
A_hull   = area of the convex hull of that same union
solidity = A_object / A_hull          dimensionless, in (0, 1]
```

## Why this module exists at all

``golden = regression reference``, and the vendor OKM files are *behavioural
fixtures with vendor annotations* -- neither is scientific ground truth. The
question "is production's solidity right?" therefore cannot be answered by
comparing production against production, nor against a golden, nor against a
vendor annotation. It can only be answered by building the quantity from its
definition and checking the implementation against that.

So this module is written **from the definition, with no shared code**:

* it never calls ``core.shape._shape_metrics``, ``core.shape._convex_hull_solidity``
  or ``diagnostics.shadow.exact_solidity`` -- all three are implementations whose
  correctness is under evaluation;
* it never uses ``scipy.spatial.ConvexHull``. The hull is built here by Andrew's
  monotone chain, and the occupied area by tracing the union's own directed
  boundary edges and applying the shoelace formula. Two unrelated algorithms
  that would have to fail in unrelated ways to agree on a wrong number;
* it carries a **second, independent** construction of the same quantities
  (:func:`occupied_area_by_runs`, the maximal-horizontal-run rectangle
  decomposition) and a test asserts the two constructions agree, so a bug in one
  cannot hide inside the other.

## Exactness

Because every cell is a translate of the same rectangle, the pitch cancels: the
solidity of a cell set depends only on the *integer* cell pattern, not on the
pitch, the origin, or the linear unit. The definitive value is therefore
computed in **exact integer/rational arithmetic** (:func:`exact_solidity`), which
has no floating-point error at all. The physical-coordinate entry point
(:func:`physical_reference`) works in metres-as-given and is the one used on real
pipeline components; it is pinned against the exact value everywhere.

## Documented treatment of the awkward cases

| case | treatment | why |
|---|---|---|
| empty set | `1.0` | no object, no measurement; matches the production contract for a non-existent component |
| 1 cell | `1.0` **derived** | the union *is* its own convex hull, so the ratio is exactly 1 |
| 2 adjacent cells | `1.0` derived | the union is a 1x2 rectangle, which is its own convex hull |
| thin line (any length) | `1.0` derived | a 1xN rectangle is convex |
| diagonal run (corner-touching) | `< 1`, derived | the union is **not** convex; e.g. 3 cells -> 3/5. The centre hull is degenerate here, which is why a centre-hull formula cannot express this at all |
| L / U / T / plus / hollow | `< 1`, derived | the union is non-convex; values are pinned in :data:`REFERENCE_CASES` |
| disconnected cells in one component | `< 1`, derived | the hull spans the gaps; the ratio is the *fill fraction of the hull* |
| anisotropic ``dx != dy`` | unchanged | the pitch cancels from numerator and denominator alike |
| non-square cells | unchanged | same reason; a 2x1 cell gives the same ratio as a 1x1 cell |
| translated coordinates | unchanged | both areas are translation-covariant |
| uniformly rescaled coordinates | unchanged | both areas scale by ``s^2`` |
| degenerate pitch (``dx <= 0``, non-finite) | `SolidityOracleError` | there is no cell geometry to integrate over; this is a caller error, not a degenerate shape |
| ratio above 1 | clamp inside floating-point tolerance, raise outside it | the union is a subset of its hull, so ``solidity <= 1`` is a theorem; exceeding it by more than round-off is a bug, not a shape |
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import TypeVar

#: A grid cell addressed as ``(row, col)`` in lattice index space.
Cell = tuple[int, int]

#: Supported linear units and their exact conversion to metres. Used by the
#: unit-invariance tests; the pipeline itself is unit-agnostic because the
#: ratio never sees a length.
UNIT_TO_METRES: dict[str, float] = {
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "km": 1e3,
    "ft": 0.3048,
    "in": 0.0254,
}

#: Relative slack allowed when a computed ratio lands just above 1.0. The
#: shoelace sum is a difference of products, so a shape that is exactly convex
#: can still come out a few ulps high. 1e-9 is ~7 orders of magnitude above the
#: observed round-off and ~7 orders below any real geometric gap.
FLOAT_TOLERANCE = 1e-9

CoordT = TypeVar("CoordT", int, float, Fraction)


class SolidityOracleError(ValueError):
    """Raised when the *inputs* violate a mathematical invariant of the ratio.

    Never raised for a legitimate shape: every non-empty cell set with a
    positive pitch has a well-defined solidity in (0, 1].
    """


# ---------------------------------------------------------------------------
# Exact lattice geometry (integers, no floating point anywhere)
# ---------------------------------------------------------------------------
# Work in **half-cell integer coordinates**: cell (row, col) has its centre at
# (2*col, 2*row) and its corners at that point +/- 1 on each axis, so a cell is
# 2 half-cells on a side. One shoelace sum of such a cell is 8 (twice its area
# of 4 half-cell units), and a cell unit is 4 half-cell units, so
# ``area_in_cell_units = |shoelace2| / 8``. Every intermediate is an exact
# integer.
_AREA_DIVISOR = 8


def cell_corners_half(cell: Cell) -> tuple[tuple[int, int], ...]:
    """The four corners of one cell, counter-clockwise, in half-cell units."""
    row, col = cell
    cx, cy = 2 * col, 2 * row
    return ((cx - 1, cy - 1), (cx + 1, cy - 1), (cx + 1, cy + 1), (cx - 1, cy + 1))


def _cross(o: tuple[CoordT, CoordT], a: tuple[CoordT, CoordT], b: tuple[CoordT, CoordT]) -> CoordT:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _shoelace2(points: Sequence[tuple[CoordT, CoordT]]) -> CoordT:
    """Twice the signed area of a closed polygon (exact; integer in, integer out)."""
    total: CoordT = points[0][0] * 0
    count = len(points)
    for index in range(count):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % count]
        total += x0 * y1 - x1 * y0
    return total


def _monotone_chain(points: Sequence[tuple[CoordT, CoordT]]) -> list[tuple[CoordT, CoordT]]:
    """Andrew's monotone chain hull. Collinear points are dropped, so a hull is
    always a minimal vertex set and its shoelace is exact."""
    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return list(ordered)
    lower: list[tuple[CoordT, CoordT]] = []
    for point in ordered:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[CoordT, CoordT]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _boundary_edges_half(cells: Iterable[Cell]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """The union's own boundary, as directed edges.

    Every cell contributes its four counter-clockwise edges; an edge shared with
    a 4-neighbour is internal and dropped. What remains is the boundary of the
    union itself -- which for a corner-touching, disconnected or holed set is
    several disjoint cycles, not one outline.

    The list is deliberately *not* grouped into cycles. Green's theorem makes
    the area a sum over directed boundary edges, and a hole's edges run the
    other way round, so the signed sum is correct for any traversal order and
    correct for a union with holes. Grouping the edges into cycles first would
    add a step that can go wrong (a pinch point admits a self-touching walk)
    without adding information the area needs.
    """
    occupied = set(cells)
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for row, col in sorted(occupied):
        bottom_left, bottom_right, top_right, top_left = cell_corners_half((row, col))
        sides = (
            (bottom_left, bottom_right, (row - 1, col) in occupied),
            (bottom_right, top_right, (row, col + 1) in occupied),
            (top_right, top_left, (row + 1, col) in occupied),
            (top_left, bottom_left, (row, col - 1) in occupied),
        )
        for start, end, shared in sides:
            if not shared:
                edges.append((start, end))
    return edges


def _components(cells: Iterable[Cell]) -> int:
    """8-connected components of the cell set.

    8-connectivity is the pipeline's default and therefore the one that decides
    whether a set of cells ever reaches solidity as a *single* component. The
    count is reported, not acted on: a disconnected set is a legitimate input
    and its solidity is a legitimate (smaller) number.
    """
    remaining = set(cells)
    count = 0
    while remaining:
        count += 1
        stack = [remaining.pop()]
        while stack:
            row, col = stack.pop()
            for drow in (-1, 0, 1):
                for dcol in (-1, 0, 1):
                    neighbour = (row + drow, col + dcol)
                    if neighbour in remaining:
                        remaining.discard(neighbour)
                        stack.append(neighbour)
    return count


def occupied_area_cells(cells: Iterable[Cell]) -> Fraction:
    """Area of the cell union in *cell units*, from the union's own boundary.

    Each cell is 1 cell unit, so this is the physically meaningful
    ``N_cells * dx * dy`` expressed without the pitch -- and it is obtained by
    integrating the boundary, not by counting cells. Edge contributions are
    summed with their signs, so a hole subtracts.
    """
    edges = _boundary_edges_half(cells)
    total = sum(start[0] * end[1] - end[0] * start[1] for start, end in edges)
    return Fraction(abs(total), _AREA_DIVISOR)


def occupied_area_by_runs(cells: Iterable[Cell]) -> Fraction:
    """Second, independent construction of the same area: maximal runs.

    Split each row of occupied cells into maximal runs of 4-adjacent cells. A
    run is one rectangle; runs are pairwise interior-disjoint, so the union area
    is the sum of the run lengths. Shares no code with the boundary trace.
    """
    by_row: dict[int, list[int]] = {}
    for row, col in cells:
        by_row.setdefault(row, []).append(col)
    total = 0
    for cols in by_row.values():
        run = 1
        for previous, current in zip(sorted(cols), sorted(cols)[1:], strict=False):
            if current == previous + 1:
                run += 1
            else:
                total += run
                run = 1
        total += run
    return Fraction(total, 1)


def hull_area_cells(cells: Iterable[Cell]) -> Fraction:
    """Area of the convex hull of the *cell regions*, in cell units.

    The convex hull of a union of polygons equals the convex hull of the union
    of their vertices, so the 4N cell corners are sufficient and exact.
    """
    corners: set[tuple[int, int]] = set()
    for cell in cells:
        corners.update(cell_corners_half(cell))
    hull = _monotone_chain(sorted(corners))
    if len(hull) < 3:
        return Fraction(0, 1)
    return Fraction(abs(_shoelace2(hull)), _AREA_DIVISOR)


def exact_solidity(cells: Iterable[Cell]) -> Fraction:
    """The definitive solidity of a cell set, in exact rational arithmetic.

    The pitch, the origin and the linear unit are all absent by construction:
    each cell is a translate of the unit cell, so the physical areas are the
    cell-unit areas times the same constant and the ratio is the cell-unit
    ratio. This is therefore simultaneously the physical answer and the
    unit-free one.
    """
    occupied = set(cells)
    if not occupied:
        return Fraction(1, 1)
    object_area = occupied_area_cells(occupied)
    if object_area != Fraction(len(occupied), 1):
        raise SolidityOracleError(
            f"traced union area {object_area} disagrees with {len(occupied)} cells"
        )
    hull_area = hull_area_cells(occupied)
    if hull_area < object_area:
        raise SolidityOracleError(
            f"hull area {hull_area} is smaller than the union area {object_area}"
        )
    if hull_area == 0:
        raise SolidityOracleError("zero-area hull: the cells have no extent")
    return object_area / hull_area


# ---------------------------------------------------------------------------
# Physical-coordinate evaluation (what the pipeline actually integrates)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolidityReference:
    """One evaluated cell set, with the intermediates kept for inspection."""

    n_cells: int
    occupied_area: float
    hull_area: float
    solidity: float
    n_components: int
    n_hull_vertices: int
    clamped: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "n_cells": self.n_cells,
            "occupied_area": self.occupied_area,
            "hull_area": self.hull_area,
            "solidity": self.solidity,
            "n_components": self.n_components,
            "n_hull_vertices": self.n_hull_vertices,
            "clamped": self.clamped,
        }


def _check_pitch(cell_dx: float, cell_dy: float) -> tuple[float, float]:
    dx, dy = float(cell_dx), float(cell_dy)
    if not (math.isfinite(dx) and math.isfinite(dy)) or dx <= 0.0 or dy <= 0.0:
        raise SolidityOracleError(f"degenerate cell pitch dx={dx!r} dy={dy!r}")
    return dx, dy


def _clamp_ratio(value: float) -> tuple[float, bool]:
    """Clamp a ratio to 1.0 only for round-off; anything larger is a bug."""
    if value > 1.0:
        if value - 1.0 > FLOAT_TOLERANCE:
            raise SolidityOracleError(
                f"solidity {value!r} exceeds 1 by more than {FLOAT_TOLERANCE}: "
                "the union is a subset of its own convex hull, so this is a defect"
            )
        return 1.0, True
    return value, False


def physical_reference(
    cells: Iterable[Cell],
    cell_dx: float = 1.0,
    cell_dy: float = 1.0,
    origin: tuple[float, float] = (0.0, 0.0),
) -> SolidityReference:
    """Evaluate solidity in **physical** coordinates and report the areas.

    ``cells`` are lattice indices; ``cell_dx``/``cell_dy`` are the physical cell
    extents in whatever linear unit the caller is using; ``origin`` is the
    physical position of cell ``(0, 0)``'s centre. Areas come back in that unit
    and the ratio is the same in every unit, which is what makes solidity
    dimensionless rather than unit-typed.

    Two numerical decisions, both measured rather than assumed:

    * The boundary topology is traced in exact integer half-cell coordinates and
      mapped to physical coordinates only for the shoelace, so a pinch point can
      never be missed because two corners did not compare equal in binary
      floating point.
    * The shoelace is accumulated about the union's own minimum corner, so the
      numbers being differenced are the size of the *component*, never the size
      of the survey. Integrating in absolute coordinates first is legal in exact
      arithmetic and wrong in binary: at an origin of 1e6 m with a 1 mm pitch,
      a one-cell component's area came out 7.6e-6 relative high, because the
      1e-3 difference between two neighbours is computed on values of magnitude
      1e6 whose ulp is already 1.2e-10. Area is translation-covariant, so the
      local frame is the same geometry, exactly.

    ``origin`` therefore does not enter the arithmetic. It is still accepted, and
    validated, so a caller can state the frame it believes it is working in --
    and so the translation-invariance tests check the claim instead of assuming
    it.
    """
    dx, dy = _check_pitch(cell_dx, cell_dy)
    if not (math.isfinite(float(origin[0])) and math.isfinite(float(origin[1]))):
        raise SolidityOracleError(f"non-finite origin {origin!r}")
    occupied = set(cells)
    if not occupied:
        return SolidityReference(0, 0.0, 0.0, 1.0, 0, 0, False)
    edges_half = _boundary_edges_half(occupied)
    min_row = min(row for row, _ in occupied)
    min_col = min(col for _, col in occupied)
    # Half-cell offsets of the union's minimum corner, as exact integers, scaled
    # by the pitch in one multiplication each. No absolute coordinate is formed.
    base_half_x = 2 * min_col - 1
    base_half_y = 2 * min_row - 1

    def to_physical(point: tuple[int, int]) -> tuple[float, float]:
        return (
            (point[0] - base_half_x) * (dx / 2.0),
            (point[1] - base_half_y) * (dy / 2.0),
        )

    # Green's theorem over the directed boundary: the area is a sum over edges,
    # signed, so a hole subtracts. Summing the edges of the half-cell lattice
    # first keeps the whole integrand exact; the physical map is a pure scale.
    total: float = 0.0
    for start, end in edges_half:
        sx, sy = to_physical(start)
        ex, ey = to_physical(end)
        total += sx * ey - ex * sy
    occupied_area = abs(0.5 * total)

    corners: set[tuple[float, float]] = set()
    for cell in occupied:
        corners.update(to_physical(point) for point in cell_corners_half(cell))
    hull = _monotone_chain(sorted(corners))
    hull_area = 0.5 * abs(_shoelace2(hull)) if len(hull) >= 3 else 0.0

    if hull_area <= 0.0:
        raise SolidityOracleError("zero-area hull: the cells have no extent")
    value, clamped = _clamp_ratio(occupied_area / hull_area)
    return SolidityReference(
        n_cells=len(occupied),
        occupied_area=occupied_area,
        hull_area=hull_area,
        solidity=value,
        n_components=_components(occupied),
        n_hull_vertices=len(hull),
        clamped=clamped,
    )


def reference_solidity(
    cells: Iterable[Cell],
    cell_dx: float = 1.0,
    cell_dy: float = 1.0,
    origin: tuple[float, float] = (0.0, 0.0),
) -> float:
    """Convenience wrapper: just the dimensionless ratio."""
    return physical_reference(cells, cell_dx, cell_dy, origin).solidity


# ---------------------------------------------------------------------------
# The reference case table (Phase B)
# ---------------------------------------------------------------------------
# Every row is a *constructed* cell set with an analytically knowable answer.
# The `solidity` column is a hand-derived rational, written down independently
# of the code that is being tested; the oracle is then required to reproduce it
# and the production implementation is required to reproduce the oracle.
#
# Two rows exist specifically because the v2 design table's printed values were
# mislabelled, and copying them would have carried the error forward:
#
# * `l_shape_3` is the geometry whose solidity is 6/7. The v2 table prints
#   0.857143 against a row labelled "L (6 cells)", which is a 3-cell L; its
#   *6-cell* L has a different value, `l_shape_6` = 2/3, and the 6-cell shape
#   with solidity 6/7 is the P shape `p_shape_6`.
# * `plus_5` is 5/7 = 0.714286: the cross's centre hull is a diamond of area 2,
#   not the 2x2 bounding square, so the hull area is 7 and not 9. Reading the
#   bounding box for the hull overstates it by 2 and would have "confirmed" a
#   wrong number.


@dataclass(frozen=True)
class ReferenceCase:
    """One constructed geometry and the exact quantities derived from it."""

    name: str
    cells: tuple[Cell, ...]
    solidity: Fraction
    treatment: str

    @property
    def n_cells(self) -> int:
        return len(self.cells)

    @property
    def occupied_cells(self) -> Fraction:
        return Fraction(self.n_cells, 1)

    @property
    def hull_cells(self) -> Fraction:
        return self.occupied_cells / self.solidity

    def cell_set(self) -> set[Cell]:
        return set(self.cells)


def _block(rows: int, cols: int) -> tuple[Cell, ...]:
    return tuple((r, c) for r in range(rows) for c in range(cols))


def _ring(rows: int, cols: int) -> tuple[Cell, ...]:
    return tuple(
        (r, c) for r in range(rows) for c in range(cols) if r in (0, rows - 1) or c in (0, cols - 1)
    )


#: name -> (cells, exact solidity, why it is the answer)
_RAW_CASES: tuple[tuple[str, tuple[Cell, ...], Fraction, str], ...] = (
    ("one_cell", ((0, 0),), Fraction(1), "a cell is its own convex hull"),
    (
        "two_adjacent_horizontal",
        ((0, 0), (0, 1)),
        Fraction(1),
        "the union is a 1x2 rectangle, which is convex",
    ),
    (
        "two_adjacent_vertical",
        ((0, 0), (1, 0)),
        Fraction(1),
        "the union is a 2x1 rectangle, which is convex",
    ),
    (
        "two_adjacent_diagonal",
        ((0, 0), (1, 1)),
        Fraction(2, 3),
        "two corner-touching cells: hull is a hexagon of area 3, not 2",
    ),
    ("horizontal_line_3", ((0, 0), (0, 1), (0, 2)), Fraction(1), "a 1x3 rectangle is convex"),
    (
        "horizontal_line_5",
        ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4)),
        Fraction(1),
        "a 1x5 rectangle is convex",
    ),
    (
        "vertical_line_3",
        ((0, 0), (1, 0), (2, 0)),
        Fraction(1),
        "a 3x1 rectangle is convex",
    ),
    (
        "vertical_line_5",
        ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0)),
        Fraction(1),
        "a 5x1 rectangle is convex",
    ),
    (
        "diagonal_3",
        ((0, 0), (1, 1), (2, 2)),
        Fraction(3, 5),
        "corner-touching run: hull hexagon of area 5, union of area 3",
    ),
    (
        "diagonal_5",
        ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4)),
        Fraction(5, 9),
        "corner-touching run: hull octagon of area 9, union of area 5",
    ),
    ("square_2x2", _block(2, 2), Fraction(1), "convex"),
    ("square_3x3", _block(3, 3), Fraction(1), "convex"),
    ("square_5x5", _block(5, 5), Fraction(1), "convex"),
    ("rectangle_5x2", _block(2, 5), Fraction(1), "convex"),
    ("rectangle_2x3", _block(2, 3), Fraction(1), "convex"),
    ("rectangle_3x2", _block(3, 2), Fraction(1), "convex"),
    (
        "l_shape_3",
        ((0, 0), (0, 1), (1, 0)),
        Fraction(6, 7),
        "2x2 block minus one corner: hull is the 2x2 square less one half cell, area 7/2",
    ),
    (
        "l_shape_4",
        ((0, 0), (0, 1), (0, 2), (1, 0)),
        Fraction(4, 5),
        "3-cell bar plus one cell on the end: centre hull triangle area 1, padded to 5",
    ),
    (
        "l_shape_6",
        ((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (2, 0)),
        Fraction(2, 3),
        "4-cell bar plus a 3-cell bar: centre hull triangle area 3, padded to 9",
    ),
    (
        "p_shape_6",
        ((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1)),
        Fraction(6, 7),
        "4-cell bar with a 2-cell tab: hull quadrilateral area 2, padded to 7 -- "
        "this, not the 6-cell L, is the shape v2's table measured at 6/7",
    ),
    (
        "u_shape_8",
        _ring(3, 3),
        Fraction(8, 9),
        "3x3 ring: centre hull is the full square, padded to 9",
    ),
    (
        "plus_5",
        ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1)),
        Fraction(5, 7),
        "cross: the centre hull is a diamond of area 2, not the 2x2 box, so 2+5=7",
    ),
    (
        "t_shape_7",
        ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 2)),
        Fraction(7, 11),
        "5-cell bar with a 2-cell stem: centre hull triangle area 4, padded to 11",
    ),
    (
        "h_hollow_19",
        tuple(set(_block(5, 5)) - {(3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3)}),
        Fraction(19, 25),
        "5x5 block with a 3x2 bite: centre hull is the full 4x4 square, padded to 25",
    ),
    (
        "disconnected_one_plus_two",
        ((0, 0), (0, 1), (1, 0)),
        Fraction(6, 7),
        "a 3-cell L: a degenerate (single-cell) component in the v2 table",
    ),
    (
        "disconnected_two_2x2_blocks",
        ((0, 0), (0, 1), (1, 0), (1, 1), (5, 5), (5, 6), (6, 5), (6, 6)),
        Fraction(1, 3),
        "two 2x2 blocks 5 cells apart: hull of area 24 for 8 cells of union",
    ),
    (
        "l_with_detached_cell",
        ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 0), (5, 5)),
        Fraction(1, 3),
        "a 6-cell L plus a detached cell: hull of area 21 for 7 cells of union",
    ),
    (
        "disconnected_diagonal_pairs",
        ((0, 0), (1, 1), (4, 0), (5, 1)),
        Fraction(4, 11),
        "two corner-touching pairs 4 cells apart: centre hull is a parallelogram of "
        "area 4, padded by 7 to 11 for a union of 4",
    ),
)

REFERENCE_CASES: tuple[ReferenceCase, ...] = tuple(
    ReferenceCase(name, cells, solidity, treatment)
    for name, cells, solidity, treatment in _RAW_CASES
)

#: The pitches the exact value must survive: isotropic, anisotropic in both
#: directions, and two orders of magnitude in either direction.
PITCHES: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (0.5, 0.5),
    (0.25, 0.5),
    (0.5, 0.25),
    (2.0, 0.5),
    (0.001, 0.001),
    (1000.0, 1000.0),
)

#: Uniform scale factors for the rescaling-invariance property.
SCALES: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 1000.0)


def case_by_name(name: str) -> ReferenceCase:
    for case in REFERENCE_CASES:
        if case.name == name:
            return case
    raise KeyError(name)


__all__ = [
    "PITCHES",
    "REFERENCE_CASES",
    "SCALES",
    "UNIT_TO_METRES",
    "FLOAT_TOLERANCE",
    "Cell",
    "ReferenceCase",
    "SolidityOracleError",
    "SolidityReference",
    "case_by_name",
    "cell_corners_half",
    "exact_solidity",
    "hull_area_cells",
    "occupied_area_by_runs",
    "occupied_area_cells",
    "physical_reference",
    "reference_solidity",
]

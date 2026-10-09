"""Independent oracles for the definitional bounds.

Every definitional bound carries three separate checks: the bound is
valid, the witness attains it, and production agrees. An oracle sharing
production's code verifies nothing, which is the defect that let a legacy
scale reference score itself against a constant wrong by a factor of 1.51
without anyone noticing: the oracle and the implementation were the same
table.

The solidity oracle is a hand-derived rational table plus a generated
exhaustive check over small cell sets, in exact arithmetic with no
tolerance. The legacy solidity oracle's stated reason turned out to be
false on inspection, so it is replaced rather than trusted: read
``docs/legacy/groundscan/validation/solidity_reference.py`` and
``docs/legacy/groundscan/core/shape.py`` as archaeology, never imported.
Its reason claimed Qhull raises on collinear input, true only for
cell-centre hulls; under the corner hull a 1xN strip does not raise. The
pitch apparatus, the physical reference and any tolerance constant are
deleted as dead under the pitch-free ruling: solidity depends only on the
integer cell pattern.

The compactness bound is proved from the perimeter inequality rather than
measured: occupied cells fit within occupied rows times columns, so the
perimeter has a floor in the square root of the area, and the bound falls
out. The proof is stated in ``docs/contract.md``.

A bound derived from an inventory rather than computed twice is
independent by construction, so it owes no second implementation: the
field area's two ends follow from the cell count and the scan's own
measured extremes, so they are built rather than read off the corpus.

The corpus's role is evidence and never a grade. Measured agreement may
support a property's coverage and may never justify, strengthen or weaken
its bound. The partition of scans across states is recorded as evidence
and never as a property. An oracle loading its data from the contract it
checks is recorded as unexercised coverage rather than passing.

This module uses only the standard library so it shares no code with the
implementation it checks: no import from descriptors, hierarchy,
positions, scale, document, quantity or property registries.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

Cell = tuple[int, int]


class SolidityCase(NamedTuple):
    """One constructed geometry with its hand-derived exact solidity."""

    name: str
    cells: tuple[Cell, ...]
    solidity: Fraction
    reason: str


SOLIDITY_REFERENCE: Final[tuple[SolidityCase, ...]] = (
    SolidityCase("one-cell", ((0, 0),), Fraction(1, 1), "a cell is its own hull"),
    SolidityCase(
        "domino",
        ((0, 0), (1, 0)),
        Fraction(1, 1),
        "the union is a 1x2 rectangle, which is convex",
    ),
    SolidityCase(
        "square-2x2",
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        Fraction(1, 1),
        "convex block is its own hull",
    ),
    SolidityCase(
        "square-3x3",
        (
            (0, 0),
            (0, 1),
            (0, 2),
            (1, 0),
            (1, 1),
            (1, 2),
            (2, 0),
            (2, 1),
            (2, 2),
        ),
        Fraction(1, 1),
        "convex block is its own hull",
    ),
    SolidityCase(
        "line-5",
        ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0)),
        Fraction(1, 1),
        "a 1x5 rectangle is convex",
    ),
    SolidityCase(
        "l-shape-3",
        ((0, 0), (0, 1), (1, 0)),
        Fraction(6, 7),
        "2x2 block minus one corner leaves half a cell outside",
    ),
    SolidityCase(
        "diagonal-2",
        ((0, 0), (1, 1)),
        Fraction(2, 3),
        "corner-touching pair spans a hexagon of area 3 for 2 cells",
    ),
    SolidityCase(
        "diagonal-3",
        ((0, 0), (1, 1), (2, 2)),
        Fraction(3, 5),
        "corner-touching run spans a hexagon of area 5 for 3 cells",
    ),
    SolidityCase(
        "plus-5",
        ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1)),
        Fraction(5, 7),
        "cross centre hull is a diamond of area 2, total hull 7",
    ),
    SolidityCase(
        "ring-3x3",
        ((0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)),
        Fraction(8, 9),
        "border of the 3x3 square fills 8 of hull area 9",
    ),
    SolidityCase(
        "two-blocks",
        ((0, 0), (0, 1), (1, 0), (1, 1), (5, 5), (5, 6), (6, 5), (6, 6)),
        Fraction(1, 3),
        "two 2x2 blocks apart span hull area 24 for 8 cells",
    ),
)

COMPACTNESS_WITNESS: Final[tuple[Cell, ...]] = ((0, 0),)

FIELD_AREA_LOWER_CELLS: Final[int] = 1

COMPONENT_WITNESS_REQUIRES_RECTANGULAR: Final[bool] = True

BOUND_DERIVATIONS: Final[dict[str, str]] = {
    "solidity": "occupied cells lie inside a hull that contains them",
    "compactness": "perimeter inequality P >= 4 sqrt(A) gives pi/4",
    "field-area": "built from cell count and scan measured extremes",
    "detection-count": "charging argument over tie groups, no connectivity",
    "component-count": "independence number of the connectivity graph",
    "scale-disagreement": "pinned relative form in [0, 1] identically",
    "median-atom-fraction": "exact numerator over exact denominator",
}

BOUND_WITNESS_KIND: Final[dict[str, str]] = {
    "solidity": "convex cell set attains 1.0",
    "compactness": "single cell attains pi/4",
    "field-area": "single cell attains floor, full cover attains ceiling",
    "detection-count": "isolated distinct cells attain n, one block attains c1",
    "component-count": "checkerboard attains ceiling on full rectangles only",
    "scale-disagreement": "coincident estimates attain 0, single-sided zero attains 1",
    "median-atom-fraction": "no tie attains 0, constant field attains 1",
}


def _oracle_turn(origin: tuple[int, int], first: tuple[int, int], second: tuple[int, int]) -> int:
    """Return the turn sign of two edges sharing one vertex.

    Args:
        origin: The shared vertex.
        first: The far end of the first edge.
        second: The far end of the second edge.

    Returns:
        Positive for a left turn, negative for right, zero if collinear.
    """
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
        second[0] - origin[0]
    )


def _oracle_corners(cells: Sequence[Cell]) -> set[tuple[int, int]]:
    """Collect doubled integer corners for one cell set.

    Args:
        cells: Lattice coordinates of one component.

    Returns:
        Doubled corner points, four per cell.
    """
    found: set[tuple[int, int]] = set()
    for impulse, scan_line in cells:
        base_x = 2 * impulse
        base_y = 2 * scan_line
        found.add((base_x - 1, base_y - 1))
        found.add((base_x + 1, base_y - 1))
        found.add((base_x + 1, base_y + 1))
        found.add((base_x - 1, base_y + 1))
    return found


def _pick_start(corners: set[tuple[int, int]]) -> tuple[int, int]:
    """Return the least corner as the gift-wrapping start.

    Args:
        corners: Doubled corner points.

    Returns:
        The minimum corner.
    """
    return min(corners)


def _pick_next(current: tuple[int, int], corners: set[tuple[int, int]]) -> tuple[int, int]:
    """Pick the most clockwise corner from the current hull vertex.

    Args:
        current: The current hull vertex.
        corners: All doubled corner points.

    Returns:
        The next hull vertex.

    Raises:
        ValueError: When no candidate differs from the current vertex.
    """
    best: tuple[int, int] | None = None
    for candidate in corners:
        if candidate == current:
            continue
        if best is None:
            best = candidate
            continue
        turn = _oracle_turn(current, best, candidate)
        if turn < 0:
            best = candidate
        elif turn == 0:
            here = (candidate[0] - current[0]) ** 2 + (candidate[1] - current[1]) ** 2
            there = (best[0] - current[0]) ** 2 + (best[1] - current[1]) ** 2
            if here > there:
                best = candidate
    if best is None:
        msg = "no corner differs from the current hull vertex"
        raise ValueError(msg)
    return best


def _gift_wrap(corners: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """Wrap the corner set by gift wrapping, unlike production's chain.

    Args:
        corners: Doubled corner points.

    Returns:
        Hull vertices in order without repetition.
    """
    start = _pick_start(corners)
    hull = [start]
    current = start
    while True:
        following = _pick_next(current, corners)
        if following == start:
            break
        hull.append(following)
        current = following
    return hull


def _shoelace_total(hull: Sequence[tuple[int, int]]) -> int:
    """Sum the shoelace cross terms over one closed hull.

    Args:
        hull: Hull vertices in order.

    Returns:
        The absolute doubled-area sum as an integer.
    """
    total = 0
    size = len(hull)
    for position in range(size):
        x1, y1 = hull[position]
        x2, y2 = hull[(position + 1) % size]
        total += x1 * y2 - x2 * y1
    return abs(total)


def oracle_hull_area8(cells: Sequence[Cell]) -> int:
    """Return eight times the corner-hull area via gift wrapping.

    Gift wrapping agrees with production's monotone chain on every input
    while sharing no code with it: different hull walk, separate shoelace.

    Args:
        cells: Lattice coordinates of one non-empty component.

    Returns:
        Eight times the hull area as an integer.
    """
    corners = _oracle_corners(cells)
    hull = _gift_wrap(corners)
    return _shoelace_total(hull)


def oracle_solidity(cells: Sequence[Cell]) -> Fraction:
    """Return occupied cells over the oracle hull, exactly.

    Args:
        cells: Lattice coordinates of one non-empty component.

    Returns:
        The solidity as an exact rational in (0, 1].
    """
    materialised = list(cells)
    return Fraction(8 * len(materialised), oracle_hull_area8(materialised))


def _side_pairs(cells: Sequence[Cell]) -> dict[frozenset[Cell], int]:
    """Count unordered shared sides over one cell set.

    Args:
        cells: Lattice coordinates of one component.

    Returns:
        Occurrence count per unordered neighbouring pair.
    """
    owned = set(cells)
    counts: dict[frozenset[Cell], int] = {}
    for impulse, scan_line in owned:
        for neighbour in (
            (impulse - 1, scan_line),
            (impulse + 1, scan_line),
            (impulse, scan_line - 1),
            (impulse, scan_line + 1),
        ):
            pair = frozenset(((impulse, scan_line), neighbour))
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def oracle_perimeter(cells: Sequence[Cell]) -> int:
    """Count exposed lattice edges via shared-side occurrences.

    An interior side is contributed from both ends and counted twice;
    a boundary side appears once. Hole boundaries count, unlike an
    erosion-based perimeter.

    Args:
        cells: Lattice coordinates of one component.

    Returns:
        The exposed edge count.
    """
    counts = _side_pairs(cells)
    return sum(1 for total in counts.values() if total == 1)


def perimeter_inequality_holds(cells: Sequence[Cell]) -> bool:
    """Report whether the perimeter inequality holds for one cell set.

    The inequality P*P >= 16*A is exact integer arithmetic: it proves the
    compactness bound pi/4 without measuring anything.

    Args:
        cells: Lattice coordinates of one non-empty component.

    Returns:
        True where the squared perimeter reaches sixteen areas.
    """
    materialised = list(cells)
    area = len(materialised)
    perimeter = oracle_perimeter(materialised)
    return perimeter * perimeter >= 16 * area


def field_area_lower(pitch_x: Fraction, pitch_y: Fraction) -> Fraction:
    """Return the field-area floor for one cell, built from pitches.

    Independent by construction: built from the inventory rather than
    computed twice, so it owes no second implementation.

    Args:
        pitch_x: The along-line pitch as an exact rational.
        pitch_y: The across-lines pitch as an exact rational.

    Returns:
        The area of the single cell a leaf detection is.
    """
    return pitch_x * pitch_y


def field_area_upper(measured_cells: int, pitch_x: Fraction, pitch_y: Fraction) -> Fraction:
    """Return the field-area ceiling for full measured coverage.

    Args:
        measured_cells: The scan's measured cells.
        pitch_x: The along-line pitch as an exact rational.
        pitch_y: The across-lines pitch as an exact rational.

    Returns:
        The area of one detection covering every measured cell.
    """
    return Fraction(measured_cells, 1) * pitch_x * pitch_y


def connected_components_4(cells: set[Cell]) -> int:
    """Count 4-connected components by breadth search, unlike union-find.

    Args:
        cells: Lattice coordinates of one polarity's cell set.

    Returns:
        The component count of the set.
    """
    remaining = set(cells)
    total = 0
    while remaining:
        total += 1
        stack = [remaining.pop()]
        while stack:
            impulse, scan_line = stack.pop()
            for neighbour in (
                (impulse - 1, scan_line),
                (impulse + 1, scan_line),
                (impulse, scan_line - 1),
                (impulse, scan_line + 1),
            ):
                if neighbour in remaining:
                    remaining.discard(neighbour)
                    stack.append(neighbour)
    return total


def detection_count_upper(entering: int) -> int:
    """Return the sharp detection-count ceiling for entering cells.

    Args:
        entering: Cells entering the hierarchy for one polarity.

    Returns:
        The entering count itself.
    """
    return entering


def detection_count_lower(components: int) -> int:
    """Return the detection-count floor for initial components.

    Args:
        components: Components of the polarity's full cell set.

    Returns:
        The component count itself.
    """
    return components


def component_count_max_4conn(width: int, height: int) -> int:
    """Return the 4-connectivity independence ceiling for a rectangle.

    The checkerboard attains it, so the bound is sharp. Claimed only
    where the lattice is a rectangular fully-measured set.

    Args:
        width: Lattice width in cells.
        height: Lattice height in cells.

    Returns:
        Ceiling of width times height over two.
    """
    return (width * height + 1) // 2


def is_rectangular_fully_measured(width: int, height: int, measured: int) -> bool:
    """Report whether a lattice is a full rectangle with no gaps.

    Args:
        width: Lattice width in cells.
        height: Lattice height in cells.
        measured: Measured cells in the scan.

    Returns:
        True exactly where measured fills the rectangle.
    """
    return width > 0 and height > 0 and measured == width * height


def _oracle_is_zero(value: float) -> bool:
    """Report whether a float is exactly zero without an equality test.

    Args:
        value: The finite value to test.

    Returns:
        True for positive or negative zero, False otherwise.
    """
    return not (value > 0.0 or value < 0.0)


def scale_disagreement_oracle(mad: float, iqr: float) -> Fraction:
    """Return the pinned disagreement for unscaled parts, exactly.

    With a = mad/Z and b = iqr/(2Z) the form |a-b|/max(a,b) equals
    |2*mad-iqr|/max(2*mad,iqr), so the calibration cancels by
    construction. Dimensionless, symmetric, in [0, 1] identically.

    Args:
        mad: Unscaled median absolute deviation.
        iqr: Unscaled interquartile range.

    Returns:
        Zero where both vanish, one where exactly one vanishes, else the
        relative gap as an exact rational of the given floats.
    """
    doubled = 2.0 * mad
    if _oracle_is_zero(doubled) and _oracle_is_zero(iqr):
        return Fraction(0, 1)
    top = abs(doubled - iqr)
    bottom = max(doubled, iqr)
    return Fraction(top).limit_denominator() / Fraction(bottom).limit_denominator()


def median_atom_oracle(numerator: int, denominator: int) -> Fraction:
    """Return the median-atom fraction for exact counts.

    Args:
        numerator: Cells exactly equal to the median.
        denominator: Finite residuals.

    Returns:
        The exact fraction, with empty support reading zero.
    """
    if denominator == 0:
        return Fraction(0, 1)
    return Fraction(numerator, denominator)

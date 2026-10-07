"""Index-space descriptors for detections: shape, area, depth and contact.

Every quantity here is computable from the index space alone, needing no
declared extent, except field area, which is the one descriptor that
needs a pitch. Solidity and compactness are ratios over a cell set and
therefore pitch-invariant: they describe index space, not the shape of
anything on the ground.

Solidity is occupied cell count over the convex hull of the cell
corners, computed in integer arithmetic so no tolerance is needed, and
exactly 1.0 for any convex cell set. Compactness is four pi times area
over exposed lattice-edge perimeter squared, counting hole boundaries.
Field area is the detection's own occupied cells times the two pitches,
never the hull, with both pitches read from the declared spans over the
observed counts. Depth is an interval spanning the covered samples'
device values, absent where no sample carries one. Boundary contact is
two distinct facts: lattice-boundary cells and padding-adjacent cells.
"""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final, Literal

_MIN_CHAIN_POINTS: Final[int] = 2
_MIN_PITCH_COUNT: Final[int] = 2


class AreaResult(NamedTuple):
    """A field area with its withheld reason where it cannot be stated."""

    value: float | None
    withheld: Literal["requires-declared-extent", "requires-homogeneous-axes"] | None


def _order_key(key: tuple[int, int]) -> tuple[int, int]:
    """Return the lattice-order sort key for one coordinate.

    Lattice order is scan-line major, matching the hierarchy's numbering.

    Args:
        key: The coordinate as an impulse and scan-line pair.

    Returns:
        The scan line first, then the impulse.
    """
    impulse, scan_line = key
    return (scan_line, impulse)


def _cross(origin: tuple[int, int], first: tuple[int, int], second: tuple[int, int]) -> int:
    """Return the z-component of the turn from two edges.

    Args:
        origin: The shared vertex.
        first: The first edge's far end.
        second: The second edge's far end.

    Returns:
        Positive for a left turn, negative for right, zero when collinear.
    """
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
        second[0] - origin[0]
    )


def _convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return the convex hull vertices in counter-clockwise order.

    Andrew's monotone chain over exact integers: collinear interior
    points are dropped, which never changes the shoelace sum.

    Args:
        points: The distinct integer points to enclose.

    Returns:
        The hull vertices without repetition.
    """
    ordered = sorted(set(points))
    lower: list[tuple[int, int]] = []
    for point in ordered:
        while len(lower) >= _MIN_CHAIN_POINTS and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[int, int]] = []
    for point in reversed(ordered):
        while len(upper) >= _MIN_CHAIN_POINTS and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def hull_shoelace8(cells: Sequence[tuple[int, int]]) -> int:
    """Return eight times the corner-hull area of one cell set.

    Corners are doubled to integers, so the shoelace sum is exact: eight
    times the hull area in cell units, never less than eight for a
    non-empty set, since one cell already spans one unit square.

    Args:
        cells: The lattice coordinates of one component.

    Returns:
        Eight times the hull area, as an integer.
    """
    corners = [
        (2 * impulse + dx, 2 * scan_line + dy)
        for impulse, scan_line in cells
        for dx in (-1, 1)
        for dy in (-1, 1)
    ]
    hull = _convex_hull(corners)
    total = 0
    for (x1, y1), (x2, y2) in zip(hull, hull[1:] + hull[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total)


def solidity(cells: Sequence[tuple[int, int]]) -> float:
    """Return occupied cells over the hull of cell corners.

    Eight times the count over the doubled shoelace sum: one division,
    exact, with no tolerance anywhere. Exactly 1.0 for any convex set,
    since a convex union of unit squares has hull area equal to its
    count. Never the legacy mix of a cell-area numerator with a
    centre-based hull.

    Args:
        cells: The lattice coordinates of one non-empty component.

    Returns:
        The solidity in (0, 1].
    """
    return 8 * len(list(cells)) / hull_shoelace8(cells)


def exposed_perimeter(cells: Sequence[tuple[int, int]]) -> int:
    """Count the exposed lattice edges of one cell set.

    An edge is exposed where its neighbour is absent from the set,
    whatever the reason: padding, a missing coordinate or open lattice.
    Hole boundaries count, so elongation and irregularity both penalise.

    Args:
        cells: The lattice coordinates of one component.

    Returns:
        The exposed edge count.
    """
    owned = set(cells)
    total = 0
    for impulse, scan_line in owned:
        neighbours = (
            (impulse - 1, scan_line),
            (impulse + 1, scan_line),
            (impulse, scan_line - 1),
            (impulse, scan_line + 1),
        )
        total += sum(1 for neighbour in neighbours if neighbour not in owned)
    return total


def compactness(cells: Sequence[tuple[int, int]]) -> float:
    """Return four pi times area over squared exposed perimeter.

    The area is the occupied count in cell units; the perimeter counts
    hole boundaries. Bounded above by pi over four, attained by the
    single cell, and discretised at small sizes: a fifty-cell line and
    a five-by-five block are both perfectly convex yet score far apart,
    so equal solidity never implies equal compactness.

    Args:
        cells: The lattice coordinates of one non-empty component.

    Returns:
        The compactness in (0, pi/4].
    """
    area = len(list(cells))
    perimeter = exposed_perimeter(cells)
    return 4 * math.pi * area / (perimeter * perimeter)


def _bits(value: float) -> int:
    """Expose the binary64 bits of one pitch for exact comparison.

    A tolerance here would be a threshold wearing a gate's clothes: two
    pitches either are one unit or are not, so homogeneity is decided by
    bitwise identity, never by closeness.

    Args:
        value: The pitch to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def field_area_result(
    cell_count: int,
    field_length: float | None,
    field_width: float | None,
    impulse_count: int,
    scan_line_count: int,
) -> AreaResult:
    """Reduce occupied cells and declared geometry to a field area.

    The area is the detection's own occupied cells times the along-line
    pitch times the across-line pitch, each pitch its declared span over
    its observed count less one. The hull is never read: an anomaly is a
    connected set of residuals, and the hull is an artefact introduced
    only to make solidity computable. Withheld in exactly two named
    ways: no declared extent, or axes that are not one unit, including
    an axis with a single observed index, which defines no pitch at all.
    The pitches are read here from the declared spans over the observed
    counts, which keeps every figure recomputable from the record; the
    citation from the field position lands with the positions themselves.

    Args:
        cell_count: The detection's occupied measured cells.
        field_length: The declared along-line span, absent where never
            declared.
        field_width: The declared across-lines span, absent where never
            declared.
        impulse_count: The observed impulse indices along one line.
        scan_line_count: The observed scan-line indices.

    Returns:
        The area with no withheld reason, or no area with its cause.
    """
    if field_length is None or field_width is None:
        return AreaResult(None, "requires-declared-extent")
    if impulse_count < _MIN_PITCH_COUNT or scan_line_count < _MIN_PITCH_COUNT:
        return AreaResult(None, "requires-homogeneous-axes")
    pitch_x = field_length / (impulse_count - 1)
    pitch_y = field_width / (scan_line_count - 1)
    if _bits(pitch_x) != _bits(pitch_y):
        return AreaResult(None, "requires-homogeneous-axes")
    return AreaResult(cell_count * pitch_x * pitch_y, None)


def depth_interval(values: Sequence[float]) -> tuple[float, float] | None:
    """Span the covered samples' device values, or stay absent.

    The interval is the minimum to the maximum over the samples carrying
    a value, never a point invented by aggregation, and absent where no
    sample carries one, never zero. A single valued sample spans the
    degenerate pair of itself with itself: that is the span of what was
    covered, not an aggregation, and aggregation is what the never-a-point
    rule forbids. Nothing is derived from travel time or soil factors:
    the inputs are the vendor's per-sample estimates as exported.

    Args:
        values: The device depth values over one detection's cells.

    Returns:
        The spanning pair, or None where no sample carries a value.
    """
    available = list(values)
    if not available:
        return None
    return (min(available), max(available))


def split_boundary(
    cells: Sequence[tuple[int, int]],
    bounds: tuple[int, int, int, int],
    unmeasured: frozenset[tuple[int, int]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Split one detection's cells into its two boundary facts.

    Lattice-boundary cells lie on the measured lattice's own edge, where
    the anomaly is clipped by the instrument's field. Padding-adjacent
    cells touch, inside the lattice bounds, a coordinate with nothing
    measured: padding or a missing region, flanked by nothing. The two
    are different confounds and travel separately, with no threshold on
    either: whether proximity matters is the consumer's judgement.

    Args:
        cells: The lattice coordinates of one component.
        bounds: The lattice edges as minimum and maximum impulse with
            minimum and maximum scan line.
        unmeasured: The in-bounds coordinates carrying no measurement.

    Returns:
        Boundary cells with padding-adjacent cells, each in lattice
        order.
    """
    low_impulse, high_impulse, low_line, high_line = bounds
    owned = set(cells)
    boundary = sorted(
        (
            key
            for key in owned
            if key[0] == low_impulse
            or key[0] == high_impulse
            or key[1] == low_line
            or key[1] == high_line
        ),
        key=_order_key,
    )
    adjacent: list[tuple[int, int]] = []
    for key in sorted(owned, key=_order_key):
        impulse, scan_line = key
        neighbours = (
            (impulse - 1, scan_line),
            (impulse + 1, scan_line),
            (impulse, scan_line - 1),
            (impulse, scan_line + 1),
        )
        if any(neighbour in unmeasured for neighbour in neighbours):
            adjacent.append(key)
    return boundary, adjacent

"""The background model: a multiscale median pinned as a versioned convention.

The background is a median across a three-scale ladder of centred, clipped
square windows of size 3, 5 and 9. Each window median is taken over measured
cells only. Padding is never filled: windows are never replicated, reflected
or wrapped, so every pinned scale is defined on every scan and no scan needs
a viability rule or a per-scan scale set. Support is derived per scale and
never stored.

The ladder count is odd and load-bearing: a median across an even number of
scales would be an average of two order statistics rather than one, forfeiting
the median-atom property that later makes the scale's blind spot predictable.
An even-support median evaluates as half the lower central order statistic
plus half the upper, in that operand order, in binary64 round-to-nearest-even:
the single IEEE-754 addition, halving first so a pair of large finite values
cannot overflow where their sum would. It is a computed value, never stored.

No trend term is removed. The largest window already is the low-frequency
removal, and an explicit fitted trend would be a geometric claim about the
ground that the claim regime forbids, and it would double-count. The
combination was pinned by measured polarity symmetry rather than taste, since
polarity is defined against the background and a background shifting it is
circular. That pinning criterion is stated here rather than left as taste.

Windows, support rule and combination are processing metadata describing the
computation, never a claim about the ground. A gap near a cell therefore does
not manufacture a value for its neighbour, which is the single most
consequential difference from the legacy engine, where nearest-valid fill
biased every neighbour within one filter radius.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

CONVENTION: Final[str] = "background-model-v1"
WINDOWS: Final[tuple[int, int, int]] = (3, 5, 9)
SUPPORT_RULE: Final[str] = "measured-cells-only"
COMBINATION: Final[str] = "median"
TREND: Final[str] = "none"

# The background operator's sup-norm Lipschitz constant. Forced for the whole
# class of order-preserving shift-equivariant operators rather than tuned for
# this model: shift-equivariance answers a uniform offset, so shifting every
# input by c shifts the output by c and LAMBDA >= 1; monotonicity answers an
# arbitrary spread, so moving inputs by at most a moves the median by at most
# a and LAMBDA <= 1. Hence exactly one. Adding a trend term would leave the
# class by construction, since a fitted slope is not shift-equivariant.
LAMBDA: Final[float] = 1.0


def median(values: Sequence[float]) -> float:
    """Return the median with the pinned even-support evaluation order.

    An odd support returns its single central order statistic. An even
    support returns half the lower central order statistic plus half the
    upper, in that operand order, in binary64 round-to-nearest-even.

    Args:
        values: The finite values to reduce, at least one.

    Returns:
        The median value.

    Raises:
        ValueError: When called with no values, which never happens for a
            measured cell since its own window always contains itself.
    """
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        msg = "median needs at least one measured value"
        raise ValueError(msg)
    middle = count // 2
    if count % 2 == 1:
        return ordered[middle]
    lower = ordered[middle - 1]
    upper = ordered[middle]
    return 0.5 * lower + 0.5 * upper


def _window_values(
    measured: dict[tuple[int, int], float],
    impulse: int,
    scan_line: int,
    half: int,
) -> list[float]:
    """Collect one window's measured responses around one cell.

    The window is the centred square of the given half-extent clipped to the
    lattice, taken over measured cells only. Missing coordinates contribute
    nothing, and no padding value is ever manufactured.

    Args:
        measured: Responses keyed by lattice coordinate, measured cells only.
        impulse: The centre cell's impulse index.
        scan_line: The centre cell's scan-line index.
        half: The half-extent, one for size 3, two for size 5, four for 9.

    Returns:
        The measured responses inside the window, at least the centre's own.
    """
    found: list[float] = []
    for candidate_impulse in range(impulse - half, impulse + half + 1):
        for candidate_line in range(scan_line - half, scan_line + half + 1):
            value = measured.get((candidate_impulse, candidate_line))
            if value is not None:
                found.append(value)
    return found


def backgrounds(measured: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """Estimate the background at every measured cell.

    Each background is the median of the three window medians at sizes 3, 5
    and 9. The three is odd on purpose, so the combination is a single order
    statistic rather than an average of two.

    Args:
        measured: Responses keyed by lattice coordinate, measured cells only.

    Returns:
        The background per measured cell, in original measurement units.
    """
    halves = [size // 2 for size in WINDOWS]
    estimated: dict[tuple[int, int], float] = {}
    for key in measured:
        impulse, scan_line = key
        scales = [median(_window_values(measured, impulse, scan_line, half)) for half in halves]
        estimated[key] = median(scales)
    return estimated


def residuals(measured: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """Return response minus background at every measured cell.

    The residual is in original measurement units and finite wherever the
    response is finite: the background is a median of finite responses, and
    a window of support one reproduces its centre, so an isolated measured
    cell yields exactly zero rather than a measurement.

    Args:
        measured: Responses keyed by lattice coordinate, measured cells only.

    Returns:
        The residual per measured cell, with negative zero canonicalised to
        positive zero so a zero residual never hides its sign.
    """
    estimated = backgrounds(measured)
    remaining: dict[tuple[int, int], float] = {}
    for key, response in measured.items():
        value = response - estimated[key]
        if not (value > 0.0 or value < 0.0):
            value = 0.0
        remaining[key] = value
    return remaining

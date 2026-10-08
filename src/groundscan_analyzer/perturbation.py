"""Mask-invariance and the effective amplitude: the guard decided, not measured.

The record answers one question it could previously only wave at: given the
perturbation an operator declared, could any cell have crossed a threshold?
If every finite measured cell's distance to every threshold of every compared
level exceeds the effective amplitude, no cell can cross a threshold, so the
thresholded sets are identical and every derived quantity is identical:
counts, parent map, hierarchy.

The amplitude compared is not the one declared. The anchor rule,
``anchor-rule-v1``, turns the declared amplitude into the compared one: equal
to it under the residual anchor, and its multiple by one plus the background
operator's Lipschitz constant under the payload anchor. That constant is
forced rather than tuned -- shift-equivariance floors it and monotonicity
ceilings it, for the whole class of order-preserving shift-equivariant
operators -- so the payload anchor's bound is exactly double. Under the
residual anchor the constant is never read at all, by branch selection,
which is a different warrant from a quantity cancelling out of an algebra.

A draw perturbs every payload cell at once, so per-input Lipschitz is the
wrong property: it would license a window's width times the amplitude. What
is needed is that a median is monotone and shift-equivariant, hence
1-Lipschitz in the sup norm. Each window median moves by at most ``a``,
their median across windows moves by at most ``a``, and a residual moves by
at most ``|dx| + |dB| <= 2a``. The bound is field-wide and not attributable
to any single cell: it is attained when one cell moves by ``+a`` while its
window median moves by ``-a``.

The criterion is sufficient and not necessary, and not-guaranteed does not
mean unstable: a large share of genuinely invariant fields read
not-guaranteed, because the criterion is conservative. On hierarchy-derived
levels a birth cell sits exactly at its threshold, so the gap is exactly
zero and the record reads not-guaranteed with no special case. Ordering
invariance and magnitude invariance are corollaries, never content: a count
that cannot change cannot reorder. Both hold only for a bounded draw.

Two honest edges. The effective amplitude must be positive: at zero every
gap clears vacuously and the guard would be a guarantee about nothing. And
an unbounded draw leaves the guard silent rather than negative, which is why
an unbounded perturbation withholds rather than reporting failure.

The field perturbation bound and the registration displacement bound are two
distinct terms. The first rides on the background model derived here; the
second rides on the scoring computation behind registration, perturbs
candidate positions rather than a field, and is decided with that check.
One term covering both would let a reader who declared one believe they had
declared the other. Neither substitutes for the other.

Legacy ran perturbations and measured what moved (see, e.g.,
``docs/legacy/groundscan/validation/decomposition_reference.py`` and its
instability zone over declared perturbation families). This guard runs
nothing: it decides from the computation whether anything could have moved.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal, NamedTuple

from groundscan_analyzer.background import LAMBDA

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

__all__ = [
    "CONVENTION",
    "LAMBDA",
    "UNIT_ROUNDOFF",
    "Anchor",
    "Bound",
    "Boundedness",
    "Corollary",
    "GuardReason",
    "GuardResult",
    "GuardStatus",
    "decide",
    "effective_amplitude",
]

CONVENTION: Final[str] = "anchor-rule-v1"

Anchor = Literal["residual", "payload"]

Boundedness = Literal["bounded", "unbounded"]

GuardStatus = Literal["mask-invariant", "not-guaranteed", "not-emitted"]

GuardReason = Literal["requires-bounded-perturbation", "requires-recorded-perturbation-bound"]

Corollary = Literal["holds", "not-established", "withheld"]

UNIT_ROUNDOFF: Final[float] = 2.0**-53


class Bound(NamedTuple):
    """One declared field perturbation bound: amplitude, class and anchor."""

    amplitude: float
    boundedness: Boundedness
    anchor: Anchor


class GuardResult(NamedTuple):
    """The guard decided: its state with both corollaries following it."""

    status: GuardStatus
    reason: GuardReason | None
    ordering_invariance: Corollary
    magnitude_invariance: Corollary


def effective_amplitude(amplitude: float, anchor: Anchor, lipschitz: float = LAMBDA) -> float:
    """Return the amplitude the guard actually compares against.

    Under the residual anchor it is the declared amplitude, and the
    Lipschitz constant is never read. Under the payload anchor it is one
    plus the constant times the declared amplitude, exactly double where
    the constant is forced to one.

    Args:
        amplitude: The declared non-negative amplitude.
        anchor: Whether the residual field or the payload was perturbed.
        lipschitz: The background operator's sup-norm constant, forced to
            one for the whole operator class.

    Returns:
        The effective amplitude, an input to the decision and never a
        recorded figure.
    """
    if anchor == "residual":
        return amplitude
    return (1.0 + lipschitz) * amplitude


def _withheld(reason: GuardReason) -> GuardResult:
    """Return the silent guard: no decision, and no corollary either.

    Args:
        reason: The named withheld state the guard reads.

    Returns:
        The guard with both corollaries withheld beside it.
    """
    return GuardResult(
        status="not-emitted",
        reason=reason,
        ordering_invariance="withheld",
        magnitude_invariance="withheld",
    )


def _clearance(cells: Sequence[float], thresholds: Sequence[float]) -> float:
    """Return the smallest error-adjusted cell-to-threshold distance.

    Each pair contributes its absolute gap with the binary64 subtraction
    error bound subtracted, so an exact tie reads zero or below and only a
    genuine clearance survives. A non-finite gap never becomes the minimum.

    Args:
        cells: The finite measured residuals.
        thresholds: Every threshold of every compared level.

    Returns:
        The minimum remaining clearance, possibly non-finite where no
        finite pair binds.
    """
    smallest = math.inf
    for cell in cells:
        for threshold in thresholds:
            gap = abs(cell - threshold)
            allowed = UNIT_ROUNDOFF * max(abs(cell), abs(threshold))
            remaining = gap - allowed
            smallest = min(smallest, remaining)
    return smallest


def _compared(cells: Sequence[float], thresholds: Sequence[float], effective: float) -> GuardResult:
    """Decide invariance over one set of compared levels.

    With no cell-threshold pair there is nothing to decide, so no
    guarantee is reported. Otherwise the comparison is strict: the
    smallest error-adjusted clearance must exceed the effective amplitude.

    Args:
        cells: The finite measured residuals.
        thresholds: Every threshold of every compared level.
        effective: The positive effective amplitude to clear.

    Returns:
        The invariant record with both corollaries holding, or the
        not-guaranteed record with neither established.
    """
    if not cells or not thresholds:
        return GuardResult(
            status="not-guaranteed",
            reason=None,
            ordering_invariance="not-established",
            magnitude_invariance="not-established",
        )
    if _clearance(cells, thresholds) > effective:
        return GuardResult(
            status="mask-invariant",
            reason=None,
            ordering_invariance="holds",
            magnitude_invariance="holds",
        )
    return GuardResult(
        status="not-guaranteed",
        reason=None,
        ordering_invariance="not-established",
        magnitude_invariance="not-established",
    )


def decide(
    cells: Sequence[float],
    thresholds: Sequence[float],
    bound: Bound | None,
    lipschitz: float = LAMBDA,
) -> GuardResult:
    """Decide the mask-invariance guard from the computation.

    No bound recorded withholds with its own reason; an unbounded draw
    withholds outright rather than reporting failure; a non-positive
    effective amplitude withholds under the bounded-perturbation reason
    rather than guaranteeing nothing. The precondition and the zero bound
    are complementary, not alternatives: the precondition is a positive
    effective amplitude, and the zero bound is what fails it.

    Args:
        cells: The finite measured residuals.
        thresholds: Every threshold of every compared level.
        bound: The declared perturbation bound, or None where nothing
            was recorded.
        lipschitz: The background operator's sup-norm constant, read only
            under the payload anchor.

    Returns:
        The guard with its state and both corollaries.
    """
    if bound is None:
        return _withheld("requires-recorded-perturbation-bound")
    if bound.boundedness == "unbounded":
        return _withheld("requires-bounded-perturbation")
    effective = effective_amplitude(bound.amplitude, bound.anchor, lipschitz)
    if effective <= 0.0:
        return _withheld("requires-bounded-perturbation")
    return _compared(cells, thresholds, effective)

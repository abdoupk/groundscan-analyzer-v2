"""The robust scale: two median-based estimates with their agreement state.

The document reports two independent estimates of the spread and refuses
to commit to either when they disagree. Both target the same quantity, a
Gaussian-equivalent sigma, with factors derived from one shared
calibration constant so the two cannot drift apart. Mean-family
estimators are out because their breakdown point falls below the
contamination fraction they would have to tolerate, and the
contamination is the signal.

The shared blind spot is the point of the record. A run of values
exactly equal to the sample median, heavy enough to outvote it, forces
the median absolute deviation to exactly zero, and every
median-of-medians estimator inherits that, while the interquartile
range, blind to the atom, is non-zero on the same sample. Two estimators
from one family would report agreement on a value that is not the
dispersion. The atom fraction is therefore carried as evidence in its
own right, with an exact numerator, an exact denominator and no
threshold, rather than left to be inferred from two estimates that share
the failure.

Disagreement is a pinned relative quantity, dimensionless and in the
unit interval identically, which is what makes the saturated state
decidable at all. Tolerance is derived per scan from the computation, a
function of the unit roundoff, the support parity and modulus, and the
field own spread-to-magnitude ratio, never a chosen number, catching
exact coincidence and nothing else.

The scale-normalised view is withheld rather than emitted with a warning
nobody is obliged to read. A quantity from a thin sample is emitted,
sufficiency being the consumer judgement. Everything else the engine
emits is scale-free, so one contested spread never removes an answer the
operator can have.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal, NamedTuple

from scipy.special import ndtri

from groundscan_analyzer import background

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

CONVENTION: Final[str] = "scale-agreement-v1"
QUANTILE_CONVENTION: Final[str] = "quantile-v1"

ScaleStatus = Literal[
    "no-finite-residual-values",
    "constant-field",
    "median-atom-zero-scale",
    "tie-tolerance-saturated",
    "tie",
    "disagreement",
]

ScaleViewReason = Literal["scale-not-positive-finite", "scale-not-warranted"]

UNIT_ROUNDOFF: Final[float] = 2.0**-53
TOLERANCE_SLOPE_COUNT: Final[int] = 11
PARITY_MODULUS: Final[int] = 2
QUARTILE_MODULUS: Final[int] = 4
QUARTILE_REMAINDER_TWO: Final[int] = 2
ODD_BASE: Final[float] = 4.0
EVEN_BASE: Final[float] = 5.0
SATURATION_LIMIT: Final[float] = 1.0

Z_75: Final[float] = float(ndtri(0.75))
MAD_FACTOR: Final[float] = 1.0 / Z_75
IQR_DIVISOR: Final[float] = 2.0 * Z_75


class ScaleResult(NamedTuple):
    """One scan residual field reduced to its scale record.

    Both estimates target sigma under the shared calibration, the
    disagreement is the pinned relative form, the tolerance is derived
    per scan, and the atom fraction is exact evidence with no threshold.
    Estimates are None where undefined, which is only the no-finite
    state, since a thin sample is still emitted.
    """

    status: ScaleStatus
    sigma_mad: float | None
    sigma_iqr: float | None
    disagreement: float | None
    tolerance: float | None
    median_atom_numerator: int
    median_atom_denominator: int


class _Computed(NamedTuple):
    """Intermediate values behind the tie-or-disagreement decision."""

    support: int
    median: float
    first: float
    third: float
    mad: float
    iqr: float
    sigma_mad: float
    sigma_iqr: float
    atom_numerator: int


def _is_zero(value: float) -> bool:
    """Report whether a float is exactly zero without an equality test.

    Args:
        value: The finite value to test.

    Returns:
        True for positive or negative zero, False otherwise.
    """
    return not (value > 0.0 or value < 0.0)


def _equals(first: float, second: float) -> bool:
    """Report whether two finite floats are exactly equal.

    Args:
        first: One finite value.
        second: Another finite value.

    Returns:
        True on exact equality, with no tolerance anywhere.
    """
    return not (first > second or first < second)


def _quantile_sorted(ordered: Sequence[float], prob: float) -> float:
    """Return one sample quantile under the pinned linear rule.

    The rule is linear interpolation (type 7): plotting position
    ``(rank - 1) / (count - 1)``, so the extreme order statistics are
    reached without clamping and reflection symmetry holds exactly as a
    mathematical property. A quantile may return a value the sample does
    not contain, which is stated rather than designed away.

    Args:
        ordered: The finite sample in non-decreasing order, at least one.
        prob: The quantile level in the unit interval.

    Returns:
        The interpolated quantile, computed as a convex combination so
        a pair of large finite values cannot overflow where their
        difference would.

    Raises:
        ValueError: When the sample is empty or the level is outside
            the unit interval.
    """
    count = len(ordered)
    if count == 0:
        msg = "quantile needs at least one finite value"
        raise ValueError(msg)
    if not 0.0 <= prob <= 1.0:
        msg = f"quantile level is outside the unit interval: {prob!r}"
        raise ValueError(msg)
    if count == 1:
        return ordered[0]
    position = float(count - 1) * prob
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - float(lower)
    low_value = ordered[lower]
    high_value = ordered[upper]
    return (1.0 - fraction) * low_value + fraction * high_value


def quartiles(values: Sequence[float]) -> tuple[float, float, float]:
    """Return the first quartile, median and third quartile.

    The median reuses the pinned even-support rule, so halving happens
    first and a pair of large finite values cannot overflow where their
    sum would. Quartiles use the pinned linear rule above.

    Args:
        values: The finite residual field, at least one.

    Returns:
        The first quartile, the median and the third quartile.

    Raises:
        ValueError: When called with no values.
    """
    if len(values) == 0:
        msg = "quartiles need at least one finite value"
        raise ValueError(msg)
    ordered = sorted(values)
    median = background.median(list(values))
    first = _quantile_sorted(ordered, 0.25)
    third = _quantile_sorted(ordered, 0.75)
    return first, median, third


def _mad_raw(values: Sequence[float], median: float) -> float:
    """Return the unscaled median absolute deviation.

    Args:
        values: The finite residual field, at least one.
        median: The centring median under the pinned rule.

    Returns:
        The median of absolute deviations, under the same pinned rule.
    """
    return background.median([abs(value - median) for value in values])


def _disagreement_from_raw(mad: float, iqr: float) -> float:
    """Return the pinned relative disagreement from unscaled parts.

    With ``a = mad / Z`` and ``b = iqr / (2 Z)`` the pinned form
    ``|a - b| / max(a, b)`` equals ``|2 mad - iqr| / max(2 mad, iqr)``,
    so the calibration constant cancels by construction and the result
    is exactly invariant to it. It is dimensionless, symmetric, and in
    the unit interval identically: zero where both vanish, one where
    exactly one vanishes, otherwise the relative gap.

    Args:
        mad: The unscaled median absolute deviation, finite.
        iqr: The unscaled interquartile range, finite.

    Returns:
        The disagreement in the unit interval.
    """
    doubled = 2.0 * mad
    if _is_zero(doubled) and _is_zero(iqr):
        return 0.0
    top = abs(doubled - iqr)
    bottom = max(doubled, iqr)
    return top / bottom


def _tolerance(count: int, spread_ratio: float) -> float:
    """Return the derived tie tolerance for one support and ratio.

    The form is ``u (C0 + c1 L/s) / (1 - K u)`` with unit roundoff
    ``u = 2^-53`` and ``K = 11``. ``C0`` is four for odd support and
    five for even, ``c1`` is zero for odd support, ``1 / Z`` where the
    support is two modulo four, and ``2 / Z`` where it is zero modulo
    four. ``L/s`` is the field own spread-to-magnitude ratio, the
    largest absolute value among the centring median and the two
    quartiles over the larger of the two estimates.

    Args:
        count: The finite support, at least one.
        spread_ratio: The ``L/s`` ratio, finite and non-negative.

    Returns:
        The dimensionless tolerance, catching exact coincidence only.
    """
    if count % PARITY_MODULUS == 1:
        base = ODD_BASE
        slope = 0.0
    elif count % QUARTILE_MODULUS == QUARTILE_REMAINDER_TWO:
        base = EVEN_BASE
        slope = 1.0 / Z_75
    else:
        base = EVEN_BASE
        slope = 2.0 / Z_75
    return (
        UNIT_ROUNDOFF
        * (base + slope * spread_ratio)
        / (1.0 - float(TOLERANCE_SLOPE_COUNT) * UNIT_ROUNDOFF)
    )


def _is_constant(values: Sequence[float]) -> bool:
    """Report whether every finite value is exactly equal.

    Args:
        values: The finite residual field, at least one.

    Returns:
        True when all values equal the first, exactly.
    """
    first = values[0]
    return all(_equals(value, first) for value in values)


def _empty_result() -> ScaleResult:
    """Return the no-finite-values record.

    Returns:
        The scale record with undefined estimates and a zero denominator.
    """
    return ScaleResult(
        status="no-finite-residual-values",
        sigma_mad=None,
        sigma_iqr=None,
        disagreement=None,
        tolerance=None,
        median_atom_numerator=0,
        median_atom_denominator=0,
    )


def _constant_result(count: int, atom_numerator: int) -> ScaleResult:
    """Return the constant-field record.

    Args:
        count: The finite support.
        atom_numerator: The exact atom count.

    Returns:
        The scale record with both estimates at zero.
    """
    return ScaleResult(
        status="constant-field",
        sigma_mad=0.0,
        sigma_iqr=0.0,
        disagreement=0.0,
        tolerance=None,
        median_atom_numerator=atom_numerator,
        median_atom_denominator=count,
    )


def _atom_result(
    sigma_iqr: float | None,
    mad: float,
    iqr: float,
    count: int,
    atom_numerator: int,
) -> ScaleResult:
    """Return the median-atom record.

    Args:
        sigma_iqr: The scaled interquartile estimate, possibly None.
        mad: The unscaled median absolute deviation, exactly zero.
        iqr: The unscaled interquartile range.
        count: The finite support.
        atom_numerator: The exact atom count.

    Returns:
        The scale record with a zero median estimate.
    """
    gap = _disagreement_from_raw(mad, iqr) if math.isfinite(iqr) else 1.0
    return ScaleResult(
        status="median-atom-zero-scale",
        sigma_mad=0.0,
        sigma_iqr=sigma_iqr,
        disagreement=gap,
        tolerance=None,
        median_atom_numerator=atom_numerator,
        median_atom_denominator=count,
    )


def _saturated(computed: _Computed, tolerance: float | None, gap: float | None) -> ScaleResult:
    """Return the tolerance-saturated record.

    Args:
        computed: The intermediate values behind the decision.
        tolerance: The derived tolerance, possibly None where undefined.
        gap: The pinned disagreement, possibly None where undefined.

    Returns:
        The scale record with the saturated status.
    """
    return ScaleResult(
        status="tie-tolerance-saturated",
        sigma_mad=computed.sigma_mad,
        sigma_iqr=computed.sigma_iqr,
        disagreement=gap,
        tolerance=tolerance,
        median_atom_numerator=computed.atom_numerator,
        median_atom_denominator=computed.support,
    )


def _decide_tie(computed: _Computed) -> ScaleResult:
    """Decide between saturated, tie and disagreement.

    Args:
        computed: The intermediate values with positive finite estimates.

    Returns:
        The saturated record where the tolerance reaches one or is not
        finite, the tie record where the gap lies within tolerance, and
        the disagreement record otherwise.
    """
    magnitude = max(abs(computed.median), abs(computed.first), abs(computed.third))
    larger = max(computed.sigma_mad, computed.sigma_iqr)
    ratio = magnitude / larger if larger > 0.0 else 0.0
    tolerance = _tolerance(computed.support, ratio)
    gap = _disagreement_from_raw(computed.mad, computed.iqr)
    if not math.isfinite(tolerance) or tolerance >= SATURATION_LIMIT:
        kept = tolerance if math.isfinite(tolerance) else None
        return _saturated(computed, kept, gap)
    if gap <= tolerance:
        return ScaleResult(
            status="tie",
            sigma_mad=computed.sigma_mad,
            sigma_iqr=computed.sigma_iqr,
            disagreement=gap,
            tolerance=tolerance,
            median_atom_numerator=computed.atom_numerator,
            median_atom_denominator=computed.support,
        )
    return ScaleResult(
        status="disagreement",
        sigma_mad=computed.sigma_mad,
        sigma_iqr=computed.sigma_iqr,
        disagreement=gap,
        tolerance=tolerance,
        median_atom_numerator=computed.atom_numerator,
        median_atom_denominator=computed.support,
    )


def _estimate_present(finite: list[float], count: int, atom_numerator: int) -> ScaleResult:
    """Estimate the scale where at least one finite value exists.

    Args:
        finite: The finite residual field.
        count: Its support.
        atom_numerator: The exact atom count.

    Returns:
        The constant record where all values coincide, the atom record
        where the median deviation vanishes, the saturated record where
        an estimate is not finite, and otherwise the tie-or-disagreement
        decision.
    """
    median = background.median(finite)
    if _is_constant(finite):
        return _constant_result(count, atom_numerator)
    mad = _mad_raw(finite, median)
    ordered = sorted(finite)
    first = _quantile_sorted(ordered, 0.25)
    third = _quantile_sorted(ordered, 0.75)
    iqr = third - first
    if _is_zero(mad):
        sigma_iqr = iqr / IQR_DIVISOR if math.isfinite(iqr) else None
        return _atom_result(sigma_iqr, mad, iqr, count, atom_numerator)
    if not math.isfinite(mad) or not math.isfinite(iqr):
        sigma_mad = mad * MAD_FACTOR if math.isfinite(mad) else None
        sigma_iqr = iqr / IQR_DIVISOR if math.isfinite(iqr) else None
        if sigma_mad is None or sigma_iqr is None:
            return ScaleResult(
                status="tie-tolerance-saturated",
                sigma_mad=sigma_mad,
                sigma_iqr=sigma_iqr,
                disagreement=None,
                tolerance=None,
                median_atom_numerator=atom_numerator,
                median_atom_denominator=count,
            )
    sigma_mad = mad * MAD_FACTOR
    sigma_iqr = iqr / IQR_DIVISOR
    computed = _Computed(
        support=count,
        median=median,
        first=first,
        third=third,
        mad=mad,
        iqr=iqr,
        sigma_mad=sigma_mad,
        sigma_iqr=sigma_iqr,
        atom_numerator=atom_numerator,
    )
    return _decide_tie(computed)


def estimate(values: Sequence[float]) -> ScaleResult:
    """Estimate the robust scale of one scan residual field.

    Five precedence levels, the last yielding tie or disagreement: no
    finite residual values, a constant field, a median atom outvoting
    the median, a saturated tolerance, then tie or disagreement. Every
    state records both estimates, and a tie is neither agreement nor
    disagreement. Agreement is asymptotic, never evidence of
    convergence.

    The atom lemma, that the median absolute deviation is zero if and
    only if twice the count of values equal to the sample median
    exceeds the sample size, holds with two named exceptions,
    subnormal underflow and overflow in even-support averaging, both
    stated here rather than left as gaps. The pinned even-support rule,
    halving first, does not reopen it: halving first avoids the
    overflow the lemma excepts, and the subnormal case is an
    underflow of that same halving.

    Args:
        values: The residual field, finite values only; non-finite
            entries are ignored upstream and never reach here.

    Returns:
        The scale record with its status, both estimates, the pinned
        disagreement, the derived tolerance, and the exact atom
        fraction with no threshold.
    """
    finite = [value for value in values if math.isfinite(value)]
    count = len(finite)
    if count == 0:
        return _empty_result()
    median = background.median(finite)
    atom_numerator = sum(1 for value in finite if _equals(value, median))
    return _estimate_present(finite, count, atom_numerator)

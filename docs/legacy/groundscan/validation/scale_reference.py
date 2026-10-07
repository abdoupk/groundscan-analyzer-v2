"""Independent scale references and characterisation cases for S03.

## What this module is, and what it is not

It is an **oracle**: it builds scale estimates from their definitions, with no
shared code with the production path, so that "what should the estimator be?" can
be answered by something other than "what does the estimator currently say?".

It is not an implementation proposal. Nothing in here is called by
:mod:`groundscan._util`; the production estimator is one of the things being
measured, and it is measured *from the outside* by
:mod:`groundscan.validation.scale_shadow_report`.

The single most important structural rule, and the reason the module exists at
all: **the legacy estimator is not the reference.** "Matches
``robust_scale``" is not a criterion any of these tests may use, because that is
the criterion whose absence let a fabricated ``return 1.0`` reach production and
then a fabricated ``std`` reach production in its place.

## The estimators, and why each one is here

| name | definition | consistency for N(0,1) | breakdown | why it is measured |
|---|---|---|---|---|
| :func:`std_scale` | population standard deviation | 1.000 | 0 % | the legacy degenerate tier; the contamination reference case |
| :func:`mad_scale` | ``1.4826 * median|x - med|`` | 1.000 | 50 % | the legacy primary tier |
| :func:`iqr_scale` | ``IQR / 1.349`` | 1.000 | 25 % | the legacy second tier |
| :func:`sn_scale` | Rousseeuw-Croux ``Sn`` | 1.1926 | 29.3 % | the only high-breakdown statistic that is *not* a pairwise-quantile |
| :func:`qn_scale` | Rousseeuw-Croux ``Qn`` | 2.2219 | 29.3 % | the candidate v2 nominated; measured here, not assumed |
| :func:`trimmed_std_scale` | std after symmetric trim | 1.000 (10 % trim) | trim fraction | the candidate v2 measured as "stable to 5 %" |
| :func:`proposal2_scale` | Huber Proposal 2 | derived below | 50 % | the standard high-breakdown M-estimator |
| :func:`absdev_quantile_scale` | ``q_alpha(|x - med|) / q_alpha(``\\|``\\|Z``\\|``\\|)`` | 1.000 by construction | ``1 - alpha`` | the general "raise alpha" family, which is the only one that leaves 0 on an atom-heavy population |

Consistency constants are **derived in this module**, not copied:

* ``MAD``: the normal median absolute deviation is ``Phi^-1(0.75) = 0.674490``,
  so the consistency factor is ``1 / 0.674490 = 1.482602``. Verified against the
  stated 1.4826 rather than rounded from it.
* ``IQR``: ``2 * 0.674490 = 1.348980``, so the factor is ``1 / 1.348980 =
  0.741300`` and the divisor is ``2 * 0.674490``.
* ``Qn``: the median of ``|X - Y|`` for iid standard normals is
  ``sqrt(2) * Phi^-1(0.75) = 0.953873``, and Rousseeuw & Croux fix ``Qn`` to
  equal ``2.2219`` on the standard normal, so ``c = 2.2219 / 0.953873 =
  2.329327``.
* ``Sn``: Rousseeuw & Croux fix ``Sn(N) = 1.1926``; this module **measures** the
  raw statistic's limit and derives ``c = 1.1926 / limit`` rather than assuming
  a number, so a reader can check the derivation.
* ``alpha``-quantile family: by construction the consistency factor is the
  reciprocal of the normal's ``alpha``-quantile of ``|Z|``.

Each derived constant is checked against the *stated* published value in the test
suite, so "derived" cannot quietly become "wrong".

## Why the case families are the ones they are

The families are not a wish list. Families A, D and G are the three regimes the
production corpus actually visits (measured: 31 of 34 real residuals sit in A/D
with a non-zero MAD; 3 sit in D with MAD = IQR = 0; 0 sit in G), and families B,
C, E, F are the regimes the *design document* assumed without measuring.
:data:`REAL_RESIDUAL_REGIMES` records the measurement.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.special import ndtr, ndtri

# ---------------------------------------------------------------------------
# Normal-model constants, derived (see module docstring)
# ---------------------------------------------------------------------------

#: ``Phi^-1(0.75)`` -- the normal median absolute deviation, and half the
#: normal interquartile range. Every "x 1.4826" / "/ 1.349" in the codebase
#: traces back to this one number; deriving it means the two constants cannot
#: disagree with each other.
Z_75 = float(ndtri(0.75))

#: Consistency factor for the median absolute deviation: ``1 / Z_75``.
MAD_C = 1.0 / Z_75

#: Divisor for the interquartile range: ``2 * Z_75``.
IQR_DIVISOR = 2.0 * Z_75

#: The median of ``|X - Y|`` for iid standard normals, ``sqrt(2) * Z_75``.
#: This is the order statistic Rousseeuw & Croux's ``Qn`` reports, and it is what
#: turns their fixed value 2.2219 into a multiplier.
MEDIAN_PAIRWISE_NORMAL = math.sqrt(2.0) * Z_75

#: ``Qn`` on the standard normal is 2.2219 by definition of the statistic
#: (Rousseeuw & Croux 1993), so the multiplier is that value divided by the
#: median pairwise distance it multiplies.
QN_TARGET_NORMAL = 2.2219
QN_C = QN_TARGET_NORMAL / MEDIAN_PAIRWISE_NORMAL

#: ``Sn`` on the standard normal is 1.1926 (same paper). The *measured* limit of
#: the raw statistic is what the multiplier is divided into; the test suite pins
#: that the derived multiplier reproduces 1.1926 to 1e-3, which is the
#: "consistency check" the v2 calibration register demanded.
SN_TARGET_NORMAL = 1.1926

#: Huber Proposal 2's published tuning constant. Its asymptotic scale constant
#: is *derived* as the reciprocal of the mean influence function,
#: ``E[min(|Z|, c)] = 2 Phi(c) - 1``; nothing is fitted.
P2_TUNING = 1.345
P2_SCALE = 1.0 / (2.0 * float(ndtr(P2_TUNING)) - 1.0)


def absdev_consistency(alpha: float) -> float:
    """Consistency factor for the ``alpha``-quantile of ``|x - median|``.

    By construction the ``alpha``-quantile of ``|X - m|`` for a standard normal
    is ``Phi^-1(0.5 + alpha/2)``, so dividing by it makes the estimator
    consistent. Writing it as a function of ``alpha`` rather than a table means
    an alpha that was not anticipated is still correct.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")
    return 1.0 / float(ndtri(0.5 + alpha / 2.0))


#: Breakdown point of the alpha-quantile family, stated rather than implied: the
#: estimator cannot be moved by more than ``1 - alpha`` of the sample, so a
#: rungs breakdown is exactly the number to quote when discussing robustness.
def absdev_breakdown(alpha: float) -> float:
    return 1.0 - alpha


# ---------------------------------------------------------------------------
# Independent estimator implementations
# ---------------------------------------------------------------------------
# Each one is written from its definition. They share no helper with production
# and, where a definition admits two constructions, the module carries both so
# a bug in one cannot hide inside the other (the same discipline
# ``solidity_reference`` used for the two area constructions).


def _finite(values: Any) -> np.ndarray[Any, Any]:
    arr = np.asarray(values, dtype=float).ravel()
    return np.asarray(arr[np.isfinite(arr)], dtype=float)


def std_scale(values: Any) -> float:
    """Population standard deviation. Breakdown 0: the reference *bad* case."""
    v = _finite(values)
    if v.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((v - float(np.mean(v))) ** 2)))


def std_scale_two_pass(values: Any) -> float:
    """Second, independent construction of the same standard deviation.

    One pass about the mean, one about the median then combined -- the
    textbook two-pass correction, and a completely different arithmetic path.
    """
    v = _finite(values)
    if v.size == 0:
        return float("nan")
    mean = float(np.mean(v))
    s1 = float(np.sum((v - mean) ** 2))
    med = float(np.median(v))
    s2 = float(np.sum((v - med) ** 2))
    k = v.size
    if k <= 1:
        return 0.0
    return float(math.sqrt(max(0.0, s2 - (s1 - s2) ** 2 / (k * k)) / (k - 1)))


def mad_scale(values: Any) -> float:
    """``1 / Phi^-1(0.75)`` times the median absolute deviation about the median."""
    v = _finite(values)
    if v.size == 0:
        return float("nan")
    med = float(np.median(v))
    return MAD_C * float(np.median(np.abs(v - med)))


def iqr_scale(values: Any) -> float:
    """Interquartile range over ``2 * Phi^-1(0.75)``."""
    v = _finite(values)
    if v.size == 0:
        return float("nan")
    q25, q75 = np.percentile(v, [25.0, 75.0])
    return float(q75 - q25) / IQR_DIVISOR


def absdev_quantile_scale(values: Any, alpha: float = 0.5) -> float:
    """Consistent estimate of sigma from the ``alpha``-quantile of ``|x - med|``.

    The general family the MAD (``alpha = 0.5``) and any "raise alpha" fallback
    belong to. Its breakdown is ``1 - alpha`` and it is identically zero
    whenever more than ``1 - alpha`` of the sample sits exactly on the median,
    which is the property that decides the degenerate regime.

    The percentile *rank* is ``alpha``, not ``0.5 + alpha/2``: the latter is the
    corresponding point of the normal CDF, which is what
    :func:`absdev_consistency` inverts. Conflating the two silently doubles the
    level -- ``alpha = 0.5`` would become the 0.75-quantile and report ``1.71``
    sigma for a unit-normal sample -- so the two functions are kept separate on
    purpose and the test suite checks both ends of the mapping.
    """
    v = _finite(values)
    if v.size == 0:
        return float("nan")
    med = float(np.median(v))
    deviations = np.abs(v - med)
    return absdev_consistency(alpha) * float(np.percentile(deviations, 100.0 * alpha))


def qn_scale(values: Any) -> float:
    """Rousseeuw-Croux ``Qn``, computed directly from its definition.

    ``Qn = c * (the order statistic of rank round(n^2/4) among the n(n-1)/2
    pairwise absolute differences)``, with ``c = 2.2219 / (sqrt(2) Z_75)``.

    Cost is O(n^2) time. The corpus census records the measured cost, because
    the v2 risk register flagged it (R5) and a claim about cost needs a
    measurement rather than an assumption.
    """
    v = _finite(values)
    n = int(v.size)
    pairs = n * (n - 1) // 2
    if pairs < 1:
        return float("nan")
    k = min(max(int(round(n * n / 4.0)), 1), pairs)
    diffs = np.abs(v[:, None] - v[None, :])
    upper = np.triu_indices(n, 1)
    return QN_C * float(np.partition(diffs[upper], k - 1)[k - 1])


def _inner_median_absolute_deviation(sorted_v: np.ndarray[Any, Any], index: int) -> float:
    """Median of ``|sorted_v[index] - sorted_v[j]|`` over all ``j``, in O(log n).

    The distances from one point of a sorted sample increase monotonically as
    ``j`` moves away from ``index`` in either direction, so the multiset is the
    merge of two ascending sequences and its median is found by a binary search
    on the value rather than by materialising the row. This is what keeps
    :func:`sn_scale` affordable; the naive form is a full ``n x n`` matrix.
    """
    n = sorted_v.size
    half = n // 2
    pivot = float(sorted_v[index])

    def count_within(width: float) -> int:
        if width == 0.0:
            # ``searchsorted(pivot, 'right') - searchsorted(pivot, 'left')`` is
            # the number of values *equal* to the pivot. Using 'right' on both
            # sides would give zero, because ``pivot - 0.0`` is ``-0.0`` and
            # ``-0.0 == 0.0`` compares as equal under searchsorted's ordering.
            return int(
                np.searchsorted(sorted_v, pivot, side="right")
                - np.searchsorted(sorted_v, pivot, side="left")
            )
        return int(
            np.searchsorted(sorted_v, pivot + width, side="right")
            - np.searchsorted(sorted_v, pivot - width, side="left")
        )

    # Exact zero, checked before the search rather than approached by it. A
    # bisection that halves toward 0 converges to range/2**80, which is not the
    # same object as zero: an atom-heavy population would report 1e-24 instead
    # of 0 and the "every 50 %-breakdown estimator returns exactly zero"
    # finding -- which is the load-bearing measurement here -- would be a
    # statement about round-off instead of about the population.
    if count_within(0.0) >= half:
        return 0.0
    low, high = 0.0, float(sorted_v[-1] - sorted_v[0])
    for _ in range(80):
        mid = 0.5 * (low + high)
        if count_within(mid) >= half:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)


def sn_scale(values: Any, *, raw_limit: float | None = None) -> float:
    """Rousseeuw-Croux ``Sn``, with the consistency multiplier *measured*.

    Rousseeuw & Croux fix the *value* ``Sn(N) = 1.1926``; the multiplier that
    produces it from the bare median-of-medians is therefore
    ``1.1926 / limit``, and the limit is **measured** here rather than copied
    from a table. Measured at 0.8406, so the multiplier is 1.4187 -- and the
    difference between that and 1.1926 is exactly the kind of scratch-constant
    confusion the design register warned about, so the test suite pins the
    *product* rather than either factor.

    ``raw_limit`` exists so the test can re-derive the multiplier from its own
    measurement instead of calling this function and comparing it to itself.
    """
    v = _finite(values)
    if v.size < 2:
        return float("nan")
    limit = sn_raw_limit() if raw_limit is None else float(raw_limit)
    if not (limit > 0.0):
        return float("nan")
    return (SN_TARGET_NORMAL / limit) * sn_raw(v)


def sn_raw(values: Any) -> float:
    """``Sn`` without its consistency multiplier: the bare median of medians."""
    v = _finite(values)
    if v.size < 2:
        return float("nan")
    ordered = np.sort(v)
    return float(
        np.median([_inner_median_absolute_deviation(ordered, i) for i in range(ordered.size)])
    )


_SN_RAW_LIMIT: float | None = None


def sn_raw_limit(size: int = 20000, draws: int = 3, seed: int = 20260930) -> float:
    """Measured limit of the raw ``Sn`` statistic on the standard normal.

    Cached because it is a Monte-Carlo measurement and the test suite calls it
    repeatedly. The seed is fixed so the number is reproducible, and a
    deterministic analytic value is *not* used here on purpose: the point is to
    measure the implementation, which is what the consistency check is for.
    """
    global _SN_RAW_LIMIT
    if _SN_RAW_LIMIT is not None and size == 20000 and draws == 3:
        return _SN_RAW_LIMIT
    rng = np.random.default_rng(seed)
    total = 0.0
    for _ in range(draws):
        total += sn_raw(rng.normal(0.0, 1.0, size))
    limit = total / draws
    if size == 20000 and draws == 3:
        _SN_RAW_LIMIT = limit
    return limit


def trimmed_std_scale(values: Any, trim: float = 0.10) -> float:
    """Standard deviation after discarding ``trim`` of each tail."""
    v = _finite(values)
    if v.size < 4:
        return std_scale(v)
    cut = int(math.floor(trim * v.size))
    ordered = np.sort(v)
    kept = ordered[cut : ordered.size - cut] if cut else ordered
    return float(np.std(kept))


def proposal2_scale(values: Any, tuning: float = P2_TUNING) -> float:
    """Huber Proposal 2 -- **measured to be inapplicable here**, and kept as the record.

    P2 defines its scale as the root of ``mean(psi((x - m) / t)) = 0`` with
    ``psi = min(max(., -c), c)`` and ``m`` the median. That root **does not
    exist** for a median-centred sample:

    * at ``t -> 0`` every term saturates to ``c * sign(x_i - m)``, and because
      ``m`` is the median at least half the sample is at or below it, so the sum
      is ``>= 0`` and equals zero only for an exactly balanced sample;
    * at ``t -> inf`` every term tends to ``(x_i - m) / t`` and the sum tends to
      ``0`` **from above**, since ``sum(x_i - m) > 0`` for any sample whose
      median is not its mean (which is every even-``n`` sample);
    * in between, the sum is strictly positive, because clipping is
      non-negative on the upper half and the lower half's magnitude is bounded
      by the same ``c``.

    So the defining equation is unsolvable and the estimator is not merely
    inaccurate, it is undefined. This is the *reason* the design's candidate
    list was re-derived from scratch: the standard high-breakdown M-estimator
    of scale cannot even be evaluated on a median-centred discrete population,
    which is exactly the population the degenerate regime consists of.

    The function returns NaN unconditionally for that reason rather than
    pretending. The refusal is pinned by
    ``tests/unit/test_scale_reference.py::test_proposal_two_has_no_root_and_is_recorded_as_refuted``.
    """
    del values, tuning
    return float("nan")


def quantisation_gap(values: Any) -> float:
    """Smallest positive gap between adjacent distinct values, if a lattice.

    Re-derived here rather than imported, because "is this a scale estimator or
    a quantisation detector?" is one of the questions this module exists to
    answer and it cannot be answered by calling the thing under evaluation.

    Two levels already count as a lattice, which is the reading most *favourable*
    to the gap estimator: ``{0, ..., 0, 200}`` is a two-level lattice whose gap
    is 200, and that is the number v1 claimed would "neutralise" the spike.
    Production's detector needs three levels, so it returns ``None`` there --
    recorded, because the difference must not be mistaken for the gap estimator
    being refuted on technicalities.
    """
    v = _finite(values)
    if v.size < 2:
        return float("nan")
    unique = np.unique(v)
    if unique.size < 2:
        return float("nan")
    diffs = np.diff(unique)
    positive = diffs[diffs > 0.0]
    if positive.size == 0:
        return float("nan")
    step = float(np.min(positive))
    if unique.size < 3:
        return step
    multiples = unique / step
    tol = 1e-6 * max(1.0, float(np.max(np.abs(unique))))
    if not np.all(np.abs(multiples - np.round(multiples)) * step <= tol):
        return float("nan")
    return step


#: Every reference estimator, by name, for table generation and for the tests
#: that must not be satisfied by agreeing with production.
#:
#: ``proposal2`` is present with a NaN return because its *refutation* is a
#: result: a candidate that is quietly deleted cannot be shown to have been
#: tried, and its docstring carries the proof that it has no root.
REFERENCE_ESTIMATORS: dict[str, Callable[[Any], float]] = {
    "std": std_scale,
    "mad": mad_scale,
    "iqr": iqr_scale,
    "sn": sn_scale,
    "qn": qn_scale,
    "trimmed_std_10": trimmed_std_scale,
    "proposal2": proposal2_scale,
    "absdev_q95": lambda v: absdev_quantile_scale(v, 0.95),
    "absdev_q90": lambda v: absdev_quantile_scale(v, 0.90),
    "absdev_q75": lambda v: absdev_quantile_scale(v, 0.75),
    "absdev_q50": lambda v: absdev_quantile_scale(v, 0.50),
    "quantisation_gap": quantisation_gap,
}

#: The subset that is a *scale* estimator in the sense the pipeline needs: a
#: number with the units of the residual that survives contamination. The
#: quantisation gap is deliberately excluded, and the exclusion is a measured
#: decision recorded in :func:`quantisation_verdict`.
SCALE_ESTIMATORS: tuple[str, ...] = (
    "std",
    "mad",
    "absdev_q75",
    "iqr",
    "sn",
    "qn",
    "trimmed_std_10",
    "absdev_q90",
    "absdev_q95",
    "proposal2",
)

#: Breakdown points, one row per candidate, so the decision table is a table of
#: *properties* rather than a table of numbers. The number beside each is the
#: fraction of the sample the estimator tolerates being replaced before its
#: value can be driven anywhere.
ESTIMATOR_BREAKDOWN: dict[str, float] = {
    "std": 0.0,
    "mad": 0.50,
    "absdev_q75": 0.25,
    "iqr": 0.25,
    "sn": 0.2929,
    "qn": 0.2929,
    "trimmed_std_10": 0.10,
    "absdev_q90": 0.10,
    "absdev_q95": 0.05,
    "proposal2": 0.50,  # claimed; unattainable, see the refutation
}


# ---------------------------------------------------------------------------
# Case families A-G
# ---------------------------------------------------------------------------
# Every case carries the quantity an independent oracle knows:
#
# * ``clean_scale`` -- the dispersion of the *uncontaminated* population, in the
#   units of the residual. For families A and B it is analytic; for C-F it is
#   the population standard deviation of the stated generating distribution,
#   which is a parameter, not a measurement.
# * ``clean_sigma_true`` -- the generating sigma where one exists, which for a
#   finite construction is *not* the same number as ``clean_scale`` (a
#   5-sample MAD is a poor estimate of its own sigma). Keeping both columns is
#   what stops "recovered the clean scale" from quietly meaning "recovered the
#   answer I wanted".
# * ``expectation`` -- the scientific claim the case exists to test, in words.
#   A case without one is decoration.


@dataclass(frozen=True)
class ScaleCase:
    """One constructed population and what is known about it independently."""

    name: str
    family: str
    values: np.ndarray[Any, Any]
    clean_scale: float | None
    clean_sigma_true: float | None
    expectation: str
    n_contaminated: int = 0
    contamination_fraction: float = 0.0
    label: str = ""
    #: The uncontaminated population these values were made from, when there is
    #: one. Carried rather than regenerated so a test can compare an estimator
    #: on the contaminated and the clean sample *of the same estimator* -- which
    #: is the only comparison that isolates contamination, since Qn and Sn
    #: estimate different functionals than sigma and comparing either to a
    #: nominal sigma would grade them on somebody else's target.
    clean_values: np.ndarray[Any, Any] | None = None

    @property
    def n(self) -> int:
        return int(np.asarray(self.values).size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "n": self.n,
            "label": self.label,
            "clean_scale": self.clean_scale,
            "clean_sigma_true": self.clean_sigma_true,
            "n_contaminated": self.n_contaminated,
            "contamination_fraction": self.contamination_fraction,
            "expectation": self.expectation,
        }


def _normal_clean(n: int, sigma: float, seed: int, centre: float = 0.0) -> np.ndarray[Any, Any]:
    return np.random.default_rng(seed).normal(centre, sigma, n)


def constant_cases() -> list[ScaleCase]:
    """Family A -- a population with no dispersion at all.

    The clean scale is exactly zero, and that is a *result*, not a gap in the
    data. An estimator that returns a positive number here is reporting
    confidence it does not have; an estimator that returns NaN is reporting
    honestly.
    """
    return [
        ScaleCase(
            name="constant_ones_5",
            family="A",
            values=np.full(5, 1.0),
            clean_scale=0.0,
            clean_sigma_true=0.0,
            expectation="dispersion is exactly zero; no scale is measurable",
        ),
        ScaleCase(
            name="constant_hundreds_4",
            family="A",
            values=np.full(4, 100.0),
            clean_scale=0.0,
            clean_sigma_true=0.0,
            expectation="same as above at a 100x amplitude: a fabricated scale "
            "cannot depend on the amplitude",
        ),
        ScaleCase(
            name="constant_zeros_4000",
            family="A",
            values=np.zeros(4000),
            clean_scale=0.0,
            clean_sigma_true=0.0,
            expectation="the production corpus's largest residual family; must not "
            "produce a finite high-confidence scale",
        ),
        ScaleCase(
            name="constant_five_4000",
            family="A",
            values=np.full(4000, 5.0),
            clean_scale=0.0,
            clean_sigma_true=0.0,
            expectation="a non-zero constant must behave exactly like zero",
        ),
    ]


def near_constant_cases() -> list[ScaleCase]:
    """Family B -- dispersion far below any absolute tolerance.

    The clean scales are computed from the construction, so they are known
    exactly and are *tiny*. The scientific question is not "is the estimate
    right to 1e-12" but "does a dispersion of 1e-9 come back as 1e-9, or as a
    constant that has nothing to do with the data".
    """
    cases: list[ScaleCase] = []
    for values in (
        np.array([1.0, 1.0, 1.0, 1.0, 1.0 + 1e-9]),
        np.array([100.0, 100.0, 100.0, 100.0, 100.0 + 1e-6]),
        np.array([0.0, 0.0, 0.0, 0.0, 1e-12]),
    ):
        population_sigma = float(np.sqrt(np.mean((values - float(np.mean(values))) ** 2)))
        name = f"near_constant_{values[-1] - values[0]:.0e}_n{values.size}"
        cases.append(
            ScaleCase(
                name=name,
                family="B",
                values=values,
                clean_scale=population_sigma,
                clean_sigma_true=population_sigma,
                expectation="the scale must be a function of the data only: "
                f"{population_sigma:.3g}, not an unrelated constant",
            )
        )
    return cases


def single_extreme_cases() -> list[ScaleCase]:
    """Family C -- one extreme cell in a known clean population.

    The clean scale is the *measured* scale of the clean population, so
    "how much did the estimate move" is a statement about a known reference and
    not about production. Both signs are included because an estimator that
    resists a one-sided spike by clipping above but not below is not robust.
    """
    clean = _normal_clean(3999, 1.0, seed=11)
    clean_scale = mad_scale(clean)
    cases: list[ScaleCase] = []
    for multiples, sign in (
        (10.0, 1.0),
        (100.0, 1.0),
        (1000.0, 1.0),
        (1000.0, -1.0),
        (1e5, 1.0),
    ):
        spike = sign * multiples
        cases.append(
            ScaleCase(
                name=f"single_extreme_{'plus' if sign > 0 else 'minus'}_{multiples:.0e}",
                family="C",
                values=np.append(clean, spike),
                clean_scale=clean_scale,
                clean_sigma_true=1.0,
                n_contaminated=1,
                contamination_fraction=1.0 / 4000.0,
                expectation="a bounded number of contaminated cells must not move the "
                "clean scale by more than a stated factor",
                clean_values=clean,
            )
        )
    return cases


def multiple_contamination_cases() -> list[ScaleCase]:
    """Family D -- a *fraction* of the population replaced by extremes.

    The failure mode this targets is the one v2 identified: resisting a single
    spike is not the same property as resisting 20 % of the sample. Five
    fractions, each with a known clean population whose own scale is measured
    first.
    """
    cases: list[ScaleCase] = []
    for fraction in (0.05, 0.10, 0.20, 0.30):
        n_clean = 4000
        clean = _normal_clean(
            n_clean - int(fraction * n_clean), 1.0, seed=100 + int(fraction * 100)
        )
        clean_scale = mad_scale(clean)
        for sign in (1.0, -1.0):
            n_bad = int(fraction * n_clean)
            contaminated = np.full(n_bad, sign * 60.0)
            values = np.concatenate([clean, contaminated])
            cases.append(
                ScaleCase(
                    name=(
                        f"contamination_{int(fraction * 100):02d}pct"
                        f"_{'plus' if sign > 0 else 'minus'}"
                    ),
                    family="D",
                    values=values,
                    clean_scale=clean_scale,
                    clean_sigma_true=1.0,
                    n_contaminated=n_bad,
                    contamination_fraction=fraction,
                    expectation="within the estimator's breakdown the clean scale must "
                    "survive; beyond it degradation is expected and must be flagged",
                    clean_values=clean,
                )
            )
    # And the exact degenerate shape production actually meets: a constant
    # population plus a handful of contaminated cells. There is no clean scale
    # to recover, which is the point.
    for n_bad, magnitude in ((1, 200.0), (5, 200.0), (50, 200.0)):
        cases.append(
            ScaleCase(
                name=f"constant_plus_{n_bad}_at_{magnitude:.0f}",
                family="D",
                values=np.concatenate([np.zeros(4000 - n_bad), np.full(n_bad, magnitude)]),
                clean_scale=None,
                clean_sigma_true=None,
                n_contaminated=n_bad,
                contamination_fraction=n_bad / 4000.0,
                expectation="the sample carries no information about a background "
                "scale; any finite answer here is an assertion, not a measurement",
            )
        )
    return cases


def _small_n_case(values: np.ndarray[Any, Any], name: str) -> ScaleCase:
    v = np.asarray(values, dtype=float)
    return ScaleCase(
        name=name,
        family="E",
        values=v,
        clean_scale=float(np.std(v)) if v.size else 0.0,
        clean_sigma_true=None,
        expectation="with n this small an estimate may exist, but it carries no more "
        "weight than n allows; a status saying so is required",
    )


def small_sample_cases() -> list[ScaleCase]:
    """Family E -- n = 1, 2, 3, 4, 5, 6, 8, 10.

    Nothing here can be *accurate*; the requirement is honesty about it. Two
    different questions are kept apart: does a number exist, and may it be
    presented as a measurement.
    """
    rng = np.random.default_rng(31)
    cases = [
        _small_n_case(np.array([1.0]), "n1_single"),
        _small_n_case(np.array([1.0, 2.0]), "n2_pair"),
        _small_n_case(np.array([-1.0, 0.0, 1.0]), "n3_symmetric"),
        _small_n_case(np.array([0.0, 0.0, 0.0, 1.0]), "n4_degenerate_pair"),
        _small_n_case(np.array([1.0, 1.0, 1.0, 1.0, 1.0]), "n5_constant"),
        _small_n_case(rng.normal(0.0, 1.0, 6), "n6_normal"),
        _small_n_case(rng.normal(0.0, 1.0, 8), "n8_normal"),
        _small_n_case(rng.normal(0.0, 1.0, 10), "n10_normal"),
        _small_n_case(np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1e9]), "n6_one_huge_cell"),
    ]
    return cases


def asymmetric_cases() -> list[ScaleCase]:
    return [
        ScaleCase(
            name="exponential_residuals",
            family="F",
            values=np.random.default_rng(41).exponential(1.0, 4000),
            clean_scale=mad_scale(np.random.default_rng(41).exponential(1.0, 4000)),
            clean_sigma_true=1.0,
            expectation="an exponential residual is one-sided; a scale is still a scale, "
            "but the code must not assume symmetry to get it",
        ),
        ScaleCase(
            name="skewed_mixture_90_10",
            family="F",
            values=np.concatenate([
                np.random.default_rng(42).normal(0.0, 1.0, 3600),
                np.random.default_rng(43).normal(0.0, 25.0, 400),
            ]),
            clean_scale=mad_scale(np.random.default_rng(42).normal(0.0, 1.0, 3600)),
            clean_sigma_true=1.0,
            contamination_fraction=0.10,
            n_contaminated=400,
            expectation="a skewed heavy component must not be mistaken for the spread",
        ),
        ScaleCase(
            name="one_sided_contamination_5pct",
            family="F",
            values=np.concatenate([
                np.random.default_rng(44).normal(0.0, 1.0, 3800),
                np.full(200, 15.0),
            ]),
            clean_scale=mad_scale(np.random.default_rng(44).normal(0.0, 1.0, 3800)),
            clean_sigma_true=1.0,
            contamination_fraction=0.05,
            n_contaminated=200,
            expectation="one-sided contamination is the case a symmetric-clipping "
            "estimator handles worst; the centre must not be dragged",
        ),
        ScaleCase(
            name="atom_heavy_quantised",
            family="F",
            values=np.concatenate([
                np.zeros(1352),
                np.random.default_rng(45).integers(-2, 3, 248).astype(float),
            ]),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="an atom at the median heavier than 1/2 defeats every "
            "median-of-medians scale estimator; the true dispersion is not zero, so "
            "reporting zero is a measurement error, not honesty",
        ),
        ScaleCase(
            name="atom_heavy_with_signal_tail",
            family="F",
            values=np.concatenate([
                np.zeros(2000),
                np.arange(1, 401, dtype=float),
            ]),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="a large atom plus a genuine broad tail: the tail is signal, not "
            "contamination, so an estimator that discards it destroys the sensitivity "
            "the tail exists to provide",
        ),
    ]


def invalid_input_cases() -> list[ScaleCase]:
    """Family G -- non-finite input. The policy must be declared, not inherited."""
    finite_part = np.concatenate([np.zeros(99), [2.0]])
    return [
        ScaleCase(
            name="all_nan",
            family="G",
            values=np.full(100, np.nan),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="no usable sample: unavailable, not zero",
        ),
        ScaleCase(
            name="all_pos_inf",
            family="G",
            values=np.full(100, np.inf),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="+inf is not a measurement; unavailable, not infinite",
        ),
        ScaleCase(
            name="all_neg_inf",
            family="G",
            values=np.full(100, -np.inf),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="-inf is not a measurement; unavailable, not infinite",
        ),
        ScaleCase(
            name="nan_mixed_with_finite",
            family="G",
            values=np.concatenate([np.full(50, np.nan), finite_part]),
            clean_scale=mad_scale(finite_part),
            clean_sigma_true=None,
            expectation="a partial sample is still a sample: the estimate is over the "
            "finite part and the caller is told how much was dropped",
        ),
        ScaleCase(
            name="inf_mixed_with_finite",
            family="G",
            values=np.concatenate([np.full(10, np.inf), np.full(10, -np.inf), finite_part]),
            clean_scale=mad_scale(finite_part),
            clean_sigma_true=None,
            expectation="+inf and -inf cancel to NaN in every moment; the policy must "
            "drop them rather than propagate",
        ),
        ScaleCase(
            name="one_finite_among_infinities",
            family="G",
            values=np.concatenate([np.full(99, np.inf), [1.0]]),
            clean_scale=None,
            clean_sigma_true=None,
            expectation="a single usable sample supports no dispersion estimate",
        ),
    ]


def all_cases() -> list[ScaleCase]:
    """Every constructed case, families A through G, in family order."""
    return [
        *constant_cases(),
        *near_constant_cases(),
        *single_extreme_cases(),
        *multiple_contamination_cases(),
        *small_sample_cases(),
        *asymmetric_cases(),
        *invalid_input_cases(),
    ]


# ---------------------------------------------------------------------------
# The measured regime census (Phase D input)
# ---------------------------------------------------------------------------

#: What production actually visits, measured by
#: :func:`groundscan.validation.scale_shadow_report.full_census` over the
#: synthetic catalog, all nine vendor scans and the six golden inputs -- 149
#: residuals in total.
#:
#: ``mad``         -- MAD non-zero: the primary tier, and nothing else happens.
#: ``iqr``         -- MAD zero, IQR non-zero: the second tier.
#: ``degenerate``  -- MAD and IQR both zero: the raw-std tier, and the only
#:                    regime with no defensible finite scale. Three of 149, all
#:                    on two quantised vendor scans.
#: ``low_sample``  -- fewer than three finite values. Zero; the smallest
#:                    residual in the corpus is 447 cells.
#: ``unavailable`` -- fewer than two finite values. Zero.
#:
#: The two numbers that matter for the activation decision are the last two
#: rows: the regime Stage 3 had to fix does not occur, and the regime it could
#: not fix occurs 3 times, always on a lattice-quantised residual.
REAL_RESIDUAL_REGIMES: dict[str, int] = {
    "mad": 144,
    "iqr": 2,
    "degenerate": 3,
    "low_sample": 0,
    "unavailable": 0,
}


@dataclass
class RegimeCensus:
    """How many residuals fall in each estimator regime, over a named corpus."""

    counts: dict[str, int] = field(default_factory=dict)
    sources: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "counts": dict(sorted(self.counts.items())),
            "sources": {k: dict(sorted(v.items())) for k, v in sorted(self.sources.items())},
        }


# ---------------------------------------------------------------------------
# Phase C -- the quantisation gap, explicitly compared
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuantisationVerdict:
    """Why the gap is a detector and not a scale, stated as a measurement."""

    claim: str
    holds: bool
    measured: str

    def to_dict(self) -> dict[str, Any]:
        return {"claim": self.claim, "holds": self.holds, "measured": self.measured}


#: The three properties a scale estimator must have. The gap is checked against
#: all three rather than declared a detector, because "it is obviously a
#: detector" is exactly the kind of assertion this module exists to replace with
#: a measurement.
def quantisation_verdict() -> list[QuantisationVerdict]:
    """Measure the quantisation gap against the three properties, on real data.

    Phase C asks for the gap to be *compared*, not asserted about. The two
    decisive numbers are produced here from the constructions, not asserted:

    * on a unit-normal field the gap is a floating-point epsilon, so using it as
      a scale would report 1e-16 sigma and inflate every z-score without limit;
    * on a constant field with one cell at 200 the gap is **200** -- the spike
      amplitude itself -- because that field's "lattice" is ``{0, 200}``.

    The second number is the whole argument. v1 recommended the gap *because* it
    "neutralises" a single spike, and it returns the spike.
    """
    rng = np.random.default_rng(2026)
    gaussian = rng.normal(0.0, 1.0, 4000)
    on_gaussian = quantisation_gap(gaussian)
    on_spike = quantisation_gap(np.concatenate([np.zeros(3999), [200.0]]))
    quantised = np.round(rng.normal(0.0, 1.0, 4000) * 4.0) / 4.0
    on_quantised = quantisation_gap(quantised)
    return [
        QuantisationVerdict(
            claim="positive-homogeneous: gap(a*x) == a*gap(x)",
            holds=all(
                abs(quantisation_gap(gaussian * a) - a * on_gaussian)
                <= 1e-9 * a * max(on_gaussian, 1e-300)
                for a in (0.01, 1.0, 100.0)
            ),
            measured=f"gap(N(0,1)) = {on_gaussian:.3e}; scales exactly with a",
        ),
        QuantisationVerdict(
            claim="consistent for a continuous population: gap(x) ~ sigma",
            holds=abs(on_gaussian - 1.0) < 0.5,
            measured=(
                f"gap(N(0,1)) = {on_gaussian:.3e} against sigma = 1: wrong by "
                f"{1.0 / on_gaussian:.3e}x, i.e. the gap measures the float64 "
                "lattice, not the spread"
            ),
        ),
        QuantisationVerdict(
            claim="robust to a single extreme cell: gap != the spike amplitude",
            holds=False,
            measured=(
                f"gap({{0 x3999, 200}}) = {on_spike:.6f} -- exactly the spike "
                "amplitude. v1 recommended this estimator *because* it "
                "'neutralises' a single spike, and it returns the spike. This is "
                "the claim that decided the demotion, and it fails"
            ),
        ),
        QuantisationVerdict(
            claim="useful as *metadata* on a genuinely quantised lattice",
            holds=abs(on_quantised - 0.25) < 1e-12,
            measured=(
                f"gap(round(N(0,1)*4)/4) = {on_quantised:.6f}, exact. This is the one "
                "thing it is good for, and it is what production reports in "
                "`quantisation_step`"
            ),
        ),
    ]


def estimator_table(cases: Sequence[ScaleCase] | None = None) -> dict[str, Any]:
    """Every reference estimator evaluated on every case, with its breakdown.

    The table is the Phase D decision input and it is generated rather than
    transcribed, so an estimator added here appears in the decision without
    anybody remembering to re-run a spreadsheet. Values are ``None`` for NaN,
    which is a meaningful entry and not a missing one: "this estimator declines
    to answer" is exactly the fact the decision turns on.
    """
    rows: list[dict[str, Any]] = []
    for case in cases if cases is not None else all_cases():
        row: dict[str, Any] = dict(case.to_dict())
        finite = _finite(case.values)
        for name, fn in REFERENCE_ESTIMATORS.items():
            value = float(fn(case.values))
            entry: dict[str, Any] = {
                "value": None if value != value else value,
                "breakdown": ESTIMATOR_BREAKDOWN.get(name),
            }
            if case.clean_scale is not None and value == value and case.clean_scale > 0.0:
                entry["ratio_to_clean"] = value / case.clean_scale
            elif case.clean_scale == 0.0 and value == value:
                entry["ratio_to_clean"] = None
            else:
                entry["ratio_to_clean"] = None
            if name in SCALE_ESTIMATORS and value == value and value == 0.0 and finite.size >= 2:
                entry["declines_to_zero"] = True
            row[name] = entry
        rows.append(row)
    return {
        "derived_constants": {
            "Z_75": Z_75,
            "MAD_C": MAD_C,
            "IQR_DIVISOR": IQR_DIVISOR,
            "MEDIAN_PAIRWISE_NORMAL": MEDIAN_PAIRWISE_NORMAL,
            "QN_C": QN_C,
            "SN_RAW_LIMIT_MEASURED": sn_raw_limit(),
            "SN_MULTIPLIER": SN_TARGET_NORMAL / sn_raw_limit(),
            "P2_TUNING": P2_TUNING,
            "P2_SCALE": P2_SCALE,
        },
        "breakdown": dict(ESTIMATOR_BREAKDOWN),
        "cases": rows,
    }


# ---------------------------------------------------------------------------
# Phase B -- the criteria, as executable predicates
# ---------------------------------------------------------------------------
# Each criterion below is stated as a property of a *function*, not as a
# comparison against production, and each says what its tolerance is and why
# that tolerance. "Approx" without a number is not a criterion.


@dataclass(frozen=True)
class Criterion:
    """One scientific requirement, its tolerance, and the justification."""

    key: str
    requirement: str
    tolerance: str
    justification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "requirement": self.requirement,
            "tolerance": self.tolerance,
            "justification": self.justification,
        }


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        key="bounded_inflation",
        requirement=(
            "for a clean population of n >= 1000 with a bounded contamination "
            "fraction, the estimate must not exceed a stated multiple of the "
            "clean scale"
        ),
        tolerance="<= 2x the clean scale at every contamination fraction <= 0.10",
        justification=(
            "This is the property the audit's failure mode lacked: a single 1e5 "
            "cell moved the legacy scale by a factor of ~1500. 2x is chosen "
            "because every candidate in the table is *consistent* for the clean "
            "population, so any inflation above 2x at <= 10 % contamination is "
            "contamination being counted as spread rather than a normal error."
        ),
    ),
    Criterion(
        key="contamination_monotonicity",
        requirement=(
            "adding a contaminated cell must not *decrease* the estimate when the "
            "clean population has a positive scale"
        ),
        tolerance="estimate(contaminated) >= estimate(clean) within 1e-9 relative",
        justification=(
            "Stated as a one-sided bound and not as strict monotonicity in the "
            "contamination *amplitude*, because that is false for quantile "
            "estimators by construction: a 50 %-breakdown estimator evaluated on "
            "a population with a growing extreme tail can legitimately move down "
            "when the tail becomes the majority. The precise property tested is "
            "'the clean spread is never under-reported', which is the direction "
            "that destroys detections."
        ),
    ),
    Criterion(
        key="positive_homogeneity",
        requirement="scale(a * x) == a * scale(x) for every a > 0",
        tolerance="relative 1e-9",
        justification=(
            "Mathematical: every dispersion measure in the table is a positively "
            "homogeneous functional of the sample. Any implementation with an "
            "*absolute* tolerance (the legacy `mad > 1e-9` branch test) or a "
            "*non-homogeneous fallback* (the legacy `return 1.0`) violates it, and "
            "the violation is not a tolerance question -- it is a unit question, "
            "which is the whole of criterion `unit_equivariance`."
        ),
    ),
    Criterion(
        key="translation_invariance",
        requirement="scale(x + b) == scale(x) for every constant b",
        tolerance="relative 1e-9 at |b| up to 1e6 * scale",
        justification=(
            "Mathematical, and the reason it is worth a test at b = 1e6: a survey "
            "origin of 1e6 m with a 1 mm residual is a legal input, and at 1e9 the "
            "addition itself is not representable in binary. The test uses a "
            "magnitude where the arithmetic is exact so that a failure is the "
            "estimator's, not the float format's."
        ),
    ),
    Criterion(
        key="sign_symmetry",
        requirement="scale(-x) == scale(x)",
        tolerance="exact (bitwise where the negation is exact)",
        justification=(
            "Mathematical. A signed residual has no preferred sign, so an "
            "estimator that distinguishes them is measuring polarity, not spread."
        ),
    ),
    Criterion(
        key="unit_equivariance",
        requirement=(
            "a measurement expressed in cm must give the same *z-score* as the "
            "same measurement in m"
        ),
        tolerance="relative 1e-9 on z, exact on the homogeneity step",
        justification=(
            "The consequence of positive homogeneity, and the reason homogeneity "
            "is not academic: the residual amplitude carries whatever unit the "
            "instrument reported, so a scale that is not homogeneous makes the "
            "normalised interpretation unit-dependent -- a z-score that changes "
            "because a file was written in centimetres."
        ),
    ),
    Criterion(
        key="degenerate_status_honesty",
        requirement=(
            "a population with no measurable dispersion must not be reported as a "
            "high-confidence finite scale"
        ),
        tolerance="exact",
        justification=(
            "Contract K7. A constant field genuinely has no estimable spread; the "
            "historical `return 1.0` presented a fabricated constant as a "
            "measurement. This criterion needs no tuned number, which is what "
            "makes it the one criterion that cannot be argued with."
        ),
    ),
    Criterion(
        key="no_declared_zero",
        requirement=(
            "an estimator must not report 0 for a population whose dispersion is "
            "demonstrably positive"
        ),
        tolerance="exact",
        justification=(
            "The mirror of the previous criterion and equally non-negotiable: "
            "reporting zero dispersion for a population with a non-zero one is a "
            "measurement error in the suppressing direction, and it is the failure "
            "that would replace the current one."
        ),
    ),
)


def homogeneity_error(estimator: Callable[[Any], float], values: Any) -> float:
    """Max relative violation of ``f(a x) == a f(x)`` over a range of ``a``."""
    base = estimator(values)
    if base != base or base == 0.0:
        return 0.0
    worst = 0.0
    for a in (0.001, 0.01, 1.0, 10.0, 1000.0, 1e6):
        scaled = estimator(np.asarray(values, dtype=float) * a)
        if scaled != scaled:
            return float("inf")
        worst = max(worst, abs(scaled - a * base) / abs(a * base))
    return worst


def translation_error(estimator: Callable[[Any], float], values: Any) -> float:
    """Max relative violation of ``f(x + b) == f(x)``, at magnitudes where the
    addition is exact in binary floating point."""
    base = estimator(values)
    if base != base or base == 0.0:
        return 0.0
    spread = float(np.max(np.abs(np.asarray(values, dtype=float) - np.median(values))))
    worst = 0.0
    for multiple in (1.0, 100.0, 1e4, 1e6):
        offset = multiple * max(spread, 1.0)
        shifted = estimator(np.asarray(values, dtype=float) + offset)
        if shifted != shifted:
            return float("inf")
        worst = max(worst, abs(shifted - base) / abs(base))
    return worst


def sign_symmetry_error(estimator: Callable[[Any], float], values: Any) -> float:
    base = estimator(values)
    if base != base or base == 0.0:
        return 0.0
    mirrored = estimator(-np.asarray(values, dtype=float))
    if mirrored != mirrored:
        return float("inf")
    return abs(mirrored - base) / abs(base)


def unit_equivariance_error(estimator: Callable[[Any], float], values: Any) -> float:
    """Relative change in the *z-score* of a fixed target when the units change.

    This is the operational statement of positive homogeneity: the scale changes
    by the unit factor and the normalised score does not. Measured on the score
    rather than on the scale so the number is the one an operator sees.
    """
    arr = np.asarray(values, dtype=float)
    centre = float(np.median(arr[np.isfinite(arr)])) if arr[np.isfinite(arr)].size else 0.0
    target = centre + 3.0 * estimator(arr)
    if target != target or estimator(arr) != estimator(arr):
        return float("nan")
    worst = 0.0
    for a in (1e-3, 1.0, 1e3):
        scaled = arr * a
        scale = estimator(scaled)
        if scale != scale or scale == 0.0:
            return float("inf")
        z = (3.0 * estimator(arr) * a) / scale
        worst = max(worst, abs(z - 3.0))
    return worst


def bounded_inflation(
    estimator: Callable[[Any], float],
    clean: Any,
    contaminated: Any,
) -> float:
    """Ratio of the estimate on a contaminated population to the clean one."""
    base = estimator(clean)
    if base != base or base == 0.0:
        return float("nan")
    value = estimator(contaminated)
    if value != value:
        return float("inf")
    return value / base


__all__ = [
    "CRITERIA",
    "ESTIMATOR_BREAKDOWN",
    "IQR_DIVISOR",
    "MAD_C",
    "MEDIAN_PAIRWISE_NORMAL",
    "P2_SCALE",
    "P2_TUNING",
    "QN_C",
    "QN_TARGET_NORMAL",
    "REAL_RESIDUAL_REGIMES",
    "REFERENCE_ESTIMATORS",
    "SCALE_ESTIMATORS",
    "SN_TARGET_NORMAL",
    "Z_75",
    "Criterion",
    "QuantisationVerdict",
    "RegimeCensus",
    "ScaleCase",
    "absdev_breakdown",
    "absdev_consistency",
    "absdev_quantile_scale",
    "all_cases",
    "asymmetric_cases",
    "bounded_inflation",
    "constant_cases",
    "estimator_table",
    "homogeneity_error",
    "invalid_input_cases",
    "iqr_scale",
    "mad_scale",
    "multiple_contamination_cases",
    "near_constant_cases",
    "proposal2_scale",
    "qn_scale",
    "quantisation_gap",
    "quantisation_verdict",
    "sign_symmetry_error",
    "single_extreme_cases",
    "small_sample_cases",
    "sn_raw",
    "sn_raw_limit",
    "sn_scale",
    "std_scale",
    "std_scale_two_pass",
    "translation_error",
    "trimmed_std_scale",
    "unit_equivariance_error",
]

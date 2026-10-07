"""Phase A-D: the independent scale oracle, its consistency, and the case families.

The discipline this file exists to enforce (v2 §12.1): **no test here asserts
"the current output is X"**. Every oracle is derived from a generating
distribution, an analytic constant, or the mathematical structure of a
construction. The production estimator is one of the things being measured and
is never the reference.

In particular there is deliberately **no** test of the form
``new_function(x) == reference_function(x)`` where both share logic. Where
production and the oracle are compared, production's value is checked against
the *known clean scale of a construction* -- a third thing, arrived at
independently.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from groundscan.validation import scale_reference as ref

# ---------------------------------------------------------------------------
# The derived constants, checked against the published values
# ---------------------------------------------------------------------------
# These are the numbers every "x 1.4826" / "/ 1.349" in the codebase traces
# back to. Pinning them here is what makes "derived" mean derived: if the
# derivation and the published value ever disagree, this is where it shows.


def test_the_consistency_constants_are_derived_and_match_the_published_values():
    assert ref.Z_75 == pytest.approx(0.6744897501960817, abs=1e-15)  # noqa: SIM300
    assert pytest.approx(1.4826, rel=1e-5) == ref.MAD_C
    assert pytest.approx(1.349, rel=1e-4) == ref.IQR_DIVISOR
    # MAD_C and IQR_DIVISOR are the same number twice: 1/Phi^-1(0.75) and
    # 2*Phi^-1(0.75). Asserting the identity is what prevents the two from
    # drifting apart -- which would make a MAD and an IQR answer different
    # questions about the same population.
    assert pytest.approx(2.0 / ref.MAD_C, rel=1e-12) == ref.IQR_DIVISOR
    assert ref.mad_scale(np.array([1.0, 3.0])) == pytest.approx(ref.MAD_C, rel=1e-12)


def test_the_qn_multiplier_follows_from_the_median_pairwise_distance():
    # Qn is fixed at 2.2219 on the standard normal and multiplies the median of
    # |X - Y|, which for iid normals is sqrt(2) * Phi^-1(0.75). So the
    # multiplier is not a table lookup; it is that ratio.
    assert pytest.approx(math.sqrt(2.0) * ref.Z_75, rel=1e-15) == ref.MEDIAN_PAIRWISE_NORMAL
    assert pytest.approx(2.2219 / ref.MEDIAN_PAIRWISE_NORMAL, rel=1e-12) == ref.QN_C
    assert pytest.approx(2.3293, abs=1e-3) == ref.QN_C


def test_the_proposal_two_constant_is_the_reciprocal_of_its_mean_influence():
    """P2's divisor is derived from Phi, not fitted to a fixture."""
    from scipy.special import ndtr

    assert pytest.approx(1.0 / (2.0 * float(ndtr(ref.P2_TUNING)) - 1.0), rel=1e-12) == ref.P2_SCALE
    assert pytest.approx(1.2175, abs=1e-3) == ref.P2_SCALE


# ---------------------------------------------------------------------------
# Consistency: does each estimator actually estimate what it claims?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["std", "mad", "absdev_q75", "iqr", "absdev_q90", "absdev_q95"],
)
def test_a_consistent_scale_estimator_returns_about_one_on_the_standard_normal(name):
    """A scale estimator that does not return 1 for sigma = 1 is not consistent.

    This is the *external* check the design register demanded ("its consistency
    constant ... not established"). It is stated as a tolerance on a property,
    not as a stored value, so it keeps working if the sample size changes.
    """
    values = [
        ref.REFERENCE_ESTIMATORS[name](np.random.default_rng(900 + s).normal(0, 1, 4000))
        for s in range(4)
    ]
    assert all(value == value for value in values), f"{name} declined on clean normal data"
    assert np.mean(values) == pytest.approx(1.0, rel=0.05), name


def test_sn_is_consistent_at_its_published_normal_value():
    """Sn's multiplier is derived from a measured limit, so the product is pinned.

    The assertion is on the *product* rather than on either factor: the whole
    point of measuring the limit is that a table copied from a paper is not the
    same object, and pinning 1.1926 alone would let a wrong multiplier pass.
    """
    rng = np.random.default_rng(4242)
    values = [ref.sn_scale(rng.normal(0, 1, 20000)) for _ in range(2)]
    assert np.mean(values) == pytest.approx(ref.SN_TARGET_NORMAL, rel=0.02)
    # The multiplier itself is reproducible, and it is not 1.1926.
    multiplier = ref.SN_TARGET_NORMAL / ref.sn_raw_limit()
    assert multiplier == pytest.approx(1.4187, rel=1e-3)
    assert multiplier != pytest.approx(ref.SN_TARGET_NORMAL, rel=1e-6)


def test_qn_is_consistent_at_its_published_normal_value():
    values = [ref.qn_scale(np.random.default_rng(500 + s).normal(0, 1, 4000)) for s in range(3)]
    assert np.mean(values) == pytest.approx(ref.QN_TARGET_NORMAL, rel=0.02)


def test_the_alpha_quantile_family_is_consistent_at_every_rung():
    """The family is consistent *by construction*; check both ends of the mapping.

    ``alpha = 0.5`` must be exactly the MAD and nothing else. Conflating the
    percentile rank with the CDF point is the specific bug this test exists to
    catch: it reports 1.71 sigma for a unit normal and is still "derived".
    """
    rng = np.random.default_rng(11)
    values = rng.normal(0.0, 1.0, 20000)
    for alpha in (0.5, 0.75, 0.9, 0.95):
        assert ref.absdev_quantile_scale(values, alpha) == pytest.approx(1.0, rel=0.03), alpha
    assert ref.absdev_quantile_scale(values, 0.5) == pytest.approx(ref.mad_scale(values), rel=1e-12)
    assert ref.absdev_breakdown(0.9) == pytest.approx(0.10, rel=1e-12)


def test_the_two_standard_deviation_constructions_agree():
    """A second, unrelated construction of the same quantity.

    ``std_scale`` is one pass about the mean; ``std_scale_two_pass`` is the
    textbook two-pass correction about the median. They would have to fail in
    unrelated ways to agree on a wrong number, which is the same discipline
    ``solidity_reference`` used for its two area constructions.
    """
    rng = np.random.default_rng(31)
    for values in (
        rng.normal(3.0, 2.0, 5000),
        np.round(rng.normal(0.0, 1.0, 2000)),
        np.concatenate([np.zeros(2000), [1e5]]),
    ):
        assert ref.std_scale(values) == pytest.approx(ref.std_scale_two_pass(values), rel=1e-3)


# ---------------------------------------------------------------------------
# Proposal 2 is refuted, and the refutation is pinned
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        np.random.default_rng(3).normal(0, 1, 500),
        np.round(np.random.default_rng(4).normal(0, 1, 500)),
        np.concatenate([np.zeros(400), [200.0]]),
    ],
)
def test_proposal_two_has_no_root_and_is_recorded_as_refuted(values):
    """The standard high-breakdown M-estimator of scale is *undefined* here.

    P2's scale is a root of ``mean(psi((x - m) / t)) = 0`` with ``m`` the
    median. That sum is non-negative everywhere and strictly positive in
    between, so there is no root. Keeping the refutation in the candidate table
    with a NaN return -- rather than deleting it -- is what makes "we tried it"
    checkable instead of a claim.
    """
    assert ref.proposal2_scale(values) != ref.proposal2_scale(values)  # NaN, not a number


# ---------------------------------------------------------------------------
# Phase C: the quantisation gap, compared rather than asserted about
# ---------------------------------------------------------------------------


def test_the_quantisation_gap_is_measured_to_be_a_detector_and_not_a_scale():
    verdicts = {v.claim: v for v in ref.quantisation_verdict()}
    claims = list(verdicts)
    assert len(claims) == 4
    # The two that decide it: it is not consistent for a continuous population,
    # and it returns the spike amplitude for the exact case v1 designed it for.
    consistency = next(v for k, v in verdicts.items() if k.startswith("consistent"))
    robustness = next(v for k, v in verdicts.items() if k.startswith("robust"))
    metadata = next(v for k, v in verdicts.items() if k.startswith("useful"))
    homogeneity = next(v for k, v in verdicts.items() if k.startswith("positive"))
    assert not consistency.holds
    assert not robustness.holds
    assert metadata.holds
    assert homogeneity.holds
    # ...and the numbers themselves, so a future edit cannot quietly change the
    # argument while leaving the verdicts alone.
    assert "8.618e+05" in consistency.measured
    assert "200.000000" in robustness.measured
    assert "0.250000" in metadata.measured


def test_the_gap_is_metadata_and_production_demotes_it_exactly_so():
    """v1 proposed the gap as the tier-3 estimator. Production never adopted it.

    The check is behavioural and it is on the *metadata field*: a quantised
    lattice must surface its quantum, and a continuous field must not.
    """
    from groundscan._util import robust_scale_with_status

    quantised = np.round(np.random.default_rng(13).normal(0, 1, 4000) * 4) / 4.0
    assert robust_scale_with_status(quantised).quantisation_step == pytest.approx(0.25, abs=1e-12)
    assert (
        robust_scale_with_status(np.random.default_rng(14).normal(0, 1, 4000)).quantisation_step
        is None
    )
    # And the gap is never the reported scale, for any of the families the
    # design listed: the spike field's scale must not be 200.
    spike = np.concatenate([np.zeros(3999), [200.0]])
    assert robust_scale_with_status(spike).scale != pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Family A -- constant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ref.constant_cases(), ids=lambda c: c.name)
def test_a_constant_population_has_exactly_zero_dispersion(case):
    assert case.clean_scale == 0.0
    for name in ("std", "mad", "iqr", "absdev_q75", "absdev_q90", "absdev_q95"):
        assert ref.REFERENCE_ESTIMATORS[name](case.values) == 0.0, name
    # The legacy single-number API is the thing that fails this criterion, and
    # it is asserted here as a failure rather than left implicit.
    from groundscan._util import robust_scale, robust_scale_with_status

    assert robust_scale(case.values) == 1.0
    estimate = robust_scale_with_status(case.values)
    assert estimate.is_indeterminate
    assert estimate.scale != estimate.scale, "indeterminate must be NaN, not a number"
    assert estimate.status == "indeterminate"


def test_a_constant_field_of_100_is_not_more_measurable_than_one_of_1():
    """A fabricated scale must not depend on the amplitude.

    The legacy ``return 1.0`` returns 1.0 for a field of 100 exactly as it does
    for a field of 1, which means the number it reports carries no information
    about the field. That is the definition of a fabricated constant and it is
    why the two rows are compared rather than each asserted alone.
    """
    from groundscan._util import robust_scale_with_status

    small = robust_scale_with_status(np.full(500, 1.0))
    large = robust_scale_with_status(np.full(500, 100.0))
    assert small.legacy_scale == large.legacy_scale
    assert small.is_indeterminate and large.is_indeterminate
    assert small.quantisation_step is None and large.quantisation_step is None


# ---------------------------------------------------------------------------
# Family B -- near constant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ref.near_constant_cases(), ids=lambda c: c.name)
def test_a_near_constant_population_reports_its_own_dispersion_not_a_constant(case):
    """The dispersion is known analytically from the construction.

    ``[1, 1, 1, 1, 1 + 1e-9]`` has a population standard deviation of 4e-10. The
    legacy absolute test cannot distinguish that from "no spread at all", so it
    returned the fabricated 1.0 -- wrong by 2.5e9, and wrong in a way that scales
    with nothing.
    """

    dispersion = case.clean_scale
    assert dispersion is not None and 0.0 < dispersion < 1e-6
    # The pre-activation code is what fabricated here, and only where its own
    # absolute 1e-9 guard could not see the spread. Where the dispersion is
    # above that guard the old code was already right, which is why the case
    # family sweeps three orders of magnitude rather than asserting one value.
    from groundscan.validation.scale_shadow_report import shipped_status_estimate

    legacy = shipped_status_estimate(case.values).legacy_scale
    if dispersion < 1e-9:
        assert legacy == 1.0, "the pre-activation code fabricated here"
    else:
        assert legacy == pytest.approx(dispersion, rel=0.05)
    # The oracle: an estimator that reports the sample's own dispersion, and a
    # scale that is a function of the data alone.
    assert ref.std_scale(case.values) == pytest.approx(dispersion, rel=1e-9)
    assert ref.absdev_quantile_scale(case.values, 0.95) == pytest.approx(dispersion, rel=0.2)
    # Scale-free gate means the answer scales with the data. The tolerance is
    # 1e-6 rather than 1e-9 because the *inputs* are at 1e-10 and are being
    # multiplied by 1e6: the round-off of the multiplication is a property of
    # the representation, not of the estimator, and at 1e-9 the test would be
    # measuring float64.
    scaled = case.values * 1e6
    assert ref.std_scale(scaled) == pytest.approx(dispersion * 1e6, rel=1e-6)


def test_contamination_inflation_grows_with_the_contaminated_amplitude():
    """Monotonicity under contamination, stated on the estimator's own scale.

    A single +10 sigma cell out of 4000 barely moves anything -- including the
    breakdown-0 tier, and including production. That is worth asserting rather
    than glossing: it is why the brief's family C sweeps amplitudes instead of
    asserting on one, and it is why the *audited* failure needed 1e5 to bite.
    The property is monotone inflation, not "any spike is fatal".
    """
    from groundscan._util import robust_scale_with_status

    cases = {c.contamination_value if hasattr(c, "contamination_value") else 0.0: c for c in ()}
    del cases
    inflations = []
    for case in ref.single_extreme_cases():
        assert case.clean_values is not None
        inflations.append((
            abs(float(case.values[-1])),
            ref.bounded_inflation(ref.std_scale, case.clean_values, case.values),
            ref.bounded_inflation(
                lambda v: robust_scale_with_status(v).legacy_scale,
                case.clean_values,
                case.values,
            ),
        ))
    inflations.sort()
    amplitudes = [a for a, _s, _p in inflations]
    assert amplitudes == sorted(amplitudes)
    std_inflation = [s for _a, s, _p in inflations]
    production_inflation = [p for _a, _s, p in inflations]
    assert std_inflation == sorted(std_inflation), "a bigger outlier must not inflate less"
    assert production_inflation == sorted(production_inflation)
    # A 10 sigma cell is invisible to everything; a 1e5 cell is visible only to
    # the tiers with no bounded influence.
    assert std_inflation[0] < 1.05
    assert std_inflation[-1] > 1000.0
    assert max(production_inflation) < 1.05, "the primary tier must not follow the tail"


# ---------------------------------------------------------------------------
# Families C and D -- contamination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ref.single_extreme_cases(), ids=lambda c: c.name)
def test_one_extreme_cell_does_not_move_a_high_breakdown_scale(case):
    """Family C, both signs, compared against the *same* estimator on the clean sample.

    The clean population is carried on the case, so the ratio is a statement
    about contamination and about nothing else. That matters: Qn and Sn
    estimate different functionals than sigma, so grading them against a nominal
    sigma would be grading them on somebody else's target.
    """
    assert case.clean_values is not None
    assert case.clean_scale is not None and case.clean_scale > 0.0
    for name in ("mad", "absdev_q75", "absdev_q90", "absdev_q95", "iqr"):
        estimator = ref.REFERENCE_ESTIMATORS[name]
        value = estimator(case.values)
        assert value == pytest.approx(case.clean_scale, rel=0.05), f"{name} on {case.name}"
        # ...and against itself on the clean sample, which is the invariance.
        assert ref.bounded_inflation(estimator, case.clean_values, case.values) == pytest.approx(
            1.0, rel=0.05
        ), f"{name} on {case.name}"


@pytest.mark.parametrize("case", ref.multiple_contamination_cases(), ids=lambda c: c.name)
def test_contamination_fractions_are_matched_to_each_estimators_breakdown(case):
    """Family D, including the point the design missed.

    An estimator is not robust because it resisted one spike. Each rungs
    contamination fraction is compared to that estimator's *own* breakdown point,
    and the assertion follows the theory in both directions: inside the
    breakdown the estimate must hold; at or beyond it the estimate is expected to
    degrade, and the *direction* of that degradation is the property, not a
    magnitude. A breakdown point is where an estimator starts to fail, not where
    it fails all at once -- an estimator measured at exactly its breakdown can
    still be within a factor of two, and pinning a threshold there would be
    inventing a sharper boundary than the mathematics has.
    """
    if case.clean_values is None:
        # A constant population plus contaminated cells: no clean scale is
        # recoverable, which is the point of these three rows.
        assert case.contamination_fraction > 0.0
        for name in ("mad", "iqr", "qn", "sn"):
            assert ref.REFERENCE_ESTIMATORS[name](case.values) == 0.0, name
        assert ref.REFERENCE_ESTIMATORS["std"](case.values) > 0.0
        return
    fraction = case.contamination_fraction
    for name in ref.SCALE_ESTIMATORS:
        breakdown = ref.ESTIMATOR_BREAKDOWN[name]
        estimator = ref.REFERENCE_ESTIMATORS[name]
        value = estimator(case.values)
        clean_value = estimator(case.clean_values)
        if value != value or value == 0.0 or clean_value != clean_value or clean_value == 0.0:
            continue
        ratio = value / clean_value
        if fraction < breakdown:
            assert 0.5 <= ratio <= 2.0, (
                f"{name} at {fraction:.0%} is inside its {breakdown:.0%} breakdown but "
                f"reports {ratio:.3g}x its own clean value"
            )
        else:
            # Degradation is allowed to be slow; what is not allowed is for a
            # contaminated population to report a *smaller* scale than its own
            # clean one, which is the suppressing direction.
            assert ratio >= 1.0, (
                f"{name} at {fraction:.0%} is past its {breakdown:.0%} breakdown and "
                f"reports {ratio:.3g}x -- under-reporting is the dangerous direction"
            )


def test_degradation_past_the_breakdown_is_monotone_in_the_contamination_fraction():
    """The boundary claim above is checked against a sweep, not a single point.

    For a fixed estimator and a growing contaminated fraction, the estimate
    relative to its own clean value must not come back down. Strict numerical
    monotonicity is *not* required and is not asserted -- a quantile estimator
    can move non-monotonically once the contaminant is a large minority -- so
    the property tested is the weaker, one-sided and sufficient one: once an
    estimator has been inflated it stays inflated.
    """
    rng = np.random.default_rng(2026)
    clean = rng.normal(0.0, 1.0, 3000)
    for name in ("std", "sn", "qn", "absdev_q90"):
        estimator = ref.REFERENCE_ESTIMATORS[name]
        base = estimator(clean)
        if base != base or base == 0.0:
            continue
        previous = 1.0
        for fraction in (0.05, 0.10, 0.20, 0.30, 0.40):
            n_bad = int(fraction * 3000)
            values = np.concatenate([clean, rng.normal(0.0, 40.0, n_bad)])
            ratio = estimator(values) / base
            if ratio != ratio:
                continue
            assert ratio >= previous * 0.99, (
                f"{name} at {fraction:.0%} came back down to {ratio:.3g}x after "
                f"reaching {previous:.3g}x: an inflated estimate must stay inflated"
            )
            previous = max(previous, ratio)


def test_the_trimmed_standard_deviation_is_refuted_by_its_own_consistency():
    """Candidate B from the design: "stable to 5 %, collapses at 20 %".

    Both halves are true and the first half is not enough. Measured here, a 10 %
    symmetric trim returns 0.66 for a unit normal -- a 34 % downward bias before
    any contamination at all. A candidate that is mis-scaled on clean data is
    not a consistency candidate however well it survives the contamination axis.
    """
    values = np.random.default_rng(77).normal(0.0, 1.0, 4000)
    assert ref.trimmed_std_scale(values) == pytest.approx(0.66, rel=0.03)
    assert ref.trimmed_std_scale(values) < 0.75


# ---------------------------------------------------------------------------
# Family E -- small n
# ---------------------------------------------------------------------------


def test_small_samples_report_a_number_but_never_a_confident_one():
    """n = 1, 2, 3, 4, 5, 6, 8, 10.

    Nothing at these sizes can be accurate. The requirement is that the record
    says so, and that the ``low_sample`` state exists for it -- which it did not
    before Stage 3, where ``n = 1`` returned the fabricated 1.0 with a
    ``valid``-shaped answer.
    """
    from groundscan._util import SCALE_STATUS_LOW_SAMPLE, robust_scale_with_status

    for case in ref.small_sample_cases():
        estimate = robust_scale_with_status(case.values)
        if case.n < 2:
            assert estimate.is_indeterminate, case.name
            assert estimate.n_effective == 1
            continue
        assert estimate.n_effective == case.n, case.name
        if case.n < 3:
            assert estimate.status == SCALE_STATUS_LOW_SAMPLE, case.name
            # The value is still there -- refusing to produce one would be a
            # different claim, and the unmeasured direction is not safer.
            assert math.isfinite(estimate.legacy_scale), case.name
        if case.n >= 3:
            assert estimate.status != SCALE_STATUS_LOW_SAMPLE, case.name


def test_the_small_sample_status_carries_no_value_change():
    """``low_sample`` is a status, not a re-estimation.

    Two values with a zero range give the same number they always gave, and the
    only thing that changed is that the record now admits what it is.
    """
    from groundscan._util import robust_scale, robust_scale_with_status

    pair = robust_scale_with_status(np.array([1.0, 2.0]))
    assert pair.status == "low_sample"
    assert pair.legacy_scale == robust_scale(np.array([1.0, 2.0]))
    assert pair.legacy_scale == pytest.approx(1.4826 * 0.5, rel=1e-12)


def test_n_of_one_and_two_are_the_only_sizes_where_a_range_is_not_a_spread():
    """Why the boundary is three, stated as a property rather than a preference.

    The MAD of two points is their range divided by two, which is a function of
    the two numbers rather than a property of any population. The third point is
    the smallest count at which a robust dispersion is even defined.
    """
    assert float(np.median(np.abs(np.array([1.0, 3.0]) - np.median([1.0, 3.0])))) == 1.0
    assert ref.mad_scale(np.array([1.0, 3.0])) == pytest.approx(ref.MAD_C, rel=1e-12)


# ---------------------------------------------------------------------------
# Family F -- asymmetric distributions
# ---------------------------------------------------------------------------


def test_an_exponential_residual_is_still_a_scale():
    """A one-sided residual must not need a symmetry assumption to be measured.

    None of the references in the table assumes symmetry: they are all
    functions of ``|x - median|``, which is symmetric by construction, and the
    consistency constants are stated for the *normal* model as the reference
    model rather than as an assumption about the data.
    """
    values = np.random.default_rng(41).exponential(1.0, 4000)
    assert ref.mad_scale(values) == pytest.approx(0.7208, rel=0.05)
    assert ref.iqr_scale(values) == pytest.approx(0.8189, rel=0.05)
    # A robust estimator must not be dragged by the tail of a one-sided
    # population: the estimate stays near the population's own sigma, not near
    # the tail's 1000th percentile.
    assert ref.std_scale(values) / ref.mad_scale(values) == pytest.approx(1.385, rel=0.05)


def test_an_atom_heavier_than_the_median_breaks_every_median_of_medians_scale():
    """The measured reason the degenerate regime has no defensible answer.

    85 % of the population sits on one value. Every estimator in the
    50 %-breakdown family returns **exactly zero** -- not a small number, zero --
    while the population's own dispersion is about 0.55. Reporting zero is a
    measurement error in the suppressing direction and is strictly worse than
    the breakdown-0 number it would replace, because it erases the detections
    instead of merely inflating the threshold.

    Only a higher alpha leaves zero, and each rung costs breakdown. The numbers
    are therefore quoted as a ratio to the population's own dispersion rather
    than as literals, so they stay true if the construction is re-seeded.
    """
    rng = np.random.default_rng(45)
    values = np.concatenate([np.zeros(1352), rng.integers(-2, 3, 248).astype(float)])
    true_dispersion = ref.std_scale(values)
    assert true_dispersion > 0.4
    for name in ("mad", "iqr", "qn", "sn", "absdev_q75"):
        assert ref.REFERENCE_ESTIMATORS[name](values) == 0.0, name
    for alpha in (0.90, 0.95):
        value = ref.absdev_quantile_scale(values, alpha)
        assert value > 0.0, alpha
        assert 0.4 <= value / true_dispersion <= 2.0, (alpha, value, true_dispersion)
    assert ref.ESTIMATOR_BREAKDOWN["absdev_q75"] == 0.25
    assert ref.ESTIMATOR_BREAKDOWN["absdev_q90"] == 0.10


def test_a_broad_tail_is_signal_and_discarding_it_is_not_robustness():
    """The counter-case to the previous test, and the reason for not replacing.

    A large atom plus a genuine broad tail: the tail is the response, not
    contamination. Here the breakdown-0 tier is the *right* answer and the
    50 %-breakdown family returns zero. An estimator that "resists" this
    population destroys the sensitivity the tail exists to provide, which is why
    the choice between them cannot be made by a breakdown point alone.
    """
    values = np.concatenate([np.zeros(2000), np.arange(1, 401, dtype=float)])
    assert ref.std_scale(values) == pytest.approx(88.35, rel=0.01)
    for name in ("mad", "iqr", "qn", "absdev_q75"):
        assert ref.REFERENCE_ESTIMATORS[name](values) == 0.0, name


# ---------------------------------------------------------------------------
# Family G -- non-finite input
# ---------------------------------------------------------------------------


def test_non_finite_input_policy_is_declared_and_dropped_not_propagated():
    """NaN and +/-inf are absent measurements, not values.

    The policy is stated in the contract: non-finite entries are removed before
    estimation, ``n_effective`` records how many survived, and fewer than two
    survivors is ``indeterminate`` rather than zero.
    """
    from groundscan._util import robust_scale_with_status

    for case in ref.invalid_input_cases():
        estimate = robust_scale_with_status(case.values)
        finite = np.asarray(case.values, dtype=float)
        finite = finite[np.isfinite(finite)]
        assert estimate.n_effective == int(finite.size), case.name
        if finite.size < 2:
            assert estimate.is_indeterminate, case.name
            assert estimate.scale != estimate.scale, case.name
        else:
            # The estimate is over the finite part and nothing else: +inf and
            # -inf cancel to NaN in every moment, so propagating either would
            # produce NaN rather than a measurement.
            assert math.isfinite(estimate.legacy_scale) or estimate.is_indeterminate, case.name
            assert case.clean_scale is None or not math.isnan(case.clean_scale)


def test_an_infinite_population_is_unavailable_and_not_infinite():
    """The two answers that are both wrong, asserted separately."""
    from groundscan._util import robust_scale, robust_scale_with_status

    for value in (np.inf, -np.inf):
        estimate = robust_scale_with_status(np.full(100, value))
        assert estimate.is_indeterminate
        assert estimate.scale != estimate.scale
        assert not math.isinf(robust_scale(np.full(100, value)))


def test_a_nan_saturated_population_does_not_manufacture_zero_dispersion():
    """0 is a number; "no measurement" is not 0."""
    from groundscan._util import robust_scale_with_status

    for value in (np.nan, np.inf, -np.inf):
        estimate = robust_scale_with_status(np.full(4000, value))
        assert estimate.is_indeterminate, value
        assert estimate.scale != estimate.scale, value


# ---------------------------------------------------------------------------
# The criteria are executable predicates, and the table is generated
# ---------------------------------------------------------------------------


def test_every_criterion_states_a_tolerance_and_a_justification():
    keys = {c.key for c in ref.CRITERIA}
    assert keys == {
        "bounded_inflation",
        "contamination_monotonicity",
        "positive_homogeneity",
        "translation_invariance",
        "sign_symmetry",
        "unit_equivariance",
        "degenerate_status_honesty",
        "no_declared_zero",
    }
    for criterion in ref.CRITERIA:
        assert criterion.tolerance and criterion.justification
        assert len(criterion.justification) > 80, criterion.key


def test_the_estimator_table_is_generated_and_covers_every_case_family():
    table = ref.estimator_table()
    families = {row["family"] for row in table["cases"]}
    assert families == {"A", "B", "C", "D", "E", "F", "G"}
    for name in ref.REFERENCE_ESTIMATORS:
        assert name in table["cases"][0]
    assert table["derived_constants"]["MAD_C"] == pytest.approx(1.4826, rel=1e-5)
    # A declining estimator is recorded as None, which is a fact and not a gap.
    spike = next(r for r in table["cases"] if r["name"] == "constant_plus_1_at_200")
    assert spike["mad"]["value"] is None or spike["mad"]["value"] == 0.0
    assert spike["quantisation_gap"]["value"] == pytest.approx(200.0)


@pytest.mark.parametrize("name", list(ref.SCALE_ESTIMATORS))
def test_a_documented_estimate_is_homogeneous_and_sign_symmetric(name):
    """Phase B, the two criteria that are properties of every scale estimator.

    Every dispersion measure in the table is a positively homogeneous, sign
    symmetric functional of the sample, so a violation is a bug in the
    implementation rather than a property of the estimator. The production
    estimator is included in the sweep deliberately: it is the one that
    violated both, and the exclusion would be the point.
    """
    from groundscan._util import robust_scale_with_status

    rng = np.random.default_rng(3)
    values = rng.normal(0.0, 1.0, 800)
    for estimator in (
        ref.REFERENCE_ESTIMATORS[name],
        lambda v: robust_scale_with_status(v).legacy_scale,
    ):
        homogeneity = ref.homogeneity_error(estimator, values)
        assert homogeneity < 1e-9, f"{name}: homogeneity error {homogeneity:.3g}"
        symmetry = ref.sign_symmetry_error(estimator, values)
        assert symmetry < 1e-9, f"{name}: sign symmetry error {symmetry:.3g}"


def test_the_production_estimator_failed_homogeneity_before_stage_3():
    """The defect, measured on the pre-activation implementation.

    The corpus reached the degenerate regime 3 times out of 149 residuals, so
    "it does not happen on real data" is a statement about the corpus, not a
    defence of the estimator. On a dust field the pre-activation code returns
    1.0 at every amplitude, so its answer is independent of the field it was
    given -- which is the definition of not being a scale estimator.
    """
    from groundscan.validation.scale_shadow_report import shipped_status_estimate

    dust = np.random.default_rng(6).normal(0.0, 1e-15, 4000)
    values = [shipped_status_estimate(dust * a).legacy_scale for a in (1e-3, 1.0, 1e3)]
    assert values == [1.0, 1.0, 1.0]
    assert len(set(values)) == 1, "a constant answer is not homogeneous"


# ---------------------------------------------------------------------------
# Phase B, the two criteria the corpus cannot exercise
# ---------------------------------------------------------------------------


def test_translation_invariance_holds_where_the_arithmetic_is_exact():
    """``scale(x + b) == scale(x)``, at offsets the float format can represent.

    The offsets stop at ``1e6 * extent`` deliberately. At ``1e9`` the addition
    itself is not representable for a unit-scale field, so a failure there would
    be a statement about binary64 and not about the estimator -- and a test that
    cannot distinguish those two is not a test.
    """
    from groundscan._util import robust_scale_with_status

    rng = np.random.default_rng(3)
    for values in (
        rng.normal(0.0, 1.0, 800),
        np.round(rng.normal(0.0, 1.0, 800)),
        np.concatenate([np.zeros(700), rng.normal(0.0, 5.0, 100)]),
    ):
        for estimator in (
            ref.std_scale,
            ref.mad_scale,
            ref.iqr_scale,
            lambda v: robust_scale_with_status(v).legacy_scale,
        ):
            error = ref.translation_error(estimator, values)
            assert error < 1e-9, f"translation error {error:.3g}"


def test_the_pre_activation_estimator_broke_translation_invariance_at_a_survey_origin():
    """At 1e12 a one-count deviation is not representable, and the old code
    reported the loss of the datum as a measurement of 1.0.

    The 1e16 origin is deliberately not a plausible survey location: it is the
    point at which the *input format* has destroyed the datum, and the point of
    the test is what each estimator says when that has happened. This is the same
    class of defect as the S02 translation finding -- a legal input produced a
    different scientific answer from an origin of 0. The activated estimator
    cannot recover a dispersion the input format destroyed, and it says so
    (``indeterminate``) rather than asserting 1.0. 1e12 is chosen because
    1e9 + 1 *is* representable (1e9 < 2**30), so the property is about the
    magnitude rather than about a remembered constant.
    """
    from groundscan._util import robust_scale_with_status
    from groundscan.validation.scale_shadow_report import shipped_status_estimate

    base = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    assert shipped_status_estimate(base).legacy_scale == pytest.approx(0.4, rel=1e-9)
    # 1e9 + 1 and 1e12 + 1 are both representable; only past 2**53 does a
    # one-unit increment vanish. The magnitude is stated so a reader can see the
    # property is about the format and not about a remembered constant.
    assert float(base[-1] + 1e12) == base[-1] + 1e12, "1e12 + 1 is not representable"
    shifted = base + 1e16
    assert float(shifted[4]) == 1e16, "1e16 + 1 is not representable; the premise changed"
    assert robust_scale_with_status(shifted).is_indeterminate
    # The pre-activation code reported a measurement for a population that has
    # none, and reported *the same* measurement it reports for every other
    # unmeasurable population.
    assert (
        shipped_status_estimate(shifted).legacy_scale
        == shipped_status_estimate(base * 0).legacy_scale
    )


def test_unit_equivalence_preserves_the_normalised_interpretation():
    """A measurement in centimetres must give the same z-score as in metres.

    The scale changes by exactly the unit factor; the z-score does not change at
    all. This is the operational consequence of positive homogeneity and it is
    the reason homogeneity is not an academic property: without it, the reported
    significance of a finding depends on the unit the vendor wrote the file in.
    """
    from groundscan._util import robust_scale_with_status

    rng = np.random.default_rng(8)
    values = rng.normal(0.0, 1.0, 2000)
    target = 3.0 * ref.mad_scale(values)
    base_scale = robust_scale_with_status(values).legacy_scale
    base_z = target / base_scale
    assert base_z == pytest.approx(3.0, rel=0.1)
    for unit_factor, name in ((100.0, "cm"), (1000.0, "mm"), (0.01, "km")):
        scaled = values * unit_factor
        scale = robust_scale_with_status(scaled).legacy_scale
        assert scale == pytest.approx(base_scale * unit_factor, rel=1e-9), name
        assert (target * unit_factor) / scale == pytest.approx(base_z, rel=1e-9), name
        assert (
            ref.unit_equivariance_error(lambda v: robust_scale_with_status(v).legacy_scale, values)
            < 1e-9
        ), name


def test_the_pre_activation_estimator_broke_unit_equivalence():
    """At a dust amplitude the old scale was 1.0 whatever the unit, so the z-score
    was a function of the unit and of nothing else.

    Same construction, three units: the reported significance moves by 1e9 while
    the physical measurement is identical. That is the defect the scale-free gate
    fixes, and it is asserted on the z-score rather than on the scale because the
    z-score is the number an operator reads.
    """
    from groundscan.validation.scale_shadow_report import shipped_status_estimate

    def legacy_z(values: np.ndarray, target: float) -> float:
        scale = shipped_status_estimate(values).legacy_scale
        return target / scale

    dust = np.random.default_rng(6).normal(0.0, 1e-15, 4000)
    target = 3.0 * 1e-15
    z_metres = legacy_z(dust, target)
    z_centimetres = legacy_z(dust * 100.0, target * 100.0)
    assert z_metres == pytest.approx(3e-15, rel=1e-9)
    # 100x smaller, on a physically identical measurement. The comparison uses
    # abs=0 because pytest.approx defaults to an absolute tolerance of 1e-12,
    # which would declare 3e-13 and 3e-15 equal and quietly pass this test.
    # Not z/100: the scale stayed at 1.0 in both units, so the reported
    # significance is *proportional* to the unit -- a 100x larger number for a
    # physically identical measurement.
    assert z_centimetres == pytest.approx(z_metres * 100.0, rel=1e-9, abs=0.0)
    assert z_centimetres != pytest.approx(z_metres, rel=1e-3, abs=0.0), (
        "the old estimator made the reported significance a function of the unit"
    )


# ---------------------------------------------------------------------------
# Production against the independent oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ref.all_cases(), ids=lambda c: c.name)
def test_production_agrees_with_the_independent_oracle_or_declines_with_it(case):
    """Category 14, and the anti-tautology discipline.

    The oracle is a separate implementation from a separate module. Where it
    gives a number, production must give the *same* number up to the ladder's own
    consistency factor -- and where it declines (every 50 %-breakdown estimator
    on an atom-heavy population) production must not be *more* confident than it
    is.

    The comparison is deliberately not "production == oracle": they estimate
    the same functional through different rungs, and the test states the
    relationship it requires -- agreement up to the rung's own factor, and
    agreement in *declining* where the oracle declines.

    The 1e-5 tolerance on the MAD rung is not slack. Production keeps the
    calibrated literal ``1.4826`` so that no existing output moves by a single
    ulp, while the oracle derives the same constant as ``1 / Phi^-1(0.75) =
    1.4826022...``. The two differ by 1.5e-6 and that difference is a recorded
    decision, not an error; asserting 1e-9 here would fail on the decision
    rather than on a defect.
    """
    from groundscan._util import robust_scale_with_status

    estimate = robust_scale_with_status(case.values)
    oracle_mad = ref.mad_scale(case.values)
    oracle_iqr = ref.iqr_scale(case.values)
    if estimate.method == "mad" and math.isfinite(estimate.scale):
        assert estimate.scale == pytest.approx(oracle_mad, rel=1e-5), case.name
    elif estimate.method == "iqr" and math.isfinite(estimate.scale):
        assert estimate.scale == pytest.approx(oracle_iqr, rel=1e-4), case.name
    # Declining: the oracle family returns exactly zero, and production must not
    # report a *confident finite* scale on the strength of a zero MAD.
    if oracle_mad == 0.0 and oracle_iqr == 0.0 and estimate.status == "valid":
        raise AssertionError(
            f"{case.name}: production reported a valid scale from a population whose "
            "MAD and IQR are both exactly zero"
        )
    # And n_effective is the finite count, always.
    finite = np.asarray(case.values, dtype=float)
    assert estimate.n_effective == int(finite[np.isfinite(finite)].size), case.name


def test_the_oracle_and_production_never_both_hold_for_one_of_them_being_wrong():
    """The oracle is a real check, so it must be able to fail.

    A test that can only pass is a mirror. This one perturbs the *production*
    ladder by a known amount and requires the oracle comparison to notice, which
    is what makes the previous test a measurement rather than a tautology.
    """
    from groundscan._util import robust_scale_with_status

    values = np.random.default_rng(5).normal(0.0, 1.0, 2000)
    assert robust_scale_with_status(values).scale == pytest.approx(ref.mad_scale(values), rel=1e-5)
    # Double the reported scale and the relationship must break.
    broken = robust_scale_with_status(values).scale * 2.0
    assert broken != pytest.approx(ref.mad_scale(values), rel=1e-9)

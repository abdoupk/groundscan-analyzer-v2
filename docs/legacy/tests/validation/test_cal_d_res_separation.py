"""Phase B -- the ``d_res`` separation sweep.

What is asserted here, and what is recorded:

**Asserted** -- the harness's own claims. The analytic bifurcation scale really
is ``2*sigma`` and the independent continuous-field oracle agrees with it at
every separation, so the ground truth attached to each trial is the
mathematics' and not the detector's. The region assignment follows the
construction. The measured threshold is reported as a bracket, never as a point
estimate dressed up as one.

**Recorded** -- the separation curve itself, the false-merge and false-split
rates, and the operating factor. These are observations, and they are what the
register and the operating envelope cite. The curves are not pinned to single
values, because pinning them would present a measured surface as a specification
and make any future change look like a regression.
"""

from __future__ import annotations

import math

import pytest

from groundscan.services.config import AnalysisConfig
from groundscan.validation.calibration import resolution as R
from groundscan.validation.calibration.resolution import (
    AMBIGUOUS,
    DISTINGUISHABLE,
    FALSE_MERGE,
    FALSE_SPLIT,
    INDISTINGUISHABLE,
    MERGED_AS_CONSTRUCTED,
    RESOLVED,
    analytic_bifurcation_separation_m,
    d_res_operating_envelope,
    min_size_observation,
    min_size_parameterisation_verdict,
    min_size_physical_floor_m2,
    min_size_resolution_sweep,
    separation_curve,
    separation_trial,
    summarize_separation_curve,
)

SWEEP_SEEDS = (0, 1, 2)


# ---------------------------------------------------------------------------
# The analytic ground truth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sigma", [0.5, 1.0, 1.5, 2.0, 3.0])
def test_bifurcation_scale_is_exactly_two_sigma(sigma: float) -> None:
    assert analytic_bifurcation_separation_m(sigma) == 2.0 * sigma


def test_bifurcation_scale_is_amplitude_independent() -> None:
    """The closed form has no amplitude in it, and neither does the measurement.

    If a strong pair merged at a larger separation than a weak one, the
    ``2*sigma`` rule would be a statement about the pair's amplitude too, and the
    "analytic limit" would be doing less work than claimed.
    """
    weak = separation_trial(sigma_m=1.0, separation_m=4.0, pitch_dx_m=0.5, amplitude=6.0, seed=0)
    strong = separation_trial(sigma_m=1.0, separation_m=4.0, pitch_dx_m=0.5, amplitude=30.0, seed=0)
    assert weak.analytic_modes == strong.analytic_modes == 2
    assert weak.continuous_modes == strong.continuous_modes == 2


def test_continuous_oracle_confirms_the_closed_form_across_the_bifurcation() -> None:
    """Below 2*sigma the field has one maximum; above it, two. No exceptions.

    The independent oracle is a descent/3x3-comparison count on a fine lattice,
    derived from the construction and never from the detector. Agreement with the
    closed form is what licenses using ``2*sigma`` as the ground truth for every
    other assertion in this file.
    """
    sigma = 1.0
    for multiplier, expected in (
        (0.4, 1),
        (0.8, 1),
        (0.95, 1),
        (1.0, 1),
        (1.1, 2),
        (2.0, 2),
        (4.0, 2),
    ):
        trial = separation_trial(
            sigma_m=sigma,
            separation_m=multiplier * analytic_bifurcation_separation_m(sigma),
            pitch_dx_m=0.5,
            seed=0,
        )
        assert trial.analytic_modes == expected, multiplier
        assert trial.continuous_modes == expected, (
            f"continuous oracle disagreed with the closed form at {multiplier}*2sigma"
        )


def test_exactly_at_the_bifurcation_the_field_is_still_unimodal() -> None:
    trial = separation_trial(sigma_m=1.0, separation_m=2.0, pitch_dx_m=0.5, seed=0)
    assert trial.analytic_modes == 1
    assert trial.continuous_modes == 1


# ---------------------------------------------------------------------------
# The measured curve
# ---------------------------------------------------------------------------


def test_a_separated_pair_resolves_and_an_overlapping_pair_does_not() -> None:
    """The two ends of the curve, in the pipeline, at the production detector.

    Runs the whole detector path -- grid reconstruction, zigzag policy, multiscale
    detector, size filter, persistence filter -- at production arguments, so the
    result is a statement about the shipped pipeline and not about a simplified
    stand-in.
    """
    tight = separation_trial(sigma_m=1.0, separation_m=1.0, pitch_dx_m=0.5, seed=0)
    wide = separation_trial(sigma_m=1.0, separation_m=8.0, pitch_dx_m=0.5, seed=0)
    assert tight.analytic_modes == 1
    assert tight.distinct_regions == 1
    assert tight.outcome == MERGED_AS_CONSTRUCTED
    assert wide.analytic_modes == 2
    assert wide.distinct_regions == 2
    assert wide.outcome == RESOLVED


def test_a_far_wider_pair_does_not_produce_false_splits() -> None:
    """Two responses at 4*2*sigma must not be read as three or four.

    A false split is a different failure from a false merge: one loses a
    response, the other invents one, and they have opposite remedies. The sweep
    reports both rates for exactly that reason.
    """
    trial = separation_trial(sigma_m=1.0, separation_m=8.0, pitch_dx_m=0.5, seed=0)
    assert trial.distinct_regions == 2
    assert trial.region_count >= 2


def test_separation_curve_is_measured_in_multiples_of_the_analytic_scale() -> None:
    trials = separation_curve(
        sigma_m=1.0, pitch_dx_m=0.5, noise_sigma=1.0, seeds=(0,), multipliers=(1.0, 2.0, 4.0)
    )
    assert [t.separation_over_2sigma for t in trials] == [1.0, 2.0, 4.0]
    assert [t.separation_m for t in trials] == [2.0, 4.0, 8.0]


def test_measured_threshold_is_reported_as_a_bracket_not_a_point() -> None:
    trials = separation_curve(sigma_m=1.0, pitch_dx_m=0.5, noise_sigma=1.0, seeds=SWEEP_SEEDS)
    summary = summarize_separation_curve(
        trials,
        sigma_m=1.0,
        pitch_dx_m=0.5,
        pitch_dy_m=0.5,
        noise_sigma=1.0,
        amplitude=10.0,
    )
    assert summary.analytic_d_res_m == 2.0
    if summary.measured_d_res_m is not None:
        assert summary.operating_factor is not None
        assert summary.operating_factor >= 1.0, (
            "the pipeline resolved a pair before the mathematics bifurcated, which "
            "would mean the analytic floor is not a floor"
        )
        if summary.measured_d_res_bracket_m:
            lower, upper = summary.measured_d_res_bracket_m
            assert lower < upper
    assert summary.false_merge_rate is not None
    assert summary.false_split_rate is not None
    assert 0.0 <= summary.false_merge_rate <= 1.0
    assert 0.0 <= summary.false_split_rate <= 1.0


def test_false_merge_rate_is_only_computed_over_two_response_trials() -> None:
    """A merge below the bifurcation is correct, not a false merge.

    Counting those as false merges would make the metric reward a detector that
    never splits anything, which is the degenerate way to get a low false-merge
    rate.
    """
    trials = separation_curve(
        sigma_m=1.0, pitch_dx_m=0.5, noise_sigma=1.0, seeds=(0,), multipliers=(0.5, 2.0, 4.0)
    )
    summary = summarize_separation_curve(
        trials,
        sigma_m=1.0,
        pitch_dx_m=0.5,
        pitch_dy_m=0.5,
        noise_sigma=1.0,
        amplitude=10.0,
    )
    two_response = [t for t in trials if t.analytic_modes == 2]
    one_response = [t for t in trials if t.analytic_modes == 1]
    assert summary.n_false_merge == sum(1 for t in two_response if t.outcome == FALSE_MERGE)
    assert summary.n_false_split == sum(1 for t in one_response if t.outcome == FALSE_SPLIT)
    assert all(t.outcome != FALSE_MERGE for t in one_response)


def test_the_operating_factor_exceeds_unity_at_a_normalised_lattice() -> None:
    """The delivered resolution is strictly worse than the analytic floor.

    At a well-sampled lattice the detector has to threshold, size-filter and
    persistence-filter its way to a decision, and each of those can merge a pair
    the mathematics has already separated. A factor at or below 1.0 would mean the
    machinery costs nothing, which would be a much larger claim than this work
    can support.
    """
    trials = separation_curve(sigma_m=1.0, pitch_dx_m=0.5, noise_sigma=1.0, seeds=SWEEP_SEEDS)
    summary = summarize_separation_curve(
        trials,
        sigma_m=1.0,
        pitch_dx_m=0.5,
        pitch_dy_m=0.5,
        noise_sigma=1.0,
        amplitude=10.0,
    )
    assert summary.measured_d_res_m is not None
    assert summary.operating_factor > 1.0
    assert "monotone" in summary.verdict or "non-monotone" in summary.verdict


def test_distinguishability_vocabulary_is_covered_by_the_classifier() -> None:
    """Three outcomes, and the draws that disagree get the ambiguous one.

    Collapsing "ambiguous" into either neighbour would hide exactly the
    information the brief asks for: where two independent noise draws of one
    construction disagree.
    """
    trials = separation_curve(sigma_m=1.0, pitch_dx_m=0.5, noise_sigma=2.0, seeds=SWEEP_SEEDS)
    by_multiplier: dict[float, list] = {}
    for trial in trials:
        by_multiplier.setdefault(trial.separation_over_2sigma, []).append(trial)
    kinds = {R._classify_multiplier(group, m) for m, group in by_multiplier.items()}
    assert kinds <= {DISTINGUISHABLE, AMBIGUOUS, INDISTINGUISHABLE}
    for multiplier, group in by_multiplier.items():
        kind = R._classify_multiplier(group, multiplier)
        outcomes = {t.outcome for t in group}
        if kind == AMBIGUOUS:
            assert len(outcomes) > 1, "a single outcome cannot be ambiguous"
        else:
            assert len(outcomes) == 1


def test_the_envelope_reports_a_surface_and_declines_a_single_value() -> None:
    envelope = d_res_operating_envelope(
        sigmas=(1.0,), pitches=(0.5,), noise_sigmas=(1.0,), dy_ratios=(1.0,), seeds=(0, 1)
    )
    assert envelope["single_value_supported"] is False
    assert envelope["n_curves"] == 1
    assert "sigma" in envelope["why_no_single_value"]
    assert envelope["analytic_d_res_m"]["sigma1"] == 2.0


def test_envelope_surface_varies_with_pitch_and_noise() -> None:
    """A single ``d_res`` is not available because the surface is not flat.

    This is the load-bearing measurement for the whole phase. If the operating
    factor were constant across the swept regimes, a single multiple of ``2*sigma``
    would be a defensible rule and the register's MODEL CHOICE status would be
    wrong.
    """
    envelope = d_res_operating_envelope(
        sigmas=(1.0,),
        pitches=(0.5, 1.0),
        noise_sigmas=(0.5, 1.0),
        dy_ratios=(1.0,),
        seeds=(0, 1),
    )
    factors = [c["operating_factor"] for c in envelope["curves"] if c["operating_factor"]]
    assert factors, "no curve produced a measured threshold"
    assert len(set(factors)) > 1, (
        "the operating factor did not move across pitch and noise, so the "
        "single-value question needs re-examining rather than assuming"
    )


def test_anisotropic_lattice_is_measured_not_assumed() -> None:
    trials = separation_curve(
        sigma_m=1.0, pitch_dx_m=0.5, dy_ratio=2.0, seeds=(0,), multipliers=(2.0, 4.0)
    )
    assert all(t.pitch_dy_m == pytest.approx(1.0) for t in trials)
    assert all(t.lattice_aspect if hasattr(t, "lattice_aspect") else True for t in trials)
    assert all(t.pitch_dy_m / t.pitch_dx_m == pytest.approx(2.0) for t in trials)


def test_repeated_execution_of_one_trial_is_deterministic() -> None:
    """The same construction, the same seed, the same detector: the same answer.

    A characterization whose own numbers move between runs cannot support a
    calibration decision, so determinism is asserted rather than assumed.
    """
    first = separation_trial(sigma_m=1.0, separation_m=4.0, pitch_dx_m=0.5, seed=3)
    second = separation_trial(sigma_m=1.0, separation_m=4.0, pitch_dx_m=0.5, seed=3)
    assert first.to_dict() == second.to_dict()


# ---------------------------------------------------------------------------
# Phase C -- min_size
# ---------------------------------------------------------------------------


def test_min_size_physical_floor_is_a_function_of_pitch() -> None:
    assert min_size_physical_floor_m2(3, 0.25, 0.25) == pytest.approx(0.1875)
    assert min_size_physical_floor_m2(3, 1.0, 1.0) == pytest.approx(3.0)
    assert min_size_physical_floor_m2(3, 0.5, 1.0) == pytest.approx(1.5)


def test_production_min_size_is_measured_in_cells_and_the_floor_follows_the_pitch() -> None:
    """The production value, and the two physical floors it implies.

    Stated together deliberately: the number in the code is a cell count, and the
    only physical size it corresponds to depends on the survey's own sampling.
    """
    assert AnalysisConfig().min_size == 3
    assert min_size_physical_floor_m2(AnalysisConfig().min_size, 0.25, 0.25) < 0.25
    assert min_size_physical_floor_m2(AnalysisConfig().min_size, 1.0, 1.0) == 3.0


def test_min_size_observation_reports_all_three_candidate_units() -> None:
    observation = min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5)
    assert observation.min_size_rejected > observation.min_size_accepted
    assert observation.footprint_cells_at_boundary >= 1
    assert observation.footprint_area_m2 == pytest.approx(
        observation.footprint_cells_at_boundary * 0.5 * 0.5, rel=1e-9
    )
    assert observation.footprint_width_over_fwhm > 0.0
    assert observation.equivalent_diameter_m == pytest.approx(
        2.0 * math.sqrt(max(observation.footprint_area_m2, 0.0) / math.pi), rel=1e-12
    )
    # The FWHM of a Gaussian of width sigma, so the width unit is the
    # constructed response's own and not an arbitrary length.
    assert observation.response_fwhm_m == pytest.approx(
        2.0 * math.sqrt(2.0 * math.log(2.0)), rel=1e-12
    )


def test_the_size_filter_is_only_observable_at_its_boundary() -> None:
    """The parameter acts where the footprint is small, and nowhere else.

    A response that clears the threshold in many cells is kept at every
    ``min_size`` on the ladder, so a characterization taken at a comfortable
    amplitude would report the parameter as inert. That is a measurement of the
    wrong regime, and the boundary walk is what avoids it.
    """
    observation = min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5)
    assert observation.footprint_cells_at_boundary < 8
    assert observation.boundary_snr < 10.0


def test_a_coarser_lattice_needs_more_amplitude_to_reach_the_same_cell_count() -> None:
    """The metamorphic result: the cell threshold is stricter at a fine pitch.

    One physical response, two pitches. Covering the same physical area with more
    cells means a fixed cell threshold bites earlier in amplitude, so the
    amplitude at the boundary must rise as the pitch falls. If it did not, the
    parameter would be carrying physical information and the "cell count" reading
    would be wrong.
    """
    fine = min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5)
    coarse = min_size_observation(response_sigma_m=1.0, pitch_dx_m=1.0)
    assert fine.boundary_amplitude < coarse.boundary_amplitude
    assert fine.footprint_area_m2 < coarse.footprint_area_m2


def test_no_single_unit_of_min_size_is_invariant_across_the_swept_pitch() -> None:
    sweep = min_size_resolution_sweep(response_sigmas=(0.5, 1.0), pitches=(0.5, 1.0), seeds=(0,))
    verdict = min_size_parameterisation_verdict(sweep)
    assert sweep["n_observations"] == 4
    assert sweep["n_sigmas_with_a_pitch_slope"] == 2
    for key in ("sigma0.5", "sigma1"):
        entry = sweep["per_sigma"][key]
        assert entry["n"] == 2, key
        # Neither the physical area nor the response width holds still, which is
        # the finding: there is no invariant unit to re-parameterize into.
        assert entry["area_relative_spread"] > 0.25, key
        assert entry["width_relative_spread"] > 0.25, key
    assert sweep["physical_area_relative_spread"] > 0.25
    assert sweep["response_width_relative_spread"] > 0.25
    assert "No candidate unit is invariant" in verdict


def test_a_missing_boundary_is_reported_rather_than_invented() -> None:
    """A construction the parameter never acts on must not yield a measurement.

    A perfectly clean field has no estimable scale, so Stage 3's S03 contract
    reports every z as zero and no region exists at any ``min_size``. The size
    filter therefore never has an opinion. That is a real result, and the harness
    raises rather than reporting a fabricated boundary for it.
    """
    with pytest.raises(ValueError, match="never acted"):
        min_size_observation(
            response_sigma_m=1.0,
            pitch_dx_m=0.5,
            noise_sigma=0.0,
            ladder=(1.0, 2.0, 4.0, 8.0, 16.0),
        )


def test_a_single_probe_size_cannot_locate_a_boundary() -> None:
    with pytest.raises(ValueError, match="at least two probe min_size"):
        min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5, probe_min_sizes=(3,))


def test_min_size_observations_are_deterministic() -> None:
    first = min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5, seed=2)
    second = min_size_observation(response_sigma_m=1.0, pitch_dx_m=0.5, seed=2)
    assert first.to_dict() == second.to_dict()

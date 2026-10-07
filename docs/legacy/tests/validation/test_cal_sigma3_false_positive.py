"""Phase G -- the 3-sigma gate, characterized as the heuristic it is.

The nominal rate ``2*Phi(-t)`` is computed in closed form, and every source of its
departure is measured separately rather than lumped into one "actual" figure:

* **multiplicity** -- the per-scale rates are measured individually, so the
  contribution of the max-over-four-scales is attributable rather than inferred;
* **non-Gaussianity per scale** -- a median-filter residual is not normal, and the
  smallest scale is where that shows most;
* **spatial correlation** -- lag-1 Moran's I, with the effective sample size it
  implies. Asserted to be *measurable* and reported with its sign, because the
  measurement came out negative and that refutes the usual intuition;
* **contamination** -- the same sweep repeated with injected spikes.

The load-bearing assertion is that the gate is *not* a significance level. The
tests check that the measured rate departs from the nominal one, that the
departure is attributed, and that the reported interpretation says so.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from groundscan.services.config import AnalysisConfig
from groundscan.validation.calibration.decision import (
    contamination_sensitivity,
    effective_sample_size,
    gaussian_two_sided_tail,
    morans_i_lag1,
    three_sigma_characterization,
    three_sigma_observation,
    threshold_false_positive_count,
)

PRODUCTION = AnalysisConfig().threshold


# ---------------------------------------------------------------------------
# The closed form
# ---------------------------------------------------------------------------


def test_the_nominal_rate_is_the_closed_form() -> None:
    """``P(|Z| > t) = erfc(t/sqrt(2))``, checked against known values.

    Written in closed form rather than sampled, so the nominal figure the measured
    rate is compared against is never itself an empirical input.
    """
    assert gaussian_two_sided_tail(1.0) == pytest.approx(0.31731, abs=1e-5)
    assert gaussian_two_sided_tail(1.959964) == pytest.approx(0.05, abs=1e-6)
    assert gaussian_two_sided_tail(2.0) == pytest.approx(0.04550, abs=1e-5)
    assert gaussian_two_sided_tail(3.0) == pytest.approx(0.00270, abs=1e-5)
    assert gaussian_two_sided_tail(4.0) == pytest.approx(6.334e-5, abs=1e-8)
    assert gaussian_two_sided_tail(5.0) == pytest.approx(5.733e-7, abs=1e-9)


def test_the_production_threshold_is_three() -> None:
    assert PRODUCTION == 3.0
    assert gaussian_two_sided_tail(PRODUCTION) < 0.003


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def test_a_noise_only_field_produces_regions_because_the_gate_is_not_a_significance_level() -> None:
    """The finding, stated as an assertion.

    On a field with no response in it at all, the production 3.0 gate still admits
    cells, and the per-cell rate is several times the nominal one. If it were a
    0.27% false-positive rate this test would fail -- which is the point.
    """
    observation = three_sigma_observation(threshold=3.0, rows=64, cols=64, seed=0)
    assert observation.nominal_cell_rate == pytest.approx(0.0027, abs=1e-4)
    assert observation.measured_cell_rate > observation.nominal_cell_rate
    assert observation.multiplicity_factor > 2.0, (
        "the measured rate is not materially above nominal, so the multiplicity "
        "characterization has stopped working"
    )
    assert observation.n_regions > 0, "a 3.0 gate admitted nothing on pure noise"


def test_the_downstream_filters_reject_every_excursion_on_a_small_field() -> None:
    """Where the surviving count is zero, and why that is a measurement.

    The per-cell rate and the number of components a report would show are
    different numbers, separated by the ``min_size`` size filter and the multiscale
    persistence filter. On a 64x64 field both reject every noise excursion, so the
    reported false-positive count is exactly zero while the gate is admitting
    1.3% of cells. Quoting either number without the other would be misleading in
    opposite directions.
    """
    for seed in (0, 1, 2):
        small = three_sigma_observation(threshold=3.0, rows=64, cols=64, seed=seed)
        assert small.n_regions > 0
        assert small.n_regions_ge_min_size == 0, (
            f"seed {seed}: an excursion survived both filters on a 64x64 field, so the "
            "reported zero no longer describes the pipeline"
        )


def test_surviving_false_positives_appear_only_once_the_field_is_large_enough() -> None:
    """The threshold at which the surviving count becomes non-zero.

    A large target-free field does produce surviving components. The count is small
    and it is the number a user would actually see, so it is measured on a field
    big enough for it to be non-zero -- and the field size travels with the figure.
    """
    counts = []
    for seed in (0, 1, 2):
        large = three_sigma_observation(threshold=3.0, rows=128, cols=128, seed=seed)
        counts.append(large.n_regions_ge_min_size)
        assert large.n_regions > large.n_regions_ge_min_size
    assert max(counts) > 0, "no surviving false positive on any 128x128 field"
    assert min(counts) <= 5, "the surviving count is not small enough to be a rate"
    result = threshold_false_positive_count(threshold=3.0, seeds=(0, 1, 2))
    assert result["rows"] == 128
    assert result["n_fields"] == 3
    assert 0.0 <= result["mean_false_positive_components_per_field"] <= 5.0


def test_the_multiplicity_is_attributable_to_the_smallest_scale() -> None:
    """Per-scale rates, so the factor is decomposed rather than asserted.

    The max-over-scales gate is a maximiser over four correlated fields, and the
    per-scale numbers say where the excess comes from: a 3-cell median filter
    barely touches the noise, so its residual's standardised tails are the
    heaviest of the four.
    """
    observation = three_sigma_observation(threshold=3.0, rows=64, cols=64, seed=0)
    per_scale = observation.per_cell
    assert set(per_scale) == {"scale3", "scale5", "scale9", "scale15"}
    ratios = {name: stats["ratio"] for name, stats in per_scale.items()}
    assert max(ratios, key=ratios.get) == "scale3", (
        "the largest single-scale excess is no longer at the smallest scale"
    )
    assert ratios["scale3"] > 1.0
    assert ratios["scale15"] < ratios["scale3"]


def test_the_effective_sample_size_is_measured_and_reported_with_its_sign() -> None:
    """Spatial correlation is reported, not assumed away.

    The measurement came out *negative*: a median-filter residual is a high-pass
    filter, so neighbouring z values anti-correlate and the number of independent
    tests exceeds the cell count. Asserting that it is measurable, and reporting
    the sign, is what stops the usual "correlated cells inflate the false-positive
    rate" claim from being repeated unmeasured in either direction.
    """
    observation = three_sigma_observation(threshold=3.0, rows=64, cols=64, seed=0)
    assert np.isfinite(observation.morans_i)
    assert -1.0 < observation.morans_i < 1.0
    assert observation.effective_sample_size > 0.0
    # Negative autocorrelation means MORE independent tests, not fewer.
    if observation.morans_i < 0.0:
        assert observation.effective_sample_size > observation.n_cells
    else:
        assert observation.effective_sample_size < observation.n_cells


def test_morans_i_is_zero_for_an_independent_field_and_one_for_a_constant_one() -> None:
    """The autocorrelation estimator is checked against two known cases.

    Independent noise must read near zero and a constant field must read exactly
    zero, or the effective-sample-size figure derived from it means nothing.
    """
    rng = np.random.default_rng(0)
    independent = rng.normal(0.0, 1.0, size=(64, 64))
    assert abs(morans_i_lag1(independent)) < 0.10
    constant = np.ones((16, 16))
    assert morans_i_lag1(constant) == 0.0
    assert not np.isfinite(morans_i_lag1(np.ones((1, 4))))


def test_a_smooth_field_reads_a_strongly_positive_autocorrelation() -> None:
    """The opposite sign is reachable, so the negative reading is not an artifact.

    A low-pass field has neighbours that move together, so the estimator must
    report a positive ``I`` and a *smaller* effective sample size. Without this,
    a sign error in the estimator would still produce a plausible-looking negative
    number on noise.
    """
    ramp = np.add.outer(np.arange(64.0), np.arange(64.0))
    assert morans_i_lag1(ramp) > 0.5
    assert effective_sample_size(ramp) < ramp.size


def test_the_measured_rate_falls_as_the_threshold_rises() -> None:
    """The sweep has the shape a threshold sweep must have.

    A sweep that did not fall would mean the measurement was not responding to the
    parameter it claims to sweep, and every rate it reported would be suspect.
    """
    rates = []
    for threshold in (2.0, 2.5, 3.0, 4.0, 5.0):
        observation = three_sigma_observation(threshold=threshold, rows=48, cols=48, seed=0)
        rates.append(observation.measured_cell_rate)
    assert rates == sorted(rates, reverse=True)
    assert rates[0] > rates[-1]


def test_the_size_and_persistence_filters_reduce_the_surviving_region_count() -> None:
    """What actually reaches a report, as distinct from what the gate admits.

    The per-cell rate is the detector's interior. The count of surviving components
    is the number whose field-performance implication anybody would want to quote,
    so it is measured separately and on a field large enough to be non-zero.
    """
    observation = three_sigma_observation(threshold=3.0, rows=128, cols=128, seed=0)
    assert observation.n_regions_ge_min_size <= observation.n_regions
    assert observation.n_regions_ge_min_size < observation.n_regions / 10.0
    result = threshold_false_positive_count(threshold=3.0, seeds=(0, 1, 2, 3))
    assert result["n_fields"] == 4
    assert result["mean_false_positive_components_per_field"] >= 0.0
    assert 0 <= result["n_fields_with_zero"] <= result["n_fields"]
    assert len(result["per_field"]) == result["n_fields"]


def test_contamination_does_not_inflate_the_per_cell_rate_through_the_scale() -> None:
    """A robust scale is high-breakdown, and the measurement confirms it.

    Injected single-cell spikes at 60 sigma should barely move the per-cell
    exceedance rate, because the MAD that sets the denominator ignores them. What
    they *can* do is create regions, so both numbers are reported -- and the test
    asserts the rate is the one that stays put.
    """
    result = contamination_sensitivity(fractions=(0.0, 0.02), seeds=(0, 1))
    clean = result["per_fraction"]["0"]
    dirty = result["per_fraction"]["0.02"]
    assert dirty["mean_measured_cell_rate"] < clean["mean_measured_cell_rate"] * 3.0
    assert clean["mean_regions"] > 0.0


def test_the_contamination_policy_constants_are_named_as_policy_not_calibration() -> None:
    reference = contamination_sensitivity(fractions=(0.0,), seeds=(0,))
    policy = reference["contamination_policy_reference"]
    assert policy["sigmas"] == 4.0
    assert policy["fraction"] == 0.05
    assert "policy choice" in policy["applies_to"]
    assert "3-sigma gate" in policy["applies_to"]


def test_the_full_characterization_states_its_interpretation() -> None:
    result = three_sigma_characterization(
        thresholds=(2.5, 3.0, 4.0), seeds=(0, 1, 2), contaminating_fractions=(0.0,)
    )
    assert result["production_threshold"] == 3.0
    assert result["n_scales"] == len(AnalysisConfig().scales)
    assert "2.5" in result["per_threshold_clean_field"]
    assert "3" in result["per_threshold_clean_field"]
    assert result["per_threshold_clean_field"]["3"]["mean_multiplicity_factor"] > 1.0
    interpretation = result["interpretation"]
    assert "is not a 0.27% false-positive rate" in interpretation
    assert "must not be reported as a significance level" in interpretation
    for row in result["observed_rows"]:
        # Reported to eight decimal places, so the tolerance is the rounding.
        assert row["nominal_cell_rate"] == pytest.approx(
            gaussian_two_sided_tail(row["threshold"]), abs=1e-8
        )


def test_a_tau_sweep_covers_the_measured_false_positive_range_not_just_the_nominal() -> None:
    """The production row must sit inside the sweep and be reachable.

    A characterization that only ever reported the nominal rate would make the
    3.0 reading look safe; the whole point is that the measured rate is several
    times larger at the same threshold.
    """
    result = three_sigma_characterization(
        thresholds=(2.0, 3.0, 4.0), seeds=(0, 1), contaminating_fractions=(0.0,)
    )
    per = result["per_threshold_clean_field"]
    at_three = per["3"]
    at_four = per["4"]
    assert at_three["mean_measured_cell_rate"] > at_four["mean_measured_cell_rate"]
    assert at_three["nominal_cell_rate"] < at_three["mean_measured_cell_rate"]


def test_the_measurement_is_deterministic() -> None:
    first = three_sigma_observation(threshold=3.0, rows=48, cols=48, seed=5)
    second = three_sigma_observation(threshold=3.0, rows=48, cols=48, seed=5)
    assert first.to_dict() == second.to_dict()


def test_a_threshold_below_the_production_one_admits_much_more() -> None:
    """The parameter is load-bearing, so there is something to characterize.

    A gate that behaved identically at 2.0 and 5.0 would be inert, and the
    register's MODEL CHOICE status for ``threshold`` would need to become
    something else.
    """
    low = three_sigma_observation(threshold=2.0, rows=48, cols=48, seed=0)
    high = three_sigma_observation(threshold=5.0, rows=48, cols=48, seed=0)
    assert low.measured_cell_rate > 5.0 * high.measured_cell_rate
    assert low.n_regions > high.n_regions
    assert math.isfinite(low.multiplicity_factor)

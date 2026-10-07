"""Phase F: the previously reported failure, reconstructed and re-measured.

The report was: *"a mostly quiet residual plus one extreme acquisition cell
pushed the 3-sigma detection threshold above every genuine anomaly and the scan
reported nothing."* This file rebuilds that scenario from a construction whose
dispersion, target amplitude and target size are all *stated*, and measures
whether it still happens -- and, when it does, whether the activated estimator
is the thing that changed.

The oracle is the clean construction. No golden hash and no vendor annotation is
consulted, because a golden is a regression reference and a vendor note is a
claim about a field, and neither can say whether a target that the construction
placed at a known cell is still detectable.

The result, stated up front so the file's assertions are not a surprise: **the
failure reproduces, and the activation does not fix it.** The measured
sensitivity loss is three of three findings, at one contaminated cell of 200
counts on a background of 0.57 counts. The third rung keeps the breakdown-0
estimate because every replacement was measured to be worse -- and that is
recorded here as an open item rather than presented as a fix.
"""

from __future__ import annotations

import numpy as np
import pytest

from groundscan.validation import scale_contamination_experiment as exp
from groundscan.validation import scale_reference as ref
from groundscan.validation.scale_shadow_report import (
    candidate_status_estimate,
    shipped_status_estimate,
)

# ---------------------------------------------------------------------------
# The construction
# ---------------------------------------------------------------------------


def test_the_construction_really_is_the_degenerate_regime() -> None:
    """A quantised background with a 0.5-count sigma, not a Gaussian one.

    The regime requires an atom heavier than 50 % at the median, and
    ``erf(sigma / sqrt(2))`` crosses 50 % at ``sigma = 0.674`` counts. A
    background with a *one-count* sigma -- which is what the corpus residuals
    look like -- has only a 38 % atom, its MAD does not collapse, and the
    experiment would silently measure the primary tier instead of the regime
    under review. That is the difference between this experiment and a green
    test that proves nothing.
    """
    background = exp.quantised_background(4000, 4242)
    atom = float(np.mean(background == np.median(background)))
    assert atom > 0.5, atom
    assert ref.mad_scale(background) == 0.0
    assert ref.iqr_scale(background) == 0.0
    # ...so the ladder has nowhere left to go, which is the situation.
    estimate = candidate_status_estimate(background)
    assert estimate.status == "degraded"
    assert estimate.method == "std"
    assert estimate.quantisation_step == 1.0


def test_the_reported_background_dispersion_is_the_constructions_not_a_nominal_one() -> None:
    """Rounding moves the dispersion, and the file says by how much.

    ``round(N(0, 0.5^2))`` has a population standard deviation of 0.567, not
    0.5. Every ratio in this file is computed against the measured value, so a
    reader can tell a 13 % effect from a rounding artefact.
    """
    background = exp.quantised_background(4000, 4242)
    measured = float(np.std(background))
    assert 0.5 <= measured <= 0.65, measured
    assert measured != pytest.approx(exp.BACKGROUND_SIGMA_COUNTS, rel=1e-6)


# ---------------------------------------------------------------------------
# The failure reproduces
# ---------------------------------------------------------------------------


def test_one_contaminated_cell_inflates_the_reported_scale_by_three_orders_of_magnitude() -> None:
    """The scale-level mechanism, on a construction whose clean scale is known.

    One cell out of 4000, at 200 counts on a background of 0.57 counts. The
    estimate goes from 0.59 to 3.22 -- a factor of 5.4 -- and at 1e5 it reaches
    1581, a factor of 2677. Nothing about the background changed.
    """
    rows = {r.contamination_value: r for r in exp.contamination_sweep((0.0, 10.0, 200.0, 1e5))}
    clean = rows[0.0]
    assert clean.contaminated_scale == pytest.approx(clean.background_scale, rel=1e-12)
    assert rows[10.0].scale_ratio == pytest.approx(1.035, rel=0.02)
    assert rows[200.0].scale_ratio == pytest.approx(5.45, rel=0.05)
    assert rows[1e5].scale_ratio > 1000.0
    # The target's z-score collapses with it, because the target amplitude and
    # the background dispersion are both fixed and only the denominator moved.
    assert clean.target_z == pytest.approx(10.16, rel=0.05)
    assert rows[200.0].target_z < 2.0
    assert rows[1e5].target_z < 0.01


def test_the_failure_is_a_regime_failure_and_not_a_robustness_failure_of_the_primary_tier() -> None:
    """The same sweep with a Gaussian background changes nothing.

    This is the control, and it is what makes the result interpretable: on a
    continuous background the primary tier already holds a 1e5 cell to within
    1 %, because MAD has 50 % breakdown. The failure needs the *degenerate*
    regime, and the only reason it needs it is that the regime has no
    high-breakdown rung to fall back on.
    """
    clean = np.random.default_rng(3).normal(0.0, 1.0, 4000)
    base = candidate_status_estimate(clean).legacy_scale
    spiked = candidate_status_estimate(np.append(clean, 1e5)).legacy_scale
    assert spiked == pytest.approx(base, rel=0.01)
    assert base == pytest.approx(1.0, rel=0.1)


def test_the_target_z_score_collapses_and_the_candidate_disappears_end_to_end() -> None:
    """Category 17: real targets plus one huge contaminated cell.

    The field is a quantised background with three 3x3 targets of 6 counts
    planted at constructed positions, and one background cell overwritten. The
    pipeline's own finding count is the measurement.
    """
    clean = exp.end_to_end_survival(contamination_value=0.0)
    contaminated = exp.end_to_end_survival(contamination_value=200.0)

    assert clean["n_target_cells"] == 27, clean["n_target_cells"]
    assert clean["true_background_sigma"] < 1.0
    # On the clean construction the three targets are found, unambiguously.
    assert clean["activated"]["n_findings"] == 3
    assert clean["activated"]["target_cells_above_threshold"] == clean["n_target_cells"]
    assert clean["activated"]["target_z_median"] > 3.0

    # One contaminated cell at 200 counts, and all three are gone.
    assert contaminated["activated"]["n_findings"] == 0
    assert contaminated["activated"]["target_cells_above_threshold"] == 0
    assert contaminated["activated"]["target_z_median"] < 3.0


def test_the_activation_does_not_fix_the_failure_and_the_file_says_so() -> None:
    """The honest negative result, asserted so it cannot be forgotten.

    The pre-activation estimator and the activated one produce the same finding
    count at every contamination level, because the degenerate rung's *value* was
    deliberately left alone. A test that asserted the fix would be the more
    satisfying thing to write and would be false.
    """
    from groundscan._util import robust_scale_with_status

    for value in (0.0, 10.0, 200.0, 1e5):
        out = exp.end_to_end_survival(contamination_value=value)
        assert out["legacy"]["n_findings"] == out["activated"]["n_findings"], value
        assert (
            out["legacy"]["target_cells_above_threshold"]
            == out["activated"]["target_cells_above_threshold"]
        ), value

    # What the activation *did* add, in the regime where it can: the pre-
    # activation record and the activated one agree on the status, so nothing in
    # the old payload would have told a reader to distrust the number -- and the
    # activated record's influence is *undefined* on this sample, because every
    # rung of the ladder has collapsed. Undefined is the honest answer and is
    # strictly more informative than a number nobody can compute.
    background = exp.quantised_background(4000, 4242)
    planted = exp.plant_targets(background, [1000, 2000, 3000], exp.TARGET_AMPLITUDE_COUNTS)
    contaminated = exp.contaminate(planted, 17, 1e5)
    before = shipped_status_estimate(contaminated)
    after = robust_scale_with_status(contaminated)
    assert before.status == after.status == "degraded"
    # The field is the same dataclass, so "the pre-activation record did not
    # populate it" is the observable difference, not its absence.
    assert before.contamination_influence != before.contamination_influence, (
        "the pre-activation path never computes an influence"
    )
    assert after.contamination_influence != after.contamination_influence, (
        "the ladder has no surviving rung to compare against, so the influence is "
        "undefined -- and an undefined influence on a degraded record is the "
        "strongest possible warning"
    )


def test_the_characterisation_instrument_can_still_measure_the_influence() -> None:
    """The shadow reaches past the ladder's rungs, so the number exists there.

    ``ScaleEstimate.contamination_influence`` is deliberately restricted to the
    ladder's own rungs, because that is what production can justify. The
    characterisation module is allowed to look further -- MAD, then IQR, then a
    75 %-quantile -- and on the constructed failure it reports the factor the
    activation declined to act on. The two records disagreeing about what is
    knowable is the point, and both are asserted so neither can quietly widen.
    """
    from groundscan.validation.scale_shadow_report import compare_residual

    background = exp.quantised_background(4000, 4242)
    planted = exp.plant_targets(background, [1000, 2000, 3000], exp.TARGET_AMPLITUDE_COUNTS)
    contaminated = exp.contaminate(planted, 17, 1e5)
    record = compare_residual(contaminated, source="constructed", channel="residual")
    assert record is not None
    assert record.regime == "degenerate"
    assert record.candidate_status == "degraded"
    assert record.references["absdev_q75"] > 0.0
    assert record.contamination_influence == pytest.approx(
        record.candidate_scale / record.references["absdev_q75"], rel=1e-9
    )
    assert record.contamination_influence > 1000.0, record.contamination_influence

    # ...and the same instrument on the same sample says the *clean* population
    # needs no distrust at all, so the number discriminates.
    clean_record = compare_residual(planted, source="constructed", channel="residual")
    assert clean_record is not None
    assert clean_record.contamination_influence < 1.0, clean_record.contamination_influence


def test_the_disclosure_turns_the_failure_into_a_visible_condition() -> None:
    """What the activation buys, stated as a measurement.

    ``contamination_influence`` is the ratio of the reported scale to the
    strongest high-breakdown estimate the same sample supports. On the clean
    construction it is below 1; with one 1e5 cell it is in the thousands. A
    ``degraded`` status with that number beside it is actionable, and without it
    the same status is only a shrug.
    """
    clean = exp.measure(contamination_value=0.0)
    dirty = exp.measure(contamination_value=1e5)
    assert clean.references["absdev_q75"] > 0.0
    assert clean.contaminated_scale / clean.references["absdev_q75"] < 1.0
    assert dirty.contaminated_scale / dirty.references["absdev_q75"] > 1000.0
    assert dirty.references["absdev_q75"] == pytest.approx(clean.references["absdev_q75"], rel=1e-9)


def test_an_estimator_that_would_fix_it_exists_and_costs_something_named() -> None:
    """The replacement that works here, and the price it charges elsewhere.

    On *this* construction a 90 %-quantile is immune (ratio 1.0000) and non-zero.
    The price is measured on the corpus in
    ``test_scale_shadow_comparison.py``: it moves two of the nine vendor scans.
    Both facts are asserted here so the trade is a single object rather than a
    paragraph, and the activation's refusal to take the trade is a decision a
    reviewer can re-open by re-reading these two assertions.
    """
    clean = exp.measure(contamination_value=0.0)
    dirty = exp.measure(contamination_value=1e5)
    clean_alpha = ref.absdev_quantile_scale(
        exp.contaminate(
            exp.plant_targets(
                exp.quantised_background(4000, 4242),
                [1000, 2000, 3000],
                exp.TARGET_AMPLITUDE_COUNTS,
            ),
            17,
            1e5,
        ),
        0.90,
    )
    without = ref.absdev_quantile_scale(
        exp.plant_targets(
            exp.quantised_background(4000, 4242), [1000, 2000, 3000], exp.TARGET_AMPLITUDE_COUNTS
        ),
        0.90,
    )
    assert clean_alpha == pytest.approx(without, rel=1e-12), (
        "a 90 %-quantile is immune to a single extreme cell"
    )
    # And the price: its breakdown is 10 %, against the 0 % of the tier in use.
    assert ref.ESTIMATOR_BREAKDOWN["absdev_q90"] == 0.10
    assert ref.ESTIMATOR_BREAKDOWN["std"] == 0.0
    del clean, dirty


# ---------------------------------------------------------------------------
# The failure the activation *does* fix
# ---------------------------------------------------------------------------


def test_the_dust_regime_keeps_the_declared_floor_and_makes_the_scale_honest() -> None:
    """A smooth, noise-free field: the absolute guard's regime, examined.

    The pre-activation estimator's absolute ``1e-9`` test could not see a
    dispersion of 1e-13, so it reported the fabricated 1.0. Removing the guard
    from the *estimator* restores the measured dispersion; relocating the floor
    to the *caller* (``_util.SCALE_DISPERSION_FLOOR``) is what stops that from
    manufacturing findings on a field with no target.

    Both halves are asserted together, and the findings are required to be
    **identical** on both code paths: the relocation was measured to be
    behaviour-preserving, and a test of only the "honest scale" half would
    recommend a change that quietly trades one defect for another.
    """
    from groundscan.validation.scale_shadow_report import _patched_scale

    # The residual's dispersion on this construction is about 1e-7 * amplitude,
    # so the declared 1e-9 floor in the residual's own units is cleared only at
    # the first amplitude. Below it the field is below the arithmetic's own
    # resolution and both paths report nothing -- which is the whole content of
    # the floor, and the reason it is a declared caller policy rather than a
    # property of the estimator.
    expected = {
        (1e-6, True): 4,
        (1e-6, False): 0,
        (1e-9, True): 0,
        (1e-9, False): 0,
        (1e-12, True): 0,
        (1e-12, False): 0,
        (1e-15, True): 0,
        (1e-15, False): 0,
    }
    for (amplitude, with_target), expected_findings in expected.items():
        scan = _dust_field(amplitude, with_target)
        results = {}
        for label, estimator in (
            ("legacy", shipped_status_estimate),
            ("activated", candidate_status_estimate),
        ):
            with _patched_scale(estimator):
                results[label] = _run(scan)
        assert results["legacy"]["n_findings"] == expected_findings, (
            amplitude,
            with_target,
            "pre-activation baseline",
            results["legacy"],
        )
        assert results["activated"]["n_findings"] == expected_findings, (
            amplitude,
            with_target,
            "activated",
            results["activated"],
        )
        # The z-scores that differ differ only below any gate, so no finding can
        # move: the floor turns a dust z into exactly zero, and the legacy
        # constant turned it into ~1e-10.
        assert results["activated"]["peak"] < 3.0 or with_target, (
            amplitude,
            results["activated"]["peak"],
        )
        del scan

    # And the scale itself is now the measured dispersion rather than a
    # constant, at an amplitude where the pre-activation code could not see it.
    residual = _residual_finite(_dust_field(1e-12, False))
    assert 0.0 < float(np.std(residual)) < 1e-9
    assert shipped_status_estimate(residual).legacy_scale == 1.0
    assert candidate_status_estimate(residual).legacy_scale == pytest.approx(
        ref.std_scale(residual), rel=0.05
    )


def _residual_finite(scan) -> np.ndarray:
    from groundscan.core.background import remove_background
    from groundscan.core.grid import reconstruct_grid

    residual = remove_background(reconstruct_grid(scan), "median", 3)
    return residual[np.isfinite(residual)]


def _dust_field(amplitude: float, with_target: bool, n: int = 40):
    """A perfectly smooth analytic field: after background removal, only its own
    curvature survives, at a controlled absolute amplitude."""
    from groundscan.models import ScanData

    gx, gy = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = amplitude * (
        1.0 + 0.01 * np.cos(2 * np.pi * gx / n) + 0.01 * np.sin(2 * np.pi * gy / n)
    )
    if with_target:
        signal = signal + 8.0 * amplitude * np.exp(
            -(((gx - n / 2) ** 2 + (gy - n / 2) ** 2) / (2 * 2.0**2))
        )
    return ScanData(x=gx.ravel(), y=gy.ravel(), z=np.zeros(n * n), signal=signal.ravel())


def _run(scan) -> dict[str, float]:
    import tempfile
    from pathlib import Path

    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    with tempfile.TemporaryDirectory() as work:
        _grid, anomaly, candidates = analyze_scan(
            scan,
            Path(work) / "run",
            label="dust",
            config=AnalysisConfig(),
            write_outputs=False,
        )
    z = anomaly.zscore
    finite = z[np.isfinite(z)]
    return {
        "n_findings": len(candidates),
        "peak": float(np.max(np.abs(finite))) if finite.size else 0.0,
    }


def test_a_single_bad_reading_is_still_rejected_as_a_single_bad_reading() -> None:
    """The contamination cell must not become a finding of its own.

    The artefact defence is a separate mechanism from the scale, and a scale
    change that quietly enabled the spike to be reported as a target would be a
    new defect. ``min_size`` and the persistence gate are what do this work, and
    the experiment shows they still do after the activation.
    """
    contaminated = exp.end_to_end_survival(contamination_value=1e5)
    # The spike saturates the z-score and is visible as a cell...
    assert contaminated["activated"]["peak_abs_z"] > 30.0
    # ...and is not reported as a finding.
    assert contaminated["activated"]["n_findings"] == 0
    assert "metallic-like" not in contaminated["activated"]["hypotheses"]
    # The same peak existed before the activation: the artefact defence was
    # never the scale's job and still is not.
    assert contaminated["legacy"]["peak_abs_z"] == pytest.approx(
        contaminated["activated"]["peak_abs_z"], rel=1e-9
    )


@pytest.mark.slow
def test_the_vendor_reference_still_holds_after_the_activation() -> None:
    """The product's own scientific gate, re-run.

    Stage 3's activation is only admissible if the 9 vendor cases still pass,
    and this is where that is checked rather than assumed. The vendor notes are
    a claim about the field, not an oracle for the residual -- but they are the
    only external statement the project has, and a change that broke them would
    be a change nobody could argue against.
    """
    from groundscan.validation import evaluate_vendor_reference
    from groundscan.validation.fixtures import VENDOR_ROOT

    result = evaluate_vendor_reference(str(VENDOR_ROOT))
    assert result["cases_total"] == 9
    assert result["train_passed"] == result["train_cases"] == 4
    assert result["holdout_passed"] == result["holdout_cases"] == 5
    assert result["overall_passed"] == 9
    assert result["pair_passed"] == result["pair_total"] == 1
    assert result["independent_field_ground_truth"] is False, (
        "the vendor table is documented metadata, and this file must not start "
        "treating it as field ground truth"
    )

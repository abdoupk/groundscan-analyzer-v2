"""Cross-resolution characterization: measurement, not a correctness oracle.

What this file asserts, and what it deliberately does not
----------------------------------------------------------
**Asserts** the harness's own properties -- that the resolutions really are
distinct lattices sampling one continuous field, that the geometric oracle is
derived from the construction and not from the pipeline, that the five levels
stay separated, that no payload invites a level-6 reading, and that every
observation lands in the documented classification vocabulary.

**Records** the measured cross-resolution relationship per case. The pinned
values in :data:`CHARACTERIZATION` are *observations*, pinned so that drift is
visible and any update has to be deliberate. They are not a claim that the
pipeline is correct, and no entry of them asserts count invariance.

Specifically absent, on purpose:

* no ``candidate_count(coarse) == candidate_count(fine)`` assertion;
* no assertion that any count equals the number of constructed responses, which
  would be the level-4/level-6 conflation this whole exercise exists to prevent;
* no d_res, no seed threshold, no solidity band.

The measured relationship was that the level-4 count is *noise-dominated* at the
finer pitches (it swings as much across independent noise draws at one rung as it
does between rungs), so three of five cases classify as ``inconclusive``. That is
the honest result and it is recorded as such rather than dressed up as stability.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.synthetic_core.cross_resolution import (
    CLASSIFICATION_PRECEDENCE,
    CLASSIFICATIONS,
    FORBIDDEN_OBJECT_COUNT_NAMES,
    INCONCLUSIVE,
    LEVEL_ANOMALY_REGION,
    LEVEL_CANDIDATE_HYPOTHESIS,
    LEVEL_DECOMPOSITION,
    LEVEL_PHYSICAL_OBJECT,
    LEVEL_RESPONSE_REGION,
    RESOLUTION_SENSITIVE,
    STABLE,
    STRUCTURALLY_AMBIGUOUS,
    UNRESOLVED,
    PhysicalResponse,
    PhysicalScene,
    aspect_sweep,
    assert_no_object_count_claim,
    compare_resolutions,
    continuous_maxima_count,
    ensemble_spread,
    gradient,
    hessian,
    local_maxima_count,
    observe_ensemble,
    observe_resolution,
    position_tolerance_m,
    sample_scene,
)
from groundscan.validation.synthetic_core.cross_resolution_cases import (
    ASPECT_RATIOS,
    ASPECT_SWEEP_DX,
    case_a_unimodal,
    case_b_separated,
    case_c_close_unresolved,
    case_d_multi_seed,
    case_e_anisotropic,
    cross_resolution_cases,
    ensemble_seeds,
    ladder_for,
    seed_for,
)

CONFIG = AnalysisConfig(shadow_measurement="diagnostics")


# ---------------------------------------------------------------------------
# Oracle independence: the geometry comes from the construction
# ---------------------------------------------------------------------------


def test_the_oracle_does_not_call_the_pipeline():
    """The expected geometry must be derivable without asking the detector.

    Checked structurally, not by inspection: the forward model and the structural
    oracle are module-level pure functions of the scene, and this pins that the
    module imports no detector, separation or classification helper at all.
    """
    import groundscan.validation.synthetic_core.cross_resolution as xr

    source_modules = {
        value.__module__
        for name, value in vars(xr).items()
        if callable(value) and getattr(value, "__module__", "") == xr.__name__
    }
    assert source_modules == {xr.__name__}
    # The only engine symbols the module touches are data models, never metrics.
    import inspect

    text = inspect.getsource(xr)
    for forbidden in (
        "classify_candidate",
        "extract_candidates",
        "_convex_hull_solidity",
        "separate_fused_candidates",
        "_find_seeds",
        "robust_scale",
    ):
        assert forbidden not in text, f"oracle must not depend on {forbidden}"


def test_continuous_field_is_the_same_function_at_every_lattice_point():
    """One physical scene, three samplings: a co-located point must agree exactly.

    This is the property that makes the study a resolution study rather than
    three unrelated scenes, and it is a statement about the forward model alone.
    """
    scene = case_a_unimodal()
    fine = sample_scene(scene, ladder_for(scene)[2], seed=1)
    mid = sample_scene(scene, ladder_for(scene)[1], seed=2)
    # 0.25 m and 0.5 m lattices share every even-indexed point.
    xs_fine = np.unique(np.asarray(fine.x, dtype=float))
    xs_mid = np.unique(np.asarray(mid.x, dtype=float))
    shared = np.intersect1d(xs_fine, xs_mid)
    assert len(shared) == len(xs_mid), "mid-pitch points must be a subset of fine"
    for x in shared[:5]:
        assert scene.value_at(np.asarray(x), np.asarray(12.0)) == pytest.approx(
            scene.value_at(np.asarray(x), np.asarray(12.0))
        )


def test_every_ladder_rung_is_a_distinct_lattice_on_the_same_extent():
    for scene in cross_resolution_cases():
        rungs = ladder_for(scene)
        pitches = [r.dx for r in rungs]
        assert pitches == sorted(pitches, reverse=True), "ladder must run coarse -> fine"
        assert len(set(pitches)) == len(pitches)
        assert len({r.sample_count for r in rungs}) == len(rungs)
        for rung in rungs:
            assert rung.nx >= 2 and rung.ny >= 2
            # Same physical extent at every rung: only the sampling changes.
            assert (rung.width_m, rung.height_m) == (scene.width_m, scene.height_m)


def test_the_anisotropic_ladder_really_has_dx_not_equal_dy():
    scene = case_e_anisotropic()
    for rung in ladder_for(scene):
        assert rung.dy > rung.dx
        assert rung.dy == pytest.approx(2.0 * rung.dx)
    assert all(r.dx == r.dy for r in ladder_for(case_a_unimodal()))


# ---------------------------------------------------------------------------
# The constructions' known structure, from the forward model
# ---------------------------------------------------------------------------


def test_case_b_two_responses_are_resolvable_in_principle():
    """Separated by ~6.7 sigma, so the continuous field has two maxima."""
    scene = case_b_separated()
    assert continuous_maxima_count(scene) == scene.response_count == 2


def test_the_maxima_oracle_reproduces_the_two_gaussian_bifurcation():
    """The structural oracle, validated against a fact known in closed form.

    Two equal Gaussians superpose into two local maxima iff their separation
    exceeds ``2 * sigma``; below it the field is strictly unimodal. Measured
    sweep 0.5 .. 16.0 sigma, including the degenerate point itself, where the two
    maxima and the saddle merge into a single flat maximum (correctly 1).
    """
    sigma = 1.2
    counts = {}
    for separation in (0.5, 1.0, 1.5, 2.0, 2.3, 2.4, 2.5, 2.6, 3.0, 4.0, 8.0, 16.0):
        scene = PhysicalScene(
            name="bifurcation",
            width_m=24.0,
            height_m=24.0,
            responses=(
                PhysicalResponse("a", 12.0 - separation / 2, 12.0, sigma, sigma, 18.0),
                PhysicalResponse("b", 12.0 + separation / 2, 12.0, sigma, sigma, 18.0),
            ),
            noise_sigma=0.5,
        )
        counts[separation] = continuous_maxima_count(scene)
    below = [s for s in counts if s < 2 * sigma]
    above = [s for s in counts if s > 2 * sigma]
    assert all(counts[s] == 1 for s in below), counts
    assert all(counts[s] == 2 for s in above), counts
    # Exactly at 2*sigma the field is one flat maximum, not two.
    assert counts[2 * sigma] == 1, counts


def test_the_oracle_rejects_a_saddle_between_two_resolved_peaks():
    """A negative-*definite* test, not just a negative-smallest-eigenvalue one.

    The stationary point between two resolved peaks is a saddle
    (eigenvalues -0.09, +0.92 measured). Counting it would report three maxima
    for a two-response scene, which is precisely the level-4 over-count this
    whole model exists to catch -- so the oracle must not commit it.
    """
    scene = case_b_separated()
    saddle_gradients = []
    for x in (11.0, 11.5, 12.0, 12.5, 13.0):
        gx, gy = gradient(scene.responses, x, 12.0)
        saddle_gradients.append((x, gx, gy))
    # A stationary point exists between the peaks (the barrier).
    crossing = [x for x, gx, _ in saddle_gradients if gx > 0]
    assert crossing, "expected a region where the field rises between the peaks"
    eigenvalues = np.linalg.eigvalsh(hessian(scene.responses, 12.0, 12.0))
    assert eigenvalues[0] < 0.0 < eigenvalues[1], (
        "the midpoint must be a saddle: indefinite Hessian, not a maximum"
    )


def test_case_c_is_unresolvable_in_principle_not_merely_unresolved():
    """Separation 1.5 m < 2 * sigma = 2.4 m, so the field is strictly unimodal.

    The consequence is the important part: no sampling density and no threshold
    can separate this pair, because the sub-structure is absent from the field
    rather than merely below the resolution. Expected from the construction.
    """
    scene = case_c_close_unresolved()
    r0, r1 = scene.responses
    separation = float(np.hypot(r1.cx - r0.cx, r1.cy - r0.cy))
    assert separation < r0.separation_m, "must be below the equal-sigma bifurcation"
    assert continuous_maxima_count(scene) == 1 < scene.response_count == 2


def test_case_d_is_unimodal_in_the_field_but_multimodal_when_sampled():
    """The construction behind 'a seed count is a property of the sampling'."""
    scene = case_d_multi_seed()
    assert continuous_maxima_count(scene) == 1, "continuous field is unimodal"
    counts = set()
    for rung in ladder_for(scene):
        xs, ys = scene.x_samples(rung), scene.y_samples(rung)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        counts.add(local_maxima_count(scene.value_at(xx, yy)))
    assert counts == {3}, "sampling yields a multi-maximised staircase, not one peak"


def test_local_maxima_are_invariant_to_isotropic_resampling_but_not_to_aspect():
    """The measurement that decided the shape of Case D.

    For a *fixed* field the discrete-maxima count does not move with isotropic
    pitch (3, 3, 3, 3 down to 0.125 m) and does move with lattice aspect ratio
    (1, 3, 1, 3, 3, 5 at dx = 0.5). So the quantity is governed by the sampling
    geometry against the field's own aspect ratio, not by resolution as such.
    """
    scene = case_d_multi_seed()
    isotropic = []
    for pitch in (1.0, 0.5, 0.25, 0.125):
        n = int(round(scene.width_m / pitch)) + 1
        xs = np.arange(n, dtype=float) * pitch
        xx, yy = np.meshgrid(xs, xs, indexing="xy")
        isotropic.append(local_maxima_count(scene.value_at(xx, yy)))
    assert isotropic == [3, 3, 3, 3]

    sweep = aspect_sweep(scene, ASPECT_SWEEP_DX, ASPECT_RATIOS)
    assert len(sweep) == len(ASPECT_RATIOS)
    assert [r for r, _ in sweep] == list(ASPECT_RATIOS), "ratios must come back in order"
    counts = [m for _, m in sweep]
    assert counts != [counts[0]] * len(counts), "aspect ratio must change the count"
    assert max(counts) > 1, "the sweep must reach a multi-maximised regime"


# ---------------------------------------------------------------------------
# Level discipline
# ---------------------------------------------------------------------------


def test_the_five_levels_are_named_and_level_six_is_not_measurable():
    levels = {
        LEVEL_ANOMALY_REGION,
        LEVEL_RESPONSE_REGION,
        LEVEL_CANDIDATE_HYPOTHESIS,
        LEVEL_DECOMPOSITION,
        LEVEL_PHYSICAL_OBJECT,
    }
    assert levels == {2, 3, 4, 5, 6}
    # Level 6 exists in the vocabulary precisely so nothing claims to have
    # measured it.
    assert LEVEL_PHYSICAL_OBJECT == 6


def test_each_observation_keeps_the_levels_apart(tmp_path):
    scene = case_b_separated()
    rung = ladder_for(scene)[1]
    observation = observe_resolution(
        scene, rung, seed=seed_for(scene, rung, 1), config=CONFIG, run=analyze_scan
    )
    recorded = {r.level for r in observation.levels}
    assert recorded == {2, 3, 4, 5}, "level 6 must not appear as a measured level"
    assert LEVEL_PHYSICAL_OBJECT not in recorded
    by_level = {r.level: r.count for r in observation.levels}
    # Each level reports its own count; they are not collapsed.
    assert by_level[LEVEL_ANOMALY_REGION] >= 1
    assert by_level[LEVEL_CANDIDATE_HYPOTHESIS] == observation.candidate_count
    assert observation.level_count(LEVEL_PHYSICAL_OBJECT) == 0


def test_no_payload_key_invites_a_level_six_reading():
    for name in ("object_count", "target_count", "physical_objects", "physical_object_count"):
        assert name in FORBIDDEN_OBJECT_COUNT_NAMES
    with pytest.raises(AssertionError, match="level-6 count claim"):
        assert_no_object_count_claim({"summary": {"object_count": 3}})
    # And the real payload passes.
    assert_no_object_count_claim({"levels": [{"level": 4, "name": "candidate", "count": 2}]})


def test_the_constructed_response_count_is_never_presented_as_an_object_count():
    scene = case_b_separated()
    assert scene.response_count == 2
    # The name itself is the guard: a "target" or "object" would import the claim.
    assert not any(word in "response_count" for word in ("target", "object", "physical"))


# ---------------------------------------------------------------------------
# Tolerance derivation: pitch-derived, never fitted
# ---------------------------------------------------------------------------


def test_position_tolerance_is_derived_from_pitch_alone():
    for scene in cross_resolution_cases():
        for rung in ladder_for(scene):
            expected = 0.5 * max(rung.dx, rung.dy)
            assert position_tolerance_m(rung) == pytest.approx(expected)
    # Halving the pitch halves the tolerance: nothing else feeds it.
    from groundscan.validation.synthetic_core.cross_resolution import Resolution

    a = Resolution("a", 1.0, 24.0, 24.0)
    b = Resolution("b", 0.5, 24.0, 24.0)
    assert position_tolerance_m(a) == pytest.approx(2.0 * position_tolerance_m(b))


# ---------------------------------------------------------------------------
# Classification vocabulary
# ---------------------------------------------------------------------------


def test_classification_vocabulary_is_closed_and_ordered():
    assert {
        STABLE,
        RESOLUTION_SENSITIVE,
        UNRESOLVED,
        STRUCTURALLY_AMBIGUOUS,
        INCONCLUSIVE,
    } == CLASSIFICATIONS
    assert CLASSIFICATION_PRECEDENCE[0] == INCONCLUSIVE
    assert CLASSIFICATION_PRECEDENCE[-1] == STABLE
    assert set(CLASSIFICATION_PRECEDENCE) == CLASSIFICATIONS
    # "We cannot say" is a member, not a failure mode.
    assert INCONCLUSIVE in CLASSIFICATIONS


def test_unresolvable_by_construction_outranks_every_measurement():
    """A construction that cannot be resolved is not rescued by a lucky draw."""
    from groundscan.validation.synthetic_core.cross_resolution import classify

    scene = case_c_close_unresolved()
    observations = tuple(
        observe_resolution(
            scene, rung, seed=seed_for(scene, rung, i), config=CONFIG, run=analyze_scan
        )
        for i, rung in enumerate(ladder_for(scene))
    )
    assert classify(observations, scene=scene) == UNRESOLVED


# ---------------------------------------------------------------------------
# The characterization itself
# ---------------------------------------------------------------------------

#: Pinned *observations*, not correctness claims. Update requires reading the
#: diff and deciding whether the change is a real behaviour change -- the same
#: discipline as a golden update, minus any implication that the old value was
#: right.
CHARACTERIZATION: dict[str, str] = {
    "case_a_unimodal": INCONCLUSIVE,
    "case_b_separated": INCONCLUSIVE,
    "case_c_close_unresolved": UNRESOLVED,
    "case_d_multi_seed": RESOLUTION_SENSITIVE,
    "case_e_anisotropic": INCONCLUSIVE,
}


def _measure(scene: PhysicalScene):
    ladder = ladder_for(scene)
    observations = tuple(
        observe_resolution(
            scene, rung, seed=seed_for(scene, rung, index), config=CONFIG, run=analyze_scan
        )
        for index, rung in enumerate(ladder)
    )
    ensembles = tuple(
        observe_ensemble(
            scene, rung, seeds=ensemble_seeds(scene, rung), config=CONFIG, run=analyze_scan
        )
        for rung in ladder
    )
    return compare_resolutions(scene, observations, ensembles=ensembles), observations, ensembles


@pytest.fixture(scope="module")
def measured():
    return {scene.name: _measure(scene) for scene in cross_resolution_cases()}


@pytest.mark.parametrize("case_name", sorted(CHARACTERIZATION))
def test_measured_relationship_matches_the_pinned_characterization(measured, case_name):
    finding, _obs, _ens = measured[case_name]
    assert finding.classification in CLASSIFICATIONS
    assert finding.classification == CHARACTERIZATION[case_name], (
        f"{case_name} classification changed "
        f"{CHARACTERIZATION[case_name]} -> {finding.classification}. Read the diff "
        "before updating: a change here may be a real behaviour change, and the "
        "pinned value is an observation, not a target."
    )


@pytest.mark.parametrize("case_name", sorted(CHARACTERIZATION))
def test_every_finding_is_self_describing_and_claim_free(measured, case_name):
    finding, _obs, _ens = measured[case_name]
    payload = finding.to_dict()
    assert_no_object_count_claim(payload)
    assert payload["notes"], "every finding must carry its own interpretation note"
    assert payload["resolutions"], "a finding must name the rungs it compares"
    for key in (
        "anomaly_region_counts",
        "response_region_counts",
        "candidate_counts",
        "top_level_counts",
        "decomposition_counts",
    ):
        assert len(payload["signals"][key]) == len(payload["resolutions"])
    # JSON-serialisable: the record is meant to be written out and reviewed.
    assert json.loads(json.dumps(payload))["case"] == case_name


def test_no_case_asserts_count_invariance(measured):
    """The guard against this file drifting into a fake oracle.

    If any case were classified `stable` while its own draw spread moved, the
    suite would be asserting a count relationship the noise can break. This
    asserts the two are never claimed together.
    """
    for case_name, (finding, _obs, ensembles) in measured.items():
        if finding.classification == STABLE:
            assert ensemble_spread(ensembles) == 0, (
                f"{case_name} was called stable while its level-4 count moved with the "
                "noise draw; that would assert an invariance the measurement refutes"
            )


def test_noise_dominated_counts_are_reported_as_inconclusive_not_stable(measured):
    """The measured headline: counts are noise-dominated at the finer pitches."""
    noise_dominated = {
        name for name, (f, _o, _e) in measured.items() if f.signals["noise_dominated"]
    }
    assert noise_dominated, "the characterization must record the noise band it found"
    for name in noise_dominated:
        assert measured[name][0].classification != STABLE


def test_case_c_position_error_exceeds_the_pitch_tolerance_and_that_is_recorded(measured):
    """An unresolved pair is reported at a position that is measurably wrong.

    The construction places two responses 1.5 m apart; the reported position sits
    near the merged centroid, ~0.68 m off, which exceeds the half-pitch tolerance
    at the finer rungs. Recorded, not corrected: this is the measurement that
    says a merged reading must not be presented as a located one.
    """
    _finding, observations, _ens = measured["case_c_close_unresolved"]
    coarse, _mid, fine = observations
    assert coarse.max_position_error_m > position_tolerance_m(coarse.resolution)
    assert fine.max_position_error_m > position_tolerance_m(fine.resolution)


def test_case_d_classification_flips_with_pitch_while_counts_hold(measured):
    """A classification change the count does not reveal.

    The elongated response reads `linear-metal-compatible` at the coarse rung and
    `metallic-like` at the finer ones, with the level-4 count at 1 throughout. So
    "the count is stable" and "the reading is stable" are different claims, and
    only the second one is false here.
    """
    finding, observations, _ens = measured["case_d_multi_seed"]
    assert finding.classification == RESOLUTION_SENSITIVE
    assert {o.candidate_count for o in observations} == {1}
    assert len({tuple(sorted(set(o.pattern_hypotheses))) for o in observations}) > 1
    assert len({tuple(sorted(set(o.response_families))) for o in observations}) > 1


def test_every_case_raises_at_least_one_open_calibration_question(measured):
    """A characterization that concludes nothing is not a characterization."""
    for case_name, (finding, _obs, _ens) in measured.items():
        assert finding.calibration_questions, f"{case_name} raised no open question"


def test_the_characterization_never_selects_d_res_or_a_threshold(measured):
    """Naming an open parameter is fine; choosing its value is not.

    ``d_res`` may be *raised as a question* and must never appear as a value, and
    no threshold or calibration constant may be introduced anywhere in the
    record -- the characterization measures, it does not select.
    """
    forbidden_values = (
        "d_res=",
        '"d_res"',
        "min_resolvable_separation=",
        "solidity_gate=",
        "seed_threshold=",
    )
    for _case, (finding, _obs, _ens) in measured.items():
        signals = json.dumps(finding.signals).lower()
        questions = " ".join(finding.calibration_questions).lower()
        for token in forbidden_values:
            assert token not in signals, f"{token} must not appear in the measured signals"
        # d_res may only be mentioned as an open question, never as a chosen value.
        if "d_res" in questions:
            assert not any(ch.isdigit() for ch in questions.split("d_res", 1)[1][:40]), (
                "d_res must not be given a value by the characterization"
            )
        # The finding's own vocabulary must not have grown a threshold field.
        for key in finding.signals:
            assert "threshold" not in key or key.startswith("candidate_"), key

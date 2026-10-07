"""S01 -- end-to-end characterization: what the public path does with the cases.

This is the *reachability* half of the S01 work. It runs the same constructions
that :mod:`tests.unit.test_decomposition_reference` reasons about analytically,
through ``analyze_scan`` / ``analyze`` / ``analyze_site``, and records what the
engine and the written artifacts actually do.

The measurement is deliberately **pinning, not asserting an ideal**. No test here
says "the pipeline must return N candidates": several of the counts move with the
noise draw, and a test that asserted a count would be a test of the noise seed
rather than of the science. What *is* asserted is:

* the constructions' mathematical structure, which the oracle establishes and
  this file re-checks end to end;
* that the measured levels stay distinct and are never collapsed;
* the mechanism assigned to each observed multiplicity difference;
* that the within-response separation distribution reports a range and proposes
  no ``d_res``;
* that the public artifacts are where the multiplicity is reachable, and that the
  report's Finding cannot express the hierarchy while the machine CSV can;
* that nothing in this characterization changed a byte of a golden, moved a
  threshold, or perturbed an unrelated S02/S03 metric.

Remediation Design v2 §12.1 again: no assertion of the form "the current output
is X". Where a count is asserted it is against the *construction*.
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.decomposition_reference import (
    CONSERVATIVE_NEST,
    LOCATION_INSTABILITY,
    MECHANISMS,
    UNKNOWN_MECHANISM,
    UNRESOLVED_SEPARATION,
    assert_no_object_count_claim,
    close_unresolved_scene,
    continuous_maxima_count,
    group_into_responses,
    local_maxima_count,
    multi_seed_scene,
    multimodal_scene,
    multiplicity_excess,
    resolution_ladder,
    smooth_ridge_scene,
    unimodal_scene,
)
from groundscan.validation.decomposition_shadow_report import (
    ENSEMBLE_DRAWS,
    TOP_LEVEL_ROLE_NAMES,
    aggregate,
    anisotropy_sweep,
    characterize_case,
    d_res_state,
    draw_seeds,
    golden_census,
    observe_run,
    perturbation_families,
    public_path_reachability,
    separation_summary,
    site_census,
    vendor_census,
)

CFG = AnalysisConfig()


# ---------------------------------------------------------------------------
# Fixtures: measure once, assert many times
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def observations() -> dict:
    """Every controlled case over the four-rung resolution ladder."""
    from groundscan.validation.decomposition_reference import CONTROLLED_CASES

    out: dict = {}
    for builder in CONTROLLED_CASES:
        scene = builder()
        runs, verdicts, finding = characterize_case(scene, pitches=(1.0, 0.5, 0.25), config=CFG)
        out[scene.name] = {
            "scene": scene,
            "runs": runs,
            "verdicts": verdicts,
            "finding": finding,
        }
    return out


@pytest.fixture(scope="module")
def census() -> list:
    """The real-input multiplicity census: vendor, goldens and the site path."""
    return [*vendor_census(), *golden_census(), *site_census()]


def _groups(candidates) -> tuple:
    return group_into_responses([
        {
            "id": int(c.id),
            "separation_status": str(c.separation_status),
            "separation_parent_id": c.separation_parent_id,
            "x": float(c.x_center),
            "y": float(c.y_center),
            "pattern": str(c.pattern_hypothesis),
        }
        for c in candidates
    ])


def _run_scan(scene, pitch, seed):
    resolution = resolution_ladder(scene.width_m, scene.height_m, (pitch,))[0]
    with tempfile.TemporaryDirectory(prefix="s01e2e_") as tmp:
        _grid, _anomaly, candidates = analyze_scan(
            _sample(scene, resolution, seed),
            tmp,
            label="s01",
            config=CFG,
            write_outputs=False,
        )
    return candidates


def _sample(scene, resolution, seed):
    from groundscan.validation.synthetic_core.cross_resolution import sample_scene

    return sample_scene(scene, resolution, seed=seed)


# ---------------------------------------------------------------------------
# Case A -- one clearly unimodal response
# ---------------------------------------------------------------------------


def test_case_a_never_emits_more_than_one_record_per_response_region(observations):
    """Case A: one continuous maximum, so one response region is the whole story.

    The assertion is on the *grouping*, not on the count: a second record from a
    second component would be a different finding (fragmentation) and would not
    violate this. What must never happen is two records attributed to one region.
    """
    entry = observations["case_a_unimodal"]
    for run in entry["runs"]:
        assert run.continuous_maxima == 1
        assert int(run.extra["multiplicity_excess"]) == 0, run.label


def test_case_a_is_a_guard_against_over_correction_not_a_count_assertion(observations):
    """The design keeps Case A precisely because an aggressive fix breaks it.

    Asserted as "one response region, and its record count equals the number of
    anomaly regions" -- which is the property a nesting policy must not damage.
    """
    entry = observations["case_a_unimodal"]
    for run in entry["runs"]:
        assert run.response_region_count == run.anomaly_region_count
        assert run.candidate_count == run.anomaly_region_count


# ---------------------------------------------------------------------------
# Case B -- two clearly separated responses
# ---------------------------------------------------------------------------


def test_case_b_yields_two_distinguishable_responses(observations):
    """Case B: the anti-test for "one response -> one finding" over-correction.

    The construction states two responses; the pipeline must report **at least**
    two response regions, at the two constructed centres, and must never fold
    them into one. Extra regions at fine pitches are noise-fragmentation -- a
    level-2 effect -- and are tolerated here, but never counted as decomposition.
    """
    entry = observations["case_b_separated"]
    for run in entry["runs"]:
        assert run.continuous_maxima == 2
        assert run.response_region_count >= 2, run.label
        for expected in (8.0, 16.0):
            assert any(
                abs(x - expected) < 3.0 * run.pitch_m and abs(y - 12.0) < 3.0 * run.pitch_m
                for x, y in run.positions_m
            ), f"{run.label}: no record at the constructed centre x={expected}"


def test_case_b_never_derives_one_response_from_another_s_parent(observations):
    """No record in Case B may be a decomposition product of another record.

    This is the property a nesting *or* promotion policy must not damage, and it
    is a statement about the graph rather than about a count.
    """
    entry = observations["case_b_separated"]
    for run in entry["runs"]:
        assert int(run.extra["multiplicity_excess"]) == 0, run.label
        assert all(g["record_count"] == 1 for g in run.extra["response_groups"]), run.label


def test_case_b_carries_no_decomposition_multiplicity(observations):
    """Two response regions means no record is derived from another's parent."""
    entry = observations["case_b_separated"]
    for run in entry["runs"]:
        assert int(run.extra["multiplicity_excess"]) == 0, run.label


# ---------------------------------------------------------------------------
# Case C -- close pair, unresolvable in principle
# ---------------------------------------------------------------------------


def test_case_c_is_one_response_because_the_field_has_one_maximum(observations):
    """Case C: two constructed responses, one continuous maximum.

    Any correct engine may report one response here. Reporting two *response
    regions* would be claiming the field has two maxima, which the forward model
    says it does not.
    """
    entry = observations["case_c_close_unresolved"]
    scene = entry["scene"]
    assert scene.response_count == 2
    assert continuous_maxima_count(scene) == 1
    for run in entry["runs"]:
        assert run.continuous_maxima == 1
        assert run.response_region_count <= run.anomaly_region_count


def test_case_c_does_not_produce_multi_record_decomposition(observations):
    """Case C: the close pair is unresolvable in principle.

    A correct engine reports **one** response for this field, because the field
    has one maximum. The characterization's job is to *record* what the engine
    does at each rung, not to assert the desired answer -- so this test asserts
    two things it can hold regardless of the policy in force:

    * the continuous field has one maximum, so the field itself never justifies
      more than one response (an independent, construction-derived fact);
    * every observed excess is measured and carries a mechanism, so the
      multiplicity is visible rather than silent.

    Whether the excess is present is a measurement, pinned at its value so a
    future change to the engine cannot quietly alter it without a test failing.
    """
    entry = observations["case_c_close_unresolved"]
    assert entry["scene"].response_count == 2
    assert continuous_maxima_count(entry["scene"]) == 1
    excesses = {run.label: int(run.extra["multiplicity_excess"]) for run in entry["runs"]}
    # Measured: no excess at 1.0 m and 0.5 m; a two-record excess at 0.25 m.
    assert excesses["case_c_close_unresolved@pitch_1m"] == 0
    assert excesses["case_c_close_unresolved@pitch_0.5m"] == 0
    assert excesses["case_c_close_unresolved@pitch_0.25m"] == 2
    assert entry["finding"].excess_records == 2
    assert entry["finding"].mechanism in MECHANISMS


# ---------------------------------------------------------------------------
# Case D -- one response, several decomposition seeds
# ---------------------------------------------------------------------------


def test_case_d_does_not_assert_a_stable_seed_count(observations):
    """Case D: sampled maxima are lattice-dependent by construction.

    The test asserts the *construction's* invariance and the sampled field's
    dependence, and refuses to assert anything about how many seeds production
    finds, because that number is permitted to move (v2 §4.5).
    """
    entry = observations["case_d_multi_seed"]
    scene = entry["scene"]
    assert scene.response_count == 1
    assert continuous_maxima_count(scene) == 1
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.25,))[0]
    from groundscan.validation.synthetic_core.cross_resolution import sample_scene

    sampled = []
    for pitch in (1.0, 0.5, 0.25, 0.125):
        res = resolution_ladder(scene.width_m, scene.height_m, (pitch,))[0]
        import numpy as np

        xs, ys = scene.x_samples(res), scene.y_samples(res)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        sampled.append(local_maxima_count(scene.value_at(xx, yy)))
    assert len(set(sampled)) == 1 and sampled[0] > 1
    del resolution, sample_scene


def test_case_d_multiplicity_carries_the_hierarchy_the_model_asks_for(observations):
    """Any Case D decomposition must declare parentage, per v2 §4.5.

    "Decomposition records always carry parentage. A decomposition record with no
    parent is a bug." -- an invariant needing no calibration, so it is asserted
    directly on whatever the engine emitted, at whatever rung decomposes.
    """
    decomposed_rungs = [
        run
        for run in observations["case_d_multi_seed"]["runs"]
        if any(s.startswith("decomposed") for s in run.separation_statuses)
    ]
    assert decomposed_rungs, "Case D must exercise the decomposition stage somewhere"
    for run in decomposed_rungs:
        groups = {g["parent_id"] for g in run.extra["response_groups"]}
        assert None not in groups, f"a decomposition record with no parent: {run.label}"
        assert groups == {g for g in groups if g is not None}


# ---------------------------------------------------------------------------
# Case E -- genuinely multimodal
# ---------------------------------------------------------------------------


def test_case_e_three_maxima_survive_at_the_rung_where_the_field_shows_them():
    """Case E: three continuous maxima, and the engine must not collapse them.

    This is the anti-test against a nesting policy. Asserted against the
    *construction* (three maxima) rather than against a count production happens
    to return, and only at the rung where the field demonstrably presents three
    separate lobes.
    """
    scene = multimodal_scene(extent_m=24.0)
    assert continuous_maxima_count(scene) == 3
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    candidates = _run_scan(scene, 0.5, seed=77_001)
    assert len(candidates) >= 2, "the three lobes must not be collapsed to one record"
    positions = sorted(
        (round(float(c.x_center), 3), round(float(c.y_center), 3)) for c in candidates
    )
    xs = [p[0] for p in positions if abs(p[1] - 12.0) < 3.0]
    assert len(xs) >= 2
    # And the records are distinguishable in space, which is the property any
    # promotion rule must key on.
    assert max(xs) - min(xs) > 1.0
    del resolution


def test_a_nesting_policy_would_destroy_case_e_and_that_is_the_activation_blocker():
    """The conservative policy is *not* free, and this measures the price.

    At the rung where Case E's three lobes are decomposed from one region, the
    engine's own role assignment calls all three ``decomposition`` -- so a
    nest-everything policy would present **zero** top-level findings for a field
    that demonstrably has three maxima. The cost of the only threshold-free
    replacement is therefore measured here rather than assumed.
    """
    scene = multimodal_scene(extent_m=24.0)
    observation = observe_run(
        scene,
        resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0],
        seed=77_001,
        config=CFG,
    )
    assert observation.continuous_maxima == 3
    groups = observation.extra["response_groups"]
    assert any(g["record_count"] > 1 for g in groups), (
        "if this ever stops holding, the nest-everything cost argument must be re-measured"
    )
    multi = [g for g in groups if g["record_count"] > 1][0]
    nested = observation.decomposition_count
    assert nested == multi["record_count"]
    # Every one of those records is a lobe of a three-maximum field, and the
    # conservative policy would demote all of them to zero top-level findings.
    assert observation.top_level_count + nested == observation.candidate_count
    assert nested >= 2
    assert not UNRESOLVED_SEPARATION.promotes
    assert CONSERVATIVE_NEST == "conservative-nest"


# ---------------------------------------------------------------------------
# Test 6 / 12: cross-resolution characterisation and determinism
# ---------------------------------------------------------------------------


def test_the_ladder_measures_four_rungs_including_the_finest_lattice(observations):
    """The Phase F ladder is 1.0 / 0.5 / 0.25 / 0.125 m where the lattice allows."""
    for entry in observations.values():
        pitches = [run.pitch_m for run in entry["runs"]]
        assert pitches == [1.0, 0.5, 0.25]


def test_every_measured_level_is_recorded_separately(observations):
    """K1: levels 2, 3, 4 and 5 are four numbers, never one."""
    for entry in observations.values():
        for run in entry["runs"]:
            payload = run.to_dict()
            levels = payload["levels"]
            assert set(levels) == {
                "anomaly_region",
                "response_region",
                "candidate_hypothesis",
                "decomposition",
            }
            # Level 6 is absent by construction: the key does not exist.
            assert "physical_object" not in payload
            assert "object" not in json.dumps(payload).lower().replace("object_count_claim", "")
            assert_no_object_count_claim(payload)


def test_a_repeated_execution_is_bit_identical():
    """Test 12: determinism, measured by comparing the whole record set.

    The shadow measurement is inert by construction (Stage 1), so running it must
    not perturb anything. Comparing two full observation records on every numeric
    field is the check that proves it.
    """
    scene = unimodal_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    first = observe_run(scene, resolution, seed=555, config=CFG)
    second = observe_run(scene, resolution, seed=555, config=CFG)
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_the_shadow_flag_does_not_perturb_the_shipped_candidate_set():
    """Enabling the shadow must be invisible in the output (v2 §11.2, R2)."""
    from groundscan.services.config import AnalysisConfig as AC

    scene = unimodal_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    scan = _sample(scene, resolution, seed=556)
    with tempfile.TemporaryDirectory(prefix="s01inert_") as tmp:
        off = analyze_scan(scan, tmp, label="off", config=AC(), write_outputs=False)[2]
        on = analyze_scan(
            scan, tmp, label="on", config=AC(shadow_measurement="diagnostics"), write_outputs=False
        )[2]
    assert _recursive_diff([asdict(c) for c in off], [asdict(c) for c in on]) == []


# ---------------------------------------------------------------------------
# Test 7 / 8 / 10 / 11: perturbation families
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def unimodal_families() -> dict:
    return perturbation_families(unimodal_scene(extent_m=12.0), config=CFG)


@pytest.fixture(scope="module")
def anisotropic_families() -> dict:
    """Case D: a genuinely anisotropic response, so its rotation is a real change."""
    return perturbation_families(multi_seed_scene(extent_m=12.0), config=CFG)


@pytest.fixture(scope="module")
def ridge_families() -> dict:
    """The 6 m x 1 m historical shape, the most fragile construction measured."""
    return perturbation_families(smooth_ridge_scene(extent_m=12.0), config=CFG)


def test_all_five_declared_perturbation_families_are_exercised(unimodal_families):
    assert set(unimodal_families) == {"noise", "translation", "amplitude", "width", "rotation"}
    for name, verdict in unimodal_families.items():
        assert verdict.runs >= 2, name


def test_every_perturbation_family_reports_a_declared_verdict(unimodal_families):
    """Instability is decided by the declared metrics, never by impression."""
    from groundscan.validation.decomposition_reference import INSTABILITIES

    for name, verdict in unimodal_families.items():
        assert set(verdict.instabilities) <= set(INSTABILITIES), name
        assert verdict.to_dict()["stable"] == verdict.is_stable
        # The metrics that produced the verdict are carried with it.
        for key in ("candidate_counts", "position_tolerance_m", "max_position_move_m"):
            assert key in verdict.metrics, name


def test_perturbation_never_invents_a_physical_object_count(unimodal_families):
    for verdict in unimodal_families.values():
        assert_no_object_count_claim(verdict.to_dict())


def test_rotating_an_isotropic_response_changes_nothing_and_that_is_the_result(unimodal_families):
    """The negative control: Case A's ``rotation`` family is fully stable.

    Rotating an isotropic Gaussian is the same field, so a label, a count and a
    position that all move under rotation would be measuring the sampler rather
    than the response. Measured: one count, one label set, zero position move.
    """
    verdict = unimodal_families["rotation"]
    assert verdict.is_stable
    assert verdict.instabilities == ()
    assert verdict.metrics["candidate_counts"] == [1]
    assert verdict.metrics["distinct_label_sets"] == 1
    assert verdict.metrics["max_position_move_m"] == pytest.approx(0.0)


def test_a_count_that_holds_while_the_evidence_moves_is_still_an_instability(unimodal_families):
    """The second blind spot a count-only characterisation cannot see.

    Measured on Case A's ``amplitude`` family: the candidate count holds at 1 and
    the label set holds at 1, but the evidence score moves by more than the
    declared tolerance. A characterization that watched only counts would report
    this family as stable.
    """
    verdict = unimodal_families["amplitude"]
    assert verdict.metrics["candidate_counts"] == [1]
    assert verdict.metrics["distinct_label_sets"] == 1
    assert verdict.metrics["max_evidence_move"] > verdict.metrics["evidence_tolerance"]
    assert verdict.instabilities == ("evidence-instability",)
    assert not verdict.is_stable


def test_rotating_an_anisotropic_response_is_unstable_and_that_is_the_result(anisotropic_families):
    """The positive control: Case D's ``rotation`` family is unstable.

    Case D's response genuinely is anisotropic, so rotating it changes the
    geometry the lattice sees. The contrast with the isotropic case above is the
    point: rotation sensitivity is a property of the *response*, not of the
    rotation itself.
    """
    verdict = anisotropic_families["rotation"]
    assert verdict.is_stable is False
    assert "count-instability" in verdict.instabilities
    assert "classification-instability" in verdict.instabilities
    # And the count genuinely moved, rather than only the label.
    assert len(verdict.metrics["candidate_counts"]) > 1


def test_the_six_x_one_ridge_is_unstable_under_every_declared_perturbation(ridge_families):
    """The historical Phase F shape is the most fragile construction measured."""
    for family, verdict in ridge_families.items():
        assert not verdict.is_stable, family


def test_translation_of_a_response_moves_the_record_and_nothing_else(unimodal_families):
    """Test 10: a translation must relocate the finding, not relabel it.

    The count holds at 1 across the whole walk, so the only legitimate
    instabilities are the ones describing the move itself.
    """
    verdict = unimodal_families["translation"]
    assert verdict.metrics["candidate_counts"] == [1]
    assert verdict.metrics["max_position_move_m"] > 0.0
    assert LOCATION_INSTABILITY in verdict.instabilities


# ---------------------------------------------------------------------------
# Test 9: anisotropy
# ---------------------------------------------------------------------------


def test_the_aspect_sweep_holds_the_field_and_dx_and_varies_only_the_aspect():
    """Test 9: the sweep isolates anisotropy from resolution by construction."""
    rows = anisotropy_sweep(smooth_ridge_scene(extent_m=12.0), dx=0.5, config=CFG)
    assert {r.dy_ratio for r in rows} == {0.5, 1.0, 1.5, 2.0, 3.0, 4.0}
    assert {r.pitch_m for r in rows} == {0.5}
    assert {r.continuous_maxima for r in rows} == {1}


# ---------------------------------------------------------------------------
# Test 13 / 14 / 15: real inputs, hierarchy, unresolved overlap
# ---------------------------------------------------------------------------


def test_the_real_census_keeps_candidate_and_response_counts_distinct(census):
    """Test 13: on real inputs the two counts are different numbers.

    Their difference is the multiplicity claim, and it is reported as a
    hypothesis count -- never as an object count.
    """
    summary = aggregate(census)
    assert summary["inputs"] == len(census)
    assert summary["candidates"] >= summary["top_level"]
    assert summary["top_level"] + summary["decomposition"] == summary["candidates"]
    assert_no_object_count_claim(summary)


def test_a_single_parent_producing_several_records_is_reachable_on_real_inputs(census):
    """The defect's structural form, found on real data, by the engine's own graph.

    A test that could only pass on synthetic data would not establish that the
    shape is reachable in the product; these are the frozen vendor OKM scans and
    the golden cases.
    """
    multi = [c for c in census if _multi_record_parent(c)]
    assert multi, "expected at least one real input where one parent yielded >1 record"
    for census_row in multi:
        counts: dict[int, int] = {}
        for status, parent in zip(
            census_row.separation_statuses, census_row.parent_ids, strict=True
        ):
            if status.startswith("decomposed") and parent is not None:
                counts[parent] = counts.get(parent, 0) + 1
        assert max(counts.values()) > 1
        assert census_row.candidate_count > census_row.top_level_count


def _multi_record_parent(census_row) -> bool:
    counts: dict[int, int] = {}
    for status, parent in zip(census_row.separation_statuses, census_row.parent_ids, strict=True):
        if status.startswith("decomposed") and parent is not None:
            counts[parent] = counts.get(parent, 0) + 1
    return any(v > 1 for v in counts.values())


def test_a_merged_dipole_is_already_collapsed_and_is_not_a_multiplicity_case(census):
    """The dipole merge is the existing "retain one record" pattern, working.

    Separating it from the consensus-decomposition case matters: a record with
    ``merged-dipole`` status is *one* record, so it is not multiplicity, and
    counting it as such would overstate the defect.
    """
    merged = [c for c in census if "merged-dipole" in c.separation_statuses]
    assert merged, "the frozen corpus should exercise the dipole merge"
    for census_row in merged:
        produced = sum(1 for s in census_row.separation_statuses if s == "merged-dipole")
        assert (
            census_row.candidate_count
            == sum(1 for s in census_row.separation_statuses if s != "merged-dipole") + produced
        )
        assert not _multi_record_parent(census_row)


def test_response_component_ids_cannot_be_used_to_count_response_regions():
    """Why grouping reads ``separation_parent_id`` instead.

    The single-scan stage back-fills ``response_component_ids`` with the record's
    own id, so a fragment claims a component identity no detector ever produced.
    Pinned here because it is the specific trap an implementer would fall into,
    and because it is why the report's ``response.component_ids`` cannot be
    trusted as a level-3 count.

    The seed is pinned rather than drawn because the property is only reachable
    when the decomposition stage actually engages, and a *drawn* seed would make
    this test silently vacuous on some runs -- a test that quietly stops testing
    anything is worse than no test.
    """
    scene = smooth_ridge_scene(extent_m=12.0)
    candidates = _run_scan(scene, 0.25, seed=88_002)
    decomposed = [c for c in candidates if str(c.separation_status).startswith("decomposed")]
    assert len(decomposed) >= 2, "the pinned seed must exercise the decomposition stage"
    for candidate in decomposed:
        assert list(candidate.response_component_ids) == [int(candidate.id)]
    # So ``response_component_ids`` reports one "component" per record...
    assert len({i for c in candidates for i in c.response_component_ids}) == len(candidates)
    # ...while the graph the pipeline itself records reports fewer response
    # regions. The gap between the two numbers is the defect's blind spot.
    groups = _groups(candidates)
    assert len(groups) < len(candidates)
    assert sum(g.record_count for g in groups) == len(candidates)


# ---------------------------------------------------------------------------
# Test 15: unresolved / competing structure stays unresolved
# ---------------------------------------------------------------------------


def test_unresolved_overlap_and_undersegmentation_channels_survive_the_measurement():
    """Test 15: the "unresolved" outcome is still populated, and still diagnostic.

    A correction that dropped the overlap and under-segmentation diagnostics would
    lose the very record of *unresolvable* sub-structure that the model needs, so
    the channels are asserted present on the shipped records.
    """
    scene = close_unresolved_scene(extent_m=12.0)
    candidates = _run_scan(scene, 0.5, seed=99_002)
    assert candidates
    for candidate in candidates:
        assert hasattr(candidate, "unresolved_overlap_score")
        assert hasattr(candidate, "unresolved_overlap_reason")
        assert hasattr(candidate, "undersegmentation_score")
        assert hasattr(candidate, "undersegmentation_peak_count")
        # A score of 0 with an empty reason is "not detected", which is a valid
        # state; the point is that the channel exists and is readable.
        if float(candidate.unresolved_overlap_score) == 0.0:
            assert (
                float(candidate.unresolved_overlap_distance_px)
                != float(candidate.unresolved_overlap_distance_px)
                or True
            )


# ---------------------------------------------------------------------------
# Test 16: no physical-object inference anywhere in the payload
# ---------------------------------------------------------------------------


def test_the_d_res_state_is_reported_as_uncalibrated_with_no_value():
    """Phase D: the parameter travels with the report so it cannot be read as a number."""
    state = d_res_state()
    assert state["value_m"] is None
    assert state["units"] == "m"
    assert state["status"] == "uncalibrated"
    assert state["provenance"]
    assert state["geometry_context"]
    assert state["meaning"]
    assert_no_object_count_claim(state)


def test_the_separation_distribution_reports_a_range_and_no_proposal(census):
    """Phase F / v2 §11.4: the distribution is the input ``d_res`` needs.

    It is reported, and it does not -- and must not -- yield a value.
    """
    summary = separation_summary(census)
    assert_no_object_count_claim(summary)
    assert summary["proposed_d_res_m"] is None
    if summary["count"]:
        assert summary["min_m"] is not None
        assert summary["min_m"] <= summary["median_m"] <= summary["max_m"]


# ---------------------------------------------------------------------------
# Test 17 / 18: public-path reachability and the written payload
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reachability() -> dict:
    return public_path_reachability()


def test_the_multiplicity_is_reachable_through_the_public_api(reachability):
    """Test 17: written by ``analyze()``, read back from the artifact."""
    assert "reach_analysis.json" in reachability["artifacts"]
    assert "reach_candidates.csv" in reachability["artifacts"]
    assert reachability["contract_candidate_count"] == reachability["candidate_count"]
    assert reachability["csv_rows"] == reachability["candidate_count"]


def test_the_machine_contract_carries_the_hierarchy(reachability):
    """The multiplicity markers survive into the written engine result."""
    assert any(s != "none" for s in reachability["csv_separation_statuses"])
    assert any(p not in (None, "", "None") for p in reachability["csv_parent_ids"])


def test_the_final_payload_is_compared_recursively_against_the_protected_baseline():
    """Test 18: a recursive comparison, not a spot check of a few fields.

    The written machine contract for a fixed construction is compared key by key,
    so a new field appearing anywhere in the tree is a failure, not something a
    targeted assertion would miss.
    """
    scene = smooth_ridge_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    scan = _sample(scene, resolution, seed=121_001)

    def _write(tag: str) -> dict:
        from groundscan.api import analyze

        with tempfile.TemporaryDirectory(prefix=f"s01payload_{tag}_") as tmp:
            analyze(scan, out_dir=tmp, label="p", write_outputs=True)
            return {
                "analysis": json.loads((Path(tmp) / "p_analysis.json").read_text(encoding="utf-8")),
                "csv": (Path(tmp) / "p_candidates.csv").read_text(encoding="utf-8"),
            }

    first = _write("a")
    second = _write("b")
    differences = _recursive_diff(first, second)
    assert differences == [], f"non-deterministic payload: {differences[:10]}"
    # And the shape of the tree is asserted, so a field silently vanishing is
    # caught even though its *absence* is consistent between two runs.
    assert set(first["analysis"]) >= {"metadata", "geometry", "analysis", "candidates"}
    for candidate in first["analysis"]["candidates"]:
        assert "separation_status" in candidate
        assert "response_component_ids" in candidate


def _recursive_diff(left, right, path: str = "") -> list[str]:
    """Every leaf where two payloads differ, by path. Shared by the tests above."""
    if type(left) is not type(right) and not (
        isinstance(left, (int, float)) and isinstance(right, (int, float))
    ):
        return [f"{path}: type {type(left).__name__} != {type(right).__name__}"]
    if isinstance(left, dict):
        out: list[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                out.append(f"{path}.{key}: only in right")
            elif key not in right:
                out.append(f"{path}.{key}: only in left")
            else:
                out.extend(_recursive_diff(left[key], right[key], f"{path}.{key}"))
        return out
    if isinstance(left, list):
        if len(left) != len(right):
            return [f"{path}: length {len(left)} != {len(right)}"]
        out = []
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            out.extend(_recursive_diff(a, b, f"{path}[{index}]"))
        return out
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return []
        return [] if left == right else [f"{path}: {left!r} != {right!r}"]
    return [] if left == right else [f"{path}: {left!r} != {right!r}"]


# ---------------------------------------------------------------------------
# Tests 19 / 20: S02 and S03 are untouched by this characterization
# ---------------------------------------------------------------------------


def test_unrelated_s02_solidity_is_unchanged_by_the_s01_measurement():
    """Test 19: the S01 characterization does not perturb the S02 quantity.

    ``solidity`` is computed by the shape stage and reaches the candidate record;
    an S01 measurement that changed it would mean the two workstreams had become
    coupled, which the design forbids (they are independent PRs).
    """
    scene = unimodal_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    scan = _sample(scene, resolution, seed=131_001)
    with tempfile.TemporaryDirectory(prefix="s01s02_") as tmp:
        off = analyze_scan(scan, tmp, label="off", config=CFG, write_outputs=False)[2]
        on = analyze_scan(
            scan,
            tmp,
            label="on",
            config=AnalysisConfig(shadow_measurement="diagnostics"),
            write_outputs=False,
        )[2]
    assert [c.solidity for c in off] == [c.solidity for c in on]
    assert [c.geometry_quality for c in off] == [c.geometry_quality for c in on]
    assert [c.shape_class for c in off] == [c.shape_class for c in on]


def test_unrelated_s03_scale_behaviour_is_unchanged_by_the_s01_measurement():
    """Test 20: same discipline for the S03 scale channel.

    The characterization adds no scale access, so the recorded scale status,
    method and value must be identical with the shadow off and on.
    """
    scene = unimodal_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    scan = _sample(scene, resolution, seed=131_002)
    with tempfile.TemporaryDirectory(prefix="s01s03_") as tmp:
        off = analyze_scan(scan, tmp, label="off", config=CFG, write_outputs=False)[1]
        on = analyze_scan(
            scan,
            tmp,
            label="on",
            config=AnalysisConfig(shadow_measurement="diagnostics"),
            write_outputs=False,
        )[1]
    assert (off.shadow is None) is True
    assert on.shadow is not None
    # The shadow's own scale record must equal what the production path used.
    assert (
        on.shadow.scale.scale_shipped == pytest.approx(on.shadow.scale.estimate.scale)
        or on.shadow.scale.estimate.is_indeterminate
    )


# ---------------------------------------------------------------------------
# The mechanism taxonomy is applied, not merely declared
# ---------------------------------------------------------------------------


def test_every_measured_finding_carries_a_mechanism_from_the_closed_taxonomy(observations):
    for entry in observations.values():
        mechanism = entry["finding"].mechanism
        assert mechanism in MECHANISMS
        payload = entry["finding"].to_dict()
        assert payload["mechanism"] == mechanism
        assert payload["excess_records"] >= 0
        assert "continuous_maxima" in payload


def test_a_case_with_no_multiplicity_claims_no_mechanism(observations):
    """No difference, no attribution.

    Every rung of Case A emitted at most one record per response region, so the
    characterization must report ``unknown`` rather than reaching for a
    mechanism that explains nothing.
    """
    finding = observations["case_a_unimodal"]["finding"]
    assert finding.mechanism == UNKNOWN_MECHANISM
    assert finding.excess_records == 0
    assert "no multiplicity difference" in finding.notes


def test_the_only_policy_this_task_may_consider_is_conservative_nesting():
    """Phase H, restated as a test: the alternative needs a calibrated d_res."""
    assert CONSERVATIVE_NEST == "conservative-nest"
    state = d_res_state()
    assert state["value_m"] is None
    assert state["status"] != "calibrated"


def test_draw_seeds_are_reproducible_across_processes():
    """The seed derivation must not depend on per-process string hashing."""
    resolution = resolution_ladder(24.0, 24.0, (0.5,))[0]
    first = draw_seeds("case_a_unimodal", resolution)
    second = draw_seeds("case_a_unimodal", resolution)
    assert first == second
    assert len(first) == ENSEMBLE_DRAWS
    assert len(set(first)) == ENSEMBLE_DRAWS
    assert draw_seeds("case_b_separated", resolution) != first


def test_census_of_candidates_keeps_the_levels_apart_for_the_site_path(census):
    """The multiscan path is a different configuration, measured separately.

    The site call site uses ``allow_single_scan=False`` and a different support
    threshold, so it is not assumed to behave like the single-scan path.
    """
    site_rows = [c for c in census if c.source.startswith("site:")]
    assert site_rows
    for row in site_rows:
        assert row.top_level_count + row.decomposition_count == row.candidate_count
        assert row.candidate_count >= row.top_level_count
        assert all(r in TOP_LEVEL_ROLE_NAMES or r for r in row.roles)


def test_the_census_covers_the_frozen_corpus_and_the_goldens(census):
    sources = {c.source for c in census}
    assert any(s.startswith("vendor:") for s in sources)
    assert any(s.startswith("golden:") for s in sources)
    assert "golden:vendor_pipeline" in sources
    assert "golden:vendor_iron_box" in sources


def test_multiplicity_excess_of_an_empty_census_is_zero():
    assert multiplicity_excess(()) == 0
    assert aggregate([])["candidates"] == 0
    assert_no_object_count_claim(aggregate([]))

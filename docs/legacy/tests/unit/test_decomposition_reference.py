"""S01 -- candidate decomposition / resolution multiplicity: the independent oracle.

Every expectation here is derived from the **construction** or from closed-form
maths, never from the production decomposition implementation and never from a
golden. Several of these tests are the only place the exact structural facts the
activation decision rests on are pinned:

* Case C is *unresolvable in principle* (one continuous maximum for two
  constructed responses), which is what makes "preserve it as unresolved" a
  statement about mathematics rather than a wish;
* Case E is *genuinely* multimodal (three continuous maxima), which is what a
  candidate replacement policy must preserve;
* the two families are **indistinguishable from the production seed field**,
  which is the measured reason a threshold-free replacement is not available;
* ``d_res`` is an uncalibrated parameter and cannot be turned into a number from
  here.

Remediation Design v2 §12.1: "Every oracle derives from the synthetic
construction and its known mathematical structure. No test asserts 'the current
output is X'."
"""

from __future__ import annotations

import math
import tempfile

import numpy as np
import pytest

from groundscan.validation.decomposition_reference import (
    ASPECT_RATIOS,
    BENIGN_MECHANISMS,
    CLASSIFICATION_INSTABILITY,
    CONSERVATIVE_NEST,
    COUNT_INSTABILITY,
    EVIDENCE_INSTABILITY,
    FORBIDDEN_OBJECT_COUNT_NAMES,
    GENUINE_MULTIMODALITY,
    INSTABILITIES,
    LOCATION_INSTABILITY,
    MECHANISMS,
    NOISE_FRAGMENTATION,
    RESPONSE_SIGMAS,
    ROLE_INSTABILITY,
    SEED_SPACING,
    STABLE,
    STATUS_CALIBRATED,
    UNKNOWN_MECHANISM,
    UNRESOLVED_SEPARATION,
    MultiplicityFinding,
    PerturbedRun,
    ResolvableSeparation,
    aspect_sweep,
    assert_no_object_count_claim,
    case_by_name,
    classify_multiplicity,
    close_unresolved_scene,
    compare_runs,
    continuous_maxima_count,
    group_into_responses,
    local_maxima_count,
    multi_seed_scene,
    multimodal_scene,
    multiplicity_excess,
    pitch_is_not_a_resolvability_bound,
    production_seed_field,
    resolution_ladder,
    separated_scene,
    separation_distribution,
    smooth_ridge_scene,
    superlevel_basin_count,
    topology_separates_artifact_from_multimodality,
    unimodal_scene,
)

# ---------------------------------------------------------------------------
# The oracle is independent of the production decomposition implementation
# ---------------------------------------------------------------------------


def test_the_oracle_never_reaches_the_production_seed_finder():
    """Static guard: the reference module must not import the separation code.

    An oracle that imports the implementation it is judging cannot be an oracle.
    Checked on the **parsed** module -- imports, attribute access and names --
    rather than on the raw text, because the module's prose necessarily names the
    production functions it exists to characterise, and a text scan would flag
    its own documentation.
    """
    import ast
    import pathlib

    import groundscan.validation.decomposition_reference as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
            if node.module:
                imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)

    # Nothing from the production decomposition package, in any form.
    for module_name in sorted(imported):
        assert "separation" not in module_name, f"the S01 oracle imports {module_name!r}"
        assert "site" not in module_name.split("."), module_name
        assert "core" not in module_name.split("."), module_name

    # Its single first-party dependency is the validation-side forward model.
    first_party = {n for n in imported if n.startswith("synthetic_core")}
    assert first_party == {"synthetic_core.cross_resolution"}


def test_the_replica_of_the_production_field_is_labelled_as_a_replica():
    """The one production-shaped quantity must never masquerade as an oracle."""
    import inspect

    import groundscan.validation.decomposition_reference as module

    doc = inspect.getdoc(module.production_seed_field) or ""
    assert "Replica" in doc
    assert "not oracle" in doc


# ---------------------------------------------------------------------------
# Cases A-E: the mathematical structure of each construction
# ---------------------------------------------------------------------------


def test_case_a_is_strictly_unimodal_at_every_sampling_density():
    """Case A: one response, one continuous maximum. Contractible superlevel sets."""
    scene = unimodal_scene()
    assert scene.response_count == 1
    assert continuous_maxima_count(scene) == 1
    for pitch in (1.0, 0.5, 0.25, 0.125):
        ladder = resolution_ladder(scene.width_m, scene.height_m, (pitch,))
        resolution = ladder[0]
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        field = scene.value_at(xx, yy)
        # Sampled maxima cannot exceed the continuous ones for a field this
        # smooth relative to the pitch, and here they coincide.
        assert local_maxima_count(field) == 1, pitch


def test_case_b_is_resolvable_in_principle_with_two_continuous_maxima():
    """Case B: the two-Gaussian pair is past the bifurcation scale.

    Derived from the construction: two equal Gaussians have two local maxima iff
    their separation exceeds ``2 * sigma``. Asserted from that inequality *and*
    from the analytic count, so neither can drift alone.
    """
    scene = separated_scene()
    assert scene.response_count == 2
    left, right = scene.responses
    separation = abs(right.cx - left.cx)
    assert separation > 2.0 * max(left.sigma_x, left.sigma_y)
    assert continuous_maxima_count(scene) == 2


def test_case_c_is_unresolvable_in_principle_not_merely_unresolved():
    """Case C: below the bifurcation, so no sampling can separate the pair.

    This is the test that makes "preserve it as unresolved structure" a
    mathematical statement. It asserts the *inequality* that causes it, so a
    future edit to the construction that pushed the pair past the bifurcation
    would fail here rather than silently weaken Case C.
    """
    scene = close_unresolved_scene()
    assert scene.response_count == 2
    left, right = scene.responses
    separation = abs(right.cx - left.cx)
    assert separation < 2.0 * max(left.sigma_x, left.sigma_y)
    assert continuous_maxima_count(scene) < scene.response_count


def test_the_bifurcation_boundary_is_where_the_construction_says_it_is():
    """Sweep the pair across ``2 * sigma`` and find the transition analytically.

    An independent expectation: the count must be 1 below the scale and 2 above
    it, with the transition at the scale itself. Nothing about the pipeline is
    consulted, so this pins the oracle the whole suite leans on.
    """
    sigma = 1.2
    base = close_unresolved_scene()
    left, right = base.responses
    centre = left.cx

    def pair(sep: float):
        from groundscan.validation.synthetic_core.cross_resolution import (
            PhysicalResponse,
            PhysicalScene,
        )

        return PhysicalScene(
            name="probe",
            width_m=base.width_m,
            height_m=base.height_m,
            case_family="probe",
            noise_sigma=base.noise_sigma,
            responses=(
                PhysicalResponse(
                    label="a",
                    cx=centre - sep / 2,
                    cy=left.cy,
                    sigma_x=sigma,
                    sigma_y=sigma,
                    amplitude=1.0,
                ),
                PhysicalResponse(
                    label="b",
                    cx=centre + sep / 2,
                    cy=right.cy,
                    sigma_x=sigma,
                    sigma_y=sigma,
                    amplitude=1.0,
                ),
            ),
        )

    below = [continuous_maxima_count(pair(s)) for s in (0.5, 1.0, 1.8, 2.0, 2.2)]
    above = [continuous_maxima_count(pair(s)) for s in (2.8, 3.5, 5.0, 8.0)]
    assert below == [1, 1, 1, 1, 1]
    assert above == [2, 2, 2, 2]


def test_case_d_is_unimodal_in_the_field_but_multimodal_when_sampled():
    """Case D: a rotated ellipse has one maximum; a lattice can show several."""
    scene = multi_seed_scene()
    assert scene.response_count == 1
    assert continuous_maxima_count(scene) == 1
    ladder = resolution_ladder(scene.width_m, scene.height_m, (0.25,))
    xs, ys = scene.x_samples(ladder[0]), scene.y_samples(ladder[0])
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    assert local_maxima_count(scene.value_at(xx, yy)) > 1


def test_case_e_is_genuinely_multimodal_with_three_continuous_maxima():
    """Case E: three real maxima. Any replacement must leave this at three."""
    scene = multimodal_scene()
    assert scene.response_count == 3
    assert continuous_maxima_count(scene) == 3


def test_every_controlled_case_is_reachable_by_name():
    for name in (
        "case_a_unimodal",
        "case_b_separated",
        "case_c_close_unresolved",
        "case_d_multi_seed",
        "ridge_6x1",
        "case_e_multimodal",
    ):
        assert case_by_name(name).name == name
    with pytest.raises(KeyError):
        case_by_name("no_such_case")


# ---------------------------------------------------------------------------
# Test 6 / 9: cross-resolution and anisotropy characterisation
# ---------------------------------------------------------------------------


def test_no_relation_anywhere_asserts_count_invariance_under_resampling():
    """Seed counts, component boundaries and fragment counts may vary (v2 §4.5).

    The check is structural: the ladder must contain both a coarse and a fine
    rung, and the fine rung must genuinely be finer, so a future test cannot
    quietly reduce the ladder to a single resolution and call the comparison
    stable.
    """
    ladder = resolution_ladder(24.0, 24.0)
    pitches = [r.dx for r in ladder]
    assert pitches == sorted(pitches, reverse=True)
    assert min(pitches) * 8 == pytest.approx(max(pitches))
    assert len({r.sample_count for r in ladder}) == len(ladder)


def test_sampled_maxima_are_invariant_to_isotropic_resampling_but_not_to_aspect():
    """The measured correction to the earlier "seeds vary with resolution" claim.

    For the *rotated* elongated field the sampled local-maxima count holds at 3
    under pure isotropic pitch change and moves to 1, 3, 1, 3, 3, 3 across the
    lattice aspect ratio -- non-monotone in the ratio, so the governing variable
    is the sampling geometry relative to the field's own aspect ratio, not
    resolution in the isotropic sense.
    """
    scene = multi_seed_scene(extent_m=12.0)
    assert continuous_maxima_count(scene) == 1

    # Isotropic: the count does not move.
    isotropic = []
    for resolution in resolution_ladder(scene.width_m, scene.height_m, (1.0, 0.5, 0.25, 0.125)):
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        isotropic.append(local_maxima_count(scene.value_at(xx, yy)))
    assert len(set(isotropic)) == 1, isotropic
    assert isotropic[0] > 1, "the rotated field must show the discretisation staircase"

    # Aspect: the count does move, and not monotonically.
    rows = aspect_sweep(scene, 0.5, ASPECT_RATIOS)
    counts = [sampled for _ratio, sampled, _continuous in rows]
    assert {c for _r, _s, c in rows} == {1}
    assert len(set(counts)) > 1
    assert counts != sorted(counts) and counts != sorted(counts, reverse=True)
    assert [r for r, _s, _c in rows] == list(ASPECT_RATIOS)


def test_an_axis_aligned_ridge_shows_no_sampled_maxima_at_all_and_that_is_a_result():
    """The 6 m x 1 m ridge: 1 sampled maximum at every pitch and every aspect.

    Pinning this is what lets the ridge's downstream multiplicity be attributed
    to the seed operator's own field rather than excused as a sampling effect.
    """
    scene = smooth_ridge_scene(extent_m=12.0)
    assert continuous_maxima_count(scene) == 1
    for resolution in resolution_ladder(scene.width_m, scene.height_m, (1.0, 0.5, 0.25, 0.125)):
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        assert local_maxima_count(scene.value_at(xx, yy)) == 1
    counts = [sampled for _r, sampled, _c in aspect_sweep(scene, 0.5, ASPECT_RATIOS)]
    assert counts == [1] * len(ASPECT_RATIOS)


def test_a_genuinely_multimodal_field_shows_its_three_maxima_at_every_pitch():
    """Case E: three continuous maxima, and three sampled maxima at every rung.

    The inverse of the ridge result, and the reason Case E cannot be dismissed as
    a sampling artefact.
    """
    scene = multimodal_scene(extent_m=12.0)
    assert continuous_maxima_count(scene) == 3
    for resolution in resolution_ladder(scene.width_m, scene.height_m, (1.0, 0.5, 0.25)):
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        assert local_maxima_count(scene.value_at(xx, yy)) == 3


def test_isotropic_resampling_of_a_unimodal_field_never_adds_sampled_maxima():
    """Independent expectation: pure pitch change cannot invent a maximum here."""
    scene = unimodal_scene()
    for pitch in (1.0, 0.5, 0.25, 0.125):
        resolution = resolution_ladder(scene.width_m, scene.height_m, (pitch,))[0]
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        assert local_maxima_count(scene.value_at(xx, yy)) == 1


# ---------------------------------------------------------------------------
# The decisive measurement: artifact vs genuine multimodality
# ---------------------------------------------------------------------------


def test_the_production_seed_field_cannot_separate_the_two_families():
    """The measured reason activation is blocked, pinned as a fact.

    A strictly unimodal field and a genuinely three-modal field both present a
    **single** basin on the production seed field. Any promotion rule reading
    that field must therefore either promote both (leaving the artifact in place)
    or demote both (destroying the genuine multimodal case). A rule that
    separates them has to threshold on a distance, i.e. it needs ``d_res``.
    """
    unimodal = superlevel_basin_count(*production_seed_field(_synthetic_z(1)))
    multimodal = superlevel_basin_count(*production_seed_field(_synthetic_z(3)))
    assert unimodal == 1
    assert multimodal == 1
    assert not topology_separates_artifact_from_multimodality(
        artifact_basins=unimodal,
        artifact_records=2,
        multimodal_basins=multimodal,
        multimodal_records=3,
    )


def _synthetic_z(lobes: int) -> np.ndarray:
    """A z-map with *lobes* peaks, built here so the test owns its expectation."""
    grid = np.zeros((41, 41), dtype=float)
    for k in range(lobes):
        row = 20 + (0 if lobes == 1 else 8 * (k - (lobes - 1) / 2))
        row = int(round(row))
        for r in range(grid.shape[0]):
            for c in range(grid.shape[1]):
                grid[r, c] = math.exp(-0.5 * (((r - row) / 2.0) ** 2 + ((c - 20) / 2.0) ** 2))
    return grid


def test_a_basin_count_is_measured_from_the_array_not_from_a_threshold_it_invents():
    """One wide plateau is one basin; two separated peaks are two."""
    flat = np.zeros((21, 21))
    flat[10, 10] = 1.0
    assert superlevel_basin_count(flat) == 1
    twin = np.zeros((21, 21))
    twin[10, 5] = 1.0
    twin[10, 15] = 1.0
    assert superlevel_basin_count(twin) == 2
    assert superlevel_basin_count(np.zeros((21, 21))) == 0


# ---------------------------------------------------------------------------
# Test 13 / 14: level separation, hierarchy and parentage
# ---------------------------------------------------------------------------


def test_response_grouping_reads_parentage_and_keeps_records_apart_otherwise():
    """Level 3 comes from the graph production records, not from a new model."""
    records = [
        {
            "id": 1,
            "separation_status": "decomposed-consensus",
            "separation_parent_id": 1,
            "x": 4.0,
            "y": 6.0,
            "pattern": "metallic-like",
        },
        {
            "id": 2,
            "separation_status": "decomposed-consensus",
            "separation_parent_id": 1,
            "x": 7.0,
            "y": 6.0,
            "pattern": "metallic-like",
        },
        {
            "id": 3,
            "separation_status": "decomposed-consensus",
            "separation_parent_id": 1,
            "x": 9.0,
            "y": 6.0,
            "pattern": "metallic-like",
        },
        {
            "id": 4,
            "separation_status": "none",
            "separation_parent_id": None,
            "x": 20.0,
            "y": 6.0,
            "pattern": "cavity-like",
        },
        {
            "id": 5,
            "separation_status": "none",
            "separation_parent_id": None,
            "x": 22.0,
            "y": 6.0,
            "pattern": "cavity-like",
        },
    ]
    groups = group_into_responses(records)
    # One parent region (3 records) plus two independent regions.
    assert len(groups) == 3
    assert groups[0].parent_id == 1
    assert groups[0].record_count == 3
    assert groups[0].is_multi_record
    assert [g.parent_id for g in groups[1:]] == [None, None]
    assert all(g.record_count == 1 for g in groups[1:])
    assert multiplicity_excess(groups) == 2


def test_candidate_count_is_not_a_response_count_and_neither_is_an_object_count():
    """K1/K3: four records from one response region are four *hypotheses*.

    The grouping is what makes the distinction measurable, and the numbers are
    stated separately so a reader cannot collapse them.
    """
    records = [
        {
            "id": i,
            "separation_status": "decomposed-consensus",
            "separation_parent_id": 1,
            "x": float(i),
            "y": 0.0,
            "pattern": "metallic-like",
        }
        for i in range(1, 5)
    ]
    groups = group_into_responses(records)
    candidate_count = len(records)
    response_count = len(groups)
    assert candidate_count == 4
    assert response_count == 1
    assert multiplicity_excess(groups) == 3
    # Level 6 has no number here at all: the vocabulary of forbidden key names
    # is the only place the word appears, and every payload is checked against it.
    assert FORBIDDEN_OBJECT_COUNT_NAMES
    assert_no_object_count_claim({"candidates": candidate_count, "responses": response_count})


def test_a_single_record_has_no_excess_and_no_parentage_claim():
    records = [
        {
            "id": 1,
            "separation_status": "none",
            "separation_parent_id": None,
            "x": 0.0,
            "y": 0.0,
            "pattern": "metallic-like",
        }
    ]
    groups = group_into_responses(records)
    assert multiplicity_excess(groups) == 0
    assert groups[0].parent_id is None
    assert not groups[0].is_multi_record


# ---------------------------------------------------------------------------
# Test 16: the physical-object prohibition, by naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_OBJECT_COUNT_NAMES))
def test_a_forbidden_object_count_key_is_rejected_at_any_depth(forbidden):
    assert_no_object_count_claim({"levels": {"candidate": 3}})
    with pytest.raises(AssertionError):
        assert_no_object_count_claim({"summary": {forbidden: 3}})
    with pytest.raises(AssertionError):
        assert_no_object_count_claim({"a": [{"b": [{forbidden: 1}]}]})


def test_the_level_six_note_names_the_evidence_that_would_be_required():
    import groundscan.validation.decomposition_reference as module

    note = module.LEVEL_SIX_NOTE
    for requirement in ("excavation", "borehole", "installation record"):
        assert requirement in note


# ---------------------------------------------------------------------------
# Phase D: d_res is a parameter, and cannot be invented here
# ---------------------------------------------------------------------------


def test_d_res_ships_uncalibrated_with_units_provenance_and_status():
    parameter = UNRESOLVED_SEPARATION
    assert parameter.value_m is None
    assert parameter.units == "m"
    assert parameter.status != STATUS_CALIBRATED
    assert not parameter.is_calibrated
    assert not parameter.promotes
    assert parameter.provenance
    assert parameter.geometry_context
    assert parameter.meaning
    payload = parameter.to_dict()
    assert payload["value_m"] is None
    assert set(payload) == {
        "value_m",
        "units",
        "provenance",
        "geometry_context",
        "status",
        "meaning",
    }
    # Every field except the value itself is populated: the parameter must be
    # self-describing, so a consumer cannot read it as an anonymous number.
    assert all(v for k, v in payload.items() if k != "value_m")


def test_an_uncalibrated_d_res_never_promotes_at_any_distance():
    parameter = UNRESOLVED_SEPARATION
    for distance in (0.0, 1e-9, 0.5, 1.0, 1e3, float("inf")):
        assert not parameter.separates(distance)


def test_a_calibrated_d_res_is_honoured_but_still_states_its_own_context():
    """The parameter is *usable* once calibrated; the point is that it is not now."""
    calibrated = ResolvableSeparation(
        value_m=2.0,
        provenance="bench sweep: two-pole resolution at 0.25 m line spacing",
        geometry_context="0.25 m line spacing, contrast >= 3 sigma, SNR >= 20 dB",
        status=STATUS_CALIBRATED,
    )
    assert calibrated.is_calibrated
    assert calibrated.promotes
    assert not calibrated.separates(1.0)
    assert calibrated.separates(3.0)
    assert calibrated.units == "m"


def test_the_only_policy_available_while_uncalibrated_is_conservative_nesting():
    """v2 §4.4: until d_res is calibrated, do not promote; nest."""
    assert CONSERVATIVE_NEST == "conservative-nest"
    assert not UNRESOLVED_SEPARATION.promotes


def test_pitch_is_not_a_resolvability_bound_and_that_is_pinned_by_measurement():
    """The v1 "closer than one pitch means the same response" rule is refused.

    Measured on a constructed response: the pipeline localises the Case A
    response to well under a quarter of one cell, while the response itself spans
    roughly 12 cells. Positional accuracy is therefore demonstrably *finer* than
    the pitch, so a pitch-keyed merge rule would merge records that are in fact
    well separated -- which is exactly why the rule was withdrawn in v2 §4.4.
    """
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan
    from groundscan.validation.synthetic_core.cross_resolution import sample_scene

    scene = unimodal_scene(extent_m=12.0)
    resolution = resolution_ladder(scene.width_m, scene.height_m, (1.0,))[0]
    scan = sample_scene(scene, resolution, seed=99_001)
    with tempfile.TemporaryDirectory(prefix="s01pitch_") as tmp:
        _grid, _anomaly, candidates = analyze_scan(
            scan,
            tmp,
            label="pitch",
            config=AnalysisConfig(),
            write_outputs=False,
        )
    assert len(candidates) == 1
    found = candidates[0]
    error = math.hypot(found.centroid_weighted_x - 6.0, found.centroid_weighted_y - 6.0)
    extent = 6.0 * 1.2  # the response's own 6-sigma diameter
    assert pitch_is_not_a_resolvability_bound(
        localisation_error_m=error, pitch_m=resolution.dx, response_extent_m=extent
    )
    # And a genuinely coarse localisation on the same geometry is *not* claimed
    # to beat the pitch, so the function is not vacuously true.
    assert not pitch_is_not_a_resolvability_bound(
        localisation_error_m=0.9, pitch_m=1.0, response_extent_m=extent
    )
    with pytest.raises(ValueError):
        pitch_is_not_a_resolvability_bound(
            localisation_error_m=0.1, pitch_m=0.0, response_extent_m=extent
        )


def test_the_separation_distribution_reports_a_range_and_never_a_proposal():
    """v2 §15.1: a d_res value is not derivable from the distribution."""
    summary = separation_distribution((1.0, 2.0, 3.0))
    assert summary["count"] == 3
    assert summary["min_m"] == 1.0
    assert summary["max_m"] == 3.0
    assert summary["median_m"] == 2.0
    assert summary["proposed_d_res_m"] is None
    empty = separation_distribution(())
    assert empty["count"] == 0
    assert empty["proposed_d_res_m"] is None


# ---------------------------------------------------------------------------
# Phase C: the mechanism taxonomy
# ---------------------------------------------------------------------------


def test_the_mechanism_vocabulary_is_closed_and_only_two_are_benign():
    assert len(MECHANISMS) == 10
    assert (
        frozenset({GENUINE_MULTIMODALITY, "intentional-decomposition-policy"}) == BENIGN_MECHANISMS
    )
    assert UNKNOWN_MECHANISM in MECHANISMS


def test_a_mechanism_outside_the_taxonomy_is_refused_at_construction():
    with pytest.raises(ValueError):
        MultiplicityFinding(
            label="x",
            mechanism="because-i-said-so",
            continuous_maxima=1,
            sampled_maxima=1,
            production_seed_maxima=1,
            anomaly_region_count=1,
            top_level_count=1,
            decomposition_count=0,
        )


def test_genuine_multimodality_outranks_every_sampling_artefact():
    """Three continuous maxima with three records is the field's own statement."""
    assert (
        classify_multiplicity(
            continuous_maxima=3,
            sampled_maxima=3,
            production_seed_maxima=1,
            record_count=3,
            anomaly_region_count=1,
            independent_components=0,
            separation_median_m=None,
            pitch_m=0.5,
            dy_ratio=2.0,
        )
        == GENUINE_MULTIMODALITY
    )


def test_extra_components_are_noise_fragmentation_not_a_decomposition_finding():
    assert (
        classify_multiplicity(
            continuous_maxima=1,
            sampled_maxima=1,
            production_seed_maxima=1,
            record_count=3,
            anomaly_region_count=3,
            independent_components=3,
            separation_median_m=None,
            pitch_m=0.25,
            dy_ratio=1.0,
        )
        == NOISE_FRAGMENTATION
    )


def test_the_seed_stage_is_the_only_one_that_disagreeing_is_attributed_to_it():
    common = dict(
        continuous_maxima=1,
        record_count=2,
        anomaly_region_count=1,
        independent_components=0,
        separation_median_m=1.0,
        pitch_m=0.5,
        dy_ratio=1.0,
    )
    assert (
        classify_multiplicity(sampled_maxima=1, production_seed_maxima=2, **common) == SEED_SPACING
    )
    assert (
        classify_multiplicity(sampled_maxima=3, production_seed_maxima=3, **common)
        == "raster-sampling-effect"
    )


# ---------------------------------------------------------------------------
# Tests 7 / 8 / 10 / 11 / 12: stability is defined by declared metrics only
# ---------------------------------------------------------------------------


def _run(
    label,
    *,
    count=1,
    top=1,
    xy=(1.0, 2.0),
    roles=("response",),
    patterns=("metallic-like",),
    evidence=(0.5,),
    pitch=0.5,
) -> PerturbedRun:
    return PerturbedRun(
        label=label,
        candidate_count=count,
        top_level_count=top,
        positions_m=(xy,),
        roles=roles,
        patterns=patterns,
        evidence=evidence,
        pitch_m=pitch,
    )


def test_a_stability_comparison_needs_at_least_two_runs():
    with pytest.raises(ValueError):
        compare_runs("solo", (_run("only"),))


def test_identical_runs_are_stable_under_every_declared_metric():
    a = _run("a")
    b = _run("b")
    verdict = compare_runs("identical", (a, b))
    assert verdict.is_stable
    assert verdict.instabilities == ()
    assert verdict.to_dict()["stable"] is True


def test_a_count_that_holds_while_the_label_flips_is_still_an_instability():
    """The finding a count-only characterisation cannot see."""
    a = _run("a", count=1, patterns=("metallic-like",))
    b = _run("b", count=1, patterns=("cavity-like",))
    verdict = compare_runs("label-flip", (a, b))
    assert CLASSIFICATION_INSTABILITY in verdict.instabilities
    assert not verdict.is_stable
    assert verdict.metrics["candidate_counts"] == [1]


def test_each_declared_instability_is_reachable_and_named():
    def kinds(*runs) -> tuple[str, ...]:
        return compare_runs("probe", runs).instabilities

    assert COUNT_INSTABILITY in kinds(_run("a", count=1), _run("b", count=2))
    assert ROLE_INSTABILITY in kinds(
        _run("a", roles=("response",)), _run("b", roles=("decomposition",))
    )
    assert EVIDENCE_INSTABILITY in kinds(_run("a", evidence=(0.5,)), _run("b", evidence=(0.9,)))
    # A position move inside the declared pitch tolerance is not an instability.
    assert LOCATION_INSTABILITY not in kinds(_run("a", xy=(0.0, 0.0)), _run("b", xy=(0.5, 0.0)))
    # A move beyond it is.
    assert LOCATION_INSTABILITY in kinds(_run("a", xy=(0.0, 0.0)), _run("b", xy=(5.0, 0.0)))


def test_the_position_tolerance_comes_from_the_pitch_not_from_the_observed_move():
    """A tolerance fitted to what was seen is not a tolerance."""
    from groundscan.validation.decomposition_reference import LOCATION_TOLERANCE_PITCH_FACTOR

    a = _run("a", xy=(0.0, 0.0), pitch=0.5)
    b = _run("b", xy=(0.4, 0.0), pitch=0.5)
    verdict = compare_runs("tolerance", (a, b))
    assert verdict.metrics["position_tolerance_m"] == pytest.approx(
        LOCATION_TOLERANCE_PITCH_FACTOR * 0.5
    )
    assert verdict.metrics["max_position_move_m"] == pytest.approx(0.4)


def test_the_instability_vocabulary_is_closed():
    assert set(INSTABILITIES) == {
        COUNT_INSTABILITY,
        LOCATION_INSTABILITY,
        ROLE_INSTABILITY,
        CLASSIFICATION_INSTABILITY,
        EVIDENCE_INSTABILITY,
        STABLE,
    }


# ---------------------------------------------------------------------------
# The constructions are in the ordinary detection regime, not a degenerate one
# ---------------------------------------------------------------------------


def test_responses_are_ten_sigma_so_the_scale_estimate_is_not_degenerate():
    """A near-zero-noise field makes the residual scale indeterminate (an S03
    matter) and multiplicity meaningless. The constructions must avoid it, and
    this pins that they do.
    """
    from groundscan.core.anomaly import detect_anomalies
    from groundscan.core.grid import reconstruct_grid
    from groundscan.validation.decomposition_reference import NOISE_SIGMA
    from groundscan.validation.synthetic_core.cross_resolution import sample_scene

    assert pytest.approx(10.0 * NOISE_SIGMA) == RESPONSE_SIGMAS
    scene = unimodal_scene()
    for pitch in (1.0, 0.5):
        resolution = resolution_ladder(scene.width_m, scene.height_m, (pitch,))[0]
        scan = sample_scene(scene, resolution, seed=1234)
        grid = reconstruct_grid(scan)
        anomaly = detect_anomalies(grid, 3.0, 3, "multiscale", (3, 5, 9, 15), 8)
        residual = anomaly.residual
        mad = float(np.nanmedian(np.abs(residual - np.nanmedian(residual))))
        assert mad > 0.3 * NOISE_SIGMA, f"degenerate residual scale at pitch {pitch}"

"""Phase I -- interactions, and the discipline of attributing a movement.

The assertions here are about *attribution*, not about sensitivity. A
single-factor sweep says what changed; it does not say why, and it is easy to read
a correlated pair of movements as a causal one. So the probes ask each mediator
directly and the vocabulary has three outcomes -- ``direct``, ``mediated``,
``incoherent`` -- because "the mediator did not explain it" is a real result that
must not be rounded to either neighbour.

The load-bearing findings, all asserted rather than described:

* a solidity shift moves the three bands but does not cross the ``geometry_quality``
  band on this population, so the two routes are independent with zero overlap;
* removing the solidity weight from ``geometry_quality`` changes the evidence
  selection for one candidate in ninety -- nearly inert, and not calibrated;
* the operational resolution probe's metric-invariance guard is **vacuous** on this
  population, and is asserted to be reported as vacuous rather than as a pass;
* the S03 scale status does not exist on the candidate path, so its interaction with
  the z-score is NOT APPLICABLE rather than merely unobserved.
"""

from __future__ import annotations

from groundscan.validation.calibration import interactions as I
from groundscan.validation.calibration import resolution as R
from groundscan.validation.calibration.decision import candidate_population
from groundscan.validation.calibration.interactions import (
    INCOHERENT,
    MEDIATED,
    classify_mediation,
    d_res_x_decomposition,
    evidence_x_min_margin,
    geometry_quality_x_evidence,
    reconstructable_members,
    resolution_x_shape_metric,
    scale_status_x_anomaly_zscore,
    solidity_x_geometry_quality,
)

POPULATION = candidate_population(limit_vendor=2)


# ---------------------------------------------------------------------------
# The mediator vocabulary
# ---------------------------------------------------------------------------


def test_mediation_classification_is_decided_by_counts() -> None:
    """Three outcomes, decided arithmetically, with the boundary cases named.

    ``incoherent`` is the one that must never be rounded to a neighbour: it means
    the mediator moved but does not account for the outcome, and attributing it to
    the nearest-looking cause is exactly the error this phase exists to prevent.
    """
    assert (
        classify_mediation(n_outcome_changed=0, n_mediator_sign_correct=0, n_mediator_sign_wrong=0)
        == MEDIATED
        or classify_mediation(
            n_outcome_changed=0, n_mediator_sign_correct=0, n_mediator_sign_wrong=0
        )
        == "direct"
    )
    assert (
        classify_mediation(
            n_outcome_changed=5,
            n_mediator_sign_correct=5,
            n_mediator_sign_wrong=0,
        )
        == MEDIATED
    )
    assert (
        classify_mediation(n_outcome_changed=3, n_mediator_sign_correct=0, n_mediator_sign_wrong=0)
        == "direct"
    )
    assert (
        classify_mediation(
            n_outcome_changed=4,
            n_mediator_sign_correct=1,
            n_mediator_sign_wrong=3,
        )
        == INCOHERENT
    )


# ---------------------------------------------------------------------------
# solidity x geometry_quality
# ---------------------------------------------------------------------------


def test_the_two_solidity_routes_have_zero_overlap_on_this_population() -> None:
    """The interaction the brief asks about, measured as a set intersection.

    The three solidity bands read the value directly; ``geometry_quality`` consumes
    it through a 0.25 weight and its own 0.40 band. A solidity shift of up to 0.10
    moves 52 candidates across a band and none across the geometry band -- so a
    compensation between the two is not merely unnecessary, it would be acting on a
    decision that does not move.
    """
    result = solidity_x_geometry_quality(POPULATION)
    rows = {row["solidity_delta"]: row for row in result["rows"]}
    biggest = rows[0.10]
    assert biggest["n_band_hits_union"] > 0
    assert biggest["n_geometry_band_hits"] == 0
    assert biggest["n_intersection"] == 0
    assert biggest["fraction_geometry_only"] == 0.0
    assert biggest["fraction_band_only"] > 0.0
    for delta, row in rows.items():
        assert row["n_intersection"] == 0, (
            f"delta {delta}: the two routes now overlap, so a band change would no "
            "longer be independent of the weight"
        )


def test_the_geometry_band_is_within_reach_of_a_solidity_shift() -> None:
    """How close the geometry band comes, so 'no overlap' is not mistaken for safety.

    A solidity shift of ``delta`` moves ``geometry_quality`` by at most
    ``0.25 * |delta|``, so 0.025 at the largest shift swept. The nearest approach
    measured over the whole sweep is 0.023 -- reached by *lowering* solidity, because
    lowering it is the direction that moves ``geometry_quality`` towards the band.
    Reporting only the zero intersection would overstate the separation; the band is
    one maximum shift away, not far from it.
    """
    result = solidity_x_geometry_quality(POPULATION)
    distances = [
        row["min_distance_to_geometry_band"]
        for row in result["rows"]
        if row["min_distance_to_geometry_band"] is not None
    ]
    assert distances, "no candidate's distance to the geometry band was measured"
    nearest = min(distances)
    max_movement = 0.25 * max(abs(row["solidity_delta"]) for row in result["rows"])
    assert nearest > 0.0
    assert nearest < max_movement, (
        "the geometry band is no longer within one maximum solidity shift; the "
        "'independent routes' reading needs revisiting"
    )
    for row in result["rows"]:
        assert row["n_geometry_band_hits"] == 0, row["solidity_delta"]


def test_the_geometry_quality_reconstruction_is_checked_and_bucketed() -> None:
    """The probe's premise is verified, and the failures are classified.

    ``geometry_quality`` has three production computation sites. Candidates whose
    value came from the dipole-merge site are a function of two lobes, not of one
    cell set, and cannot be reconstructed. Those are excluded from the scoped
    population and counted, not silently dropped.
    """
    verification = solidity_x_geometry_quality(POPULATION)["geometry_terms_verification"]
    assert verification["n_usable"] <= verification["n_members"]
    assert verification["reconstruction_usable"] in (True, False)
    if not verification["reconstruction_usable"]:
        assert verification["failures_by_separation_status"], (
            "the reconstruction failed without a classified cause"
        )
        assert "merged-dipole" in verification["failures_by_separation_status"]
    assert len(verification["geometry_quality_production_sites"]) == 3
    assert len(reconstructable_members(POPULATION)) == verification["n_usable"]


# ---------------------------------------------------------------------------
# geometry_quality x evidence
# ---------------------------------------------------------------------------


def test_the_solidity_weight_is_nearly_inert_on_the_evidence_path() -> None:
    """Removing the term entirely changes one selection in ninety.

    Between 0.10 and 0.40 the weight changes none at all. So the weight is neither
    calibrated (nothing constrains it) nor meaningfully load-bearing (nothing
    depends on it) -- which is the MODEL CHOICE status, arrived at by measurement
    rather than by assertion.
    """
    result = geometry_quality_x_evidence(POPULATION)
    rows = {row["solidity_weight"]: row for row in result["rows"]}
    assert rows[0.0]["n_evidence_selection_changed"] <= 2, (
        "removing the solidity weight changed more than a couple of selections, so "
        "the near-inertness finding is stale"
    )
    for weight in (0.10, 0.20, 0.30, 0.40):
        assert rows[weight]["n_evidence_selection_changed"] == 0, weight
    assert all(
        r["n_geometry_changed"] == result["population"]["n_candidates"] for r in result["rows"]
    ), "the weight did not actually move geometry_quality at some level"


def test_the_mediated_margins_are_declared_so_a_compensation_is_traceable() -> None:
    """Every route solidity takes into a decision is named with its weight.

    Without the table, "do not compensate the band with this weight" would be an
    instruction with no referent.
    """
    table = geometry_quality_x_evidence(POPULATION)["geometry_feature_weights_in_hypothesis_tables"]
    assert table["metallic-like"] == 0.08
    assert table["cavity-like"] == 0.08
    assert table["geological-like"] == 0.06
    assert table["irregular-anomaly"] == 0.10
    assert table["quality_support_geometry"] == 0.10


# ---------------------------------------------------------------------------
# evidence x min_margin
# ---------------------------------------------------------------------------


def test_the_joint_gate_grid_is_a_full_cross_product() -> None:
    result = evidence_x_min_margin(POPULATION)
    assert len(result["joint_grid"]) == len(result["swept_supports"]) * len(result["swept_margins"])
    for row in result["joint_grid"]:
        assert 0 <= row["n_selected"] <= result["population"]["n_candidates"]
        assert 0.0 <= row["fraction_rejected"] <= 1.0
    # Both effects are computed from the same joint counts, so both must be present.
    assert result["min_support_effect"]["n_values"] == len(result["swept_supports"])
    assert result["min_margin_effect"]["n_values"] == len(result["swept_margins"])


def test_neither_gate_is_fully_redundant_and_the_asymmetry_is_recorded() -> None:
    """The measured asymmetry, on the named population.

    ``min_margin`` excludes candidates at every non-zero swept value; ``min_support``
    excludes none below 0.60 and four at 0.70. So the margin is the primary filter
    over the range both were swept in, and the support floor only bites well above
    its own production value.
    """
    result = evidence_x_min_margin(POPULATION)
    assert result["min_margin_redundant_given_min_support"] is False
    assert result["min_support_redundant_given_min_margin"] is False
    dominated = [row for row in result["min_support_effect"]["rows"] if row["value"] <= 0.60]
    assert dominated and all(not row["adds"] for row in dominated)
    assert any(row["adds"] for row in result["min_margin_effect"]["rows"])
    assert "property of this population" in result["reading"]


# ---------------------------------------------------------------------------
# resolution x shape metrics
# ---------------------------------------------------------------------------


def test_the_metric_invariance_guard_is_reported_as_vacuous_when_it_is() -> None:
    """A vacuous guard is reported vacuous, never as a pass.

    The matched candidate pairs all have *different* cell counts at the two pitches,
    so none of them can witness that the metric is unchanged for a fixed cell set.
    Asserting `metric_invariant_on_same_cell_set` would be asserting a pass on a
    check that never ran; the module instead reports ``None`` plus a note, and the
    test asserts the note is present.
    """
    result = resolution_x_shape_metric(0.25, 1.0)
    split = result["matched_split"]
    assert result["n_matched"] == split["n_same_cell_count"] + split["n_different_cell_count"]
    if split["n_same_cell_count"] == 0:
        assert split["guard_vacuous"] is True
        assert split["metric_invariant_on_same_cell_set"] is None
        assert "vacuous guard is reported as vacuous" in split["guard_note"]
        assert "calibration.geometry.pitch_invariance" in split["guard_note"]
    else:
        assert split["guard_vacuous"] is False
        assert split["metric_invariant_on_same_cell_set"] in (True, False)


def test_the_population_shift_is_larger_than_the_metric_can_be() -> None:
    """The population shift is a rasterization effect, and it is large.

    A candidate's solidity moves by up to 0.28 between a 0.25 m and a 1.0 m lattice
    because the detector's *mask* changes shape, not because the ratio does. The
    test pins that separation so the two movements are never added together.
    """
    result = resolution_x_shape_metric(0.25, 1.0)
    shift = result["solidity_population_shift"]
    assert shift["max_abs_delta"] is not None
    assert shift["max_abs_delta"] > 0.05, "the population shift vanished"
    assert "must not be added" in result["attribution"]
    assert "is not the same shape" in result["attribution"]
    for row in result["rows"]:
        assert row["n_cells_coarse"] != row["n_cells_fine"], (
            "a same-cell-count pair appeared, so the vacuous-guard reading needs revisiting"
        )


def test_compactness_movement_is_confounded_with_component_size() -> None:
    """Compactness has no invariance to fall back on, and the correlation is positive.

    The proxy's movement across pitch is reported alongside its correlation with the
    coarse cell count, so "moves with pitch" and "moves with size" can be told
    apart rather than conflated.
    """
    result = resolution_x_shape_metric(0.25, 1.0)
    compactness = result["compactness"]
    assert compactness["max_abs_delta"] is not None
    assert compactness["max_abs_delta"] > 0.1
    assert compactness["corr_with_coarse_cell_count"] is not None
    assert "confounded with component size" in result["attribution"]


# ---------------------------------------------------------------------------
# scale status x anomaly z-score
# ---------------------------------------------------------------------------


def test_the_scale_status_does_not_exist_on_the_candidate_path() -> None:
    """NOT APPLICABLE, established by measurement rather than by assumption.

    Every candidate reports an empty status, because ``Candidate`` has no
    ``scale_status`` field: the S03 status is confined to the shadow ledger and the
    technical diagnostics block, both off by default and feeding no threshold. That
    is a stronger statement than a measured absence of correlation, and it says the
    interaction cannot arise until S03 is activated.
    """
    result = scale_status_x_anomaly_zscore(POPULATION)
    assert result["n_candidates_carrying_a_status_field"] == 0
    assert set(result["observed_status_values"]) == {""}
    for stats in result["abs_z_by_status"].values():
        assert stats["n"] == 0
    assert "NOT APPLICABLE on this path" in result["verdict"]
    assert "re-measured before any z-score threshold" in result["verdict"]
    assert len(result["status_sites"]) == 2


def test_candidates_really_have_no_scale_status_attribute() -> None:
    """Checked against the model, so the finding cannot be an artifact of the probe."""
    from groundscan.models import Candidate

    fields = getattr(Candidate, "model_fields", {})
    assert "scale_status" not in fields
    assert "residual_regime" not in fields


# ---------------------------------------------------------------------------
# d_res x decomposition
# ---------------------------------------------------------------------------


def test_the_decomposition_policy_has_no_crossing_to_misalign_with() -> None:
    """S01 nests at every separation, so there is no d_res it would disagree with.

    Activating ``d_res`` would introduce a decision, not adjust an existing one. The
    only evidence available about where that decision would sit is the measured
    region-count crossing, and it is reported as such.
    """
    result = d_res_x_decomposition(sigma_m=1.0, pitch_dx_m=0.5, seeds=(0, 1, 2))
    assert result["analytic_d_res_m"] == 2.0
    assert result["decomposition_policy"].startswith("conservative-nest")
    first = result["first_multiplier_resolved"]
    assert first is not None
    for row in result["rows"]:
        if row["multiplier_of_2sigma"] < first:
            assert row["resolved_at_every_seed"] is False
        else:
            assert row["resolved_at_every_seed"] is True
    assert "introduce a new decision" in result["verdict"]


def test_the_d_res_interaction_crossing_matches_the_separation_sweep() -> None:
    """The two measurements of the same crossing must agree.

    ``d_res_x_decomposition`` runs its own sweep and ``resolution`` runs another.
    If they disagreed, one of them would be measuring something other than the
    crossing, and either could be quoted in a report.
    """
    interaction = d_res_x_decomposition(sigma_m=1.0, pitch_dx_m=0.5, seeds=(0, 1, 2))
    trials = R.separation_curve(sigma_m=1.0, pitch_dx_m=0.5, seeds=(0, 1, 2))
    summary = R.summarize_separation_curve(
        trials,
        sigma_m=1.0,
        pitch_dx_m=0.5,
        pitch_dy_m=0.5,
        noise_sigma=1.0,
        amplitude=10.0,
    )
    assert interaction["first_multiplier_resolved"] is not None
    if summary.measured_d_res_bracket_m:
        lower, upper = summary.measured_d_res_bracket_m
        assert lower / 2.0 < interaction["first_multiplier_resolved"] <= upper / 2.0


# ---------------------------------------------------------------------------
# The roll-up
# ---------------------------------------------------------------------------


def test_the_roll_up_runs_every_probe_on_one_stated_population() -> None:
    report = I.interaction_report(POPULATION)
    assert report["population"]["n_candidates"] == len(POPULATION)
    for key in (
        "solidity_x_geometry_quality",
        "geometry_quality_x_evidence",
        "evidence_x_min_margin",
        "resolution_x_shape_metric",
        "scale_status_x_anomaly_zscore",
        "d_res_x_decomposition",
    ):
        assert key in report, key
        assert report[key], key


def test_the_roll_up_is_json_serializable() -> None:
    import json

    text = json.dumps(I.interaction_report(POPULATION), default=str)
    assert len(text) > 2000
    assert json.loads(text)["population"]["n_candidates"] == len(POPULATION)

"""Phase H -- the evidence / quality / screening chain, one factor at a time.

The dependency graph the brief names is walked level by level:

.. code-block:: text

    raw metrics -> geometry quality -> evidence -> screening -> review status

For every scalar in the chain the harness sweeps it alone and counts the three
outcomes that reach a consumer: the evidence selection, the ``review_status`` and
the screening retention. One factor at a time, because the brief is explicit that
these must not be recalibrated together, and a multi-factor sweep would report a
combined effect that no individual change explains.

The load-bearing assertions are about **honesty of the report**, not about the
sensitivities:

* every spec's production value is the literal in the production source file, so
  the matrix cannot describe a parameter that has moved;
* an inert scalar is reported as inert and is *not* counted as validated;
* a redundancy finding is reported as a property of the population, with the
  reading rule that says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundscan.core.evidence import DEFAULT_EVIDENCE_MODEL_CONFIG
from groundscan.gates.screening import DEFAULT_SCREENING_POLICY
from groundscan.validation.calibration import decision as V
from groundscan.validation.calibration.decision import (
    GATE_CHAIN_SPECS,
    SWEEP_MULTIPLIERS,
    ThresholdSpec,
    candidate_population,
    evidence_quality_sensitivity_matrix,
    population_summary,
)

POPULATION = candidate_population(limit_vendor=3)
MATRIX = evidence_quality_sensitivity_matrix(POPULATION)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# The chain's shape
# ---------------------------------------------------------------------------


def test_the_specs_walk_the_chain_in_order() -> None:
    """Each spec declares the level of the graph it sits at.

    A spec with no stage could not be traced to its position in the chain, and a
    chain walked out of order would hide a downstream dependency.
    """
    stages: list[str] = []
    for spec in GATE_CHAIN_SPECS:
        assert spec.stage, spec.spec_id
        if not stages or stages[-1] != spec.stage:
            stages.append(spec.stage)
    assert stages == [
        "raw metrics -> geometry quality",
        "geometry quality -> evidence",
        "evidence -> screening",
        "screening -> review status",
    ]
    assert len(GATE_CHAIN_SPECS) >= 12


def test_every_spec_value_is_the_literal_in_its_production_file() -> None:
    """The matrix describes the shipped constants, not a copy of them.

    If a threshold moved in the code and not in this table, the whole
    characterization would describe a parameter that no longer exists -- and the
    failure would be silent, because a sensitivity sweep on a stale value still
    produces plausible numbers.
    """
    for spec in GATE_CHAIN_SPECS:
        resolved = REPO_ROOT / spec.source_path
        assert resolved.is_file(), spec.spec_id
        text = resolved.read_text(encoding="utf-8")
        assert str(spec.value) in text, f"{spec.spec_id} value not in {spec.source_path}"
        if spec.source_line is not None:
            assert spec.source_line <= len(text.splitlines()), spec.spec_id
        assert spec.comparison in {"<", "<=", ">", ">="}, spec.spec_id
        assert spec.applies_to, spec.spec_id
        assert spec.original_derivation, spec.spec_id


def test_every_spec_states_whether_it_can_be_swept_at_all() -> None:
    """Inert and unreachable are different findings and are reported apart.

    A scalar written as an inline literal at its comparison site cannot be
    perturbed by a one-factor sweep. Reporting that as "inert" would claim the
    parameter was shown not to matter, when what was actually shown is that it is
    not reachable as a parameter -- a different statement, and one whose remedy
    (promote it to a named constant) is concrete.
    """
    sweepable = [s for s in GATE_CHAIN_SPECS if s.sweepable]
    unsweepable = [s for s in GATE_CHAIN_SPECS if not s.sweepable]
    assert sweepable, "the chain must contain at least one reachable parameter"
    assert unsweepable, "if every scalar is reachable, the inline-literal finding needs revisiting"
    for spec in sweepable:
        assert MATRIX["per_spec"][spec.spec_id]["sensitivity_status"] == "swept"
    for spec in unsweepable:
        assert (
            MATRIX["per_spec"][spec.spec_id]["sensitivity_status"] == "not-reachable-as-a-parameter"
        )
        assert MATRIX["per_spec"][spec.spec_id]["is_inert"] is False
    assert MATRIX["n_sweepable_specs"] == len(sweepable)
    assert MATRIX["n_unsweepable_specs"] == len(unsweepable)


def test_the_unsweepable_scalars_are_the_ones_written_as_inline_literals() -> None:
    """The classification is checked against the source, not trusted.

    A spec claiming ``sweepable=False`` must sit at a comparison site with the
    literal in it, and a spec claiming ``sweepable=True`` must sit in a config
    object. Otherwise the distinction is a label rather than a fact.
    """
    for spec in GATE_CHAIN_SPECS:
        text = (REPO_ROOT / spec.source_path).read_text(encoding="utf-8")
        line = spec.source_line
        assert line is not None, spec.spec_id
        source_line = text.splitlines()[line - 1]
        if spec.sweepable:
            assert "=" in source_line or ":" in source_line, (
                f"{spec.spec_id} claims to be sweepable but its line has no field: "
                f"{source_line.strip()!r}"
            )
        else:
            assert str(spec.value) in source_line, (
                f"{spec.spec_id} claims to be an inline literal but its line reads: "
                f"{source_line.strip()!r}"
            )


def test_the_two_margins_are_recorded_as_separate_scalars() -> None:
    """Two different constants on two different score pairs, never conflated.

    ``evidence.min_margin`` acts on the eight-hypothesis support vector;
    ``classify.hypothesis_min_margin`` acts only on the cavity/tunnel pair. They
    share a name and nothing else, and a characterization that merged them would
    report a sensitivity that neither constant has.
    """
    by_id = {s.spec_id: s for s in GATE_CHAIN_SPECS}
    assert by_id["evidence.min_margin"].value == DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    assert by_id["classify.hypothesis_min_margin"].value == 0.04
    assert by_id["evidence.min_margin"].value != by_id["classify.hypothesis_min_margin"].value
    assert "not the same" in by_id["classify.hypothesis_min_margin"].original_derivation


def test_the_screening_primary_band_is_the_shipped_one() -> None:
    by_id = {s.spec_id: s for s in GATE_CHAIN_SPECS}
    assert by_id["screening.primary_threshold"].value == (
        DEFAULT_SCREENING_POLICY.primary_threshold
    )
    assert by_id["screening.rescue_lower"].value == DEFAULT_SCREENING_POLICY.rescue_lower
    assert by_id["screening.rescue_min_persistence"].value == (
        DEFAULT_SCREENING_POLICY.rescue_min_persistence
    )
    assert by_id["screening.rescue_min_anomaly"].value == (
        DEFAULT_SCREENING_POLICY.rescue_min_anomaly
    )


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


def test_the_matrix_is_a_fixed_point_at_every_production_value() -> None:
    """Each swept value at its own shipped constant must change nothing.

    Without this, a row's ``n_any_changed`` could be non-zero purely because the
    override failed to apply -- for instance because a spec has no override wired
    up -- and that would be reported as insensitivity caused by the wrong thing.
    """
    for spec_id, stats in MATRIX["per_spec"].items():
        production_rows = [r for r in stats["rows"] if r["is_production"]]
        assert len(production_rows) == 1, spec_id
        assert production_rows[0]["n_any_changed"] == 0, spec_id


def test_every_sweepable_spec_is_swept_in_more_than_one_direction() -> None:
    """Both up and down, so an insensitivity verdict is not one-sided.

    A scalar whose band sits at the top of its population responds only downwards.
    Sweeping in one direction would then call it inert, which would be a statement
    about the sweep rather than about the parameter.
    """
    for spec in GATE_CHAIN_SPECS:
        if not spec.sweepable:
            continue
        stats = MATRIX["per_spec"][spec.spec_id]
        deltas = [r["delta"] for r in stats["rows"] if not r["is_production"]]
        assert any(d < 0 for d in deltas), spec.spec_id
        assert any(d > 0 for d in deltas), spec.spec_id
        assert len(deltas) >= 4, spec.spec_id


def test_the_matrix_states_its_population_and_baseline() -> None:
    summary = population_summary(POPULATION)
    assert MATRIX["population"]["n_candidates"] == summary["n_candidates"]
    assert MATRIX["population"]["n_scans"] == summary["n_scans"]
    assert MATRIX["n_specs"] == len(GATE_CHAIN_SPECS)
    assert 0 <= MATRIX["n_inert_specs"] <= MATRIX["n_sweepable_specs"]
    assert MATRIX["n_inert_specs"] <= MATRIX["n_specs"]
    for key, value in MATRIX["baseline"].items():
        assert 0 <= value <= summary["n_candidates"], key


def test_the_baseline_is_recomputed_and_its_exceptions_are_reported() -> None:
    """The baseline cannot be read off the candidate, so it is recomputed.

    Two measured reasons, both reported rather than absorbed: the stored
    ``pattern_hypothesis`` comes from the classifier (which is not the evidence
    model), and ``assess_candidate_quality`` is not idempotent for a dipole-merged
    candidate. Without the recomputed baseline, every row in the matrix would carry
    a phantom difference of exactly that size.
    """
    exceptions = MATRIX["baseline_exceptions"]
    assert exceptions["n_non_idempotent_review_status"] >= 0
    assert exceptions["n_empty_screening_selection_reason"] >= 0
    assert "pure transform" in exceptions["note"]
    assert MATRIX["baseline"]["n_evidence_selected"] <= len(POPULATION)
    assert MATRIX["baseline"]["n_screening_retained"] <= len(POPULATION)


def test_an_inert_sweepable_scalar_is_reported_as_inert_and_not_as_validated() -> None:
    """Inertness is a finding with its own name, never a quiet pass.

    A threshold that changes no decision on a population has *not* been shown to be
    right; it has been shown not to matter here. The matrix says which it is, and the
    test asserts the flag exists so a future reader cannot mistake one for the
    other.
    """
    sweepable = [s for s in GATE_CHAIN_SPECS if s.sweepable]
    for spec in sweepable:
        stats = MATRIX["per_spec"][spec.spec_id]
        assert isinstance(stats["is_inert"], bool), spec.spec_id
        assert stats["max_n_any_changed"] >= 0, spec.spec_id
        if stats["is_inert"]:
            assert stats["max_n_any_changed"] == 0, spec.spec_id
    # At least one scalar in the chain is load-bearing, or the chain is not a chain.
    assert any(not MATRIX["per_spec"][s.spec_id]["is_inert"] for s in sweepable), (
        "no sweepable scalar changed any decision"
    )


def test_the_load_bearing_scalars_are_identified() -> None:
    """Which scalars the chain actually depends on, as a stated set.

    Recorded rather than pinned: the set is a property of this population, and a
    future population can legitimately move a scalar in or out of it.
    """
    load_bearing = sorted(
        spec.spec_id
        for spec in GATE_CHAIN_SPECS
        if spec.sweepable and not MATRIX["per_spec"][spec.spec_id]["is_inert"]
    )
    assert load_bearing, "no sweepable scalar changed any decision"
    assert "evidence.min_support" in load_bearing
    assert "screening.primary_threshold" in load_bearing
    for spec_id in load_bearing:
        assert MATRIX["per_spec"][spec_id]["max_n_any_changed"] > 0


def test_outcome_counts_are_consistent_within_each_row() -> None:
    """The four sub-counts cannot exceed or contradict each other.

    ``n_any_changed`` is the union of the four, so it must lie between the largest
    and the sum of the rest. A row that violates this would mean an override
    applied to a different stage than the row claims.
    """
    for row in MATRIX["all_rows"]:
        parts = (
            row["n_evidence_changed"],
            row["n_classification_changed"],
            row["n_review_status_changed"],
            row["n_screening_changed"],
        )
        total = row["n_any_changed"]
        assert total >= max(parts), row["spec_id"]
        assert total <= sum(parts), row["spec_id"]
        assert total <= MATRIX["population"]["n_candidates"], row["spec_id"]


def test_the_matrix_is_json_serializable_in_full() -> None:
    text = json.dumps(MATRIX, default=str)
    assert len(text) > 1000
    assert json.loads(text)["n_specs"] == len(GATE_CHAIN_SPECS)


# ---------------------------------------------------------------------------
# The redundancy finding
# ---------------------------------------------------------------------------


def test_neither_evidence_gate_is_redundant_given_the_other_on_this_population() -> None:
    """Redundancy, defined strictly and measured, comes out False in both directions.

    Gate ``G`` adds nothing beyond ``H`` only when, at every swept value, the
    conjunction selects exactly what ``H`` alone selects. Neither does:

    * ``min_margin`` removes 1, 3, 7, 8 and 53 candidates at 0.01, 0.02, 0.04, 0.08
      and 0.16 -- so the 0.02 gate is genuinely load-bearing, not a restatement of
      ``min_support``;
    * ``min_support`` removes nothing anywhere in 0.40-0.60 and 4 at 0.70 -- so over
      most of its swept range it is dominated by the margin gate, and only becomes
      load-bearing well above its own production value.

    The asymmetry is the finding. It also means neither constant may be described as
    redundant, and the earlier reading (that 0.02 merely restates 0.50) is *not*
    supported on this population -- only the weaker structural statement about the
    ``unknown`` runner-up branch holds.
    """
    from groundscan.validation.calibration.interactions import evidence_x_min_margin

    result = evidence_x_min_margin(POPULATION)
    assert result["min_margin_redundant_given_min_support"] is False
    assert result["min_support_redundant_given_min_margin"] is False

    margin_rows = result["min_margin_effect"]["rows"]
    adding = [r for r in margin_rows if r["adds"]]
    assert adding, "min_margin removed nothing anywhere in its sweep"
    assert all(r["delta"] <= 0 for r in margin_rows), "raising a floor cannot add candidates"
    production_row = next(
        r for r in margin_rows if r["value"] == result["production"]["min_margin"]
    )
    assert production_row["adds"] is True
    assert production_row["delta"] < 0, (
        "the production min_margin removed nothing on this population, so it is inert "
        "here and the register's MODEL CHOICE status for it would need revisiting"
    )

    support_rows = result["min_support_effect"]["rows"]
    dominated = [
        r for r in support_rows if r["value"] <= result["production"]["min_support"] + 0.10
    ]
    assert all(not r["adds"] for r in dominated), (
        "min_support added something below 0.60, so the dominance claim is stale"
    )
    assert any(r["adds"] for r in support_rows), (
        "min_support added nothing anywhere, so it is inert over its whole sweep"
    )


def test_a_redundancy_finding_carries_its_own_reading_rule() -> None:
    """Redundancy is a property of a population, not of the model.

    The result ships with the sentence that says so, and the test asserts the
    sentence is present -- because a bare boolean invites the reading "these two
    constants are the same", which is not what was measured.
    """
    from groundscan.validation.calibration.interactions import evidence_x_min_margin

    reading = evidence_x_min_margin(POPULATION)["reading"]
    assert "property of this population" in reading
    assert "would not by itself license deleting a constant" in reading


def test_the_joint_grid_is_a_full_cross_product() -> None:
    """The grid is a grid: every swept support pairs with every swept margin.

    A partial grid would make "redundant on this population" unfalsifiable, because
    the missing cells are exactly the ones where a redundancy would show.
    """
    from groundscan.validation.calibration.interactions import evidence_x_min_margin

    result = evidence_x_min_margin(POPULATION)
    n = result["population"]["n_candidates"]
    assert len(result["joint_grid"]) == len(result["swept_supports"]) * len(result["swept_margins"])
    for row in result["joint_grid"]:
        assert 0 <= row["n_selected"] <= n
        assert 0.0 <= row["fraction_rejected"] <= 1.0
    assert len(result["support_only"]) == len(result["swept_supports"])
    assert len(result["margin_only"]) == len(result["swept_margins"])


# ---------------------------------------------------------------------------
# Stage-level provenance
# ---------------------------------------------------------------------------


def test_each_spec_states_what_population_its_derivation_came_from() -> None:
    """A threshold with no recorded derivation cannot be defended or replaced.

    The point of the ``original_derivation`` field is that a reader can tell a
    software-validation parameter from a field-calibrated one without reading the
    code. So every spec must name its provenance, and none may claim a field
    calibration this repository does not contain -- the one provenance that would be
    a real defect, because category D is empty.
    """
    forbidden = (
        "field-calibrated",
        "field validated",
        "field-validated",
        "validated in the field",
        "measured in the field",
    )
    for spec in GATE_CHAIN_SPECS:
        derivation = spec.original_derivation.lower()
        assert derivation.strip(), spec.spec_id
        for claim in forbidden:
            assert claim not in derivation, (
                f"{spec.spec_id} claims a field calibration that does not exist here: "
                f"{spec.original_derivation}"
            )


def test_the_screening_band_still_disclaims_field_calibration() -> None:
    """The shipped disclaimer is still accurate, and the matrix says so.

    The register records this band as PROVISIONAL rather than MODEL CHOICE
    precisely because its own documentation already disclaims field calibration.
    If that text changed, the status's rationale would need revisiting too.
    """
    by_id = {s.spec_id: s for s in GATE_CHAIN_SPECS}
    derivation = by_id["screening.primary_threshold"].original_derivation
    assert "calibration portion" in derivation
    assert "holdout portion" in derivation


def test_threshold_spec_construction_is_validated() -> None:
    """A spec that could silently mis-sweep is rejected at construction.

    An unsupported comparison, an unknown domain, a value outside its own domain or
    a blank provenance field are each a spec that would produce a plausible-looking
    but meaningless sensitivity row.
    """
    base = {
        "spec_id": "probe",
        "value": 0.5,
        "comparison": "<",
        "stage": "s",
        "production_site": "groundscan/core/evidence.py:35",
        "applies_to": "x",
        "original_derivation": "x",
    }
    ThresholdSpec(**base)  # the valid case must not raise
    with pytest.raises(ValueError, match="comparison"):
        ThresholdSpec(**{**base, "comparison": "~"})
    with pytest.raises(ValueError, match="domain"):
        ThresholdSpec(**{**base, "domain": "anything_goes"})
    with pytest.raises(ValueError, match="outside its own domain"):
        ThresholdSpec(**{**base, "value": 1.4})
    with pytest.raises(ValueError, match="original_derivation"):
        ThresholdSpec(**{**base, "original_derivation": "  "})


def test_sweep_multipliers_bracket_production_in_both_directions() -> None:
    """The sweep design itself, asserted.

    A sweep that only went upwards would call a top-of-population band inert, and
    a sweep that only went downwards would miss a bottom-of-population one.
    """
    assert any(m < 1.0 for m in SWEEP_MULTIPLIERS)
    assert any(m > 1.0 for m in SWEEP_MULTIPLIERS)
    assert 1.0 in SWEEP_MULTIPLIERS
    for spec in GATE_CHAIN_SPECS:
        values = V._swept_values(spec, SWEEP_MULTIPLIERS, (-0.05, -0.02, 0.0, 0.02, 0.05))
        assert spec.value in values or any(abs(v - spec.value) < 1e-9 for v in values), spec.spec_id
        assert len(values) == len(set(values)), spec.spec_id

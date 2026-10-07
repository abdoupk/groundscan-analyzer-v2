"""Phases J, K and L -- the operating envelope, the decision table, and activation.

The register and the envelope are the two artefacts a reader actually consults, so
the tests are mostly about whether they can be trusted rather than about their
contents:

* **one status per parameter**, drawn from a closed vocabulary, with the two roll-ups
  consistent with the records;
* **no parameter is ACTIVATED**, asserted as the stage's headline result;
* every **CALIBRATED** record names a closed-form derivation and an independent
  check -- the one status that could be granted carelessly, and the one a reader
  would most want to challenge;
* every **INSUFFICIENT EVIDENCE** record points at something measurable or says
  plainly that nothing would;
* the envelope's three tiers are **mutually exclusive and exhaustive**, and every
  ``unknown`` row has a ``None`` value rather than a plausible-looking number.

The individual measured values live in the other files of this suite; these tests
assert the *structure* and the *self-consistency* of the summary artefacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundscan.validation.calibration.envelope import (
    ENVELOPE_TIERS,
    TIER_ASSUMPTION,
    TIER_UNKNOWN,
    TIER_VALIDATED,
    operating_envelope,
)
from groundscan.validation.calibration.register import (
    ACTIVATION_ACTIVATED,
    ACTIVATION_DECISIONS,
    ACTIVATION_NOT_ACTIVATED,
    ACTIVATION_PROVISIONAL,
    ACTIVATION_REQUIRES_FIELD_VALIDATION,
    PARAMETER_STATUSES,
    STATUS_CALIBRATED,
    STATUS_EMPIRICAL_VALIDATION_REQUIRED,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_MODEL_CHOICE,
    STATUS_NOT_APPLICABLE,
    STATUS_PROVISIONAL,
    ParameterRecord,
    activation_decisions,
    parameter_register,
    register_report,
    status_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER = parameter_register()
ENVELOPE = operating_envelope()


# ---------------------------------------------------------------------------
# Phase K -- the decision table's structure
# ---------------------------------------------------------------------------


def test_every_brief_parameter_appears_in_the_register() -> None:
    """The nine questions the brief names, plus the interactions and the stages.

    Absence is the failure mode here: a parameter nobody wrote down is a parameter
    nobody decided about.
    """
    ids = {record.parameter_id for record in REGISTER}
    required = {
        "d_res",
        "min_size",
        "min_margin",
        "solidity.band.shape_irregular",
        "solidity.band.geology",
        "solidity.band.recovery_note",
        "geometry_quality.solidity_weight",
        "threshold.3sigma",
        "threshold.sigma_claim",
        "evidence.min_support",
        "compactness.metal_min_compactness",
        "compactness.estimator",
        "screening.primary_threshold",
        "field_evidence",
        "scale_status_x_anomaly_zscore",
        "s01_decomposition.d_res",
        "review_status_bands",
        "evidence.unknown_floor",
        "min_margin.instability_zone",
        "d_res.response_width_dependence",
    }
    assert required <= ids, sorted(required - ids)
    assert len(ids) == len(REGISTER), "duplicate parameter_id"


def test_every_record_carries_exactly_one_status_from_the_closed_vocabulary() -> None:
    for record in REGISTER:
        assert record.status in PARAMETER_STATUSES, record.parameter_id
        assert record.activation in ACTIVATION_DECISIONS, record.parameter_id
    assert set(PARAMETER_STATUSES) == {
        STATUS_CALIBRATED,
        STATUS_PROVISIONAL,
        STATUS_MODEL_CHOICE,
        STATUS_EMPIRICAL_VALIDATION_REQUIRED,
        STATUS_INSUFFICIENT_EVIDENCE,
        STATUS_NOT_APPLICABLE,
    }
    assert set(ACTIVATION_DECISIONS) == {
        ACTIVATION_ACTIVATED,
        ACTIVATION_NOT_ACTIVATED,
        ACTIVATION_PROVISIONAL,
        ACTIVATION_REQUIRES_FIELD_VALIDATION,
    }


def test_every_record_fills_every_field_the_brief_asks_for() -> None:
    """Value, unit, dataset, sample count, derivation, uncertainty, applicability.

    A field left empty is a field a reader will assume is unimportant, which is the
    opposite of the truth for most of these parameters.
    """
    for record in REGISTER:
        for name in (
            "question",
            "unit",
            "dataset",
            "derivation",
            "uncertainty",
            "applicability",
            "rationale",
            "recommended_action",
        ):
            value = getattr(record, name)
            assert isinstance(value, str) and value.strip(), (record.parameter_id, name)
        assert isinstance(record.sample_count, int), record.parameter_id
        assert record.sample_count >= 0, record.parameter_id
        assert isinstance(record.production_sites, tuple), record.parameter_id


def test_the_current_value_is_read_from_production_not_copied() -> None:
    """Each shipped value is verified against the source file it names.

    A register whose ``current_value`` had drifted from the code would describe a
    system that does not exist, and the drift would be invisible: the table would
    still read as a complete answer.
    """
    verified = 0
    for record in REGISTER:
        if record.current_value is None or not record.production_sites:
            continue
        numeric = isinstance(record.current_value, (int, float))
        for site in record.production_sites:
            path = site.split(":", 1)[0].strip()
            resolved = REPO_ROOT / path
            assert resolved.is_file(), (record.parameter_id, path)
            text = resolved.read_text(encoding="utf-8")
            if numeric:
                needle = str(record.current_value)
                assert needle in text or needle.rstrip("0").rstrip(".") in text, (
                    f"{record.parameter_id}: value {record.current_value} not found in {path}"
                )
                verified += 1
    assert verified >= 10, (
        "too few register values were checked against production to be meaningful"
    )


def test_no_parameter_is_activated() -> None:
    """The stage's headline result, asserted rather than narrated.

    Characterization against a corpus that contains no field ground truth cannot
    justify a production change. Reporting that as zero activations is the honest
    outcome; reporting a number that happens to improve regression results would not
    be.
    """
    decisions = activation_decisions(REGISTER)
    activated = [k for k, v in decisions.items() if v == ACTIVATION_ACTIVATED]
    assert activated == [], f"parameters activated without independent evidence: {activated}"
    report = register_report()
    assert report["n_activated"] == 0
    assert sum(report["activation_counts"].values()) == len(REGISTER)


def test_the_activation_roll_up_is_consistent_with_the_records() -> None:
    report = register_report()
    counts = report["activation_counts"]
    assert sum(counts.values()) == report["n_parameters"] == len(REGISTER)
    assert report["status_counts"] == status_counts(REGISTER)
    for record in REGISTER:
        assert counts[record.activation] >= 1
    assert counts[ACTIVATION_REQUIRES_FIELD_VALIDATION] == 1, (
        "exactly one parameter -- the field-evidence gap -- should require field validation"
    )


def test_a_calibrated_record_names_a_closed_form_and_an_independent_check() -> None:
    """The one status that could be granted carelessly, checked hardest.

    ``CALIBRATED`` means determined by mathematics from the construction, with a
    check that does not go through the code being validated. Anything less would be
    a fitted number wearing the word.
    """
    calibrated = [r for r in REGISTER if r.status == STATUS_CALIBRATED]
    assert calibrated, "no parameter was calibrated, which would itself be suspicious"
    for record in calibrated:
        assert record.sample_count > 0, record.parameter_id
        derivation = record.derivation.lower()
        assert any(token in derivation for token in ("closed form", "exactly", "closed-form")), (
            record.parameter_id
        )
        assert "uncert" not in derivation or "none" in derivation, record.parameter_id
        assert record.uncertainty.strip(), record.parameter_id
        assert "applies only" in record.applicability.lower() or (
            "only" in record.applicability.lower()
        ), f"{record.parameter_id} must state the domain of validity"
        assert record.measured_evidence, record.parameter_id


def test_a_model_choice_record_says_why_the_alternatives_were_not_chosen() -> None:
    """``MODEL CHOICE`` means a free parameter, so the alternatives must be named.

    The claim is that nothing available discriminates between the value in the code
    and its neighbours. That is only a meaningful claim if the neighbours are
    identified.
    """
    model_choices = [r for r in REGISTER if r.status == STATUS_MODEL_CHOICE]
    assert model_choices, "no parameter was a model choice"
    for record in model_choices:
        text = (record.rationale + record.uncertainty + record.applicability).lower()
        assert any(
            token in text
            for token in ("no evidence", "nothing available", "not inert", "chosen", "policy")
        ), record.parameter_id


def test_an_insufficient_evidence_record_says_what_would_change_it() -> None:
    """A gap with no remedy named is a gap nobody intends to close."""
    gaps = [r for r in REGISTER if r.status == STATUS_INSUFFICIENT_EVIDENCE]
    assert gaps, "no parameter was recorded as insufficiently evidenced"
    for record in gaps:
        text = (record.recommended_action + record.rationale).lower()
        assert any(
            token in text
            for token in ("field", "requires", "revisit", "harness", "unavailable", "leave")
        ), record.parameter_id


def test_a_not_applicable_record_says_why_the_question_does_not_arise() -> None:
    """``NOT APPLICABLE`` is a claim about reachability, not a dismissal."""
    not_applicable = [r for r in REGISTER if r.status == STATUS_NOT_APPLICABLE]
    assert not_applicable
    for record in not_applicable:
        text = (record.rationale + record.applicability).lower()
        assert any(
            token in text
            for token in ("does not", "no longer", "confined", "nests", "conservative", "dead")
        ), record.parameter_id
        assert record.recommended_action.strip(), record.parameter_id


def test_the_provisional_and_empirical_validation_statuses_are_distinct() -> None:
    """``PROVISIONAL`` is in service; ``EMPIRICAL VALIDATION REQUIRED`` is not.

    Collapsing them would lose the only useful distinction: whether a number is
    currently doing work, or is waiting for a measurement before it can.
    """
    provisional = [r for r in REGISTER if r.status == STATUS_PROVISIONAL]
    needs_validation = [r for r in REGISTER if r.status == STATUS_EMPIRICAL_VALIDATION_REQUIRED]
    assert provisional and needs_validation
    assert {r.parameter_id for r in provisional}.isdisjoint({
        r.parameter_id for r in needs_validation
    })
    for record in needs_validation:
        text = (record.derivation + record.uncertainty).lower()
        assert "field" in text or "independent evidence" in text, record.parameter_id


def test_the_register_is_json_serializable_in_full() -> None:
    text = json.dumps(register_report(), default=str)
    assert len(text) > 5000
    assert json.loads(text)["n_parameters"] == len(REGISTER)


def test_a_record_with_an_unknown_status_is_rejected_at_construction() -> None:
    """The vocabulary is closed at construction, not validated on the way out."""
    base = REGISTER[0]
    with pytest.raises(ValueError, match="status"):
        ParameterRecord(
            parameter_id="probe",
            question=base.question,
            current_value=None,
            unit=base.unit,
            production_sites=(),
            status="VERY CALIBRATED",
            dataset=base.dataset,
            sample_count=0,
            derivation=base.derivation,
            uncertainty=base.uncertainty,
            applicability=base.applicability,
            rationale=base.rationale,
            recommended_action=base.recommended_action,
            activation=ACTIVATION_NOT_ACTIVATED,
        )
    with pytest.raises(ValueError, match="activation"):
        ParameterRecord(
            parameter_id="probe",
            question=base.question,
            current_value=None,
            unit=base.unit,
            production_sites=(),
            status=STATUS_PROVISIONAL,
            dataset=base.dataset,
            sample_count=0,
            derivation=base.derivation,
            uncertainty=base.uncertainty,
            applicability=base.applicability,
            rationale=base.rationale,
            recommended_action=base.recommended_action,
            activation="ACTIVATED, PROBABLY",
        )


def test_the_register_does_not_claim_a_field_calibration_it_cannot_have() -> None:
    """Category D is empty, so no record may claim a field-calibrated number."""
    forbidden = (
        "field-calibrated",
        "field validated",
        "field-validated",
        "validated in the field",
        "measured in the field",
    )
    for record in REGISTER:
        haystack = " ".join((record.derivation, record.uncertainty, record.rationale)).lower()
        for claim in forbidden:
            assert claim not in haystack, (record.parameter_id, claim)


# ---------------------------------------------------------------------------
# Phase J -- the operating envelope
# ---------------------------------------------------------------------------


def test_the_envelope_tiers_are_exhaustive_and_mutually_exclusive() -> None:
    assert set(ENVELOPE["tiers"]) == set(ENVELOPE_TIERS)
    assert ENVELOPE_TIERS == (TIER_VALIDATED, TIER_ASSUMPTION, TIER_UNKNOWN)
    for row in ENVELOPE["rows"]:
        assert row["tier"] in ENVELOPE_TIERS, row["row_id"]
    counts = {tier: 0 for tier in ENVELOPE_TIERS}
    for row in ENVELOPE["rows"]:
        counts[row["tier"]] += 1
    assert ENVELOPE["tier_counts"] == counts
    assert sum(counts.values()) == len(ENVELOPE["rows"])


def test_every_envelope_row_states_its_evidence_and_its_limitation() -> None:
    """A validated range with no stated limitation reads as a specification.

    That is the specific failure the tiers exist to prevent, so the limitation field
    is mandatory and the test checks it is non-empty for every row including the
    validated ones.
    """
    for row in ENVELOPE["rows"]:
        assert row["quantity"].strip(), row["row_id"]
        assert row["unit"].strip(), row["row_id"]
        assert row["evidence"].strip(), row["row_id"]
        assert row["limitation"].strip(), row["row_id"]
        assert len(row["limitation"]) > 20, row["row_id"]


def test_every_unknown_row_has_no_value_rather_than_a_plausible_one() -> None:
    """An unknown reported as a number is a guess wearing a label."""
    unknowns = [r for r in ENVELOPE["rows"] if r["tier"] == TIER_UNKNOWN]
    assert len(unknowns) >= 3
    assert ENVELOPE["n_unknown"] == len(unknowns)
    for row in unknowns:
        assert row["value"] is None, (
            f"{row['row_id']} is tiered unknown but carries the value {row['value']!r}"
        )


def test_the_residual_scale_row_is_an_assumption_not_a_validated_range() -> None:
    """``1e-9`` is an arithmetic floor, and reading it as a resolution would be wrong.

    This is the one numeric row most likely to be mistaken for a specification, so
    its tier is asserted and its limitation is asserted to say so.
    """
    row = next(r for r in ENVELOPE["rows"] if r["row_id"] == "residual.scale")
    assert row["tier"] == TIER_ASSUMPTION
    assert row["value"] == 1e-9
    assert "arithmetic floor" in row["limitation"]
    assert "NOT a physical resolution" in row["limitation"]


def test_the_d_res_row_is_unknown_because_a_single_value_is_not_available() -> None:
    row = next(r for r in ENVELOPE["rows"] if r["row_id"] == "resolution.d_res")
    assert row["tier"] == TIER_UNKNOWN
    assert row["value"] is None
    assert "2*sigma" in row["evidence"]
    assert "single d_res cannot be reported" in row["limitation"]


def test_the_swept_ranges_are_reported_separately_from_the_rows() -> None:
    """A swept range is a test design, and the table must not present it as a spec.

    The ranges live under their own key so a reader can see exactly what was
    exercised, and each validated row names its own basis.
    """
    swept = ENVELOPE["swept_ranges"]
    for key in (
        "pitches_m",
        "dy_ratios",
        "response_sigmas_m",
        "noise_sigmas",
        "response_amplitudes",
    ):
        assert swept[key], key
    validated = [r for r in ENVELOPE["rows"] if r["tier"] == TIER_VALIDATED]
    assert validated
    for row in validated:
        # A validated row must carry a quantity: a validated range stated only in
        # words is exactly the presentation this tier exists to prevent.
        assert any(ch.isdigit() for ch in row["evidence"]), (
            f"{row['row_id']} is tiered validated with no measured quantity in its evidence"
        )
        assert row["value"] is not None, row["row_id"]


def test_the_field_ground_truth_gap_is_in_the_envelope() -> None:
    """The absence of category D must be visible in the envelope, not only in the register."""
    row = next(r for r in ENVELOPE["rows"] if r["row_id"] == "field.ground_truth")
    assert row["tier"] == TIER_UNKNOWN
    assert "excavated" in row["limitation"]
    assert "annotation" in row["limitation"]


def test_the_envelope_is_json_serializable_in_full() -> None:
    text = json.dumps(ENVELOPE, default=str)
    assert len(text) > 3000
    assert json.loads(text)["tier_counts"] == ENVELOPE["tier_counts"]


def test_the_roll_up_never_proceeds_to_field_release_claims() -> None:
    """The register and the envelope must not combine to assert field readiness.

    The single parameter that requires field validation is the field-evidence gap
    itself, and no record claims a field-calibrated number. Together those two facts
    are the boundary of what this stage may conclude, and they are asserted rather
    than left to the reader's inference.
    """
    report = register_report()
    requiring = [r for r in REGISTER if r.activation == ACTIVATION_REQUIRES_FIELD_VALIDATION]
    assert [r.parameter_id for r in requiring] == ["field_evidence"]
    calibrated = [r for r in REGISTER if r.status == STATUS_CALIBRATED]
    assert all("field" not in r.applicability.lower() for r in calibrated)
    assert report["n_activated"] == 0
    assert ENVELOPE["n_unknown"] >= 3

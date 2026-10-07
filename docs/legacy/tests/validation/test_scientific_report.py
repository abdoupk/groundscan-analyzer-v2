"""Science report contract: taxonomy, schema, strict JSON (P4)."""

import json

from groundscan.validation.payload_schema import validate_science_report_payload
from groundscan.validation.science_reporting import sanitize_json, write_science_report
from groundscan.validation.scientific import (
    SCIENCE_SCHEMA_VERSION,
    assemble_science_report,
    run_science,
)


def test_science_smoke_report_passes_schema(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    assert report["verdict"] == "pass"
    body = {k: v for k, v in report.items() if not k.startswith("_")}
    assert validate_science_report_payload(body) == []


def test_report_artifact_is_strict_json(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    body = {k: v for k, v in report.items() if not k.startswith("_")}
    paths = write_science_report(body, tmp_path / "out")
    text = paths["json"].read_text(encoding="utf-8")
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in text
    assert json.loads(text) == sanitize_json(body)
    assert paths["markdown"].read_text(encoding="utf-8").startswith("# Science validation report")


def test_evidence_taxonomy_and_field_unknown(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    kinds = {name: section["evidence_kind"] for name, section in report["sections"].items()}
    assert kinds["mathematical"] == "scientific"
    assert kinds["synthetic"] == "scientific"
    assert kinds["adversarial"] == "scientific"
    assert kinds["metamorphic"] == "scientific"
    assert kinds["reference_compatibility"] == "reference"
    assert kinds["regression_protection"] == "regression"
    assert kinds["field_validation"] == "empirical"
    assert report["sections"]["field_validation"]["status"] == "unknown"
    assert report["science_schema_version"] == SCIENCE_SCHEMA_VERSION

    def _keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from _keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from _keys(item)

    section_keys = set(_keys(report["sections"]["synthetic"]))
    assert not ({"recall", "precision", "accuracy"} & section_keys)


def test_gating_flags_and_verdict_basis_are_explicit(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    sections = report["sections"]
    for name in ("mathematical", "synthetic", "adversarial", "metamorphic"):
        assert sections[name]["gating"] is True
    for name in ("reference_compatibility", "regression_protection", "field_validation"):
        assert sections[name]["gating"] is False
    assert report["verdict_basis"] == [
        "mathematical",
        "synthetic",
        "adversarial",
        "metamorphic",
    ]
    for family, metrics in sections["synthetic"]["families"].items():
        assert metrics["gating"] is True, family
    review_pairs = [
        p for p in sections["metamorphic"]["pair_records"] if p["strength"] == "review_required"
    ]
    assert review_pairs, "expected review-only pairs in the record"
    assert all(p["gating"] is False for p in review_pairs)
    assert all(
        p["gating"] is True
        for p in sections["metamorphic"]["pair_records"]
        if p["strength"] != "review_required"
    )


def test_documented_limitations_are_registered_not_hidden(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    adversarial = report["sections"]["adversarial"]
    limitations = adversarial["limitations"]
    assert limitations, "smooth-noise/gradient cases must appear as limitations"
    limited_ids = {entry["case_id"] for entry in limitations}
    binned_limitation = sum(
        1 for record in adversarial["case_records"] if record["verdict"] == "documented_limitation"
    )
    assert len(limitations) == binned_limitation
    assert adversarial["status"] == "pass"
    # A limitation is tracked: every registered entry carries its allowance context.
    for entry in limitations:
        assert entry["detail"]
        assert entry["retained_candidates"] >= 0
    assert set(limited_ids) <= {r["case_id"] for r in adversarial["case_records"]}


def test_no_unified_scientific_score(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    for forbidden in ("score", "grade", "rating", "overall_accuracy"):
        assert forbidden not in report
        assert forbidden not in report["sections"]


def test_operating_point_carries_no_claim(tmp_path):
    report = run_science(tmp_path / "science", mode="smoke")
    operating = report["operating_point"]
    assert operating["status"] == "documented-default"
    assert operating["scientific_claim"].startswith("none")
    assert operating["policy_version"] == "rescue-screening"


def test_sanitize_json_replaces_non_finite():
    clean = sanitize_json({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.0}})
    assert clean == {"a": None, "b": [1.0, None], "c": {"d": 2.0}}


def test_assembled_report_verdict_is_conjunction():
    base = {
        "evidence_kind": "scientific",
        "validation_domain": "x",
        "status": "pass",
        "gating": True,
        "converts_to": [],
    }
    good = assemble_science_report(dict(base), dict(base), dict(base), dict(base))
    assert good["verdict"] == "pass"
    bad_math = dict(base, status="fail")
    bad = assemble_science_report(bad_math, dict(base), dict(base), dict(base))
    assert bad["verdict"] == "fail"

"""Scientific synthetic ground-truth validation (P1).

Frozen oracle over the existing generator: Hungarian one-to-one matching,
pattern compatibility, 3.0 m gate, per-family floors. All metrics are
synthetic-only by construction (synthetic_* names) and must never be read
as field accuracy.
"""

from pathlib import Path

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.synthetic_core.core import (
    generate_scan,
    ladder_scenarios,
    scenario_catalog,
)
from groundscan.validation.synthetic_core.oracles import (
    MATCH_DISTANCE_TOLERANCE_M,
    ORACLE_VERSION,
    check_oracle_result,
    evaluate_oracle_case,
)


def _run(scenario, tmp_path):
    scan, truth = generate_scan(scenario)
    _, _, candidates = analyze_scan(
        scan,
        tmp_path / scenario.name,
        label=scenario.name,
        config=AnalysisConfig(),
        write_outputs=False,
    )
    return evaluate_oracle_case(candidates, truth, case_id=scenario.name, family=scenario.name)


def test_oracle_version_pinned():
    # Floor/tolerance/allowance changes must bump this deliberately.
    assert ORACLE_VERSION == "1.0"
    assert MATCH_DISTANCE_TOLERANCE_M == 3.0


def test_catalog_families_meet_frozen_floors(tmp_path):
    failures = []
    for scenario in scenario_catalog():
        result = _run(scenario, tmp_path)
        for failure in check_oracle_result(result):
            failures.append(f"{scenario.name}: {failure}")
    assert failures == []


def test_ladder_families_meet_frozen_floors(tmp_path):
    failures = []
    for scenario in ladder_scenarios():
        result = _run(scenario, tmp_path)
        for failure in check_oracle_result(result):
            failures.append(f"{scenario.name}: {failure}")
    assert failures == []


def test_operating_point_is_provenance_not_science(tmp_path):
    scenario = scenario_catalog()[0]
    result = _run(scenario, tmp_path)
    operating = result["operating_point"]
    assert operating["status"] == "documented-default"
    assert operating["policy_version"] == "rescue-screening"
    assert operating["scientific_claim"].startswith("none")


def test_oracle_output_uses_domain_prefixed_metrics(tmp_path):
    scenario = scenario_catalog()[0]
    result = _run(scenario, tmp_path)
    assert "synthetic_recall" in result
    assert "synthetic_precision" in result
    assert "recall" not in result
    assert "precision" not in result
    assert "accuracy" not in result


def test_oracle_rejects_unknown_family():
    result = {
        "family": "not-a-family",
        "synthetic_recall": 1.0,
        "synthetic_precision": 1.0,
        "synthetic_center_error_m": 0.0,
        "synthetic_depth_error_m": 0.0,
        "false_positives": 0,
        "polarity_correct": 0,
        "polarity_checked": 0,
        "orientation_errors_deg": [],
    }
    assert check_oracle_result(result) != []


def test_oracle_does_not_import_detector_response_internals():
    import groundscan.validation.synthetic_core.oracles as oracles

    source = Path(oracles.__file__).read_text(encoding="utf-8")
    for private in ("_gaussian_rotated", "_target_response"):
        assert private not in source

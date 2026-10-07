"""P1 gap-closer: validation shims (0% -> covered) + field positive/depth + extraction helpers."""

from __future__ import annotations

import json

from groundscan import Candidate


def _cand(**overrides) -> Candidate:
    base = dict(
        id=7,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    base.update(overrides)
    return Candidate(**base)


def test_profiles_data_shape():
    from groundscan.validation import profiles

    assert profiles.FAST_SUITES == ["tests/unit"]
    assert "tests/integration" in profiles.FULL_SUITES
    assert len(profiles.RELEASE_STEPS) == 7
    assert [s[0] for s in profiles.RELEASE_STEPS] == [
        "unit",
        "integration",
        "regression",
        "contracts",
        "goldens",
        "equivalence",
        "release-gates",
    ]
    assert "tests/validation" in profiles.RELEASE_SUITES
    assert "tests/experimental" in profiles.EXPERIMENTAL_SUITES


def test_extraction_false_positives_counts_far_candidates():
    from groundscan.validation.extraction import _false_positives
    from groundscan.validation.synthetic_core.core import SyntheticTarget

    targets = (SyntheticTarget("positive_compact", 5.0, 5.0),)
    near = _cand(x_center=5.5, y_center=5.0)
    far = _cand(x_center=50.0, y_center=50.0)
    assert _false_positives([near], targets) == 0
    assert _false_positives([near, far], targets) == 1
    assert _false_positives([], targets) == 0


def _write_manifest(tmp_path, cases):
    p = tmp_path / "m.json"
    p.write_text(
        json.dumps({"independent_field_ground_truth": True, "cases": cases}),
        encoding="utf-8",
    )
    (tmp_path / "dummy.csv").write_text("x,y,signal\n0,0,1\n", encoding="utf-8")
    return p


def test_field_positive_position_and_depth_paths(tmp_path, monkeypatch):
    import groundscan.validation.field as F

    c = _cand(
        x_center=10.0,
        y_center=10.0,
        pattern_hypothesis="metallic-like",
        evidence_score=0.9,
        depth_estimate=2.0,
    )

    def _fake_analyze(scan, out_dir, label="scan", **kwargs):
        return (object(), object(), [c])

    monkeypatch.setattr(F, "analyze_scan", _fake_analyze)
    monkeypatch.setattr(F, "load_scan", lambda path: object())

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "case_id": "pos1",
                "scan_path": "dummy.csv",
                "target_present": True,
                "expected_patterns": ["metallic-like"],
                "x": 10.5,
                "y": 10.0,
                "tolerance_m": 3.0,
                "depth_m": 2.1,
                "depth_tolerance_m": 0.5,
            },
            {
                "case_id": "pos2",
                "scan_path": "dummy.csv",
                "target_present": True,
                "expected_patterns": [],
                "depth_m": 5.0,
                "depth_tolerance_m": 0.2,
            },
        ],
    )
    result = F.evaluate_field_dataset(manifest, out_dir=None)
    assert result["cases"] == 2
    rows = {r["case_id"]: r for r in result["rows"]}
    assert rows["pos1"]["passed"] is True
    assert rows["pos1"]["position_ok"] is True
    assert rows["pos1"]["depth_ok"] is True
    # pos2 depth far from estimate -> depth_ok False -> not passed
    assert rows["pos2"]["depth_ok"] is False
    assert rows["pos2"]["passed"] is False
    assert result["positive_cases"] == 2


def test_field_no_position_selects_highest_evidence(tmp_path, monkeypatch):
    import groundscan.validation.field as F

    low = _cand(
        id=1, x_center=0.0, y_center=0.0, evidence_score=0.2, pattern_hypothesis="metallic-like"
    )
    high = _cand(
        id=2, x_center=9.0, y_center=9.0, evidence_score=0.95, pattern_hypothesis="metallic-like"
    )

    monkeypatch.setattr(
        F, "analyze_scan", lambda scan, out_dir, label="s", **k: (None, None, [low, high])
    )
    monkeypatch.setattr(F, "load_scan", lambda path: object())

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "case_id": "nopos",
                "scan_path": "dummy.csv",
                "target_present": True,
                "expected_patterns": ["metallic-like"],
            },
        ],
    )
    result = F.evaluate_field_dataset(manifest, out_dir=None)
    assert result["rows"][0]["selected_candidate_id"] == 2

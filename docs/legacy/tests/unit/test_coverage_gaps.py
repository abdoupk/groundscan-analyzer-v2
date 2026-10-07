"""Pins for historic coverage gaps: agreement, soil, field, extraction (fast)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from groundscan import Candidate, ScanMetadata
from groundscan.core.grid import Grid2D


def _cand(**overrides) -> Candidate:
    base = dict(
        id=1,
        x_center=8.0,
        y_center=8.0,
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
        evidence_score=0.8,
        scan_count=1,
        scale_class="local",
    )
    base.update(overrides)
    return Candidate(**base)


def _grid(n=16, value=1.0) -> Grid2D:
    x = np.arange(n, dtype=float)
    return Grid2D(
        x_centers=x,
        y_centers=x.copy(),
        signal=np.full((n, n), value),
        depth=np.full((n, n), 2.0),
        counts=np.ones((n, n), dtype=int),
    )


def _alignment(n=20, value=5.0, valid=True, correlation=0.95):
    from groundscan.site.registration import AlignmentResult

    return AlignmentResult(
        transform_name="translation",
        shift_dy=0,
        shift_dx=0,
        correlation=correlation,
        overlap_fraction=1.0,
        b_resampled=np.full((n, n), value),
        b_valid=np.full((n, n), valid),
        ambiguity_margin=0.2,
        multiscale_correlation=0.9,
    )


# --- site/agreement (diagnostic-only, F-07) -----------------------------------


def test_patch_indices_stay_in_bounds():
    from groundscan.site.agreement import _candidate_patch_indices

    c = _cand(x_center=0.0, y_center=0.0, width=40.0, height=40.0)
    rs, cs = _candidate_patch_indices(c, _grid(), 20)
    assert 0 <= rs.start < rs.stop <= 20
    assert 0 <= cs.start < cs.stop <= 20


def test_agreement_no_valid_region_marks_unevaluable():
    from groundscan.site.agreement import cross_scan_agreement

    c = _cand()
    out = cross_scan_agreement([c], _grid(), _alignment(valid=False))
    assert out[0].cross_scan_agreement is None
    assert "not evaluable" in (out[0].notes or "")


def test_agreement_strong_support_never_raises_confidence():
    from groundscan.site.agreement import cross_scan_agreement

    c = _cand(confidence=0.8)
    out = cross_scan_agreement([c], _grid(), _alignment(value=7.0))
    score = out[0].cross_scan_agreement
    assert score is not None and 0.0 <= score <= 1.0
    assert out[0].confidence == 0.8
    assert "diagnostic only" in (out[0].notes or "")


def test_agreement_conflicting_sign_note():
    from groundscan.site.agreement import cross_scan_agreement

    c = _cand()
    out = cross_scan_agreement([c], _grid(), _alignment(value=-7.0))
    assert out[0].cross_scan_agreement == 0.0
    assert "conflicting" in (out[0].notes or "")


def test_append_note_empty_and_chained():
    from groundscan.site.agreement import _append_note

    assert _append_note("", "hi") == "hi"
    assert _append_note("a", "b") == "a; b"


# --- soil/context ---------------------------------------------------------------


def test_mineralization_risk_clamps_and_nan():
    from groundscan.soil.context import mineralization_risk_from_pct

    assert mineralization_risk_from_pct(None) == 0.0
    assert mineralization_risk_from_pct(float("nan")) == 0.0
    assert mineralization_risk_from_pct(-5.0) == 0.0
    assert mineralization_risk_from_pct(150.0) == 1.0
    assert mineralization_risk_from_pct(50.0) == 0.5


def test_build_soil_context_flags_invalid():
    from groundscan.soil.context import build_soil_context

    ctx = build_soil_context(ScanMetadata(mineralization_pct="not-a-number", humidity_pct=150.0))
    assert "mineralization_pct" in ctx["invalid_factors"]
    assert "humidity_pct" in ctx["invalid_factors"]
    assert ctx["used_for_signal_correction"] is False


def test_confounder_flags_high_and_elevated():
    from groundscan.soil.context import soil_confounder_context

    high = soil_confounder_context(ScanMetadata(mineralization_pct=90.0))
    assert "high-mineralization-risk" in high["flags"]
    mid = soil_confounder_context(ScanMetadata(mineralization_pct=40.0))
    assert "elevated-mineralization-risk" in mid["flags"]
    low = soil_confounder_context(ScanMetadata())
    assert low["flags"] == []
    assert low["used_for_detector_correction"] is False


def test_soil_summary_three_branches():
    from groundscan.soil.context import soil_context_summary

    assert "No exported soil factors" in soil_context_summary(ScanMetadata())
    assert "invalid values" in soil_context_summary(
        ScanMetadata(humidity_pct=40.0, mineralization_pct="xx")
    )
    assert "no signal/depth correction" in soil_context_summary(ScanMetadata(humidity_pct=40.0))


# --- soil/experimental ------------------------------------------------------------


def test_finite_positive_rejects():
    from groundscan.soil.experimental import _finite_positive

    assert _finite_positive(None) is None
    assert _finite_positive(-2.0) is None
    assert _finite_positive(float("nan")) is None
    assert _finite_positive("bad") is None
    assert _finite_positive(2.5) == 2.5


def test_physics_velocity_math():
    from groundscan.soil.experimental import C_M_PER_NS, soil_physics_diagnostics

    assert soil_physics_diagnostics(ScanMetadata()).refractive_index is None
    d = soil_physics_diagnostics(ScanMetadata(dielectric_constant=9.0, relative_permeability=1.0))
    assert d.refractive_index == 3.0
    assert d.wave_velocity_m_per_ns == C_M_PER_NS / 3.0
    assert d.relative_velocity_to_air == 1.0 / 3.0


def test_twt_depth_requires_soil_factors():
    from groundscan.soil.experimental import depth_from_twt_ns

    with pytest.raises(ValueError):
        depth_from_twt_ns(np.array([10.0]), ScanMetadata())


def test_scale_weights_edges():
    from groundscan.soil.experimental import soil_scale_weights

    assert soil_scale_weights([], 80.0).size == 0
    assert list(soil_scale_weights([5], 80.0)) == [1.0]
    w = soil_scale_weights([3, 5, 9], None)
    assert len(w) == 3 and abs(float(np.sum(w)) - 1.0) < 1e-9


def test_ab_summary_edges():
    from groundscan.soil.experimental import soil_ab_summary

    empty = soil_ab_summary(np.full((4, 4), np.nan), np.full((4, 4), np.nan), 3.0)
    assert empty["baseline_flag_fraction"] == 0.0
    same = soil_ab_summary(np.ones((6, 6)) * 5.0, np.ones((6, 6)) * 5.0, 3.0)
    assert same["flag_overlap"] == 1.0


def test_compare_depth_channels_edges():
    from groundscan.soil.experimental import compare_depth_channels

    g = _grid(n=8)
    assert compare_depth_channels(g, _grid(n=6))["available"] is False
    assert compare_depth_channels(g, g)["available"] is True
    assert compare_depth_channels(g, g)["bias_m"] == 0.0
    nodata = _grid(n=8)
    nodata.depth[:] = np.nan
    assert compare_depth_channels(nodata, _grid(n=8))["available"] is False


def test_depth_diagnostic_branches():
    from groundscan.soil.experimental import soil_depth_diagnostic

    class _Scan:
        def __init__(self, twt):
            self.twt_ns = twt

    assert soil_depth_diagnostic(_Scan(None), ScanMetadata())["available"] is False
    assert soil_depth_diagnostic(_Scan(np.full(4, np.nan)), ScanMetadata())["available"] is False
    ok = soil_depth_diagnostic(
        _Scan(np.array([10.0, 12.0])),
        ScanMetadata(dielectric_constant=9.0, relative_permeability=1.0),
    )
    assert ok["available"] is True
    assert ok["replaces_device_depth"] is False
    assert soil_depth_diagnostic(_Scan(np.array([10.0])), ScanMetadata())["available"] is False


def test_twt_grid_none_without_twt():
    from groundscan.soil.experimental import soil_twt_depth_grid

    class _Scan:
        twt_ns = None

    assert soil_twt_depth_grid(_Scan(), ScanMetadata()) is None


def test_twt_grid_none_on_bad_twt():
    from groundscan.soil.experimental import soil_twt_depth_grid

    class _Scan:
        twt_ns = "not-a-number"

    assert (
        soil_twt_depth_grid(
            _Scan(), ScanMetadata(dielectric_constant=9.0, relative_permeability=1.0)
        )
        is None
    )


def test_sweep_marks_factors():
    from groundscan.soil.experimental import soil_background_factor_sweep

    out = soil_background_factor_sweep(_grid(n=10), ScanMetadata())
    assert out["experimental_factor"] == "homogeneity_pct"
    assert out["factors"]["humidity_pct"]["status"] == "unavailable"
    out2 = soil_background_factor_sweep(_grid(n=10), ScanMetadata(homogeneity_pct=80.0))
    rec = out2["factors"]["homogeneity_pct"]
    assert rec["background_experiment_eligible"] is True
    assert rec["status"] == "experimental"


def test_aware_background_tiny_grid_fallback():
    from groundscan.soil.experimental import soil_aware_background_zscore

    z, weights, residual = soil_aware_background_zscore(
        _grid(n=4), scales=(9, 15), homogeneity_pct=80.0
    )
    assert z.shape == (4, 4)
    assert weights.size == 0


def test_attach_diagnostics_shape():
    from groundscan.soil.experimental import attach_soil_model_diagnostics

    out = attach_soil_model_diagnostics(ScanMetadata(), soil_mode="diagnostic")
    assert out["mode"] == "diagnostic"
    assert out["background"]["applied_to_detector"] is False
    assert out["ab"] is None


# --- validation/field ---------------------------------------------------------------


def test_field_manifest_rejections(tmp_path):
    from groundscan.validation.field import load_field_truth

    def _write(payload):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    with pytest.raises(ValueError):
        load_field_truth(_write({"cases": "nope", "independent_field_ground_truth": True}))
    with pytest.raises(ValueError):
        load_field_truth(_write({"cases": []}))
    with pytest.raises(ValueError):
        load_field_truth(
            _write({"cases": [{"case_id": "a"}], "independent_field_ground_truth": True})
        )
    with pytest.raises(ValueError):
        load_field_truth(
            _write({
                "cases": [{"case_id": "a", "scan_path": "s.csv", "x": 1.0}],
                "independent_field_ground_truth": True,
            })
        )
    with pytest.raises(ValueError):
        load_field_truth(
            _write({
                "cases": [{"case_id": "a", "scan_path": "s.csv", "tolerance_m": 0}],
                "independent_field_ground_truth": True,
            })
        )
    with pytest.raises(ValueError):
        load_field_truth(
            _write({
                "cases": [
                    {
                        "case_id": "a",
                        "scan_path": "s.csv",
                        "depth_m": 2.0,
                        "depth_tolerance_m": 0,
                    }
                ],
                "independent_field_ground_truth": True,
            })
        )


def test_field_manifest_minimal_parses(tmp_path):
    from groundscan.validation.field import load_field_truth

    p = tmp_path / "m.json"
    p.write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "a", "scan_path": "s.csv", "target_present": False}],
        }),
        encoding="utf-8",
    )
    cases = load_field_truth(p)
    assert len(cases) == 1 and cases[0].target_present is False


def test_field_missing_scan_raises(tmp_path):
    from groundscan.validation.field import evaluate_field_dataset

    p = tmp_path / "m.json"
    p.write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "a", "scan_path": "gone.csv", "target_present": False}],
        }),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError):
        evaluate_field_dataset(p, out_dir=tmp_path / "out")


def test_field_negative_case_end_to_end(tmp_path):
    from groundscan.validation.field import evaluate_field_dataset

    rows = ["x,y,signal"]
    for gy in range(12):
        for gx in range(12):
            rows.append(f"{gx}.0,{gy}.0,5.0")
    (tmp_path / "flat.csv").write_text("\n".join(rows), encoding="utf-8")
    (tmp_path / "m.json").write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "neg1", "scan_path": "flat.csv", "target_present": False}],
        }),
        encoding="utf-8",
    )
    result = evaluate_field_dataset(tmp_path / "m.json", out_dir=tmp_path / "out")
    assert result["cases"] == 1
    assert result["negative_cases"] == 1
    assert result["passed"] == 1
    assert (tmp_path / "out" / "field_validation.json").exists()
    assert (tmp_path / "out" / "field_validation.md").exists()


# --- validation/extraction (distance-to-target counting) -----------------


def test_near_candidates_empty_and_sorted():
    from groundscan.validation.extraction import _near_candidates
    from groundscan.validation.synthetic_core.core import SyntheticTarget

    target = SyntheticTarget("positive_compact", 5.0, 5.0)
    assert _near_candidates([], target) == []
    rows = _near_candidates(
        [
            _cand(x_center=20.0, y_center=20.0),
            _cand(x_center=6.0, y_center=5.0, pattern_hypothesis="cavity-like"),
        ],
        target,
        radius=3.0,
    )
    assert len(rows) == 1
    assert rows[0]["pattern"] == "cavity-like"
    assert rows[0]["distance_m"] == 1.0

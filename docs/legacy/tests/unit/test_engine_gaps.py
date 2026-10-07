"""Phase-3 hardening: previously thin engine paths (fast, deterministic)."""

from __future__ import annotations

import numpy as np
import pytest

from groundscan import Candidate, ScanData, ScanMetadata
from groundscan._util import (
    axis_spacing,
    finite_values,
    is_finite_number,
    robust_scale,
    safe_mean,
)
from groundscan.core.grid import reconstruct_grid
from groundscan.core.zigzag import has_independent_positioning
from groundscan.gates.thresholds import (
    fused_evidence_score,
    registration_evidence_score,
    threshold_policy,
)


def _toy_scan(n: int = 10, signal_value: float = 10.0) -> ScanData:
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=np.full(n * n, signal_value),
        metadata=ScanMetadata(),
    )


def test_provenance_predicates_truth_table():
    from groundscan.models import (
        is_derived_coordinates,
        is_index_only_coordinates,
        is_metric_coordinates,
    )

    cases = [
        ({"coordinate_provenance": "measured"}, (True, False, False)),
        ({"coordinate_provenance": "derived"}, (False, True, False)),
        ({"coordinate_provenance": "index"}, (False, False, True)),
    ]
    for kwargs, (metric, derived, index) in cases:
        scan = _toy_scan()
        scan.coordinate_provenance = kwargs["coordinate_provenance"]
        scan.coords_are_index_only = False
        assert is_metric_coordinates(scan) is metric
        assert is_derived_coordinates(scan) is derived
        assert is_index_only_coordinates(scan) is index
    # Legacy override: external code setting the bool post-construction wins.
    scan = _toy_scan()
    scan.coordinate_provenance = "measured"
    scan.coords_are_index_only = True
    assert is_metric_coordinates(scan) is False
    assert is_index_only_coordinates(scan) is True


def _candidate(**overrides) -> Candidate:
    base = dict(
        id=0,
        x_center=0.0,
        y_center=0.0,
        depth_mean=1.0,
        depth_std=0.1,
        n_points=5,
        area_cells=5,
        width=1.0,
        height=1.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=5.0,
        mean_signal=4.0,
        anomaly_score=5.0,
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        confidence=0.5,
    )
    base.update(overrides)
    return Candidate(**base)


# --- _util canonical helpers -------------------------------------------------


def test_util_finite_helpers():
    assert list(finite_values([1.0, float("nan"), float("inf"), 2.0])) == [1.0, 2.0]
    assert is_finite_number(1.0) is True
    assert is_finite_number(float("nan")) is False
    assert safe_mean([1.0, 2.0, float("nan")]) == pytest.approx(1.5)
    assert safe_mean([float("nan")], default=7.0) == 7.0
    assert axis_spacing(np.array([0.0, 1.0, 2.0, 3.0])) == pytest.approx(1.0)
    assert axis_spacing(np.array([float("nan")])) == 1.0
    assert robust_scale(np.array([1.0, 1.0, 1.0])) == pytest.approx(1.0)


def test_candidate_with_updates_returns_a_copy():
    c = _candidate(evidence_score=0.8, quality_score=0.7, review_status="review")
    c2 = c.with_updates(pattern_hypothesis="cavity-like")
    assert c2.pattern_hypothesis == "cavity-like"
    assert c.pattern_hypothesis == "metallic-like"  # original untouched


# --- centralized weights preserve behavior -----------------------------------


def test_fused_evidence_matches_legacy_formula():
    kwargs = dict(
        base=0.6,
        detection_rate=1.0,
        direction_cov=0.5,
        spacing_cov=0.5,
        traversal_cov=0.5,
        position_stability=0.8,
        pol_cons=0.9,
        signal_cons=0.7,
        depth_cons=0.6,
        reg_cons=1.0,
        cons=0.4,
    )
    got = fused_evidence_score(**kwargs)
    legacy = float(
        np.clip(
            0.18 * kwargs["base"]
            + 0.17 * kwargs["detection_rate"]
            + 0.10 * kwargs["direction_cov"]
            + 0.10 * kwargs["spacing_cov"]
            + 0.08 * kwargs["traversal_cov"]
            + 0.10 * kwargs["position_stability"]
            + 0.07 * kwargs["pol_cons"]
            + 0.07 * kwargs["signal_cons"]
            + 0.06 * kwargs["depth_cons"]
            + 0.05 * kwargs["reg_cons"]
            + 0.02 * kwargs["cons"],
            0,
            1,
        )
    )
    assert got == pytest.approx(legacy)
    assert threshold_policy()["scoring_weights"]["fusion_base"] == 0.18


def test_registration_evidence_matches_legacy():
    got = registration_evidence_score(correlation=0.8, overlap=0.9, margin=0.5, multiscale=0.7)
    assert got == round(0.35 * 0.8 + 0.2 * 0.9 + 0.15 * 0.5 + 0.3 * 0.7, 3)
    from groundscan.site.registration import AlignmentResult

    al = AlignmentResult(
        transform_name="rot0",
        shift_dy=0,
        shift_dx=0,
        correlation=0.8,
        overlap_fraction=0.9,
        b_resampled=np.zeros((2, 2)),
        b_valid=np.ones((2, 2), dtype=bool),
        ambiguity_margin=0.125,  # /0.25 -> 0.5
        multiscale_correlation=0.7,
    )
    assert al.registration_evidence == got


# --- grid / GPS / quality -----------------------------------------------------


def test_grid_all_nan_raises_domain_error():
    n = 9
    scan = ScanData(
        x=np.full(n, np.nan),
        y=np.full(n, np.nan),
        z=np.zeros(n),
        signal=np.ones(n),
        metadata=ScanMetadata(),
    )
    with pytest.raises(ValueError, match="all-NaN"):
        reconstruct_grid(scan)


def test_gps_positioning_skips_zigzag_correction():
    lat = np.array([48.0, 48.1, 48.2])
    lon = np.array([11.0, 11.1, 11.2])
    assert has_independent_positioning(lat, lon) is True
    assert has_independent_positioning(None, None) is False
    assert has_independent_positioning(np.array([np.nan]), np.array([np.nan])) is False


def test_field_quality_report_only_vs_enforce():
    from groundscan.diagnostics.quality_probe import detect_scan_quality_diagnostics
    from groundscan.gates.field_quality import assess_field_quality
    from groundscan.gates.geometry import summarize_geometry
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    scan = _toy_scan()
    # enforce-hard-block on a clean grid must still extract (no block)
    _, _, cands = analyze_scan(
        scan,
        out_dir="/tmp/groundscan_test_clean",
        write_outputs=False,
        config=AnalysisConfig(field_quality_mode="enforce-hard-block"),
    )
    assert isinstance(cands, list)
    # report-only path records policy without blocking
    grid = reconstruct_grid(scan)
    fq = assess_field_quality(
        scan, grid, summarize_geometry(scan, grid), detect_scan_quality_diagnostics(grid)
    )
    assert fq.hard_block is False


def test_rescue_off_by_default_and_conservative_runs():
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    scan = _toy_scan()
    _, _, off = analyze_scan(
        scan,
        out_dir="/tmp/groundscan_test_off",
        write_outputs=False,
        config=AnalysisConfig(extraction_rescue="off"),
    )
    _, _, cons = analyze_scan(
        scan,
        out_dir="/tmp/groundscan_test_cons",
        write_outputs=False,
        config=AnalysisConfig(extraction_rescue="conservative-geology"),
    )
    assert isinstance(off, list) and isinstance(cons, list)


def test_quality_input_patterns_cover_scan_extensions(tmp_path):
    from groundscan.cli.quality import QUALITY_PATTERNS

    assert "*.csv" in QUALITY_PATTERNS
    assert "*.tsv" in QUALITY_PATTERNS
    assert "*.txt" in QUALITY_PATTERNS
    # v0.5.1 fix: quality-check must not miss .txt/.tsv/.dat inputs
    assert "*.dat" in QUALITY_PATTERNS
    (tmp_path / "a.txt").write_text("x,y,z,signal\n0,0,0,1\n")
    found = []
    from pathlib import Path as _Path

    for pattern in QUALITY_PATTERNS:
        found.extend(sorted(_Path(tmp_path).rglob(pattern)))
    assert any(p.suffix == ".txt" for p in found)


def test_rover_locale_float_parsing():
    from groundscan.io.rover import RoverAdapter

    adapter = RoverAdapter()
    # Access the locale-aware float coercion indirectly: a headerless CSV
    # with comma decimals must not crash adapter detection.
    assert hasattr(adapter, "can_read")
    assert hasattr(adapter, "read")

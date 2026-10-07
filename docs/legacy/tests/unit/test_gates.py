"""Gate semantics in the refactored layout (fast)."""

import numpy as np

from groundscan import ScanData, ScanMetadata
from groundscan.core.grid import reconstruct_grid
from groundscan.diagnostics.quality_probe import detect_scan_quality_diagnostics
from groundscan.gates.field_quality import assess_field_quality
from groundscan.gates.geometry import summarize_geometry
from groundscan.gates.screening import DEFAULT_SCREENING_POLICY, screening_summary
from groundscan.gates.thresholds import threshold_policy


def test_threshold_policy_is_named_and_flagged():
    pol = threshold_policy()
    assert pol["field_quality"]["signal_valid_hard_block"] == 0.60
    assert pol["operational_gate"]["registration_block"] == 0.50


def test_screening_is_advisory_not_filter():
    from groundscan import Candidate

    c = Candidate(
        id=0,
        x_center=0,
        y_center=0,
        depth_mean=0,
        depth_std=0,
        n_points=5,
        area_cells=5,
        width=1,
        height=1,
        aspect_ratio=1,
        orientation_deg=0,
        peak_signal=5,
        mean_signal=4,
        anomaly_score=5,
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        confidence=0.5,
        evidence_score=0.2,
    )
    s = screening_summary([c], DEFAULT_SCREENING_POLICY)
    assert s["policy_version"] == DEFAULT_SCREENING_POLICY.version
    assert s["input_candidates"] == 1
    assert "semantics" in s


def test_field_quality_clean_grid_not_blocked():
    n = 12
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    rng = np.random.default_rng(1)
    scan = ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=rng.normal(10, 1, size=n * n),
        metadata=ScanMetadata(),
    )
    grid = reconstruct_grid(scan)
    diag = detect_scan_quality_diagnostics(grid)
    fq = assess_field_quality(scan, grid, summarize_geometry(scan, grid), diag)
    assert fq.hard_block is False

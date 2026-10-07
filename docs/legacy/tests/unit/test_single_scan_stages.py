"""Stage isolation for the single-scan orchestrator (fast, no I/O)."""

from __future__ import annotations

import numpy as np

from groundscan import Candidate, ScanData, ScanMetadata
from groundscan.core.anomaly import AnomalyMap
from groundscan.core.artifact import ArtifactMap
from groundscan.core.grid import Grid2D
from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan_stages import (
    apply_candidate_enrichment,
    build_enrichment,
    run_extraction_rescue,
    separate_single_scan_candidates,
    write_provenance_note,
)


def _cand(**overrides) -> Candidate:
    base = dict(
        id=1,
        x_center=2.0,
        y_center=2.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=6,
        area_cells=6,
        width=2.0,
        height=2.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=8.0,
        mean_signal=6.0,
        anomaly_score=8.0,
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        confidence=0.8,
    )
    base.update(overrides)
    return Candidate(**base)


def _scan(**meta) -> ScanData:
    n = 8
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=np.zeros(n * n),
        metadata=ScanMetadata(**meta),
    )


def test_build_enrichment_measured_default():
    assert build_enrichment(_scan()).metric_geometry_reliable is True
    assert build_enrichment(_scan()).geometry_reason.startswith("physical/metric")


def test_apply_enrichment_stamps_soil_and_risk():
    scan = _scan(mineralization_pct=50.0, humidity_pct=40.0)
    scan.metadata.extra["soil_context"] = {
        "factors": {"mineralization_pct": 50.0},
        "completeness": 0.2,
    }
    out = apply_candidate_enrichment([_cand()], scan, build_enrichment(scan))
    assert out[0].mineralization_pct == 50.0
    assert out[0].mineralization_risk == 0.5
    assert out[0].soil_context_completeness == 0.2
    assert out[0].metric_geometry_reliable is True


def test_separate_empty_is_noop():
    grid = Grid2D(
        x_centers=np.arange(4.0),
        y_centers=np.arange(4.0),
        signal=np.zeros((4, 4)),
        depth=np.ones((4, 4)),
        counts=np.ones((4, 4), dtype=int),
    )
    anomaly = AnomalyMap(
        zscore=np.zeros((4, 4)),
        labels=np.zeros((4, 4), dtype=int),
        n_components=0,
        threshold=3.0,
        residual=np.zeros((4, 4)),
        persistence=np.zeros((4, 4)),
    )
    artifacts = ArtifactMap(score=np.zeros((4, 4)))
    scan = _scan()
    out = separate_single_scan_candidates(
        [],
        config=AnalysisConfig(),
        anomaly=anomaly,
        artifacts=artifacts,
        grid=grid,
        separation_config=None,
        classification_config=None,
        enrichment=build_enrichment(scan),
        scan=scan,
    )
    assert out == []


def test_rescue_blocked_returns_diag():
    grid = Grid2D(
        x_centers=np.arange(4.0),
        y_centers=np.arange(4.0),
        signal=np.zeros((4, 4)),
        depth=np.ones((4, 4)),
        counts=np.ones((4, 4), dtype=int),
    )
    anomaly = AnomalyMap(
        zscore=np.zeros((4, 4)),
        labels=np.zeros((4, 4), dtype=int),
        n_components=0,
        threshold=3.0,
        residual=np.zeros((4, 4)),
        persistence=np.zeros((4, 4)),
    )
    cands = [_cand()]
    out, diag = run_extraction_rescue(
        cands,
        config=AnalysisConfig(),
        grid=grid,
        anomaly=anomaly,
        scan=_scan(),
        field_quality_blocked=True,
    )
    assert out is cands
    assert diag["accepted_count"] == 0
    assert diag["candidate_extraction_blocked"] is True


def test_provenance_note_only_for_non_measured(tmp_path):
    scan = _scan()
    write_provenance_note(tmp_path, "s", scan)
    assert list(tmp_path.iterdir()) == []

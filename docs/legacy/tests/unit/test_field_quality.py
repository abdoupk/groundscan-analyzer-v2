"""Field-quality gate: flag branches, tiers, and status mapping (fast)."""

from __future__ import annotations

import numpy as np

from groundscan import ScanData, ScanMetadata
from groundscan.core.grid import Grid2D
from groundscan.gates.field_quality import assess_field_quality
from groundscan.gates.geometry import GeometrySummary


def _grid(n=10, *, signal_value=10.0, valid_fraction=1.0, depth_value=1.0, seed=0):
    rng = np.random.default_rng(seed)
    signal = rng.normal(signal_value, 1.0, size=(n, n))
    depth = np.full((n, n), depth_value)
    counts = np.ones((n, n), dtype=int)
    if valid_fraction < 1.0:
        flat = rng.random(n * n)
        missing = flat > valid_fraction
        signal.ravel()[missing] = np.nan
        counts.ravel()[missing] = 0
    x = np.arange(n, dtype=float)
    return Grid2D(x_centers=x, y_centers=x.copy(), signal=signal, depth=depth, counts=counts)


def _scan(n=10) -> ScanData:
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    return ScanData(
        x=x.ravel(), y=y.ravel(), z=np.zeros(n * n), signal=np.ones(n * n), metadata=ScanMetadata()
    )


def _geometry(**overrides) -> GeometrySummary:
    base = dict(
        n_points=100,
        n_unique_lines=10,
        n_unique_impulses=10,
        points_per_line_min=10,
        points_per_line_max=10,
        points_per_line_median=10.0,
        is_clean_rectangle=True,
    )
    base.update(overrides)
    return GeometrySummary(**base)


def test_clean_scan_is_field_ready():
    fq = assess_field_quality(_scan(), _grid(), _geometry(), {})
    assert fq.hard_block is False
    assert fq.status == "field-ready"
    assert fq.field_ready is True
    assert "no-critical-quality-flags" in fq.flags
    d = fq.to_dict()
    assert d["status"] == "field-ready"


def test_mostly_nan_signal_hard_blocks():
    scan = _scan()
    grid = _grid(valid_fraction=0.2)
    fq = assess_field_quality(scan, grid, _geometry(), {})
    assert fq.hard_block is True
    assert fq.status == "insufficient-quality"
    assert "insufficient-valid-signal" in fq.flags


def test_degraded_signal_tiers():
    assert (
        "low-valid-signal"
        in assess_field_quality(_scan(), _grid(valid_fraction=0.8), _geometry(), {}).flags
    )
    assert (
        "missing-signal-cells"
        in assess_field_quality(_scan(), _grid(valid_fraction=0.97), _geometry(), {}).flags
    )


def test_sparse_coverage_hard_blocks():
    grid = _grid()
    grid.counts[:] = 0
    grid.counts[:3, :] = 1
    grid.signal[3:, :] = np.nan
    fq = assess_field_quality(_scan(), grid, _geometry(), {})
    assert fq.hard_block is True
    assert "severely-incomplete-grid" in fq.flags


def test_partial_coverage_is_caution():
    fq = assess_field_quality(_scan(), _grid(valid_fraction=0.9), _geometry(), {})
    assert fq.hard_block is False
    assert fq.status == "usable-with-caution"
    assert "incomplete-grid" in fq.flags


def test_tiny_grid_hard_blocks():
    fq = assess_field_quality(_scan(2), _grid(n=2), _geometry(), {})
    assert fq.hard_block is True
    assert "too-small-grid" in fq.flags


def test_irregular_geometry_flagged():
    fq = assess_field_quality(
        _scan(), _grid(), _geometry(n_unique_lines=9, is_clean_rectangle=False), {}
    )
    assert "irregular-grid-geometry" in fq.flags
    assert fq.status == "usable-with-caution"


def test_index_coordinates_not_metric():
    scan = _scan()
    scan.coords_are_index_only = True
    scan.coordinate_provenance = "index"
    fq = assess_field_quality(scan, _grid(), _geometry(), {})
    assert fq.metric_geometry_available is False
    assert "non-metric-geometry" in fq.flags


def test_headerless_source_ambiguity_disclosed():
    scan = _scan()
    scan.metadata.extra["headerless_xyz"] = True
    fq = assess_field_quality(scan, _grid(), _geometry(), {})
    assert "headerless-source-ambiguity" in fq.flags
    assert any(key == "fq_headerless_source" for key, _ in fq.reason_messages)


def test_missing_depth_channel_flagged():
    grid = _grid()
    grid.depth[:] = np.nan
    fq = assess_field_quality(_scan(), grid, _geometry(), {})
    assert "weak-depth-channel" in fq.flags
    assert fq.depth_valid_fraction == 0.0


def test_partial_depth_channel_flagged():
    grid = _grid()
    grid.depth.ravel()[::5] = np.nan  # 80% valid -> partial tier
    fq = assess_field_quality(_scan(), grid, _geometry(), {})
    assert "partial-depth-channel" in fq.flags
    assert fq.hard_block is False


def test_constant_signal_low_dynamic_range():
    grid = _grid()
    grid.signal[:] = 5.0  # truly constant: no dynamic information
    fq = assess_field_quality(_scan(), grid, _geometry(), {})
    assert "low-signal-dynamic-range" in fq.flags


def test_artifact_score_tiers():
    strong = assess_field_quality(_scan(), _grid(), _geometry(), {"instrument_artifact_score": 0.9})
    assert "strong-instrument-artifact-concern" in strong.flags
    assert strong.instrument_artifact_score == 0.9
    mild = assess_field_quality(_scan(), _grid(), _geometry(), {"instrument_artifact_score": 0.6})
    assert "instrument-artifact-concern" in mild.flags
    assert mild.hard_block is False

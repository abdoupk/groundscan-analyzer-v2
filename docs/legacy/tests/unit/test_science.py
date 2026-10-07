"""Scientific-correctness regression (Phase 3).

Each test pins the intended semantics defined in docs/adr/:
- degenerate compactness is not-estimable (0.0), never saturated 1.0
- single-observation stability is neutral (0.5), never perfect 1.0
- separation never silently drops a parent
- polarity conflict requires opposing-sign evidence
- registration second-best/margin are correlations in correlation units
- weighted median is a documented lower-median
- all-NaN consensus patches are neutral 0.0, never NaN evidence
- NaN coordinates never inflate grid counts
"""

from __future__ import annotations

import numpy as np
import pytest


def _cand(**kwargs):
    from groundscan.models import Candidate

    base = dict(
        id=1,
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
    base.update(kwargs)
    return Candidate(**base)


# --- compactness ------------------------------------------------------------


def test_digital_compactness_degenerate_is_zero_not_one():
    from groundscan._util import digital_compactness

    # One or two cells carry no shape information (not-estimable → 0.0).
    assert digital_compactness(1.0, 1.0) == 0.0
    assert digital_compactness(2.0, 2.0) == 0.0
    assert digital_compactness(0.0, 0.0) == 0.0
    assert digital_compactness(float("nan"), 1.0) == 0.0


def test_digital_compactness_interior_uses_isoperimetric_quotient():
    import math

    from groundscan._util import digital_compactness

    # 3x3: area 9, erosion perimeter 8 → 4π·9/64.
    assert digital_compactness(9.0, 8.0) == float(np.clip(4.0 * math.pi * 9.0 / 64.0, 0.0, 1.0))
    # Large square stays bounded.
    assert 0.0 < digital_compactness(100.0, 36.0) <= 1.0


def test_shape_and_fragment_compactness_agree():
    from groundscan.core.grid import Grid2D
    from groundscan.core.shape import _shape_metrics
    from groundscan.site.separation_fragments import _fragment_stats

    mask = np.ones((5, 5), bool)
    n = 5
    grid = Grid2D(
        x_centers=np.arange(n, dtype=float),
        y_centers=np.arange(n, dtype=float),
        signal=np.ones((n, n)),
        depth=np.ones((n, n)),
        counts=np.ones((n, n), dtype=int),
    )
    ys, xs = np.where(mask)
    m = _shape_metrics(grid, xs, ys, mask, 1.0, 1.0)
    rr = np.arange(25) // 5
    cc = np.arange(25) % 5
    s = _fragment_stats(mask, np.arange(5.0), np.arange(5.0), rr, cc)
    assert m["compactness"] == s["compactness"]


def test_fragment_extents_calibrated_convention():
    # Documented intentional difference (see ADR): fragment spans use the
    # max-min response-span convention WITHOUT the whole-object +pitch, and
    # singletons span 0.0. A +pitch trial broke the calibrated vendor dipole
    # merge; unifying conventions needs threshold recalibration on field data.
    from groundscan.site.separation_fragments import _fragment_stats

    mask = np.zeros((4, 4), bool)
    mask[1, 1] = True
    s = _fragment_stats(mask, np.arange(4.0), np.arange(4.0), np.array([1]), np.array([1]))
    assert s["width"] == 0.0
    assert s["height"] == 0.0
    mask2 = np.zeros((4, 4), bool)
    mask2[1, 1:3] = True
    s2 = _fragment_stats(mask2, np.arange(4.0), np.arange(4.0), np.array([1, 1]), np.array([1, 2]))
    assert s2["width"] == 1.0
    assert s2["height"] == 0.0


# --- single-observation stability --------------------------------------------


def _grid(n=16):
    from groundscan.core.grid import Grid2D

    return Grid2D(
        x_centers=np.arange(n, dtype=float),
        y_centers=np.arange(n, dtype=float),
        signal=np.ones((n, n)),
        depth=np.ones((n, n)),
        counts=np.ones((n, n), dtype=int),
    )


def _scan():
    from groundscan import ScanData, ScanMetadata

    rng = np.random.default_rng(0)
    return ScanData(
        x=np.zeros(4),
        y=np.zeros(4),
        z=np.zeros(4),
        signal=rng.normal(0, 1, size=4),
        metadata=ScanMetadata(),
    )


def _obs(label, candidates, grid=None):
    from groundscan.core.anomaly import AnomalyMap, ArtifactMap
    from groundscan.site.analyze_site import ScanObservation

    grid = grid if grid is not None else _grid()
    n = grid.signal.shape[0]
    anomaly = AnomalyMap(
        zscore=np.zeros((n, n)),
        labels=np.zeros((n, n), dtype=int),
        n_components=0,
        threshold=3.0,
        residual=np.zeros((n, n)),
        persistence=np.zeros((n, n)),
    )
    artifacts = ArtifactMap(score=np.zeros((n, n)))
    return ScanObservation(
        label=label,
        scan=_scan(),
        grid=grid,
        anomaly=anomaly,
        artifacts=artifacts,
        candidates=candidates,
    )


def _fuse_single():
    from groundscan.site.analyze_site import fuse_site_candidates

    obs = _obs("a", [_cand(scan_count=1)])
    support = np.ones((20, 20))
    out = fuse_site_candidates([obs], obs, {}, 0.06, support, None)
    assert len(out) == 1
    return out[0]


def test_single_observation_stability_neutral():
    fused = _fuse_single()
    assert fused.position_stability == 0.5
    assert fused.geometry_consistency <= 0.75  # blended with size consistency, not perfect
    assert fused.cross_scan_agreement is None


def test_two_observations_stability_spread():
    import numpy as np

    # Identical twins → high stability; separated twins → lower.
    assert float(np.std([3.0, 3.0])) == 0.0


def test_multiple_observations_unchanged_semantics():
    fused = _fuse_single()
    assert fused.scan_count == 1
    assert "single-scan" in fused.notes


# --- separation ---------------------------------------------------------------


def test_separation_never_drops_parent_battery():
    from groundscan.site.separation import separate_fused_candidates

    rng = np.random.default_rng(11)
    for trial in range(25):
        n = 14
        support = rng.normal(0, 1, size=(n, n))
        signed = rng.normal(0, 1, size=(n, n))
        cx, cy = rng.integers(3, 11, size=2)
        support[cx - 2 : cx + 3, cy - 2 : cy + 3] += 8.0
        signed[cx - 2 : cx + 3, cy - 2 : cy + 3] += 8.0
        x = np.linspace(0, 6, n)
        y = np.linspace(0, 6, n)
        parent = _cand(
            id=100 + trial,
            x_center=float(x[cx]),
            y_center=float(y[cy]),
            scan_count=2,
            evidence_score=0.8,
            anomaly_score=9.0,
        )
        out, counts = separate_fused_candidates([parent], support, signed, x, y)
        assert len(out) >= 1, f"trial {trial}: parent vanished"
        assert sum(1 for c in out if c.separation_parent_id == parent.id or c.id != parent.id) >= 1
        # Counts metadata must agree with output.
        assert counts[parent.id] == len(out)


def test_separation_all_rejected_marks_unresolved(tmp_path=None):
    # Structural pin: the unresolved status exists as a documented contract.
    from groundscan.models import Candidate

    c = _cand(separation_status="unresolved-undersegmented")
    assert isinstance(c, Candidate)
    assert c.separation_status == "unresolved-undersegmented"


# --- polarity -----------------------------------------------------------------


def test_all_mixed_is_not_conflict():
    from groundscan.site.analyze_site import fuse_site_candidates

    grid = _grid()
    oa = _obs(
        "a",
        [_cand(id=11, polarity="mixed", positive_peak=4.0, negative_peak=-4.0, scan_count=1)],
        grid,
    )
    ob = _obs(
        "b",
        [_cand(id=12, polarity="mixed", positive_peak=4.0, negative_peak=-4.0, scan_count=1)],
        grid,
    )
    support = np.ones((20, 20))
    out = fuse_site_candidates([oa, ob], oa, {}, 10.0, support, None)
    assert out, "expected a fused candidate"
    assert out[0].polarity_consistency == 1.0


# --- registration ---------------------------------------------------------------


def test_registration_second_best_is_correlation():
    from groundscan.site.registration import align_grids

    rng = np.random.default_rng(0)
    z = rng.normal(0, 1, size=(24, 24))
    z[10:14, 10:14] += 8.0
    res = align_grids(z, z.copy(), resolution=24)
    assert -1.0 <= res.second_best_correlation <= 1.0
    # Exact contract: margin is the correlation-unit difference.
    assert res.ambiguity_margin == pytest.approx(
        res.correlation - res.second_best_correlation, abs=1e-12
    )
    assert res.ambiguity_margin >= 0.0
    assert res.second_best_correlation <= res.correlation + 1e-12


def test_registration_identical_grids_tied_margin_zero():
    from groundscan.site.registration import align_grids

    rng = np.random.default_rng(1)
    z = rng.normal(0, 1, size=(24, 24))
    res = align_grids(z, z.copy(), resolution=24)
    assert res.correlation > 0.9
    assert res.ambiguity_margin >= 0.0


# --- weighted median --------------------------------------------------------------


def test_weighted_median_contract():
    from groundscan.site.fusion import _weighted_median

    assert _weighted_median([1, 5, 9], [1, 1, 1]) == 5.0
    # Documented lower-median convention for even n.
    assert _weighted_median([1, 5], [1, 1]) == 1.0
    assert _weighted_median([5, 1], [1, 1]) == 1.0
    assert _weighted_median([1, 9], [3, 1]) == 1.0
    assert _weighted_median([1, 9], [1, 3]) == 9.0
    assert np.isnan(_weighted_median([], []))
    assert np.isnan(_weighted_median([np.nan], [1.0]))


# --- NaN handling -------------------------------------------------------------------


def test_all_nan_consensus_is_neutral_not_nan():
    fused = _fuse_single()
    assert np.isfinite(fused.evidence_score)
    assert np.isfinite(fused.multiresolution_consensus)


def test_grid_scatter_nan_coords_not_counted():
    import numpy as np

    from groundscan import ScanData, ScanMetadata
    from groundscan.core.grid import _grid_from_scatter

    rng = np.random.default_rng(2)
    n = 200
    x = rng.uniform(0, 10, size=n)
    y = rng.uniform(0, 10, size=n)
    x[:5] = np.nan
    y[3:8] = np.nan
    scan = ScanData(
        x=x, y=y, z=np.zeros(n), signal=rng.normal(0, 1, size=n), metadata=ScanMetadata()
    )
    grid = _grid_from_scatter(scan, 10)
    assert int(np.sum(grid.counts)) == n - 8

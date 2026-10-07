"""Mathematical/analytical contracts for the science validation framework (P0, fast).

Each test pins an exact identity or an explicitly justified tolerance that the
production engine already guarantees. Nothing here asserts field truth,
detection accuracy, or threshold optimality. For the permanent validation
model see docs/SCIENTIFIC_VALIDATION_CONTRACT.md.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# --- registration transform algebra (exact) ---------------------------------


def _transform_names():
    from groundscan.site.registration import _TRANSFORMS

    return _TRANSFORMS


def test_all_eight_transforms_agree_with_point_mapping():
    """Array op and _apply_transform_to_point move every cell identically."""
    from groundscan.site.registration import _apply_transform_to_point

    size = 7
    for name, fn in _transform_names():
        marker = np.arange(size * size).reshape(size, size)
        moved = fn(marker)
        for row in range(size):
            for col in range(size):
                r2, c2 = _apply_transform_to_point(name, float(row), float(col), size)
                assert moved[int(r2), int(c2)] == marker[row, col]


def test_transform_composition_identities():
    from groundscan.site.registration import _apply_transform_to_point as mp

    size = 7
    point = (2.0, 5.0)
    cycled = point
    for _ in range(4):
        cycled = mp("rot90", *cycled, size)
    assert cycled == point
    assert mp("rot180", *mp("rot180", *point, size), size) == point
    assert mp("flip_rot0", *mp("flip_rot0", *point, size), size) == point


def test_transform_point_mapping_degenerate_size_one():
    from groundscan.site.registration import _apply_transform_to_point

    for name, _ in _transform_names():
        assert _apply_transform_to_point(name, 0.0, 0.0, 1) == (0.0, 0.0)


def test_alignment_status_boundaries():
    from groundscan.site.registration import AlignmentResult

    def status(*, correlation, overlap, margin=0.0, multiscale=0.0):
        return AlignmentResult(
            transform_name="rot0",
            shift_dy=0,
            shift_dx=0,
            correlation=correlation,
            overlap_fraction=overlap,
            b_resampled=np.zeros((4, 4)),
            b_valid=np.ones((4, 4), dtype=bool),
            ambiguity_margin=margin,
            multiscale_correlation=multiscale,
        ).status

    # Status reads registration_evidence (weighted score), not raw correlation.
    assert status(correlation=0.1, overlap=0.9) == "weak"
    assert status(correlation=1.0, overlap=1.0, margin=1.0, multiscale=1.0) == "strong"
    assert status(correlation=1.0, overlap=0.6, margin=1.0, multiscale=1.0) == "caution"
    assert status(correlation=0.9, overlap=0.1) == "weak"


# --- _util edge-case matrix --------------------------------------------------


def test_finite_helpers_edge_matrix():
    from groundscan._util import finite_values, is_finite_number

    assert finite_values([]).size == 0
    assert finite_values([float("nan"), float("inf")]).size == 0
    np.testing.assert_allclose(finite_values([1.0, float("nan"), 2.5]), [1.0, 2.5])
    assert finite_values("not-numbers").size == 0
    assert is_finite_number(1.0) is True
    assert is_finite_number(float("nan")) is False
    assert is_finite_number(float("-inf")) is False
    assert is_finite_number(None) is False


def test_robust_scale_degenerate_inputs():
    from groundscan._util import robust_scale

    assert robust_scale(np.array([3.0])) == 1.0
    assert robust_scale(np.array([5.0, 5.0, 5.0, 5.0])) == 1.0
    assert robust_scale(np.array([float("nan"), float("nan")])) == 1.0
    scale = robust_scale(np.array([1.0, 2.0, 3.0, 4.0]))
    assert math.isfinite(scale) and scale > 0.0


def test_axis_spacing_and_safe_mean_degenerates():
    from groundscan._util import axis_spacing, safe_mean

    assert axis_spacing(np.array([7.0])) == 1.0
    assert axis_spacing(np.array([0.0, 1.0, 2.0, 3.0])) == 1.0
    assert safe_mean([], default=0.25) == 0.25
    assert safe_mean([float("nan")], default=0.0) == 0.0


def test_digital_compactness_invalid_inputs_are_not_compact():
    from groundscan._util import digital_compactness

    assert digital_compactness("x", 4.0) == 0.0
    assert digital_compactness(9.0, "x") == 0.0
    assert digital_compactness(-9.0, 8.0) == 0.0
    assert digital_compactness(9.0, -8.0) == 0.0
    # NOTE: infinite area is outside the documented input domain (cell counts
    # from digital masks); only NaN/non-numeric/non-positive are contracted
    # to 0.0 (see also tests/unit/test_science.py NaN pins).
    assert digital_compactness(9.0, float("inf")) == 0.0
    assert 0.0 <= digital_compactness(64.0, 28.0) <= 1.0


# --- score bound and finiteness sweeps ---------------------------------------


def test_fused_evidence_score_bounds_and_clip():
    from groundscan.gates.thresholds import fused_evidence_score

    keys = [
        "base",
        "detection_rate",
        "direction_cov",
        "spacing_cov",
        "traversal_cov",
        "position_stability",
        "pol_cons",
        "signal_cons",
        "depth_cons",
        "reg_cons",
        "cons",
    ]
    assert fused_evidence_score(**dict.fromkeys(keys, 0.0)) == 0.0
    assert fused_evidence_score(**dict.fromkeys(keys, 1.0)) == 1.0
    assert fused_evidence_score(**dict.fromkeys(keys, 5.0)) == 1.0
    assert fused_evidence_score(**dict.fromkeys(keys, -5.0)) == 0.0


def test_registration_evidence_score_clamps_inputs():
    from groundscan.gates.thresholds import registration_evidence_score

    assert registration_evidence_score(
        correlation=2.0, overlap=-1.0, margin=0.5, multiscale=0.5
    ) == registration_evidence_score(correlation=1.0, overlap=0.0, margin=0.5, multiscale=0.5)
    value = registration_evidence_score(correlation=0.8, overlap=0.9, margin=0.4, multiscale=0.7)
    assert 0.0 <= value <= 1.0


def test_screening_policy_rejects_invalid_thresholds():
    from groundscan.gates.screening import ScreeningPolicy

    with pytest.raises(ValueError):
        ScreeningPolicy(primary_threshold=1.5)
    with pytest.raises(ValueError):
        ScreeningPolicy(rescue_lower=0.8, rescue_upper=0.6)


def test_screen_candidates_retention_semantics():
    from groundscan.gates.screening import DEFAULT_SCREENING_POLICY, screen_candidates
    from groundscan.models import Candidate

    def cand(score, **over):
        base = dict(
            id=1,
            x_center=0.0,
            y_center=0.0,
            depth_mean=1.0,
            depth_std=0.1,
            n_points=10,
            area_cells=10,
            width=2.0,
            height=2.0,
            aspect_ratio=1.0,
            orientation_deg=0.0,
            peak_signal=9.0,
            mean_signal=7.0,
            anomaly_score=6.0,
            shape_class="compact",
            pattern_hypothesis="metallic-like",
            confidence=0.8,
            screening_score=score,
            multiscale_persistence=0.9,
            boundary_contact_ratio=0.1,
            artifact_score=0.1,
        )
        base.update(over)
        return Candidate(**base)

    kept = screen_candidates([cand(0.9), cand(0.1), cand(0.67)], DEFAULT_SCREENING_POLICY)
    reasons = {c.screening_selection_reason for c in kept}
    assert reasons == {"primary-threshold", "soft-rescue"}
    assert all(c.screening_policy_version == "rescue-screening" for c in kept)


# --- coordinate provenance x geometry matrix ---------------------------------


def test_coordinate_provenance_predicates():
    from groundscan.models import (
        ScanData,
        is_derived_coordinates,
        is_index_only_coordinates,
        is_metric_coordinates,
    )

    def scan(prov, index_only=False):
        n = 4
        return ScanData(
            x=np.arange(n, dtype=float),
            y=np.arange(n, dtype=float),
            z=np.ones(n),
            signal=np.ones(n),
            coordinate_provenance=prov,
            coords_are_index_only=index_only,
        )

    assert is_metric_coordinates(scan("measured"))
    assert is_derived_coordinates(scan("derived"))
    assert is_index_only_coordinates(scan("index"))
    # Legacy boolean wins over the stored state.
    assert is_index_only_coordinates(scan("measured", index_only=True))
    with pytest.raises(ValueError):
        scan("unverified")


def test_synthetic_scan_forms_clean_rectangle_grid():
    from groundscan.core.grid import reconstruct_grid
    from groundscan.gates.geometry import summarize_geometry
    from groundscan.validation.synthetic_core.core import generate_scan, scenario_catalog

    scan, _ = generate_scan(scenario_catalog()[0])
    grid = reconstruct_grid(scan)
    assert grid.signal.shape == (21, 31)
    assert bool((grid.counts == 1).all())
    summary = summarize_geometry(scan, grid)
    assert summary.is_clean_rectangle is True
    assert summary.grid_matches_raw_rectangle is True
    assert (summary.grid_nx, summary.grid_ny) == (31, 21)


def test_cluster_axis_coordinates_exact_and_jittered():
    from groundscan.core.grid import cluster_axis_coordinates

    centers, labels = cluster_axis_coordinates(np.array([0.0, 1.0, 2.0, 3.0]))
    assert centers.tolist() == [0.0, 1.0, 2.0, 3.0]
    assert labels.tolist() == [0, 1, 2, 3]
    jittered = np.array([1e-7, -1e-7, 1.0, 1.0 + 1e-7, 2.0])
    centers_j, _ = cluster_axis_coordinates(jittered)
    assert len(centers_j) == 3
    empty_c, empty_l = cluster_axis_coordinates(np.empty(0))
    assert empty_c.size == 0 and empty_l.size == 0


def test_scatter_grid_rejects_all_nan_coordinates():
    from groundscan.core.grid import _grid_from_scatter
    from groundscan.models import ScanData

    n = 6
    bad = ScanData(
        x=np.full(n, float("nan")),
        y=np.full(n, float("nan")),
        z=np.ones(n),
        signal=np.ones(n),
    )
    with pytest.raises(ValueError):
        _grid_from_scatter(bad, 8)


# --- zigzag correction contract ----------------------------------------------


def _smooth_grid(ny=12, nx=20, seed=0):
    from groundscan.core.grid import Grid2D

    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:ny, 0:nx].astype(float)
    signal = 3.0 * xx + 2.0 * yy + rng.normal(0.0, 0.05, (ny, nx))
    return Grid2D(
        x_centers=np.arange(nx, dtype=float),
        y_centers=np.arange(ny, dtype=float),
        signal=signal,
        depth=np.ones_like(signal),
        counts=np.ones_like(signal, dtype=int),
    )


def test_zigzag_diagnosis_detects_constructed_zigzag():
    from groundscan.core.zigzag import diagnose_zigzag

    smooth = _smooth_grid()
    assert diagnose_zigzag(smooth).recommend_correction is False
    zigzagged = _smooth_grid()
    zigzagged.signal[1::2] = zigzagged.signal[1::2, ::-1]
    diagnosis = diagnose_zigzag(zigzagged)
    assert diagnosis.recommend_correction is True
    assert diagnosis.margin == diagnosis.continuity_if_flipped - diagnosis.continuity_as_is


def test_correct_zigzag_is_involution_and_restores():
    from groundscan.core.zigzag import correct_zigzag

    smooth = _smooth_grid()
    zigzagged = _smooth_grid()
    zigzagged.signal[1::2] = zigzagged.signal[1::2, ::-1]
    restored = correct_zigzag(zigzagged)
    np.testing.assert_allclose(restored.signal, smooth.signal)
    twice = correct_zigzag(restored)
    np.testing.assert_allclose(twice.signal, zigzagged.signal)
    # Input grids are never mutated; geometry channels travel with signal.
    assert restored.signal.shape == smooth.signal.shape


def test_independent_positioning_predicate():
    from groundscan.core.zigzag import has_independent_positioning

    assert has_independent_positioning(np.zeros(5), np.zeros(5)) is False
    assert has_independent_positioning(np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])) is True
    assert has_independent_positioning(np.array([1.0]), np.array([2.0])) is False
    assert has_independent_positioning(None, None) is False

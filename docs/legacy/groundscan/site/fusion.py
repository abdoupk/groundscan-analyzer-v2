"""Robust multi-scan depth and geometry fusion helpers.

All outputs are descriptive/heuristic measurements. They do not constitute a
physical inversion or a calibrated probability of an underground object.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..models import Candidate


@dataclass(frozen=True)
class DepthFusion:
    estimate: float
    std: float
    minimum: float
    maximum: float
    value_range: float
    iqr: float
    relative_dispersion: float
    consistency: float
    quality: float
    measurement_count: int


@dataclass(frozen=True)
class GeometryFusion:
    width: float
    height: float
    major_extent: float
    minor_extent: float
    aspect_ratio: float
    elongation_ratio: float
    orientation_deg: float
    orientation_dispersion_deg: float
    orientation_consistency: float
    compactness: float
    solidity: float
    linearity_score: float
    boundary_contact_ratio: float
    broadness_score: float
    geometry_size_consistency: float
    geometry_fusion_quality: float
    measurement_count: int


def finite_values(values: Iterable[float]) -> np.ndarray[Any, Any]:
    """Backward-compat alias — canonical impl is groundscan._util.finite_values."""
    from .._util import finite_values

    return finite_values(values)


def _weighted_finite(
    values: Sequence[float], weights: Sequence[float]
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    return v[mask], w[mask]


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    """Lower weighted median (documented convention, see ADR on fusion statistics).

    Non-finite values and non-positive weights are excluded; empty input
    returns NaN. With ``side="left"`` the cutoff selects the lower middle
    for even totals (``[1, 5] → 1.0``) — the conservative direction for the
    dominant two-scan fusion path (avoids overstating fused depth/size).
    Odd totals return the middle value (``[1, 5, 9] → 5.0``).
    """
    v, w = _weighted_finite(values, weights)
    if not len(v):
        return float("nan")
    order = np.argsort(v)
    v, w = v[order], w[order]
    cutoff = 0.5 * float(np.sum(w))
    idx = int(np.searchsorted(np.cumsum(w), cutoff, side="left"))
    return float(v[min(idx, len(v) - 1)])


def _weighted_mean(
    values: Sequence[float], weights: Sequence[float], default: float = float("nan")
) -> float:
    v, w = _weighted_finite(values, weights)
    if not len(v):
        return default
    return float(np.sum(v * w) / np.sum(w))


def _weighted_quantile(values: Sequence[float], weights: Sequence[float], q: float) -> float:
    v, w = _weighted_finite(values, weights)
    if not len(v):
        return float("nan")
    order = np.argsort(v)
    v, w = v[order], w[order]
    cumulative = np.cumsum(w)
    target = float(np.clip(q, 0.0, 1.0)) * float(cumulative[-1])
    idx = int(np.searchsorted(cumulative, target, side="left"))
    return float(v[min(idx, len(v) - 1)])


def _robust_dispersion(
    values: Sequence[float] | np.ndarray[Any, Any],
    floor: float = 1e-9,
) -> float:
    v = finite_values(values)
    if len(v) < 2:
        return 0.0
    center = float(np.median(v))
    mad = float(np.median(np.abs(v - center)))
    scale = 1.4826 * mad
    if scale <= floor:
        scale = float(np.std(v))
    return float(max(scale, 0.0))


def _robust_relative_dispersion(values: Sequence[float], floor: float = 1e-9) -> float:
    v = finite_values(values)
    if len(v) < 2:
        # Fewer than two observations means consistency is not estimable, which
        # is not the same as "identical". Returning 0.0 made the caller's
        # `size_consistency = clip(1.0 - relative_dispersion)` report a
        # *perfect* 1.0 for a cluster built from one observation. Match the
        # neutral already used for the same situation in analyze_site:
        # "repeatability is not estimable -> neutral 0.5 (unknown, never
        # perfect)", so a single-member fusion reports 0.5.
        return 0.5
    center = float(np.median(v))
    return float(np.clip(_robust_dispersion(v, floor=floor) / max(abs(center), floor), 0.0, 1.0))


def _effective_depth_weight(candidate: Candidate) -> float:
    """Weight depth by usable coverage, internal stability and candidate evidence."""
    valid = float(np.clip(getattr(candidate, "depth_valid_fraction", 0.0), 0.0, 1.0))
    stable = float(np.clip(getattr(candidate, "depth_stability_score", 0.0), 0.0, 1.0))
    evidence = float(np.clip(getattr(candidate, "evidence_score", 0.0), 0.0, 1.0))
    geom = float(np.clip(getattr(candidate, "geometry_quality", 0.5), 0.0, 1.0))
    # Do not zero-out usable measurements solely because a legacy component has
    # an absent stability score; preserve a small floor from evidence/coverage.
    return max(1e-3, 0.35 * valid + 0.30 * stable + 0.20 * evidence + 0.15 * geom)


def fuse_depth(members: Sequence[Candidate]) -> DepthFusion:
    estimates: list[float] = []
    weights: list[float] = []
    within: list[float] = []
    minima: list[float] = []
    maxima: list[float] = []
    for c in members:
        estimate = getattr(c, "depth_estimate", float("nan"))
        if not np.isfinite(estimate):
            estimate = getattr(c, "depth_mean", float("nan"))
        if not np.isfinite(estimate):
            continue
        w = _effective_depth_weight(c)
        estimates.append(float(estimate))
        weights.append(w)
        std = getattr(c, "depth_estimate_std", float("nan"))
        if np.isfinite(std):
            within.append(float(std))
        lo = getattr(c, "depth_min", float("nan"))
        hi = getattr(c, "depth_max", float("nan"))
        if np.isfinite(lo):
            minima.append(float(lo))
        if np.isfinite(hi):
            maxima.append(float(hi))

    count = len(estimates)
    if not count:
        return DepthFusion(
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            1.0,
            0.0,
            0.0,
            0,
        )

    estimate = _weighted_median(estimates, weights)
    q25 = _weighted_quantile(estimates, weights, 0.25)
    q75 = _weighted_quantile(estimates, weights, 0.75)
    iqr = max(0.0, q75 - q25)
    between = _robust_dispersion(estimates)
    within_rms = float(np.sqrt(np.mean(np.square(within)))) if within else 0.0
    std = float(np.sqrt(between * between + within_rms * within_rms))
    # The reported range prefers per-scan envelopes but always contains the fused estimate.
    minimum = min(minima) if minima else min(estimates)
    maximum = max(maxima) if maxima else max(estimates)
    minimum = min(minimum, estimate)
    maximum = max(maximum, estimate)
    value_range = max(0.0, maximum - minimum)
    # Stage 2 (S08 / contract K11): a single observation makes the *between-scan*
    # spread not estimable, and "not estimable" is not "perfect".
    # ``_robust_dispersion`` returns 0.0 for n < 2, so the old relative spread
    # collapsed to 0.0 and consistency came out a perfect 1.0 for a depth
    # "confirmed" by exactly one scan -- the same defect ADR-002 fixed for
    # position_stability. Route through the same neutral convention
    # ``_robust_relative_dispersion`` already uses, so the derived fields
    # (relative_dispersion, consistency, quality, and the caller's
    # fused_depth_quality) all move together instead of one of them claiming
    # perfect agreement.
    relative = 0.5 if count < 2 else float(np.clip(std / max(abs(estimate), 1e-6), 0.0, 1.0))
    consistency = float(np.clip(1.0 - relative, 0.0, 1.0))
    coverage_mean = (
        float(np.mean([getattr(c, "depth_valid_fraction", 0.0) for c in members]))
        if members
        else 0.0
    )
    quality = float(
        np.clip(0.45 * consistency + 0.35 * min(1.0, count / 3.0) + 0.20 * coverage_mean, 0.0, 1.0)
    )
    return DepthFusion(
        estimate=estimate,
        std=std,
        minimum=minimum,
        maximum=maximum,
        value_range=value_range,
        iqr=iqr,
        relative_dispersion=relative,
        consistency=consistency,
        quality=quality,
        measurement_count=count,
    )


def _double_angle_mean(
    angles_deg: Sequence[float], weights: Sequence[float]
) -> tuple[float, float]:
    """Axial mean of [0, 180) orientations plus its resultant (consistency).

    Stage 2 (S07 / contract K10): the mean now delegates to the canonical
    :func:`groundscan._util.axial_mean_deg` so there is exactly one axial
    implementation in the codebase. The *resultant* is kept here because it is
    the dispersion measure fused as ``orientation_consistency``, and an
    orientation and its consistency must be computed from the same statistics.

    An orientation population with no resultant (isotropic) has no mean
    direction; that now yields ``nan`` rather than an arbitrary angle, which the
    caller already handles (``finite_angles`` check before the fusion quality
    blend).
    """
    values, w = _weighted_finite(angles_deg, weights)
    if not len(values):
        return float("nan"), 0.0
    from .._util import axial_mean_deg

    angle = axial_mean_deg(values, w)
    theta = np.radians(2.0 * values)
    resultant = float(
        np.hypot(np.sum(np.cos(theta) * w), np.sum(np.sin(theta) * w)) / max(np.sum(w), 1e-12)
    )
    if not np.isfinite(angle):
        return float("nan"), float(np.clip(resultant, 0.0, 1.0))
    return angle, float(np.clip(resultant, 0.0, 1.0))


def _angle_distance_deg(a: float, b: float) -> float:
    from .._util import axial_angle_distance_deg

    return axial_angle_distance_deg(a, b)


def fuse_geometry(members: Sequence[Candidate]) -> GeometryFusion:
    if not members:
        return GeometryFusion(
            width=float("nan"),
            height=float("nan"),
            major_extent=float("nan"),
            minor_extent=float("nan"),
            aspect_ratio=float("nan"),
            elongation_ratio=float("nan"),
            orientation_deg=float("nan"),
            orientation_dispersion_deg=float("nan"),
            orientation_consistency=0.0,
            compactness=0.0,
            solidity=0.0,
            linearity_score=0.0,
            boundary_contact_ratio=0.0,
            broadness_score=0.0,
            geometry_size_consistency=0.0,
            geometry_fusion_quality=0.0,
            measurement_count=0,
        )
    weights = [
        max(
            1e-3,
            0.55 * float(np.clip(getattr(c, "geometry_quality", 0.5), 0, 1))
            + 0.45 * float(np.clip(getattr(c, "evidence_score", 0.0), 0, 1)),
        )
        for c in members
    ]
    width = _weighted_median([c.width for c in members], weights)
    height = _weighted_median([c.height for c in members], weights)
    major = _weighted_median([c.major_extent for c in members], weights)
    minor = _weighted_median([c.minor_extent for c in members], weights)
    aspect = (
        major / max(minor, 1e-9)
        if np.isfinite(major) and np.isfinite(minor)
        else _weighted_median([c.aspect_ratio for c in members], weights)
    )
    elongation = _weighted_median([c.elongation_ratio for c in members], weights)

    angle_values = [c.orientation_deg for c in members]
    finite_angles = [float(v) for v in angle_values if np.isfinite(v)]
    angle_weights = [weights[i] for i, v in enumerate(angle_values) if np.isfinite(v)]
    orientation, orientation_consistency = _double_angle_mean(finite_angles, angle_weights)
    if np.isfinite(orientation) and finite_angles:
        dispersion = float(
            np.sqrt(
                np.average(
                    [_angle_distance_deg(a, orientation) ** 2 for a in finite_angles],
                    weights=angle_weights,
                )
            )
        )
    else:
        dispersion = float("nan")

    compactness = _weighted_mean([c.compactness for c in members], weights, 0.0)
    solidity = _weighted_mean([c.solidity for c in members], weights, 0.0)
    linearity = _weighted_mean([c.linearity_score for c in members], weights, 0.0)
    boundary = _weighted_mean([c.boundary_contact_ratio for c in members], weights, 0.0)
    broadness = _weighted_mean([c.broadness_score for c in members], weights, 0.0)
    size_values = [
        max(float(c.major_extent), float(c.minor_extent), 1e-9)
        for c in members
        if np.isfinite(c.major_extent) and np.isfinite(c.minor_extent)
    ]
    size_relative = _robust_relative_dispersion(size_values)
    size_consistency = float(np.clip(1.0 - size_relative, 0.0, 1.0))
    mean_geo_quality = _weighted_mean([c.geometry_quality for c in members], weights, 0.0)
    fusion_quality = float(
        np.clip(
            0.45 * mean_geo_quality + 0.30 * size_consistency + 0.25 * orientation_consistency
            if finite_angles
            else 0.55 * mean_geo_quality + 0.45 * size_consistency,
            0.0,
            1.0,
        )
    )
    return GeometryFusion(
        width=width,
        height=height,
        major_extent=major,
        minor_extent=minor,
        aspect_ratio=aspect,
        elongation_ratio=elongation,
        orientation_deg=orientation,
        orientation_dispersion_deg=dispersion,
        orientation_consistency=orientation_consistency,
        compactness=compactness,
        solidity=solidity,
        linearity_score=linearity,
        boundary_contact_ratio=boundary,
        broadness_score=broadness,
        geometry_size_consistency=size_consistency,
        geometry_fusion_quality=fusion_quality,
        measurement_count=len(members),
    )

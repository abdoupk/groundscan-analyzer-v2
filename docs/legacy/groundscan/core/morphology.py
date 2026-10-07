"""Second-generation morphology descriptors for anomaly components.

These metrics describe geometric consistency of a component. They are
measurement aids, not material/object probabilities, and do not alter the
baseline anomaly detector by themselves.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .._util import finite_values


def _robust_cv(values: list[float] | np.ndarray[Any, Any]) -> float:
    arr = finite_values(np.asarray(values, dtype=float))
    arr = arr[arr > 1e-9]
    if arr.size < 2:
        return float("nan")
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return float((1.4826 * mad) / max(abs(med), 1e-9))


def _consistency_from_cv(cv: float, scale: float = 0.35) -> float:
    if not np.isfinite(cv):
        return 0.0
    return float(np.clip(math.exp(-max(cv, 0.0) / max(scale, 1e-9)), 0.0, 1.0))


def _angle_distance_deg(a: float, b: float) -> float:
    if not (np.isfinite(a) and np.isfinite(b)):
        return float("nan")
    d = abs(float(a) - float(b)) % 180.0
    return min(d, 180.0 - d)


def _principal_axis(
    x: np.ndarray[Any, Any], y: np.ndarray[Any, Any]
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], float]:
    points = np.column_stack([x, y]).astype(float)
    center = np.mean(points, axis=0)
    if len(points) < 4:
        return center, np.array([1.0, 0.0]), 0.0
    centered = points - center
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    axis = eigvecs[:, int(np.argmax(eigvals))]
    axis = axis / max(float(np.linalg.norm(axis)), 1e-12)
    angle = float(np.degrees(np.arctan2(axis[1], axis[0])) % 180.0)
    return center, axis, angle


def morphology_metrics(
    x_coords: np.ndarray[Any, Any],
    y_coords: np.ndarray[Any, Any],
    z_vals: np.ndarray[Any, Any],
    *,
    major_extent: float,
    minor_extent: float,
    linearity_score: float,
    line_support_score: float = 0.0,
) -> dict[str, float]:
    """Return width/orientation stability and a conservative line-coherence score."""
    x = np.asarray(x_coords, dtype=float)
    y = np.asarray(y_coords, dtype=float)
    z = np.asarray(z_vals, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[finite], y[finite], z[finite]

    empty = {
        "width_consistency_score": 0.0,
        "orientation_stability_score": 0.0,
        "morphology_line_coherence_score": 0.0,
        "morphology_axial_coverage_score": 0.0,
    }
    if len(x) < 8 or not np.isfinite(major_extent) or major_extent <= 0:
        return empty

    center, axis, global_angle = _principal_axis(x, y)
    perp = np.array([-axis[1], axis[0]])
    points = np.column_stack([x, y]) - center
    axial = points @ axis
    lateral = points @ perp

    span = float(np.max(axial) - np.min(axial))
    if span <= 1e-9:
        return empty

    width_scale = max(float(minor_extent), span / 32.0, 1e-9)
    bins = int(np.clip(round(span / width_scale), 5, 20))
    edges = np.linspace(float(np.min(axial)), float(np.max(axial)), bins + 1)
    bin_idx = np.clip(np.digitize(axial, edges[1:-1], right=False), 0, bins - 1)

    widths: list[float] = []
    orientations: list[float] = []
    orientation_weights: list[float] = []
    occupied = 0
    peak_abs_z = float(np.max(np.abs(z))) if z.size else 0.0
    strong_bins = 0

    for idx in range(bins):
        mask = bin_idx == idx
        if int(np.count_nonzero(mask)) < 2:
            continue
        occupied += 1
        lat = lateral[mask]
        width = float(np.quantile(lat, 0.90) - np.quantile(lat, 0.10))
        widths.append(max(width, 1e-9))

        # Estimate local orientation from a small axial neighborhood rather than
        # a single bin. A single bin often contains mostly the transverse width
        # and can therefore report a perpendicular PCA axis for a true line.
        center_axial = float((edges[idx] + edges[idx + 1]) / 2.0)
        bin_width = max(float(edges[idx + 1] - edges[idx]), 1e-9)
        neighborhood = np.abs(axial - center_axial) <= 1.5 * bin_width
        sub = points[neighborhood]
        if len(sub) >= 4:
            cov = np.cov(sub, rowvar=False)
            eigvals, eigvecs = np.linalg.eigh(cov)
            local_axis = eigvecs[:, int(np.argmax(eigvals))]
            local_angle = float(np.degrees(np.arctan2(local_axis[1], local_axis[0])) % 180.0)
            orientations.append(local_angle)
            weight = float(np.sum(np.abs(z[neighborhood])))
            orientation_weights.append(max(weight, 1e-6))
        if peak_abs_z > 1e-9:
            local_strength = float(np.max(np.abs(z[mask])))
            if local_strength >= 0.55 * peak_abs_z:
                strong_bins += 1

    if not widths or occupied < max(3, bins // 2):
        return empty

    width_cv = _robust_cv(widths)
    width_consistency = _consistency_from_cv(width_cv, scale=0.30)

    if orientations:
        angle_devs = np.array(
            [_angle_distance_deg(a, global_angle) for a in orientations], dtype=float
        )
        angle_devs = angle_devs[np.isfinite(angle_devs)]
        if angle_devs.size:
            weights = np.asarray(orientation_weights[: len(angle_devs)], dtype=float)
            weights = weights[: angle_devs.size]
            mean_dev = (
                float(np.average(angle_devs, weights=weights))
                if weights.size == angle_devs.size
                else float(np.mean(angle_devs))
            )
            orientation_stability = float(np.clip(math.exp(-mean_dev / 22.5), 0.0, 1.0))
        else:
            orientation_stability = 0.0
    else:
        orientation_stability = 0.0

    axial_coverage = float(np.clip(occupied / max(bins, 1), 0.0, 1.0))
    strong_coverage = float(np.clip(strong_bins / max(occupied, 1), 0.0, 1.0))
    axial_coverage_score = float(np.clip(0.55 * axial_coverage + 0.45 * strong_coverage, 0.0, 1.0))

    morphology_line_coherence = float(
        np.clip(
            0.24 * float(np.clip(linearity_score, 0.0, 1.0))
            + 0.22 * float(np.clip(line_support_score, 0.0, 1.0))
            + 0.18 * width_consistency
            + 0.18 * orientation_stability
            + 0.12 * axial_coverage_score
            + 0.06 * float(np.clip(len(widths) / max(bins, 1), 0.0, 1.0)),
            0.0,
            1.0,
        )
    )

    return {
        "width_consistency_score": round(width_consistency, 3),
        "orientation_stability_score": round(orientation_stability, 3),
        "morphology_line_coherence_score": round(morphology_line_coherence, 3),
        "morphology_axial_coverage_score": round(axial_coverage_score, 3),
    }

"""Seed utilities for consensus-map target separation (split from separation.py).

Pure helpers: peak finding, ROI patching, bipolar checks, depth-layer seeds.
No import from separation.py (config values are passed as arguments).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage

from ..models import Candidate


def _finite_peak(field: np.ndarray[Any, Any]) -> float:
    """Largest finite value in *field* (0.0 when there is none)."""
    from .._util import finite_values

    finite = finite_values(field)
    return float(np.max(finite)) if finite.size else 0.0


def _find_seeds(
    field: np.ndarray[Any, Any],
    mask: np.ndarray[Any, Any],
    *,
    min_distance: int,
    rel_height: float = 0.42,
) -> list[tuple[int, int, float]]:
    work = np.where(mask & np.isfinite(field), field, 0.0)
    peak = _finite_peak(work)
    if peak <= 0:
        return []
    threshold = max(1.5, float(peak * rel_height))
    size = max(3, int(2 * min_distance + 1))
    maxima = work == ndimage.maximum_filter(work, size=size, mode="nearest")
    coords = np.argwhere(maxima & (work >= threshold))
    if len(coords) == 0:
        return []
    ranked = sorted(
        ((int(r), int(c), float(work[r, c])) for r, c in coords), key=lambda t: t[2], reverse=True
    )
    accepted: list[tuple[int, int, float]] = []
    for r, c, value in ranked:
        if all(math.hypot(r - rr, c - cc) >= min_distance for rr, cc, _ in accepted):
            accepted.append((r, c, value))
    return accepted


def _patch_for_candidate(
    candidate: Candidate,
    *,
    field_shape: tuple[int, int],
    x0: float,
    y0: float,
    site_width: float,
    site_height: float,
) -> tuple[slice, slice]:
    """Return a local ROI using the actual rectangular field dimensions.

    Pixel mapping uses ``field_shape`` so non-square scan grids cannot mix
    X/Y axes.
    """
    height_px, width_px = field_shape
    cx = int(round(((candidate.x_center - x0) / max(site_width, 1e-9)) * (width_px - 1)))
    cy = int(round(((candidate.y_center - y0) / max(site_height, 1e-9)) * (height_px - 1)))
    radius_x = max(
        3,
        int(
            round(
                0.55
                * max(candidate.width, candidate.major_extent, 1.0)
                / max(site_width, 1e-9)
                * width_px
            )
        ),
    )
    radius_y = max(
        3,
        int(
            round(
                0.55
                * max(candidate.height, candidate.minor_extent, 1.0)
                / max(site_height, 1e-9)
                * height_px
            )
        ),
    )
    r0 = max(0, cy - radius_y)
    r1 = min(height_px, cy + radius_y + 1)
    c0 = max(0, cx - radius_x)
    c1 = min(width_px, cx + radius_x + 1)
    return slice(r0, r1), slice(c0, c1)


def _parent_is_bipolar(parent: Candidate, *, floor: float = 2.0, min_ratio: float = 0.35) -> bool:
    """True when the parent response shows strong opposite-sign lobes.

    Real metal-detector / EM responses are bipolar (positive + negative lobes
    from one object), while the synthetic test fixtures are monopolar. A fused
    parent with strong peaks on both sides is therefore a dipole candidate, not
    two independent objects.
    """
    try:
        pos = float(parent.positive_peak)
        neg = float(abs(parent.negative_peak))
    except (TypeError, ValueError):
        return False
    if pos < floor or neg < floor:
        return False
    return min(pos, neg) / max(pos, neg) >= min_ratio


def _depth_layer_seed_pair(
    field: np.ndarray[Any, Any],
    mask: np.ndarray[Any, Any],
    depth_field: np.ndarray[Any, Any] | None,
    *,
    min_depth_gap_m: float = 0.75,
    min_cluster_weight: float = 0.22,
    min_spatial_separation_px: float = 3.0,
) -> list[tuple[int, int, float, str]]:
    """Find a conservative same-sign seed pair from two local depth layers.

    This second-pass deblender only proposes seeds when the response-weighted
    depth distribution contains a real gap, both depth groups carry meaningful
    response mass, and their XY centroids are separated. It is a decomposition
    hypothesis, not proof of two physical objects.
    """
    if depth_field is None or np.shape(depth_field) != np.shape(field):
        return []
    fld = np.asarray(field, dtype=float)
    dep = np.asarray(depth_field, dtype=float)
    valid = np.asarray(mask, dtype=bool) & np.isfinite(fld) & (fld > 0) & np.isfinite(dep)
    rr, cc = np.nonzero(valid)
    if len(rr) < 12:
        return []
    d = dep[rr, cc]
    w = np.maximum(fld[rr, cc], 1e-6)
    order = np.argsort(d)
    d, rr, cc, w = d[order], rr[order], cc[order], w[order]
    gaps = np.diff(d)
    if not gaps.size:
        return []
    split = int(np.argmax(gaps))
    gap = float(gaps[split])
    if not np.isfinite(gap) or gap < float(min_depth_gap_m):
        return []
    left = np.arange(0, split + 1)
    right = np.arange(split + 1, len(d))
    total_w = float(np.sum(w))
    wl = float(np.sum(w[left]))
    wr = float(np.sum(w[right]))
    if wl / total_w < float(min_cluster_weight) or wr / total_w < float(min_cluster_weight):
        return []
    mu_l = float(np.average(d[left], weights=w[left]))
    mu_r = float(np.average(d[right], weights=w[right]))
    std_l = float(np.sqrt(np.average((d[left] - mu_l) ** 2, weights=w[left])))
    std_r = float(np.sqrt(np.average((d[right] - mu_r) ** 2, weights=w[right])))
    depth_sep = abs(mu_l - mu_r) / max(0.25 * (std_l + std_r), 0.20)
    if depth_sep < 1.8:
        return []
    cx_l = float(np.average(cc[left], weights=w[left]))
    cy_l = float(np.average(rr[left], weights=w[left]))
    cx_r = float(np.average(cc[right], weights=w[right]))
    cy_r = float(np.average(rr[right], weights=w[right]))
    spatial_sep = float(math.hypot(cx_l - cx_r, cy_l - cy_r))
    if spatial_sep < float(min_spatial_separation_px):
        return []
    peak = float(np.max(fld[valid]))
    seeds = []
    for inds in (left, right):
        best = inds[int(np.argmax(fld[rr[inds], cc[inds]]))]
        value = float(fld[rr[best], cc[best]])
        if value < 0.30 * peak:
            return []
        seeds.append((int(rr[best]), int(cc[best]), value, "depth-layer"))
    return seeds


__all__ = [
    "_finite_peak",
    "_find_seeds",
    "_patch_for_candidate",
    "_parent_is_bipolar",
    "_depth_layer_seed_pair",
]

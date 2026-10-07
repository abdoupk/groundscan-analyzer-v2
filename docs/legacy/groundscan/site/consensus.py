"""Site-level consensus maps and spatial clustering helpers.

Extracted verbatim from ``compare.multiscan`` orchestration; logic preserved
byte-for-byte, only imports adjusted to the refactored layout.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import ndimage

from ..core.grid import Grid2D
from ..models import Candidate
from .registration import AlignmentResult

if TYPE_CHECKING:
    from .analyze_site import ScanObservation


def _scan_extent(grid: Grid2D) -> tuple[float, float, float, float]:
    return (
        float(np.nanmin(grid.x_centers)),
        float(np.nanmax(grid.x_centers)),
        float(np.nanmin(grid.y_centers)),
        float(np.nanmax(grid.y_centers)),
    )


def _normalized_dims(candidate: Candidate, grid: Grid2D) -> tuple[float, float]:
    x0, x1, y0, y1 = _scan_extent(grid)
    return candidate.width / max(x1 - x0, 1e-9), candidate.height / max(y1 - y0, 1e-9)


def _reference_xy_from_aligned_point(
    row: float, col: float, ref_grid: Grid2D, resolution: int
) -> tuple[float, float]:
    x0, x1, y0, y1 = _scan_extent(ref_grid)
    x = x0 + (col / max(resolution - 1, 1)) * (x1 - x0)
    y = y0 + (row / max(resolution - 1, 1)) * (y1 - y0)
    return x, y


def _consensus_maps(
    observations: list[ScanObservation],
    alignments: dict[str, AlignmentResult],
    reference: ScanObservation,
    resolution: int,
    threshold: float,
    *,
    return_sign_consistency: bool = False,
) -> tuple[np.ndarray[Any, Any], ...]:
    """Build site-level consensus maps in the reference frame.

    ``sign_consistency`` (fraction of covering scans agreeing on the response
    sign) is folded into ``consensus_signed`` by default. Callers that need
    to *preserve* disagreement as disagreement (audit F-03 polarity
    conflict) pass ``return_sign_consistency=True`` and receive it as a
    sixth map instead of having it destroyed by the multiplication.
    """
    arrays = []
    masks = []
    ref_z = reference.anomaly.zscore
    base_ref, ref_mask = _resample_masked(ref_z, resolution)
    arrays.append(base_ref)
    masks.append(ref_mask)
    for obs in observations:
        if obs.label == reference.label:
            continue
        alignment = alignments[obs.label]
        arr = np.array(alignment.b_resampled, copy=True)
        mask = np.array(alignment.b_valid, copy=True)
        arr[~mask] = np.nan
        arrays.append(arr)
        masks.append(mask)
    stack = np.stack([np.nan_to_num(a, nan=0.0) for a in arrays])
    valid = np.stack(masks)
    coverage = valid.sum(axis=0)
    signed_mean = np.where(
        coverage > 0, np.sum(stack * valid, axis=0) / np.maximum(coverage, 1), np.nan
    )
    support = np.where(
        coverage > 0,
        np.sum((np.abs(stack) >= threshold) * valid, axis=0) / np.maximum(coverage, 1),
        np.nan,
    )
    positive_maps = []
    negative_maps = []
    for a, m in zip(arrays, masks, strict=True):
        aa = np.nan_to_num(a, nan=0.0)
        positive_maps.append(np.maximum(aa, 0.0) * m)
        negative_maps.append(np.maximum(-aa, 0.0) * m)
    positive_stack = np.stack(positive_maps)
    negative_stack = np.stack(negative_maps)
    positive_mean = np.where(
        coverage > 0, np.sum(positive_stack, axis=0) / np.maximum(coverage, 1), np.nan
    )
    negative_mean = np.where(
        coverage > 0, np.sum(negative_stack, axis=0) / np.maximum(coverage, 1), np.nan
    )

    sign_scores = []
    for a, m in zip(arrays, masks, strict=True):
        sign_scores.append(np.sign(np.nan_to_num(a, nan=0.0)) * m)
    sign_stack = np.stack(sign_scores)
    nonzero = valid & (np.abs(stack) > 0)
    sign_consistency = np.where(
        coverage > 0, np.abs(np.sum(sign_stack, axis=0)) / np.maximum(coverage, 1), 0.0
    )
    del sign_stack, nonzero

    persistence_maps = []
    for sigma in (0.0, 1.0, 2.0, 4.0):
        scale_vals = []
        for arr, mask in zip(arrays, masks, strict=True):
            if sigma:
                sm = ndimage.gaussian_filter(np.nan_to_num(arr, nan=0.0), sigma=sigma)
                mw = ndimage.gaussian_filter(mask.astype(float), sigma=sigma)
                sm = np.divide(sm, np.maximum(mw, 1e-6))
            else:
                sm = np.nan_to_num(arr, nan=0.0)
            sm = np.where(mask, sm, np.nan)
            scale_vals.append(sm)
        scale_stack = np.stack(scale_vals)
        # Uncovered cells are validly all-NaN; treat them as no persistence
        # rather than leaking a RuntimeWarning from nanmedian.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="All-NaN slice encountered", category=RuntimeWarning
            )
            robust_level = np.nanmedian(np.abs(scale_stack), axis=0)
        robust_level = np.nan_to_num(robust_level, nan=0.0)
        persistence_maps.append(robust_level >= (threshold * 0.75))
    multires_persistence = np.mean(np.stack(persistence_maps), axis=0)
    consensus_strength = np.clip(0.65 * support + 0.35 * multires_persistence, 0.0, 1.0)
    consensus_signed = np.clip(signed_mean, -np.inf, np.inf) * sign_consistency
    if return_sign_consistency:
        return (
            consensus_strength,
            consensus_signed,
            multires_persistence,
            positive_mean,
            negative_mean,
            sign_consistency,
        )
    return consensus_strength, consensus_signed, multires_persistence, positive_mean, negative_mean


def _resample_masked(
    array: np.ndarray[Any, Any], resolution: int
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    valid = np.isfinite(array)
    vals = ndimage.zoom(
        np.nan_to_num(array, nan=0.0),
        (resolution / array.shape[0], resolution / array.shape[1]),
        order=1,
    )
    mask = (
        ndimage.zoom(
            valid.astype(float), (resolution / array.shape[0], resolution / array.shape[1]), order=0
        )
        >= 0.5
    )
    vals[~mask] = np.nan
    return vals, mask


def _cluster_items(
    items: list[dict[str, Any]], distance_threshold: float = 0.06
) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for item in items:
        best = None
        best_d = float("inf")
        for idx, cluster in enumerate(clusters):
            cx = float(np.mean([q["u"] for q in cluster]))
            cy = float(np.mean([q["v"] for q in cluster]))
            d = float(np.hypot(item["u"] - cx, item["v"] - cy))
            adaptive = max(
                distance_threshold, 0.45 * max(item["scale"], *(q["scale"] for q in cluster))
            )
            if d <= adaptive and d < best_d:
                best, best_d = idx, d
        if best is None:
            clusters.append([item])
        else:
            clusters[best].append(item)
    return clusters

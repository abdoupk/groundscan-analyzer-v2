"""Multiscale signed anomaly detection and artifact-aware component labeling."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage

from .background import multiscale_zscore, remove_background, robust_scale, robust_zscore
from .grid import Grid2D


@dataclass
class AnomalyMap:
    zscore: np.ndarray[Any, Any]
    labels: np.ndarray[Any, Any]
    n_components: int
    threshold: float
    residual: np.ndarray[Any, Any]
    persistence: np.ndarray[Any, Any]
    # v0.2.1 robust broad-pattern channel. These fields are additive so old
    # callers can keep using zscore/labels unchanged.
    component_types: dict[int, str] = field(default_factory=dict)
    broad_zscore: np.ndarray[Any, Any] | None = None
    broad_persistence: np.ndarray[Any, Any] | None = None
    # Remediation Design v2 §11 (Wave 1): the shadow-measurement ledger.
    #
    # `AnomalyMap` is the carrier because it is the one per-run object that is
    # threaded to every stage needing the shadow *and* is never serialised.
    # `Candidate` fields and `ScanMetadata.extra` both reach `analysis.json`,
    # which is golden-hashed, so a shadow value written to either would be a
    # behaviour change wearing a diagnostics label. `None` means "not measured";
    # the default keeps the field inert for every pre-Wave-1 caller.
    shadow: Any | None = None


@dataclass
class ArtifactMap:
    """Per-cell artifact likelihood, 0..1, used as evidence rather than a hard filter."""

    score: np.ndarray[Any, Any]


def _largest_odd_scale(scales: tuple[int, ...], shape: tuple[int, int]) -> int | None:
    """Return the largest configured scale, but reserve a larger regional scale when possible."""
    viable = []
    for raw in scales:
        size = max(1, int(raw))
        if size % 2 == 0:
            size += 1
        if min(shape) >= size:
            viable.append(size)
    if not viable:
        return None
    configured = max(viable)
    # The broad channel should sit below the whole field, not merely equal the
    # largest local background scale. On small grids this safely falls back to
    # the largest configured value.
    regional = max(1, min(shape) - 2)
    if regional % 2 == 0:
        regional -= 1
    if regional >= 3:
        return max(configured, regional) if max(configured, regional) < min(shape) else configured
    return configured


def _detrended_residual(grid: Grid2D) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Return the planar-detrended residual and the valid-cell mask.

    v0.4.2 (audit F-06): extracted from ``_regional_trend_zscore`` so the
    broad-component selection can measure *unsmoothed* raw support. Identical
    fit to the previous inline lstsq; numbers are unchanged.
    """
    signal = np.asarray(grid.signal, dtype=float)
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.full(signal.shape, np.nan, dtype=float), valid
    yy, xx = np.indices(signal.shape)
    # Integer-take instead of boolean-mask getitem: identical values in
    # C order, but typed on every numpy stub generation (mask getitem on
    # np.indices output is rejected as call-overload or index).
    keep = np.flatnonzero(valid)
    A = np.column_stack([np.ones(keep.size), xx.ravel()[keep], yy.ravel()[keep]])
    coef, *_ = np.linalg.lstsq(A, signal[valid], rcond=None)
    plane = coef[0] + coef[1] * xx + coef[2] * yy
    return np.where(valid, signal - plane, np.nan), valid


def _regional_trend_zscore(grid: Grid2D, sigma: float | None = None) -> np.ndarray[Any, Any]:
    """Return a low-frequency z-score after removing a first-order spatial trend.

    The regional channel is intentionally separate from local anomaly detection.
    It is useful for broad geological/background variation where a median filter
    can absorb the anomaly itself. Missing cells are imputed only for convolution;
    the returned z-score restores them to NaN.
    """
    signal = np.asarray(grid.signal, dtype=float)
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.full(signal.shape, np.nan, dtype=float)
    residual, valid = _detrended_residual(grid)
    fill = float(np.nanmedian(residual[valid]))
    filled = np.nan_to_num(residual, nan=fill)
    if sigma is None:
        sigma = float(np.clip(min(signal.shape) * 0.055, 1.5, 4.0))
    smooth = ndimage.gaussian_filter(filled, sigma=float(sigma), mode="nearest")
    z = robust_zscore(smooth)
    z[~valid] = np.nan
    return z


def _broad_component_selection(
    grid: Grid2D,
    z: np.ndarray[Any, Any],
    threshold: float,
    min_area_fraction: float,
    min_span_fraction: float,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], int]:
    """Find spatially broad, low-frequency regions without turning them into point targets."""
    valid = np.isfinite(z)
    mask = valid & (np.abs(z) >= threshold)
    structure = ndimage.generate_binary_structure(2, 2)
    labels, n = ndimage.label(mask, structure=structure)
    if n == 0:
        return np.zeros_like(z, dtype=int), np.zeros_like(z, dtype=float), 0

    # v0.4.2 (audit F-06): a broad component must be supported by many cells in
    # the *unsmoothed* detrended residual, not only by the smoothed z-field.
    # Without this, a single-cell instrument spike distorts the planar fit and
    # the Gaussian smoothing turns it into a plausible-looking broad "regional"
    # component that inherits the spike's saturated magnitude (measured: one
    # 500-value spike on a constant field became a 63-cell broad candidate with
    # |z|~147 classified metallic-like at confidence 0.94).
    # The support cut is relative to the component's own peak residual (25%)
    # with a 1.5-sigma floor, so it is scale-free: an isolated spike has a
    # unique peak (support = 1 cell) while genuine regional variation deviates
    # across its whole core (measured on the geological_broad reference:
    # 37-87% of component cells).
    _BROAD_RAW_SUPPORT_PEAK_FRACTION = 0.25
    _BROAD_RAW_SUPPORT_SIGMA = 1.5
    _BROAD_RAW_SUPPORT_MIN_FRACTION = 0.12
    detrended, _ = _detrended_residual(grid)
    r_finite = detrended[np.isfinite(detrended)]
    r_sigma = _BROAD_RAW_SUPPORT_SIGMA * robust_scale(r_finite) if r_finite.size else 0.0

    total_cells = int(np.count_nonzero(np.isfinite(grid.signal)))
    min_area = max(8, int(math.ceil(max(total_cells, 1) * min_area_fraction)))
    h, w = z.shape
    kept = np.zeros_like(labels, dtype=bool)
    broadness = np.zeros_like(z, dtype=float)

    for comp_id in range(1, n + 1):
        ys, xs = np.where(labels == comp_id)
        area = len(xs)
        if area < min_area:
            continue
        # Broad-pattern requirement: occupy meaningful spans in BOTH axes.
        span_x = (xs.max() - xs.min() + 1) / max(w, 1)
        span_y = (ys.max() - ys.min() + 1) / max(h, 1)
        if span_x < min_span_fraction or span_y < min_span_fraction:
            continue
        comp_res = np.abs(detrended[labels == comp_id])
        comp_res = comp_res[np.isfinite(comp_res)]
        if comp_res.size and r_sigma > 0.0:
            support_cut = max(
                _BROAD_RAW_SUPPORT_PEAK_FRACTION * float(np.max(comp_res)),
                r_sigma,
            )
            raw_support = int(np.count_nonzero(comp_res >= support_cut))
        else:
            raw_support = area
        if raw_support < max(4, int(round(_BROAD_RAW_SUPPORT_MIN_FRACTION * area))):
            continue
        touches_edge = xs.min() == 0 or ys.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1
        density = area / max((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1), 1)
        peak = float(np.nanmax(np.abs(z[labels == comp_id]))) if area else 0.0
        # Boundary broad patterns are retained only when their low-frequency
        # support is strong. They remain auditable as boundary-contact candidates.
        if touches_edge and not (
            peak >= max(2.8, threshold + 0.4) and density >= 0.45 and area >= min_area * 1.25
        ):
            continue
        span_score = min(1.0, math.sqrt(span_x * span_y) / max(min_span_fraction, 1e-9))
        area_score = min(1.0, area / max(min_area * 2.0, 1))
        score = float(np.clip(0.55 * density + 0.30 * span_score + 0.15 * area_score, 0.0, 1.0))
        kept[labels == comp_id] = True
        broadness[labels == comp_id] = score

    kept_labels, kept_n = ndimage.label(kept, structure=structure)
    return kept_labels.astype(int), broadness, int(kept_n)


def detect_artifacts(grid: Grid2D, anomaly: AnomalyMap) -> ArtifactMap:
    """Estimate obvious analysis artifacts without deleting real edge targets.

    Evidence includes boundary proximity, sparse/missing neighborhoods and
    single-cell isolation. The result is a soft score so later classification
    can say "artifact-prone" instead of silently throwing data away.
    """
    valid = np.isfinite(grid.signal)
    score = np.zeros(grid.signal.shape, dtype=float)
    if not np.any(valid):
        return ArtifactMap(score)

    h, w = grid.signal.shape
    yy, xx = np.indices((h, w))
    edge_distance = np.minimum.reduce([yy, xx, h - 1 - yy, w - 1 - xx]).astype(float)
    score += np.where(edge_distance <= 0, 0.45, np.where(edge_distance <= 1, 0.20, 0.0))

    local_valid = ndimage.uniform_filter(valid.astype(float), size=3, mode="nearest")
    score += np.clip(1.0 - local_valid, 0.0, 1.0) * 0.45

    comp_sizes = (
        ndimage.sum(
            np.ones_like(anomaly.labels, dtype=float),
            anomaly.labels,
            index=range(1, anomaly.n_components + 1),
        )
        if anomaly.n_components
        else np.array([])
    )
    if anomaly.n_components:
        isolated = np.zeros_like(score)
        for comp_id, size in enumerate(comp_sizes, start=1):
            if size <= 2:
                isolated[anomaly.labels == comp_id] = 1.0
        score += isolated * 0.30

    return ArtifactMap(np.clip(score, 0.0, 1.0))


def detect_anomalies(
    grid: Grid2D,
    threshold: float = 3.0,
    min_size: int = 3,
    background_method: str = "multiscale",
    scales: tuple[int, ...] = (3, 5, 9, 15),
    connectivity: int = 8,
    include_broad: bool = True,
    broad_threshold: float = 2.1,
    broad_min_area_fraction: float = 0.02,
    broad_min_span_fraction: float = 0.18,
    min_persistence: float = 0.5,
) -> AnomalyMap:
    """Detect local signed anomalies and, optionally, broad low-frequency regions.

    Local anomalies use the v0.2 multiscale detector. Broad patterns are a separate
    scale channel, designed to retain regional/geological variation without turning
    every smooth field into a point candidate.

    v0.4.2 (audit F-18): the detector keeps the max over scales, which is a
    multiple-comparison maximizer -- a 3.0 gate on the max of 4 correlated
    z-fields admits more noise than a single-field 3.0. Local components
    must therefore confirm on more than one scale: the component's best
    persistence (fraction of viable scales reaching |z| >= 2.0) has to reach
    ``min_persistence``. Single-scale speckles that clear the max-gate on one
    lucky scale are rejected; genuine responses persist across neighboring
    scales. The gate is skipped when fewer than two scales are viable
    (nothing to confirm against) and never applies to broad-channel
    components, which carry their own conservative selection.
    """
    if background_method == "multiscale":
        z, persistence, residual = multiscale_zscore(grid, scales=scales)
    else:
        residual = remove_background(grid, method=background_method)
        z = robust_zscore(residual)
        persistence = (np.isfinite(z) & (np.abs(z) >= threshold)).astype(float)

    mask = np.isfinite(z) & (np.abs(z) >= threshold)
    structure = ndimage.generate_binary_structure(2, 2 if connectivity == 8 else 1)
    labels, n = ndimage.label(mask, structure=structure)

    if min_size > 1 and n > 0:
        sizes = ndimage.sum(mask, labels, index=range(1, n + 1))
        keep = np.zeros(n + 1, dtype=bool)
        for comp_id, size in enumerate(sizes, start=1):
            keep[comp_id] = size >= min_size
        labels = np.where(keep[labels], labels, 0)
        labels, n = ndimage.label(labels > 0, structure=structure)

    # v0.4.2 (audit F-18): multiple-comparison guard for max-of-scales
    # selection (see docstring). Uses each component's best cell so halo
    # cells cannot veto a confirmed core.
    if (
        background_method == "multiscale"
        and min_persistence > 0
        and n > 0
        and int(np.count_nonzero(np.isfinite(persistence))) > 0
    ):
        viable_scales = 0
        for raw_size in scales:
            size = max(1, int(raw_size))
            if size % 2 == 0:
                size += 1
            if min(grid.signal.shape) >= size:
                viable_scales += 1
        if viable_scales >= 2:
            keep = np.zeros(n + 1, dtype=bool)
            keep[0] = True
            for comp_id in range(1, int(n) + 1):
                cells = persistence[labels == comp_id]
                cells = cells[np.isfinite(cells)]
                keep[comp_id] = bool(cells.size) and float(np.max(cells)) >= min_persistence
            labels = np.where(keep[labels], labels, 0)
            labels, n = ndimage.label(labels > 0, structure=structure)

    component_types: dict[int, str] = {int(i): "local" for i in range(1, int(n) + 1)}
    broad_z = None
    broad_persistence = None

    if include_broad:
        broad_scale = _largest_odd_scale(scales, grid.signal.shape)
        if broad_scale is not None:
            broad_z = _regional_trend_zscore(grid)
            # Large-scale support is intentionally conservative: it is a
            # morphology channel, not another local-target detector.
            broad_persistence = (np.isfinite(broad_z) & (np.abs(broad_z) >= 2.0)).astype(float)
            broad_labels, _, broad_n = _broad_component_selection(
                grid, broad_z, broad_threshold, broad_min_area_fraction, broad_min_span_fraction
            )
            if broad_n:
                next_id = int(n) + 1
                for broad_id in range(1, broad_n + 1):
                    cell_mask = broad_labels == broad_id
                    # If a broad region substantially overlaps a local candidate,
                    # the local candidate already explains that area at finer scale.
                    overlap = int(np.count_nonzero(cell_mask & (labels > 0))) / max(
                        int(np.count_nonzero(cell_mask)), 1
                    )
                    local_neighborhood = ndimage.binary_dilation(
                        labels > 0, iterations=2, structure=structure
                    )
                    neighborhood_overlap = int(
                        np.count_nonzero(cell_mask & local_neighborhood)
                    ) / max(int(np.count_nonzero(cell_mask)), 1)
                    # A broad background region that hugs a strong local component is
                    # treated as context, not a second target. This prevents a smooth
                    # low-frequency halo around a tunnel/compact response from becoming
                    # a competing geological candidate.
                    if overlap > 0.35 or neighborhood_overlap > 0.30:
                        continue
                    new_mask = cell_mask & (labels == 0)
                    if np.count_nonzero(new_mask) < max(
                        8, int(np.ceil(grid.signal.size * broad_min_area_fraction))
                    ):
                        continue
                    labels[new_mask] = next_id
                    component_types[next_id] = "broad"
                    next_id += 1
                n = next_id - 1

    # At merged broad cells, use the broad-channel signed score; local cells retain
    # their multiscale signed score. This preserves polarity through extraction.
    if broad_z is not None and component_types:
        z = z.copy()
        persistence = persistence.copy()
        broad_cells = np.zeros_like(labels, dtype=bool)
        for comp_id, kind in component_types.items():
            if kind == "broad":
                broad_cells |= labels == comp_id
        z[broad_cells] = broad_z[broad_cells]
        persistence[broad_cells] = (
            broad_persistence[broad_cells] if broad_persistence is not None else 1.0
        )

    return AnomalyMap(
        zscore=z,
        labels=labels,
        n_components=int(n),
        threshold=float(threshold),
        residual=residual,
        persistence=persistence,
        component_types=component_types,
        broad_zscore=broad_z,
        broad_persistence=broad_persistence,
    )

"""Robust, signed, multiscale signal processing."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage

from .._util import SCALE_DISPERSION_FLOOR, robust_scale_with_status
from .grid import Grid2D


def _nan_safe_fill(signal: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Fill NaN cells for window filtering without biasing the background.

    v0.4.2 (audit F-24): the previous global-median fill pulled the
    background ring around a large hole toward the field median. Filling
    with the NEAREST valid sample instead keeps the fill local: hole
    interiors take after their own edges, and any residual leak into
    neighbors' residuals is bounded by one filter radius in space. NaN
    cells are still restored to NaN by the caller after filtering.
    """
    signal = np.asarray(signal, dtype=float)
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.zeros_like(signal, dtype=float)
    if np.all(valid):
        return signal
    edt = ndimage.distance_transform_edt(~valid, return_indices=True)
    if isinstance(edt, tuple):
        # Build-dependent shape: either (distances, stacked-indices) or one
        # index array per axis. Accept either and reduce to stacked indices.
        stacked = [np.asarray(el) for el in edt if np.shape(el) == (valid.ndim,) + valid.shape]
        indices = stacked[0] if stacked else np.stack([np.asarray(el) for el in edt])
    else:
        indices = np.asarray(edt)
    nearest = tuple(indices[axis][~valid] for axis in range(valid.ndim))
    filled = signal.copy()
    filled[~valid] = signal[nearest]
    return filled


def remove_background(grid: Grid2D, method: str = "median", size: int = 5) -> np.ndarray[Any, Any]:
    """Return a signed local residual (positive and negative anomalies survive)."""
    signal = np.asarray(grid.signal, dtype=float)
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.full_like(signal, np.nan)

    size = max(1, int(size))
    if size % 2 == 0:
        size += 1

    if method == "none" or min(signal.shape) < size:
        baseline = float(np.median(signal[valid]))
        residual = signal - baseline
    elif method == "median":
        filled = _nan_safe_fill(signal)
        background = ndimage.median_filter(filled, size=size, mode="nearest")
        residual = signal - background
    else:
        raise ValueError(f"Unknown background method: {method!r}")

    residual[~valid] = np.nan
    return residual


# v0.4.2 (audit F-01): on near-constant fields the MAD/IQR of a median-filter
# residual can measure only floating-point/quantization dust, collapsing the
# noise scale to ~1e-9 and inflating |z| to astronomical values (measured
# 4.17e9 for a plain Gaussian anomaly) for every downstream consumer
# (evidence strength, thresholds, cross-scan ratios, plots).
#
# This was originally addressed by flooring the robust scale at 5% of the
# residual standard deviation. That floor is gone: it was computed from a
# winsorized std and was therefore provably a no-op (see
# ``groundscan._util.robust_scale``). The dust regime is now handled where it
# belongs -- the caller applies ``SCALE_DISPERSION_FLOOR`` (1e-9, the same
# number, relocated) and the saturation knee below caps the reported |z|.
# v0.4.2 (audit F-01): reported z-scores are saturating, not hard-clipped. A
# hard clip would flatten strong anomaly cores into plateaus of equal value,
# which downstream peak-seeding would misread as multiple same-sign peaks and
# split a single response into fragments. Below the knee the transform is the
# identity (exact parity with the 3.0 detection threshold); above it the value
# rises monotonically toward ZSCORE_CLIP without ever forming a plateau.
_ZSCORE_KNEE = 100.0
ZSCORE_CLIP = 150.0
# Empirical basis (v0.4.2 audit): across all nine OKM vendor-reference files the
# legitimate multiscale peak |z| never exceeded 67.45, and the robust-scale
# floor never activated on them (real device data carries genuine noise). The
# dust regime -- where the floor-less estimator produced |z| of 1e3..1e9 --
# begins around |z|~200. The knee at 100 therefore leaves every legitimate
# magnitude in the exact-identity region (byte-identical analysis on real
# data) while compressing only degenerate magnitudes, bounded at 150.


def _saturate_magnitude(z: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Monotone bounded saturation: identity up to the knee, asymptotic to the clip."""
    magnitude = np.abs(z)
    excess = magnitude - _ZSCORE_KNEE
    saturated = np.where(
        excess > 0.0,
        _ZSCORE_KNEE
        + (ZSCORE_CLIP - _ZSCORE_KNEE) * np.tanh(excess / (ZSCORE_CLIP - _ZSCORE_KNEE)),
        magnitude,
    )
    # asarray keeps the return typed across numpy stub versions (np.where
    # and np.sign resolve to Any on newer stubs).
    return np.asarray(np.sign(z) * saturated, dtype=float)


def robust_scale(values: np.ndarray[Any, Any]) -> float:
    """Estimate spread robustly with MAD -> IQR -> std fallback (audit F-01).

    Canonical implementation lives in :mod:`groundscan._util`; this wrapper
    is kept so existing ``from .background import robust_scale`` imports
    keep working with identical behavior.
    """
    from .._util import robust_scale as _canonical

    return _canonical(values)


def robust_zscore(residual: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Signed robust z-score with stable fallbacks for near-zero MAD data.

    v0.4.2 (audit F-01): the result is a bounded, monotone function of the
    raw ratio (identity below ``_ZSCORE_KNEE``, asymptotic to ``ZSCORE_CLIP``
    above), so no reported magnitude can exceed a documented bound and no
    dust-collapsed scale estimate can inflate it. NaN cells stay NaN.

    Remediation risk R4, closed in Stage 3: the scale now carries a status, and
    an ``indeterminate`` one must never reach a threshold as if it were a
    number. So this function reads the status instead of the legacy constant,
    and it reports **zero** for every finite cell in two situations:

    * the scale is ``indeterminate`` -- the residual's own dispersion is below
      ``1e-9`` of its own extent, so no cell deviates from the population by a
      measurable amount;
    * the scale is finite but below :data:`_util.SCALE_DISPERSION_FLOOR` -- the
      residual's spread is below the double-precision resolution of the
      arithmetic that produced it, so the ratio is arithmetically computable and
      physically meaningless.

    Zero is the honest answer in both cases, and it is what the fabricated
    constant already produced for the first (``(r - median) / 1.0`` is 0 for a
    constant residual). For the second the *ratio* is what the estimator now
    reports instead of a fabricated 1.0, and this is where the unit-dependent
    policy is stated rather than hidden: see the comment on
    ``_util.SCALE_DISPERSION_FLOOR`` for why the absolute floor is a caller
    decision and not a property of a dispersion estimator. A ``|z|`` of 1e-10
    changing to exactly 0 cannot move a finding count -- nothing at 1e-10 reaches
    a 3.0 gate -- and it removes a reported number that asserted nothing.
    """
    residual = np.asarray(residual, dtype=float)
    valid = residual[np.isfinite(residual)]
    if valid.size == 0:
        return np.full_like(residual, np.nan)
    estimate = robust_scale_with_status(valid)
    if estimate.is_indeterminate or not (estimate.scale >= SCALE_DISPERSION_FLOOR):
        return np.where(np.isfinite(residual), 0.0, np.nan)
    z = (residual - float(np.median(valid))) / estimate.scale
    return _saturate_magnitude(z)


def multiscale_zscore(
    grid: Grid2D,
    scales: tuple[int, ...] = (3, 5, 9),
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Return ``(signed_z, persistence, residual)`` across several spatial scales.

    For every cell the strongest absolute signed z-score across the viable scales
    is retained. Persistence is the fraction of tested scales where |z| >= 2.
    This prevents the detector from being tied to one arbitrary filter size.
    """
    viable: list[np.ndarray[Any, Any]] = []
    residuals: list[np.ndarray[Any, Any]] = []
    for raw_size in scales:
        size = max(1, int(raw_size))
        if size % 2 == 0:
            size += 1
        if min(grid.signal.shape) < size:
            continue
        residual = remove_background(grid, method="median", size=size)
        viable.append(robust_zscore(residual))
        residuals.append(residual)

    if not viable:
        residual = remove_background(grid, method="none")
        z = robust_zscore(residual)
        return z, (np.isfinite(z) & (np.abs(z) >= 2.0)).astype(float), residual

    stack = np.stack(viable, axis=0)
    abs_stack = np.abs(stack)
    best_idx = np.nanargmax(np.where(np.isfinite(abs_stack), abs_stack, -np.inf), axis=0)
    best_z = np.take_along_axis(stack, best_idx[None, ...], axis=0)[0]
    valid_count = np.sum(np.isfinite(stack), axis=0)
    support_count = np.sum(np.isfinite(stack) & (np.abs(stack) >= 2.0), axis=0)
    persistence = np.divide(
        support_count,
        np.maximum(valid_count, 1),
        out=np.zeros_like(support_count, dtype=float),
        where=valid_count > 0,
    )
    residual = np.take_along_axis(np.stack(residuals, axis=0), best_idx[None, ...], axis=0)[0]
    best_z[valid_count == 0] = np.nan
    persistence[valid_count == 0] = np.nan
    residual[valid_count == 0] = np.nan
    return best_z, persistence, residual

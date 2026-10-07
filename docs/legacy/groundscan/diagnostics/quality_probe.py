"""Scan-quality acquisition/instrument diagnostics.

Split from ``groundscan.analysis.realworld``: this module holds the generic
scan-quality probe (:func:`detect_scan_quality_diagnostics` plus helpers).
Dipolar response merging/deblending lives in :mod:`groundscan.diagnostics.dipole`.

The heuristics are deliberately conservative and generic (no vendor/device
names or rules). This is a scan-quality diagnostic, not an object detector.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.grid import Grid2D


def _robust_scale(values: np.ndarray[Any, Any]) -> float:
    """Local scale WITHOUT the _util floor (see gates/field_quality note).

    Kept separate so artifact scoring returns 0.0 on degenerate input.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 3:
        return 0.0
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med)))
    if mad > 1e-12:
        return 1.4826 * mad
    q1, q3 = np.percentile(v, [25, 75])
    return float((q3 - q1) / 1.349)


def detect_scan_quality_diagnostics(grid: Grid2D) -> dict[str, Any]:
    """Detect generic acquisition/instrument artifacts not represented by candidates.

    The detector is deliberately conservative. It looks for isolated depth or signal
    excursions at the scan boundary that are extreme relative to the rest of the grid.
    This is a scan-quality diagnostic, not an object detector.
    """
    signal = np.asarray(grid.signal, dtype=float)
    depth = np.asarray(grid.depth, dtype=float)
    signal_valid = np.isfinite(signal)
    depth_valid = np.isfinite(depth)
    if not np.any(signal_valid):
        return {
            "flags": ["no-valid-measurements"],
            "instrument_artifact_score": 1.0,
            "depth_outlier_fraction": 0.0,
            "signal_outlier_fraction": 0.0,
            "corner_depth_outlier": False,
        }

    s = signal[signal_valid]
    s_med = float(np.median(s))
    s_scale = max(_robust_scale(s), 1e-9)
    s_robust_z = np.abs(s - s_med) / s_scale
    signal_outlier_fraction = float(np.mean(s_robust_z >= 8.0))

    if np.any(depth_valid):
        d = depth[depth_valid]
        d_med = float(np.median(d))
        d_scale = max(_robust_scale(d), 1e-9)
        d_robust_z = np.abs(d - d_med) / d_scale
        depth_outlier_fraction = float(np.mean(d_robust_z >= 8.0))
    else:
        d = np.array([], dtype=float)
        d_med = 0.0
        d_scale = 1.0
        d_robust_z = np.array([], dtype=float)
        depth_outlier_fraction = 0.0
    h, w = signal.shape
    edge = np.zeros(signal.shape, dtype=bool)
    edge[0, :] = True
    edge[-1, :] = True
    edge[:, 0] = True
    edge[:, -1] = True
    corner = np.zeros(signal.shape, dtype=bool)
    corner[0, 0] = corner[0, -1] = corner[-1, 0] = corner[-1, -1] = True

    if np.any(depth_valid):
        edge_depth_z = np.where(edge & depth_valid, np.abs(depth - d_med) / d_scale, -np.inf)
        corner_depth_outlier = bool(
            np.nanmax(np.where(corner & depth_valid, edge_depth_z, -np.inf)) >= 8.0
        )
        extreme_edge = edge & depth_valid & (edge_depth_z >= 8.0)
        extreme_count = int(np.count_nonzero(extreme_edge))
        concentration = extreme_count / max(int(np.count_nonzero(edge & depth_valid)), 1)
    else:
        edge_depth_z = np.full(depth.shape, -np.inf, dtype=float)
        corner_depth_outlier = False
        concentration = 0.0

    # A very large depth excursion concentrated in one boundary cell/region is a
    # common acquisition error signature. Requiring both concentration and a strong
    # robust excursion prevents broad real depth variation from being flagged.
    instrument_score = 0.0
    flags: list[str] = []
    # Keep this diagnostic intentionally strict: broad depth/signal variation can
    # be a real subsurface response. We only label an acquisition artifact when
    # an extreme depth excursion is isolated at a corner/boundary.
    if corner_depth_outlier and concentration <= 0.20:
        instrument_score = 0.90
        flags.append("isolated-boundary-depth-outlier")
    if not flags:
        flags.append("no-obvious-instrument-artifact")
    if not np.any(depth_valid):
        flags.append("no-depth-channel")

    return {
        "flags": flags,
        "instrument_artifact_score": float(np.clip(instrument_score, 0.0, 1.0)),
        "depth_outlier_fraction": round(depth_outlier_fraction, 4),
        "signal_outlier_fraction": round(signal_outlier_fraction, 4),
        "corner_depth_outlier": corner_depth_outlier,
    }


__all__ = ["detect_scan_quality_diagnostics"]

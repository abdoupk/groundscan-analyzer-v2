"""
Turn a ScanData's (possibly irregular) points into regular 2D grids
that the rest of the analysis pipeline can work on with plain array
operations. Works for both grid-based devices (Rover) and scattered
point clouds (generic CSV), the difference is just which reconstruction
strategy fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..models import ScanData


@dataclass
class Grid2D:
    x_centers: np.ndarray[Any, Any]  # 1D, shape (nx,)
    y_centers: np.ndarray[Any, Any]  # 1D, shape (ny,)
    signal: np.ndarray[Any, Any]  # 2D, shape (ny, nx)
    depth: np.ndarray[Any, Any]  # 2D, shape (ny, nx)
    counts: np.ndarray[Any, Any]  # 2D, shape (ny, nx) — samples per cell


def reconstruct_grid(scan: ScanData, target_cells: int = 60) -> Grid2D:
    """
    Reconstruct a regular grid from scan points.

    If the device already reports grid indices (grid_i/grid_j — true for
    Rover-style exports), we use those directly: no interpolation, no
    guessing. Otherwise we bin the scattered x/y points into a roughly
    `target_cells`-per-axis grid and average signal/depth per cell.
    """
    # Prefer trustworthy physical x/y lattice coordinates when available.
    # This also handles re-oriented exports where device grid_i/grid_j remain
    # unchanged but x/y were transformed with the scan.
    regular = _grid_from_regular_coordinates(scan)
    if regular is not None:
        return regular
    if (
        scan.grid_i is not None
        and scan.grid_j is not None
        and not np.any(np.isnan(scan.grid_i))
        and not np.any(np.isnan(scan.grid_j))
    ):
        return _grid_from_indices(scan)
    return _grid_from_scatter(scan, target_cells)


def _grid_from_indices(scan: ScanData) -> Grid2D:
    gi = np.asarray(scan.grid_i, dtype=int)
    gj = np.asarray(scan.grid_j, dtype=int)
    i_vals = np.unique(gi)
    j_vals = np.unique(gj)
    ci = np.searchsorted(i_vals, gi)
    cj = np.searchsorted(j_vals, gj)
    nx, ny = i_vals.size, j_vals.size
    flat = cj * nx + ci
    counts = np.bincount(flat, minlength=nx * ny).reshape(ny, nx)
    signal_sum = np.bincount(
        flat,
        weights=np.nan_to_num(np.asarray(scan.signal, dtype=float), nan=0.0),
        minlength=nx * ny,
    ).reshape(ny, nx)
    signal_valid = np.bincount(
        flat, weights=np.isfinite(scan.signal).astype(float), minlength=nx * ny
    ).reshape(ny, nx)
    depth_values = np.asarray(scan.z, dtype=float)
    depth_sum = np.bincount(
        flat, weights=np.nan_to_num(depth_values, nan=0.0), minlength=nx * ny
    ).reshape(ny, nx)
    depth_valid = np.bincount(
        flat, weights=np.isfinite(depth_values).astype(float), minlength=nx * ny
    ).reshape(ny, nx)
    with np.errstate(invalid="ignore", divide="ignore"):
        signal = signal_sum / np.maximum(signal_valid, 1.0)
        depth = depth_sum / np.maximum(depth_valid, 1.0)
    signal[signal_valid == 0] = np.nan
    depth[depth_valid == 0] = np.nan
    x_values = np.asarray(scan.x, dtype=float)
    y_values = np.asarray(scan.y, dtype=float)
    x_sum = np.bincount(flat, weights=np.nan_to_num(x_values, nan=0.0), minlength=nx * ny).reshape(
        ny, nx
    )
    x_valid = np.bincount(
        flat, weights=np.isfinite(x_values).astype(float), minlength=nx * ny
    ).reshape(ny, nx)
    y_sum = np.bincount(flat, weights=np.nan_to_num(y_values, nan=0.0), minlength=nx * ny).reshape(
        ny, nx
    )
    y_valid = np.bincount(
        flat, weights=np.isfinite(y_values).astype(float), minlength=nx * ny
    ).reshape(ny, nx)
    x_centers = np.divide(x_sum.sum(axis=0), np.maximum(x_valid.sum(axis=0), 1.0))
    y_centers = np.divide(y_sum.sum(axis=1), np.maximum(y_valid.sum(axis=1), 1.0))
    x_centers[x_valid.sum(axis=0) == 0] = np.nan
    y_centers[y_valid.sum(axis=1) == 0] = np.nan
    return Grid2D(
        x_centers=x_centers,
        y_centers=y_centers,
        signal=signal,
        depth=depth,
        counts=counts.astype(int),
    )


def cluster_axis_coordinates(
    values: np.ndarray[Any, Any], tolerance: float = 1e-6
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Tolerance-aware axis clustering for lattice reconstruction.

    Sorts the coordinates and merges values whose gap is small relative to the
    dominant between-cell spacing (or below the absolute ``tolerance`` floor).
    Returns ``(centers, labels)`` where ``centers[k]`` is the mean coordinate of
    cluster ``k`` (ascending order) and ``labels[i]`` is the cluster index of
    ``values[i]``.

    For an exactly regular lattice this is equivalent to ``np.unique`` followed
    by an index lookup.  For coordinates with small floating-point jitter it
    groups each jittered copy of a lattice position back into one cell instead
    of exploding the axis into one entry per sample.  The cluster tolerance is
    ``max(tolerance, spacing * 2.5e-3)`` where ``spacing`` is estimated only from
    the large between-cell gaps, so small within-cluster jitter gaps cannot
    pollute the estimate.  This mirrors the regularity tolerance already used
    by ``_grid_from_regular_coordinates`` (max per-point deviation <=
    spacing * 1e-3, i.e. within-cell gaps up to twice that), so clustering can
    never merge two legitimately distinct lattice positions.
    """
    vals = np.asarray(values, dtype=float)
    if vals.size == 0:
        return np.empty(0, dtype=float), np.empty(0, dtype=int)
    order = np.argsort(vals, kind="stable")
    sorted_vals = vals[order]
    if vals.size == 1:
        return np.array([sorted_vals[0]]), np.zeros(1, dtype=int)
    gaps = np.diff(sorted_vals)
    big = gaps[gaps > tolerance]
    if big.size == 0:
        # Every coordinate coincides within the absolute tolerance.
        return np.array([float(np.mean(sorted_vals))]), np.zeros(vals.size, dtype=int)
    large = big[big >= 0.5 * float(big.max())]
    spacing = float(np.median(large))
    # Two samples of the same cell may each deviate up to the regularity limit
    # used by ``_grid_from_regular_coordinates`` (spacing * 1e-3), so a
    # within-cell gap can reach 2 * spacing * 1e-3.  The 2.5e-3 factor covers
    # that worst case with margin while remaining ~400x smaller than the
    # smallest legitimate between-cell gap (~spacing * (1 - 2e-3)), so two
    # genuinely distinct lattice positions can never be merged.
    cluster_tol = max(float(tolerance), spacing * 2.5e-3)
    is_new = np.concatenate(([True], gaps > cluster_tol))
    labels_sorted = np.cumsum(is_new) - 1
    labels = np.empty(vals.size, dtype=int)
    labels[order] = labels_sorted
    counts = np.bincount(labels_sorted)
    sums = np.bincount(labels_sorted, weights=sorted_vals)
    # For clusters whose members are exactly identical (the common no-jitter
    # case, including exact duplicate samples), keep the exact coordinate
    # rather than the float-rounded mean so that exact lattices reconstruct
    # bit-identically to plain ``np.unique``.  Only genuinely jittered
    # clusters get the mean estimate.
    starts = np.flatnonzero(is_new)
    seg_min = np.minimum.reduceat(sorted_vals, starts)
    seg_max = np.maximum.reduceat(sorted_vals, starts)
    centers = np.where(seg_min == seg_max, seg_min, sums / counts)
    return centers, labels


def _grid_from_regular_coordinates(scan: ScanData, tolerance: float = 1e-6) -> Grid2D | None:
    """Use native x/y coordinates when the export already forms a regular lattice.

    Axis coordinates are clustered with :func:`cluster_axis_coordinates` so that
    small coordinate jitter (floating-point noise, re-export rounding) does not
    explode the lattice into one column/row per sample and falsely report the
    scan as incomplete.
    """
    x = np.asarray(scan.x, dtype=float)
    y = np.asarray(scan.y, dtype=float)
    valid_xy = np.isfinite(x) & np.isfinite(y)
    valid_idx = np.flatnonzero(valid_xy)
    if valid_idx.size < 4:
        return None
    ux, ix = cluster_axis_coordinates(x[valid_xy], tolerance)
    uy, iy = cluster_axis_coordinates(y[valid_xy], tolerance)
    if ux.size < 2 and uy.size < 2:
        return None
    flat = iy * ux.size + ix
    total = ux.size * uy.size
    counts: np.ndarray[Any, Any] = np.bincount(flat, minlength=total)
    expected = ux.size * uy.size
    # v0.4.2 (audit F-17 remainder): coverage counts DISTINCT occupied
    # lattice cells, not samples. Duplicate samples used to push the ratio
    # above 1.0 (measured 1.111), masking holes left by missing lines.
    # Occupied-cell coverage is bounded by 1.0 by construction.
    coverage = float(np.count_nonzero(counts)) / max(expected, 1)
    if coverage < 0.90 or expected > max(4 * len(scan), 0):
        return None

    def regular_axis(values: np.ndarray[Any, Any]) -> bool:
        # v0.4.2 (audit F-15): gaps may skip whole lines/columns (integer
        # multiples of the step) without the lattice becoming irregular. A
        # 23/24-line survey used to fall back to a 60x60 scatter grid that
        # was 85% empty; now it stays a regular lattice with the sampled
        # rows. Non-integer gaps (re-walked offset lines) still reject.
        # Tolerance is two-tiered: the nominal step keeps the documented
        # 1e-3 regularity boundary (pinned by the jitter suite), while
        # skipped steps (multiple >= 2) allow up to 2.5e-3 -- the worst case
        # for two independently jittered endpoints -- so a missing line is
        # never confused with jitter, nor jitter with a missing line.
        if values.size <= 1:
            return True
        diffs = np.diff(values)
        if diffs.size == 0 or not np.all(diffs > tolerance):
            return False
        median = float(np.median(diffs))
        if not median > tolerance:
            return False
        for gap in diffs:
            multiple = round(float(gap) / median)
            if multiple < 1:
                return False
            step_tol = (
                max(float(tolerance), abs(median) * 1e-3) if multiple == 1 else abs(median) * 2.5e-3
            )
            if abs(float(gap) - multiple * median) > step_tol:
                return False
        return True

    if not regular_axis(ux) or not regular_axis(uy):
        return None
    counts = counts.reshape(uy.size, ux.size)
    sig = np.asarray(scan.signal, dtype=float)[valid_xy]
    dep = np.asarray(scan.z, dtype=float)[valid_xy]
    sig_sum = np.bincount(flat, weights=np.nan_to_num(sig, nan=0.0), minlength=total).reshape(
        uy.size, ux.size
    )
    sig_n = np.bincount(flat, weights=np.isfinite(sig).astype(float), minlength=total).reshape(
        uy.size, ux.size
    )
    dep_sum = np.bincount(flat, weights=np.nan_to_num(dep, nan=0.0), minlength=total).reshape(
        uy.size, ux.size
    )
    dep_n = np.bincount(flat, weights=np.isfinite(dep).astype(float), minlength=total).reshape(
        uy.size, ux.size
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        signal = sig_sum / np.maximum(sig_n, 1.0)
        depth = dep_sum / np.maximum(dep_n, 1.0)
    signal[sig_n == 0] = np.nan
    depth[dep_n == 0] = np.nan
    return Grid2D(x_centers=ux, y_centers=uy, signal=signal, depth=depth, counts=counts.astype(int))


def _grid_from_scatter(scan: ScanData, target_cells: int) -> Grid2D:
    # v0.5.1: guard the all-NaN path — np.nanmin raises on empty/all-NaN
    # input, unlike _grid_from_regular which returns None. Raise a domain
    # ValueError so the CLI maps it to exit 1 (not a crash traceback).
    x = np.asarray(scan.x, dtype=float)
    y = np.asarray(scan.y, dtype=float)
    if not np.any(np.isfinite(x)) or not np.any(np.isfinite(y)):
        raise ValueError("Cannot reconstruct grid: x/y coordinates are all-NaN or missing.")
    x_edges = np.linspace(np.nanmin(x), np.nanmax(x), target_cells + 1)
    y_edges = np.linspace(np.nanmin(y), np.nanmax(y), target_cells + 1)
    x_centers = (x_edges[:-1] + x_edges[1:]) / 2
    y_centers = (y_edges[:-1] + y_edges[1:]) / 2
    nx, ny = x_centers.size, y_centers.size
    # NaN coordinates have no cell: digitize(NaN) clips to the last cell and
    # would inflate its counts while contributing zero signal weight. Drop
    # non-finite samples explicitly (mirrors the regular-lattice valid_xy).
    raw_x = np.asarray(scan.x, dtype=float)
    raw_y = np.asarray(scan.y, dtype=float)
    finite_xy = np.isfinite(raw_x) & np.isfinite(raw_y)
    ix = np.clip(np.digitize(raw_x[finite_xy], x_edges) - 1, 0, nx - 1)
    iy = np.clip(np.digitize(raw_y[finite_xy], y_edges) - 1, 0, ny - 1)
    flat = iy * nx + ix
    total = nx * ny
    signal_values = np.asarray(scan.signal, dtype=float)[finite_xy]
    depth_values = np.asarray(scan.z, dtype=float)[finite_xy]
    counts = np.bincount(flat, minlength=total).reshape(ny, nx)
    sig_sum = np.bincount(
        flat, weights=np.nan_to_num(signal_values, nan=0.0), minlength=total
    ).reshape(ny, nx)
    sig_n = np.bincount(
        flat, weights=np.isfinite(signal_values).astype(float), minlength=total
    ).reshape(ny, nx)
    dep_sum = np.bincount(
        flat, weights=np.nan_to_num(depth_values, nan=0.0), minlength=total
    ).reshape(ny, nx)
    dep_n = np.bincount(
        flat, weights=np.isfinite(depth_values).astype(float), minlength=total
    ).reshape(ny, nx)
    with np.errstate(invalid="ignore", divide="ignore"):
        signal = sig_sum / np.maximum(sig_n, 1.0)
        depth = dep_sum / np.maximum(dep_n, 1.0)
    signal[sig_n == 0] = np.nan
    depth[dep_n == 0] = np.nan
    return Grid2D(
        x_centers=x_centers,
        y_centers=y_centers,
        signal=signal,
        depth=depth,
        counts=counts.astype(int),
    )

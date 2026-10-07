"""Robust geometric and depth descriptors for anomaly components."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull

from .._util import axis_spacing, safe_mean
from ..models import Candidate
from .anomaly import AnomalyMap, ArtifactMap
from .grid import Grid2D
from .morphology import morphology_metrics

_MIN_POINTS_FOR_ORIENTATION = 4


#: Relative slack when a ratio lands just above 1.0. The union of the cells is a
#: subset of its own convex hull, so ``solidity <= 1`` is a theorem, not an
#: empirical observation; a convex cell set must therefore come out at exactly
#: 1.0. This absorbs the round-off that could push it a few ulps over.
#: 1e-9 is ~7 orders above the observed round-off and ~7 orders below any real
#: geometric difference.
_SOLIDITY_FP_TOLERANCE = 1e-9


def _convex_hull_solidity(
    x_coords: np.ndarray[Any, Any],
    y_coords: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
) -> float:
    """Solidity of a cell set: occupied cell area / convex-hull area of the cells.

    ```
    A_object = n_cells * cell_dx * cell_dy
    A_hull   = area(ConvexHull(union of the 4N cell corners))
    solidity = clip(A_object / A_hull, 0, 1)
    ```

    The hull is over the **cell regions**, not the cell centres, and that is the
    whole of S02. The previous denominator was the hull of the N centres while
    the numerator was a cell *count* -- a count over an area, whose units are
    1/area. A quantity with units cannot be a shape ratio, and it behaved like
    one: it collapsed to 0.02 for a 6-cell L at a pitch of 10 and to 3e-6 at
    1000. It is dimensionless now, and that is a property, not a coincidence.

    The denominator is computed from the centre hull by an identity rather than
    from 4N corners, which keeps the cost identical to the old call and the
    arithmetic better conditioned. For a cell set whose cells are all translates
    of the same rectangle ``R = [-dx/2, dx/2] x [-dy/2, dy/2]``:

    ```
    ConvexHull(union of cells) = ConvexHull(centres) (+) R
    ```

    because both sides have the same support function in every direction --
    ``max_i <c_i, u> + h_R(u) = h_C(u) + h_R(u)`` -- and a convex body is
    determined by its support function. For a convex polygon ``P`` and an
    axis-aligned ``R``, ``area(P (+) R) = area(P) + dx*H + dy*W + dx*dy`` where
    ``W`` and ``H`` are the width and height of ``P``'s bounding box (each
    bounding-box edge sweeps one full cell width/height). So:

    ```
    A_hull = hull_area(centres) + cell_dx * span_y + cell_dy * span_x + cell_dx * cell_dy
    ```

    The payoff is that **there is no degenerate branch any more**. Collinear
    centres used to raise ``QhullError`` and be reported as ``solidity = 1.0``,
    which conflated two opposite facts: a straight line of *adjacent* cells is a
    rectangle and genuinely solid, while a *diagonal* run (one component under
    the default 8-connectivity) is not a rectangle at all -- 3 such cells have
    solidity 3/5, not 1. A collinear centre hull has area exactly zero and now
    contributes exactly zero, which is the truth in both cases.

    The result is defined for every non-empty cell set, is invariant under
    translation and under uniform rescaling, and does not depend on the pitch
    (``dx != dy`` included). The independent oracle
    ``validation.solidity_reference`` derives the same quantity from the cell
    geometry by an unrelated algorithm; the two are pinned against each other
    and against a hand-derived rational table in
    ``tests/unit/test_solidity_reference.py``.

    Non-finite coordinates or a non-positive pitch leave the geometry
    unintegrable. That is unreachable from a real grid (a cell with a NaN centre
    has no signal, so it cannot be in the anomaly mask) and the legacy value of
    1.0 is preserved rather than changing a public contract -- but it is a
    *fallback*, not a measurement, and the test that says so is named.
    """
    n_cells = int(x_coords.size)
    if n_cells == 0:
        return 1.0
    dx = float(cell_dx)
    dy = float(cell_dy)
    finite = np.all(np.isfinite(x_coords)) and np.all(np.isfinite(y_coords))
    if not finite or not (dx > 0.0 and dy > 0.0) or dx == float("inf") or dy == float("inf"):
        import logging as _logging

        _logging.getLogger(__name__).debug(
            "Solidity is unmeasurable for a non-finite or zero-extent grid; using 1.0"
        )
        return 1.0

    span_x = float(np.max(x_coords) - np.min(x_coords))
    span_y = float(np.max(y_coords) - np.min(y_coords))
    if n_cells < 3:
        # Fewer than three centres cannot span an area: the hull is a segment or
        # a point, and its area is exactly zero.
        hull_area = 0.0
    else:
        # Hull in a frame anchored at the component's own minimum corner. The
        # shoelace that qhull evaluates is a difference of products, so on
        # absolute coordinates the significant digits of a ~1-cell hull are
        # cancelled by coordinates of survey magnitude: measured 1.6e-12
        # relative error on a 4-cell L placed at x0 = 1e5 m, against 1e-16 in a
        # local frame. `x - min(x)` is exact (Sterbenz) wherever the component
        # spans less than a factor of two of its own minimum, which is the
        # normal case, and the shift costs one subtraction per axis.
        points = np.column_stack([x_coords - np.min(x_coords), y_coords - np.min(y_coords)])
        try:
            hull_area = float(ConvexHull(points).volume)
        except Exception as exc:  # collinear centres: hull area is exactly 0
            import logging as _logging

            _logging.getLogger(__name__).debug("ConvexHull(centres) is degenerate: %s", exc)
            hull_area = 0.0
    # Every cell is the centre-hull translated and grown by one cell, so the
    # hull of the cell regions is the centre hull swept by the cell rectangle.
    hull_area = hull_area + dx * span_y + dy * span_x + dx * dy
    solidity = (n_cells * dx * dy) / hull_area
    if solidity > 1.0:
        if solidity - 1.0 > _SOLIDITY_FP_TOLERANCE:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Solidity %.17g exceeds 1 by more than %g; the cell union is a subset of its "
                "own convex hull, so this indicates a defect. Clipping.",
                solidity,
                _SOLIDITY_FP_TOLERANCE,
            )
        return 1.0
    return float(solidity)


def _principal_extents(
    x_coords: np.ndarray[Any, Any],
    y_coords: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
) -> tuple[float, float, float, float]:
    if len(x_coords) < _MIN_POINTS_FOR_ORIENTATION:
        width = float(np.nanmax(x_coords) - np.nanmin(x_coords) + cell_dx)
        height = float(np.nanmax(y_coords) - np.nanmin(y_coords) + cell_dy)
        major, minor = max(width, height), min(width, height)
        return major, minor, float("nan"), major / max(minor, 1e-9)

    coords = np.column_stack([x_coords - np.mean(x_coords), y_coords - np.mean(y_coords)])
    cov = np.cov(coords, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = np.maximum(eigvals[order], 0.0)
    major_vec = eigvecs[:, order[0]]
    orientation_deg = float(np.degrees(np.arctan2(major_vec[1], major_vec[0])) % 180)
    projections = coords @ eigvecs[:, order]
    major = float(np.max(projections[:, 0]) - np.min(projections[:, 0]) + max(cell_dx, cell_dy))
    minor = float(np.max(projections[:, 1]) - np.min(projections[:, 1]) + min(cell_dx, cell_dy))
    ratio = math.sqrt((eigvals[0] + 1e-9) / (eigvals[1] + 1e-9))
    return max(major, 1e-9), max(minor, 1e-9), orientation_deg, max(ratio, 1.0)


def _classify_shape(
    x_coords: np.ndarray[Any, Any],
    y_coords: np.ndarray[Any, Any],
    major_extent: float,
    minor_extent: float,
    boundary_contact_ratio: float,
    broadness_score: float,
    solidity: float,
) -> tuple[str, float, float, float]:
    n = len(x_coords)
    major_over_minor = major_extent / max(minor_extent, 1e-9)
    linearity_score = float(np.clip(1.0 - minor_extent / max(major_extent, 1e-9), 0.0, 1.0))
    if n <= 2:
        return "point", float("nan"), major_over_minor, linearity_score

    _, _, orientation_deg, eig_ratio = _principal_extents(
        x_coords,
        y_coords,
        cell_dx=max(
            np.nanmedian(np.diff(np.unique(x_coords))) if len(np.unique(x_coords)) > 1 else 1.0,
            1e-9,
        ),
        cell_dy=max(
            np.nanmedian(np.diff(np.unique(y_coords))) if len(np.unique(y_coords)) > 1 else 1.0,
            1e-9,
        ),
    )
    if boundary_contact_ratio >= 0.45 and n >= 4:
        shape_class = "boundary-like"
    elif (eig_ratio >= 5.0 or major_over_minor >= 4.0) and linearity_score >= 0.70:
        shape_class = "linear"
    elif eig_ratio >= 2.0 or major_over_minor >= 1.8:
        shape_class = "elongated"
    elif broadness_score >= 0.55:
        shape_class = "broad"
    elif solidity < 0.48 and linearity_score < 0.70:
        shape_class = "irregular"
    else:
        shape_class = "compact"
    return shape_class, orientation_deg, major_over_minor, linearity_score


def _line_footprint(length: int, angle_deg: float) -> np.ndarray[Any, Any]:
    length = max(3, int(length))
    if length % 2 == 0:
        length += 1
    half = length // 2
    radius = half + 1
    footprint = np.zeros((2 * radius + 1, 2 * radius + 1), dtype=bool)
    center = radius
    theta = np.radians(float(angle_deg))
    for t in np.linspace(-half, half, length):
        rr = int(round(center + t * np.sin(theta)))
        cc = int(round(center + t * np.cos(theta)))
        if 0 <= rr < footprint.shape[0] and 0 <= cc < footprint.shape[1]:
            footprint[rr, cc] = True
    # Give the line a little tolerance for rasterized diagonal tracks.
    if abs(np.sin(theta)) > 0.25 and abs(np.cos(theta)) > 0.25:
        footprint = ndimage.binary_dilation(footprint, structure=np.ones((2, 2), dtype=bool))
    return footprint


def _line_support_metrics(
    local_mask: np.ndarray[Any, Any], major_extent: float, min_extent: float
) -> tuple[float, float]:
    if local_mask.size == 0 or not np.any(local_mask):
        return 0.0, float("nan")
    candidate_lengths = [5, 7, 9, 13]
    max_allowed = max(3, int(round(max(major_extent, min_extent))))
    candidate_lengths = [length for length in candidate_lengths if length <= max_allowed + 2]
    if not candidate_lengths:
        candidate_lengths = [5]
    best_score = 0.0
    best_angle = float("nan")
    for length in candidate_lengths:
        for angle in (0.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0):
            fp = _line_footprint(length, angle)
            response = ndimage.convolve(
                local_mask.astype(float), fp.astype(float), mode="constant", cval=0.0
            ) / max(float(fp.sum()), 1.0)
            score = float(np.max(response))
            if score > best_score:
                best_score = score
                best_angle = angle
    # Normalize for short components so a small blob does not look linear merely
    # because a short raster line happens to fit through it.
    scale_penalty = np.clip((major_extent - min_extent) / max(major_extent, 1e-9), 0.0, 1.0)
    best_score *= 0.65 + 0.35 * scale_penalty
    return float(np.clip(best_score, 0.0, 1.0)), best_angle


def _axial_signal_continuity(
    x_coords: np.ndarray[Any, Any],
    y_coords: np.ndarray[Any, Any],
    z_vals: np.ndarray[Any, Any],
    minor_extent: float,
) -> float:
    """Measure how continuously strong the response occupies the major axis.

    A flat/continuous linear response tends to support most axial bins, while an
    isolated elliptical/compact response decays toward its ends. This is a shape
    descriptor, not proof of a tunnel.
    """
    if len(x_coords) < 5:
        return 0.0
    points = np.column_stack([x_coords, y_coords]).astype(float)
    center = np.mean(points, axis=0)
    try:
        cov = np.cov((points - center), rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(cov)
        axis = eigvecs[:, int(np.argmax(eigvals))]
    except Exception:
        return 0.0
    projection = (points - center) @ axis
    lo, hi = float(np.min(projection)), float(np.max(projection))
    span = hi - lo
    if span <= 1e-9:
        return 0.0
    bins = max(4, min(32, int(round(span / max(float(minor_extent), 1e-9)))))
    edges = np.linspace(lo, hi, bins + 1)
    bin_index = np.clip(np.digitize(projection, edges[1:-1], right=False), 0, bins - 1)
    abs_z = np.abs(np.asarray(z_vals, dtype=float))
    finite = np.isfinite(abs_z)
    if not np.any(finite):
        return 0.0
    peak = float(np.max(abs_z[finite]))
    if peak <= 1e-9:
        return 0.0
    occupied: list[float] = []
    for bin_id in range(bins):
        values = abs_z[(bin_index == bin_id) & finite]
        occupied.append(float(np.max(values)) if values.size else 0.0)
    strong_fraction = float(np.mean(np.asarray(occupied) >= 0.55 * peak))
    return float(np.clip(strong_fraction, 0.0, 1.0))


def _shape_metrics(
    grid: Grid2D,
    xs: np.ndarray[Any, Any],
    ys: np.ndarray[Any, Any],
    local_mask: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
) -> dict[str, float]:
    x_coords = grid.x_centers[xs]
    y_coords = grid.y_centers[ys]
    width = float(np.nanmax(x_coords) - np.nanmin(x_coords) + cell_dx)
    height = float(np.nanmax(y_coords) - np.nanmin(y_coords) + cell_dy)
    aspect_ratio = max(width, height) / max(min(width, height), 1e-9)
    area_cells = float(len(xs))
    grid_area_cells = float(np.count_nonzero(np.isfinite(grid.signal)))
    bbox_area = float(local_mask.size)
    bbox_fraction = bbox_area / max(grid.signal.size, 1)
    area_fraction = area_cells / max(grid_area_cells, 1.0)
    broadness_score = float(
        np.clip(
            0.65 * min(bbox_fraction / 0.20, 1.0) + 0.35 * min(area_fraction / 0.12, 1.0), 0.0, 1.0
        )
    )
    # Stage 2 (S12): the full-grid ``edge_distance`` was built once per component
    # and then read at only that component's own cells. The arithmetic is
    # identical -- the same integer min over the same *global* row/column indices
    # -- so the extracted values are bit-identical (verified by
    # ``test_local_edge_distance_matches_full_grid``); only the allocation is
    # removed. Measured: 43.9% of ``_shape_metrics`` at a 300x300 grid, and the
    # share grows as components multiply on a fixed grid (4.9% -> 32.9% going
    # from 5 to 83 components), because the cost was per-component rather than
    # per-cell. No numerical behaviour changes.
    #
    # NOTE: these must not be named `width`/`height` -- those locals already hold
    # this component's physical extent above and are what the returned metric
    # dict reports. Shadowing them here silently replaced the candidate's width
    # and height with the grid's row/column counts.
    grid_rows, grid_cols = grid.signal.shape
    edge_distance = np.minimum.reduce([ys, xs, grid_rows - 1 - ys, grid_cols - 1 - xs])
    boundary_contact_ratio = float(np.mean(edge_distance <= 1))
    eroded = ndimage.binary_erosion(local_mask)
    perimeter = float(np.sum(local_mask & ~eroded))
    from .._util import digital_compactness

    compactness = digital_compactness(area_cells, perimeter)
    solidity = _convex_hull_solidity(x_coords, y_coords, cell_dx, cell_dy)
    major_extent, minor_extent, orientation_deg, _ = _principal_extents(
        x_coords, y_coords, cell_dx, cell_dy
    )
    elongation_ratio = major_extent / max(minor_extent, 1e-9)
    linearity_score = float(np.clip(1.0 - minor_extent / max(major_extent, 1e-9), 0.0, 1.0))
    geometry_quality = float(
        np.clip(
            0.30 * min(len(xs) / 10.0, 1.0)
            + 0.25 * min(np.count_nonzero(local_mask) / max(local_mask.size, 1), 1.0)
            + 0.25 * solidity
            + 0.20 * (1.0 - min(boundary_contact_ratio, 1.0)),
            0.0,
            1.0,
        )
    )
    line_support_score, line_support_orientation_deg = _line_support_metrics(
        local_mask, major_extent, minor_extent
    )
    return {
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "major_extent": major_extent,
        "minor_extent": minor_extent,
        "elongation_ratio": elongation_ratio,
        "linearity_score": linearity_score,
        "orientation_deg": orientation_deg,
        "compactness": compactness,
        "solidity": solidity,
        "boundary_contact_ratio": boundary_contact_ratio,
        "broadness_score": broadness_score,
        "geometry_quality": geometry_quality,
        "line_support_score": line_support_score,
        "line_support_orientation_deg": line_support_orientation_deg,
    }


def extract_candidates(
    grid: Grid2D,
    anomaly: AnomalyMap,
    artifacts: ArtifactMap | None = None,
    auxiliary_depth: np.ndarray[Any, Any] | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    dx = axis_spacing(grid.x_centers)
    dy = axis_spacing(grid.y_centers)

    for comp_id in range(1, anomaly.n_components + 1):
        ys, xs = np.where(anomaly.labels == comp_id)
        if len(xs) == 0:
            continue
        x_coords = grid.x_centers[xs]
        y_coords = grid.y_centers[ys]
        signal_vals = grid.signal[ys, xs]
        depth_vals = grid.depth[ys, xs]
        z_vals = anomaly.zscore[ys, xs]
        persistence_vals = anomaly.persistence[ys, xs]
        bbox = (slice(int(ys.min()), int(ys.max()) + 1), slice(int(xs.min()), int(xs.max()) + 1))
        local_mask = anomaly.labels[bbox] == comp_id
        metrics = _shape_metrics(grid, xs, ys, local_mask, dx, dy)
        morphology = morphology_metrics(
            x_coords,
            y_coords,
            z_vals,
            major_extent=metrics["major_extent"],
            minor_extent=metrics["minor_extent"],
            linearity_score=metrics["linearity_score"],
            line_support_score=metrics["line_support_score"],
        )
        shape_class, shape_orientation, _, _ = _classify_shape(
            x_coords,
            y_coords,
            metrics["major_extent"],
            metrics["minor_extent"],
            metrics["boundary_contact_ratio"],
            metrics["broadness_score"],
            metrics["solidity"],
        )
        orientation_deg = (
            metrics["orientation_deg"]
            if np.isfinite(metrics["orientation_deg"])
            else shape_orientation
        )

        positive_peak = float(np.nanmax(z_vals))
        negative_peak = float(np.nanmin(z_vals))
        signed_mean = float(np.nanmean(z_vals))
        pos_mass = float(np.sum(np.clip(z_vals, 0.0, None)))
        neg_mass = float(np.sum(np.clip(-z_vals, 0.0, None)))
        polarity = (
            "positive"
            if pos_mass > neg_mass * 1.25
            else "negative"
            if neg_mass > pos_mass * 1.25
            else "mixed"
        )
        anomaly_density = float(len(xs) / max(local_mask.size, 1))
        artifact_score = (
            float(np.nanmean(artifacts.score[ys, xs])) if artifacts is not None else 0.0
        )
        rows = np.unique(ys)
        cols = np.unique(xs)
        row_cont = len(rows) / max(int(ys.max() - ys.min() + 1), 1)
        col_cont = len(cols) / max(int(xs.max() - xs.min() + 1), 1)
        continuity_score = float(max(row_cont, col_cont))

        finite_depth_mask = np.isfinite(depth_vals)
        depth_valid = depth_vals[finite_depth_mask]
        persistence_valid = persistence_vals[np.isfinite(persistence_vals)]
        depth_valid_fraction = float(len(depth_valid) / max(len(depth_vals), 1))
        if depth_valid.size:
            depth_min = float(np.min(depth_valid))
            depth_max = float(np.max(depth_valid))
            depth_mean = float(np.mean(depth_valid))
            depth_std = float(np.std(depth_valid))
            depth_range = depth_max - depth_min
            # v0.2.6: emphasize the anomaly core when fusing depth. A component
            # often includes transition/background cells; a quadratic contrast
            # weight prevents those cells from dominating the depth estimate.
            depth_contrast = np.maximum(np.abs(z_vals[finite_depth_mask]) - anomaly.threshold, 0.0)
            depth_weights = np.square(depth_contrast)
            if np.sum(depth_weights) <= 1e-9:
                depth_weights = np.abs(z_vals[finite_depth_mask])
            if np.sum(depth_weights) > 1e-9:
                depth_estimate = float(np.sum(depth_valid * depth_weights) / np.sum(depth_weights))
                depth_estimate_std = float(
                    np.sqrt(
                        np.sum(depth_weights * (depth_valid - depth_estimate) ** 2)
                        / np.sum(depth_weights)
                    )
                )
            else:
                depth_estimate = depth_mean
                depth_estimate_std = depth_std
            depth_relative_dispersion = depth_std / max(abs(depth_mean), 1e-9)
            depth_stability_score = float(np.clip(1.0 - depth_relative_dispersion / 0.5, 0.0, 1.0))
        else:
            depth_min = depth_max = depth_mean = depth_std = depth_range = float("nan")
            depth_estimate = depth_estimate_std = depth_relative_dispersion = float("nan")
            depth_stability_score = 0.0

        if auxiliary_depth is not None and np.asarray(auxiliary_depth).shape != grid.signal.shape:
            raise ValueError("auxiliary_depth must have the same 2D shape as grid.signal")
        aux_depth_vals = (
            np.asarray(auxiliary_depth, dtype=float)[ys, xs]
            if auxiliary_depth is not None
            else np.array([], dtype=float)
        )
        aux_valid = np.isfinite(aux_depth_vals)
        if np.any(aux_valid):
            aux_v = aux_depth_vals[aux_valid]
            aux_mean = float(np.mean(aux_v))
            aux_std = float(np.std(aux_v))
            aux_min = float(np.min(aux_v))
            aux_max = float(np.max(aux_v))
            aux_valid_fraction = float(np.mean(aux_valid))
            aux_delta = (
                float(aux_mean - depth_estimate) if np.isfinite(depth_estimate) else float("nan")
            )
            aux_status = "available"
        else:
            aux_mean = aux_std = aux_min = aux_max = aux_delta = float("nan")
            aux_valid_fraction = 0.0
            aux_status = "unavailable"

        abs_signal = np.abs(z_vals)
        weight_sum = float(np.nansum(abs_signal))
        if weight_sum > 1e-9:
            centroid_weighted_x = float(np.nansum(x_coords * abs_signal) / weight_sum)
            centroid_weighted_y = float(np.nansum(y_coords * abs_signal) / weight_sum)
        else:
            centroid_weighted_x = float(np.mean(x_coords))
            centroid_weighted_y = float(np.mean(y_coords))

        scale_class = getattr(anomaly, "component_types", {}).get(comp_id, "local")
        candidates.append(
            Candidate(
                id=comp_id,
                x_center=float(np.mean(x_coords)),
                y_center=float(np.mean(y_coords)),
                depth_mean=depth_mean,
                depth_std=depth_std,
                n_points=int(len(xs)),
                area_cells=int(len(xs)),
                width=float(metrics["width"]),
                height=float(metrics["height"]),
                aspect_ratio=float(metrics["aspect_ratio"]),
                orientation_deg=float(orientation_deg),
                peak_signal=float(np.nanmax(signal_vals)),
                mean_signal=float(np.nanmean(signal_vals)),
                anomaly_score=float(np.nanmax(np.abs(z_vals))),
                shape_class=shape_class,
                pattern_hypothesis="unclassified",
                confidence=0.0,
                notes="",
                signed_anomaly_mean=signed_mean,
                positive_peak=positive_peak,
                negative_peak=negative_peak,
                polarity=polarity,
                anomaly_density=anomaly_density,
                compactness=float(metrics["compactness"]),
                continuity_score=continuity_score,
                artifact_score=artifact_score,
                multiscale_persistence=safe_mean(persistence_valid, 0.0),
                major_extent=float(metrics["major_extent"]),
                minor_extent=float(metrics["minor_extent"]),
                elongation_ratio=float(metrics["elongation_ratio"]),
                linearity_score=float(metrics["linearity_score"]),
                solidity=float(metrics["solidity"]),
                boundary_contact_ratio=float(metrics["boundary_contact_ratio"]),
                broadness_score=float(metrics["broadness_score"]),
                centroid_weighted_x=centroid_weighted_x,
                centroid_weighted_y=centroid_weighted_y,
                geometry_quality=float(metrics["geometry_quality"]),
                depth_estimate=depth_estimate,
                depth_estimate_std=depth_estimate_std,
                depth_min=depth_min,
                depth_max=depth_max,
                depth_range=depth_range,
                depth_valid_fraction=depth_valid_fraction,
                depth_stability_score=depth_stability_score,
                depth_relative_dispersion=depth_relative_dispersion,
                scale_class=scale_class,
                line_support_score=float(metrics["line_support_score"]),
                line_support_orientation_deg=float(metrics["line_support_orientation_deg"]),
                regional_support_score=float(
                    metrics["broadness_score"] if scale_class == "broad" else 0.0
                ),
                axial_signal_continuity_score=float(
                    _axial_signal_continuity(x_coords, y_coords, z_vals, metrics["minor_extent"])
                ),
                width_consistency_score=float(morphology["width_consistency_score"]),
                orientation_stability_score=float(morphology["orientation_stability_score"]),
                morphology_line_coherence_score=float(
                    morphology["morphology_line_coherence_score"]
                ),
                morphology_axial_coverage_score=float(
                    morphology["morphology_axial_coverage_score"]
                ),
                soil_twt_depth_estimate=aux_mean,
                soil_twt_depth_std=aux_std,
                soil_twt_depth_min=aux_min,
                soil_twt_depth_max=aux_max,
                soil_twt_depth_valid_fraction=aux_valid_fraction,
                soil_depth_delta_m=aux_delta,
                soil_depth_channel_status=aux_status,
            )
        )
        if scale_class == "broad":
            candidates[-1].notes = "broad-scale channel contributed"
    return candidates

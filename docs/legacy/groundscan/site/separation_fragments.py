"""Fragment descriptor helpers for target separation (split from separation.py).

Recomputes a fragment's descriptors from its own assigned cells using the same
formulas as core.shape.extract_candidates. No import from separation.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage


def _fragment_stats(
    mask: np.ndarray[Any, Any],
    grid_x: np.ndarray[Any, Any],
    grid_y: np.ndarray[Any, Any],
    rr: np.ndarray[Any, Any],
    cc: np.ndarray[Any, Any],
) -> dict[str, float]:
    if len(rr) == 0:
        return {}
    from .._util import digital_compactness

    xs = grid_x[cc]
    ys = grid_y[rr]
    # Calibrated convention (see ADR on fragment extents): Voronoi-assigned
    # response spans WITHOUT the +1-cell-pitch bounding-box convention used
    # by core.shape.extract_candidates for whole objects. A +pitch trial was
    # measured to cascade through line-support → linear-metal refinement →
    # the dipole-merge guard, unmerging a calibrated vendor dipole (Iron
    # Treasure 9/9 gate). Downstream morphology thresholds are tuned on this
    # convention; unifying it requires threshold recalibration on field
    # data, not a silent geometry change. Singleton spans stay 0.0.
    width = float(np.nanmax(xs) - np.nanmin(xs)) if len(xs) > 1 else 0.0
    height = float(np.nanmax(ys) - np.nanmin(ys)) if len(ys) > 1 else 0.0
    major = max(width, height)
    minor = max(min(width, height), 1e-9)
    aspect = max(major, 1e-9) / minor
    area = float(len(rr))
    eroded = ndimage.binary_erosion(mask)
    perimeter = float(np.count_nonzero(mask & ~eroded))
    compactness = digital_compactness(area, perimeter)
    return {
        "width": width,
        "height": height,
        "major_extent": major,
        "minor_extent": minor,
        "aspect_ratio": aspect,
        "elongation_ratio": major / minor,
        "compactness": compactness,
        "area_cells": area,
        "n_points": area,
    }


def _fragment_full_descriptors(
    *,
    mask: np.ndarray[Any, Any],
    frag_rr: np.ndarray[Any, Any],
    frag_cc: np.ndarray[Any, Any],
    local_x_axis: np.ndarray[Any, Any],
    local_y_axis: np.ndarray[Any, Any],
    field_shape: tuple[int, int],
    signed_patch: np.ndarray[Any, Any],
    stats: dict[str, float],
    total_cells: int,
    row_offset: int,
    col_offset: int,
    depth_patch: np.ndarray[Any, Any] | None = None,
    persist_patch: np.ndarray[Any, Any] | None = None,
    artifact_patch: np.ndarray[Any, Any] | None = None,
    signal_patch: np.ndarray[Any, Any] | None = None,
    anomaly_threshold: float = 2.0,
) -> dict[str, Any]:
    """Recompute a fragment's descriptors from its own assigned cells.

    A decomposed fragment must describe the response where it actually is, not
    inherit the parent's whole-object statistics. Copying the parent's
    ``anomaly_score`` / ``shape_class`` / ``depth`` / ``persistence`` /
    ``artifact`` / ``continuity`` onto every lobe lets one iron dipole read as
    "metal + independent cavity" (observed on real Rover data). Every value
    below uses the same formulas as ``analysis.shape.extract_candidates``,
    applied to this fragment's mask. Optional channels (depth, persistence,
    artifact, raw signal) are only used when supplied on the same grid as the
    consensus/support field; otherwise those keys are omitted and the caller
    keeps the inherited values.
    """
    from ..core.shape import (
        _axial_signal_continuity,
        _classify_shape,
        _convex_hull_solidity,
        _line_support_metrics,
    )

    out: dict[str, Any] = {}
    z_vals = np.asarray(signed_patch[frag_rr, frag_cc], dtype=float)
    finite_z = z_vals[np.isfinite(z_vals)]
    if finite_z.size:
        out["anomaly_score"] = float(np.max(np.abs(finite_z)))
        out["positive_peak"] = float(np.max(finite_z))
        out["negative_peak"] = float(np.min(finite_z))
        out["signed_anomaly_mean"] = float(np.mean(finite_z))
    else:
        out["anomaly_score"] = 0.0
        out["positive_peak"] = 0.0
        out["negative_peak"] = 0.0
        out["signed_anomaly_mean"] = 0.0
    # Line/region continuity of this fragment's own cells.
    row_cont = len(np.unique(frag_rr)) / max(int(np.max(frag_rr) - np.min(frag_rr) + 1), 1)
    col_cont = len(np.unique(frag_cc)) / max(int(np.max(frag_cc) - np.min(frag_cc) + 1), 1)
    out["continuity_score"] = float(max(row_cont, col_cont))
    bbox_area = float(
        max(
            (int(np.max(frag_rr) - np.min(frag_rr)) + 1)
            * (int(np.max(frag_cc) - np.min(frag_cc)) + 1),
            1,
        )
    )
    out["anomaly_density"] = float(len(frag_rr) / bbox_area)
    xs = np.asarray(local_x_axis[frag_cc], dtype=float)
    ys = np.asarray(local_y_axis[frag_rr], dtype=float)
    h, w = int(field_shape[0]), int(field_shape[1])
    gr = np.asarray(frag_rr, dtype=int) + int(row_offset)
    gc = np.asarray(frag_cc, dtype=int) + int(col_offset)
    edge = np.minimum.reduce([gr, gc, h - 1 - gr, w - 1 - gc]).astype(float)
    out["boundary_contact_ratio"] = float(np.mean(edge <= 1)) if len(gr) else 0.0
    bbox_fraction = bbox_area / max(h * w, 1)
    area_fraction = len(frag_rr) / max(int(total_cells), 1)
    broadness = float(
        np.clip(
            0.65 * min(bbox_fraction / 0.20, 1.0) + 0.35 * min(area_fraction / 0.12, 1.0), 0.0, 1.0
        )
    )
    out["broadness_score"] = broadness
    # Solidity is a dimensionless ratio of two areas (S02), so it needs the cell
    # pitch that `core.shape` takes from the grid axes. The same canonical
    # estimator, `axis_spacing`, is used on the same lattice the fragment's cells
    # index into, so a fragment and the whole object it came from are measured
    # on one footing. Before S02 this passed a cell *count* against a centre
    # hull, which is a count over an area and therefore not a ratio at all.
    from .._util import axis_spacing

    solidity = float(
        _convex_hull_solidity(
            xs,
            ys,
            axis_spacing(np.asarray(local_x_axis, dtype=float)),
            axis_spacing(np.asarray(local_y_axis, dtype=float)),
        )
    )
    out["solidity"] = solidity
    n = float(len(frag_rr))
    out["geometry_quality"] = float(
        np.clip(
            0.30 * min(n / 10.0, 1.0)
            + 0.25 * min(n / bbox_area, 1.0)
            + 0.25 * solidity
            + 0.20 * (1.0 - min(float(out["boundary_contact_ratio"]), 1.0)),
            0.0,
            1.0,
        )
    )
    shape_class, orientation_deg, _, _ = _classify_shape(
        xs,
        ys,
        float(stats["major_extent"]),
        float(stats["minor_extent"]),
        float(out["boundary_contact_ratio"]),
        broadness,
        solidity,
    )
    out["shape_class"] = shape_class
    out["orientation_deg"] = float(orientation_deg)
    try:
        lss, lso = _line_support_metrics(
            mask, float(stats["major_extent"]), float(stats["minor_extent"])
        )
    except (ValueError, TypeError, IndexError, ArithmeticError):
        lss, lso = 0.0, float("nan")
    out["line_support_score"] = float(lss)
    out["line_support_orientation_deg"] = float(lso)
    try:
        axial = _axial_signal_continuity(xs, ys, z_vals, float(stats["minor_extent"]))
    except (ValueError, TypeError, IndexError, ArithmeticError):
        axial = 0.0
    out["axial_signal_continuity_score"] = float(axial)
    if persist_patch is not None:
        try:
            pv = np.asarray(persist_patch[frag_rr, frag_cc], dtype=float)
            pv = pv[np.isfinite(pv)]
            out["multiscale_persistence"] = float(np.mean(pv)) if pv.size else 0.0
        except (IndexError, ValueError):
            pass
    if artifact_patch is not None:
        try:
            av = np.asarray(artifact_patch[frag_rr, frag_cc], dtype=float)
            av = av[np.isfinite(av)]
            out["artifact_score"] = float(np.mean(av)) if av.size else 0.0
        except (IndexError, ValueError):
            pass
    if signal_patch is not None:
        try:
            sv = np.asarray(signal_patch[frag_rr, frag_cc], dtype=float)
            sv = sv[np.isfinite(sv)]
            if sv.size:
                out["peak_signal"] = float(np.max(sv))
                out["mean_signal"] = float(np.mean(sv))
        except (IndexError, ValueError):
            pass
    if depth_patch is not None:
        try:
            dv = np.asarray(depth_patch[frag_rr, frag_cc], dtype=float)
            fin = np.isfinite(dv)
            out["depth_valid_fraction"] = float(np.count_nonzero(fin) / max(len(frag_rr), 1))
            valid = dv[fin]
            if valid.size:
                dmin = float(np.min(valid))
                dmax = float(np.max(valid))
                dmean = float(np.mean(valid))
                dstd = float(np.std(valid))
                contrast = np.maximum(np.abs(z_vals[fin]) - float(anomaly_threshold), 0.0)
                wgt = np.square(contrast)
                if float(np.sum(wgt)) <= 1e-9:
                    wgt = np.abs(z_vals[fin])
                if float(np.sum(wgt)) > 1e-9:
                    dest = float(np.sum(valid * wgt) / np.sum(wgt))
                    destd = float(np.sqrt(np.sum(wgt * (valid - dest) ** 2) / np.sum(wgt)))
                else:
                    dest, destd = dmean, dstd
                disp = dstd / max(abs(dmean), 1e-9)
                out.update(
                    depth_mean=dmean,
                    depth_std=dstd,
                    depth_min=dmin,
                    depth_max=dmax,
                    depth_range=float(dmax - dmin),
                    depth_estimate=dest,
                    depth_estimate_std=destd,
                    depth_relative_dispersion=float(disp),
                    depth_stability_score=float(np.clip(1.0 - disp / 0.5, 0.0, 1.0)),
                )
            else:
                nan = float("nan")
                out.update(
                    depth_mean=nan,
                    depth_std=nan,
                    depth_min=nan,
                    depth_max=nan,
                    depth_range=nan,
                    depth_estimate=nan,
                    depth_estimate_std=nan,
                    depth_relative_dispersion=nan,
                    depth_stability_score=0.0,
                )
        except (IndexError, ValueError):
            pass
    return out


__all__ = ["_fragment_stats", "_fragment_full_descriptors"]

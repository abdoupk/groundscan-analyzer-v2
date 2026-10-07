"""Generator-shift audit for broad/geological response representations, v0.2.86.

Diagnostic-only. Compares alternative low-frequency representations before the
existing broad-component selection logic. No production detector/classifier,
threshold, scoring, registration, or suppression behavior is changed.
"""

from __future__ import annotations

import json
from math import hypot
from pathlib import Path

import numpy as np
from scipy import ndimage

from groundscan.core.anomaly import (
    _broad_component_selection,
    _regional_trend_zscore,
)
from groundscan.core.background import robust_zscore
from groundscan.core.grid import reconstruct_grid
from groundscan.validation.synthetic_core.core import SyntheticScenario, generate_scan
from groundscan_research.synthetic_generator_independence import _generate, _master_plan

GENERATORS = ("A", "B", "C")
REPRESENTATIONS = (
    {"name": "regional_default", "kind": "regional", "sigma": None},
    {"name": "regional_sigma_1p2", "kind": "regional", "sigma": 1.2},
    {"name": "regional_sigma_2p5", "kind": "regional", "sigma": 2.5},
    {"name": "regional_sigma_4p0", "kind": "regional", "sigma": 4.0},
    {"name": "regional_sigma_6p0", "kind": "regional", "sigma": 6.0},
    {"name": "uniform_7_plane", "kind": "uniform", "size": 7},
    {"name": "uniform_11_plane", "kind": "uniform", "size": 11},
    {"name": "gaussian_raw_4", "kind": "raw_gaussian", "sigma": 4.0},
    {"name": "gaussian_raw_6", "kind": "raw_gaussian", "sigma": 6.0},
    {"name": "quadratic_sigma_4", "kind": "quadratic", "sigma": 4.0},
)

BROAD_THRESHOLD = 2.1
MIN_AREA_FRACTION = 0.02
MIN_SPAN_FRACTION = 0.18
MATCH_RADIUS_M = 3.0


def _fit_plane_residual(signal: np.ndarray) -> np.ndarray:
    valid = np.isfinite(signal)
    yy, xx = np.indices(signal.shape)
    if int(valid.sum()) < 3:
        return np.full(signal.shape, np.nan, dtype=float)
    A = np.column_stack([np.ones(int(valid.sum())), xx[valid], yy[valid]])
    coef, *_ = np.linalg.lstsq(A, signal[valid], rcond=None)
    plane = coef[0] + coef[1] * xx + coef[2] * yy
    out = np.where(valid, signal - plane, np.nan)
    return out


def _fit_quadratic_residual(signal: np.ndarray) -> np.ndarray:
    valid = np.isfinite(signal)
    yy, xx = np.indices(signal.shape)
    if int(valid.sum()) < 6:
        return _fit_plane_residual(signal)
    xv = xx[valid].astype(float)
    yv = yy[valid].astype(float)
    A = np.column_stack([np.ones(len(xv)), xv, yv, xv * xv, xv * yv, yv * yv])
    coef, *_ = np.linalg.lstsq(A, signal[valid], rcond=None)
    plane = (
        coef[0]
        + coef[1] * xx
        + coef[2] * yy
        + coef[3] * xx * xx
        + coef[4] * xx * yy
        + coef[5] * yy * yy
    )
    return np.where(valid, signal - plane, np.nan)


def _smooth_and_z(signal: np.ndarray, sigma: float) -> np.ndarray:
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.full(signal.shape, np.nan, dtype=float)
    fill = float(np.nanmedian(signal))
    filled = np.nan_to_num(signal, nan=fill)
    smooth = ndimage.gaussian_filter(filled, sigma=float(sigma), mode="nearest")
    z = robust_zscore(smooth)
    z[~valid] = np.nan
    return z


def _representation(grid, spec: dict) -> np.ndarray:
    signal = np.asarray(grid.signal, dtype=float)
    kind = spec["kind"]
    if kind == "regional":
        if spec["sigma"] is None:
            return _regional_trend_zscore(grid)
        residual = _fit_plane_residual(signal)
        return _smooth_and_z(residual, float(spec["sigma"]))
    if kind == "uniform":
        residual = _fit_plane_residual(signal)
        valid = np.isfinite(residual)
        if not np.any(valid):
            return np.full(signal.shape, np.nan, dtype=float)
        fill = float(np.nanmedian(residual))
        smooth = ndimage.uniform_filter(
            np.nan_to_num(residual, nan=fill), size=int(spec["size"]), mode="nearest"
        )
        z = robust_zscore(smooth)
        z[~valid] = np.nan
        return z
    if kind == "raw_gaussian":
        return _smooth_and_z(signal, float(spec["sigma"]))
    if kind == "quadratic":
        residual = _fit_quadratic_residual(signal)
        return _smooth_and_z(residual, float(spec["sigma"]))
    raise ValueError(spec)


def _target_mask(grid, target, scale: float = 1.5) -> np.ndarray:
    yy, xx = np.indices(grid.signal.shape)
    cx = int(np.argmin(np.abs(grid.x_centers - target.x)))
    cy = int(np.argmin(np.abs(grid.y_centers - target.y)))
    # Grid center arrays are metric; map through mesh coordinates for a metric ellipse.
    gx = grid.x_centers[np.newaxis, :]
    gy = grid.y_centers[:, np.newaxis]
    theta = np.radians(float(target.orientation_deg))
    dx = gx - float(target.x)
    dy = gy - float(target.y)
    xr = np.cos(theta) * dx + np.sin(theta) * dy
    yr = -np.sin(theta) * dx + np.cos(theta) * dy
    sx = max(float(target.sx) * scale, 1.5)
    sy = max(float(target.sy) * scale, 1.5)
    return (xr / sx) ** 2 + (yr / sy) ** 2 <= 1.0


def _nearest_component(labels: np.ndarray, grid, target):
    best = None
    n = int(np.nanmax(labels)) if labels.size else 0
    for cid in range(1, n + 1):
        ys, xs = np.where(labels == cid)
        if len(xs) == 0:
            continue
        cx = float(np.mean(grid.x_centers[xs]))
        cy = float(np.mean(grid.y_centers[ys]))
        d = hypot(cx - float(target.x), cy - float(target.y))
        row = {"component": int(cid), "x": cx, "y": cy, "distance_m": d, "area_cells": int(len(xs))}
        if best is None or d < best["distance_m"]:
            best = row
    return best


def _analyze_one(scan, target, spec: dict) -> dict:
    grid = reconstruct_grid(scan)
    rep = _representation(grid, spec)
    labels, broadness, n = _broad_component_selection(
        grid, rep, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    valid = np.isfinite(rep)
    mask = _target_mask(grid, target)
    vals = rep[mask & valid]
    abs_vals = np.abs(vals)
    peak = float(np.max(abs_vals)) if vals.size else 0.0
    mean_abs = float(np.mean(abs_vals)) if vals.size else 0.0
    frac_2 = float(np.mean(abs_vals >= 2.0)) if vals.size else 0.0
    comp = _nearest_component(labels, grid, target)
    hit = comp is not None and float(comp["distance_m"]) <= MATCH_RADIUS_M
    # Soft capture is representation-level, independent of connected-component suppression.
    return {
        "component_hit": bool(hit),
        "nearest_component_distance_m": None if comp is None else float(comp["distance_m"]),
        "components": int(n),
        "target_peak_abs_z": peak,
        "target_mean_abs_z": mean_abs,
        "target_fraction_abs_z_ge_2": frac_2,
    }


def _generate_scan(plan, generator: str, seed: int):
    if generator == "A":
        spec = SyntheticScenario(
            name=plan["scenario"],
            width_m=float(plan["width"]),
            height_m=float(plan["height"]),
            nx=int(plan["nx"]),
            ny=int(plan["ny"]),
            targets=tuple(plan["targets"]),
            noise_sigma=float(plan["noise_sigma"]),
            gradient_x=0.11,
            gradient_y=-0.07,
            depth_noise_sigma=0.06,
            seed=int(seed),
        )
        return generate_scan(spec)[0]
    offset = 0 if generator == "B" else 500_000
    return _generate(plan, generator=generator, seed=seed + offset)[0]


def run_broad_response_representation_audit(
    out_dir: str | Path, *, seeds=(8601, 8602), count: int = 24
):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for seed in map(int, seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            for generator in GENERATORS:
                scan = _generate_scan(plan, generator, seed * 1000 + i)
                for spec in REPRESENTATIONS:
                    for ti, target in enumerate(plan["targets"]):
                        if target.kind not in {"geology", "geological"}:
                            continue
                        metrics = _analyze_one(scan, target, spec)
                        records.append({
                            "seed": seed,
                            "site": plan["scenario"],
                            "generator": generator,
                            "representation": spec["name"],
                            "target_index": ti,
                            **metrics,
                        })

    summary = {}
    for generator in GENERATORS:
        summary[generator] = {}
        for spec in REPRESENTATIONS:
            rows = [
                r
                for r in records
                if r["generator"] == generator and r["representation"] == spec["name"]
            ]
            summary[generator][spec["name"]] = {
                "targets": len(rows),
                "component_hit_rate": float(np.mean([r["component_hit"] for r in rows]))
                if rows
                else 0.0,
                "mean_peak_abs_z": float(np.mean([r["target_peak_abs_z"] for r in rows]))
                if rows
                else 0.0,
                "mean_target_abs_z": float(np.mean([r["target_mean_abs_z"] for r in rows]))
                if rows
                else 0.0,
                "mean_fraction_abs_z_ge_2": float(
                    np.mean([r["target_fraction_abs_z_ge_2"] for r in rows])
                )
                if rows
                else 0.0,
                "mean_components": float(np.mean([r["components"] for r in rows])) if rows else 0.0,
            }

    payload = {
        "version": "0.2.86",
        "benchmark": "broad_response_representation",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "thresholds_changed": False,
        "classifier_changed": False,
        "summary": summary,
        "representations": list(REPRESENTATIONS),
        "validation_boundary": "Synthetic representation audit only; no field ground truth.",
        "decision": "diagnostic_only_no_production_change",
        "records": records,
    }
    (out / "broad_response_representation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.86 — Broad-Response Representation Audit",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, or scoring changes.",
        "",
        f"Seeds: **{len(seeds)}**; sites per seed: **{count}**.",
        "",
        "| Generator | Representation | Targets | Component hit | Mean peak | Mean target abs-z | Mean frac abs-z≥2 | Mean components |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for spec in REPRESENTATIONS:
            s = summary[g][spec["name"]]
            lines.append(
                f"| {g} | {spec['name']} | {s['targets']} | {s['component_hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | "
                f"{s['mean_target_abs_z']:.3f} | {s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "The audit compares the existence and strength of a broad/geological representation before the existing production suppression logic. This is intended to distinguish representation sensitivity from classifier sensitivity.",
        "",
        "A useful representation should improve broad-response capture across generators without relying on generator-specific thresholds or increasing component fragmentation excessively.",
        "",
        "## Decision",
        "",
        "Keep all representations diagnostic-only. Promote a representation only after independent generator evaluation shows stable gains and the production path remains regression-safe.",
    ]
    (out / "broad_response_representation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

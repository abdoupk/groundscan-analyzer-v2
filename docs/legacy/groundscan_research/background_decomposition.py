"""Diagnostic background decomposition audit for GroundScan Analyzer v0.2.92.

No production detector/classifier/threshold/registration/fusion behavior is
changed. The audit compares practical residualization families after v0.2.91
identified periodic and radial-curvature backgrounds as the dominant synthetic
confounders. It also reports an oracle background-removed ceiling.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.background import robust_zscore
from groundscan.core.grid import Grid2D
from groundscan.validation.synthetic_core.core import SyntheticTarget
from groundscan_research.forward_background_interaction import (
    BROAD_THRESHOLD,
    MATCH_RADIUS_M,
    MIN_AREA_FRACTION,
    MIN_SPAN_FRACTION,
    _background_b,
    _background_c,
    _compress_b,
)
from groundscan_research.synthetic_generator_independence import (
    _master_plan,
    _response_b,
    _response_c,
)

GENERATORS = ("B", "C")
METHODS = (
    "current",
    "plane_residual_sigma2",
    "poly2_residual_sigma2",
    "poly2_residual_sigma4",
    "gaussian_residual_sigma4",
    "gaussian_residual_sigma6",
    "gaussian_residual_sigma8",
    "median_residual_9",
    "median_residual_13",
    "oracle_true_background_removed",
)


def _grid(field: np.ndarray, plan: dict) -> Grid2D:
    ny, nx = field.shape
    return Grid2D(
        x_centers=np.linspace(0.0, float(plan["width"]), nx),
        y_centers=np.linspace(0.0, float(plan["height"]), ny),
        signal=np.asarray(field, dtype=float),
        depth=np.full_like(field, 5.0, dtype=float),
        counts=np.ones_like(field, dtype=int),
    )


def _fit_poly_residual(signal: np.ndarray, degree: int) -> np.ndarray:
    valid = np.isfinite(signal)
    yy, xx = np.indices(signal.shape)
    x = xx.astype(float)
    y = yy.astype(float)
    n = int(valid.sum())
    if n < (6 if degree >= 2 else 3):
        degree = 1
    cols = [np.ones(n), x[valid], y[valid]]
    if degree >= 2:
        cols.extend([x[valid] ** 2, x[valid] * y[valid], y[valid] ** 2])
    coef = np.linalg.lstsq(np.column_stack(cols), signal[valid], rcond=None)[0]
    bg = coef[0] + coef[1] * x + coef[2] * y
    if degree >= 2:
        bg += coef[3] * x * x + coef[4] * x * y + coef[5] * y * y
    return np.where(valid, signal - bg, np.nan)


def _gaussian_residual(signal: np.ndarray, sigma: float) -> np.ndarray:
    valid = np.isfinite(signal)
    fill = float(np.nanmedian(signal[valid])) if np.any(valid) else 0.0
    sm = ndimage.gaussian_filter(np.where(valid, signal, fill), sigma=float(sigma), mode="nearest")
    residual = signal - sm
    residual[~valid] = np.nan
    return residual


def _median_residual(signal: np.ndarray, size: int) -> np.ndarray:
    valid = np.isfinite(signal)
    fill = float(np.nanmedian(signal[valid])) if np.any(valid) else 0.0
    sm = ndimage.median_filter(np.where(valid, signal, fill), size=int(size), mode="nearest")
    residual = signal - sm
    residual[~valid] = np.nan
    return residual


def _compress_inverse_b(signal: np.ndarray) -> np.ndarray:
    # Exact algebraic inverse for y = x/(1 + 0.035|x|), where x is centered at 142.
    y = np.asarray(signal, dtype=float) - 142.0
    ay = np.abs(y)
    denominator = np.maximum(1.0 - 0.035 * ay, 1e-6)
    x = ay / denominator
    return 142.0 + np.sign(y) * x


def _oracle(field: np.ndarray, background: np.ndarray, generator: str) -> np.ndarray:
    linear = _compress_inverse_b(field) if generator == "B" else field
    return linear - background


def _scene(plan: dict, generator: str, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    width, height = float(plan["width"]), float(plan["height"])
    nx, ny = int(plan["nx"]), int(plan["ny"])
    x = np.linspace(0.0, width, nx)
    y = np.linspace(0.0, height, ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    targets = plan["targets"]
    responses = [
        (_response_b(xx, yy, t) if generator == "B" else _response_c(xx, yy, t)) for t in targets
    ]
    geos = [t for t in targets if t.kind in {"geology", "geological"}]
    target = geos[0]
    target_index = next(i for i, t in enumerate(targets) if t is target)
    background = _background_b(xx, yy) if generator == "B" else _background_c(xx, yy)
    linear = background + sum(responses, np.zeros_like(xx))
    linear += rng.normal(0.0, float(plan["noise_sigma"]), size=linear.shape)
    if generator == "B":
        observed = _compress_b(linear)
    else:
        observed = linear.copy()
        impulse_mask = rng.random(observed.shape) < 0.008
        if np.any(impulse_mask):
            observed[impulse_mask] += rng.normal(0.0, 3.5, size=int(impulse_mask.sum()))
    return observed, background, target


def _representation(
    field: np.ndarray, background: np.ndarray, plan: dict, generator: str, method: str
) -> np.ndarray:
    if method == "current":
        return _regional_trend_zscore(_grid(field, plan))
    if method == "oracle_true_background_removed":
        return robust_zscore(_oracle(field, background, generator))
    if generator == "B":
        linear = _compress_inverse_b(field)
    else:
        linear = field
    if method == "plane_residual_sigma2":
        residual = _fit_poly_residual(linear, 1)
        response = ndimage.gaussian_filter(
            np.nan_to_num(residual, nan=0.0), sigma=2.0, mode="nearest"
        )
    elif method == "poly2_residual_sigma2":
        residual = _fit_poly_residual(linear, 2)
        response = ndimage.gaussian_filter(
            np.nan_to_num(residual, nan=0.0), sigma=2.0, mode="nearest"
        )
    elif method == "poly2_residual_sigma4":
        residual = _fit_poly_residual(linear, 2)
        response = ndimage.gaussian_filter(
            np.nan_to_num(residual, nan=0.0), sigma=4.0, mode="nearest"
        )
    elif method.startswith("gaussian_residual_sigma"):
        sigma = float(method.rsplit("sigma", 1)[1])
        response = _gaussian_residual(linear, sigma)
    elif method == "median_residual_9":
        response = _median_residual(linear, 9)
    elif method == "median_residual_13":
        response = _median_residual(linear, 13)
    else:
        raise ValueError(method)
    z = robust_zscore(response)
    z[~np.isfinite(field)] = np.nan
    return z


def _metrics(field: np.ndarray, plan: dict, target: SyntheticTarget, rep: np.ndarray) -> dict:
    labels, _, n = _broad_component_selection(
        _grid(field, plan), rep, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    mask = np.zeros_like(field, dtype=bool)
    theta = np.radians(float(target.orientation_deg))
    yy, xx = np.meshgrid(y, x, indexing="ij")
    dx, dy = xx - float(target.x), yy - float(target.y)
    xr = np.cos(theta) * dx + np.sin(theta) * dy
    yr = -np.sin(theta) * dx + np.cos(theta) * dy
    sx, sy = max(float(target.sx) * 1.5, 1.5), max(float(target.sy) * 1.5, 1.5)
    mask = (xr / sx) ** 2 + (yr / sy) ** 2 <= 1.0
    vals = np.abs(rep[mask & np.isfinite(rep)])
    nearest = None
    false = 0
    for cid in range(1, int(n) + 1):
        ys, xs = np.where(labels == cid)
        if not len(xs):
            continue
        d = float(np.hypot(np.mean(x[xs]) - target.x, np.mean(y[ys]) - target.y))
        nearest = d if nearest is None else min(nearest, d)
        overlap = np.count_nonzero((labels == cid) & mask) / max(np.count_nonzero(labels == cid), 1)
        if overlap < 0.25:
            false += 1
    return {
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "nearest_distance_m": nearest,
        "components": int(n),
        "false_components": int(false),
        "peak_abs_z": float(np.max(vals)) if vals.size else 0.0,
        "mean_abs_z": float(np.mean(vals)) if vals.size else 0.0,
        "fraction_abs_z_ge_2": float(np.mean(vals >= 2.0)) if vals.size else 0.0,
    }


def _summarize(records: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = (r["generator"], r["method"])
        groups.setdefault(key, []).append(r)
    out = {}
    for (g, m), rs in groups.items():
        out[f"{g}|{m}"] = {
            "records": len(rs),
            "hit_rate": float(np.mean([r["component_hit"] for r in rs])),
            "mean_false_components": float(np.mean([r["false_components"] for r in rs])),
            "mean_components": float(np.mean([r["components"] for r in rs])),
            "mean_peak_abs_z": float(np.mean([r["peak_abs_z"] for r in rs])),
        }
    return out


def _write_report(out: Path, payload: dict) -> None:
    lines = [
        "# GroundScan Analyzer v0.2.92 — Background Decomposition Audit",
        "",
        "> Diagnostic-only. No production detector, threshold, classifier, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(payload['seeds'])}**; sites/seed: **{payload['count']}**; geology records/generator: **{payload['geology_records_per_generator']}**.",
        "",
        "## Practical residualization methods",
        "",
        "| Generator | Method | Hit rate | False comps | Components | Peak abs-z |",
        "|---|---|---:|---:|---:|---:|",
    ]
    summary = payload["summary"]
    for key, s in sorted(summary.items()):
        g, method = key.split("|", 1)
        lines.append(
            f"| {g} | {method} | {s['hit_rate']:.3f} | {s['mean_false_components']:.2f} | {s['mean_components']:.2f} | {s['mean_peak_abs_z']:.3f} |"
        )
    lines += ["", "## Oracle ceiling", ""]
    for g in GENERATORS:
        oracle = summary[f"{g}|oracle_true_background_removed"]
        current = summary[f"{g}|current"]
        lines.append(
            f"- **{g}:** current hit **{current['hit_rate']:.3f}** → oracle background-removed **{oracle['hit_rate']:.3f}**; "
            f"oracle false components **{oracle['mean_false_components']:.2f}**."
        )
    lines += [
        "",
        "## Decision",
        "",
        "No production decomposition is enabled by this audit. A candidate is eligible only if it improves both independent generators without materially increasing false broad components or regressing the existing hard/frozen gates.",
        "",
        "## Validation boundary",
        "",
        "Synthetic software-validation measurements only. They do not establish real-device field performance and do not prove any physical material or structure.",
    ]
    (out / "background_decomposition.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_background_decomposition_audit(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = tuple(range(9211, 9219)),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for seed in map(int, seeds):
        for i, plan in enumerate(_master_plan(seed, count)):
            if not any(t.kind in {"geology", "geological"} for t in plan["targets"]):
                continue
            for generator in GENERATORS:
                field, background, target = _scene(
                    plan, generator, seed * 1000 + i + (0 if generator == "B" else 500000)
                )
                for method in METHODS:
                    rep = _representation(field, background, plan, generator, method)
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "method": method,
                        **_metrics(field, plan, target, rep),
                    })
    b_rows = [r for r in records if r["generator"] == "B"]
    geology_records = len(b_rows) // len(METHODS) if b_rows else 0
    payload = {
        "version": "0.2.92",
        "benchmark": "background_decomposition",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "geology_records_per_generator": int(geology_records),
        "methods": list(METHODS),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "summary": _summarize(records),
        "records": records,
        "decision": "diagnostic_only_no_production_change",
        "validation_boundary": "Synthetic diagnostic only; no field ground truth or material identification.",
    }
    (out / "background_decomposition.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    _write_report(out, payload)
    return payload

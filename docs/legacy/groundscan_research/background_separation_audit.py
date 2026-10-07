"""Diagnostic background-separation audit for GroundScan Analyzer v0.2.88.

No production detector/classifier/threshold/registration/fusion behavior is
changed here. The audit asks a narrower question: how much of the geological
broad-response loss comes from background estimation, and can a practical
background estimator recover it without creating broad false components?
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.background import robust_zscore
from groundscan.core.grid import Grid2D
from groundscan.models import ScanData, ScanMetadata
from groundscan.validation.synthetic_core.core import SyntheticTarget
from groundscan_research.forward_background_interaction import (
    BROAD_THRESHOLD,
    MATCH_RADIUS_M,
    MIN_AREA_FRACTION,
    MIN_SPAN_FRACTION,
    _background_b,
    _background_c,
    _compress_b,
    _target_mask,
)
from groundscan_research.synthetic_generator_independence import (
    _master_plan,
    _response_b,
    _response_c,
)

GENERATORS = ("B", "C")
REPRESENTATIONS = (
    "current",
    "gaussian_bg6_sigma2",
    "gaussian_bg8_sigma2",
    "gaussian_bg10_sigma2",
    "quadratic_sigma2",
    "quadratic_sigma4",
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
    if valid.sum() < (6 if degree >= 2 else 3):
        degree = 1
    cols = [np.ones(int(valid.sum())), x[valid], y[valid]]
    if degree >= 2:
        cols.extend([x[valid] ** 2, x[valid] * y[valid], y[valid] ** 2])
    coef = np.linalg.lstsq(np.column_stack(cols), signal[valid], rcond=None)[0]
    bg = coef[0] + coef[1] * x + coef[2] * y
    if degree >= 2:
        bg += coef[3] * x * x + coef[4] * x * y + coef[5] * y * y
    return np.where(valid, signal - bg, np.nan)


def _gaussian_background_residual(
    signal: np.ndarray, background_sigma: float, response_sigma: float
) -> np.ndarray:
    valid = np.isfinite(signal)
    if not np.any(valid):
        return np.full_like(signal, np.nan, dtype=float)
    fill = float(np.nanmedian(signal[valid]))
    smoothed_background = ndimage.gaussian_filter(
        np.where(valid, signal, fill), sigma=float(background_sigma), mode="nearest"
    )
    residual = signal - smoothed_background
    residual[~valid] = np.nan
    # A small response smoothing is retained so the diagnostic remains comparable
    # to the broad production channel rather than evaluating isolated pixels.
    fill_resid = float(np.nanmedian(residual[valid])) if np.any(valid) else 0.0
    response = ndimage.gaussian_filter(
        np.where(valid, residual, fill_resid), sigma=float(response_sigma), mode="nearest"
    )
    z = robust_zscore(response)
    z[~valid] = np.nan
    return z


def _quadratic_representation(signal: np.ndarray, response_sigma: float) -> np.ndarray:
    residual = _fit_poly_residual(signal, degree=2)
    valid = np.isfinite(residual)
    if not np.any(valid):
        return np.full_like(signal, np.nan, dtype=float)
    fill = float(np.nanmedian(residual[valid]))
    smooth = ndimage.gaussian_filter(
        np.where(valid, residual, fill), sigma=float(response_sigma), mode="nearest"
    )
    z = robust_zscore(smooth)
    z[~valid] = np.nan
    return z


def _inverse_compress_b(signal: np.ndarray) -> np.ndarray:
    """Exact inverse of v0.2.82 Generator-B compression in its valid range."""
    y = np.asarray(signal, dtype=float) - 142.0
    ay = np.abs(y)
    denominator = np.maximum(1.0 - 0.035 * ay, 1e-6)
    delta = ay / denominator
    return 142.0 + np.sign(y) * delta


def _oracle_representation(
    observed: np.ndarray, background: np.ndarray, generator: str
) -> np.ndarray:
    if generator == "B":
        linear = _inverse_compress_b(observed)
    else:
        linear = observed
    return robust_zscore(linear - background)


def _scan_from_field(field: np.ndarray, plan: dict, generator: str) -> ScanData:
    ny, nx = field.shape
    x = np.linspace(0.0, float(plan["width"]), nx)
    y = np.linspace(0.0, float(plan["height"]), ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=np.full(field.size, 5.0),
        signal=np.asarray(field, dtype=float).ravel(),
        grid_i=np.tile(np.arange(nx, dtype=float), ny),
        grid_j=np.repeat(np.arange(ny, dtype=float), nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device=f"synthetic-independent-{generator}",
            field_length_m=float(plan["width"]),
            field_width_m=float(plan["height"]),
            notes=f"v0.2.88 background separation audit {generator}",
            source_file=f"synthetic:{generator}:{plan['scenario']}:v088",
        ),
    )


def _scene(
    plan: dict, generator: str, seed: int, target_index: int
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    width, height = float(plan["width"]), float(plan["height"])
    nx, ny = int(plan["nx"]), int(plan["ny"])
    x = np.linspace(0.0, width, nx)
    y = np.linspace(0.0, height, ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    responses = [
        _response_b(xx, yy, t) if generator == "B" else _response_c(xx, yy, t)
        for t in plan["targets"]
    ]
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
    return observed, background


def _representation(
    field: np.ndarray, plan: dict, variant: str, background: np.ndarray, generator: str
) -> np.ndarray:
    if variant == "current":
        return _regional_trend_zscore(_grid(field, plan))
    if variant == "gaussian_bg6_sigma2":
        return _gaussian_background_residual(field, 6.0, 2.0)
    if variant == "gaussian_bg8_sigma2":
        return _gaussian_background_residual(field, 8.0, 2.0)
    if variant == "gaussian_bg10_sigma2":
        return _gaussian_background_residual(field, 10.0, 2.0)
    if variant == "quadratic_sigma2":
        return _quadratic_representation(field, 2.0)
    if variant == "quadratic_sigma4":
        return _quadratic_representation(field, 4.0)
    if variant == "oracle_true_background_removed":
        return _oracle_representation(field, background, generator)
    raise ValueError(variant)


def _metrics(
    field: np.ndarray, plan: dict, target: SyntheticTarget, representation: np.ndarray
) -> dict:
    grid = _grid(field, plan)
    labels, _, n = _broad_component_selection(
        grid, representation, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    mask = _target_mask(plan, target, field.shape)
    valid = np.isfinite(representation)
    vals = np.abs(representation[mask & valid])
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    distances: list[float] = []
    false_components = 0
    for cid in range(1, int(n) + 1):
        ys, xs = np.where(labels == cid)
        if len(xs) == 0:
            continue
        distances.append(float(np.hypot(np.mean(x[xs]) - target.x, np.mean(y[ys]) - target.y)))
        overlap = float(np.count_nonzero((labels == cid) & mask)) / max(
            int(np.count_nonzero(labels == cid)), 1
        )
        if overlap < 0.25:
            false_components += 1
    nearest = min(distances) if distances else None
    return {
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "nearest_component_distance_m": nearest,
        "components": int(n),
        "false_components_away_from_target": int(false_components),
        "target_peak_abs_z": float(np.max(vals)) if vals.size else 0.0,
        "target_mean_abs_z": float(np.mean(vals)) if vals.size else 0.0,
        "target_fraction_abs_z_ge_2": float(np.mean(vals >= 2.0)) if vals.size else 0.0,
    }


def run_background_separation_audit(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = tuple(range(8811, 8819)),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for seed in map(int, seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            geo_items = [
                (j, t) for j, t in enumerate(plan["targets"]) if t.kind in {"geology", "geological"}
            ]
            if not geo_items:
                continue
            target_index, target = geo_items[0]
            for generator in GENERATORS:
                observed, background = _scene(
                    plan,
                    generator,
                    seed * 1000 + i + (0 if generator == "B" else 500_000),
                    target_index,
                )
                for variant in REPRESENTATIONS:
                    rep = _representation(observed, plan, variant, background, generator)
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "representation": variant,
                        **_metrics(observed, plan, target, rep),
                    })

    summary: dict[str, dict[str, dict]] = {g: {} for g in GENERATORS}
    for generator in GENERATORS:
        for variant in REPRESENTATIONS:
            rows = [
                r for r in records if r["generator"] == generator and r["representation"] == variant
            ]
            summary[generator][variant] = {
                "records": len(rows),
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
                "mean_false_components_away": float(
                    np.mean([r["false_components_away_from_target"] for r in rows])
                )
                if rows
                else 0.0,
            }

    delta = {}
    for generator in GENERATORS:
        base = summary[generator]["current"]
        delta[generator] = {}
        for variant in REPRESENTATIONS:
            delta[generator][variant] = {
                "hit_rate_delta": summary[generator][variant]["component_hit_rate"]
                - base["component_hit_rate"],
                "false_component_delta": summary[generator][variant]["mean_false_components_away"]
                - base["mean_false_components_away"],
                "peak_delta": summary[generator][variant]["mean_peak_abs_z"]
                - base["mean_peak_abs_z"],
            }

    payload = {
        "version": "0.2.88",
        "benchmark": "background_separation_audit",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "production_detector_changed": False,
        "production_thresholds_changed": False,
        "production_classifier_changed": False,
        "production_registration_changed": False,
        "production_fusion_changed": False,
        "representations": list(REPRESENTATIONS),
        "summary": summary,
        "delta_vs_current": delta,
        "records": records,
        "validation_boundary": "Synthetic diagnostic only; no field ground truth, material identification, or proof of real-world geological detection.",
        "decision": "diagnostic_only_no_production_change",
    }
    (out / "background_separation_audit.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.88 — Background Separation Audit",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per seed: **{count}**; geology records per generator: **{sum(r['generator'] == 'B' for r in records) // len(REPRESENTATIONS)}**.",
        "",
        "| Generator | Representation | Records | Broad hit | Mean peak | Mean target abs-z | Mean frac abs-z≥2 | Mean comps | False comps |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for generator in GENERATORS:
        for variant in REPRESENTATIONS:
            s = summary[generator][variant]
            lines.append(
                f"| {generator} | {variant} | {s['records']} | {s['component_hit_rate']:.3f} | "
                f"{s['mean_peak_abs_z']:.3f} | {s['mean_target_abs_z']:.3f} | "
                f"{s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} | "
                f"{s['mean_false_components_away']:.2f} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "The oracle representation removes the known synthetic background after reversing Generator-B compression. It is a ceiling diagnostic, not a deployable production method.",
        "",
        "Practical Gaussian and quadratic variants are judged on both broad-response capture and false broad components. A gain in one generator is not sufficient for promotion when the same representation increases fragmentation or false components in the other generator.",
        "",
        "## Decision",
        "",
        "Do not change the production broad channel in v0.2.88. The oracle ceiling shows that background interaction is a major contributor, but no practical estimator tested here is stable enough across independent generators to promote without a new validation basis.",
        "",
        "## Validation boundary",
        "",
        "All measurements are synthetic. They do not establish field detection performance, identify gold/metal/minerals, or prove a cavity, tunnel, or geological structure in real survey data.",
    ]
    (out / "background_separation_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

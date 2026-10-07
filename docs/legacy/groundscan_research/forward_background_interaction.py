"""Diagnostic forward-model/background interaction audit for v0.2.87.

This module does not alter production detection, classification, thresholds,
registration, fusion, or scoring. It decomposes the independent synthetic
scenes into target/background/acquisition stages so generator-shift losses can
be attributed to the forward response, the background field, or their
interaction rather than tuned away with generator-specific heuristics.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.background import robust_scale
from groundscan.core.grid import Grid2D
from groundscan.models import ScanData, ScanMetadata
from groundscan.validation.synthetic_core.core import SyntheticTarget
from groundscan_research.synthetic_generator_independence import (
    _master_plan,
    _response_b,
    _response_c,
)

GENERATORS = ("B", "C")
VARIANTS = (
    "target_only",
    "background_only",
    "target_plus_background_clean",
    "target_plus_background_noisy",
    "full_scene",
)
BROAD_THRESHOLD = 2.1
MIN_AREA_FRACTION = 0.02
MIN_SPAN_FRACTION = 0.18
MATCH_RADIUS_M = 3.0


def _background_b(xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    return 142.0 + 0.11 * xx - 0.07 * yy + 2.2 * np.sin(xx / 7.0) + 1.4 * np.cos(yy / 5.0)


def _background_c(xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    return (
        118.0
        + 0.16 * np.sqrt(xx**2 + yy**2)
        + 1.7 * np.sin((xx + 1.8 * yy) / 9.5)
        + 0.9 * np.sin(yy / 3.7)
    )


def _compress_b(signal: np.ndarray) -> np.ndarray:
    return 142.0 + (signal - 142.0) / (1.0 + 0.035 * np.abs(signal - 142.0))


def _grid_from_field(field: np.ndarray, width: float, height: float) -> Grid2D:
    ny, nx = field.shape
    return Grid2D(
        x_centers=np.linspace(0.0, width, nx),
        y_centers=np.linspace(0.0, height, ny),
        signal=np.asarray(field, dtype=float),
        depth=np.full_like(field, 5.0, dtype=float),
        counts=np.ones_like(field, dtype=int),
    )


def _scan_from_field(field: np.ndarray, plan: dict, generator: str) -> ScanData:
    ny, nx = field.shape
    x = np.linspace(0.0, float(plan["width"]), nx)
    y = np.linspace(0.0, float(plan["height"]), ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    depth = np.full_like(field, 5.0, dtype=float)
    return ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=depth.ravel(),
        signal=np.asarray(field, dtype=float).ravel(),
        grid_i=np.tile(np.arange(nx, dtype=float), ny),
        grid_j=np.repeat(np.arange(ny, dtype=float), nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device=f"synthetic-independent-{generator}",
            field_length_m=float(plan["width"]),
            field_width_m=float(plan["height"]),
            notes=f"v0.2.87 forward/background interaction stage {generator}",
            source_file=f"synthetic:{generator}:{plan['scenario']}:v087",
        ),
    )


def _target_mask(
    plan: dict, target: SyntheticTarget, shape: tuple[int, int], scale: float = 1.5
) -> np.ndarray:
    ny, nx = shape
    x = np.linspace(0.0, float(plan["width"]), nx)
    y = np.linspace(0.0, float(plan["height"]), ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    theta = np.radians(float(target.orientation_deg))
    dx = xx - float(target.x)
    dy = yy - float(target.y)
    xr = np.cos(theta) * dx + np.sin(theta) * dy
    yr = -np.sin(theta) * dx + np.cos(theta) * dy
    sx = max(float(target.sx) * scale, 1.5)
    sy = max(float(target.sy) * scale, 1.5)
    return (xr / sx) ** 2 + (yr / sy) ** 2 <= 1.0


def _representation_stats(field: np.ndarray, plan: dict, target: SyntheticTarget) -> dict:
    grid = _grid_from_field(field, float(plan["width"]), float(plan["height"]))
    z = _regional_trend_zscore(grid)
    labels, _, n = _broad_component_selection(
        grid, z, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    mask = _target_mask(plan, target, field.shape)
    valid = np.isfinite(z)
    vals = np.abs(z[mask & valid])
    peak = float(np.max(vals)) if vals.size else 0.0
    mean_abs = float(np.mean(vals)) if vals.size else 0.0
    frac2 = float(np.mean(vals >= 2.0)) if vals.size else 0.0
    ys, xs = np.where(labels > 0)
    nearest = None
    if len(xs):
        x = np.linspace(0.0, float(plan["width"]), field.shape[1])
        y = np.linspace(0.0, float(plan["height"]), field.shape[0])
        for cid in range(1, int(n) + 1):
            cyi, cxi = np.where(labels == cid)
            if len(cxi) == 0:
                continue
            cx = float(np.mean(x[cxi]))
            cy = float(np.mean(y[cyi]))
            d = float(np.hypot(cx - float(target.x), cy - float(target.y)))
            nearest = d if nearest is None else min(nearest, d)
    broad_hit = nearest is not None and nearest <= MATCH_RADIUS_M
    outside = valid & ~mask
    false_components = 0
    for cid in range(1, int(n) + 1):
        cm = labels == cid
        overlap = float(np.count_nonzero(cm & mask)) / max(int(np.count_nonzero(cm)), 1)
        if overlap < 0.25:
            false_components += 1
    return {
        "component_hit": bool(broad_hit),
        "nearest_component_distance_m": None if nearest is None else nearest,
        "components": int(n),
        "false_components_away_from_target": int(false_components),
        "target_peak_abs_z": peak,
        "target_mean_abs_z": mean_abs,
        "target_fraction_abs_z_ge_2": frac2,
        "background_abs_z_p95_outside_target": float(np.nanpercentile(np.abs(z[outside]), 95))
        if np.any(outside)
        else 0.0,
        "background_robust_scale": float(robust_scale(z[outside]))
        if np.count_nonzero(outside) >= 2
        else 1.0,
    }


def _field_stages(
    plan: dict, generator: str, seed: int, target_index: int
) -> dict[str, np.ndarray]:
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
    geology_response = responses[target_index]
    other_response = sum(
        (r for i, r in enumerate(responses) if i != target_index), np.zeros_like(xx)
    )
    background = _background_b(xx, yy) if generator == "B" else _background_c(xx, yy)
    noisy_background = background + rng.normal(
        0.0, float(plan["noise_sigma"]), size=background.shape
    )
    clean_additive = background + geology_response
    noisy_additive = clean_additive + rng.normal(
        0.0, float(plan["noise_sigma"]), size=background.shape
    )
    full_linear = (
        background
        + geology_response
        + other_response
        + rng.normal(0.0, float(plan["noise_sigma"]), size=background.shape)
    )
    if generator == "B":
        full = _compress_b(full_linear)
        noisy_target_plus_background = _compress_b(noisy_additive)
        background_only = _compress_b(noisy_background)
        target_only = _compress_b(142.0 + geology_response)
    else:
        impulse_mask = rng.random(full_linear.shape) < 0.008
        impulses = np.zeros_like(full_linear)
        if np.any(impulse_mask):
            impulses[impulse_mask] = rng.normal(0.0, 3.5, size=int(impulse_mask.sum()))
        full = full_linear + impulses
        noisy_target_plus_background = noisy_additive
        background_only = noisy_background
        target_only = geology_response
    return {
        "target_only": target_only,
        "background_only": background_only,
        "target_plus_background_clean": clean_additive
        if generator == "C"
        else _compress_b(clean_additive),
        "target_plus_background_noisy": noisy_target_plus_background,
        "full_scene": full,
    }


def _aggregate(rows: list[dict]) -> dict:
    def mean(key: str) -> float:
        return float(np.mean([float(r[key]) for r in rows])) if rows else 0.0

    return {
        "records": len(rows),
        "component_hit_rate": mean("component_hit"),
        "mean_peak_abs_z": mean("target_peak_abs_z"),
        "mean_target_abs_z": mean("target_mean_abs_z"),
        "mean_fraction_abs_z_ge_2": mean("target_fraction_abs_z_ge_2"),
        "mean_components": mean("components"),
        "mean_false_components_away": mean("false_components_away_from_target"),
        "mean_background_abs_z_p95": mean("background_abs_z_p95_outside_target"),
        "mean_background_robust_scale": mean("background_robust_scale"),
    }


def run_forward_background_interaction_audit(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = (8701, 8702, 8703),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for seed in tuple(int(s) for s in seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            geology = [t for t in plan["targets"] if t.kind in {"geology", "geological"}]
            if not geology:
                continue
            target_index = next(
                j for j, t in enumerate(plan["targets"]) if t.kind in {"geology", "geological"}
            )
            for generator in GENERATORS:
                stages = _field_stages(
                    plan,
                    generator,
                    seed * 1000 + i + (0 if generator == "B" else 500000),
                    target_index,
                )
                for variant, field in stages.items():
                    stats = _representation_stats(field, plan, geology[0])
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "variant": variant,
                        **stats,
                    })

    summary: dict[str, dict[str, dict]] = {g: {} for g in GENERATORS}
    for g in GENERATORS:
        for variant in VARIANTS:
            rows = [r for r in records if r["generator"] == g and r["variant"] == variant]
            summary[g][variant] = _aggregate(rows)

    interaction = {}
    for g in GENERATORS:
        a = summary[g]["target_only"]
        b = summary[g]["target_plus_background_clean"]
        c = summary[g]["target_plus_background_noisy"]
        d = summary[g]["full_scene"]
        interaction[g] = {
            "clean_component_hit_delta_vs_target_only": b["component_hit_rate"]
            - a["component_hit_rate"],
            "noisy_component_hit_delta_vs_target_only": c["component_hit_rate"]
            - a["component_hit_rate"],
            "full_component_hit_delta_vs_target_only": d["component_hit_rate"]
            - a["component_hit_rate"],
            "clean_peak_ratio_vs_target_only": b["mean_peak_abs_z"]
            / max(a["mean_peak_abs_z"], 1e-9),
            "noisy_peak_ratio_vs_target_only": c["mean_peak_abs_z"]
            / max(a["mean_peak_abs_z"], 1e-9),
            "full_peak_ratio_vs_target_only": d["mean_peak_abs_z"]
            / max(a["mean_peak_abs_z"], 1e-9),
            "full_background_p95": d["mean_background_abs_z_p95"],
            "background_only_component_rate": summary[g]["background_only"]["component_hit_rate"],
            "background_only_false_components": summary[g]["background_only"][
                "mean_false_components_away"
            ],
        }

    payload = {
        "version": "0.2.87",
        "benchmark": "forward_background_interaction",
        "seeds": [int(s) for s in seeds],
        "count_per_seed": int(count),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "thresholds_changed": False,
        "classifier_changed": False,
        "summary": summary,
        "interaction": interaction,
        "method": {
            "representation": "current production regional broad channel only",
            "target_family": "geology/geological",
            "stages": list(VARIANTS),
            "purpose": "attribute generator-shift broad-response loss to target response, background, acquisition nonlinearity/noise, or their interaction",
        },
        "validation_boundary": "Synthetic diagnostic only; no field ground truth or device-calibrated forward model.",
        "decision": "diagnostic_only_no_production_change",
        "records": records,
    }
    (out / "forward_background_interaction.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.87 — Forward-Model / Background Interaction Audit",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per seed: **{count}**. The same target plans are used for B and C.",
        "",
        "## Stage results",
        "",
        "| Generator | Variant | Records | Component hit | Mean peak | Mean target abs-z | Mean frac | Mean components | Background p95 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for v in VARIANTS:
            s = summary[g][v]
            lines.append(
                f"| {g} | {v} | {s['records']} | {s['component_hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | {s['mean_target_abs_z']:.3f} | {s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} | {s['mean_background_abs_z_p95']:.3f} |"
            )
    lines += [
        "",
        "## Interaction deltas",
        "",
        "| Generator | Clean hit Δ | Noisy hit Δ | Full hit Δ | Clean peak ratio | Noisy peak ratio | Full peak ratio | Background-only false comps |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        s = interaction[g]
        lines.append(
            f"| {g} | {s['clean_component_hit_delta_vs_target_only']:+.3f} | {s['noisy_component_hit_delta_vs_target_only']:+.3f} | {s['full_component_hit_delta_vs_target_only']:+.3f} | {s['clean_peak_ratio_vs_target_only']:.3f} | {s['noisy_peak_ratio_vs_target_only']:.3f} | {s['full_peak_ratio_vs_target_only']:.3f} | {s['background_only_false_components']:.2f} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "`target_only` asks whether the geological forward response is representable on its own. `background_only` measures broad-channel contamination without the target. The clean/noisy/full stages then expose the loss caused by background interaction and acquisition effects.",
        "",
        "A large drop from `target_only` to `target_plus_background_clean` indicates background interaction. A further drop after noise/nonlinearity indicates acquisition interaction. A target that is weak even in `target_only` points to forward-response representation rather than background suppression.",
        "",
        "## Decision",
        "",
        "Diagnostic only. No production change is justified from this audit alone.",
        "",
        "## Validation boundary",
        "",
        "Results are synthetic. They do not establish field detection performance, material identity, or proof of a geological anomaly in real ground data.",
    ]
    (out / "forward_background_interaction.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

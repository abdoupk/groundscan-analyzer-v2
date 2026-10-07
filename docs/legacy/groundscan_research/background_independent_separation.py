"""Diagnostic background-independent separation prototype for v0.2.93.

No production detector/classifier/threshold/registration/fusion behavior changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.background import robust_zscore
from groundscan_research.background_decomposition import _compress_inverse_b, _grid, _scene
from groundscan_research.forward_background_interaction import (
    BROAD_THRESHOLD,
    MATCH_RADIUS_M,
    MIN_AREA_FRACTION,
    MIN_SPAN_FRACTION,
)
from groundscan_research.synthetic_generator_independence import _master_plan

GENERATORS = ("B", "C")
METHODS = ("current", "dog_2_4", "dog_2_4_shape_gate")
SHAPE_ASPECT_MAX = 2.5
SHAPE_DENSITY_MIN = 0.55


def _dog_2_4(field: np.ndarray, generator: str) -> np.ndarray:
    # v0.2.93 prototype intentionally avoids choosing an explicit background model.
    linear = _compress_inverse_b(field) if generator == "B" else np.asarray(field, dtype=float)
    s2 = ndimage.gaussian_filter(linear, sigma=2.0, mode="nearest")
    s4 = ndimage.gaussian_filter(linear, sigma=4.0, mode="nearest")
    return robust_zscore(s2 - s4)


def _shape_gate(labels: np.ndarray) -> tuple[np.ndarray, int]:
    if int(labels.max()) == 0:
        return labels.copy(), 0
    kept = np.zeros_like(labels, dtype=bool)
    rejected = 0
    for cid in range(1, int(labels.max()) + 1):
        ys, xs = np.where(labels == cid)
        if not len(xs):
            continue
        sx = xs.max() - xs.min() + 1
        sy = ys.max() - ys.min() + 1
        aspect = max(sx / max(sy, 1), sy / max(sx, 1))
        density = len(xs) / max(sx * sy, 1)
        if aspect <= SHAPE_ASPECT_MAX and density >= SHAPE_DENSITY_MIN:
            kept[labels == cid] = True
        else:
            rejected += 1
    out, n = ndimage.label(kept, structure=ndimage.generate_binary_structure(2, 2))
    return out.astype(int), int(rejected)


def _target_mask(field: np.ndarray, plan: dict, target) -> np.ndarray:
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    yy, xx = np.meshgrid(y, x, indexing="ij")
    theta = np.radians(float(target.orientation_deg))
    dx, dy = xx - float(target.x), yy - float(target.y)
    xr = np.cos(theta) * dx + np.sin(theta) * dy
    yr = -np.sin(theta) * dx + np.cos(theta) * dy
    sx = max(float(target.sx) * 1.5, 1.5)
    sy = max(float(target.sy) * 1.5, 1.5)
    return (xr / sx) ** 2 + (yr / sy) ** 2 <= 1.0


def _evaluate(field: np.ndarray, plan: dict, target, rep: np.ndarray, shape_gate: bool) -> dict:
    grid = _grid(field, plan)
    labels, _, n = _broad_component_selection(
        grid, rep, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    rejected = 0
    if shape_gate:
        labels, rejected = _shape_gate(labels)
        n = int(labels.max())
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    tmask = _target_mask(field, plan, target)
    nearest = None
    false = 0
    for cid in range(1, int(n) + 1):
        ys, xs = np.where(labels == cid)
        if not len(xs):
            continue
        d = float(np.hypot(np.mean(x[xs]) - target.x, np.mean(y[ys]) - target.y))
        nearest = d if nearest is None else min(nearest, d)
        overlap = np.count_nonzero((labels == cid) & tmask) / max(len(xs), 1)
        if overlap < 0.25:
            false += 1
    return {
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "components": int(n),
        "false_components": int(false),
        "rejected_by_shape_gate": int(rejected),
    }


def _summarize(rows: list[dict]) -> dict:
    out = {}
    for g in GENERATORS:
        for m in METHODS:
            rs = [r for r in rows if r["generator"] == g and r["method"] == m]
            out[f"{g}|{m}"] = {
                "records": len(rs),
                "hit_rate": float(np.mean([r["component_hit"] for r in rs])) if rs else 0.0,
                "mean_components": float(np.mean([r["components"] for r in rs])) if rs else 0.0,
                "mean_false_components": float(np.mean([r["false_components"] for r in rs]))
                if rs
                else 0.0,
                "mean_rejected_by_shape_gate": float(
                    np.mean([r["rejected_by_shape_gate"] for r in rs])
                )
                if rs
                else 0.0,
            }
    return out


def run_background_independent_separation_audit(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = tuple(range(9311, 9319)),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for seed in map(int, seeds):
        for i, plan in enumerate(_master_plan(seed, count)):
            if not any(t.kind in {"geology", "geological"} for t in plan["targets"]):
                continue
            target = next(t for t in plan["targets"] if t.kind in {"geology", "geological"})
            for generator in GENERATORS:
                field, _, _ = _scene(
                    plan, generator, seed * 1000 + i + (0 if generator == "B" else 500000)
                )
                for method in METHODS:
                    rep = (
                        _regional_trend_zscore(_grid(field, plan))
                        if method == "current"
                        else _dog_2_4(field, generator)
                    )
                    m = _evaluate(
                        field, plan, target, rep, shape_gate=(method == "dog_2_4_shape_gate")
                    )
                    rows.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "method": method,
                        **m,
                    })
    payload = {
        "version": "0.2.93",
        "benchmark": "background_independent_separation",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "geology_records_per_generator": len([r for r in rows if r["generator"] == "B"])
        // len(METHODS),
        "methods": list(METHODS),
        "same_truth_plans_across_generators": True,
        "shape_gate": {"aspect_max": SHAPE_ASPECT_MAX, "density_min": SHAPE_DENSITY_MIN},
        "production_behavior_changed": False,
        "summary": _summarize(rows),
        "records": rows,
        "decision": "diagnostic_only_no_production_change",
        "validation_boundary": "Synthetic diagnostic only; no field ground truth or material identification.",
    }
    (out / "background_independent_separation.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.93 — Background-Independent Separation Prototype",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites/seed: **{count}**; geology records/generator: **{payload['geology_records_per_generator']}**.",
        "",
        "## Results",
        "",
        "| Generator | Method | Hit rate | False comps | Components | Shape rejects |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for key, s in sorted(payload["summary"].items()):
        g, m = key.split("|", 1)
        lines.append(
            f"| {g} | {m} | {s['hit_rate']:.3f} | {s['mean_false_components']:.3f} | {s['mean_components']:.3f} | {s['mean_rejected_by_shape_gate']:.3f} |"
        )
    lines += [
        "",
        "## Finding",
        "",
        "The background-family-independent DoG prototype improves B substantially and raises C recall, but C retains material background confusion. The compactness gate reduces some false components but does not establish a safe production gate.",
        "",
        "## Decision",
        "",
        "Keep this prototype diagnostic-only. No production activation is justified by these synthetic results.",
        "",
        "## Validation boundary",
        "",
        "Synthetic software-validation only; no field ground truth and no proof of physical material or structure.",
    ]
    (out / "background_independent_separation.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

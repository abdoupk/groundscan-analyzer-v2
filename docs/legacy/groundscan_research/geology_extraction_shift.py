"""Generator-shift audit for broad/geological extraction, v0.2.84.

Diagnostic-only. Separates broad-component extraction coverage from downstream
classification so generator-shift failures cannot be incorrectly treated as
classifier failures. No production detector behavior is changed.
"""

from __future__ import annotations

import json
from math import hypot
from pathlib import Path

import numpy as np

from groundscan.core import detect_anomalies, detect_artifacts, extract_candidates
from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.grid import reconstruct_grid
from groundscan_research.synthetic_generator_independence import _generate, _master_plan

GENERATORS = ("A", "B", "C")

CONFIGS = (
    {
        "name": "production_broad",
        "threshold": 2.1,
        "min_area_fraction": 0.02,
        "min_span_fraction": 0.18,
    },
    {
        "name": "relaxed_broad",
        "threshold": 1.8,
        "min_area_fraction": 0.01,
        "min_span_fraction": 0.14,
    },
)


def _generate_a(plan, seed):
    from groundscan.validation.synthetic_core.core import SyntheticScenario, generate_scan

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
    return generate_scan(spec)


def _nearest_component_centroid(labels, grid, target):
    best = None
    for cid in range(1, int(labels.max()) + 1):
        ys, xs = np.where(labels == cid)
        if len(xs) == 0:
            continue
        cx = float(np.mean(grid.x_centers[xs]))
        cy = float(np.mean(grid.y_centers[ys]))
        d = hypot(cx - target.x, cy - target.y)
        row = {"component": int(cid), "x": cx, "y": cy, "distance_m": d, "area_cells": int(len(xs))}
        if best is None or d < best["distance_m"]:
            best = row
    return best


def _broad_only_candidates(grid, threshold, area_fraction, span_fraction):
    z = _regional_trend_zscore(grid)
    labels, broadness, n = _broad_component_selection(
        grid, z, threshold, area_fraction, span_fraction
    )
    # Build an AnomalyMap containing only raw broad components, before local-overlap suppression.
    from groundscan.core.anomaly import AnomalyMap

    persistence = (np.isfinite(z) & (np.abs(z) >= 2.0)).astype(float)
    amap = AnomalyMap(
        zscore=z.copy(),
        labels=labels,
        n_components=n,
        threshold=threshold,
        residual=z.copy(),
        persistence=persistence,
        component_types={int(i): "broad" for i in range(1, n + 1)},
        broad_zscore=z,
        broad_persistence=persistence,
    )
    artifacts = detect_artifacts(grid, amap)
    cands = extract_candidates(grid, amap, artifacts)
    return labels, cands


def _run_one(scan, plan, cfg):
    grid = reconstruct_grid(scan)
    labels_raw, cands_raw = _broad_only_candidates(
        grid, cfg["threshold"], cfg["min_area_fraction"], cfg["min_span_fraction"]
    )
    prod = detect_anomalies(
        grid,
        threshold=3.0,
        min_size=3,
        background_method="multiscale",
        scales=(3, 5, 9, 15),
        connectivity=8,
    )
    prod_broad = [
        c
        for c in extract_candidates(grid, prod, detect_artifacts(grid, prod))
        if getattr(c, "scale_class", "") == "broad"
    ]
    rows = []
    for ti, t in enumerate(plan["targets"]):
        if t.kind not in ("geology", "geological"):
            continue
        raw = _nearest_component_centroid(labels_raw, grid, t)
        raw_hit = raw is not None and raw["distance_m"] <= 3.0
        pc = min(prod_broad, key=lambda c: hypot(c.x_center - t.x, c.y_center - t.y), default=None)
        pc_d = None if pc is None else hypot(pc.x_center - t.x, pc.y_center - t.y)
        prod_hit = pc_d is not None and pc_d <= 3.0
        rows.append({
            "target_index": ti,
            "raw_pre_suppression_hit": raw_hit,
            "production_broad_hit": prod_hit,
            "raw_nearest": raw,
            "production_nearest": None
            if pc is None
            else {
                "x": float(pc.x_center),
                "y": float(pc.y_center),
                "distance_m": float(pc_d),
                "broadness": float(pc.broadness_score),
            },
        })
    return rows, len(cands_raw), len(prod_broad)


def run_geology_extraction_shift(out_dir: str | Path, *, seeds=(8401, 8402), count=24):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for seed in map(int, seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            for g in GENERATORS:
                scan, _truth = (
                    _generate_a(plan, seed * 1000 + i)
                    if g == "A"
                    else _generate(
                        plan, generator=g, seed=seed * 1000 + i + (0 if g == "B" else 500000)
                    )
                )
                for cfg in CONFIGS:
                    rows, raw_count, prod_count = _run_one(scan, plan, cfg)
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": g,
                        "config": cfg["name"],
                        "geology_targets": len(rows),
                        "rows": rows,
                        "raw_broad_candidates": raw_count,
                        "production_broad_candidates": prod_count,
                    })
    agg = {}
    for g in GENERATORS:
        for cfg in CONFIGS:
            rr = [r for r in records if r["generator"] == g and r["config"] == cfg["name"]]
            geo = [row for r in rr for row in r["rows"]]
            agg.setdefault(g, {})[cfg["name"]] = {
                "sites": len(rr),
                "targets": len(geo),
                "pre_suppression_hit_rate": sum(x["raw_pre_suppression_hit"] for x in geo)
                / len(geo)
                if geo
                else 0.0,
                "production_broad_hit_rate": sum(x["production_broad_hit"] for x in geo) / len(geo)
                if geo
                else 0.0,
                "mean_raw_candidates": float(np.mean([r["raw_broad_candidates"] for r in rr]))
                if rr
                else 0.0,
                "mean_production_broad_candidates": float(
                    np.mean([r["production_broad_candidates"] for r in rr])
                )
                if rr
                else 0.0,
            }
    payload = {
        "version": "0.2.84",
        "benchmark": "geology_extraction_shift",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "summary": agg,
        "method": {
            "production_behavior_changed": False,
            "classifier_tested": False,
            "focus": "broad/geological extraction before vs after local-overlap suppression",
            "same_truth_plans_across_generators": True,
        },
        "validation_boundary": "Synthetic extraction diagnostics only; no field ground truth.",
        "decision": "diagnostic_only_no_production_change",
    }
    (out / "geology_extraction_shift.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.84 — Geological Extraction Generator-Shift Audit",
        "",
        "Diagnostic-only; production detector and classifier are unchanged.",
        "",
        "| Generator | Config | Geological targets | Pre-suppression broad hit | Production broad hit | Mean raw broad candidates | Mean production broad candidates |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for cfg in CONFIGS:
            s = agg[g][cfg["name"]]
            lines.append(
                f"| {g} | {cfg['name']} | {s['targets']} | {s['pre_suppression_hit_rate']:.3f} | {s['production_broad_hit_rate']:.3f} | {s['mean_raw_candidates']:.2f} | {s['mean_production_broad_candidates']:.2f} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "The pre-suppression channel answers whether a geology-shaped broad component exists before local-overlap suppression. A large gap between pre-suppression and production hit rate indicates extraction suppression rather than classifier failure.",
        "",
        "Generator B/C results are intentionally treated as generator-shift diagnostics. No threshold is promoted from these results.",
    ]
    (out / "geology_extraction_shift.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

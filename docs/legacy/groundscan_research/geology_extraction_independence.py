"""Generator-independent broad-response extraction audit, v0.2.85.

Diagnostic-only. Uses the fixed target plans from v0.2.82 and the three forward
models (A/B/C) to classify geology outcomes into distinct upstream/downstream
failure states:

- correct_broad: a broad geology candidate is produced near the truth;
- suppressed_broad: a pre-suppression broad component is present but the normal
  production broad channel does not keep a nearby broad candidate;
- present_misclassified: a nearby production candidate exists but is not
  geological-like/broad;
- component_absent: no broad component is found before local-overlap suppression;
- extraction_miss: no production candidate is found near the target.

No production detector, classifier, scoring, or thresholds are changed.
"""

from __future__ import annotations

import json
from math import hypot
from pathlib import Path
from statistics import mean

import numpy as np

from groundscan.core import detect_anomalies, detect_artifacts, extract_candidates
from groundscan.core.anomaly import AnomalyMap, _broad_component_selection, _regional_trend_zscore
from groundscan.core.classify import classify_candidate
from groundscan.core.grid import reconstruct_grid
from groundscan.validation.synthetic_core.core import (
    SyntheticScenario,
    generate_scan,
)
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
RADIUS_M = 3.0


def _generate_a(plan: dict, seed: int):
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


def _broad_labels(grid, threshold: float, min_area_fraction: float, min_span_fraction: float):
    z = _regional_trend_zscore(grid)
    labels, _, n = _broad_component_selection(
        grid, z, threshold, min_area_fraction, min_span_fraction
    )
    persistence = (np.isfinite(z) & (np.abs(z) >= 2.0)).astype(float)
    amap = AnomalyMap(
        zscore=z.copy(),
        labels=labels,
        n_components=n,
        threshold=threshold,
        residual=z.copy(),
        persistence=persistence,
        component_types={int(i): "broad" for i in range(1, n + 1)},
        broad_zscore=z.copy(),
        broad_persistence=persistence,
    )
    artifacts = detect_artifacts(grid, amap)
    cands = extract_candidates(grid, amap, artifacts)
    return z, labels, cands


def _nearest(cands, target):
    nearest = None
    for c in cands:
        d = hypot(float(c.x_center) - target.x, float(c.y_center) - target.y)
        if nearest is None or d < nearest[0]:
            nearest = (d, c)
    return nearest


def _nearest_component(labels, grid, target):
    best = None
    max_label = int(np.nanmax(labels)) if np.size(labels) else 0
    for cid in range(1, max_label + 1):
        ys, xs = np.where(labels == cid)
        if len(xs) == 0:
            continue
        cx = float(np.mean(grid.x_centers[xs]))
        cy = float(np.mean(grid.y_centers[ys]))
        d = hypot(cx - target.x, cy - target.y)
        candidate = {
            "component": int(cid),
            "x": cx,
            "y": cy,
            "distance_m": d,
            "area_cells": int(len(xs)),
        }
        if best is None or d < best["distance_m"]:
            best = candidate
    return best


def _scan_for_generator(plan: dict, generator: str, seed: int):
    if generator == "A":
        scan, _ = _generate_a(plan, seed)
    else:
        offset = 0 if generator == "B" else 500_000
        scan, _ = _generate(plan, generator=generator, seed=seed + offset)
    return scan


def _classify_target(scan, target, *, cfg):
    grid = reconstruct_grid(scan)
    z, labels, raw_broad_candidates = _broad_labels(
        grid,
        cfg["threshold"],
        cfg["min_area_fraction"],
        cfg["min_span_fraction"],
    )
    raw_component = _nearest_component(labels, grid, target)
    raw_hit = raw_component is not None and raw_component["distance_m"] <= RADIUS_M

    production = detect_anomalies(
        grid,
        threshold=3.0,
        min_size=3,
        background_method="multiscale",
        scales=(3, 5, 9, 15),
        connectivity=8,
    )
    production_candidates = [
        classify_candidate(c)
        for c in extract_candidates(grid, production, detect_artifacts(grid, production))
    ]
    nearby = [
        c
        for c in production_candidates
        if hypot(float(c.x_center) - target.x, float(c.y_center) - target.y) <= RADIUS_M
    ]
    nearby_broad = [c for c in nearby if getattr(c, "scale_class", "") == "broad"]
    nearby_geo = [
        c for c in nearby_broad if getattr(c, "pattern_hypothesis", "") == "geological-like"
    ]

    if nearby_geo:
        state = "correct_broad"
    elif raw_hit and not nearby_broad:
        state = "suppressed_broad"
    elif nearby:
        state = "present_misclassified"
    elif not raw_hit:
        state = "component_absent"
    else:
        state = "extraction_miss"

    nearest_prod = _nearest(production_candidates, target)
    return {
        "state": state,
        "raw_pre_suppression_hit": bool(raw_hit),
        "raw_component": raw_component,
        "nearby_candidate_count": len(nearby),
        "nearby_broad_count": len(nearby_broad),
        "nearby_geological_count": len(nearby_geo),
        "nearest_production": None
        if nearest_prod is None
        else {
            "distance_m": float(nearest_prod[0]),
            "pattern": getattr(nearest_prod[1], "pattern_hypothesis", ""),
            "scale_class": getattr(nearest_prod[1], "scale_class", ""),
            "broadness": float(getattr(nearest_prod[1], "broadness_score", 0.0)),
            "anomaly_score": float(getattr(nearest_prod[1], "anomaly_score", 0.0)),
        },
        "raw_candidate_count": int(len(raw_broad_candidates)),
        "production_candidate_count": int(len(production_candidates)),
        "production_broad_candidate_count": int(len(nearby_broad)),
        "z_local": float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else None,
    }


def run_geology_extraction_independence(out_dir: str | Path, *, seeds=(8501, 8502), count=24):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []

    for seed in map(int, seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            geology_targets = [t for t in plan["targets"] if t.kind in {"geology", "geological"}]
            for generator in GENERATORS:
                scan = _scan_for_generator(plan, generator, seed * 1000 + i)
                for cfg in CONFIGS:
                    for ti, target in enumerate(geology_targets):
                        result = _classify_target(scan, target, cfg=cfg)
                        records.append({
                            "seed": seed,
                            "site": plan["scenario"],
                            "generator": generator,
                            "config": cfg["name"],
                            "target_index": ti,
                            **result,
                        })

    summary = {}
    states = (
        "correct_broad",
        "suppressed_broad",
        "present_misclassified",
        "component_absent",
        "extraction_miss",
    )
    for generator in GENERATORS:
        summary[generator] = {}
        for cfg in CONFIGS:
            rows = [
                r for r in records if r["generator"] == generator and r["config"] == cfg["name"]
            ]
            counts = {s: sum(r["state"] == s for r in rows) for s in states}
            summary[generator][cfg["name"]] = {
                "targets": len(rows),
                "state_counts": counts,
                "correct_rate": counts["correct_broad"] / len(rows) if rows else 0.0,
                "pre_suppression_rate": sum(r["raw_pre_suppression_hit"] for r in rows) / len(rows)
                if rows
                else 0.0,
                "mean_production_candidates": mean(r["production_candidate_count"] for r in rows)
                if rows
                else 0.0,
            }

    payload = {
        "version": "0.2.85",
        "benchmark": "geology_extraction_independence",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "match_radius_m": RADIUS_M,
        "summary": summary,
        "method": {
            "same_truth_plans_across_generators": True,
            "production_behavior_changed": False,
            "classifier_tuning": False,
            "threshold_tuning": False,
            "diagnostic_only": True,
            "state_definitions": {
                "correct_broad": "nearby production broad candidate with geological-like hypothesis",
                "suppressed_broad": "broad component exists pre-suppression but no nearby production broad candidate",
                "present_misclassified": "nearby production candidate exists but is not geological-like/broad",
                "component_absent": "no nearby pre-suppression broad component",
                "extraction_miss": "reserved for cases with a pre-suppression component but no nearby production candidate",
            },
        },
        "validation_boundary": "Synthetic software diagnostic only; no field ground truth.",
        "decision": "no production extraction change",
        "records": records,
    }
    (out / "geology_extraction_independence.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.85 — Geological Extraction Independence Audit",
        "",
        "> Diagnostic-only. No production detector, classifier, scoring, registration, or threshold changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per seed: **{count}**; match radius: **{RADIUS_M:.1f} m**.",
        "",
        "## Outcome states",
        "",
        "| State | Meaning |",
        "|---|---|",
        "| correct_broad | Nearby production broad + geological-like candidate |",
        "| suppressed_broad | Broad component present before suppression, then lost |",
        "| present_misclassified | Nearby candidate exists, but not broad/geological-like |",
        "| component_absent | No broad component near truth before suppression |",
        "| extraction_miss | Reserved for an upstream component that still disappears before production |",
        "",
        "## Aggregate",
        "",
        "| Generator | Config | Targets | Correct | Suppressed | Misclassified | Component absent | Extraction miss | Correct rate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for cfg in CONFIGS:
            s = summary[g][cfg["name"]]
            c = s["state_counts"]
            lines.append(
                f"| {g} | {cfg['name']} | {s['targets']} | {c['correct_broad']} | {c['suppressed_broad']} | "
                f"{c['present_misclassified']} | {c['component_absent']} | {c['extraction_miss']} | {s['correct_rate']:.3f} |"
            )

    lines += [
        "",
        "## Interpretation",
        "",
        "The key distinction is whether a geology-shaped broad component exists before production suppression. This prevents a classifier failure from being confused with an upstream extraction failure.",
        "",
        "Generator-shift differences are treated as a validation finding. The audit does not justify changing thresholds to match any generator and does not establish field detection accuracy.",
        "",
        "## Decision",
        "",
        "Keep production behavior unchanged. Use the state breakdown to design the next broad-response representation experiment.",
    ]
    (out / "geology_extraction_independence.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

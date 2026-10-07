"""Generator-C mechanism isolation audit for v0.2.90.

Diagnostic-only. This module does not alter production detector, classifier,
threshold, registration, fusion, scoring, or screening behavior. It isolates
the geological broad-response loss by introducing the independent synthetic
scene ingredients one stage at a time and measuring the existing production
broad representation after each stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.grid import Grid2D
from groundscan.models import ScanData, ScanMetadata
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
STAGES = (
    "target_only_forward",
    "background_only_forward",
    "target_plus_background_clean_linear",
    "target_plus_background_noisy_linear",
    "post_nonlinearity",
    "post_sparse_impulses",
    "full_scene",
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


def _scan(field: np.ndarray, plan: dict, generator: str, stage: str) -> ScanData:
    ny, nx = field.shape
    x = np.linspace(0.0, float(plan["width"]), nx)
    y = np.linspace(0.0, float(plan["height"]), ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=np.full(field.size, 5.0),
        signal=field.ravel(),
        grid_i=np.tile(np.arange(nx, dtype=float), ny),
        grid_j=np.repeat(np.arange(ny, dtype=float), nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device=f"synthetic-independent-{generator}",
            field_length_m=float(plan["width"]),
            field_width_m=float(plan["height"]),
            notes=f"v0.2.90 mechanism isolation {generator}/{stage}",
            source_file=f"synthetic:{generator}:{plan['scenario']}:v090:{stage}",
        ),
    )


def _stage_fields(
    plan: dict, generator: str, seed: int, target_index: int
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    width, height = float(plan["width"]), float(plan["height"])
    nx, ny = int(plan["nx"]), int(plan["ny"])
    x = np.linspace(0.0, width, nx)
    y = np.linspace(0.0, height, ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    targets = plan["targets"]
    response_fn = _response_b if generator == "B" else _response_c
    responses = [response_fn(xx, yy, t) for t in targets]
    geology = responses[target_index]
    other = sum((r for i, r in enumerate(responses) if i != target_index), np.zeros_like(geology))
    background = _background_b(xx, yy) if generator == "B" else _background_c(xx, yy)
    noise = rng.normal(0.0, float(plan["noise_sigma"]), size=geology.shape)

    target_forward = _compress_b(142.0 + geology) if generator == "B" else geology.copy()
    background_forward = _compress_b(background) if generator == "B" else background.copy()
    clean_linear = background + geology
    noisy_linear = clean_linear + noise
    post_nonlinearity = _compress_b(noisy_linear) if generator == "B" else noisy_linear.copy()

    post_sparse_impulses = post_nonlinearity.copy()
    if generator == "C":
        impulse_mask = rng.random(post_sparse_impulses.shape) < 0.008
        if np.any(impulse_mask):
            post_sparse_impulses[impulse_mask] += rng.normal(0.0, 3.5, size=int(impulse_mask.sum()))

    full_linear = background + geology + other + noise
    full_scene = _compress_b(full_linear) if generator == "B" else full_linear.copy()
    if generator == "C":
        impulse_mask = rng.random(full_scene.shape) < 0.008
        if np.any(impulse_mask):
            full_scene[impulse_mask] += rng.normal(0.0, 3.5, size=int(impulse_mask.sum()))

    return {
        "target_only_forward": target_forward,
        "background_only_forward": background_forward,
        "target_plus_background_clean_linear": clean_linear,
        "target_plus_background_noisy_linear": noisy_linear,
        "post_nonlinearity": post_nonlinearity,
        "post_sparse_impulses": post_sparse_impulses,
        "full_scene": full_scene,
    }


def _metrics(field: np.ndarray, plan: dict, target, stage: str) -> dict:
    grid = _grid(field, plan)
    z = _regional_trend_zscore(grid)
    labels, _, n = _broad_component_selection(
        grid, z, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    mask = _target_mask(plan, target, field.shape)
    valid = np.isfinite(z)
    vals = np.abs(z[mask & valid])
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    distances: list[float] = []
    false_components = 0
    target_overlap_components = 0
    for cid in range(1, int(n) + 1):
        ys, xs = np.where(labels == cid)
        if not len(xs):
            continue
        d = float(np.hypot(np.mean(x[xs]) - float(target.x), np.mean(y[ys]) - float(target.y)))
        distances.append(d)
        overlap = float(np.count_nonzero((labels == cid) & mask)) / max(
            int(np.count_nonzero(labels == cid)), 1
        )
        if overlap >= 0.25:
            target_overlap_components += 1
        else:
            false_components += 1
    nearest = min(distances) if distances else None
    outside = valid & ~mask
    outside_abs = np.abs(z[outside]) if np.any(outside) else np.array([], dtype=float)
    return {
        "stage": stage,
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "nearest_component_distance_m": nearest,
        "components": int(n),
        "target_overlap_components": int(target_overlap_components),
        "false_components_away": int(false_components),
        "target_peak_abs_z": float(np.max(vals)) if vals.size else 0.0,
        "target_mean_abs_z": float(np.mean(vals)) if vals.size else 0.0,
        "target_fraction_abs_z_ge_2": float(np.mean(vals >= 2.0)) if vals.size else 0.0,
        "outside_p95_abs_z": float(np.nanpercentile(outside_abs, 95)) if outside_abs.size else 0.0,
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
        "mean_target_overlap_components": mean("target_overlap_components"),
        "mean_false_components_away": mean("false_components_away"),
        "mean_outside_p95_abs_z": mean("outside_p95_abs_z"),
    }


def run_generator_c_mechanism_isolation(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = tuple(range(9001, 9009)),
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
                stages = _stage_fields(
                    plan,
                    generator,
                    seed * 1000 + i + (0 if generator == "B" else 500_000),
                    target_index,
                )
                for stage, field in stages.items():
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        **_metrics(field, plan, target, stage),
                    })

    summary: dict[str, dict[str, dict]] = {g: {} for g in GENERATORS}
    for g in GENERATORS:
        for stage in STAGES:
            summary[g][stage] = _aggregate([
                r for r in records if r["generator"] == g and r["stage"] == stage
            ])

    transitions: dict[str, list[dict]] = {g: [] for g in GENERATORS}
    for g in GENERATORS:
        for prev, cur in zip(STAGES[:-1], STAGES[1:]):
            a, b = summary[g][prev], summary[g][cur]
            transitions[g].append({
                "from": prev,
                "to": cur,
                "hit_rate_delta": b["component_hit_rate"] - a["component_hit_rate"],
                "peak_delta": b["mean_peak_abs_z"] - a["mean_peak_abs_z"],
                "target_abs_z_delta": b["mean_target_abs_z"] - a["mean_target_abs_z"],
                "false_component_delta": b["mean_false_components_away"]
                - a["mean_false_components_away"],
            })

    first_loss = {}
    for g in GENERATORS:
        base = summary[g]["target_only_forward"]["component_hit_rate"]
        clean = summary[g]["target_plus_background_clean_linear"]["component_hit_rate"]
        post_clean_transitions = [
            tr
            for tr in transitions[g]
            if tr["from"]
            in {
                "target_plus_background_clean_linear",
                "target_plus_background_noisy_linear",
                "post_nonlinearity",
                "post_sparse_impulses",
            }
        ]
        downstream_first = None
        for tr in post_clean_transitions:
            if tr["hit_rate_delta"] < -0.05:
                downstream_first = tr
                break
        first_loss[g] = {
            "target_only_hit_rate": base,
            "clean_target_background_hit_rate": clean,
            "background_interaction_hit_rate_delta": clean - base,
            "first_downstream_material_hit_rate_drop": downstream_first,
        }

    payload = {
        "version": "0.2.90",
        "benchmark": "generator_c_mechanism",
        "seeds": list(map(int, seeds)),
        "count_per_seed": int(count),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "production_detector_changed": False,
        "production_thresholds_changed": False,
        "production_classifier_changed": False,
        "production_registration_changed": False,
        "production_fusion_changed": False,
        "stages": list(STAGES),
        "summary": summary,
        "transitions": transitions,
        "first_material_hit_rate_drop": first_loss,
        "method": {
            "representation": "current production regional broad representation and broad component selection",
            "isolation": "introduce geological response, background, noise, nonlinearity/sparse contamination, then remaining targets",
            "purpose": "locate the first stage at which a geology response becomes non-extractable under Generator B/C",
        },
        "validation_boundary": "Synthetic diagnostic only; no field ground truth, device calibration, material identification, or proof of geological detection.",
        "decision": "diagnostic_only_no_production_change",
        "records": records,
    }
    (out / "generator_c_mechanism.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.90 — Generator Mechanism Isolation",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites/seed: **{count}**; geology records/generator: **{sum(r['generator'] == 'B' for r in records) // len(STAGES)}**.",
        "",
        "## Stage results",
        "",
        "| Generator | Stage | Records | Broad hit | Mean peak | Mean target abs-z | ≥2 fraction | Mean comps | False comps |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for stage in STAGES:
            s = summary[g][stage]
            lines.append(
                f"| {g} | {stage} | {s['records']} | {s['component_hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | "
                f"{s['mean_target_abs_z']:.3f} | {s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} | {s['mean_false_components_away']:.2f} |"
            )
    lines += [
        "",
        "## Transition analysis",
        "",
        "| Generator | From | To | Hit-rate Δ | Peak Δ | Target abs-z Δ | False comps Δ |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for tr in transitions[g]:
            lines.append(
                f"| {g} | {tr['from']} | {tr['to']} | {tr['hit_rate_delta']:+.3f} | {tr['peak_delta']:+.3f} | {tr['target_abs_z_delta']:+.3f} | {tr['false_component_delta']:+.2f} |"
            )
    lines += ["", "## First material loss", ""]
    for g in GENERATORS:
        f = first_loss[g]
        lines.append(
            f"- **{g}** target-only broad hit: **{f['target_only_hit_rate']:.3f}**; after clean background: **{f['clean_target_background_hit_rate']:.3f}** (background-interaction Δ **{f['background_interaction_hit_rate_delta']:+.3f}**)"
        )
        if f["first_downstream_material_hit_rate_drop"]:
            tr = f["first_downstream_material_hit_rate_drop"]
            lines.append(
                f"  - first >5-point downstream drop: `{tr['from']} → {tr['to']}` ({tr['hit_rate_delta']:+.3f})"
            )
        else:
            lines.append("  - no >5-point downstream stage drop detected")
    lines += [
        "",
        "## Interpretation",
        "",
        "The same truth plans are used for B and C. The audit changes one synthetic ingredient at a time while keeping the current production broad representation fixed.",
        "",
        "A large loss at `target_plus_background_clean_linear` implicates background interaction. A later loss at `post_nonlinearity` implicates nonlinear acquisition. A loss only at `full_scene` implicates interaction with other targets/final scene complexity.",
        "",
        "## Decision",
        "",
        "Diagnostic only. No production change is justified by this audit alone.",
        "",
        "## Validation boundary",
        "",
        "These are synthetic software-validation measurements. They do not establish real-device field detection performance or prove a geological structure, cavity, tunnel, metal, gold, or mineral in field data.",
    ]
    (out / "generator_c_mechanism.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

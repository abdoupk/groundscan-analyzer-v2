"""Diagnostic adaptive-scale background separation audit for v0.2.89.

No production detector/classifier/threshold/registration/fusion behavior is
changed. This audit tests whether an unsupervised multiscale representation
can recover broad responses more consistently than a fixed background scale.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.background import robust_zscore
from groundscan.core.grid import Grid2D
from groundscan.validation.synthetic_core.core import SyntheticTarget
from groundscan_research.background_separation_audit import (
    BROAD_THRESHOLD,
    GENERATORS,
    MATCH_RADIUS_M,
    MIN_AREA_FRACTION,
    MIN_SPAN_FRACTION,
    _gaussian_background_residual,
    _scene,
    _target_mask,
)
from groundscan_research.synthetic_generator_independence import _master_plan

SCALES = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 14.0)
REPRESENTATIONS = (
    "current",
    "fixed_bg4",
    "fixed_bg6",
    "fixed_bg8",
    "fixed_bg10",
    "fixed_bg12",
    "fixed_bg14",
    "multiscale_max_abs",
    "multiscale_stable",
    "broad_consensus_2of3",
    "oracle_best_scale",
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


def _stable_multiscale(stack: np.ndarray) -> np.ndarray:
    """Select a scale using adjacent-scale persistence and sign agreement.

    stack shape: [n_scales, ny, nx], robust-z residual maps.
    The selected score rewards a response that remains strong at neighboring
    scales with the same sign, instead of a single-scale spike.
    """
    abs_stack = np.abs(stack)
    signs = np.sign(stack)
    n = stack.shape[0]
    persistence = np.zeros_like(abs_stack)
    for i in range(n):
        peers = []
        if i > 0:
            peers.append(abs_stack[i - 1])
        if i + 1 < n:
            peers.append(abs_stack[i + 1])
        if peers:
            persistence[i] = np.minimum.reduce([abs_stack[i], *peers])
        else:
            persistence[i] = abs_stack[i]
        if i > 0:
            persistence[i] *= signs[i] == signs[i - 1]
        if i + 1 < n:
            persistence[i] *= signs[i] == signs[i + 1]
    idx = np.argmax(persistence, axis=0)
    chosen = np.take_along_axis(stack, idx[None, ...], axis=0)[0]
    # Preserve only genuinely persistent responses; isolated-scale spikes are
    # intentionally attenuated rather than promoted to the broad channel.
    chosen_p = np.take_along_axis(persistence, idx[None, ...], axis=0)[0]
    scale_conf = np.clip(chosen_p / (np.max(abs_stack, axis=0) + 1e-9), 0.0, 1.0)
    return chosen * scale_conf


def _multiscale_max_abs(stack: np.ndarray) -> np.ndarray:
    idx = np.argmax(np.abs(stack), axis=0)
    return np.take_along_axis(stack, idx[None, ...], axis=0)[0]


def _broad_consensus(stack: np.ndarray, plan: dict, min_support: int = 2) -> np.ndarray:
    """Build a diagnostic representation from agreement of broad components.

    A pixel belongs to the representation when its scale-specific broad
    component is supported by at least ``min_support`` neighboring scales.
    Values retain the sign/strength of the strongest supporting scale.
    """
    broad_masks = []
    for s in stack:
        labels, _, n = _broad_component_selection(
            _grid(np.zeros_like(s), plan), s, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
        )
        broad_masks.append(labels > 0)
    support = np.sum(np.stack(broad_masks, axis=0), axis=0)
    chosen = _multiscale_max_abs(stack)
    out = np.where(support >= int(min_support), chosen, 0.0)
    return robust_zscore(out)


def _oracle_best_scale(
    stack: np.ndarray, field: np.ndarray, plan: dict, target: SyntheticTarget
) -> tuple[np.ndarray, float, dict]:
    candidates = []
    for scale, rep in zip(SCALES, stack):
        stats = _metrics(field, plan, target, rep)
        candidates.append((
            bool(stats["component_hit"]),
            float(stats["target_mean_abs_z"]),
            float(-stats["false_components_away_from_target"]),
            float(scale),
            rep,
            stats,
        ))
    best = max(candidates, key=lambda x: (x[0], x[1], x[2], -abs(x[3] - 7.0)))
    return best[4], best[3], best[5]


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
    outside = valid & ~mask
    return {
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "nearest_component_distance_m": nearest,
        "components": int(n),
        "false_components_away_from_target": int(false_components),
        "target_peak_abs_z": float(np.max(vals)) if vals.size else 0.0,
        "target_mean_abs_z": float(np.mean(vals)) if vals.size else 0.0,
        "target_fraction_abs_z_ge_2": float(np.mean(vals >= 2.0)) if vals.size else 0.0,
        "outside_p95_abs_z": float(np.nanpercentile(np.abs(representation[outside]), 95))
        if np.any(outside)
        else 0.0,
    }


def _representation(
    field: np.ndarray,
    plan: dict,
    variant: str,
    background: np.ndarray,
    generator: str,
    target: SyntheticTarget,
) -> tuple[np.ndarray, float | None, dict | None]:
    if variant == "current":
        return _regional_trend_zscore(_grid(field, plan)), None, None
    if variant.startswith("fixed_bg"):
        scale = float(variant.replace("fixed_bg", ""))
        return _gaussian_background_residual(field, scale, 2.0), scale, None
    stack = np.stack([_gaussian_background_residual(field, s, 2.0) for s in SCALES], axis=0)
    if variant == "multiscale_max_abs":
        return _multiscale_max_abs(stack), None, None
    if variant == "multiscale_stable":
        return _stable_multiscale(stack), None, None
    if variant == "broad_consensus_2of3":
        # 2-of-3 is interpreted as at least two of the scale neighbors around
        # the selected family; the full bank is used as a stable pool here.
        return _broad_consensus(stack, plan, min_support=2), None, None
    if variant == "oracle_best_scale":
        rep, scale, stats = _oracle_best_scale(stack, field, plan, target)
        return rep, scale, stats
    raise ValueError(variant)


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
        "mean_outside_p95_abs_z": mean("outside_p95_abs_z"),
    }


def run_adaptive_scale_separation_audit(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = (8901, 8902, 8903, 8904),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for seed in map(int, seeds):
        plans = _master_plan(seed, count)
        for i, plan in enumerate(plans):
            geo = [
                (j, t) for j, t in enumerate(plan["targets"]) if t.kind in {"geology", "geological"}
            ]
            if not geo:
                continue
            target_index, target = geo[0]
            for generator in GENERATORS:
                observed, background = _scene(
                    plan,
                    generator,
                    seed * 1000 + i + (0 if generator == "B" else 500_000),
                    target_index,
                )
                for variant in REPRESENTATIONS:
                    rep, selected_scale, oracle_stats = _representation(
                        observed, plan, variant, background, generator, target
                    )
                    stats = _metrics(observed, plan, target, rep)
                    records.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "representation": variant,
                        "selected_scale": selected_scale,
                        "oracle_scale_stats": oracle_stats,
                        **stats,
                    })

    summary = {g: {} for g in GENERATORS}
    for g in GENERATORS:
        for rep in REPRESENTATIONS:
            rows = [r for r in records if r["generator"] == g and r["representation"] == rep]
            summary[g][rep] = _aggregate(rows)

    oracle_scale_counts = {g: {} for g in GENERATORS}
    for g in GENERATORS:
        for r in records:
            if r["generator"] == g and r["representation"] == "oracle_best_scale":
                key = str(r["selected_scale"])
                oracle_scale_counts[g][key] = oracle_scale_counts[g].get(key, 0) + 1

    delta = {}
    for g in GENERATORS:
        base = summary[g]["current"]
        delta[g] = {}
        for rep in REPRESENTATIONS:
            delta[g][rep] = {
                "hit_rate_delta": summary[g][rep]["component_hit_rate"]
                - base["component_hit_rate"],
                "false_component_delta": summary[g][rep]["mean_false_components_away"]
                - base["mean_false_components_away"],
                "outside_p95_delta": summary[g][rep]["mean_outside_p95_abs_z"]
                - base["mean_outside_p95_abs_z"],
            }

    payload = {
        "version": "0.2.89",
        "benchmark": "adaptive_scale_separation",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "production_detector_changed": False,
        "production_thresholds_changed": False,
        "production_classifier_changed": False,
        "production_registration_changed": False,
        "production_fusion_changed": False,
        "scale_bank": list(SCALES),
        "representations": list(REPRESENTATIONS),
        "summary": summary,
        "delta_vs_current": delta,
        "oracle_best_scale_counts": oracle_scale_counts,
        "records": records,
        "method": {
            "fixed_scales": "Gaussian background subtraction followed by sigma=2 response smoothing",
            "multiscale_max_abs": "pixelwise strongest absolute residual across scale bank",
            "multiscale_stable": "pixelwise adjacent-scale persistence and sign agreement",
            "broad_consensus_2of3": "broad component masks supported by at least two scale-specific maps",
            "oracle_best_scale": "truth-aware diagnostic selecting the best fixed scale per target; upper-bound diagnostic only",
        },
        "validation_boundary": "Synthetic diagnostic only; no field ground truth, device-calibrated forward model, material identification, or proof of real geological detection.",
        "decision": "diagnostic_only_no_production_change",
    }
    (out / "adaptive_scale_separation.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.89 — Adaptive Scale Separation Audit",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per seed: **{count}**; geology records per generator: **{sum(r['generator'] == 'B' for r in records) // len(REPRESENTATIONS)}**.",
        "",
        "Scale bank: " + ", ".join(f"{s:g}" for s in SCALES),
        "",
        "| Generator | Representation | Records | Broad hit | Mean peak | Mean target abs-z | Mean frac | Mean comps | False comps | Outside p95 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for rep in REPRESENTATIONS:
            s = summary[g][rep]
            lines.append(
                f"| {g} | {rep} | {s['records']} | {s['component_hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | "
                f"{s['mean_target_abs_z']:.3f} | {s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} | "
                f"{s['mean_false_components_away']:.2f} | {s['mean_outside_p95_abs_z']:.3f} |"
            )
    lines += ["", "## Oracle scale selection", ""]
    for g in GENERATORS:
        counts_text = ", ".join(
            f"sigma {k}: {v}"
            for k, v in sorted(oracle_scale_counts[g].items(), key=lambda kv: float(kv[0]))
        )
        lines.append(f"- Generator {g}: {counts_text}")
    lines += [
        "",
        "## Interpretation",
        "",
        "The fixed-scale bank answers whether there is a useful spatial scale at all. `oracle_best_scale` then shows the target-aware ceiling from selecting that scale. The adaptive variants are unsupervised and must be judged by repeated improvements across both independent generators without materially increasing broad false components.",
        "",
        "A large gap between adaptive and oracle performance means scale selection, not the scale bank itself, is the limiting factor. A small gap means the remaining issue is not solved by scale choice alone.",
        "",
        "## Decision",
        "",
        "Diagnostic only. No production change is justified until an adaptive rule is stable across independent generators and regression suites.",
        "",
        "## Validation boundary",
        "",
        "All measurements are synthetic. They do not establish field detection performance, identify gold/metal/minerals, or prove a cavity, tunnel, or geological structure in real ground data.",
    ]
    (out / "adaptive_scale_separation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

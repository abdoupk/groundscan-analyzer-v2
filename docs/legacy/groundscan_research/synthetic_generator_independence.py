"""Independent synthetic forward-model validation for v0.2.82.

This module deliberately does not calibrate, fit, retune, or alter production
analysis. It generates the same ground-truth target plans through two
independent forward models so the current analyzer can be evaluated under
generator shift rather than only seed changes.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from math import isfinite
from pathlib import Path

import numpy as np

from groundscan.models import ScanData, ScanMetadata
from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.synthetic_core.benchmark import evaluate
from groundscan.validation.synthetic_core.core import SyntheticTarget

GENERATOR_NAMES = ("B", "C")
KINDS = ("positive_compact", "cavity", "tunnel", "geology")


def _rotate(xx, yy, t: SyntheticTarget):
    theta = np.radians(t.orientation_deg)
    c, s = np.cos(theta), np.sin(theta)
    xr = c * (xx - t.x) + s * (yy - t.y)
    yr = -s * (xx - t.x) + c * (yy - t.y)
    return xr, yr


def _response_b(xx, yy, t: SyntheticTarget) -> np.ndarray:
    xr, yr = _rotate(xx, yy, t)
    kind = t.kind
    if kind.startswith("positive"):
        q = (xr / max(t.sx, 0.65)) ** 2 + (yr / max(t.sy, 0.65)) ** 2
        # Moffat-like tail + weak anisotropic shoulder.
        core = (1.0 + q) ** -2.1
        shoulder = 0.10 * np.exp(
            -0.5 * ((xr / max(2.5 * t.sx, 1.0)) ** 2 + (yr / max(2.3 * t.sy, 1.0)) ** 2)
        )
        return t.amplitude * (core + shoulder)
    if kind in {"cavity", "negative_cavity"}:
        q = (xr / max(t.sx, 0.7)) ** 2 + (yr / max(t.sy, 0.7)) ** 2
        return -abs(t.amplitude) * np.exp(-0.5 * q**1.15)
    if kind in {"tunnel", "linear_negative", "linear_positive"}:
        half = max(t.length / 2.0, 1.0)
        along = np.clip(xr, -half, half)
        dist = np.sqrt((xr - along) ** 2 + yr**2)
        val = np.exp(-((dist / max(t.sy, 0.55)) ** 1.35))
        taper = np.clip(1.0 - 0.15 * np.maximum(np.abs(xr) - half, 0.0), 0.0, 1.0)
        sign = -1.0 if kind != "linear_positive" else 1.0
        return sign * abs(t.amplitude) * val * taper
    if kind in {"geology", "geological"}:
        q = (np.abs(xr) / max(t.sx, 2.0)) ** 3.0 + (np.abs(yr) / max(t.sy, 2.0)) ** 3.0
        return abs(t.amplitude) * 0.50 / (1.0 + q) * (0.92 + 0.08 * np.cos(xr / max(t.sx, 2.0)))
    raise ValueError(kind)


def _response_c(xx, yy, t: SyntheticTarget) -> np.ndarray:
    xr, yr = _rotate(xx, yy, t)
    kind = t.kind
    if kind.startswith("positive"):
        q = (np.abs(xr) / max(t.sx, 0.7)) ** 1.55 + (np.abs(yr) / max(t.sy, 0.7)) ** 1.55
        return t.amplitude * np.exp(-q) * (1.0 + 0.08 * np.cos(yr / max(t.sy, 0.8)))
    if kind in {"cavity", "negative_cavity"}:
        q = (np.abs(xr) / max(t.sx, 0.8)) ** 1.7 + (np.abs(yr) / max(t.sy, 0.8)) ** 1.7
        return -abs(t.amplitude) / (1.0 + q**2.1)
    if kind in {"tunnel", "linear_negative", "linear_positive"}:
        half = max(t.length / 2.0, 1.0)
        curve = 0.20 * np.sin(xr / half * np.pi) * max(t.sy, 0.55)
        inside = np.clip(np.abs(xr) / half, 0.0, 1.0)
        lateral = np.exp(-0.5 * ((yr - curve) / max(t.sy, 0.5)) ** 2)
        end = np.exp(-0.5 * (np.maximum(np.abs(xr) - half, 0.0) / max(t.sy, 0.5)) ** 2)
        taper = 0.96 + 0.04 * np.cos(np.pi * inside)
        sign = -1.0 if kind != "linear_positive" else 1.0
        return sign * abs(t.amplitude) * lateral * end * taper
    if kind in {"geology", "geological"}:
        ridge = np.exp(-0.5 * ((xr / max(t.sx, 2.0)) ** 2 + (yr / max(t.sy, 2.0)) ** 2))
        ripple = 0.86 + 0.14 * np.cos((xr + 0.7 * yr) / max(t.sx, 2.0))
        return abs(t.amplitude) * 0.43 * ridge * ripple
    raise ValueError(kind)


def _master_plan(seed: int, count: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    plans: list[dict] = []
    for i in range(int(count)):
        width, height = 40.0, 30.0
        kind = KINDS[i % len(KINDS)]
        x = float(rng.uniform(7.0, width - 7.0))
        y = float(rng.uniform(6.0, height - 6.0))
        depth = float(rng.uniform(2.5, 10.5))
        amp = float(rng.uniform(9.0, 20.0))
        angle = float(rng.uniform(0.0, 180.0))
        if kind == "geology":
            sx, sy = float(rng.uniform(5.0, 9.0)), float(rng.uniform(4.0, 8.0))
            length = 8.0
        elif kind == "tunnel":
            sx, sy, length = 1.3, float(rng.uniform(0.75, 1.25)), float(rng.uniform(8.0, 16.0))
        else:
            sx, sy, length = float(rng.uniform(1.0, 3.0)), float(rng.uniform(1.0, 3.0)), 8.0
        targets = [
            SyntheticTarget(
                kind,
                x,
                y,
                depth=depth,
                amplitude=amp,
                sx=sx,
                sy=sy,
                length=length,
                orientation_deg=angle,
            )
        ]
        # Exactly one in four is multi-target, with a distinct second target.
        if i % 4 == 0:
            kind2 = ("cavity", "tunnel", "positive_compact")[(i // 4) % 3]
            x2 = float(np.clip(x + rng.uniform(3.5, 8.0), 6.0, width - 6.0))
            y2 = float(np.clip(y + rng.uniform(-5.0, 5.0), 5.0, height - 5.0))
            targets.append(
                SyntheticTarget(
                    kind2,
                    x2,
                    y2,
                    depth=float(rng.uniform(3.0, 9.0)),
                    amplitude=float(rng.uniform(10.0, 18.0)),
                    sx=float(rng.uniform(1.0, 2.5)),
                    sy=float(rng.uniform(0.8, 2.2)),
                    length=float(rng.uniform(8.0, 14.0)),
                    orientation_deg=float(rng.uniform(0.0, 180.0)),
                )
            )
        plans.append({
            "scenario": f"ind_{i:03d}",
            "width": width,
            "height": height,
            "nx": 41,
            "ny": 31,
            "targets": targets,
            "noise_sigma": float(rng.uniform(0.8, 1.6)),
        })
    return plans


def _generate(plan: dict, *, generator: str, seed: int) -> tuple[ScanData, dict]:
    rng = np.random.default_rng(seed)
    width, height = plan["width"], plan["height"]
    nx, ny = plan["nx"], plan["ny"]
    x = np.linspace(0.0, width, nx)
    y = np.linspace(0.0, height, ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    responses = []
    signal = np.zeros_like(xx, dtype=float)
    for t in plan["targets"]:
        r = _response_b(xx, yy, t) if generator == "B" else _response_c(xx, yy, t)
        signal += r
        responses.append(np.clip(np.abs(r) / max(abs(t.amplitude), 1e-6), 0.0, 1.0))

    if generator == "B":
        background = 142.0 + 0.11 * xx - 0.07 * yy + 2.2 * np.sin(xx / 7.0) + 1.4 * np.cos(yy / 5.0)
        correlated = rng.normal(0.0, 0.65, size=(ny, 1)) + rng.normal(0.0, 0.35, size=(1, nx))
        signal = (
            background
            + signal
            + correlated
            + rng.normal(0.0, plan["noise_sigma"], size=signal.shape)
        )
        signal = 142.0 + (signal - 142.0) / (1.0 + 0.035 * np.abs(signal - 142.0))
    else:
        background = (
            118.0
            + 0.16 * np.sqrt(xx**2 + yy**2)
            + 1.7 * np.sin((xx + 1.8 * yy) / 9.5)
            + 0.9 * np.sin(yy / 3.7)
        )
        signal = background + signal + rng.normal(0.0, plan["noise_sigma"], size=signal.shape)
        impulse_mask = rng.random(signal.shape) < 0.008
        if np.any(impulse_mask):
            signal[impulse_mask] += rng.normal(0.0, 3.5, size=int(impulse_mask.sum()))

    influence = np.sum(responses, axis=0) if responses else np.zeros_like(signal)
    weight = np.maximum(1.0 - influence, 0.0)
    if generator == "B":
        baseline_depth = 11.5
        depth_factor = lambda t: 0.92 * t.depth + 0.08 * (max(t.depth, 0.0) ** 1.15)
    else:
        baseline_depth = 10.8
        depth_factor = lambda t: 0.85 * t.depth + 0.15 * np.sqrt(max(t.depth, 0.0))
    depth_num = weight * baseline_depth
    depth_weight = weight.copy()
    for influence_i, t in zip(responses, plan["targets"]):
        depth_num += influence_i * depth_factor(t)
        depth_weight += influence_i
    depth = depth_num / np.maximum(depth_weight, 1e-9)
    depth += rng.normal(0.0, 0.07 if generator == "B" else 0.09, size=depth.shape)

    scan = ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=depth.ravel(),
        signal=signal.ravel(),
        grid_i=np.tile(np.arange(nx, dtype=float), ny),
        grid_j=np.repeat(np.arange(ny, dtype=float), nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device=f"synthetic-independent-{generator}",
            field_length_m=width,
            field_width_m=height,
            notes=f"Independent synthetic forward-model generator {generator}",
            source_file=f"synthetic:{generator}:{plan['scenario']}",
        ),
    )
    truth = {
        "scenario": plan["scenario"],
        "width_m": width,
        "height_m": height,
        "targets": [asdict(t) for t in plan["targets"]],
        "seed": seed,
        "generator": generator,
    }
    return scan, truth


def _aggregate(rows: list[dict]) -> dict:
    targets = sum(r["targets"] for r in rows)
    matched = sum(r["matched_targets"] for r in rows)
    candidates = sum(r["candidates"] for r in rows)
    return {
        "sites": len(rows),
        "targets": targets,
        "matched": matched,
        "candidates": candidates,
        "recall": matched / targets if targets else 1.0,
        "precision": matched / candidates if candidates else (1.0 if targets == 0 else 0.0),
        "mean_case_recall": float(np.mean([r["recall"] for r in rows])) if rows else 0.0,
        "mean_case_precision": float(np.mean([r["precision"] for r in rows])) if rows else 0.0,
        "exact_target_count_rate": float(np.mean([r["candidates"] == r["targets"] for r in rows]))
        if rows
        else 0.0,
        "mean_center_error_m": float(np.nanmean([r["mean_center_error_m"] for r in rows]))
        if any(isfinite(float(r["mean_center_error_m"])) for r in rows)
        else None,
        "mean_depth_error_m": float(np.nanmean([r["mean_depth_error_m"] for r in rows]))
        if any(isfinite(float(r["mean_depth_error_m"])) for r in rows)
        else None,
    }


def run_synthetic_generator_independence(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = (8201, 8202),
    count: int = 24,
    fusion_resolution: int = 32,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Same master truth plans for B and C within each seed: only the forward model changes.
    rows_by_generator: dict[str, list[dict]] = {g: [] for g in GENERATOR_NAMES}
    for seed_idx, seed in enumerate(tuple(int(s) for s in seeds)):
        plans = _master_plan(seed, count)
        for g in GENERATOR_NAMES:
            for i, plan in enumerate(plans):
                scan, truth = _generate(
                    plan, generator=g, seed=seed * 1000 + i + (0 if g == "B" else 500000)
                )
                _, _, candidates = analyze_scan(
                    scan,
                    out / f"seed_{seed}" / g / plan["scenario"],
                    label=f"{g}_{plan['scenario']}",
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                row = evaluate(candidates, truth, distance_tolerance_m=3.0)
                rows_by_generator[g].append(row.__dict__)

    generators = {g: _aggregate(rows) for g, rows in rows_by_generator.items()}
    by_family: dict[str, dict[str, dict]] = {}
    for g, rows in rows_by_generator.items():
        fam: dict[str, list[dict]] = {}
        for r in rows:
            fam.setdefault(r["scenario"].split("_")[1], []).append(r)
        # Scenario family is encoded by the deterministic index modulo four.
        by_family[g] = {}
        for name, idx in [("compact", 0), ("cavity", 1), ("tunnel", 2), ("geology", 3)]:
            rr = [r for i, r in enumerate(rows) if i % 4 == idx]
            by_family[g][name] = _aggregate(rr)

    payload = {
        "version": "0.2.82",
        "benchmark": "synthetic_generator_independence",
        "seeds": [int(s) for s in seeds],
        "count_per_generator_per_seed": int(count),
        "total_sites": int(sum(v["sites"] for v in generators.values())),
        "total_targets": int(sum(v["targets"] for v in generators.values())),
        "generators": generators,
        "by_family": by_family,
        "method": {
            "calibration": "none",
            "thresholds_changed": False,
            "production_behavior_changed": False,
            "same_truth_plans_across_generators": True,
            "generator_shift": [
                "different target forward response functions",
                "different background fields",
                "different noise/contamination process",
                "different depth-coupling function",
                "different nonlinear/sparse acquisition effects",
            ],
        },
        "validation_boundary": "Synthetic generator-shift validation only; no independently verified field ground truth is available.",
        "decision": "diagnostic_only_no_production_change",
    }
    (out / "synthetic_generator_independence.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.82 — Independent Synthetic Generator Validation",
        "",
        "> Diagnostic-only. No calibration or production detector/scoring behavior was changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per generator/seed: **{count}**.",
        "",
        "## Aggregate by generator",
        "",
        "| Generator | Sites | Targets | Matched | Candidates | Recall | Precision | Exact count |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATOR_NAMES:
        s = generators[g]
        lines.append(
            f"| {g} | {s['sites']} | {s['targets']} | {s['matched']} | {s['candidates']} | {s['recall']:.3f} | {s['precision']:.3f} | {s['exact_target_count_rate']:.3f} |"
        )
    lines += [
        "",
        "## By family",
        "",
        "| Generator | Family | Sites | Recall | Precision | Center error (m) | Depth error (m) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATOR_NAMES:
        for family, s in by_family[g].items():
            ce = "n/a" if s["mean_center_error_m"] is None else f"{s['mean_center_error_m']:.3f}"
            de = "n/a" if s["mean_depth_error_m"] is None else f"{s['mean_depth_error_m']:.3f}"
            lines.append(
                f"| {g} | {family} | {s['sites']} | {s['recall']:.3f} | {s['precision']:.3f} | {ce} | {de} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "Generators B and C use the same target plans per seed but different forward-model assumptions. No weights, thresholds, or production decisions are fitted on B or C.",
        "",
        "The purpose is to test generalization across generator shift, not merely across random seeds. Differences between generators are therefore expected and are evidence about model sensitivity, not a failure of the benchmark itself.",
        "",
        "## Validation boundary",
        "",
        "These are synthetic software-validation results. They do not establish field detection accuracy, material identification, field depth accuracy, or proof of a cavity/tunnel.",
        "",
        "## Decision",
        "",
        "Keep all generator-shift results diagnostic-only. Do not promote any new production threshold or scoring rule based on these results alone.",
    ]
    (out / "synthetic_generator_independence.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

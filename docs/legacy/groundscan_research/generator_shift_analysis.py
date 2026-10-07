"""Diagnostic analysis of candidate behavior under independent synthetic forward models.

v0.2.83 deliberately does not change detection, scoring, registration, fusion, or
classification behavior. It compares the same truth plans rendered through
Generator A (the legacy/simple forward model), Generator B and Generator C,
and separates:

* extraction miss: no candidate is within the geometric match radius;
* classification mismatch: a nearby candidate exists but has the wrong pattern;
* correct match: a nearby candidate has the expected pattern.

All values are synthetic software-validation diagnostics only.
"""

from __future__ import annotations

import json
from math import hypot
from pathlib import Path

import numpy as np

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.synthetic_core.benchmark import expected_patterns
from groundscan.validation.synthetic_core.core import (
    SyntheticScenario,
    SyntheticTarget,
    generate_scan,
)
from groundscan_research.synthetic_generator_independence import _generate, _master_plan

GENERATORS = ("A", "B", "C")
FAMILIES = ("compact", "cavity", "tunnel", "geology")
FEATURES = (
    "anomaly_score",
    "broadness_score",
    "regional_support_score",
    "linearity_score",
    "compactness",
    "area_cells",
    "artifact_score",
    "geometry_quality",
    "multiscale_persistence",
    "solidity",
    "boundary_contact_ratio",
)


def _generate_a(plan: dict, seed: int):
    scenario = SyntheticScenario(
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
    return generate_scan(scenario)


def _nearest(candidates, target):
    if not candidates:
        return None, float("inf")
    best = min(candidates, key=lambda c: hypot(c.x_center - target.x, c.y_center - target.y))
    return best, hypot(best.x_center - target.x, best.y_center - target.y)


def _candidate_snapshot(c):
    out = {
        "id": int(c.id),
        "pattern": c.pattern_hypothesis,
        "shape": c.shape_class,
        "scale": c.scale_class,
    }
    for name in FEATURES:
        value = getattr(c, name)
        out[name] = float(value) if np.isfinite(float(value)) else None
    out["depth_estimate"] = (
        float(c.depth_estimate) if np.isfinite(float(c.depth_estimate)) else None
    )
    out["cross_scan_agreement"] = (
        None if c.cross_scan_agreement is None else float(c.cross_scan_agreement)
    )
    return out


def _diagnose_targets(candidates, targets: list[SyntheticTarget], radius: float):
    rows = []
    for index, target in enumerate(targets):
        expected = sorted(expected_patterns(target))
        nearest, distance = _nearest(candidates, target)
        if nearest is None or distance > radius:
            status = "extraction_miss"
        elif nearest.pattern_hypothesis in expected:
            status = "correct_match"
        else:
            status = "classification_mismatch"
        rows.append({
            "target_index": index,
            "kind": target.kind,
            "expected_patterns": expected,
            "target_x": float(target.x),
            "target_y": float(target.y),
            "distance_m": None if not np.isfinite(distance) else float(distance),
            "status": status,
            "nearest": None if nearest is None else _candidate_snapshot(nearest),
        })
    return rows


def _mean(values):
    values = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return float(np.mean(values)) if values else None


def _feature_summary(target_rows):
    summary = {f: {} for f in FEATURES}
    for family in FAMILIES:
        fam_rows = [
            r
            for r in target_rows
            if r["kind"] == family
            and r["nearest"] is not None
            and r["distance_m"] is not None
            and r["distance_m"] <= 3.0
        ]
        for f in FEATURES:
            summary[f][family] = _mean([r["nearest"].get(f) for r in fam_rows])
    return summary


def _aggregate_target_rows(rows):
    total = len(rows)
    counts = {
        s: sum(1 for r in rows if r["status"] == s)
        for s in ("correct_match", "classification_mismatch", "extraction_miss")
    }
    return {
        "targets": total,
        "correct_match": counts["correct_match"],
        "classification_mismatch": counts["classification_mismatch"],
        "extraction_miss": counts["extraction_miss"],
        "correct_match_rate": counts["correct_match"] / total if total else 0.0,
        "classification_mismatch_rate": counts["classification_mismatch"] / total if total else 0.0,
        "extraction_miss_rate": counts["extraction_miss"] / total if total else 0.0,
    }


def run_generator_shift_analysis(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = (8301, 8302),
    count: int = 24,
    radius: float = 3.0,
    fusion_resolution: int = 32,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    by_generator: dict[str, list[dict]] = {g: [] for g in GENERATORS}

    for seed in tuple(int(s) for s in seeds):
        plans = _master_plan(seed, count)
        for idx, plan in enumerate(plans):
            for generator in GENERATORS:
                if generator == "A":
                    scan, truth = _generate_a(plan, seed=seed * 1000 + idx)
                else:
                    scan, truth = _generate(
                        plan,
                        generator=generator,
                        seed=seed * 1000 + idx + (0 if generator == "B" else 500000),
                    )
                _, _, candidates = analyze_scan(
                    scan,
                    out / "runs" / str(seed) / generator / plan["scenario"],
                    label=f"{generator}_{plan['scenario']}",
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                target_rows = _diagnose_targets(candidates, plan["targets"], radius)
                by_generator[generator].append({
                    "seed": seed,
                    "scenario": plan["scenario"],
                    "family": FAMILIES[idx % 4],
                    "targets": len(plan["targets"]),
                    "candidates": len(candidates),
                    "target_rows": target_rows,
                    "correct_pattern_hits": sum(
                        r["status"] == "correct_match" for r in target_rows
                    ),
                    "classification_mismatches": sum(
                        r["status"] == "classification_mismatch" for r in target_rows
                    ),
                    "extraction_misses": sum(r["status"] == "extraction_miss" for r in target_rows),
                })

    generators = {}
    per_family = {}
    for generator, site_rows in by_generator.items():
        targets = sum(r["targets"] for r in site_rows)
        candidates = sum(r["candidates"] for r in site_rows)
        target_rows = [tr for r in site_rows for tr in r["target_rows"]]
        agg = _aggregate_target_rows(target_rows)
        generators[generator] = {
            "sites": len(site_rows),
            "targets": targets,
            "candidates": candidates,
            **agg,
        }
        per_family[generator] = {}
        for family in FAMILIES:
            fam_target_rows = [
                tr for r in site_rows if r["family"] == family for tr in r["target_rows"]
            ]
            per_family[generator][family] = _aggregate_target_rows(fam_target_rows)
        generators[generator]["nearest_feature_means"] = _feature_summary(target_rows)

    geology_confusions = {}
    for generator, site_rows in by_generator.items():
        conf = {}
        geology_rows = [tr for r in site_rows for tr in r["target_rows"] if tr["kind"] == "geology"]
        for tr in geology_rows:
            if tr["status"] == "classification_mismatch" and tr["nearest"]:
                pattern = tr["nearest"]["pattern"]
                conf[pattern] = conf.get(pattern, 0) + 1
        geology_confusions[generator] = conf

    payload = {
        "version": "0.2.83",
        "benchmark": "generator_shift_analysis",
        "generators": list(GENERATORS),
        "seeds": [int(s) for s in seeds],
        "sites_per_generator_per_seed": int(count),
        "match_radius_m": float(radius),
        "fusion_resolution": int(fusion_resolution),
        "summary": generators,
        "by_family": per_family,
        "geology_wrong_pattern_counts": geology_confusions,
        "method": {
            "same_truth_plans_across_generators": True,
            "generator_A": "legacy core SyntheticScenario forward model",
            "generator_B": "independent alternate target/background/noise/depth model",
            "generator_C": "independent alternate target/background/noise/depth model",
            "classification": "unchanged production classifier",
            "status_definitions": {
                "correct_match": "nearest candidate is within radius and matches expected pattern",
                "classification_mismatch": "nearest candidate is within radius but has a non-expected pattern",
                "extraction_miss": "no candidate is within match radius",
            },
        },
        "validation_boundary": "Synthetic generator-shift diagnostics only; no independent field ground truth is available.",
        "decision": "diagnostic_only_no_production_change",
    }
    (out / "generator_shift_analysis.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.83 — Generator-Shift Analysis",
        "",
        "> Diagnostic-only. No detector, registration, fusion, scoring, or classification behavior changed.",
        "",
        f"Seeds: **{len(seeds)}**; sites per generator/seed: **{count}**; match radius: **{radius:.1f} m**.",
        "",
        "## Aggregate target outcomes",
        "",
        "| Generator | Sites | Targets | Candidates | Correct | Class mismatch | Extraction miss | Correct rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        s = generators[g]
        lines.append(
            f"| {g} | {s['sites']} | {s['targets']} | {s['candidates']} | {s['correct_match']} | {s['classification_mismatch']} | {s['extraction_miss']} | {s['correct_match_rate']:.3f} |"
        )
    lines += [
        "",
        "## By family",
        "",
        "| Generator | Family | Targets | Correct | Class mismatch | Extraction miss |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for g in GENERATORS:
        for family in FAMILIES:
            s = per_family[g][family]
            lines.append(
                f"| {g} | {family} | {s['targets']} | {s['correct_match']} | {s['classification_mismatch']} | {s['extraction_miss']} |"
            )
    lines += [
        "",
        "## Geology wrong-pattern counts",
        "",
        "| Generator | Wrong nearest pattern | Count |",
        "|---|---|---:|",
    ]
    for g in GENERATORS:
        counts = geology_confusions[g]
        if not counts:
            lines.append(f"| {g} | none | 0 |")
        else:
            for pattern, count_value in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"| {g} | {pattern} | {count_value} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "This audit keeps the target plans fixed while changing the forward model. A target is classified as an extraction miss only when no candidate is within the geometric match radius; a nearby wrong-pattern candidate is a classification mismatch. This separation prevents an apparent classifier failure from hiding an upstream extraction failure.",
        "",
        "The feature summaries and wrong-pattern counts are diagnostic. They are not calibration data for production thresholds and do not establish real-world material or cavity identification.",
        "",
        "## Validation boundary",
        "",
        "Generator-shift results are synthetic software-validation evidence. They do not establish field detection accuracy, material identification, field depth accuracy, or proof of a cavity/tunnel.",
        "",
        "## Decision",
        "",
        "Keep production behavior unchanged and use the failure split to choose the next investigation target.",
    ]
    (out / "generator_shift_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload

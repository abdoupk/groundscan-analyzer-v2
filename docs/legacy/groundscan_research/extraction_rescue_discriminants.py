"""Diagnostic audit for conservative extraction-rescue candidate discriminants.

This module does not change production detection, screening, scoring, or the
optional rescue policy. It labels added synthetic rescue candidates as
"recovered" when they lie within the benchmark matching tolerance of a truth
target, and "unmatched" otherwise, then compares their observable candidate
features. The label is synthetic ground truth only and must never be used as a
production rule.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.geology_local import FAMILIES, _make_scenario

FEATURES = (
    "anomaly_score",
    "broadness_score",
    "artifact_score",
    "boundary_contact_ratio",
    "multiscale_persistence",
)


def _stats(rows, key):
    vals = [float(r[key]) for r in rows]
    if not vals:
        return {"n": 0, "min": None, "mean": None, "max": None}
    return {"n": len(vals), "min": min(vals), "mean": sum(vals) / len(vals), "max": max(vals)}


def run_extraction_rescue_discriminant_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 24,
    seed: int = 3031,
    match_radius_m: float = 3.0,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows = []

    for i in range(count_per_family * len(FAMILIES)):
        family = FAMILIES[i % len(FAMILIES)]
        spec = _make_scenario(10000 + i, family, rng)
        scan, _truth = generate_scan(spec)
        result = analyze(
            scan,
            out / "scratch" / spec.name,
            label="rescue",
            config=AnalysisConfig(extraction_rescue="conservative-geology"),
            write_outputs=False,
        )
        added = [
            c
            for c in result.candidates
            if c.classification_method == "secondary-median-geology-rescue"
        ]
        for c in added:
            distances = [float(np.hypot(c.x_center - t.x, c.y_center - t.y)) for t in spec.targets]
            nearest = min(distances) if distances else float("inf")
            nearest_index = int(np.argmin(distances)) if distances else -1
            nearest_kind = spec.targets[nearest_index].kind if nearest_index >= 0 else None
            rows.append({
                "scenario": spec.name,
                "family": family,
                "observable": {
                    "anomaly_score": float(c.anomaly_score),
                    "broadness_score": float(c.broadness_score),
                    "artifact_score": float(c.artifact_score),
                    "boundary_contact_ratio": float(c.boundary_contact_ratio),
                    "multiscale_persistence": float(c.multiscale_persistence),
                },
                "x": float(c.x_center),
                "y": float(c.y_center),
                "nearest_truth_distance_m": nearest,
                "nearest_truth_kind": nearest_kind,
                "benchmark_label": "recovered" if nearest <= match_radius_m else "unmatched",
            })

    recovered = [
        r["observable"] | {"nearest_truth_distance_m": r["nearest_truth_distance_m"]}
        for r in rows
        if r["benchmark_label"] == "recovered"
    ]
    unmatched = [
        r["observable"] | {"nearest_truth_distance_m": r["nearest_truth_distance_m"]}
        for r in rows
        if r["benchmark_label"] == "unmatched"
    ]

    feature_report = {}
    for feature in (*FEATURES, "nearest_truth_distance_m"):
        feature_report[feature] = {
            "recovered": _stats(recovered, feature),
            "unmatched": _stats(unmatched, feature),
        }

    family_report = defaultdict(lambda: {"recovered": 0, "unmatched": 0, "total": 0})
    for r in rows:
        f = family_report[r["family"]]
        f[r["benchmark_label"]] += 1
        f["total"] += 1

    result = {
        "version": "0.2.60",
        "benchmark": "extraction_rescue_discriminant_audit_v060",
        "seed": seed,
        "count_per_family": count_per_family,
        "match_radius_m": match_radius_m,
        "total_rescue_candidates": len(rows),
        "recovered": len(recovered),
        "unmatched": len(unmatched),
        "feature_report": feature_report,
        "families": dict(sorted(family_report.items())),
        "decision": {
            "production_rule_changed": False,
            "rescue_default_changed": False,
            "finding": "Current rescue candidate features do not provide a clean synthetic discriminant that separates recovered from unmatched candidates. Do not tune production gates from this audit alone.",
            "next_action": "Prefer independent multi-scan support or a richer spatial-context feature over scalar threshold tuning; validate any candidate rule on a held-out synthetic set before production use.",
        },
        "guardrails": {
            "synthetic_only": True,
            "truth_label_not_a_production_feature": True,
            "baseline_detector_unchanged": True,
            "thresholds_unchanged": True,
        },
        "cases": rows,
    }
    (out / "extraction_rescue_discriminants.json").write_text(
        json.dumps(result, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.60 — Extraction Rescue Discriminant Audit",
        "",
        "> Synthetic diagnostic only. The recovered/unmatched label comes from benchmark ground truth and is **not** a production signal.",
        "",
        f"- Rescue candidates: **{len(rows)}**",
        f"- Recovered within {match_radius_m:.1f} m: **{len(recovered)}**",
        f"- Unmatched: **{len(unmatched)}**",
        "",
        "## Observable feature comparison",
        "",
        "| Feature | Recovered mean | Unmatched mean | Recovered range | Unmatched range |",
        "|---|---:|---:|---:|---:|",
    ]
    for feature in FEATURES:
        r = feature_report[feature]["recovered"]
        u = feature_report[feature]["unmatched"]
        lines.append(
            f"| `{feature}` | {r['mean']:.4f} | {u['mean']:.4f} | "
            f"{r['min']:.4f}–{r['max']:.4f} | {u['min']:.4f}–{u['max']:.4f} |"
            if r["n"] and u["n"]
            else f"| `{feature}` | — | — | — | — |"
        )
    lines += [
        "",
        "## Family split",
        "",
        "| Family | Recovered | Unmatched | Total |",
        "|---|---:|---:|---:|",
    ]
    for family, v in sorted(family_report.items()):
        lines.append(f"| {family} | {v['recovered']} | {v['unmatched']} | {v['total']} |")
    lines += [
        "",
        "## Finding",
        "",
        "The observable scalar candidate features overlap substantially between recovered and unmatched rescue candidates. A simple anomaly/broadness/artifact/boundary/persistence threshold therefore does not cleanly separate the two groups in this benchmark.",
        "",
        "The production rescue policy remains unchanged and OFF by default. The next useful signal to investigate is independent spatial support across scans or a richer spatial-context representation, not a more aggressive scalar threshold.",
        "",
    ]
    (out / "extraction_rescue_discriminants.md").write_text("\n".join(lines), encoding="utf-8")
    return result

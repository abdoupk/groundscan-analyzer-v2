"""Diagnostic audit for independent spatial support of extraction-rescue candidates.

This module is synthetic-only and does not alter detector, screening, scoring, or
rescue defaults. It evaluates whether a secondary geology rescue candidate that
appears on one scan also appears near the same physical coordinates on repeated
scans. The benchmark label is derived from synthetic truth and is never used as
a production rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.models import ScanData
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.geology_local import FAMILIES, _make_scenario

RESCUE_METHOD = "secondary-median-geology-rescue"
FEATURES = (
    "support_count",
    "support_ratio",
    "all_candidate_support_ratio",
    "geology_candidate_support_ratio",
    "support_candidate_count",
    "support_geology_count",
    "position_dispersion_m",
    "anomaly_consistency",
)


def _clone_scan(scan: ScanData, rng: np.random.Generator, gain: float, noise: float) -> ScanData:
    signal = np.asarray(scan.signal, dtype=float).copy()
    baseline = float(np.median(signal))
    signal = baseline + gain * (signal - baseline)
    if noise:
        signal += rng.normal(0.0, noise, size=signal.shape)
    return ScanData(
        x=scan.x.copy(),
        y=scan.y.copy(),
        z=scan.z.copy(),
        signal=signal,
        twt_ns=None if scan.twt_ns is None else scan.twt_ns.copy(),
        grid_i=None if scan.grid_i is None else scan.grid_i.copy(),
        grid_j=None if scan.grid_j is None else scan.grid_j.copy(),
        latitude=None if scan.latitude is None else scan.latitude.copy(),
        longitude=None if scan.longitude is None else scan.longitude.copy(),
        coords_are_index_only=scan.coords_are_index_only,
        metadata=scan.metadata,
    )


def _truth_label(candidate, targets, radius: float) -> tuple[str, float, str | None]:
    if not targets:
        return "unmatched", float("inf"), None
    distances = [
        float(np.hypot(candidate.x_center - t.x, candidate.y_center - t.y)) for t in targets
    ]
    idx = int(np.argmin(distances))
    nearest = distances[idx]
    return ("recovered" if nearest <= radius else "unmatched", nearest, targets[idx].kind)


def _spatial_cluster(candidate, candidates, radius: float):
    near = [
        c
        for c in candidates
        if float(np.hypot(candidate.x_center - c.x_center, candidate.y_center - c.y_center))
        <= radius
    ]
    return near


def run_spatial_context_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 12,
    seed: int = 4061,
    match_radius_m: float = 3.0,
    spatial_radius_m: float = 2.5,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows = []

    for i in range(count_per_family * len(FAMILIES)):
        family = FAMILIES[i % len(FAMILIES)]
        spec = _make_scenario(20000 + i, family, rng)
        base_scan, _ = generate_scan(spec)
        per_scan = []
        for j, (gain, noise) in enumerate(((1.0, 0.0), (0.97, 0.25), (1.04, 0.55))):
            scan = _clone_scan(
                base_scan, np.random.default_rng(seed * 17 + i * 31 + j), gain, noise
            )
            result = analyze(
                scan,
                out / "scratch" / spec.name / f"scan{j + 1}",
                label=f"s{j + 1}",
                config=AnalysisConfig(extraction_rescue="conservative-geology"),
                write_outputs=False,
            )
            per_scan.append(result.candidates)

        rescue_by_scan = []
        for scan_index, candidates in enumerate(per_scan):
            rescues = [c for c in candidates if c.classification_method == RESCUE_METHOD]
            for c in rescues:
                label, distance, kind = _truth_label(c, spec.targets, match_radius_m)
                support = []
                all_support = []
                geology_support = []
                for other_index, other_candidates in enumerate(per_scan):
                    if other_index == scan_index:
                        continue
                    other_rescues = [
                        x for x in other_candidates if x.classification_method == RESCUE_METHOD
                    ]
                    support.extend(_spatial_cluster(c, other_rescues, spatial_radius_m))
                    near_all = _spatial_cluster(c, other_candidates, spatial_radius_m)
                    all_support.extend(near_all)
                    geology_support.extend([
                        x for x in near_all if x.pattern_hypothesis == "geological-like"
                    ])
                # Deduplicate support by scan index to measure independent scan support.
                support_scan_indices = set()
                all_support_scan_indices = set()
                geology_support_scan_indices = set()
                support_rows = []
                all_support_rows = []
                for other_index, other_candidates in enumerate(per_scan):
                    if other_index == scan_index:
                        continue
                    other_rescues = [
                        x for x in other_candidates if x.classification_method == RESCUE_METHOD
                    ]
                    near = _spatial_cluster(c, other_rescues, spatial_radius_m)
                    near_all = _spatial_cluster(c, other_candidates, spatial_radius_m)
                    near_geo = [x for x in near_all if x.pattern_hypothesis == "geological-like"]
                    if near:
                        support_scan_indices.add(other_index)
                        nearest = min(
                            near,
                            key=lambda x: float(
                                np.hypot(c.x_center - x.x_center, c.y_center - x.y_center)
                            ),
                        )
                        support_rows.append(nearest)
                    if near_all:
                        all_support_scan_indices.add(other_index)
                        nearest_all = min(
                            near_all,
                            key=lambda x: float(
                                np.hypot(c.x_center - x.x_center, c.y_center - x.y_center)
                            ),
                        )
                        all_support_rows.append(nearest_all)
                    if near_geo:
                        geology_support_scan_indices.add(other_index)
                all_cluster = [c] + support_rows
                dispersion = float(
                    np.sqrt(
                        np.mean([
                            (float(x.x_center) - float(np.mean([q.x_center for q in all_cluster])))
                            ** 2
                            + (
                                float(x.y_center)
                                - float(np.mean([q.y_center for q in all_cluster]))
                            )
                            ** 2
                            for x in all_cluster
                        ])
                    )
                )
                values = [float(x.anomaly_score) for x in all_cluster]
                mean_abs = float(np.mean(np.abs(values))) if values else 0.0
                anomaly_consistency = (
                    1.0
                    if len(values) <= 1 or mean_abs <= 1e-9
                    else float(np.clip(1.0 - np.std(values) / mean_abs, 0.0, 1.0))
                )
                rows.append({
                    "scenario": spec.name,
                    "family": family,
                    "source_scan": scan_index + 1,
                    "x": float(c.x_center),
                    "y": float(c.y_center),
                    "benchmark_label": label,
                    "nearest_truth_distance_m": distance,
                    "nearest_truth_kind": kind,
                    "support_count": 1 + len(support_scan_indices),
                    "support_ratio": (1 + len(support_scan_indices)) / len(per_scan),
                    "all_candidate_support_count": 1 + len(all_support_scan_indices),
                    "all_candidate_support_ratio": (1 + len(all_support_scan_indices))
                    / len(per_scan),
                    "geology_candidate_support_count": 1 + len(geology_support_scan_indices),
                    "geology_candidate_support_ratio": (1 + len(geology_support_scan_indices))
                    / len(per_scan),
                    "support_candidate_count": len(all_support),
                    "support_geology_count": len(geology_support),
                    "position_dispersion_m": dispersion,
                    "anomaly_consistency": anomaly_consistency,
                })

    def stats(rows_subset, key):
        vals = [float(r[key]) for r in rows_subset]
        return {
            "n": len(vals),
            "min": min(vals) if vals else None,
            "mean": float(np.mean(vals)) if vals else None,
            "median": float(np.median(vals)) if vals else None,
            "max": max(vals) if vals else None,
        }

    recovered = [r for r in rows if r["benchmark_label"] == "recovered"]
    unmatched = [r for r in rows if r["benchmark_label"] == "unmatched"]

    feature_report = {}
    for feature in FEATURES:
        feature_report[feature] = {
            "recovered": stats(recovered, feature),
            "unmatched": stats(unmatched, feature),
        }

    gate_report = {}
    for min_support in (2, 3):
        selected = [r for r in rows if r["support_count"] >= min_support]
        rec = [r for r in selected if r["benchmark_label"] == "recovered"]
        un = [r for r in selected if r["benchmark_label"] == "unmatched"]
        gate_report[f"support_count>={min_support}"] = {
            "selected": len(selected),
            "recovered": len(rec),
            "unmatched": len(un),
            "recovered_retain_rate": len(rec) / len(recovered) if recovered else 0.0,
            "unmatched_retain_rate": len(un) / len(unmatched) if unmatched else 0.0,
            "precision_among_selected": len(rec) / len(selected) if selected else 0.0,
        }

    for min_support in (2, 3):
        selected = [r for r in rows if r["all_candidate_support_count"] >= min_support]
        rec = [r for r in selected if r["benchmark_label"] == "recovered"]
        un = [r for r in selected if r["benchmark_label"] == "unmatched"]
        gate_report[f"all_candidate_support_count>={min_support}"] = {
            "selected": len(selected),
            "recovered": len(rec),
            "unmatched": len(un),
            "recovered_retain_rate": len(rec) / len(recovered) if recovered else 0.0,
            "unmatched_retain_rate": len(un) / len(unmatched) if unmatched else 0.0,
            "precision_among_selected": len(rec) / len(selected) if selected else 0.0,
        }
        selected = [r for r in rows if r["geology_candidate_support_count"] >= min_support]
        rec = [r for r in selected if r["benchmark_label"] == "recovered"]
        un = [r for r in selected if r["benchmark_label"] == "unmatched"]
        gate_report[f"geology_candidate_support_count>={min_support}"] = {
            "selected": len(selected),
            "recovered": len(rec),
            "unmatched": len(un),
            "recovered_retain_rate": len(rec) / len(recovered) if recovered else 0.0,
            "unmatched_retain_rate": len(un) / len(unmatched) if unmatched else 0.0,
            "precision_among_selected": len(rec) / len(selected) if selected else 0.0,
        }

    result = {
        "version": "0.2.61",
        "benchmark": "extraction_rescue_spatial_context_audit_v061",
        "seed": seed,
        "count_per_family": count_per_family,
        "match_radius_m": match_radius_m,
        "spatial_radius_m": spatial_radius_m,
        "total_rescue_candidates": len(rows),
        "recovered": len(recovered),
        "unmatched": len(unmatched),
        "feature_report": feature_report,
        "gates": gate_report,
        "decision": {
            "production_rule_changed": False,
            "rescue_default_changed": False,
            "finding": "Independent spatial support is useful only when measured at the same physical location across separate scans; no production gate is enabled from this synthetic audit alone.",
            "next_action": "Validate a held-out multi-scan rule using real survey design metadata and independently known targets before enabling rescue by spatial support.",
        },
        "guardrails": {
            "synthetic_only": True,
            "truth_label_not_a_production_feature": True,
            "baseline_detector_unchanged": True,
            "rescue_default_off": True,
        },
        "cases": rows,
    }
    (out / "extraction_rescue_spatial_context.json").write_text(
        json.dumps(result, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.61 — Extraction Rescue Spatial Context Audit",
        "",
        "> Synthetic diagnostic only. Spatial support is measured across three repeated scans. Benchmark labels are derived from synthetic truth and are not production signals.",
        "",
        f"- Rescue candidates: **{len(rows)}**",
        f"- Recovered: **{len(recovered)}**",
        f"- Unmatched: **{len(unmatched)}**",
        "",
        "## Observable spatial features",
        "",
        "| Feature | Recovered mean | Unmatched mean | Recovered median | Unmatched median |",
        "|---|---:|---:|---:|---:|",
    ]
    for feature in FEATURES:
        r = feature_report[feature]["recovered"]
        u = feature_report[feature]["unmatched"]
        lines.append(
            f"| `{feature}` | {r['mean']:.4f} | {u['mean']:.4f} | {r['median']:.4f} | {u['median']:.4f} |"
            if r["n"] and u["n"]
            else f"| `{feature}` | — | — | — | — |"
        )
    lines += [
        "",
        "## Support gates",
        "",
        "| Gate | Selected | Recovered | Unmatched | Recovered retention | Unmatched retention | Precision among selected |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for gate, v in gate_report.items():
        lines.append(
            f"| `{gate}` | {v['selected']} | {v['recovered']} | {v['unmatched']} | {v['recovered_retain_rate']:.3f} | {v['unmatched_retain_rate']:.3f} | {v['precision_among_selected']:.3f} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "Spatial support is promising as an evidence channel because it is independent across scans, but this synthetic audit does not justify enabling an automatic rescue gate. Direction, registration quality, scan spacing, and real field ground truth must be evaluated before production use.",
        "",
    ]
    (out / "extraction_rescue_spatial_context.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return result

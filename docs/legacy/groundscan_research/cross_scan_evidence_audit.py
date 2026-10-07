"""Audit cross-scan patch evidence as an independent signal.

Diagnostic-only for v0.2.67. It does not change production fusion, detector,
or scoring. It evaluates whether the patch-based cross-scan evidence already
implemented in ``compare.agreement`` separates matched from unmatched fused
candidates, and reports threshold sweeps without selecting a production gate.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.agreement import cross_scan_agreement
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import AlignmentResult, _resample_to, align_grids
from groundscan.validation.synthetic_core.benchmark_large import match_candidates
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.cross_scan_variation_audit import (
    _apply_variation,
    _families,
    _fuse,
    _scenario,
    _variations,
)


def _identity_alignment(reference_anomaly, other_anomaly, resolution: int) -> AlignmentResult:
    a, am = _resample_to(reference_anomaly.zscore, (resolution, resolution))
    b, bm = _resample_to(other_anomaly.zscore, (resolution, resolution))
    valid = am & bm & np.isfinite(a) & np.isfinite(b)
    corr = (
        float(np.corrcoef(a[valid], b[valid])[0, 1])
        if int(valid.sum()) >= 3 and np.std(a[valid]) > 1e-9 and np.std(b[valid]) > 1e-9
        else 0.0
    )
    return AlignmentResult(
        "rot0",
        0,
        0,
        corr,
        float(np.mean(valid)),
        b,
        bm,
        max(0.0, corr - 0.01),
        0.01,
        max(0.0, corr),
        1,
    )


def _safe_mean(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if np.isfinite(v)]
    return float(np.mean(vals)) if vals else float("nan")


def _agreement_metrics(
    candidate, reference_obs: ScanObservation, alignments: dict[str, AlignmentResult]
):
    scores = []
    for label, alignment in alignments.items():
        probe = copy.deepcopy(candidate)
        probe.cross_scan_agreement = None
        cross_scan_agreement([probe], reference_obs.grid, alignment)
        value = probe.cross_scan_agreement
        if value is not None and np.isfinite(value):
            scores.append(float(value))
    if not scores:
        return {
            "mean": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "coverage_05": 0.0,
            "coverage_07": 0.0,
            "count": 0,
        }
    arr = np.asarray(scores, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "coverage_05": float(np.mean(arr >= 0.5)),
        "coverage_07": float(np.mean(arr >= 0.7)),
        "count": int(arr.size),
    }


def run_cross_scan_evidence_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 8,
    seed: int = 7067,
    fusion_resolution: int = 32,
    match_radius: float = 3.0,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    variations = _variations()
    records = []
    for family in _families():
        for i in range(count_per_family):
            idx = len(records)
            scenario = _scenario(family, idx, seed)
            base_scan, truth = generate_scan(scenario)
            observations = []
            for v_idx, variation in enumerate(variations):
                scan = _apply_variation(base_scan, scenario, variation, seed + idx * 100 + v_idx)
                result = analyze(
                    scan,
                    out_dir / "scans" / scenario.name / variation.name,
                    label=variation.name,
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                observations.append(
                    ScanObservation(
                        variation.name,
                        scan,
                        result.grid,
                        result.anomaly,
                        detect_artifacts(result.grid, result.anomaly),
                        result.candidates,
                    )
                )
            reference = observations[0]
            alignments = {}
            for obs in observations[1:]:
                if (
                    obs.scan.metadata.orientation_deg != reference.scan.metadata.orientation_deg
                    or obs.scan.metadata.line_spacing_m != reference.scan.metadata.line_spacing_m
                ):
                    al = align_grids(
                        reference.anomaly.zscore,
                        obs.anomaly.zscore,
                        resolution=fusion_resolution,
                        max_shift=2,
                        orientation_a_deg=reference.scan.metadata.orientation_deg,
                        orientation_b_deg=obs.scan.metadata.orientation_deg,
                    )
                else:
                    al = _identity_alignment(reference.anomaly, obs.anomaly, fusion_resolution)
                alignments[obs.label] = al
            fused = _fuse(observations, reference, alignments, fusion_resolution)
            matches, _, matched_candidate_idxs = match_candidates(
                fused, truth["targets"], match_radius
            )
            matched_candidate_idxs = set(matched_candidate_idxs)
            case = {
                "site_id": scenario.name,
                "family": family,
                "targets": len(truth["targets"]),
                "candidates": len(fused),
                "records": [],
            }
            for ci, candidate in enumerate(fused):
                metrics = _agreement_metrics(candidate, reference, alignments)
                case["records"].append({
                    "candidate_index": ci,
                    "matched": ci in matched_candidate_idxs,
                    "x": float(candidate.x_center),
                    "y": float(candidate.y_center),
                    "pattern": candidate.pattern_hypothesis,
                    **metrics,
                })
                records.append({
                    "family": family,
                    "matched": ci in matched_candidate_idxs,
                    **metrics,
                })
            (out_dir / "cases").mkdir(exist_ok=True)
            (out_dir / "cases" / f"{scenario.name}.json").write_text(
                json.dumps(case, indent=2, allow_nan=True), encoding="utf-8"
            )

    matched = [r for r in records if r["matched"]]
    unmatched = [r for r in records if not r["matched"]]

    def stats(rows):
        return {
            "n": len(rows),
            "mean": round(_safe_mean([r["mean"] for r in rows]), 4),
            "median": round(
                float(np.nanmedian([r["mean"] for r in rows])) if rows else float("nan"), 4
            ),
            "p25": round(
                float(np.nanpercentile([r["mean"] for r in rows], 25)) if rows else float("nan"), 4
            ),
            "p75": round(
                float(np.nanpercentile([r["mean"] for r in rows], 75)) if rows else float("nan"), 4
            ),
            "coverage_05": round(_safe_mean([r["coverage_05"] for r in rows]), 4),
            "coverage_07": round(_safe_mean([r["coverage_07"] for r in rows]), 4),
        }

    threshold_rows = []
    for threshold in np.arange(0.0, 0.81, 0.05):
        kept = [r for r in records if np.isfinite(r["mean"]) and r["mean"] >= threshold]
        kept_matched = sum(r["matched"] for r in kept)
        kept_total = len(kept)
        target_matched = sum(r["matched"] for r in records)
        threshold_rows.append({
            "threshold": round(float(threshold), 2),
            "kept_candidates": kept_total,
            "matched_kept": kept_matched,
            "candidate_recall": round(kept_matched / max(target_matched, 1), 4),
            "candidate_precision": round(kept_matched / max(kept_total, 1), 4),
        })

    family_summary = {}
    for family in _families():
        rows = [r for r in records if r["family"] == family]
        family_summary[family] = {
            "all": stats(rows),
            "matched": stats([r for r in rows if r["matched"]]),
            "unmatched": stats([r for r in rows if not r["matched"]]),
        }

    payload = {
        "version": "0.2.67",
        "benchmark": "cross_scan_evidence_audit",
        "sites": len(records),
        "seed": seed,
        "candidates_total": len(records),
        "matched_candidates": len(matched),
        "unmatched_candidates": len(unmatched),
        "matched_stats": stats(matched),
        "unmatched_stats": stats(unmatched),
        "family_summary": family_summary,
        "threshold_sweep": threshold_rows,
        "decision": "diagnostic_only_no_production_change",
        "note": "Cross-scan patch agreement is evaluated as an independent diagnostic feature. Threshold sweep is descriptive; no production gate is selected. Synthetic only, not field validation.",
    }
    (out_dir / "cross_scan_evidence_audit.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.67 — Cross-Scan Evidence Audit",
        "",
        "> Diagnostic-only synthetic audit. No production detector/fusion policy change.",
        "",
        f"Sites: **{len(set(r['family'] for r in records))} families; seed {seed}**",
        "",
        "## Candidate agreement distributions",
        "",
        "| Group | N | Mean | Median | P25 | P75 | Mean coverage ≥0.5 | Mean coverage ≥0.7 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, data in (("Matched", stats(matched)), ("Unmatched", stats(unmatched))):
        lines.append(
            f"| {label} | {data['n']} | {data['mean']:.3f} | {data['median']:.3f} | {data['p25']:.3f} | {data['p75']:.3f} | {data['coverage_05']:.1%} | {data['coverage_07']:.1%} |"
        )
    lines += [
        "",
        "## Threshold sweep on mean cross-scan agreement",
        "",
        "| Threshold | Kept | Matched | Recall of matched candidates | Precision |",
        "|---:|---:|---:|---:|---:|",
    ]
    for r in threshold_rows:
        lines.append(
            f"| {r['threshold']:.2f} | {r['kept_candidates']} | {r['matched_kept']} | {r['candidate_recall']:.3f} | {r['candidate_precision']:.3f} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "No production threshold was selected. The audit measures whether cross-scan patch evidence provides useful separation without changing the default pipeline.",
        "",
    ]
    (out_dir / "cross_scan_evidence_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

"""Multidimensional calibration audit for cross-scan evidence.

Diagnostic/experimental only for v0.2.71.  This module fits a bounded
ranking score from existing multi-scan evidence components, selecting a
threshold on a calibration split and evaluating once on an independent
holdout split.  It does not alter the default detector, fusion, pruning, or
candidate scoring pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import align_grids
from groundscan.validation.synthetic_core.benchmark_large import match_candidates
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.cross_scan_variation_audit import (
    _apply_variation,
    _families,
    _fuse,
    _scenario,
    _variations,
)
from groundscan_research.cross_scan_evidence_audit import _identity_alignment

FEATURES: tuple[str, ...] = (
    "multi_scan_evidence_score",
    "detection_rate",
    "directional_persistence",
    "spacing_persistence",
    "traversal_persistence",
    "position_stability",
    "multiscan_signal_consistency",
    "multiresolution_consensus",
    "depth_cross_scan_consistency",
    "geometry_consistency",
    "registration_consistency",
    "leave_one_out_stability",
)

CALIBRATED_FEATURES: tuple[str, ...] = (
    "position_stability",
    "depth_cross_scan_consistency",
    "multiscan_signal_consistency",
    "leave_one_out_stability",
)
CALIBRATED_WEIGHTS: tuple[float, ...] = (0.35, 0.25, 0.30, 0.10)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def _roc_auc(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(-score, kind="mergesort")
    ys = y[order]
    pos = int(np.sum(ys == 1))
    neg = int(np.sum(ys == 0))
    if pos == 0 or neg == 0:
        return float("nan")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1, dtype=float)
    sum_pos = float(np.sum(ranks[y == 1]))
    return float((sum_pos - pos * (pos + 1) / 2.0) / (pos * neg))


def _threshold_metrics(
    y: np.ndarray, score: np.ndarray, threshold: float
) -> dict[str, float | int]:
    keep = score >= threshold
    tp = int(np.sum((y == 1) & keep))
    fp = int(np.sum((y == 0) & keep))
    fn = int(np.sum((y == 1) & ~keep))
    tn = int(np.sum((y == 0) & ~keep))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-12)
    return {
        "threshold": float(threshold),
        "kept": int(np.sum(keep)),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _select_threshold(y: np.ndarray, score: np.ndarray) -> dict[str, float | int]:
    thresholds = np.unique(np.quantile(score, np.linspace(0.0, 1.0, 101)))
    rows = [_threshold_metrics(y, score, float(t)) for t in thresholds]
    # Select on calibration only. F1 is secondary to recall to avoid trading
    # away many true candidates simply to reduce false positives.
    rows.sort(key=lambda r: (r["f1"], r["recall"], r["precision"]), reverse=True)
    return rows[0]


def _feature_row(candidate) -> list[float]:
    return [
        float(
            np.clip(
                getattr(candidate, f, 0.0) if getattr(candidate, f, None) is not None else 0.0,
                0.0,
                1.0,
            )
        )
        for f in FEATURES
    ]


def _collect(
    seed: int,
    *,
    count_per_family: int,
    out_dir: Path,
    fusion_resolution: int = 32,
    match_radius: float = 3.0,
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    families = _families()
    variations = _variations()
    for family in families:
        for i in range(count_per_family):
            idx = len({r["site_id"] for r in rows})
            scenario = _scenario(family, idx, seed)
            base_scan, truth = generate_scan(scenario)
            observations: list[ScanObservation] = []
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
            _, _, matched_indices = match_candidates(fused, truth["targets"], match_radius)
            matched_indices = set(matched_indices)
            for ci, c in enumerate(fused):
                rows.append({
                    "site_id": scenario.name,
                    "family": family,
                    "candidate_index": ci,
                    "matched": bool(ci in matched_indices),
                    "pattern": c.pattern_hypothesis,
                    "x": float(c.x_center),
                    "y": float(c.y_center),
                    "features": {f: float(_feature_row(c)[j]) for j, f in enumerate(FEATURES)},
                })
    y = np.asarray([1 if r["matched"] else 0 for r in rows], dtype=int)
    x = np.asarray([[r["features"][f] for f in FEATURES] for r in rows], dtype=float)
    summary = {
        "seed": seed,
        "sites": count_per_family * len(families),
        "candidates": len(rows),
        "matched": int(y.sum()),
        "unmatched": int((1 - y).sum()),
        "positive_rate": float(np.mean(y)) if len(y) else 0.0,
    }
    return rows, {"summary": summary, "X": x, "y": y}


def run_cross_scan_evidence_calibration(
    out_dir: str | Path,
    *,
    train_seed: int = 7068,
    calibration_seed: int = 9092,
    holdout_seed: int = 10092,
    train_count_per_family: int = 8,
    calibration_count_per_family: int = 4,
    holdout_count_per_family: int = 8,
    fusion_resolution: int = 32,
    l2: float = 0.5,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_rows, train = _collect(
        train_seed,
        count_per_family=train_count_per_family,
        out_dir=out_dir / "train",
        fusion_resolution=fusion_resolution,
    )
    cal_rows, cal = _collect(
        calibration_seed,
        count_per_family=calibration_count_per_family,
        out_dir=out_dir / "calibration",
        fusion_resolution=fusion_resolution,
    )
    hold_rows, hold = _collect(
        holdout_seed,
        count_per_family=holdout_count_per_family,
        out_dir=out_dir / "holdout",
        fusion_resolution=fusion_resolution,
    )

    calibrated_idx = [FEATURES.index(f) for f in CALIBRATED_FEATURES]
    weights = np.asarray(CALIBRATED_WEIGHTS, dtype=float)
    weights = weights / np.sum(weights)

    def calibrated_score(x: np.ndarray) -> np.ndarray:
        return np.clip(x[:, calibrated_idx] @ weights, 0.0, 1.0)

    train_score = calibrated_score(train["X"])
    cal_score = calibrated_score(cal["X"])
    hold_score = calibrated_score(hold["X"])
    baseline_train = train["X"][:, FEATURES.index("multi_scan_evidence_score")]
    baseline_cal = cal["X"][:, FEATURES.index("multi_scan_evidence_score")]
    baseline_hold = hold["X"][:, FEATURES.index("multi_scan_evidence_score")]

    cal_gate = _select_threshold(cal["y"], cal_score)
    base_cal_gate = _select_threshold(cal["y"], baseline_cal)
    calibrated_hold = _threshold_metrics(hold["y"], hold_score, cal_gate["threshold"])
    baseline_hold_metrics = _threshold_metrics(hold["y"], baseline_hold, base_cal_gate["threshold"])

    component_discrimination = {}
    for f in FEATURES:
        idx = FEATURES.index(f)
        component_discrimination[f] = _roc_auc(hold["y"], hold["X"][:, idx])

    payload = {
        "version": "0.2.71",
        "benchmark": "cross_scan_evidence_multidimensional_calibration",
        "features": list(FEATURES),
        "calibrated_features": list(CALIBRATED_FEATURES),
        "train": train["summary"],
        "calibration": cal["summary"],
        "holdout": hold["summary"],
        "model": {
            "type": "fixed_weight_multidimensional_ranking",
            "weights": {f: float(w) for f, w in zip(CALIBRATED_FEATURES, weights)},
        },
        "auc": {
            "baseline_scalar": _roc_auc(hold["y"], baseline_hold),
            "multidimensional": _roc_auc(hold["y"], hold_score),
        },
        "threshold_selection": {
            "baseline_from_calibration": base_cal_gate,
            "multidimensional_from_calibration": cal_gate,
        },
        "holdout_metrics": {
            "baseline_scalar": baseline_hold_metrics,
            "multidimensional": calibrated_hold,
        },
        "component_auc_holdout": component_discrimination,
        "decision": "diagnostic_only_no_production_change",
        "note": "This score is a bounded ranking/separation heuristic, not a probability. Feature subset/weights are fixed before the holdout evaluation. Thresholds are selected on the calibration split only. No production detector/fusion/scoring behavior is changed.",
        "rows": {"train": train_rows, "calibration": cal_rows, "holdout": hold_rows},
    }
    (out_dir / "cross_scan_evidence_calibration.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.71 — Cross-Scan Evidence Calibration",
        "",
        "> Diagnostic-only synthetic calibration. No production behavior changed.",
        "",
        "## Dataset splits",
        "",
        "| Split | Sites | Candidates | Matched | Unmatched |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, s in (
        ("Train", train["summary"]),
        ("Calibration", cal["summary"]),
        ("Holdout", hold["summary"]),
    ):
        lines.append(
            f"| {name} | {s['sites']} | {s['candidates']} | {s['matched']} | {s['unmatched']} |"
        )
    lines += [
        "",
        "## Holdout discrimination",
        "",
        "| Model | AUC | Precision @ calibration threshold | Recall @ calibration threshold | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    b = baseline_hold_metrics
    m = calibrated_hold
    lines.append(
        f"| Existing scalar `multi_scan_evidence_score` | {payload['auc']['baseline_scalar']:.3f} | {b['precision']:.3f} | {b['recall']:.3f} | {b['f1']:.3f} |"
    )
    lines.append(
        f"| Multidimensional calibrated score | {payload['auc']['multidimensional']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |"
    )
    lines += ["", "## Component AUC on holdout", "", "| Component | AUC |", "|---|---:|"]
    for f, auc in sorted(
        component_discrimination.items(),
        key=lambda kv: (-(kv[1] if np.isfinite(kv[1]) else -1), kv[0]),
    ):
        lines.append(f"| `{f}` | {auc:.3f} |")
    lines += [
        "",
        "## Decision",
        "",
        "No production threshold was selected. The multidimensional score remains diagnostic until repeated independent holdouts and real field ground truth support operational use.",
        "",
    ]
    (out_dir / "cross_scan_evidence_calibration.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

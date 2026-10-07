"""Repeated independent holdout audit for cross-scan evidence (v0.2.71).
Diagnostic only: no production behavior changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan_research.cross_scan_evidence_calibration import (
    CALIBRATED_FEATURES,
    CALIBRATED_WEIGHTS,
    FEATURES,
    _collect,
    _roc_auc,
    _threshold_metrics,
)

DEFAULT_HOLDOUT_SEEDS = (11169, 22269, 33369, 44469, 55569)
FIXED_THRESHOLD = 0.3462032574991704
BASELINE_THRESHOLD = 0.7190799999999999


def _score(X):
    idx = [FEATURES.index(f) for f in CALIBRATED_FEATURES]
    w = np.asarray(CALIBRATED_WEIGHTS, float)
    w = w / w.sum()
    return np.clip(X[:, idx] @ w, 0, 1)


def run_repeated_holdouts(
    out_dir: str | Path,
    *,
    seeds=DEFAULT_HOLDOUT_SEEDS,
    count_per_family=3,
    fusion_resolution=32,
    match_radius=3.0,
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, seed in enumerate(seeds):
        _, d = _collect(
            seed,
            count_per_family=count_per_family,
            out_dir=out_dir / f"seed_{seed}",
            fusion_resolution=fusion_resolution,
            match_radius=match_radius,
        )
        y = d["y"]
        X = d["X"]
        ms = _score(X)
        base = X[:, FEATURES.index("multi_scan_evidence_score")]
        row = {
            "seed": seed,
            "sites": d["summary"]["sites"],
            "candidates": len(y),
            "matched": int(y.sum()),
            "unmatched": int((1 - y).sum()),
            "auc_baseline": _roc_auc(y, base),
            "auc_multidim": _roc_auc(y, ms),
            "fixed_threshold": FIXED_THRESHOLD,
            "multidim_at_fixed": _threshold_metrics(y, ms, FIXED_THRESHOLD),
            "baseline_at_fixed": _threshold_metrics(y, base, BASELINE_THRESHOLD),
        }
        rows.append(row)
    auc_b = [r["auc_baseline"] for r in rows if np.isfinite(r["auc_baseline"])]
    auc_m = [r["auc_multidim"] for r in rows if np.isfinite(r["auc_multidim"])]
    result = {
        "version": "0.2.71",
        "mode": "repeated_independent_holdouts",
        "seeds": list(seeds),
        "count_per_family": count_per_family,
        "fixed_weights": dict(zip(CALIBRATED_FEATURES, map(float, CALIBRATED_WEIGHTS))),
        "thresholds_frozen_from_v0268_calibration": {
            "multidimensional": FIXED_THRESHOLD,
            "baseline": BASELINE_THRESHOLD,
        },
        "holdouts": rows,
        "aggregate": {
            "holdouts": len(rows),
            "mean_auc_baseline": float(np.mean(auc_b)) if auc_b else None,
            "mean_auc_multidim": float(np.mean(auc_m)) if auc_m else None,
            "auc_delta_mean": float(np.mean(auc_m) - np.mean(auc_b)) if auc_b and auc_m else None,
            "multidim_auc_positive_count": sum(
                1
                for b, m in zip(
                    [r["auc_baseline"] for r in rows], [r["auc_multidim"] for r in rows]
                )
                if np.isfinite(b) and np.isfinite(m) and m > b
            ),
        },
        "decision": "diagnostic_only_no_production_change",
        "note": "All feature weights and thresholds are frozen from v0.2.68; no fitting is performed on these holdouts.",
    }
    (out_dir / "repeated_holdouts.json").write_text(
        json.dumps(result, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.71 — Repeated Independent Holdouts",
        "",
        "Diagnostic only. v0.2.68 weights/thresholds are frozen.",
        "",
        "| Seed | Sites | Candidates | Matched | Baseline AUC | Multidim AUC | ΔAUC | Multi P | Multi R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        d = r["multidim_at_fixed"]
        lines.append(
            f"| {r['seed']} | {r['sites']} | {r['candidates']} | {r['matched']} | {r['auc_baseline']:.3f} | {r['auc_multidim']:.3f} | {r['auc_multidim'] - r['auc_baseline']:+.3f} | {d['precision']:.3f} | {d['recall']:.3f} |"
        )
    lines += [
        "",
        "## Aggregate",
        "",
        f"Mean baseline AUC: **{result['aggregate']['mean_auc_baseline']:.3f}**",
        f"Mean multidimensional AUC: **{result['aggregate']['mean_auc_multidim']:.3f}**",
        f"Mean ΔAUC: **{result['aggregate']['auc_delta_mean']:+.3f}**",
        f"Holdouts where multidimensional AUC > baseline: **{result['aggregate']['multidim_auc_positive_count']}/{len(rows)}**",
        "",
        "## Decision",
        "",
        "Remain diagnostic-only. Repeated synthetic holdouts are encouraging but do not justify production activation without broader independent data and real field ground truth.",
    ]
    (out_dir / "repeated_holdouts.md").write_text("\n".join(lines), encoding="utf-8")
    return result

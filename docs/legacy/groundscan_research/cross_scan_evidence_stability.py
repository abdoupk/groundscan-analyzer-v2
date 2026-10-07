"""Repeated multi-seed stability audit for cross-scan evidence (v0.2.71).

Diagnostic only: no production detector, fusion, pruning, screening, or
candidate-scoring behavior is changed.

This release intentionally stops at repeated synthetic validation because the
project currently has no independently verified field ground-truth dataset.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
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

DEFAULT_SEEDS = (40670, 41670, 42670, 43670, 44670, 45670)
FIXED_THRESHOLD = 0.3462032574991704
BASELINE_THRESHOLD = 0.7190799999999999


def _score(x: np.ndarray) -> np.ndarray:
    idx = [FEATURES.index(f) for f in CALIBRATED_FEATURES]
    weights = np.asarray(CALIBRATED_WEIGHTS, dtype=float)
    weights = weights / max(float(weights.sum()), 1e-12)
    return np.clip(x[:, idx] @ weights, 0.0, 1.0)


def _safe_stats(values: Iterable[float]) -> dict[str, float | None]:
    arr = np.asarray([float(v) for v in values if np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def run_stability_audit(
    out_dir: str | Path,
    *,
    seeds=DEFAULT_SEEDS,
    count_per_family: int = 4,
    fusion_resolution: int = 32,
    match_radius: float = 3.0,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = tuple(int(s) for s in seeds)
    rows = []

    for seed in seeds:
        _, data = _collect(
            seed,
            count_per_family=count_per_family,
            out_dir=out_dir / f"seed_{seed}",
            fusion_resolution=fusion_resolution,
            match_radius=match_radius,
        )
        y = data["y"]
        x = data["X"]
        multi = _score(x)
        base = x[:, FEATURES.index("multi_scan_evidence_score")]
        md = _threshold_metrics(y, multi, FIXED_THRESHOLD)
        bd = _threshold_metrics(y, base, BASELINE_THRESHOLD)
        rows.append({
            "seed": seed,
            "sites": int(data["summary"]["sites"]),
            "candidates": int(len(y)),
            "matched": int(y.sum()),
            "unmatched": int((1 - y).sum()),
            "auc_baseline": _roc_auc(y, base),
            "auc_multidim": _roc_auc(y, multi),
            "auc_delta": (_roc_auc(y, multi) - _roc_auc(y, base))
            if np.isfinite(_roc_auc(y, base)) and np.isfinite(_roc_auc(y, multi))
            else float("nan"),
            "baseline_at_frozen_threshold": bd,
            "multidim_at_frozen_threshold": md,
        })

    auc_base = [r["auc_baseline"] for r in rows]
    auc_multi = [r["auc_multidim"] for r in rows]
    deltas = [r["auc_delta"] for r in rows]
    p_base = [r["baseline_at_frozen_threshold"]["precision"] for r in rows]
    p_multi = [r["multidim_at_frozen_threshold"]["precision"] for r in rows]
    r_base = [r["baseline_at_frozen_threshold"]["recall"] for r in rows]
    r_multi = [r["multidim_at_frozen_threshold"]["recall"] for r in rows]

    aggregate = {
        "holdouts": len(rows),
        "total_sites": int(sum(r["sites"] for r in rows)),
        "total_candidates": int(sum(r["candidates"] for r in rows)),
        "total_matched": int(sum(r["matched"] for r in rows)),
        "total_unmatched": int(sum(r["unmatched"] for r in rows)),
        "auc_baseline": _safe_stats(auc_base),
        "auc_multidim": _safe_stats(auc_multi),
        "auc_delta": _safe_stats(deltas),
        "multidim_auc_beats_baseline": int(
            sum(
                1
                for b, m in zip(auc_base, auc_multi)
                if np.isfinite(b) and np.isfinite(m) and m > b
            )
        ),
        "baseline_precision": _safe_stats(p_base),
        "multidim_precision": _safe_stats(p_multi),
        "baseline_recall": _safe_stats(r_base),
        "multidim_recall": _safe_stats(r_multi),
    }

    payload = {
        "version": "0.2.71",
        "benchmark": "cross_scan_evidence_repeated_stability",
        "mode": "diagnostic_only_repeated_synthetic_holdouts",
        "seeds": list(seeds),
        "count_per_family": int(count_per_family),
        "fixed_features": list(CALIBRATED_FEATURES),
        "fixed_weights": {f: float(w) for f, w in zip(CALIBRATED_FEATURES, CALIBRATED_WEIGHTS)},
        "frozen_thresholds": {"multidimensional": FIXED_THRESHOLD, "baseline": BASELINE_THRESHOLD},
        "holdouts": rows,
        "aggregate": aggregate,
        "decision": "diagnostic_only_no_production_activation",
        "field_data_status": "No independently verified field ground-truth dataset is available for this project; all results are synthetic.",
        "note": "The multidimensional score is evaluated repeatedly on independent synthetic seeds using weights and thresholds frozen before these holdouts. It remains a ranking/separation heuristic, not a probability or field-validated accuracy estimate.",
    }
    (out_dir / "cross_scan_evidence_stability.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.71 — Cross-Scan Evidence Stability",
        "",
        "> Diagnostic-only synthetic validation. Production detector/fusion/pruning behavior is unchanged.",
        "",
        f"Seeds: **{len(seeds)}**; sites: **{aggregate['total_sites']}**; candidates: **{aggregate['total_candidates']}**.",
        "",
        "## Per-holdout results",
        "",
        "| Seed | Sites | Candidates | Matched | Baseline AUC | Multidim AUC | ΔAUC | Multi P | Multi R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        m = r["multidim_at_frozen_threshold"]
        lines.append(
            f"| {r['seed']} | {r['sites']} | {r['candidates']} | {r['matched']} | {r['auc_baseline']:.3f} | {r['auc_multidim']:.3f} | {r['auc_delta']:+.3f} | {m['precision']:.3f} | {m['recall']:.3f} |"
        )

    lines += [
        "",
        "## Stability summary",
        "",
        f"Multidimensional AUC beat baseline on **{aggregate['multidim_auc_beats_baseline']}/{aggregate['holdouts']}** holdouts.",
        f"Mean baseline AUC: **{aggregate['auc_baseline']['mean']:.3f}**; mean multidimensional AUC: **{aggregate['auc_multidim']['mean']:.3f}**.",
        f"Mean ΔAUC: **{aggregate['auc_delta']['mean']:+.3f}**.",
        f"Multidimensional recall at frozen threshold: **{aggregate['multidim_recall']['mean']:.3f} ± {aggregate['multidim_recall']['std']:.3f}**.",
        f"Multidimensional precision at frozen threshold: **{aggregate['multidim_precision']['mean']:.3f} ± {aggregate['multidim_precision']['std']:.3f}**.",
        "",
        "## Validation boundary",
        "",
        "No independently verified field ground-truth dataset is currently available. These repeated synthetic results can validate software stability and regression behavior, but they cannot establish real-world detection accuracy, material identification, or proof of a cavity/tunnel.",
        "",
        "## Decision",
        "",
        "Keep the multidimensional score diagnostic-only. Do not promote it to production pruning, screening, or probability semantics based on synthetic data alone.",
    ]
    (out_dir / "cross_scan_evidence_stability.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

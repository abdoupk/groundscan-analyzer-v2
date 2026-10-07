"""Hard regression suite for GroundScan Analyzer v0.2.52.

The suite freezes the difficult synthetic families discovered in v0.2.51 and
adds target-level diagnostics for the ``void_plus_geology`` interaction.
It does not modify detector thresholds, soil corrections, or physical models.
"""

from __future__ import annotations

import json
from math import hypot
from pathlib import Path

from .benchmark import expected_patterns
from .core import SyntheticTarget
from .multiscan_benchmark import run_multiscan_benchmark

BASELINE_V051 = {
    "aggregate_fused_recall_floor": 0.8889,
    "close_multi_recall_floor": 1.0,
    "overlapping_multi_recall_floor": 1.0,
    "void_plus_geology_recall_floor": 0.6667,
    "void_plus_geology_precision_floor": 0.4444,
    "void_plus_geology_cavity_recall_floor": 0.3333,
}


def _compatible(candidate_pattern: str, target_kind: str) -> bool:
    target = SyntheticTarget(target_kind, 0.0, 0.0)
    return candidate_pattern in expected_patterns(target)


def _target_level_metrics(case: dict) -> dict:
    targets = case["truth"]["targets"]
    candidates = case["fused_candidates"]
    unused = set(range(len(candidates)))
    matched = []
    for ti, target in enumerate(targets):
        eligible = []
        for ci in unused:
            cand = candidates[ci]
            if not _compatible(cand.get("pattern_hypothesis", ""), target["kind"]):
                continue
            d = hypot(
                float(cand["x_center"]) - float(target["x"]),
                float(cand["y_center"]) - float(target["y"]),
            )
            if d <= 3.0:
                eligible.append((d, ci))
        if eligible:
            d, ci = min(eligible)
            matched.append({
                "target_index": ti,
                "kind": target["kind"],
                "candidate_id": candidates[ci]["id"],
                "distance_m": round(d, 4),
            })
            unused.remove(ci)
    by_kind: dict[str, dict] = {}
    for kind in sorted({t["kind"] for t in targets}):
        total = sum(1 for t in targets if t["kind"] == kind)
        hit = sum(1 for m in matched if m["kind"] == kind)
        by_kind[kind] = {
            "targets": total,
            "matched": hit,
            "recall": round(hit / total, 4) if total else 1.0,
        }
    return {
        "target_matches": matched,
        "by_kind": by_kind,
        "unmatched_candidate_count": len(unused),
    }


def run_hard_regression(
    out_dir: str | Path,
    *,
    count: int = 18,
    seed: int = 2047,
    fusion_resolution: int = 24,
) -> dict:
    """Run the frozen hard regression set and publish explicit guardrails."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = run_multiscan_benchmark(
        out_dir / "full",
        count=count,
        seed=seed,
        fusion_resolution=fusion_resolution,
    )

    cases = payload["cases"]
    hard_cases = [
        c for c in cases if c["family"] in {"close_multi", "overlapping_multi", "void_plus_geology"}
    ]
    for case in hard_cases:
        if case["family"] == "void_plus_geology":
            case["target_level"] = _target_level_metrics(case)

    def agg(rows: list[dict]) -> dict:
        targets = sum(int(r["targets"]) for r in rows)
        candidates = sum(int(r["fused_raw"]["candidates"]) for r in rows)
        matched = sum(int(r["fused_raw"]["matched_targets"]) for r in rows)
        false_positives = sum(int(r["fused_raw"]["false_positives"]) for r in rows)
        return {
            "sites": len(rows),
            "targets": targets,
            "candidates": candidates,
            "matched_targets": matched,
            "false_positives": false_positives,
            "recall": round(matched / targets, 4) if targets else 1.0,
            "precision": round(matched / candidates, 4)
            if candidates
            else (1.0 if not targets else 0.0),
        }

    family = {}
    for fam in ("close_multi", "overlapping_multi", "void_plus_geology"):
        subset = [c for c in hard_cases if c["family"] == fam]
        family[fam] = agg(subset)

    void_cases = [c for c in hard_cases if c["family"] == "void_plus_geology"]
    cavity_targets = sum(
        c["target_level"]["by_kind"].get("cavity", {}).get("targets", 0) for c in void_cases
    )
    cavity_matched = sum(
        c["target_level"]["by_kind"].get("cavity", {}).get("matched", 0) for c in void_cases
    )
    geology_targets = sum(
        c["target_level"]["by_kind"].get("geology", {}).get("targets", 0) for c in void_cases
    )
    geology_matched = sum(
        c["target_level"]["by_kind"].get("geology", {}).get("matched", 0) for c in void_cases
    )

    metrics = {
        "hard_fused": agg(hard_cases),
        "family": family,
        "void_plus_geology_target_level": {
            "cavity_targets": cavity_targets,
            "cavity_matched": cavity_matched,
            "cavity_recall": round(cavity_matched / cavity_targets, 4) if cavity_targets else 1.0,
            "geology_targets": geology_targets,
            "geology_matched": geology_matched,
            "geology_recall": round(geology_matched / geology_targets, 4)
            if geology_targets
            else 1.0,
        },
    }

    checks = {
        "aggregate_fused_recall_not_regressed": metrics["hard_fused"]["recall"]
        >= BASELINE_V051["aggregate_fused_recall_floor"],
        "close_multi_recall_not_regressed": family["close_multi"]["recall"]
        >= BASELINE_V051["close_multi_recall_floor"],
        "overlapping_multi_recall_not_regressed": family["overlapping_multi"]["recall"]
        >= BASELINE_V051["overlapping_multi_recall_floor"],
        "void_plus_geology_recall_not_regressed": family["void_plus_geology"]["recall"]
        >= BASELINE_V051["void_plus_geology_recall_floor"],
        "void_plus_geology_precision_not_regressed": family["void_plus_geology"]["precision"]
        >= BASELINE_V051["void_plus_geology_precision_floor"],
        "void_plus_geology_cavity_recall_not_regressed": metrics["void_plus_geology_target_level"][
            "cavity_recall"
        ]
        >= BASELINE_V051["void_plus_geology_cavity_recall_floor"],
    }

    result = {
        "benchmark": "hard_regression",
        "baseline_reference": {"version": "0.2.51", "floors": BASELINE_V051},
        "source_benchmark": {
            "count": payload["count"],
            "seed": payload["seed"],
            "scan_count": payload["scan_count"],
            "fusion_resolution": payload["fusion_resolution"],
        },
        "metrics": metrics,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "cases": hard_cases,
        "guardrails": {
            "synthetic_only": True,
            "not_field_validation": True,
            "no_detector_threshold_changes": True,
            "no_soil_correction_changes": True,
            "no_physical_inversion": True,
            "purpose": "freeze and diagnose difficult regression behavior before any future production scoring change",
        },
    }
    (out_dir / "hard_regression.json").write_text(
        json.dumps(result, indent=2, allow_nan=True), encoding="utf-8"
    )
    (out_dir / "hard_regression.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _markdown(result: dict) -> str:
    m = result["metrics"]
    f = m["family"]
    v = m["void_plus_geology_target_level"]
    lines = [
        "# GroundScan Analyzer v0.2.52 — Hard Regression Set",
        "",
        "> Synthetic software regression only. This does not establish field accuracy, physical detector performance, material identification, or proof of a void/tunnel.",
        "",
        f"Frozen families: **close_multi, overlapping_multi, void_plus_geology**; sites: **{sum(x['sites'] for x in f.values())}**; scans/site: **{result['source_benchmark']['scan_count']}**.",
        "",
        "## Regression metrics",
        "",
        "| Family | Recall | Precision | Matched | Candidates |",
        "|---|---:|---:|---:|---:|",
    ]
    for fam in ("close_multi", "overlapping_multi", "void_plus_geology"):
        x = f[fam]
        lines.append(
            f"| {fam} | {x['recall']:.4f} | {x['precision']:.4f} | {x['matched_targets']} | {x['candidates']} |"
        )
    lines += [
        "",
        "## void_plus_geology target-level diagnosis",
        "",
        f"Cavity recall: **{v['cavity_recall']:.4f}** ({v['cavity_matched']}/{v['cavity_targets']}). Geology recall: **{v['geology_recall']:.4f}** ({v['geology_matched']}/{v['geology_targets']}).",
        "",
        "This separates the broad geology component from the cavity component so an aggregate site recall cannot hide a cavity-specific miss.",
        "",
        "## Guardrails",
        "",
    ]
    for name, passed in result["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — {name}")
    lines += [
        "",
        f"**Overall regression status: {'PASS' if result['all_checks_pass'] else 'FAIL'}**",
        "",
        "No detector threshold, soil correction, or physical inversion change is enabled by this release.",
        "",
    ]
    return "\n".join(lines)

"""v0.2.80 compound-registration interaction analysis.

Diagnostic-only. No production registration behavior is changed.
Measures nonlinear degradation from combinations of acquisition corruptions by
comparing pair/triple/full-compound evidence against the worst relevant lower-
order condition. This is intended to guide recovery design, not to tune gates.
"""

from __future__ import annotations

import itertools
import json
import zlib
from pathlib import Path
from statistics import mean

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import align_grids
from groundscan.validation.synthetic_core.acquisition_stress import _scenario
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.robustness import PerturbationProfile
from groundscan_research.registration_compound_atlas import ATOMIC, SELECTED_TRIPLES, _combine
from groundscan_research.registration_failure_semantics import (
    FAMILIES,
    _build_semantic_scan,
    _failure_flags,
    _severity,
)

ATOMIC_NAMES = tuple(ATOMIC)


def _stable_seed(base: int, token: str) -> int:
    return int((base + zlib.crc32(token.encode("utf-8"))) % (2**32 - 1))


def _expected_family(delta_deg: float) -> set[str]:
    delta = float(delta_deg) % 180.0
    if min(delta, 180.0 - delta) < 22.5:
        return {"rot0", "rot180"}
    if abs(delta - 90.0) < 22.5:
        return {"rot90", "rot270"}
    return {"rot0", "rot90", "rot180", "rot270"}


def _detail(reference: ScanObservation, other: ScanObservation, *, resolution: int) -> dict:
    al = align_grids(
        reference.anomaly.zscore,
        other.anomaly.zscore,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=reference.scan.metadata.orientation_deg,
        orientation_b_deg=other.scan.metadata.orientation_deg,
    )
    allowed = _expected_family(
        float(other.scan.metadata.orientation_deg or 0.0)
        - float(reference.scan.metadata.orientation_deg or 0.0)
    )
    flags = _failure_flags(al)
    family_match = al.transform_name in allowed
    if not family_match:
        flags.append("transform_family_mismatch")
    return {
        "registration_evidence": float(al.registration_evidence),
        "correlation": float(al.correlation),
        "multiscale_correlation": float(al.multiscale_correlation),
        "overlap_fraction": float(al.overlap_fraction),
        "ambiguity_margin": float(al.ambiguity_margin),
        "status": al.status,
        "severity": _severity(al, flags),
        "transform_family_match": bool(family_match),
        "failure_flags": sorted(set(flags)),
    }


def _aggregate(vals: list[dict]) -> dict:
    n = len(vals)
    return {
        "n": n,
        "mean_evidence": mean([v["registration_evidence"] for v in vals]) if vals else 0.0,
        "mean_correlation": mean([v["correlation"] for v in vals]) if vals else 0.0,
        "mean_overlap": mean([v["overlap_fraction"] for v in vals]) if vals else 0.0,
        "strong_rate": sum(v["status"] == "strong" for v in vals) / n if n else 0.0,
        "family_match_rate": sum(v["transform_family_match"] for v in vals) / n if n else 0.0,
    }


def _condition_list() -> list[tuple[str, tuple[str, ...]]]:
    conditions: list[tuple[str, tuple[str, ...]]] = [("clean", ())]
    conditions.extend((name, (name,)) for name in ATOMIC_NAMES)
    conditions.extend(("+".join(pair), pair) for pair in itertools.combinations(ATOMIC_NAMES, 2))
    conditions.extend(("+".join(triple), triple) for triple in SELECTED_TRIPLES)
    conditions.append(("full_compound", ATOMIC_NAMES))
    return conditions


def _build_rows(
    out_dir: Path,
    *,
    seed: int,
    count_per_family: int,
    resolution: int,
) -> list[dict]:
    rows: list[dict] = []
    conditions = _condition_list()
    for family in FAMILIES:
        for i in range(int(count_per_family)):
            site_index = len({r["site_id"] for r in rows})
            scenario = _scenario(family, site_index, seed)
            base_scan, _truth = generate_scan(scenario)
            ref_scan = _build_semantic_scan(
                base_scan,
                scenario,
                0.0,
                PerturbationProfile("clean"),
                _stable_seed(seed + site_index * 1000, "reference"),
            )
            ref_result = analyze(
                ref_scan,
                out_dir / "sites" / scenario.name / "reference",
                config=AnalysisConfig(),
                write_outputs=False,
            )
            ref_obs = ScanObservation(
                "reference",
                ref_scan,
                ref_result.grid,
                ref_result.anomaly,
                detect_artifacts(ref_result.grid, ref_result.anomaly),
                ref_result.candidates,
            )
            for c_idx, (condition, names) in enumerate(conditions):
                orientation = (
                    90.0 if ((site_index + c_idx) % 2 == 1 and condition != "clean") else 0.0
                )
                profile = _combine(names)
                label = f"{condition}__{int(orientation)}deg"
                scan = _build_semantic_scan(
                    base_scan,
                    scenario,
                    orientation,
                    profile,
                    _stable_seed(seed + site_index * 1000, label),
                )
                result = analyze(
                    scan,
                    out_dir / "sites" / scenario.name / condition / f"o{int(orientation)}",
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                obs = ScanObservation(
                    label,
                    scan,
                    result.grid,
                    result.anomaly,
                    detect_artifacts(result.grid, result.anomaly),
                    result.candidates,
                )
                detail = _detail(ref_obs, obs, resolution=resolution)
                rows.append({
                    **detail,
                    "site_id": scenario.name,
                    "family": family,
                    "condition": condition,
                    "factors": list(names),
                    "factor_count": len(names),
                    "orientation_deg": orientation,
                })
    return rows


def run_compound_interaction_analysis(
    out_dir: str | Path,
    *,
    count_per_family: int = 2,
    seed: int = 8080,
    resolution: int = 20,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = _build_rows(out, seed=seed, count_per_family=count_per_family, resolution=resolution)
    condition_map: dict[str, list[dict]] = {}
    for r in rows:
        condition_map.setdefault(r["condition"], []).append(r)
    condition_summary = {k: _aggregate(v) for k, v in condition_map.items()}

    singles = {name: condition_summary[name]["mean_evidence"] for name in ATOMIC_NAMES}
    pair_rows: list[dict] = []
    for a, b in itertools.combinations(ATOMIC_NAMES, 2):
        pair = f"{a}+{b}"
        pair_e = condition_summary[pair]["mean_evidence"]
        worst_single = min(singles[a], singles[b])
        best_single = max(singles[a], singles[b])
        pair_rows.append({
            "condition": pair,
            "factors": [a, b],
            "mean_evidence": pair_e,
            "delta_vs_worst_single": pair_e - worst_single,
            "delta_vs_best_single": pair_e - best_single,
            "strong_rate": condition_summary[pair]["strong_rate"],
        })
    pair_rows.sort(key=lambda x: x["delta_vs_worst_single"])

    triple_rows: list[dict] = []
    for triple in SELECTED_TRIPLES:
        name = "+".join(triple)
        triple_e = condition_summary[name]["mean_evidence"]
        pair_names = ["+".join(sorted(p)) for p in itertools.combinations(triple, 2)]
        pair_e = [
            condition_summary[p]["mean_evidence"] for p in pair_names if p in condition_summary
        ]
        worst_pair = min(pair_e) if pair_e else 0.0
        triple_rows.append({
            "condition": name,
            "factors": list(triple),
            "mean_evidence": triple_e,
            "delta_vs_worst_pair": triple_e - worst_pair,
            "strong_rate": condition_summary[name]["strong_rate"],
        })
    triple_rows.sort(key=lambda x: x["delta_vs_worst_pair"])

    full_e = condition_summary["full_compound"]["mean_evidence"]
    full_pair_e = [r["mean_evidence"] for r in pair_rows]
    full_triple_e = [r["mean_evidence"] for r in triple_rows]
    decision = {
        "production_change": False,
        "compound_unresolved": True,
        "dominant_pair_interaction": pair_rows[0] if pair_rows else None,
        "dominant_triple_interaction": triple_rows[0] if triple_rows else None,
        "full_compound_evidence": full_e,
        "full_minus_worst_pair": full_e - min(full_pair_e) if full_pair_e else 0.0,
        "full_minus_worst_triple": full_e - min(full_triple_e) if full_triple_e else 0.0,
    }
    payload = {
        "version": "0.2.80",
        "benchmark": "compound_interaction_analysis",
        "seed": seed,
        "sites": len({r["site_id"] for r in rows}),
        "alignments": len(rows),
        "count_per_family": count_per_family,
        "resolution": resolution,
        "condition_summary": condition_summary,
        "pair_interactions": pair_rows,
        "triple_interactions": triple_rows,
        "decision": decision,
        "validation_boundary": "Synthetic diagnostic only; no independently verified field ground truth is available.",
    }
    (out / "compound_interaction_analysis.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.80 — Compound Registration Interaction Analysis",
        "",
        "> Diagnostic-only. No production registration behavior changed.",
        "",
        f"Seed: **{seed}**; sites: **{payload['sites']}**; alignments: **{payload['alignments']}**.",
        "",
        "## Condition summary",
        "",
        "| Condition | Evidence | Correlation | Overlap | Strong | Family match |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, s in condition_summary.items():
        lines.append(
            f"| {name} | {s['mean_evidence']:.3f} | {s['mean_correlation']:.3f} | {s['mean_overlap']:.3f} | {s['strong_rate']:.1%} | {s['family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## Worst pair interactions",
        "",
        "| Pair | Mean evidence | Δ vs worst single | Strong |",
        "|---|---:|---:|---:|",
    ]
    for r in pair_rows[:8]:
        lines.append(
            f"| {r['condition']} | {r['mean_evidence']:.3f} | {r['delta_vs_worst_single']:+.3f} | {r['strong_rate']:.1%} |"
        )
    lines += [
        "",
        "## Worst selected triple interactions",
        "",
        "| Triple | Mean evidence | Δ vs worst pair | Strong |",
        "|---|---:|---:|---:|",
    ]
    for r in triple_rows:
        lines.append(
            f"| {r['condition']} | {r['mean_evidence']:.3f} | {r['delta_vs_worst_pair']:+.3f} | {r['strong_rate']:.1%} |"
        )
    lines += [
        "",
        "## Full compound",
        "",
        f"- Mean evidence: **{full_e:.3f}**",
        f"- Difference from worst pair: **{decision['full_minus_worst_pair']:+.3f}**",
        f"- Difference from worst selected triple: **{decision['full_minus_worst_triple']:+.3f}**",
        "",
        "## Decision",
        "",
        "The analysis is diagnostic only. The dominant interactions are used to prioritize recovery experiments; no production registration gate or detector score is changed.",
        "",
        "## Validation boundary",
        "",
        "Synthetic data only. Results do not establish field registration or detection accuracy.",
        "",
    ]
    (out / "compound_interaction_analysis.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

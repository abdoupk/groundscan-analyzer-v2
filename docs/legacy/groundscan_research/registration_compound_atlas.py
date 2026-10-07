"""v0.2.77 compound registration failure atlas.

Diagnostic-only. Decomposes compound acquisition corruption into singles, pairs,
and selected triples using the v0.2.74 scan-frame orientation contract.
No production registration algorithm or detector policy is changed.
"""

from __future__ import annotations

import itertools
import json
import zlib
from collections.abc import Iterable
from pathlib import Path

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import align_grids
from groundscan.validation.synthetic_core.acquisition_stress import _safe_mean, _scenario
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.robustness import PerturbationProfile
from groundscan_research.registration_failure_semantics import (
    FAILURE_THRESHOLDS,
    FAMILIES,
    _build_semantic_scan,
    _failure_flags,
    _severity,
)

ATOMIC: dict[str, PerturbationProfile] = {
    "noise": PerturbationProfile("noise", extra_noise_sigma=1.6),
    "dropout": PerturbationProfile("dropout", missing_fraction=0.12, drop_row_fraction=0.06),
    "partial_coverage": PerturbationProfile(
        "partial_coverage", missing_fraction=0.22, drop_row_fraction=0.18
    ),
    "drift": PerturbationProfile(
        "drift", baseline_drift_x=0.10, baseline_drift_y=-0.07, line_bias_sigma=0.9
    ),
    "outliers": PerturbationProfile("outliers", outlier_fraction=0.025, outlier_sigma=18.0),
    "jitter": PerturbationProfile("jitter", coordinate_jitter_m=0.16),
}

SELECTED_TRIPLES = (
    ("noise", "dropout", "partial_coverage"),
    ("noise", "drift", "outliers"),
    ("dropout", "drift", "partial_coverage"),
    ("drift", "outliers", "jitter"),
    ("noise", "dropout", "drift"),
    ("noise", "partial_coverage", "outliers"),
)


def _stable_seed(base: int, token: str) -> int:
    return int((base + zlib.crc32(token.encode("utf-8"))) % (2**32 - 1))


def _combine(names: Iterable[str]) -> PerturbationProfile:
    names = tuple(names)
    if not names:
        return PerturbationProfile("clean")
    fields = {
        k: 0.0
        for k in (
            "extra_noise_sigma",
            "outlier_fraction",
            "outlier_sigma",
            "missing_fraction",
            "drop_row_fraction",
            "duplicate_fraction",
            "coordinate_jitter_m",
            "baseline_drift_x",
            "baseline_drift_y",
            "line_bias_sigma",
            "quantization_step",
        )
    }
    clip_percentile = None
    for name in names:
        p = ATOMIC[name]
        for key in fields:
            fields[key] += float(getattr(p, key))
        if p.clip_percentile is not None:
            clip_percentile = min(clip_percentile or p.clip_percentile, p.clip_percentile)
    return PerturbationProfile(name="+".join(names), **fields, clip_percentile=clip_percentile)


def _expected_family(delta_deg: float) -> set[str]:
    delta = float(delta_deg) % 180.0
    if min(delta, 180.0 - delta) < 22.5:
        return {"rot0", "rot180"}
    if abs(delta - 90.0) < 22.5:
        return {"rot90", "rot270"}
    return {"rot0", "rot90", "rot180", "rot270"}


def _pair_detail(reference: ScanObservation, other: ScanObservation, *, resolution: int) -> dict:
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
    if al.transform_name not in allowed:
        flags.append("transform_family_mismatch")
    return {
        "status": al.status,
        "severity": _severity(al, flags),
        "registration_evidence": float(al.registration_evidence),
        "correlation": float(al.correlation),
        "multiscale_correlation": float(al.multiscale_correlation),
        "overlap_fraction": float(al.overlap_fraction),
        "ambiguity_margin": float(al.ambiguity_margin),
        "candidate_count": int(al.candidate_count),
        "transform": al.transform_name,
        "transform_family_match": bool(al.transform_name in allowed),
        "failure_flags": sorted(set(flags)),
    }


def run_registration_compound_atlas(
    out_dir: str | Path,
    *,
    count_per_family: int = 2,
    seed: int = 7777,
    resolution: int = 32,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conditions: list[tuple[str, tuple[str, ...]]] = [("clean", ())]
    conditions.extend((name, (name,)) for name in ATOMIC)
    conditions.extend(("+".join(pair), pair) for pair in itertools.combinations(ATOMIC, 2))
    conditions.extend(("+".join(triple), triple) for triple in SELECTED_TRIPLES)
    all_names = tuple(ATOMIC)
    conditions.append(("full_compound", all_names))

    rows: list[dict] = []
    by_condition: dict[str, list[dict]] = {name: [] for name, _ in conditions}

    for family in FAMILIES:
        for i in range(int(count_per_family)):
            site_index = len(rows)
            scenario = _scenario(family, site_index, seed)
            base_scan, _truth = generate_scan(scenario)
            ref_scan = _build_semantic_scan(
                base_scan,
                scenario,
                0.0,
                PerturbationProfile("clean"),
                _stable_seed(seed + site_index * 1000, "clean"),
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
            site_details = []
            for condition, names in conditions:
                profile = _combine(names)
                # Alternate frame orientation only for a fraction of the cases, after fixing semantics.
                orientation = (
                    90.0 if ((site_index + len(names)) % 2 == 1 and condition != "clean") else 0.0
                )
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
                other_anomaly = result.anomaly
                # _build_semantic_scan already physically rotates the signal. Do not rotate the analyzed map again.
                obs = ScanObservation(
                    label,
                    scan,
                    result.grid,
                    other_anomaly,
                    detect_artifacts(result.grid, other_anomaly),
                    result.candidates,
                )
                detail = _pair_detail(ref_obs, obs, resolution=resolution)
                detail.update({
                    "site_id": scenario.name,
                    "family": family,
                    "condition": condition,
                    "factors": list(names),
                    "factor_count": len(names),
                    "orientation_deg": orientation,
                })
                rows.append(detail)
                by_condition[condition].append(detail)

    # Condition-level summaries and pair interaction effects.
    summary: dict[str, dict] = {}
    for name, _ in conditions:
        vals = by_condition[name]
        summary[name] = {
            "n": len(vals),
            "mean_evidence": round(_safe_mean([v["registration_evidence"] for v in vals]), 4),
            "mean_correlation": round(_safe_mean([v["correlation"] for v in vals]), 4),
            "mean_overlap": round(_safe_mean([v["overlap_fraction"] for v in vals]), 4),
            "strong_rate": round(sum(v["status"] == "strong" for v in vals) / max(len(vals), 1), 4),
            "family_match_rate": round(
                sum(v["transform_family_match"] for v in vals) / max(len(vals), 1), 4
            ),
            "critical_rate": round(
                sum(v["severity"] == "critical" for v in vals) / max(len(vals), 1), 4
            ),
            "flag_counts": {},
        }
        counts: dict[str, int] = {}
        for v in vals:
            for flag in v["failure_flags"]:
                if flag != "none":
                    counts[flag] = counts.get(flag, 0) + 1
        summary[name]["flag_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    singles = {n: summary[n]["mean_evidence"] for n in ATOMIC}
    pair_interactions = []
    for a, b in itertools.combinations(ATOMIC, 2):
        name = f"{a}+{b}"
        pair_e = summary[name]["mean_evidence"]
        baseline = min(singles[a], singles[b])
        pair_interactions.append({
            "pair": name,
            "single_a": singles[a],
            "single_b": singles[b],
            "pair": name,
            "pair_mean_evidence": pair_e,
            "interaction_delta_vs_worst_single": round(pair_e - baseline, 4),
            "strong_rate": summary[name]["strong_rate"],
        })
    pair_interactions.sort(key=lambda r: r["interaction_delta_vs_worst_single"])

    strongest_degradation = pair_interactions[:8]
    compound = summary["full_compound"]
    payload = {
        "version": "0.2.77",
        "benchmark": "registration_compound_atlas",
        "sites": len(set(r["site_id"] for r in rows)),
        "alignments": len(rows),
        "count_per_family": int(count_per_family),
        "seed": int(seed),
        "resolution": int(resolution),
        "atomic_factors": list(ATOMIC),
        "selected_triples": [list(x) for x in SELECTED_TRIPLES],
        "failure_thresholds": FAILURE_THRESHOLDS,
        "summary": summary,
        "pair_interactions": pair_interactions,
        "strongest_pair_degradations": strongest_degradation,
        "full_compound": compound,
        "decision": "diagnostic_only_no_production_registration_change",
        "field_data_status": "No independently verified field ground truth is available; synthetic testing only.",
    }
    (out_dir / "registration_compound_atlas.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.77 — Compound Registration Failure Atlas",
        "",
        "> Diagnostic-only. Production registration is unchanged.",
        "> The benchmark isolates single factors, all pairwise interactions, selected triples, and a full compound condition under the v0.2.74 scan-frame orientation contract.",
        "",
        f"Sites: **{payload['sites']}**; alignments: **{payload['alignments']}**; seed: **{seed}**.",
        "",
        "## Condition summary",
        "",
        "| Condition | N | Mean evidence | Strong | Mean corr | Mean overlap | Family match |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, _ in conditions:
        m = summary[name]
        lines.append(
            f"| {name} | {m['n']} | {m['mean_evidence']:.3f} | {m['strong_rate']:.1%} | {m['mean_correlation']:.3f} | {m['mean_overlap']:.3f} | {m['family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## Strongest pair degradations",
        "",
        "Pairs are ranked by evidence loss relative to the worse of their two single-factor baselines. Negative values indicate a compound interaction that is worse than either factor alone.",
        "",
        "| Pair | Single A | Single B | Pair | Interaction Δ | Strong |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in strongest_degradation:
        lines.append(
            f"| {r['pair']} | {r['single_a']:.3f} | {r['single_b']:.3f} | {r['pair_mean_evidence']:.3f} | {r['interaction_delta_vs_worst_single']:+.3f} | {r['strong_rate']:.1%} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "This atlas is intended to identify interaction effects before choosing any registration recovery. A low score in a compound condition is not treated as proof that one factor is causal; the pairwise/triple structure is used to prioritize controlled follow-up experiments.",
        "",
        "## Decision",
        "",
        "No production registration or detector change is enabled by this release.",
        "",
        "## Validation boundary",
        "",
        "Synthetic stress tests characterize software robustness and reproducibility. They do not establish field registration accuracy or physical detection accuracy.",
        "",
    ]
    (out_dir / "registration_compound_atlas.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

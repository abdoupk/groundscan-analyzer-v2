"""v0.2.81 controlled compound registration recovery.

Diagnostic-only. Production registration is unchanged.

A conservative compound-recovery proposal is considered recoverable only when
both independent recovery searches (coverage-aware and outlier-robust) agree on
transform + shift and the shared alignment satisfies the frozen quality gates.
The intent is to test whether compound corruption can be recovered without
accepting a single optimistic alignment.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan_research.registration_failure_semantics import (
    FAMILIES,
    _build_semantic_scan,
    _expected_family,
    _profiles075,
)
from groundscan_research.registration_recovery_coverage import (
    RECOVERY_CORR_MIN,
    RECOVERY_MARGIN_MIN,
    RECOVERY_MULTI_MIN,
    _align_recovery,
    _pair_result,
)

MODES = ("production", "coverage-aware", "robust", "hybrid", "consensus-recovery")
DEFAULT_PROFILES = ("partial_coverage", "outliers", "compound")
DEFAULT_FAMILIES = ("single_compact", "overlapping_multi", "void_plus_geology")


def _mean(values):
    vals = [float(v) for v in values if np.isfinite(float(v))]
    return float(np.mean(vals)) if vals else 0.0


def _consensus_pair(reference: ScanObservation, other: ScanObservation, *, resolution: int) -> dict:
    oa = reference.scan.metadata.orientation_deg
    ob = other.scan.metadata.orientation_deg
    coverage = _align_recovery(
        reference.anomaly.zscore,
        other.anomaly.zscore,
        orientation_a_deg=oa,
        orientation_b_deg=ob,
        resolution=resolution,
        max_shift=2,
        min_overlap_fraction=0.30,
        robust=False,
    )
    robust = _align_recovery(
        reference.anomaly.zscore,
        other.anomaly.zscore,
        orientation_a_deg=oa,
        orientation_b_deg=ob,
        resolution=resolution,
        max_shift=2,
        min_overlap_fraction=0.50,
        robust=True,
    )
    transform_agree = coverage.transform_name == robust.transform_name
    shift_agree = coverage.shift_dy == robust.shift_dy and coverage.shift_dx == robust.shift_dx
    family_match = coverage.transform_name in set(
        _expected_family(float(ob or 0.0) - float(oa or 0.0))
    )
    shared_score = min(float(coverage.registration_evidence), float(robust.registration_evidence))
    shared_corr = min(float(coverage.correlation), float(robust.correlation))
    shared_multi = min(float(coverage.multiscale_correlation), float(robust.multiscale_correlation))
    shared_margin = min(float(coverage.ambiguity_margin), float(robust.ambiguity_margin))
    eligible = bool(
        transform_agree
        and shift_agree
        and family_match
        and shared_corr >= RECOVERY_CORR_MIN
        and shared_multi >= RECOVERY_MULTI_MIN
        and shared_margin >= RECOVERY_MARGIN_MIN
    )
    return {
        "mode": "consensus-recovery",
        "transform": coverage.transform_name
        if transform_agree
        else f"{coverage.transform_name}|{robust.transform_name}",
        "shift_dy": int(coverage.shift_dy) if shift_agree else None,
        "shift_dx": int(coverage.shift_dx) if shift_agree else None,
        "coverage_evidence": float(coverage.registration_evidence),
        "robust_evidence": float(robust.registration_evidence),
        "registration_evidence": round(shared_score, 6),
        "correlation": round(shared_corr, 6),
        "multiscale_correlation": round(shared_multi, 6),
        "ambiguity_margin": round(shared_margin, 6),
        "transform_agree": bool(transform_agree),
        "shift_agree": bool(shift_agree),
        "family_match": bool(family_match),
        "recovery_eligible": eligible,
        "recovery_label": "compound-consensus-recovered" if eligible else "not-recovered",
    }


def run_registration_compound_recovery(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = (8181,),
    count_per_family: int = 2,
    resolution: int = 20,
    profiles: tuple[str, ...] = DEFAULT_PROFILES,
    families: tuple[str, ...] = DEFAULT_FAMILIES,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prof_objs = tuple(p for p in _profiles075() if p.name in set(profiles))
    fams = tuple(f for f in FAMILIES if f in set(families))
    runs = []
    for seed in seeds:
        rows = []
        for family in fams:
            for i in range(int(count_per_family)):
                idx = len(rows)
                scenario = __import__(
                    "groundscan.validation.synthetic_core.acquisition_stress",
                    fromlist=["_scenario"],
                )._scenario(family, idx, seed)
                base_scan, truth = generate_scan(scenario)
                base_profile = next((p for p in prof_objs if p.name == "clean"), prof_objs[0])
                ref_scan = _build_semantic_scan(
                    base_scan, scenario, 0.0, base_profile, seed + idx * 1000
                )
                ref_result = analyze(
                    ref_scan,
                    out / f"seed_{seed}" / scenario.name / "reference",
                    label="reference",
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                reference = ScanObservation(
                    "reference",
                    ref_scan,
                    ref_result.grid,
                    ref_result.anomaly,
                    detect_artifacts(ref_result.grid, ref_result.anomaly),
                    ref_result.candidates,
                )
                for p_idx, profile in enumerate(prof_objs):
                    for orientation in (0.0, 90.0):
                        label = f"{orientation:g}deg__{profile.name}"
                        scan = _build_semantic_scan(
                            base_scan,
                            scenario,
                            orientation,
                            profile,
                            seed + idx * 1000 + p_idx * 101 + int(orientation),
                        )
                        rr = analyze(
                            scan,
                            out / f"seed_{seed}" / scenario.name / label,
                            label=label,
                            config=AnalysisConfig(),
                            write_outputs=False,
                        )
                        rot = __import__(
                            "groundscan_research.registration_failure_semantics",
                            fromlist=["_physical_rotate_anomaly"],
                        )._physical_rotate_anomaly(rr.anomaly, orientation)
                        other = ScanObservation(
                            label, scan, rr.grid, rot, detect_artifacts(rr.grid, rot), rr.candidates
                        )
                        baseline = _pair_result(
                            reference, other, mode="production", resolution=resolution
                        )
                        cov = _pair_result(
                            reference, other, mode="coverage-aware", resolution=resolution
                        )
                        rob = _pair_result(reference, other, mode="robust", resolution=resolution)
                        hyb = _pair_result(reference, other, mode="hybrid", resolution=resolution)
                        cons = _consensus_pair(reference, other, resolution=resolution)
                        rows.append({
                            "site_id": scenario.name,
                            "family": family,
                            "profile": profile.name,
                            "orientation_deg": orientation,
                            "truth_targets": len(truth["targets"]),
                            "production": baseline,
                            "coverage-aware": cov,
                            "robust": rob,
                            "hybrid": hyb,
                            "consensus-recovery": cons,
                        })
        runs.append({"seed": int(seed), "rows": rows})

    aggregates = {}
    for mode in MODES:
        cells = []
        for run in runs:
            for row in run["rows"]:
                d = row[mode]
                cells.append(d)
        aggregates[mode] = {
            "alignments": len(cells),
            "mean_evidence": round(_mean([d.get("registration_evidence", 0.0) for d in cells]), 4),
            "family_match_rate": round(
                float(np.mean([bool(d.get("family_match", False)) for d in cells])), 4
            )
            if cells
            else 0.0,
            "eligible_rate": round(
                float(np.mean([bool(d.get("recovery_eligible", False)) for d in cells])), 4
            )
            if cells
            else 0.0,
        }

    by_profile = {}
    for profile in profiles:
        by_profile[profile] = {}
        for mode in MODES:
            cells = [r[mode] for run in runs for r in run["rows"] if r["profile"] == profile]
            by_profile[profile][mode] = {
                "alignments": len(cells),
                "mean_evidence": round(
                    _mean([d.get("registration_evidence", 0.0) for d in cells]), 4
                ),
                "family_match_rate": round(
                    float(np.mean([bool(d.get("family_match", False)) for d in cells])), 4
                )
                if cells
                else 0.0,
                "eligible_rate": round(
                    float(np.mean([bool(d.get("recovery_eligible", False)) for d in cells])), 4
                )
                if cells
                else 0.0,
                "transform_agreement_rate": round(
                    float(np.mean([bool(d.get("transform_agree", True)) for d in cells])), 4
                )
                if cells
                else 0.0,
                "shift_agreement_rate": round(
                    float(np.mean([bool(d.get("shift_agree", True)) for d in cells])), 4
                )
                if cells
                else 0.0,
            }

    payload = {
        "version": "0.2.81",
        "benchmark": "registration_compound_recovery",
        "seeds": [int(s) for s in seeds],
        "runs": len(runs),
        "sites_total": sum(len(r["rows"]) for r in runs),
        "alignments_total": sum(len(r["rows"]) * 1 for r in runs),
        "profiles": list(profiles),
        "families": list(families),
        "aggregates": aggregates,
        "by_profile": by_profile,
        "decision": "diagnostic_only_no_production_registration_change",
        "validation_boundary": "Synthetic only; no independently verified field ground truth is available.",
    }
    (out / "registration_compound_recovery.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.81 — Controlled Compound Registration Recovery",
        "",
        "> Diagnostic-only. Production registration is unchanged.",
        "",
        f"Seeds: **{len(seeds)}**; sites: **{payload['sites_total']}**.",
        "",
        "## Consensus rule",
        "",
        "A compound recovery is eligible only when coverage-aware and robust searches agree on transform + shift, the expected transform family matches, and the shared correlation/multiscale/margin gates pass.",
        "",
        "## Aggregate",
        "",
        "| Mode | Mean evidence | Family match | Eligible |",
        "|---|---:|---:|---:|",
    ]
    for mode, m in aggregates.items():
        lines.append(
            f"| {mode} | {m['mean_evidence']:.3f} | {m['family_match_rate']:.1%} | {m['eligible_rate']:.1%} |"
        )
    lines += [
        "",
        "## By profile",
        "",
        "| Profile | Production evidence | Coverage | Robust | Hybrid | Consensus | Consensus eligible |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in profiles:
        bp = by_profile[profile]
        lines.append(
            "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.1%} |".format(
                profile,
                bp["production"]["mean_evidence"],
                bp["coverage-aware"]["mean_evidence"],
                bp["robust"]["mean_evidence"],
                bp["hybrid"]["mean_evidence"],
                bp["consensus-recovery"]["mean_evidence"],
                bp["consensus-recovery"]["eligible_rate"],
            )
        )
    lines += [
        "",
        "## Decision",
        "",
        "The consensus recovery remains diagnostic-only. No production registration, detector, fusion, pruning, scoring, or soil behavior is changed.",
        "",
        "## Validation boundary",
        "",
        "Synthetic software validation only. This does not establish field registration or detection accuracy.",
    ]
    (out / "registration_compound_recovery.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

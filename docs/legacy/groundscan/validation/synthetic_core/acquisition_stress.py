"""v0.2.71 synthetic acquisition-stress audit.

Diagnostic-only. This module does not change production detector/fusion/scoring.
It composes existing scan-design variation with bounded signal/acquisition
corruptions to probe robustness under harsher synthetic conditions.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from ...api import AnalysisConfig, analyze
from ...core.artifact import detect_artifacts
from ...site.analyze_site import ScanObservation
from .benchmark_large import evaluate_case
from .core import generate_scan
from .cross_scan_variation_audit import _apply_variation, _fuse, _scenario
from .robustness import PerturbationProfile, perturb_scan

FAMILIES = (
    "single_compact",
    "single_cavity",
    "single_tunnel",
    "close_multi",
    "overlapping_multi",
    "void_plus_geology",
)


def _profiles() -> tuple[PerturbationProfile, ...]:
    return (
        PerturbationProfile("clean"),
        PerturbationProfile(
            "mild",
            extra_noise_sigma=0.7,
            outlier_fraction=0.004,
            outlier_sigma=8.0,
            missing_fraction=0.02,
            coordinate_jitter_m=0.03,
            line_bias_sigma=0.25,
        ),
        PerturbationProfile(
            "moderate",
            extra_noise_sigma=1.4,
            outlier_fraction=0.010,
            outlier_sigma=12.0,
            missing_fraction=0.06,
            drop_row_fraction=0.04,
            duplicate_fraction=0.02,
            coordinate_jitter_m=0.08,
            baseline_drift_x=0.045,
            baseline_drift_y=-0.028,
            line_bias_sigma=0.55,
            quantization_step=0.05,
        ),
        PerturbationProfile(
            "severe",
            extra_noise_sigma=2.2,
            outlier_fraction=0.025,
            outlier_sigma=18.0,
            missing_fraction=0.14,
            drop_row_fraction=0.10,
            duplicate_fraction=0.04,
            coordinate_jitter_m=0.18,
            baseline_drift_x=0.11,
            baseline_drift_y=-0.075,
            line_bias_sigma=1.0,
            quantization_step=0.10,
            clip_percentile=99.0,
        ),
        PerturbationProfile(
            "partial_coverage",
            extra_noise_sigma=1.0,
            missing_fraction=0.22,
            drop_row_fraction=0.18,
            duplicate_fraction=0.01,
            coordinate_jitter_m=0.10,
            baseline_drift_x=0.05,
            baseline_drift_y=-0.03,
            line_bias_sigma=0.6,
        ),
    )


def _designs() -> tuple[dict, ...]:
    return (
        {
            "name": "H_parallel_1m",
            "orientation_deg": 0.0,
            "line_spacing_m": 1.0,
            "scan_pattern": "parallel",
            "noise_add": 0.15,
            "shift": None,
            "gain": 1.0,
        },
        {
            "name": "V_parallel_1m",
            "orientation_deg": 90.0,
            "line_spacing_m": 1.0,
            "scan_pattern": "parallel",
            "noise_add": 0.25,
            "shift": (0, 0),
            "gain": 0.99,
        },
        {
            "name": "H_zigzag_0p5m",
            "orientation_deg": 0.0,
            "line_spacing_m": 0.5,
            "scan_pattern": "zigzag",
            "noise_add": 0.45,
            "shift": (1, -1),
            "gain": 1.01,
        },
        {
            "name": "V_zigzag_0p5m",
            "orientation_deg": 90.0,
            "line_spacing_m": 0.5,
            "scan_pattern": "zigzag",
            "noise_add": 0.70,
            "shift": (-1, 1),
            "gain": 0.98,
        },
    )


def _safe_mean(values: Iterable[float]) -> float:
    """Backward-compat alias — canonical impl is groundscan._util.safe_mean."""
    from groundscan._util import safe_mean

    return safe_mean(values, default=float("nan"))


def _build_scan(base_scan, scenario, design: dict, profile: PerturbationProfile, seed: int):
    # Reuse the established design-variation transform, then stack corruption.
    from .cross_scan_variation_audit import Variation

    v = Variation(
        name=f"{design['name']}__{profile.name}",
        orientation_deg=float(design["orientation_deg"]),
        line_spacing_m=float(design["line_spacing_m"]),
        scan_pattern=str(design["scan_pattern"]),
        noise_add=float(design["noise_add"]),
        dropout=False,
        shift=design["shift"],
        gain=float(design["gain"]),
    )
    designed = _apply_variation(base_scan, scenario, v, seed)
    return perturb_scan(designed, profile, seed=seed + 7919)


def _analyze_site(scans, truth, out_dir: Path, *, resolution: int, family: str, site_id: str):
    observations = []
    registration = []
    single_results = []
    for label, scan in scans:
        result = analyze(
            scan,
            out_dir / "scans" / label,
            label=label,
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
        observations.append(obs)
        ev = evaluate_case(result.candidates, truth, split="stress", case_id=site_id, family=family)
        single_results.append(asdict(ev))
    reference = observations[0]
    from ...site.registration import align_grids
    from .cross_scan_variation_audit import _identity_alignment

    alignments = {}
    for obs in observations[1:]:
        if (
            obs.scan.metadata.orientation_deg != reference.scan.metadata.orientation_deg
            or obs.scan.metadata.line_spacing_m != reference.scan.metadata.line_spacing_m
        ):
            al = align_grids(
                reference.anomaly.zscore,
                obs.anomaly.zscore,
                resolution=resolution,
                max_shift=2,
                orientation_a_deg=reference.scan.metadata.orientation_deg,
                orientation_b_deg=obs.scan.metadata.orientation_deg,
            )
        else:
            al = _identity_alignment(reference.anomaly, obs.anomaly, resolution)
        alignments[obs.label] = al
        registration.append({
            "scan": obs.label,
            "status": al.status,
            "registration_evidence": float(al.registration_evidence),
            "overlap_fraction": float(al.overlap_fraction),
            "transform": al.transform_name,
        })
    fused = _fuse(observations, reference, alignments, resolution)
    fused_eval = evaluate_case(fused, truth, split="stress", case_id=site_id, family=family)
    return single_results, registration, asdict(fused_eval), [asdict(c) for c in fused]


def run_acquisition_stress_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 4,
    seed: int = 4071,
    fusion_resolution: int = 32,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    designs = _designs()
    profiles = _profiles()
    rows = []
    registration_rows = []
    combo_rows = []

    for family in FAMILIES:
        for i in range(int(count_per_family)):
            site_index = len(rows)
            scenario = _scenario(family, site_index, seed)
            base_scan, truth = generate_scan(scenario)
            scans = []
            for d_idx, design in enumerate(designs):
                # Rotate severity across designs so every site sees mixed acquisition quality.
                p = profiles[(d_idx + i) % len(profiles)]
                label = f"{design['name']}__{p.name}"
                scan = _build_scan(
                    base_scan, scenario, design, p, seed + site_index * 10000 + d_idx * 101 + i
                )
                scans.append((label, scan))
                combo_rows.append({
                    "site_id": scenario.name,
                    "family": family,
                    "design": design["name"],
                    "profile": p.name,
                })
            singles, regs, fused, fused_candidates = _analyze_site(
                scans,
                truth,
                out_dir,
                resolution=fusion_resolution,
                family=family,
                site_id=scenario.name,
            )
            registration_rows.extend([
                {**r, "site_id": scenario.name, "family": family} for r in regs
            ])
            rows.append({
                "site_id": scenario.name,
                "family": family,
                "targets": len(truth["targets"]),
                "single": singles,
                "fused": fused,
                "fused_candidates": fused_candidates,
            })

    fused_rows = [r["fused"] for r in rows]
    targets = sum(int(r["targets"]) for r in rows)
    candidates = sum(int(r["candidates"]) for r in fused_rows)
    matched = sum(int(r["matched_targets"]) for r in fused_rows)
    false_positives = candidates - matched

    family_summary = {}
    for family in FAMILIES:
        fs = [r["fused"] for r in rows if r["family"] == family]
        ft = sum(int(r["targets"]) for r in rows if r["family"] == family)
        fc = sum(int(r["candidates"]) for r in fs)
        fm = sum(int(r["matched_targets"]) for r in fs)
        family_summary[family] = {
            "sites": len(fs),
            "targets": ft,
            "candidates": fc,
            "matched": fm,
            "false_positives": fc - fm,
            "recall": round(fm / max(ft, 1), 4),
            "precision": round(fm / max(fc, 1), 4),
        }

    reg_e = [r["registration_evidence"] for r in registration_rows]
    reg_strong = [r for r in registration_rows if r["status"] == "strong"]
    payload = {
        "benchmark": "synthetic_acquisition_stress",
        "sites": len(rows),
        "scans_per_site": len(designs),
        "count_per_family": int(count_per_family),
        "seed": int(seed),
        "designs": designs,
        "profiles": [asdict(p) for p in profiles],
        "fused": {
            "targets": targets,
            "candidates": candidates,
            "matched": matched,
            "false_positives": false_positives,
            "recall": round(matched / max(targets, 1), 4),
            "precision": round(matched / max(candidates, 1), 4),
        },
        "family_summary": family_summary,
        "registration": {
            "alignments": len(registration_rows),
            "strong_rate": round(len(reg_strong) / max(len(registration_rows), 1), 4),
            "mean_evidence": round(_safe_mean(reg_e), 4),
            "mean_overlap": round(
                _safe_mean([r["overlap_fraction"] for r in registration_rows]), 4
            ),
        },
        "combination_count": len(combo_rows),
        "rows": rows,
        "registration_rows": registration_rows,
        "combo_rows": combo_rows,
        "decision": "diagnostic_only_no_production_change_determinism_fix",
        "field_data_status": "No independently verified field ground-truth dataset is available; results are synthetic software robustness tests.",
        "determinism_fix": "v0.2.71 makes multiscan majority tie-breaking deterministic; repeated identical-seed runs must now match.",
        "limitations": [
            "orientation and traversal are represented primarily through normalized survey metadata and registration variation, not true sensor physics",
            "line spacing is metadata plus acquisition-design variation rather than a measured field-resampling process",
            "synthetic corruption profiles are software stressors, not empirical detector error distributions",
        ],
    }
    (out_dir / "acquisition_stress.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.71 — Synthetic Acquisition Stress",
        "",
        "> Diagnostic-only synthetic robustness validation. Production detector, scoring, pruning, and fusion policies are unchanged.",
        "",
        f"Sites: **{len(rows)}**; scans/site: **{len(designs)}**; total targets: **{targets}**.",
        "",
        "## Aggregate fused result",
        "",
        f"Recall: **{payload['fused']['recall']:.2%}**; precision: **{payload['fused']['precision']:.2%}**; matched: **{matched}**; false positives: **{false_positives}**.",
        "",
        "## Family results",
        "",
        "| Family | Recall | Precision | Matched | False positives |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, m in family_summary.items():
        lines.append(
            f"| {family} | {m['recall']:.2%} | {m['precision']:.2%} | {m['matched']} | {m['false_positives']} |"
        )
    lines += [
        "",
        "## Registration",
        "",
        f"Strong registration: **{payload['registration']['strong_rate']:.2%}**; mean evidence: **{payload['registration']['mean_evidence']:.3f}**; mean overlap: **{payload['registration']['mean_overlap']:.3f}**.",
        "",
        "## Designed stressors",
        "",
        "orientation, 0.5/1.0 m line spacing, parallel/zigzag metadata, noise, dropout, partial coverage, line bias, baseline drift, coordinate jitter, outliers, duplicates, quantization, and clipping.",
        "",
        "## Decision",
        "",
        "No production change is enabled. This release is a stress benchmark to locate robustness failure modes before any future algorithmic change.",
        "",
        "## Validation boundary",
        "",
        "These are synthetic software tests and do not establish field detection accuracy, material identification, or proof of a cavity/tunnel.",
        "",
    ]
    (out_dir / "acquisition_stress.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

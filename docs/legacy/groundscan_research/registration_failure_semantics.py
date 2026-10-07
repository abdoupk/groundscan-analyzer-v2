"""v0.2.75 registration failure atlas.

Diagnostic-only. The production registration algorithm is unchanged.
This version uses a semantics-aware synthetic acquisition model: when a scan
has a 90-degree scan-frame orientation, the signal raster is physically rotated
before metadata is updated. The goal is to separate acquisition corruption from
orientation-frame effects and produce a reproducible failure atlas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import AlignmentResult, align_grids
from groundscan.validation.synthetic_core.acquisition_stress import _safe_mean, _scenario
from groundscan.validation.synthetic_core.benchmark_large import evaluate_case
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan.validation.synthetic_core.cross_scan_variation_audit import (
    Variation,
    _apply_variation,
)
from groundscan.validation.synthetic_core.robustness import PerturbationProfile, perturb_scan

FAMILIES = (
    "single_compact",
    "single_cavity",
    "single_tunnel",
    "close_multi",
    "overlapping_multi",
    "void_plus_geology",
)

FAILURE_THRESHOLDS = {
    "no_valid_alignment": 0,
    "no_overlap": 0.20,
    "insufficient_overlap": 0.50,
    "low_correlation": 0.25,
    "low_multiscale_correlation": 0.25,
    "ambiguous_transform_margin": 0.03,
    "weak_evidence": 0.50,
}


def _profiles075() -> tuple[PerturbationProfile, ...]:
    return (
        PerturbationProfile("clean"),
        PerturbationProfile("noise", extra_noise_sigma=1.6),
        PerturbationProfile("dropout", missing_fraction=0.12, drop_row_fraction=0.06),
        PerturbationProfile("partial_coverage", missing_fraction=0.22, drop_row_fraction=0.18),
        PerturbationProfile(
            "drift", baseline_drift_x=0.10, baseline_drift_y=-0.07, line_bias_sigma=0.9
        ),
        PerturbationProfile("outliers", outlier_fraction=0.025, outlier_sigma=18.0),
        PerturbationProfile("jitter", coordinate_jitter_m=0.16),
        PerturbationProfile(
            "compound",
            extra_noise_sigma=2.0,
            outlier_fraction=0.020,
            outlier_sigma=16.0,
            missing_fraction=0.12,
            drop_row_fraction=0.08,
            coordinate_jitter_m=0.14,
            baseline_drift_x=0.09,
            baseline_drift_y=-0.06,
            line_bias_sigma=0.9,
            quantization_step=0.08,
        ),
    )


def _expected_family(delta_deg: float) -> set[str]:
    delta = float(delta_deg) % 180.0
    if min(delta, 180.0 - delta) < 22.5:
        return {"rot0", "rot180", "flip_rot0", "flip_rot180"}
    if abs(delta - 90.0) < 22.5:
        return {"rot90", "rot270", "flip_rot90", "flip_rot270"}
    return {"rot0", "rot90", "rot180", "rot270"}


def _failure_flags(al: AlignmentResult) -> list[str]:
    flags: list[str] = []
    if al.candidate_count == 0:
        flags.append("no_valid_alignment")
    if al.overlap_fraction < FAILURE_THRESHOLDS["no_overlap"]:
        flags.append("no_overlap")
    elif al.overlap_fraction < FAILURE_THRESHOLDS["insufficient_overlap"]:
        flags.append("insufficient_overlap")
    if al.correlation < FAILURE_THRESHOLDS["low_correlation"]:
        flags.append("low_correlation")
    if al.multiscale_correlation < FAILURE_THRESHOLDS["low_multiscale_correlation"]:
        flags.append("low_multiscale_correlation")
    if al.ambiguity_margin < FAILURE_THRESHOLDS["ambiguous_transform_margin"]:
        flags.append("ambiguous_transform")
    if al.registration_evidence < FAILURE_THRESHOLDS["weak_evidence"]:
        flags.append("weak_evidence")
    return flags or ["none"]


def _severity(al: AlignmentResult, flags: list[str]) -> str:
    if "no_valid_alignment" in flags or al.registration_evidence < 0.25:
        return "critical"
    if "no_overlap" in flags or al.registration_evidence < 0.50:
        return "high"
    if flags != ["none"] or al.registration_evidence < 0.70:
        return "medium"
    return "low"


def _physical_rotate_anomaly(
    anomaly, orientation_deg: float, reference_orientation_deg: float = 0.0
):
    """Return an anomaly-map copy physically rotated into its scan-frame orientation."""
    from dataclasses import replace

    delta = (float(orientation_deg) - float(reference_orientation_deg)) % 360.0
    steps = int(round(delta / 90.0)) % 4
    if steps == 0:
        return anomaly
    return replace(
        anomaly,
        zscore=np.rot90(anomaly.zscore, steps),
        labels=np.rot90(anomaly.labels, steps),
        residual=np.rot90(anomaly.residual, steps),
        persistence=np.rot90(anomaly.persistence, steps),
        broad_zscore=None
        if anomaly.broad_zscore is None
        else np.rot90(anomaly.broad_zscore, steps),
        broad_persistence=None
        if anomaly.broad_persistence is None
        else np.rot90(anomaly.broad_persistence, steps),
    )


def _build_semantic_scan(
    base_scan, scenario, orientation_deg: float, profile: PerturbationProfile, seed: int
):
    variation = Variation(
        name=f"frame_{orientation_deg:g}__{profile.name}",
        orientation_deg=float(orientation_deg),
        line_spacing_m=1.0,
        scan_pattern="parallel",
        noise_add=0.0,
        dropout=False,
        shift=None,
        gain=1.0,
    )
    designed = _apply_variation(base_scan, scenario, variation, seed)
    designed.metadata.extra["synthetic_ny"] = scenario.ny
    designed.metadata.extra["synthetic_nx"] = scenario.nx
    designed.metadata.extra["orientation_semantics"] = "scan-frame"
    return perturb_scan(designed, profile, seed=seed + 7919)


def _analyze_pair(reference: ScanObservation, other: ScanObservation, *, resolution: int) -> dict:
    al = align_grids(
        reference.anomaly.zscore,
        other.anomaly.zscore,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=reference.scan.metadata.orientation_deg,
        orientation_b_deg=other.scan.metadata.orientation_deg,
    )
    allowed = _expected_family(
        (
            float(other.scan.metadata.orientation_deg or 0.0)
            - float(reference.scan.metadata.orientation_deg or 0.0)
        ),
    )
    flags = _failure_flags(al)
    transform_family_match = al.transform_name in allowed
    if not transform_family_match:
        flags.append("transform_family_mismatch")
    return {
        "transform": al.transform_name,
        "shift_dy": int(al.shift_dy),
        "shift_dx": int(al.shift_dx),
        "correlation": float(al.correlation),
        "multiscale_correlation": float(al.multiscale_correlation),
        "overlap_fraction": float(al.overlap_fraction),
        "ambiguity_margin": float(al.ambiguity_margin),
        "registration_evidence": float(al.registration_evidence),
        "status": al.status,
        "severity": _severity(al, flags),
        "failure_flags": sorted(set(flags)),
        "candidate_count": int(al.candidate_count),
        "expected_transform_family": sorted(allowed),
        "transform_family_match": bool(transform_family_match),
    }


def run_registration_failure_analysis(
    out_dir: str | Path,
    *,
    count_per_family: int = 3,
    seed: int = 7575,
    resolution: int = 32,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = _profiles075()
    rows: list[dict] = []
    alignments: list[dict] = []

    for family in FAMILIES:
        for i in range(int(count_per_family)):
            site_index = len(rows)
            scenario = _scenario(family, site_index, seed)
            base_scan, truth = generate_scan(scenario)
            reference_scan = _build_semantic_scan(
                base_scan, scenario, 0.0, profiles[0], seed + site_index * 1000
            )
            ref_result = analyze(
                reference_scan,
                out_dir / "sites" / scenario.name / "reference",
                label="reference",
                config=AnalysisConfig(),
                write_outputs=False,
            )
            reference = ScanObservation(
                "reference",
                reference_scan,
                ref_result.grid,
                ref_result.anomaly,
                detect_artifacts(ref_result.grid, ref_result.anomaly),
                ref_result.candidates,
            )

            site_rows = []
            for p_idx, profile in enumerate(profiles):
                for orientation_deg in (0.0, 90.0):
                    label = f"{orientation_deg:g}deg__{profile.name}"
                    scan = _build_semantic_scan(
                        base_scan,
                        scenario,
                        orientation_deg,
                        profile,
                        seed + site_index * 1000 + p_idx * 101 + int(orientation_deg),
                    )
                    result = analyze(
                        scan,
                        out_dir / "sites" / scenario.name / label,
                        label=label,
                        config=AnalysisConfig(),
                        write_outputs=False,
                    )
                    analysis_anomaly = _physical_rotate_anomaly(result.anomaly, orientation_deg)
                    obs = ScanObservation(
                        label,
                        scan,
                        result.grid,
                        analysis_anomaly,
                        detect_artifacts(result.grid, analysis_anomaly),
                        result.candidates,
                    )
                    detail = _analyze_pair(reference, obs, resolution=resolution)
                    ev = evaluate_case(
                        result.candidates,
                        truth,
                        split="stress",
                        case_id=scenario.name,
                        family=family,
                    )
                    detail.update({
                        "site_id": scenario.name,
                        "family": family,
                        "orientation_deg": orientation_deg,
                        "profile": profile.name,
                        "expected_orientation_semantics": "scan-frame",
                        "single_scan_recall": float(ev.recall),
                        "single_scan_precision": float(ev.precision),
                    })
                    alignments.append(detail)
                    site_rows.append(detail)
            rows.append({"site_id": scenario.name, "family": family, "alignments": site_rows})

    def mean(key: str, values: Iterable[dict]) -> float:
        return _safe_mean([float(v.get(key, np.nan)) for v in values])

    failure_counts: dict[str, int] = {}
    for row in alignments:
        for flag in row["failure_flags"]:
            if flag != "none":
                failure_counts[flag] = failure_counts.get(flag, 0) + 1

    by_profile: dict[str, dict] = {}
    for profile in [p.name for p in profiles]:
        vals = [r for r in alignments if r["profile"] == profile]
        by_profile[profile] = {
            "alignments": len(vals),
            "strong_rate": round(sum(r["status"] == "strong" for r in vals) / max(len(vals), 1), 4),
            "mean_evidence": round(mean("registration_evidence", vals), 4),
            "mean_correlation": round(mean("correlation", vals), 4),
            "mean_overlap": round(mean("overlap_fraction", vals), 4),
            "transform_family_match_rate": round(
                sum(r["transform_family_match"] for r in vals) / max(len(vals), 1), 4
            ),
        }

    by_orientation: dict[str, dict] = {}
    for orientation in (0.0, 90.0):
        vals = [r for r in alignments if float(r["orientation_deg"]) == orientation]
        by_orientation[f"{int(orientation)}deg"] = {
            "alignments": len(vals),
            "strong_rate": round(sum(r["status"] == "strong" for r in vals) / max(len(vals), 1), 4),
            "mean_evidence": round(mean("registration_evidence", vals), 4),
            "mean_correlation": round(mean("correlation", vals), 4),
            "mean_overlap": round(mean("overlap_fraction", vals), 4),
            "transform_family_match_rate": round(
                sum(r["transform_family_match"] for r in vals) / max(len(vals), 1), 4
            ),
        }

    payload = {
        "version": "0.2.75",
        "benchmark": "registration_failure_semantics",
        "semantics": "scan-frame orientation; physical raster rotation applied for non-zero frame orientation",
        "sites": len(rows),
        "alignments": len(alignments),
        "count_per_family": int(count_per_family),
        "seed": int(seed),
        "profiles": [asdict(p) for p in profiles],
        "failure_thresholds": FAILURE_THRESHOLDS,
        "summary": {
            "mean_evidence": round(mean("registration_evidence", alignments), 4),
            "mean_correlation": round(mean("correlation", alignments), 4),
            "mean_overlap": round(mean("overlap_fraction", alignments), 4),
            "strong_rate": round(
                sum(r["status"] == "strong" for r in alignments) / max(len(alignments), 1), 4
            ),
            "transform_family_match_rate": round(
                sum(r["transform_family_match"] for r in alignments) / max(len(alignments), 1), 4
            ),
            "failure_counts": failure_counts,
        },
        "by_profile": by_profile,
        "by_orientation": by_orientation,
        "alignment_rows": alignments,
        "decision": "diagnostic_only_no_production_registration_change",
        "field_data_status": "No independently verified field ground truth is available; synthetic testing only.",
    }
    (out_dir / "registration_failure_semantics.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.75 — Registration Failure Analysis",
        "",
        "> Diagnostic-only. Production registration is unchanged.",
        "> Orientation semantics follow the v0.2.74 frame contract: non-zero scan-frame orientation is paired with a physical raster rotation in the synthetic benchmark.",
        "",
        f"Sites: **{payload['sites']}**  ",
        f"Alignments: **{payload['alignments']}**  ",
        f"Seed: **{seed}**",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Mean registration evidence | {payload['summary']['mean_evidence']:.3f} |",
        f"| Mean correlation | {payload['summary']['mean_correlation']:.3f} |",
        f"| Mean overlap | {payload['summary']['mean_overlap']:.3f} |",
        f"| Strong | {payload['summary']['strong_rate']:.1%} |",
        f"| Transform-family match | {payload['summary']['transform_family_match_rate']:.1%} |",
        "",
        "## Failure flags",
        "",
    ]
    for reason, count in sorted(failure_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{reason}`: {count}")
    lines += [
        "",
        "## By profile",
        "",
        "| Profile | Strong | Mean evidence | Mean correlation | Mean overlap | Family match |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, m in by_profile.items():
        lines.append(
            f"| {name} | {m['strong_rate']:.1%} | {m['mean_evidence']:.3f} | {m['mean_correlation']:.3f} | {m['mean_overlap']:.3f} | {m['transform_family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## By orientation",
        "",
        "| Orientation | Strong | Mean evidence | Mean correlation | Mean overlap | Family match |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, m in by_orientation.items():
        lines.append(
            f"| {name} | {m['strong_rate']:.1%} | {m['mean_evidence']:.3f} | {m['mean_correlation']:.3f} | {m['mean_overlap']:.3f} | {m['transform_family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "Failure flags are diagnostic descriptions of registration metrics, not causal proof. The semantics-aware generator removes the previously identified benchmark ambiguity around orientation metadata. Any future registration recovery should be evaluated independently on held-out synthetic generators and should preserve the existing detector/fusion gates.",
        "",
        "## Validation boundary",
        "",
        "These are synthetic software-validation results only. No independently verified field ground-truth dataset is available.",
        "",
    ]
    (out_dir / "registration_failure_semantics.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

"""v0.2.76 controlled registration-recovery experiments.

Diagnostic-only. Production registration is unchanged.
Compares the current aligner with two conservative recovery ideas:
- winsorized correlation: clip each overlap vector to robust percentile bounds
- relaxed-overlap search: permit lower minimum overlap but never change the
  selected transform unless it scores better under the same search contract

The goal is to identify recoverable failure modes before any production change.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import (
    AlignmentResult,
    _multiscale_maps,
    _safe_correlation,
    _shift_with_mask,
    align_grids,
)
from groundscan.validation.synthetic_core.core import generate_scan
from groundscan_research.registration_failure_semantics import (
    FAMILIES,
    _build_semantic_scan,
    _expected_family,
    _failure_flags,
    _profiles075,
    _severity,
)


def _winsorize_pair(
    a: np.ndarray, b: np.ndarray, lower: float = 0.05, upper: float = 0.95
) -> tuple[np.ndarray, np.ndarray]:
    if a.size < 8 or b.size < 8:
        return a, b

    def clip(v: np.ndarray) -> np.ndarray:
        lo, hi = np.nanpercentile(v, [lower * 100.0, upper * 100.0])
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            return v
        return np.clip(v, lo, hi)

    return clip(a), clip(b)


def _winsorized_multiscale(a_maps, b_maps, valid: np.ndarray) -> float:
    if int(valid.sum()) < 12:
        return 0.0
    scores = []
    for aa, bb in zip(a_maps, b_maps):
        av, bv = _winsorize_pair(aa[valid], bb[valid])
        scores.append(max(0.0, _safe_correlation(av, bv)))
    return float(np.mean(scores)) if scores else 0.0


def _align_custom(
    zscore_a: np.ndarray,
    zscore_b: np.ndarray,
    *,
    resolution: int,
    max_shift: int,
    min_overlap_fraction: float,
    robust: bool,
) -> AlignmentResult:
    # Reproduce the production search space exactly; only the scoring statistic differs.
    from groundscan.site.registration import _resample_to

    a, a_mask = _resample_to(zscore_a, (resolution, resolution))
    b_base, b_mask_base = _resample_to(zscore_b, (resolution, resolution))
    min_overlap_cells = int(min_overlap_fraction * resolution * resolution)
    transforms = []
    orientation_pairs = []
    # Geometry is unknown here; the audit intentionally searches all production transforms.
    from groundscan.site.registration import _TRANSFORMS

    transforms = _TRANSFORMS
    a_maps = _multiscale_maps(a)
    b_maps_base = _multiscale_maps(b_base)
    scored = []
    for name, transform in transforms:
        b_t = transform(b_base)
        mask_t = transform(b_mask_base)
        b_maps_t = [transform(m) for m in b_maps_base]
        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                b_s, mask_s = _shift_with_mask(b_t, mask_t, dy, dx)
                valid = a_mask & mask_s & np.isfinite(a) & np.isfinite(b_s)
                if int(valid.sum()) < min_overlap_cells:
                    continue
                av, bv = a[valid], b_s[valid]
                if robust:
                    av, bv = _winsorize_pair(av, bv)
                    correlation = _safe_correlation(av, bv)
                    shifted_scale_maps = [
                        _shift_with_mask(m, np.isfinite(m), dy, dx)[0] for m in b_maps_t
                    ]
                    multiscale = _winsorized_multiscale(a_maps, shifted_scale_maps, valid)
                else:
                    correlation = _safe_correlation(av, bv)
                    shifted_scale_maps = [
                        _shift_with_mask(m, np.isfinite(m), dy, dx)[0] for m in b_maps_t
                    ]
                    vals = []
                    for aa, bb in zip(a_maps, shifted_scale_maps):
                        vals.append(max(0.0, _safe_correlation(aa[valid], bb[valid])))
                    multiscale = float(np.mean(vals)) if vals else 0.0
                score = 0.55 * correlation + 0.45 * multiscale
                scored.append((
                    score,
                    correlation,
                    multiscale,
                    name,
                    dy,
                    dx,
                    float(valid.mean()),
                    b_s,
                    mask_s,
                ))
    if not scored:
        return align_grids(
            zscore_a,
            zscore_b,
            resolution=resolution,
            max_shift=max_shift,
            min_overlap_fraction=min_overlap_fraction,
        )
    scored.sort(key=lambda row: row[0], reverse=True)
    best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else best[0]
    return AlignmentResult(
        transform_name=best[3],
        shift_dy=best[4],
        shift_dx=best[5],
        correlation=float(best[1]),
        overlap_fraction=float(best[6]),
        b_resampled=best[7],
        b_valid=best[8],
        second_best_correlation=float(second_score),
        ambiguity_margin=float(best[0] - second_score),
        multiscale_correlation=float(best[2]),
        candidate_count=len(scored),
    )


def _analyze_pair(
    reference: ScanObservation, other: ScanObservation, *, resolution: int, mode: str
) -> dict:
    if mode == "baseline":
        al = align_grids(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            resolution=resolution,
            max_shift=2,
            orientation_a_deg=reference.scan.metadata.orientation_deg,
            orientation_b_deg=other.scan.metadata.orientation_deg,
        )
    elif mode == "winsorized":
        al = _align_custom(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.50,
            robust=True,
        )
    elif mode == "relaxed-overlap":
        al = align_grids(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.40,
            orientation_a_deg=reference.scan.metadata.orientation_deg,
            orientation_b_deg=other.scan.metadata.orientation_deg,
        )
    elif mode == "winsorized-relaxed":
        al = _align_custom(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.40,
            robust=True,
        )
    else:
        raise ValueError(mode)
    delta = float(other.scan.metadata.orientation_deg or 0.0) - float(
        reference.scan.metadata.orientation_deg or 0.0
    )
    allowed = _expected_family(delta)
    flags = _failure_flags(al)
    family_match = al.transform_name in allowed
    if not family_match:
        flags.append("transform_family_mismatch")
    return {
        "mode": mode,
        "transform": al.transform_name,
        "correlation": float(al.correlation),
        "multiscale_correlation": float(al.multiscale_correlation),
        "overlap_fraction": float(al.overlap_fraction),
        "ambiguity_margin": float(al.ambiguity_margin),
        "registration_evidence": float(al.registration_evidence),
        "status": al.status,
        "severity": _severity(al, flags),
        "failure_flags": sorted(set(flags)),
        "transform_family_match": bool(family_match),
    }


def run_registration_recovery_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 1,
    seed: int = 7676,
    resolution: int = 16,
    profile_names: tuple[str, ...] = ("partial_coverage", "outliers", "compound"),
    family_names: tuple[str, ...] = ("single_compact", "overlapping_multi", "void_plus_geology"),
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = tuple(p for p in _profiles075() if p.name in set(profile_names))
    families = tuple(f for f in FAMILIES if f in set(family_names))
    if not families:
        raise ValueError("family_names must select at least one known family")
    if not profiles:
        raise ValueError("profile_names must select at least one known profile")
    modes = ("baseline", "winsorized", "relaxed-overlap", "winsorized-relaxed")
    rows = []
    for family in families:
        for i in range(int(count_per_family)):
            site_index = len(rows)
            scenario = __import__(
                "groundscan.validation.synthetic_core.acquisition_stress", fromlist=["_scenario"]
            )._scenario(family, site_index, seed)
            base_scan, truth = generate_scan(scenario)
            ref_scan = _build_semantic_scan(
                base_scan, scenario, 0.0, profiles[0], seed + site_index * 1000
            )
            ref_result = analyze(
                ref_scan,
                out_dir / "sites" / scenario.name / "reference",
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
                    from groundscan_research.registration_failure_semantics import (
                        _physical_rotate_anomaly,
                    )

                    anomaly = _physical_rotate_anomaly(result.anomaly, orientation_deg)
                    obs = ScanObservation(
                        label,
                        scan,
                        result.grid,
                        anomaly,
                        detect_artifacts(result.grid, anomaly),
                        result.candidates,
                    )
                    for mode in modes:
                        d = _analyze_pair(reference, obs, resolution=resolution, mode=mode)
                        d.update({
                            "site_id": scenario.name,
                            "family": family,
                            "profile": profile.name,
                            "orientation_deg": orientation_deg,
                        })
                        rows.append(d)

    def mean(vals):
        vals = [float(v) for v in vals if np.isfinite(float(v))]
        return float(np.mean(vals)) if vals else 0.0

    summary = {}
    for mode in modes:
        vals = [r for r in rows if r["mode"] == mode]
        summary[mode] = {
            "alignments": len(vals),
            "mean_evidence": round(mean([r["registration_evidence"] for r in vals]), 4),
            "mean_correlation": round(mean([r["correlation"] for r in vals]), 4),
            "mean_overlap": round(mean([r["overlap_fraction"] for r in vals]), 4),
            "strong_rate": round(sum(r["status"] == "strong" for r in vals) / max(len(vals), 1), 4),
            "family_match_rate": round(
                sum(r["transform_family_match"] for r in vals) / max(len(vals), 1), 4
            ),
        }
    by_profile = {}
    for profile in [p.name for p in profiles]:
        by_profile[profile] = {}
        for mode in modes:
            vals = [r for r in rows if r["profile"] == profile and r["mode"] == mode]
            by_profile[profile][mode] = {
                "mean_evidence": round(mean([r["registration_evidence"] for r in vals]), 4),
                "mean_correlation": round(mean([r["correlation"] for r in vals]), 4),
                "mean_overlap": round(mean([r["overlap_fraction"] for r in vals]), 4),
                "strong_rate": round(
                    sum(r["status"] == "strong" for r in vals) / max(len(vals), 1), 4
                ),
            }
    payload = {
        "version": "0.2.76",
        "benchmark": "registration_recovery_experiments",
        "seed": int(seed),
        "sites": len(families) * int(count_per_family),
        "alignments": len(rows),
        "count_per_family": int(count_per_family),
        "modes": list(modes),
        "profiles_selected": list(profile_names),
        "families_selected": list(family_names),
        "summary": summary,
        "by_profile": by_profile,
        "decision": "diagnostic_only_no_production_registration_change",
        "field_data_status": "No independently verified field ground truth is available; synthetic testing only.",
    }
    (out_dir / "registration_recovery_experiments.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.76 — Registration Recovery Audit",
        "",
        "> Diagnostic-only. Production registration is unchanged.",
        "",
        f"Sites: **{payload['sites']}**  ",
        f"Alignments: **{payload['alignments']}**  ",
        f"Seed: **{seed}**",
        "",
        "## Aggregate",
        "",
        "| Mode | Mean evidence | Mean correlation | Mean overlap | Strong | Family match |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, m in summary.items():
        lines.append(
            f"| {mode} | {m['mean_evidence']:.3f} | {m['mean_correlation']:.3f} | {m['mean_overlap']:.3f} | {m['strong_rate']:.1%} | {m['family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## By profile",
        "",
        "| Profile | Baseline evidence | Winsorized | Relaxed overlap | Winsorized + relaxed |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile, modes_data in by_profile.items():
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                profile,
                f"{modes_data['baseline']['mean_evidence']:.3f}",
                f"{modes_data['winsorized']['mean_evidence']:.3f}",
                f"{modes_data['relaxed-overlap']['mean_evidence']:.3f}",
                f"{modes_data['winsorized-relaxed']['mean_evidence']:.3f}",
            )
        )
    lines += [
        "",
        "## Decision",
        "",
        "No recovery policy is enabled in production. Any future registration change must be validated on independent synthetic generators/holdouts and preserve the existing detector and fusion gates.",
        "",
        "## Validation boundary",
        "",
        "Synthetic software-validation results only; no independently verified field ground-truth dataset is available.",
        "",
    ]
    (out_dir / "registration_recovery_experiments.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return payload

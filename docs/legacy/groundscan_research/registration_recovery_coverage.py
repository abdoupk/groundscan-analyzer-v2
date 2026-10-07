"""v0.2.78 controlled registration recovery experiments.

Diagnostic-only. Production registration is unchanged.

This module tests a coverage-aware + robust recovery search after the v0.2.75
semantics contract and the v0.2.77 compound-failure atlas:
- keep the production orientation transform constraints;
- permit lower valid overlap only for a recovery search;
- use winsorized overlap statistics for outlier resistance;
- report recovery separately from production registration status.

No production gate is changed by this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.api import AnalysisConfig, analyze
from groundscan.core.artifact import detect_artifacts
from groundscan.site.analyze_site import ScanObservation
from groundscan.site.registration import (
    _TRANSFORMS,
    AlignmentResult,
    _multiscale_maps,
    _resample_to,
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

RECOVERY_CORR_MIN = 0.45
RECOVERY_MULTI_MIN = 0.40
RECOVERY_MARGIN_MIN = 0.02


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


def _orientation_allowed(a_deg: float | None, b_deg: float | None) -> list[tuple[str, object]]:
    if a_deg is None or b_deg is None:
        return list(_TRANSFORMS)
    delta = (float(b_deg) - float(a_deg)) % 180.0
    if min(delta, 180.0 - delta) < 22.5:
        allowed = {"rot0", "rot180"}
    elif abs(delta - 90.0) < 22.5:
        allowed = {"rot90", "rot270"}
    else:
        allowed = {"rot0", "rot90", "rot180", "rot270"}
    return [(n, f) for n, f in _TRANSFORMS if n in allowed]


def _align_recovery(
    zscore_a: np.ndarray,
    zscore_b: np.ndarray,
    *,
    orientation_a_deg: float | None,
    orientation_b_deg: float | None,
    resolution: int,
    max_shift: int,
    min_overlap_fraction: float,
    robust: bool,
) -> AlignmentResult:
    common = (resolution, resolution)
    a, a_mask = _resample_to(zscore_a, common)
    b_base, b_mask_base = _resample_to(zscore_b, common)
    min_cells = int(min_overlap_fraction * resolution * resolution)
    a_maps = _multiscale_maps(a)
    b_maps_base = _multiscale_maps(b_base)
    transforms = _orientation_allowed(orientation_a_deg, orientation_b_deg)
    scored = []
    for name, transform in transforms:
        bt = transform(b_base)
        mt = transform(b_mask_base)
        bmaps = [transform(m) for m in b_maps_base]
        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                bs, ms = _shift_with_mask(bt, mt, dy, dx)
                valid = a_mask & ms & np.isfinite(a) & np.isfinite(bs)
                if int(valid.sum()) < min_cells:
                    continue
                av, bv = a[valid], bs[valid]
                if robust:
                    av_score, bv_score = _winsorize_pair(av, bv)
                    corr = _safe_correlation(av_score, bv_score)
                else:
                    corr = _safe_correlation(av, bv)
                shifted_maps = [_shift_with_mask(m, np.isfinite(m), dy, dx)[0] for m in bmaps]
                ms_scores = []
                for aa, bb in zip(a_maps, shifted_maps):
                    va, vb = aa[valid], bb[valid]
                    if robust:
                        va, vb = _winsorize_pair(va, vb)
                    ms_scores.append(max(0.0, _safe_correlation(va, vb)))
                multi = float(np.mean(ms_scores)) if ms_scores else 0.0
                score = 0.55 * corr + 0.45 * multi
                scored.append((score, corr, multi, name, dy, dx, float(valid.mean()), bs, ms))
    if not scored:
        return align_grids(
            zscore_a,
            zscore_b,
            resolution=resolution,
            max_shift=max_shift,
            min_overlap_fraction=min_overlap_fraction,
            orientation_a_deg=orientation_a_deg,
            orientation_b_deg=orientation_b_deg,
        )
    scored.sort(key=lambda x: (-x[0], x[3], x[4], x[5]))
    best = scored[0]
    second = scored[1] if len(scored) > 1 else best
    margin = float(best[0] - second[0])
    return AlignmentResult(
        transform_name=best[3],
        shift_dy=best[4],
        shift_dx=best[5],
        correlation=float(best[1]),
        overlap_fraction=float(best[6]),
        b_resampled=best[7],
        b_valid=best[8],
        second_best_correlation=float(second[0]),
        ambiguity_margin=margin,
        multiscale_correlation=float(best[2]),
        candidate_count=len(scored),
    )


def _pair_result(
    reference: ScanObservation, other: ScanObservation, *, mode: str, resolution: int
) -> dict:
    oa = reference.scan.metadata.orientation_deg
    ob = other.scan.metadata.orientation_deg
    if mode == "production":
        al = align_grids(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            resolution=resolution,
            max_shift=2,
            orientation_a_deg=oa,
            orientation_b_deg=ob,
        )
    elif mode == "coverage-aware":
        al = _align_recovery(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            orientation_a_deg=oa,
            orientation_b_deg=ob,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.30,
            robust=False,
        )
    elif mode == "robust":
        al = _align_recovery(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            orientation_a_deg=oa,
            orientation_b_deg=ob,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.50,
            robust=True,
        )
    elif mode == "hybrid":
        al = _align_recovery(
            reference.anomaly.zscore,
            other.anomaly.zscore,
            orientation_a_deg=oa,
            orientation_b_deg=ob,
            resolution=resolution,
            max_shift=2,
            min_overlap_fraction=0.30,
            robust=True,
        )
    else:
        raise ValueError(mode)
    allowed = _expected_family(float(ob or 0.0) - float(oa or 0.0))
    family_match = al.transform_name in allowed
    flags = _failure_flags(al)
    if not family_match:
        flags.append("transform_family_mismatch")
    recovery_eligible = (
        family_match
        and al.correlation >= RECOVERY_CORR_MIN
        and al.multiscale_correlation >= RECOVERY_MULTI_MIN
        and al.ambiguity_margin >= RECOVERY_MARGIN_MIN
    )
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
        "family_match": family_match,
        "recovery_eligible": recovery_eligible,
        "recovery_label": "coverage-recovered" if recovery_eligible else "not-recovered",
        "failure_flags": sorted(set(flags)),
    }


def run_registration_recovery_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 2,
    seed: int = 7878,
    resolution: int = 24,
    profile_names: tuple[str, ...] = ("partial_coverage", "outliers", "compound"),
    family_names: tuple[str, ...] = ("single_compact", "overlapping_multi", "void_plus_geology"),
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = tuple(p for p in _profiles075() if p.name in set(profile_names))
    families = tuple(f for f in FAMILIES if f in set(family_names))
    modes = ("production", "coverage-aware", "robust", "hybrid")
    rows: list[dict] = []
    site_rows: list[dict] = []
    scenario_factory = __import__(
        "groundscan.validation.synthetic_core.acquisition_stress", fromlist=["_scenario"]
    )._scenario
    for family in families:
        for i in range(int(count_per_family)):
            site_index = len(site_rows)
            scenario = scenario_factory(family, site_index, seed)
            base_scan, _truth = generate_scan(scenario)
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
                for orientation in (0.0, 90.0):
                    label = f"{orientation:g}deg__{profile.name}"
                    s = _build_semantic_scan(
                        base_scan,
                        scenario,
                        orientation,
                        profile,
                        seed + site_index * 1000 + p_idx * 101 + int(orientation),
                    )
                    rr = analyze(
                        s,
                        out_dir / "sites" / scenario.name / label,
                        label=label,
                        config=AnalysisConfig(),
                        write_outputs=False,
                    )
                    from groundscan_research.registration_failure_semantics import (
                        _physical_rotate_anomaly,
                    )

                    an = _physical_rotate_anomaly(rr.anomaly, orientation)
                    other = ScanObservation(
                        label, s, rr.grid, an, detect_artifacts(rr.grid, an), rr.candidates
                    )
                    for mode in modes:
                        d = _pair_result(reference, other, mode=mode, resolution=resolution)
                        d.update({
                            "site_id": scenario.name,
                            "family": family,
                            "profile": profile.name,
                            "orientation_deg": orientation,
                        })
                        rows.append(d)
            site_rows.append({"site_id": scenario.name, "family": family})

    def _mean(vals):
        vals = [float(v) for v in vals if np.isfinite(float(v))]
        return float(np.mean(vals)) if vals else 0.0

    summary = {}
    for mode in modes:
        vals = [r for r in rows if r["mode"] == mode]
        summary[mode] = {
            "alignments": len(vals),
            "mean_evidence": round(_mean([r["registration_evidence"] for r in vals]), 4),
            "mean_correlation": round(_mean([r["correlation"] for r in vals]), 4),
            "mean_overlap": round(_mean([r["overlap_fraction"] for r in vals]), 4),
            "family_match_rate": round(np.mean([r["family_match"] for r in vals]), 4)
            if vals
            else 0.0,
            "recovery_eligible_rate": round(np.mean([r["recovery_eligible"] for r in vals]), 4)
            if vals
            else 0.0,
        }

    by_profile = {}
    for profile in profile_names:
        by_profile[profile] = {}
        for mode in modes:
            vals = [r for r in rows if r["profile"] == profile and r["mode"] == mode]
            by_profile[profile][mode] = {
                "alignments": len(vals),
                "mean_evidence": round(_mean([r["registration_evidence"] for r in vals]), 4),
                "family_match_rate": round(np.mean([r["family_match"] for r in vals]), 4)
                if vals
                else 0.0,
                "recovery_eligible_rate": round(np.mean([r["recovery_eligible"] for r in vals]), 4)
                if vals
                else 0.0,
            }

    payload = {
        "version": "0.2.78",
        "benchmark": "registration_recovery_coverage",
        "seed": int(seed),
        "sites": len(site_rows),
        "alignments": len(rows),
        "profiles": list(profile_names),
        "families": list(family_names),
        "recovery_thresholds": {
            "correlation": RECOVERY_CORR_MIN,
            "multiscale": RECOVERY_MULTI_MIN,
            "margin": RECOVERY_MARGIN_MIN,
        },
        "summary": summary,
        "by_profile": by_profile,
        "rows": rows,
        "decision": "diagnostic_only_no_production_registration_change",
        "field_data_status": "No independently verified field ground truth is available; synthetic testing only.",
    }
    (out_dir / "registration_recovery_coverage.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.78 — Controlled Registration Recovery",
        "",
        "> Diagnostic-only. Production registration is unchanged.",
        "",
        f"Sites: **{payload['sites']}**; alignments: **{payload['alignments']}**; seed: **{seed}**.",
        "",
        "## Recovery policy",
        "",
        "- Production orientation constraints are preserved.",
        "- Recovery may use 30% minimum valid overlap; this does not upgrade production status to `strong`.",
        "- Robust mode winsorizes overlap statistics for outlier resistance.",
        f"- Recovery eligibility requires family match + correlation >= {RECOVERY_CORR_MIN:.2f} + multiscale >= {RECOVERY_MULTI_MIN:.2f} + ambiguity margin >= {RECOVERY_MARGIN_MIN:.2f}.",
        "",
        "## Aggregate",
        "",
        "| Mode | Mean evidence | Mean correlation | Mean overlap | Family match | Recovery eligible |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, m in summary.items():
        lines.append(
            f"| {mode} | {m['mean_evidence']:.3f} | {m['mean_correlation']:.3f} | {m['mean_overlap']:.3f} | {m['family_match_rate']:.1%} | {m['recovery_eligible_rate']:.1%} |"
        )
    lines += [
        "",
        "## By profile",
        "",
        "| Profile | Mode | Mean evidence | Family match | Recovery eligible |",
        "|---|---|---:|---:|---:|",
    ]
    for profile, modes_data in by_profile.items():
        for mode, m in modes_data.items():
            lines.append(
                f"| {profile} | {mode} | {m['mean_evidence']:.3f} | {m['family_match_rate']:.1%} | {m['recovery_eligible_rate']:.1%} |"
            )
    lines += [
        "",
        "## Decision",
        "",
        "The recovery search remains diagnostic-only. It is not wired into production registration, detector scoring, fusion, pruning, or candidate confidence.",
        "",
        "## Validation boundary",
        "",
        "These are synthetic software-validation results only; no independently verified field ground truth is available.",
        "",
    ]
    (out_dir / "registration_recovery_coverage.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

"""v0.2.72 registration robustness audit.

Compares the production registration search with conservative diagnostic scoring
alternatives under synthetic acquisition stress. No production registration,
detector, fusion, pruning, or scoring policy is changed by this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from groundscan.api import AnalysisConfig, analyze
from groundscan.site.registration import (
    _TRANSFORMS,
    AlignmentResult,
    _multiscale_maps,
    _resample_to,
    _safe_correlation,
    _shift_array_integer,
    _shift_with_mask,
    align_grids,
)
from groundscan.validation.synthetic_core.acquisition_stress import (
    _build_scan,
    _designs,
    _profiles,
    _safe_mean,
    _scenario,
)
from groundscan.validation.synthetic_core.core import generate_scan

FAMILIES = (
    "single_compact",
    "single_cavity",
    "single_tunnel",
    "close_multi",
    "overlapping_multi",
    "void_plus_geology",
)


def _masked_gaussian(array: np.ndarray, sigma: float) -> np.ndarray:
    valid = np.isfinite(array)
    values = np.nan_to_num(array, nan=0.0)
    weighted = ndimage.gaussian_filter(values * valid, sigma=sigma)
    weights = ndimage.gaussian_filter(valid.astype(float), sigma=sigma)
    return np.divide(weighted, np.maximum(weights, 1e-9))


def _alt_alignment(
    a_raw: np.ndarray,
    b_raw: np.ndarray,
    *,
    resolution: int,
    mode: str,
    orientation_a: float,
    orientation_b: float,
    max_shift: int = 2,
) -> AlignmentResult:
    a, am = _resample_to(a_raw, (resolution, resolution))
    b, bm = _resample_to(b_raw, (resolution, resolution))
    min_overlap_cells = int(0.5 * resolution * resolution)
    a_maps = _multiscale_maps(a)
    if mode == "masked-multiscale":
        b_maps_base = [np.nan_to_num(b, nan=0.0)] + [
            np.where(np.isfinite(b), _masked_gaussian(b, sigma), 0.0) for sigma in (1.0, 2.0, 4.0)
        ]
        a_maps = [np.nan_to_num(a, nan=0.0)] + [
            np.where(np.isfinite(a), _masked_gaussian(a, sigma), 0.0) for sigma in (1.0, 2.0, 4.0)
        ]
    else:
        b_maps_base = _multiscale_maps(b)
    delta = (float(orientation_b) - float(orientation_a)) % 180.0
    if min(delta, 180.0 - delta) < 22.5:
        allowed = {"rot0", "rot180"}
    elif abs(delta - 90.0) < 22.5:
        allowed = {"rot90", "rot270"}
    else:
        allowed = {"rot0", "rot90", "rot180", "rot270"}
    transforms = [(n, f) for n, f in _TRANSFORMS if n in allowed]
    scored = []
    for name, transform in transforms:
        bt = transform(b)
        maskt = transform(bm)
        bmaps = [transform(m) for m in b_maps_base]
        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                bs, ms = _shift_with_mask(bt, maskt, dy, dx)
                valid = am & ms & np.isfinite(a) & np.isfinite(bs)
                if int(valid.sum()) < min_overlap_cells:
                    continue
                av, bv = a[valid], bs[valid]
                corr = _safe_correlation(av, bv)
                mag = _safe_correlation(np.abs(av), np.abs(bv))
                shifted = [_shift_array_integer(m, dy, dx) for m in bmaps]
                values = [
                    max(0.0, _safe_correlation(aa, bb))
                    for aa, bb in zip([m[valid] for m in a_maps], [m[valid] for m in shifted])
                ]
                multi = float(np.mean(values)) if values else 0.0
                overlap = float(valid.sum()) / float(resolution * resolution)
                if mode == "magnitude-assisted":
                    score = 0.40 * corr + 0.25 * mag + 0.35 * multi
                else:
                    score = 0.55 * corr + 0.45 * multi
                scored.append((score, corr, multi, name, dy, dx, overlap, bs, ms))
    if not scored:
        bs, ms = _shift_with_mask(b, bm, 0, 0)
        corr = _safe_correlation(a[am], bs[am & ms])
        return AlignmentResult("rot0", 0, 0, corr, float(np.mean(am & ms)), bs, ms)
    scored.sort(key=lambda row: row[0], reverse=True)
    best = scored[0]
    second = scored[1][0] if len(scored) > 1 else best[0]
    return AlignmentResult(
        best[3],
        best[4],
        best[5],
        float(best[1]),
        float(best[6]),
        best[7],
        best[8],
        float(second),
        float(best[0] - second),
        float(best[2]),
        len(scored),
    )


def run_registration_robustness_audit(
    out_dir: str | Path, *, count_per_family: int = 4, seed: int = 7272, resolution: int = 32
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for family in FAMILIES:
        for i in range(count_per_family):
            site_index = len(rows)
            scenario = _scenario(family, site_index, seed)
            base, _ = generate_scan(scenario)
            scan_pairs = []
            for d_idx, d in enumerate(_designs()):
                p = _profiles()[(d_idx + i) % len(_profiles())]
                scan_pairs.append(
                    _build_scan(base, scenario, d, p, seed + site_index * 10000 + d_idx * 101 + i)
                )
            analyses = []
            for j, scan in enumerate(scan_pairs):
                analyses.append(
                    analyze(
                        scan,
                        out_dir / f"site_{site_index:03d}" / f"scan_{j}",
                        config=AnalysisConfig(),
                        write_outputs=False,
                    )
                )
            ref = analyses[0]
            scores = {"baseline": [], "magnitude-assisted": [], "masked-multiscale": []}
            for j, ob in enumerate(analyses[1:], 1):
                orient_a = scan_pairs[0].metadata.orientation_deg
                orient_b = scan_pairs[j].metadata.orientation_deg
                al = align_grids(
                    ref.anomaly.zscore,
                    ob.anomaly.zscore,
                    resolution=resolution,
                    max_shift=2,
                    orientation_a_deg=orient_a,
                    orientation_b_deg=orient_b,
                )
                scores["baseline"].append(al)
                scores["magnitude-assisted"].append(
                    _alt_alignment(
                        ref.anomaly.zscore,
                        ob.anomaly.zscore,
                        resolution=resolution,
                        mode="magnitude-assisted",
                        orientation_a=orient_a,
                        orientation_b=orient_b,
                    )
                )
                scores["masked-multiscale"].append(
                    _alt_alignment(
                        ref.anomaly.zscore,
                        ob.anomaly.zscore,
                        resolution=resolution,
                        mode="masked-multiscale",
                        orientation_a=orient_a,
                        orientation_b=orient_b,
                    )
                )
            for mode, als in scores.items():
                rows.append({
                    "site_id": scenario.name,
                    "family": family,
                    "mode": mode,
                    "strong_rate": sum(a.status == "strong" for a in als) / max(len(als), 1),
                    "mean_evidence": _safe_mean([a.registration_evidence for a in als]),
                    "mean_overlap": _safe_mean([a.overlap_fraction for a in als]),
                    "mean_correlation": _safe_mean([a.correlation for a in als]),
                    "mean_multiscale": _safe_mean([a.multiscale_correlation for a in als]),
                })
    summary = {}
    for mode in ("baseline", "magnitude-assisted", "masked-multiscale"):
        rr = [r for r in rows if r["mode"] == mode]
        summary[mode] = {
            "alignments": len(rr) * 3,
            "mean_evidence": round(_safe_mean([r["mean_evidence"] for r in rr]), 4),
            "strong_rate": round(_safe_mean([r["strong_rate"] for r in rr]), 4),
            "mean_overlap": round(_safe_mean([r["mean_overlap"] for r in rr]), 4),
            "mean_correlation": round(_safe_mean([r["mean_correlation"] for r in rr]), 4),
            "mean_multiscale": round(_safe_mean([r["mean_multiscale"] for r in rr]), 4),
        }
    payload = {
        "version": "0.2.72",
        "benchmark": "registration_robustness_audit",
        "sites": len(set(r["site_id"] for r in rows)),
        "count_per_family": count_per_family,
        "seed": seed,
        "summary": summary,
        "rows": rows,
        "decision": "diagnostic_only_no_production_registration_change",
        "field_data_status": "No independently verified field ground truth is available; this is synthetic software robustness testing only.",
    }
    (out_dir / "registration_robustness.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.72 — Registration Robustness Audit",
        "",
        "> Diagnostic-only. Production registration remains unchanged.",
        "",
        f"Sites: **{payload['sites']}**; seed: **{seed}**.",
        "",
        "| Mode | Mean evidence | Strong rate | Mean overlap | Mean corr | Mean multiscale |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, m in summary.items():
        lines.append(
            f"| {mode} | {m['mean_evidence']:.3f} | {m['strong_rate']:.1%} | {m['mean_overlap']:.3f} | {m['mean_correlation']:.3f} | {m['mean_multiscale']:.3f} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "No alternative was enabled in production. A registration change requires improvement on independent stress sets without regression in hard/frozen benchmarks.",
        "",
        "## Validation boundary",
        "",
        "Synthetic acquisition stress is not field validation and does not establish detection accuracy or material identification.",
        "",
    ]
    (out_dir / "registration_robustness.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

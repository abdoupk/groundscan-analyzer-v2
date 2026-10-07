"""Deterministic synthetic multi-scan benchmark for GroundScan Analyzer.

This benchmark evaluates site-level fusion using repeated scans of the same
synthetic scene with independent noise and controlled acquisition variation.
It is software validation only; it is not a field-accuracy or material
identification benchmark.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ...api import AnalysisConfig, analyze
from ...core.artifact import detect_artifacts
from ...core.classify import apply_local_geology_context
from ...diagnostics.dipole import (
    deblend_spatially_separated_multitarget_pairs,
    merge_dipolar_response_components,
)
from ...gates.quality import assess_candidate_quality
from ...gates.screening import DEFAULT_SCREENING_POLICY, screen_candidates
from ...models import ScanData
from ...site.analyze_site import ScanObservation, fuse_site_candidates
from ...site.consensus import _consensus_maps
from ...site.registration import AlignmentResult, _resample_to, align_grids
from ...site.separation import resolve_dipole_pairs, separate_fused_candidates
from .benchmark_large import evaluate_case
from .core import SyntheticScenario, SyntheticTarget, generate_scan


@dataclass(frozen=True)
class MultiScanSiteSpec:
    site_id: str
    split: str
    family: str
    scenario: SyntheticScenario
    scan_count: int = 3
    dropout_scan: int | None = None
    shift_scan: int | None = None
    rotate_scan: int | None = None
    depth_bias_scan: int | None = None


def _safe_mean(values: Iterable[float]) -> float:
    """Backward-compat alias — canonical impl is groundscan._util.safe_mean."""
    from groundscan._util import safe_mean

    return safe_mean(values, default=float("nan"))


def _ring_median(signal_2d: np.ndarray[Any, Any], row: int, col: int, radius: int) -> float:
    h, w = signal_2d.shape
    r0, r1 = max(0, row - radius - 1), min(h, row + radius + 2)
    c0, c1 = max(0, col - radius - 1), min(w, col + radius + 2)
    patch = signal_2d[r0:r1, c0:c1].copy()
    yy, xx = np.ogrid[: patch.shape[0], : patch.shape[1]]
    cy = row - r0
    cx = col - c0
    dist2 = (yy - cy) ** 2 + (xx - cx) ** 2
    ring = patch[(dist2 >= max(4, radius * radius * 0.55)) & (dist2 <= (radius + 2) ** 2)]
    ring = ring[np.isfinite(ring)]
    if ring.size:
        return float(np.median(ring))
    finite = patch[np.isfinite(patch)]
    return float(np.median(finite)) if finite.size else 150.0


def _clone_with_variation(
    scan: ScanData,
    scenario: SyntheticScenario,
    rng: np.random.Generator,
    *,
    dropout: bool = False,
    shift: tuple[int, int] | None = None,
    rotate: int | None = None,
    depth_bias: float = 0.0,
    gain: float = 1.0,
    noise_add: float = 0.0,
) -> ScanData:
    nx, ny = scenario.nx, scenario.ny
    signal = np.asarray(scan.signal, dtype=float).reshape(ny, nx).copy()
    depth = np.asarray(scan.z, dtype=float).reshape(ny, nx).copy()

    # Preserve the physical baseline while varying gain/noise.
    baseline = 150.0 + scenario.gradient_x * np.tile(np.linspace(0, scenario.width_m, nx), (ny, 1))
    baseline += scenario.gradient_y * np.tile(
        np.linspace(0, scenario.height_m, ny)[:, None], (1, nx)
    )
    signal = baseline + gain * (signal - baseline)
    if noise_add > 0:
        signal += rng.normal(0.0, noise_add, size=signal.shape)

    if dropout and scenario.targets:
        # Remove the strongest local expression around one target. This is a
        # controlled synthetic acquisition dropout, not a physical model.
        target = max(scenario.targets, key=lambda t: abs(t.amplitude))
        col = int(round(target.x / max(scenario.width_m, 1e-9) * (nx - 1)))
        row = int(round(target.y / max(scenario.height_m, 1e-9) * (ny - 1)))
        radius = max(2, int(round(2.0 * max(target.sx, target.sy, 0.8))))
        r0, r1 = max(0, row - radius), min(ny, row + radius + 1)
        c0, c1 = max(0, col - radius), min(nx, col + radius + 1)
        replacement = _ring_median(signal, row, col, radius)
        signal[r0:r1, c0:c1] = replacement + rng.normal(
            0.0, max(0.15, noise_add * 0.5), size=(r1 - r0, c1 - c0)
        )

    if shift is not None:
        dy, dx = shift
        signal = np.roll(signal, shift=(dy, dx), axis=(0, 1))
        depth = np.roll(depth, shift=(dy, dx), axis=(0, 1))

    if rotate is not None:
        k = int((rotate % 360) // 90)
        if k:
            signal = np.rot90(signal, k=k)
            depth = np.rot90(depth, k=k)

    depth = depth + float(depth_bias)
    return ScanData(
        x=np.asarray(scan.x, dtype=float).copy(),
        y=np.asarray(scan.y, dtype=float).copy(),
        z=depth.ravel(),
        signal=signal.ravel(),
        twt_ns=None if scan.twt_ns is None else np.asarray(scan.twt_ns).copy(),
        grid_i=None if scan.grid_i is None else np.asarray(scan.grid_i).copy(),
        grid_j=None if scan.grid_j is None else np.asarray(scan.grid_j).copy(),
        latitude=None if scan.latitude is None else np.asarray(scan.latitude).copy(),
        longitude=None if scan.longitude is None else np.asarray(scan.longitude).copy(),
        coords_are_index_only=scan.coords_are_index_only,
        metadata=scan.metadata,
    )


def _site_specs(count: int = 36, seed: int = 2047) -> list[MultiScanSiteSpec]:
    rng = np.random.default_rng(seed)
    families = [
        "single_compact",
        "single_cavity",
        "single_tunnel",
        "close_multi",
        "overlapping_multi",
        "void_plus_geology",
    ]
    specs: list[MultiScanSiteSpec] = []
    per = count // len(families)
    idx = 0
    for family in families:
        for _ in range(per):
            width, height = 40.0, 30.0
            noise = float(rng.choice([0.6, 1.0, 1.5, 2.0]))
            depth_noise = float(rng.choice([0.04, 0.08, 0.16, 0.25]))
            depth = float(rng.choice([3.0, 4.5, 6.5, 8.5, 10.5]))
            if family == "single_compact":
                targets = (
                    SyntheticTarget(
                        "positive_compact",
                        10 + rng.uniform(-1, 1),
                        13 + rng.uniform(-1, 1),
                        depth=depth,
                        amplitude=float(rng.choice([12, 18, 24])),
                        sx=1.0,
                        sy=1.2,
                    ),
                )
            elif family == "single_cavity":
                targets = (
                    SyntheticTarget(
                        "cavity",
                        24 + rng.uniform(-1.5, 1.5),
                        14 + rng.uniform(-1, 1),
                        depth=depth,
                        amplitude=float(rng.choice([12, 16, 20])),
                        sx=2.3,
                        sy=2.0,
                    ),
                )
            elif family == "single_tunnel":
                targets = (
                    SyntheticTarget(
                        "tunnel",
                        20,
                        15,
                        depth=depth,
                        amplitude=float(rng.choice([10, 14, 18])),
                        sy=0.9,
                        length=float(rng.choice([9, 13, 17])),
                        orientation_deg=float(rng.choice([0, 35, 65, 90, 125, 160])),
                    ),
                )
            elif family == "close_multi":
                x = 13 + rng.uniform(-1, 1)
                y = 14 + rng.uniform(-1, 1)
                targets = (
                    SyntheticTarget(
                        "positive_compact",
                        x,
                        y,
                        depth=3.0 + rng.uniform(0, 2),
                        amplitude=22,
                        sx=1.2,
                        sy=1.1,
                    ),
                    SyntheticTarget(
                        "cavity",
                        x + rng.uniform(3.2, 5.0),
                        y + rng.uniform(-1.5, 1.5),
                        depth=6.0 + rng.uniform(-1, 1),
                        amplitude=17,
                        sx=2.0,
                        sy=1.8,
                    ),
                )
            elif family == "overlapping_multi":
                x = 15 + rng.uniform(-1, 1)
                y = 14 + rng.uniform(-1, 1)
                targets = (
                    SyntheticTarget(
                        "positive_compact",
                        x,
                        y,
                        depth=3.0 + rng.uniform(0, 1.5),
                        amplitude=24,
                        sx=1.6,
                        sy=1.4,
                    ),
                    SyntheticTarget(
                        "cavity",
                        x + rng.uniform(1.5, 3.0),
                        y + rng.uniform(-1.0, 1.0),
                        depth=7.0 + rng.uniform(-0.8, 0.8),
                        amplitude=20,
                        sx=2.4,
                        sy=2.1,
                    ),
                )
            else:
                targets = (
                    SyntheticTarget(
                        "geology",
                        20 + rng.uniform(-2, 2),
                        15 + rng.uniform(-1.5, 1.5),
                        depth=10.0,
                        amplitude=10,
                        sx=7.0,
                        sy=5.5,
                    ),
                    SyntheticTarget(
                        "cavity",
                        29 + rng.uniform(-1, 1),
                        18 + rng.uniform(-1, 1),
                        depth=5.0 + rng.uniform(-0.7, 0.7),
                        amplitude=17,
                        sx=2.5,
                        sy=2.2,
                    ),
                )
            scenario = SyntheticScenario(
                name=f"ms_{idx:03d}_{family}",
                width_m=width,
                height_m=height,
                nx=int(rng.choice([31, 41, 51])),
                ny=int(rng.choice([25, 31])),
                targets=tuple(targets),
                noise_sigma=noise,
                gradient_x=float(rng.uniform(-0.12, 0.12)),
                gradient_y=float(rng.uniform(-0.08, 0.08)),
                depth_noise_sigma=depth_noise,
                seed=seed + idx * 17,
            )
            split = "calibration" if idx % 5 < 3 else "holdout"
            specs.append(
                MultiScanSiteSpec(
                    site_id=scenario.name,
                    split=split,
                    family=family,
                    scenario=scenario,
                    scan_count=3,
                    dropout_scan=2 if idx % 6 == 0 else None,
                    shift_scan=1 if idx % 4 == 0 else None,
                    rotate_scan=2 if idx % 7 == 0 else None,
                    depth_bias_scan=3 if idx % 5 == 0 else None,
                )
            )
            idx += 1
    return specs


def _make_variants(spec: MultiScanSiteSpec) -> tuple[list[tuple[str, ScanData]], dict]:
    base_seed = spec.scenario.seed + 10000
    base_scan, truth = generate_scan(spec.scenario)
    scans: list[tuple[str, ScanData]] = []
    variations = []
    for scan_idx in range(spec.scan_count):
        rng = np.random.default_rng(base_seed + scan_idx * 101)
        dropout = spec.dropout_scan == (scan_idx + 1)
        shift = (1, -1) if spec.shift_scan == (scan_idx + 1) else None
        rotate = 90 if spec.rotate_scan == (scan_idx + 1) else None
        depth_bias = 0.0
        if spec.depth_bias_scan == (scan_idx + 1):
            depth_bias = 0.35
        gain = float(rng.uniform(0.88, 1.12))
        noise_add = float(rng.uniform(0.05, 0.35))
        scan = _clone_with_variation(
            base_scan,
            spec.scenario,
            rng,
            dropout=dropout,
            shift=shift,
            rotate=rotate,
            depth_bias=depth_bias,
            gain=gain,
            noise_add=noise_add,
        )
        scan.metadata.extra = dict(scan.metadata.extra)
        scan.metadata.extra.update({
            "orientation_deg": float(rotate or 0.0),
            "line_spacing_m": float(1.0 + 0.05 * scan_idx),
            "scan_pattern": "parallel" if scan_idx % 2 else "zigzag",
        })
        scans.append((f"scan_{scan_idx + 1}", scan))
        variations.append({
            "index": scan_idx + 1,
            "dropout": dropout,
            "shift": shift,
            "rotate": rotate,
            "depth_bias": depth_bias,
            "gain": gain,
            "noise_add": noise_add,
        })
    truth["multiscan_variations"] = variations
    return scans, truth


def _screen(candidates):
    return screen_candidates(candidates, DEFAULT_SCREENING_POLICY)


def _identity_alignment(reference_anomaly, other_anomaly, resolution: int) -> AlignmentResult:
    a, am = _resample_to(reference_anomaly.zscore, (resolution, resolution))
    b, bm = _resample_to(other_anomaly.zscore, (resolution, resolution))
    valid = am & bm & np.isfinite(a) & np.isfinite(b)
    corr = (
        float(np.corrcoef(a[valid], b[valid])[0, 1])
        if int(valid.sum()) >= 3 and np.std(a[valid]) > 1e-9 and np.std(b[valid]) > 1e-9
        else 0.0
    )
    return AlignmentResult(
        transform_name="rot0",
        shift_dy=0,
        shift_dx=0,
        correlation=corr,
        overlap_fraction=float(np.mean(valid)),
        b_resampled=b,
        b_valid=bm,
        second_best_correlation=max(0.0, corr - 0.01),
        ambiguity_margin=0.01,
        multiscale_correlation=max(0.0, corr),
        candidate_count=1,
    )


def _fuse_preanalyzed(
    observations: list[ScanObservation],
    reference: ScanObservation,
    alignments: dict[str, AlignmentResult],
    *,
    resolution: int,
    threshold: float = 3.0,
    fusion_pruning: str = "off",
):
    qualities = [a.registration_evidence for a in alignments.values()]
    reg_consistency = float(np.mean(qualities)) if qualities else 1.0
    support, signed, persist, positive, negative = _consensus_maps(
        observations, alignments, reference, resolution, threshold
    )
    fused = fuse_site_candidates(observations, reference, alignments, 0.06, support, persist)
    fused, _ = separate_fused_candidates(
        fused,
        support,
        signed,
        reference.grid.x_centers,
        reference.grid.y_centers,
        positive_channel=positive,
        negative_channel=negative,
        persistence_map=persist,
        anomaly_threshold=float(threshold),
    )
    fused = [assess_candidate_quality(c) for c in fused]
    fused = [c for c in fused if int(getattr(c, "scan_count", 1)) >= 2]
    fused = deblend_spatially_separated_multitarget_pairs(fused)
    fused = resolve_dipole_pairs(fused)
    fused = merge_dipolar_response_components(fused)
    fused = [apply_local_geology_context(c) for c in fused]
    if fusion_pruning == "conservative-repeatability":
        from ...site.verdicts import _prune_repeatability_fused_candidates

        fused = _prune_repeatability_fused_candidates(fused)
    elif fusion_pruning != "off":
        raise ValueError("fusion_pruning must be one of: off, conservative-repeatability")
    for c in fused:
        c.registration_consistency = reg_consistency
    return fused, support, signed, persist, alignments


def run_multiscan_benchmark(
    out_dir: str | Path, *, count: int = 30, seed: int = 2047, fusion_resolution: int = 24
) -> dict:
    """Run deterministic multi-scan benchmark and write JSON/Markdown report.

    The core sites use identical physical coordinate frames and an explicit
    identity registration to exercise fusion without paying the full rigid
    registration search for every site. A subset of sites carries shift/rotation
    perturbations and uses the production aligner with a bounded stress-search.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = _site_specs(count=count, seed=seed)
    rows = []
    registration_rows = []
    for spec in specs:
        scans, truth = _make_variants(spec)
        site_dir = out_dir / spec.site_id
        site_dir.mkdir(parents=True, exist_ok=True)
        observations: list[ScanObservation] = []
        single_results = []
        for label, scan in scans:
            result = analyze(
                scan,
                site_dir / "single" / label,
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
            raw = evaluate_case(
                result.candidates, truth, split=spec.split, case_id=spec.site_id, family=spec.family
            )
            screened = evaluate_case(
                _screen(result.candidates),
                truth,
                split=spec.split,
                case_id=spec.site_id,
                family=spec.family,
            )
            single_results.append({
                "label": label,
                "raw": asdict(raw),
                "screened": asdict(screened),
            })

        reference = observations[0]
        alignments: dict[str, AlignmentResult] = {}
        for idx, obs in enumerate(observations[1:], start=2):
            variation = truth["multiscan_variations"][idx - 1]
            spatial_stress = variation["shift"] is not None or variation["rotate"] is not None
            if spatial_stress:
                al = align_grids(
                    reference.anomaly.zscore,
                    obs.anomaly.zscore,
                    resolution=fusion_resolution,
                    max_shift=2,
                    orientation_a_deg=reference.orientation_deg,
                    orientation_b_deg=obs.orientation_deg,
                )
            else:
                al = _identity_alignment(reference.anomaly, obs.anomaly, fusion_resolution)
            alignments[obs.label] = al
            registration_rows.append({
                "site_id": spec.site_id,
                "label": obs.label,
                "status": al.status,
                "evidence": al.registration_evidence,
                "correlation": al.correlation,
                "overlap": al.overlap_fraction,
                "margin": al.ambiguity_margin,
                "stress_search": spatial_stress,
            })

        fused, support, signed, persist, alignments = _fuse_preanalyzed(
            observations, reference, alignments, resolution=fusion_resolution
        )
        fused_raw = evaluate_case(
            fused, truth, split=spec.split, case_id=spec.site_id, family=spec.family
        )
        fused_screened = evaluate_case(
            _screen(fused), truth, split=spec.split, case_id=spec.site_id, family=spec.family
        )

        rows.append({
            "site_id": spec.site_id,
            "split": spec.split,
            "family": spec.family,
            "targets": len(truth["targets"]),
            "single_scan": single_results,
            "fused_raw": asdict(fused_raw),
            "fused_screened": asdict(fused_screened),
            "fused_candidates": [asdict(c) for c in fused],
            "registration": [r for r in registration_rows if r["site_id"] == spec.site_id],
            "truth": truth,
        })
        (site_dir / "ground_truth.json").write_text(
            json.dumps(truth, indent=2, allow_nan=True), encoding="utf-8"
        )

    def agg_dict(dict_rows):
        targets = sum(int(r["targets"]) for r in dict_rows)
        cand = sum(int(r["candidates"]) for r in dict_rows)
        matched = sum(int(r["matched_targets"]) for r in dict_rows)
        fps = sum(int(r["false_positives"]) for r in dict_rows)
        return {
            "sites": len(dict_rows),
            "targets": targets,
            "candidates": cand,
            "matched_targets": matched,
            "false_positives": fps,
            "recall": round(matched / targets, 4) if targets else 1.0,
            "precision": round(matched / cand, 4) if cand else (1.0 if not targets else 0.0),
            "mean_center_error_m": round(_safe_mean([r["center_error_m"] for r in dict_rows]), 4),
            "mean_depth_error_m": round(_safe_mean([r["depth_error_m"] for r in dict_rows]), 4),
        }

    fused_raw_dicts = [r["fused_raw"] for r in rows]
    fused_screen_dicts = [r["fused_screened"] for r in rows]
    reference_dicts = [r["single_scan"][0]["raw"] for r in rows]
    best_dicts = [
        max(r["single_scan"], key=lambda s: (s["raw"]["matched_targets"], s["raw"]["precision"]))[
            "raw"
        ]
        for r in rows
    ]
    family_summary = {}
    for family in sorted({r["family"] for r in rows}):
        family_summary[family] = agg_dict([r["fused_raw"] for r in rows if r["family"] == family])

    payload = {
        "benchmark": "synthetic_multiscan_site_fusion",
        "count": len(rows),
        "seed": seed,
        "scan_count": 3,
        "fusion_resolution": int(fusion_resolution),
        "split_rule": "3/5 calibration, 2/5 holdout, deterministic by site index",
        "baseline": {
            "reference_single_scan_raw": agg_dict(reference_dicts),
            "best_single_scan_raw_oracle": agg_dict(best_dicts),
        },
        "fused": {"raw": agg_dict(fused_raw_dicts), "screened": agg_dict(fused_screen_dicts)},
        "family_fused_raw": family_summary,
        "registration": {
            "sites": len(rows),
            "alignments": len(registration_rows),
            "strong_rate": round(
                sum(r["status"] == "strong" for r in registration_rows)
                / max(len(registration_rows), 1),
                4,
            ),
            "caution_rate": round(
                sum(r["status"] == "caution" for r in registration_rows)
                / max(len(registration_rows), 1),
                4,
            ),
            "weak_rate": round(
                sum(r["status"] == "weak" for r in registration_rows)
                / max(len(registration_rows), 1),
                4,
            ),
            "mean_evidence": round(_safe_mean([r["evidence"] for r in registration_rows]), 4),
            "mean_overlap": round(_safe_mean([r["overlap"] for r in registration_rows]), 4),
            "stress_alignment_cases": sum(1 for r in registration_rows if r["stress_search"]),
        },
        "cases": rows,
        "interpretation": {
            "synthetic_only": True,
            "not_field_validation": True,
            "not_material_probability": True,
            "purpose": "establish deterministic multi-scan regression before any production fusion scoring changes",
            "identity_registration_core": True,
            "registration_stress_uses_bounded_search": True,
            "best_single_scan_is_oracle_comparator": True,
        },
    }
    (out_dir / "multiscan_benchmark.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    (out_dir / "multiscan_registration.json").write_text(
        json.dumps(registration_rows, indent=2, allow_nan=True), encoding="utf-8"
    )
    (out_dir / "multiscan_benchmark.md").write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict) -> str:
    b = payload["baseline"]
    f = payload["fused"]
    r = payload["registration"]
    lines = [
        "# GroundScan Analyzer v0.2.49 — Multi-Scan Benchmark",
        "",
        "> Synthetic software validation only. This benchmark does not establish field accuracy, target/material probability, or physical detector performance.",
        "",
        f"Sites: **{payload['count']}**; scans per site: **{payload['scan_count']}**; seed: **{payload['seed']}**; fusion resolution: **{payload['fusion_resolution']}×{payload['fusion_resolution']}**.",
        "",
        "## Baseline vs fusion (raw)",
        "",
        "| Metric | Reference single scan | Best single scan (oracle) | Multi-scan fusion |",
        "|---|---:|---:|---:|",
    ]
    for key, label in [
        ("recall", "Recall"),
        ("precision", "Precision"),
        ("matched_targets", "Matched targets"),
        ("candidates", "Candidates"),
        ("mean_center_error_m", "Mean center error"),
        ("mean_depth_error_m", "Mean depth error"),
    ]:
        unit = " m" if "error" in key else ""
        lines.append(
            f"| {label} | {b['reference_single_scan_raw'][key]}{unit} | {b['best_single_scan_raw_oracle'][key]}{unit} | {f['raw'][key]}{unit} |"
        )
    lines += [
        "",
        "## Fusion after default screening",
        "",
        f"Recall: **{f['screened']['recall']:.4f}**; Precision: **{f['screened']['precision']:.4f}**; matched: **{f['screened']['matched_targets']}** / **{f['screened']['targets']}**.",
        "",
        "## Registration",
        "",
        f"Strong: **{r['strong_rate']:.1%}**, caution: **{r['caution_rate']:.1%}**, weak: **{r['weak_rate']:.1%}**, mean evidence: **{r['mean_evidence']:.3f}**, mean overlap: **{r['mean_overlap']:.3f}**; bounded stress alignments: **{r['stress_alignment_cases']}**.",
        "",
        "## Families (raw fusion)",
        "",
        "| Family | Recall | Precision | Matched | Candidates |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, m in payload["family_fused_raw"].items():
        lines.append(
            f"| {family} | {m['recall']:.4f} | {m['precision']:.4f} | {m['matched_targets']} | {m['candidates']} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "This benchmark establishes a deterministic multi-scan regression fixture. It is not evidence that the current fusion algorithm is physically accurate. Production fusion changes should beat the reference single-scan and current-fusion baselines on holdout while retaining OKM regression parity.",
        "",
    ]
    return "\n".join(lines)

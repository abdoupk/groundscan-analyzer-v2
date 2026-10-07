"""Cross-scan variation audit for GroundScan Analyzer v0.2.66.

Diagnostic-only synthetic validation of the current multi-scan fusion path under
acquisition-design and signal-quality variation. No production detector or
scoring policy is changed by this module.
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
from ...site.analyze_site import ScanObservation, fuse_site_candidates
from ...site.consensus import _consensus_maps
from ...site.registration import AlignmentResult, _resample_to, align_grids
from ...site.separation import resolve_dipole_pairs, separate_fused_candidates
from .benchmark_large import evaluate_case
from .core import SyntheticScenario, SyntheticTarget, generate_scan


@dataclass(frozen=True)
class Variation:
    name: str
    orientation_deg: float
    line_spacing_m: float
    scan_pattern: str
    noise_add: float = 0.0
    dropout: bool = False
    shift: tuple[int, int] | None = None
    gain: float = 1.0


def _safe_mean(values: Iterable[float]) -> float:
    """Backward-compat alias — canonical impl is groundscan._util.safe_mean."""
    from groundscan._util import safe_mean

    return safe_mean(values, default=float("nan"))


def _ring_median(signal: np.ndarray[Any, Any], row: int, col: int, radius: int) -> float:
    h, w = signal.shape
    r0, r1 = max(0, row - radius - 1), min(h, row + radius + 2)
    c0, c1 = max(0, col - radius - 1), min(w, col + radius + 2)
    patch = signal[r0:r1, c0:c1]
    yy, xx = np.ogrid[: patch.shape[0], : patch.shape[1]]
    cy, cx = row - r0, col - c0
    d2 = (yy - cy) ** 2 + (xx - cx) ** 2
    ring = patch[(d2 >= max(4, radius * radius * 0.55)) & (d2 <= (radius + 2) ** 2)]
    ring = ring[np.isfinite(ring)]
    return float(np.median(ring)) if ring.size else 150.0


def _apply_variation(scan, scenario: SyntheticScenario, variation: Variation, seed: int):
    rng = np.random.default_rng(seed)
    nx, ny = scenario.nx, scenario.ny
    signal = np.asarray(scan.signal, dtype=float).reshape(ny, nx).copy()
    depth = np.asarray(scan.z, dtype=float).reshape(ny, nx).copy()
    baseline = 150.0 + scenario.gradient_x * np.tile(np.linspace(0, scenario.width_m, nx), (ny, 1))
    baseline += scenario.gradient_y * np.tile(
        np.linspace(0, scenario.height_m, ny)[:, None], (1, nx)
    )
    signal = baseline + variation.gain * (signal - baseline)
    if variation.noise_add:
        signal += rng.normal(0.0, variation.noise_add, size=signal.shape)
    if variation.dropout and scenario.targets:
        target = max(scenario.targets, key=lambda t: abs(t.amplitude))
        col = int(round(target.x / max(scenario.width_m, 1e-9) * (nx - 1)))
        row = int(round(target.y / max(scenario.height_m, 1e-9) * (ny - 1)))
        radius = max(2, int(round(2.0 * max(target.sx, target.sy, 0.8))))
        r0, r1 = max(0, row - radius), min(ny, row + radius + 1)
        c0, c1 = max(0, col - radius), min(nx, col + radius + 1)
        replacement = _ring_median(signal, row, col, radius)
        signal[r0:r1, c0:c1] = replacement + rng.normal(
            0.0, max(0.15, variation.noise_add * 0.5), size=(r1 - r0, c1 - c0)
        )
    if variation.shift:
        dy, dx = variation.shift
        signal = np.roll(signal, (dy, dx), axis=(0, 1))
        depth = np.roll(depth, (dy, dx), axis=(0, 1))
    out = scan.__class__(
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
    out.metadata.extra = dict(out.metadata.extra)
    out.metadata.orientation_deg = variation.orientation_deg
    out.metadata.line_spacing_m = variation.line_spacing_m
    out.metadata.scan_pattern = variation.scan_pattern
    out.metadata.extra.update({
        "cross_scan_variation": variation.name,
        "cross_scan_noise_add": variation.noise_add,
        "cross_scan_dropout": variation.dropout,
        "cross_scan_shift": variation.shift,
        "cross_scan_gain": variation.gain,
        "cross_scan_truth_disclaimer": "synthetic acquisition-design variation; not field validation",
    })
    return out


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
        "rot0",
        0,
        0,
        corr,
        float(np.mean(valid)),
        b,
        bm,
        max(0.0, corr - 0.01),
        0.01,
        max(0.0, corr),
        1,
    )


def _families() -> tuple[str, ...]:
    return (
        "single_compact",
        "single_cavity",
        "single_tunnel",
        "close_multi",
        "overlapping_multi",
        "void_plus_geology",
    )


def _scenario(family: str, idx: int, seed: int) -> SyntheticScenario:
    rng = np.random.default_rng(seed + idx * 31)
    width, height = 40.0, 30.0
    depth = float(rng.choice([3.0, 5.0, 7.5, 10.0]))
    if family == "single_compact":
        targets = (
            SyntheticTarget(
                "positive_compact",
                10 + rng.uniform(-1, 1),
                13 + rng.uniform(-1, 1),
                depth=depth,
                amplitude=20,
                sx=1.1,
                sy=1.2,
            ),
        )
    elif family == "single_cavity":
        targets = (
            SyntheticTarget(
                "cavity",
                24 + rng.uniform(-1, 1),
                14 + rng.uniform(-1, 1),
                depth=depth,
                amplitude=18,
                sx=2.4,
                sy=2.1,
            ),
        )
    elif family == "single_tunnel":
        targets = (
            SyntheticTarget(
                "tunnel",
                20,
                15,
                depth=depth,
                amplitude=14,
                sy=0.9,
                length=14,
                orientation_deg=float(rng.choice([0, 35, 90, 135])),
            ),
        )
    elif family == "close_multi":
        x, y = 13 + rng.uniform(-1, 1), 14 + rng.uniform(-1, 1)
        targets = (
            SyntheticTarget("positive_compact", x, y, depth=3.5, amplitude=22, sx=1.2, sy=1.1),
            SyntheticTarget(
                "cavity", x + 4.0, y + rng.uniform(-1, 1), depth=6.5, amplitude=17, sx=2.0, sy=1.8
            ),
        )
    elif family == "overlapping_multi":
        x, y = 15 + rng.uniform(-1, 1), 14 + rng.uniform(-1, 1)
        targets = (
            SyntheticTarget("positive_compact", x, y, depth=3.8, amplitude=24, sx=1.6, sy=1.4),
            SyntheticTarget(
                "cavity",
                x + 2.2,
                y + rng.uniform(-0.8, 0.8),
                depth=7.0,
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
                depth=5.0,
                amplitude=17,
                sx=2.5,
                sy=2.2,
            ),
        )
    return SyntheticScenario(
        name=f"v066_{idx:03d}_{family}",
        width_m=width,
        height_m=height,
        nx=int(rng.choice([31, 41, 51])),
        ny=int(rng.choice([25, 31])),
        targets=tuple(targets),
        noise_sigma=float(rng.choice([0.6, 1.0, 1.5, 2.0])),
        gradient_x=float(rng.uniform(-0.12, 0.12)),
        gradient_y=float(rng.uniform(-0.08, 0.08)),
        depth_noise_sigma=float(rng.choice([0.04, 0.08, 0.16, 0.25])),
        seed=seed + idx * 31,
    )


def _variations() -> tuple[Variation, ...]:
    return (
        Variation("baseline_parallel_1m", 0.0, 1.0, "parallel", 0.05, False, None, 1.0),
        Variation("noise_zigzag_0_5m", 0.0, 0.5, "zigzag", 0.45, False, None, 0.98),
        Variation("dropout_parallel_1m", 90.0, 1.0, "parallel", 0.75, True, None, 1.02),
        Variation("shift_zigzag_0_5m", 90.0, 0.5, "zigzag", 1.0, False, (1, -1), 1.05),
        Variation("noisy_parallel_0_5m", 45.0, 0.5, "parallel", 1.5, False, None, 0.94),
    )


def _fuse(
    observations: list[ScanObservation],
    reference: ScanObservation,
    alignments: dict[str, AlignmentResult],
    resolution: int,
):
    support, signed, persist, positive, negative = _consensus_maps(
        observations, alignments, reference, resolution, 3.0
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
        anomaly_threshold=3.0,
    )
    fused = [assess_candidate_quality(c) for c in fused]
    fused = [c for c in fused if int(getattr(c, "scan_count", 1)) >= 2]
    fused = deblend_spatially_separated_multitarget_pairs(fused)
    fused = resolve_dipole_pairs(fused)
    fused = merge_dipolar_response_components(fused)
    fused = [apply_local_geology_context(c) for c in fused]
    return fused


def run_cross_scan_variation_audit(
    out_dir: str | Path,
    *,
    count_per_family: int = 4,
    seed: int = 4066,
    fusion_resolution: int = 32,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    variations = _variations()
    rows = []
    reg_rows = []
    for family in _families():
        for _ in range(count_per_family):
            idx = len(rows)
            scenario = _scenario(family, idx, seed)
            base_scan, truth = generate_scan(scenario)
            observations = []
            singles = []
            for v_idx, variation in enumerate(variations):
                scan = _apply_variation(base_scan, scenario, variation, seed + idx * 100 + v_idx)
                result = analyze(
                    scan,
                    out_dir / "scans" / scenario.name / variation.name,
                    label=variation.name,
                    config=AnalysisConfig(),
                    write_outputs=False,
                )
                obs = ScanObservation(
                    variation.name,
                    scan,
                    result.grid,
                    result.anomaly,
                    detect_artifacts(result.grid, result.anomaly),
                    result.candidates,
                )
                observations.append(obs)
                ev = evaluate_case(
                    result.candidates, truth, split="holdout", case_id=scenario.name, family=family
                )
                singles.append(asdict(ev))
            reference = observations[0]
            alignments = {}
            for obs in observations[1:]:
                if (
                    obs.scan.metadata.orientation_deg != reference.scan.metadata.orientation_deg
                    or obs.scan.metadata.line_spacing_m != reference.scan.metadata.line_spacing_m
                ):
                    al = align_grids(
                        reference.anomaly.zscore,
                        obs.anomaly.zscore,
                        resolution=fusion_resolution,
                        max_shift=2,
                        orientation_a_deg=reference.scan.metadata.orientation_deg,
                        orientation_b_deg=obs.scan.metadata.orientation_deg,
                    )
                else:
                    al = _identity_alignment(reference.anomaly, obs.anomaly, fusion_resolution)
                alignments[obs.label] = al
                reg_rows.append({
                    "site_id": scenario.name,
                    "scan": obs.label,
                    "status": al.status,
                    "evidence": al.registration_evidence,
                    "overlap": al.overlap_fraction,
                    "transform": al.transform_name,
                    "variation": obs.scan.metadata.extra.get("cross_scan_variation"),
                })
            fused = _fuse(observations, reference, alignments, fusion_resolution)
            fused_eval = evaluate_case(
                fused, truth, split="holdout", case_id=scenario.name, family=family
            )
            rows.append({
                "site_id": scenario.name,
                "family": family,
                "truth_targets": len(truth["targets"]),
                "single": singles,
                "fused": asdict(fused_eval),
                "fused_candidates": [asdict(c) for c in fused],
            })

    def agg(dict_rows):
        targets = sum(int(r["targets"]) for r in dict_rows)
        cand = sum(int(r["candidates"]) for r in dict_rows)
        matched = sum(int(r["matched_targets"]) for r in dict_rows)
        return {
            "sites": len(dict_rows),
            "targets": targets,
            "candidates": cand,
            "matched_targets": matched,
            "false_positives": cand - matched,
            "recall": round(matched / max(targets, 1), 4),
            "precision": round(matched / max(cand, 1), 4),
        }

    fused_rows = [r["fused"] for r in rows]
    family_summary = {f: agg([r["fused"] for r in rows if r["family"] == f]) for f in _families()}
    reg_values = [r["evidence"] for r in reg_rows]
    payload = {
        "benchmark": "cross_scan_variation_audit",
        "sites": len(rows),
        "scans_per_site": len(variations),
        "seed": seed,
        "variations": [asdict(v) for v in variations],
        "fused": agg(fused_rows),
        "family_fused": family_summary,
        "registration": {
            "alignments": len(reg_rows),
            "strong_rate": round(
                sum(r["status"] == "strong" for r in reg_rows) / max(len(reg_rows), 1), 4
            ),
            "mean_evidence": round(_safe_mean(reg_values), 4),
            "mean_overlap": round(_safe_mean([r["overlap"] for r in reg_rows]), 4),
        },
        "cases": rows,
        "registration_rows": reg_rows,
        "decision": "diagnostic_only_no_production_change",
        "note": "Synthetic acquisition-design and signal-quality robustness only; traversal and spacing are represented as survey metadata while raster geometry remains the reconstructed spatial field. Not field validation.",
    }
    (out_dir / "cross_scan_variation_audit.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.66 — Cross-Scan Variation Audit",
        "",
        "> Synthetic robustness audit only; no production fusion/detector change.",
        "",
        f"Sites: **{len(rows)}**; scans/site: **{len(variations)}**; seed: **{seed}**.",
        "",
        "## Variations",
        "",
        "| Name | Orientation | Spacing | Traversal | Noise | Dropout | Shift |",
        "|---|---:|---:|---|---:|---|---|",
    ]
    for v in variations:
        lines.append(
            f"| {v.name} | {v.orientation_deg:.0f}° | {v.line_spacing_m:.2f} m | {v.scan_pattern} | {v.noise_add:.2f} | {'yes' if v.dropout else 'no'} | {v.shift or '-'} |"
        )
    f = payload["fused"]
    r = payload["registration"]
    lines += [
        "",
        "## Aggregate fusion",
        "",
        f"Recall **{f['recall']:.4f}**; precision **{f['precision']:.4f}**; matched **{f['matched_targets']}** / **{f['targets']}**; false positives **{f['false_positives']}**.",
        "",
        "## Registration",
        "",
        f"Strong rate **{r['strong_rate']:.1%}**; mean evidence **{r['mean_evidence']:.3f}**; mean overlap **{r['mean_overlap']:.3f}**.",
        "",
        "## Families",
        "",
        "| Family | Recall | Precision | Matched | Candidates |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, m in family_summary.items():
        lines.append(
            f"| {family} | {m['recall']:.4f} | {m['precision']:.4f} | {m['matched_targets']} | {m['candidates']} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "This release is diagnostic-only. Production fusion/pruning remains unchanged; use this audit to identify robustness regressions before enabling any new policy.",
        "",
    ]
    (out_dir / "cross_scan_variation_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

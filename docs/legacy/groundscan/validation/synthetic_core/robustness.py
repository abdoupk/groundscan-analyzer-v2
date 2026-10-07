"""Synthetic real-world robustness generator and benchmark helpers.

All perturbations preserve a separate ground-truth truth object. The forward
model is still synthetic and intentionally device-agnostic; these utilities
exercise software robustness, not physical instrument behavior.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ...models import ScanData, ScanMetadata
from ...services.config import AnalysisConfig
from ...services.single_scan import analyze_scan
from .benchmark_large import evaluate_case
from .core import SyntheticScenario, generate_scan, scenario_catalog


@dataclass(frozen=True)
class PerturbationProfile:
    name: str
    extra_noise_sigma: float = 0.0
    outlier_fraction: float = 0.0
    outlier_sigma: float = 0.0
    missing_fraction: float = 0.0
    drop_row_fraction: float = 0.0
    duplicate_fraction: float = 0.0
    coordinate_jitter_m: float = 0.0
    baseline_drift_x: float = 0.0
    baseline_drift_y: float = 0.0
    line_bias_sigma: float = 0.0
    quantization_step: float = 0.0
    clip_percentile: float | None = None
    shuffle: bool = True


def _clone_metadata(metadata: ScanMetadata, *, extra: dict | None = None) -> ScanMetadata:
    values = asdict(metadata)
    merged_extra = dict(values.get("extra") or {})
    merged_extra.update(extra or {})
    values["extra"] = merged_extra
    return ScanMetadata(**values)


def perturb_scan(scan: ScanData, profile: PerturbationProfile, seed: int = 0) -> ScanData:
    """Apply bounded synthetic corruption while preserving semantic metadata.

    The returned object never mutates the input. Grid indices are preserved for
    grid-based scans so missing cells remain explicit rather than being silently
    reinterpolated. Coordinate jitter is applied independently to physical x/y.
    """
    rng = np.random.default_rng(seed)
    n = len(scan)
    idx = np.arange(n)

    keep = np.ones(n, dtype=bool)
    if profile.drop_row_fraction > 0:
        drop_n = int(round(n * np.clip(profile.drop_row_fraction, 0.0, 0.95)))
        if drop_n:
            drop_idx = rng.choice(n, size=drop_n, replace=False)
            keep[drop_idx] = False
    idx = idx[keep]

    x = np.asarray(scan.x[idx], dtype=float).copy()
    y = np.asarray(scan.y[idx], dtype=float).copy()
    z = np.asarray(scan.z[idx], dtype=float).copy()
    signal = np.asarray(scan.signal[idx], dtype=float).copy()
    gi = np.asarray(scan.grid_i[idx], dtype=float).copy() if scan.grid_i is not None else None
    gj = np.asarray(scan.grid_j[idx], dtype=float).copy() if scan.grid_j is not None else None
    lat = np.asarray(scan.latitude[idx], dtype=float).copy() if scan.latitude is not None else None
    lon = (
        np.asarray(scan.longitude[idx], dtype=float).copy() if scan.longitude is not None else None
    )

    finite_signal = np.isfinite(signal)
    if profile.extra_noise_sigma > 0:
        signal[finite_signal] += rng.normal(0.0, profile.extra_noise_sigma, finite_signal.sum())

    if profile.baseline_drift_x or profile.baseline_drift_y:
        x0 = float(np.nanmin(x)) if np.any(np.isfinite(x)) else 0.0
        y0 = float(np.nanmin(y)) if np.any(np.isfinite(y)) else 0.0
        signal += profile.baseline_drift_x * (x - x0) + profile.baseline_drift_y * (y - y0)

    if profile.line_bias_sigma > 0 and gj is not None:
        unique_lines = np.unique(gj[np.isfinite(gj)])
        bias = {float(v): float(rng.normal(0.0, profile.line_bias_sigma)) for v in unique_lines}
        signal += np.array([bias.get(float(v), 0.0) for v in gj])

    if profile.outlier_fraction > 0 and np.any(finite_signal):
        out_n = int(
            round(np.count_nonzero(finite_signal) * np.clip(profile.outlier_fraction, 0.0, 0.5))
        )
        if out_n:
            candidates = np.flatnonzero(finite_signal)
            picks = rng.choice(candidates, size=min(out_n, len(candidates)), replace=False)
            sigma = (
                profile.outlier_sigma
                if profile.outlier_sigma > 0
                else max(float(np.nanstd(signal[finite_signal])), 1.0) * 6.0
            )
            signal[picks] += rng.normal(0.0, sigma, len(picks))

    if profile.clip_percentile is not None and np.any(finite_signal):
        p = float(np.clip(profile.clip_percentile, 50.0, 100.0))
        lo, hi = np.nanpercentile(signal[finite_signal], [100.0 - p, p])
        signal[finite_signal] = np.clip(signal[finite_signal], lo, hi)

    if profile.quantization_step > 0:
        step = float(profile.quantization_step)
        signal[finite_signal] = np.round(signal[finite_signal] / step) * step

    if profile.missing_fraction > 0:
        missing_n = int(round(len(signal) * np.clip(profile.missing_fraction, 0.0, 0.90)))
        if missing_n:
            missing = rng.choice(len(signal), size=missing_n, replace=False)
            signal[missing] = np.nan
            z[missing] = np.nan

    if profile.coordinate_jitter_m > 0:
        x += rng.normal(0.0, profile.coordinate_jitter_m, len(x))
        y += rng.normal(0.0, profile.coordinate_jitter_m, len(y))

    if profile.duplicate_fraction > 0 and len(signal):
        dup_n = int(round(len(signal) * np.clip(profile.duplicate_fraction, 0.0, 0.30)))
        if dup_n:
            picks = rng.choice(len(signal), size=min(dup_n, len(signal)), replace=False)
            x = np.concatenate([x, x[picks]])
            y = np.concatenate([y, y[picks]])
            z = np.concatenate([z, z[picks]])
            signal = np.concatenate([signal, signal[picks]])
            if gi is not None:
                gi = np.concatenate([gi, gi[picks]])
            if gj is not None:
                gj = np.concatenate([gj, gj[picks]])
            if lat is not None:
                lat = np.concatenate([lat, lat[picks]])
            if lon is not None:
                lon = np.concatenate([lon, lon[picks]])

    if profile.shuffle:
        order = rng.permutation(len(signal))
        x, y, z, signal = x[order], y[order], z[order], signal[order]
        if gi is not None:
            gi = gi[order]
        if gj is not None:
            gj = gj[order]
        if lat is not None:
            lat = lat[order]
        if lon is not None:
            lon = lon[order]

    metadata = _clone_metadata(
        scan.metadata,
        extra={
            "synthetic_robustness_profile": profile.name,
            "synthetic_robustness_seed": seed,
        },
    )
    return ScanData(
        x=x,
        y=y,
        z=z,
        signal=signal,
        grid_i=gi,
        grid_j=gj,
        latitude=lat,
        longitude=lon,
        coords_are_index_only=scan.coords_are_index_only,
        metadata=metadata,
    )


def robustness_profiles() -> tuple[PerturbationProfile, ...]:
    """Profiles from clean to severe-but-plausible software stress."""
    return (
        PerturbationProfile("clean"),
        PerturbationProfile(
            "mild",
            extra_noise_sigma=0.6,
            outlier_fraction=0.005,
            outlier_sigma=8.0,
            missing_fraction=0.02,
            coordinate_jitter_m=0.03,
            line_bias_sigma=0.25,
        ),
        PerturbationProfile(
            "moderate",
            extra_noise_sigma=1.2,
            outlier_fraction=0.012,
            outlier_sigma=12.0,
            missing_fraction=0.06,
            drop_row_fraction=0.04,
            duplicate_fraction=0.02,
            coordinate_jitter_m=0.08,
            baseline_drift_x=0.04,
            baseline_drift_y=-0.025,
            line_bias_sigma=0.5,
            quantization_step=0.05,
        ),
        PerturbationProfile(
            "severe",
            extra_noise_sigma=2.0,
            outlier_fraction=0.025,
            outlier_sigma=18.0,
            missing_fraction=0.12,
            drop_row_fraction=0.08,
            duplicate_fraction=0.04,
            coordinate_jitter_m=0.15,
            baseline_drift_x=0.09,
            baseline_drift_y=-0.06,
            line_bias_sigma=0.9,
            quantization_step=0.10,
            clip_percentile=99.0,
        ),
    )


def _robust_catalog() -> list[SyntheticScenario]:
    wanted = {
        "positive_compact",
        "negative_cavity",
        "linear_tunnel",
        "geological_broad",
        "no_target_noise",
        "multiple_targets",
        "close_targets",
        "overlapping_targets",
        "rotated_tunnel",
        "void_plus_geology",
    }
    return [s for s in scenario_catalog() if s.name in wanted]


def write_scan_csv(scan: ScanData, path: str | Path) -> None:
    """Write a normalized synthetic CSV suitable for the generic adapter."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["x", "y", "z", "signal"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for row in zip(scan.x, scan.y, scan.z, scan.signal, strict=True):
            writer.writerow([float(v) if np.isfinite(v) else "" for v in row])


def generate_robust_dataset(
    out_dir: str | Path, *, repeats: int = 2, seed: int = 2901, export_csv: bool = True
) -> dict:
    """Generate reproducible synthetic datasets and manifest with truth preserved."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    profiles = robustness_profiles()
    for base_idx, scenario in enumerate(_robust_catalog()):
        clean_scan, truth = generate_scan(scenario)
        for profile_idx, profile in enumerate(profiles):
            for rep in range(repeats):
                case_seed = seed + base_idx * 1000 + profile_idx * 100 + rep
                scan = perturb_scan(clean_scan, profile, seed=case_seed)
                case_id = f"{scenario.name}__{profile.name}__r{rep:02d}"
                case_dir = out_dir / case_id
                case_dir.mkdir(parents=True, exist_ok=True)
                truth_payload = dict(truth)
                truth_payload.update({
                    "base_scenario": scenario.name,
                    "profile": asdict(profile),
                    "case_id": case_id,
                    "seed": case_seed,
                })
                (case_dir / "ground_truth.json").write_text(
                    json.dumps(truth_payload, indent=2), encoding="utf-8"
                )
                if export_csv:
                    write_scan_csv(scan, case_dir / "scan.csv")
                manifest.append({
                    "case_id": case_id,
                    "base_scenario": scenario.name,
                    "family": scenario.name,
                    "profile": asdict(profile),
                    "truth": truth_payload,
                    "path": str((case_dir / "scan.csv").relative_to(out_dir))
                    if export_csv
                    else None,
                })
    payload = {
        "count": len(manifest),
        "profiles": [asdict(p) for p in profiles],
        "cases": manifest,
        "note": "synthetic robustness dataset only; no field validation",
    }
    (out_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def run_robustness_benchmark(
    out_dir: str | Path, *, repeats: int = 3, seed: int = 2920, write_cases: bool = False
) -> dict:
    """Run stratified corruption benchmark across the synthetic catalog."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = robustness_profiles()
    rows: list[dict] = []
    family_results: dict[str, list[dict]] = {}
    for base_idx, scenario in enumerate(_robust_catalog()):
        clean_scan, truth = generate_scan(scenario)
        for profile_idx, profile in enumerate(profiles):
            for rep in range(repeats):
                case_seed = seed + base_idx * 1000 + profile_idx * 100 + rep
                scan = perturb_scan(clean_scan, profile, seed=case_seed)
                case_id = f"{scenario.name}__{profile.name}__r{rep:02d}"
                case_dir = out_dir / case_id if write_cases else out_dir / "cases"
                case_dir.mkdir(parents=True, exist_ok=True)
                _, _, candidates = analyze_scan(
                    scan,
                    case_dir,
                    label=case_id,
                    config=AnalysisConfig(),
                    write_outputs=write_cases,
                )
                result = evaluate_case(
                    candidates, truth, split="robustness", case_id=case_id, family=scenario.name
                )
                row = {
                    "case_id": case_id,
                    "profile": profile.name,
                    "family": scenario.name,
                    **asdict(result),
                }
                rows.append(row)
                family_results.setdefault(scenario.name, []).append(row)

    def avg(seq: Iterable[float]) -> float:
        vals = [float(v) for v in seq if np.isfinite(v)]
        return float(np.mean(vals)) if vals else float("nan")

    profiles_summary = {}
    for profile in profiles:
        subset = [r for r in rows if r["profile"] == profile.name]
        profiles_summary[profile.name] = {
            "cases": len(subset),
            "recall": round(avg(r["recall"] for r in subset), 4),
            "precision": round(avg(r["precision"] for r in subset), 4),
            "mean_center_error_m": round(avg(r["center_error_m"] for r in subset), 4),
            "mean_depth_error_m": round(avg(r["depth_error_m"] for r in subset), 4),
            "false_positive_case_rate": round(
                avg(1.0 if (r["targets"] == 0 and r["candidates"] > 0) else 0.0 for r in subset), 4
            ),
            "exact_target_count_rate": round(
                avg(1.0 if r["exact_target_count"] else 0.0 for r in subset), 4
            ),
        }

    families_summary = {}
    for family, values in family_results.items():
        families_summary[family] = {
            "cases": len(values),
            "recall": round(avg(r["recall"] for r in values), 4),
            "precision": round(avg(r["precision"] for r in values), 4),
            "mean_center_error_m": round(avg(r["center_error_m"] for r in values), 4),
            "mean_depth_error_m": round(avg(r["depth_error_m"] for r in values), 4),
        }

    payload = {
        "cases": len(rows),
        "repeats": repeats,
        "seed": seed,
        "profiles": profiles_summary,
        "families": families_summary,
        "rows": rows,
        "failure_modes": [
            "missing_cells",
            "outliers",
            "coordinate_jitter",
            "baseline_drift",
            "line_bias",
            "duplicates",
            "quantization",
            "clipping",
            "multi-target_overlap",
            "no-target_noise",
        ],
        "note": "Synthetic software robustness benchmark only; metrics are not field accuracy and no material/void probability is inferred.",
    }
    (out_dir / "robustness_benchmark.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    return payload

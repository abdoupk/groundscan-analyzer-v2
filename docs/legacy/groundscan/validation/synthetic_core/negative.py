"""Adversarial/negative scan builders for the science framework (P2).

All builders produce target-free scans (truth carries no targets) with
hostile structure the detector must survive: crash-freedom, finite
outputs, quality-gate discipline, and bounded false positives. Builders
use only NumPy with fixed seeds; no new dependencies.

Correlated-noise note: the historical generator uses white Gaussian noise
only. Smooth (spatially correlated) noise is the known object-mimic, so
it is generated here as a Gaussian random field via FFT low-pass
filtering — deliberately outside the white-noise family the detector's
background estimators were exercised against.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ...models import ScanData, ScanMetadata


@dataclass(frozen=True)
class NegativeCase:
    """One hostile target-free scan plus its generation conditions."""

    family: str
    case_id: str
    scan: ScanData
    seed: int
    description: str


def _base_scan(
    nx: int,
    ny: int,
    width_m: float,
    height_m: float,
    signal: np.ndarray,
    *,
    device_note: str,
    seed: int,
) -> ScanData:
    yy, xx = np.meshgrid(
        np.linspace(0.0, height_m, ny), np.linspace(0.0, width_m, nx), indexing="ij"
    )
    return ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=np.full(xx.size, 12.0),
        signal=np.asarray(signal, dtype=float).ravel(),
        grid_i=np.tile(np.arange(nx, dtype=float), ny),
        grid_j=np.repeat(np.arange(ny, dtype=float), nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device="synthetic-negative",
            field_length_m=width_m,
            field_width_m=height_m,
            notes=device_note,
            source_file=f"synthetic-negative:{device_note}",
        ),
    )


def _grf(rng: np.random.Generator, ny: int, nx: int, correlation_cells: float) -> np.ndarray:
    """Gaussian random field: white noise low-passed in Fourier space."""
    white = rng.normal(0.0, 1.0, (ny, nx))
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.fftfreq(nx)[None, :]
    kernel = np.exp(-0.5 * ((fx**2 + fy**2) * (float(correlation_cells) ** 2)))
    field = np.fft.ifft2(np.fft.fft2(white) * kernel).real
    std = float(np.std(field))
    return field / max(std, 1e-9)


def smooth_noise_cases(seed: int = 501) -> list[NegativeCase]:
    """Spatially correlated noise at three correlation lengths (object-mimic)."""
    rng = np.random.default_rng(seed)
    cases = []
    for length in (2.0, 4.0, 8.0):
        field = _grf(rng, 25, 31, length)
        signal = 150.0 + 6.0 * field + rng.normal(0.0, 0.5, field.shape)
        cases.append(
            NegativeCase(
                family="smooth_noise",
                case_id=f"smooth_noise_L{length:g}",
                scan=_base_scan(
                    31,
                    25,
                    30.0,
                    24.0,
                    signal,
                    device_note=f"correlated-noise-L{length:g}",
                    seed=seed,
                ),
                seed=seed,
                description=(
                    "Gaussian random field, correlation length "
                    f"{length:g} cells; may legitimately read as structure."
                ),
            )
        )
    return cases


def white_noise_case(seed: int = 502) -> NegativeCase:
    rng = np.random.default_rng(seed)
    signal = 150.0 + rng.normal(0.0, 2.5, (21, 31))
    return NegativeCase(
        family="white_noise_empty",
        case_id="white_noise_empty",
        scan=_base_scan(31, 21, 30.0, 20.0, signal, device_note="white-noise-empty", seed=seed),
        seed=seed,
        description="Pure white noise, no structure; engine should stay silent.",
    )


def gradient_extreme_case(seed: int = 503) -> NegativeCase:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:21, 0:31].astype(float)
    signal = 150.0 + 2.5 * xx + -1.8 * yy + rng.normal(0.0, 1.0, xx.shape)
    return NegativeCase(
        family="gradient_extreme",
        case_id="gradient_extreme",
        scan=_base_scan(31, 21, 30.0, 20.0, signal, device_note="gradient-extreme", seed=seed),
        seed=seed,
        description="Strong planar gradient, no targets; background must absorb it.",
    )


def stripe_cases(seed: int = 504) -> list[NegativeCase]:
    """Periodic stripes: coherent linear structure with no target behind it."""
    rng = np.random.default_rng(seed)
    cases = []
    for period in (3.0, 5.0):
        yy, xx = np.mgrid[0:21, 0:31].astype(float)
        signal = 150.0 + 7.0 * np.sin(2.0 * np.pi * xx / period) + rng.normal(0.0, 0.8, xx.shape)
        cases.append(
            NegativeCase(
                family="periodic_stripes",
                case_id=f"periodic_stripes_P{period:g}",
                scan=_base_scan(
                    31,
                    21,
                    30.0,
                    20.0,
                    signal,
                    device_note=f"periodic-stripes-P{period:g}",
                    seed=seed,
                ),
                seed=seed,
                description=(
                    f"Sinusoidal stripes period {period:g} cells; coherent "
                    "linear energy with no target."
                ),
            )
        )
    return cases


def nan_block_case(seed: int = 505) -> NegativeCase:
    """Contiguous NaN block (~15% of cells); engine must stay finite."""
    rng = np.random.default_rng(seed)
    signal = 150.0 + rng.normal(0.0, 1.5, (21, 31))
    signal[8:13, 10:20] = float("nan")
    return NegativeCase(
        family="nan_block",
        case_id="nan_block",
        scan=_base_scan(31, 21, 30.0, 20.0, signal, device_note="nan-block", seed=seed),
        seed=seed,
        description="Contiguous NaN block; missing-data path must stay finite.",
    )


def missing_lines_case(seed: int = 506) -> NegativeCase:
    """Two adjacent acquisition lines dropped entirely."""
    rng = np.random.default_rng(seed)
    nx, ny = 31, 21
    yy, xx = np.meshgrid(np.linspace(0.0, 20.0, ny), np.linspace(0.0, 30.0, nx), indexing="ij")
    signal = 150.0 + rng.normal(0.0, 1.5, (ny, nx))
    keep_rows = np.array([r for r in range(ny) if r not in (9, 10)])
    xx, yy, signal = xx[keep_rows], yy[keep_rows], signal[keep_rows]
    gi = np.tile(np.arange(nx, dtype=float), len(keep_rows))
    gj = np.repeat(keep_rows.astype(float), nx)
    scan = ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=np.full(xx.size, 12.0),
        signal=signal.ravel(),
        grid_i=gi,
        grid_j=gj,
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device="synthetic-negative",
            field_length_m=30.0,
            field_width_m=20.0,
            notes="missing adjacent lines 9-10",
            source_file="synthetic-negative:missing-lines",
        ),
    )
    return NegativeCase(
        family="missing_lines",
        case_id="missing_lines",
        scan=scan,
        seed=seed,
        description="Lines 9-10 absent; lattice has a hole but stays regular.",
    )


def all_negative_cases() -> list[NegativeCase]:
    """Every adversarial family in deterministic order (fixed seeds)."""
    return [
        white_noise_case(),
        gradient_extreme_case(),
        *smooth_noise_cases(),
        *stripe_cases(),
        nan_block_case(),
        missing_lines_case(),
    ]


def negative_truth(case: NegativeCase) -> dict:
    """Truth descriptor: the absence of targets IS the ground truth."""
    return {
        "case_id": case.case_id,
        "family": case.family,
        "targets": [],
        "seed": case.seed,
        "description": case.description,
        "scan_meta": asdict(case.scan.metadata),
    }


def run_negative_case(case: NegativeCase, work_dir, *, policy=None) -> dict:
    """Run one negative case through the public pipeline and classify it.

    Uses the documented screening operating point (read from the policy
    object, never hardcoded). Crash-freedom and output finiteness are
    measured outcomes here, not assumptions.
    """
    import math
    from pathlib import Path

    from ...gates.screening import DEFAULT_SCREENING_POLICY, screen_candidates
    from ...services.config import AnalysisConfig
    from ...services.single_scan import analyze_scan
    from .oracles import (
        ORACLE_VERSION,
        classify_negative,
        negative_verdict_passes,
        operating_point_record,
    )

    active = DEFAULT_SCREENING_POLICY if policy is None else policy
    out_dir = Path(work_dir) / case.case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    crashed = False
    crash_detail = ""
    raw_count = 0
    retained: list = []
    try:
        _, _, candidates = analyze_scan(
            case.scan,
            out_dir,
            label=case.case_id,
            config=AnalysisConfig(),
            write_outputs=False,
        )
        raw_count = len(candidates)
        retained = screen_candidates(candidates, active)
    except Exception as exc:  # noqa: BLE001 -- crashes are measured outcomes here
        crashed = True
        crash_detail = f"{type(exc).__name__}: {exc}"
    blocked = False
    if not crashed:
        quality = (case.scan.metadata.extra or {}).get("field_quality", {})
        blocked = bool(quality.get("hard_block", False))
    nonfinite = sum(
        1
        for c in retained
        if not (math.isfinite(float(c.evidence_score)) and math.isfinite(float(c.screening_score)))
    )
    binned, detail = classify_negative(
        case.family,
        len(retained),
        crashed=crashed,
        blocked=blocked,
        nonfinite_outputs=nonfinite,
    )
    if crashed:
        detail = crash_detail or detail
    return {
        "oracle_version": ORACLE_VERSION,
        "case_id": case.case_id,
        "family": case.family,
        "truth": negative_truth(case),
        "raw_candidates": raw_count,
        "retained_candidates": len(retained),
        "retained_patterns": sorted({c.pattern_hypothesis for c in retained}),
        "quality_blocked": blocked,
        "crashed": crashed,
        "verdict": binned,
        "verdict_detail": detail,
        "passes": negative_verdict_passes(binned),
        "operating_point": operating_point_record(active),
    }

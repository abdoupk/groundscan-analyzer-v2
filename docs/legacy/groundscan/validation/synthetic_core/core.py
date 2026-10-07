"""Deterministic synthetic scan generation with explicit ground truth.

These fixtures are intentionally simple forward-model patterns, not claims about
any real instrument's EM/geo-physical response. They exist to exercise software
logic, robustness, geometry handling and regression tests when no real dataset is
available.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ...models import ScanData, ScanMetadata


@dataclass(frozen=True)
class SyntheticTarget:
    kind: str
    x: float
    y: float
    depth: float = 4.0
    amplitude: float = 10.0
    sx: float = 1.5
    sy: float = 1.5
    length: float = 8.0
    orientation_deg: float = 0.0


@dataclass(frozen=True)
class SyntheticScenario:
    name: str
    width_m: float
    height_m: float
    nx: int
    ny: int
    targets: tuple[SyntheticTarget, ...]
    noise_sigma: float = 1.0
    gradient_x: float = 0.0
    gradient_y: float = 0.0
    depth_noise_sigma: float = 0.05
    seed: int = 0
    mineralization_pct: float | None = None


def _gaussian_rotated(xx, yy, target: SyntheticTarget):
    theta = np.radians(target.orientation_deg)
    cx, cy = target.x, target.y
    xr = np.cos(theta) * (xx - cx) + np.sin(theta) * (yy - cy)
    yr = -np.sin(theta) * (xx - cx) + np.cos(theta) * (yy - cy)
    return np.exp(-0.5 * ((xr / max(target.sx, 1e-6)) ** 2 + (yr / max(target.sy, 1e-6)) ** 2))


def _target_response(xx, yy, target: SyntheticTarget):
    kind = target.kind
    if kind in {"positive_point", "negative_point", "positive_compact", "negative_compact"}:
        response = _gaussian_rotated(xx, yy, target)
        return response * target.amplitude * (-1.0 if kind.startswith("negative") else 1.0)

    if kind in {"cavity", "negative_cavity"}:
        core = _gaussian_rotated(xx, yy, target)
        return -abs(target.amplitude) * core

    if kind in {"tunnel", "linear_negative", "linear_positive"}:
        theta = np.radians(target.orientation_deg)
        cx, cy = target.x, target.y
        xr = np.cos(theta) * (xx - cx) + np.sin(theta) * (yy - cy)
        yr = -np.sin(theta) * (xx - cx) + np.cos(theta) * (yy - cy)
        along = target.length / 2.0
        axial = np.exp(-0.5 * (xr / max(along, 1e-6)) ** 8)
        lateral = np.exp(-0.5 * (yr / max(target.sy, 0.5)) ** 2)
        sign = -1.0 if kind != "linear_positive" else 1.0
        return sign * abs(target.amplitude) * axial * lateral

    if kind in {"geology", "geological"}:
        return abs(target.amplitude) * _gaussian_rotated(xx, yy, target) * 0.55

    raise ValueError(f"Unknown synthetic target kind: {kind!r}")


def generate_scan(scenario: SyntheticScenario) -> tuple[ScanData, dict]:
    rng = np.random.default_rng(scenario.seed)
    x = np.linspace(0.0, scenario.width_m, scenario.nx)
    y = np.linspace(0.0, scenario.height_m, scenario.ny)
    yy, xx = np.meshgrid(y, x, indexing="ij")

    signal = 150.0 + scenario.gradient_x * xx + scenario.gradient_y * yy
    for target in scenario.targets:
        signal += _target_response(xx, yy, target)
    signal += rng.normal(0.0, scenario.noise_sigma, size=signal.shape)

    baseline_depth = 12.0
    influences = []
    for target in scenario.targets:
        influences.append(
            np.clip(
                np.abs(_target_response(xx, yy, target)) / max(abs(target.amplitude), 1e-6),
                0.0,
                1.0,
            )
        )
    total_influence = (
        np.sum(influences, axis=0) if influences else np.zeros(signal.shape, dtype=float)
    )
    background_weight = np.maximum(1.0 - total_influence, 0.0)
    depth_num = background_weight * baseline_depth
    depth_weight = background_weight.copy()
    for influence, target in zip(influences, scenario.targets, strict=True):
        depth_num += influence * float(target.depth)
        depth_weight += influence
    depth = depth_num / np.maximum(depth_weight, 1e-9)
    depth += rng.normal(0.0, scenario.depth_noise_sigma, size=signal.shape)

    scan = ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=depth.ravel(),
        signal=signal.ravel(),
        grid_i=np.tile(np.arange(scenario.nx, dtype=float), scenario.ny),
        grid_j=np.repeat(np.arange(scenario.ny, dtype=float), scenario.nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device="synthetic",
            field_length_m=scenario.width_m,
            field_width_m=scenario.height_m,
            notes=f"Synthetic scenario: {scenario.name}",
            source_file=f"synthetic:{scenario.name}",
            mineralization_pct=scenario.mineralization_pct,
        ),
    )
    truth = {
        "scenario": scenario.name,
        "width_m": scenario.width_m,
        "height_m": scenario.height_m,
        "targets": [asdict(t) for t in scenario.targets],
        "seed": scenario.seed,
        "mineralization_pct": scenario.mineralization_pct,
    }
    return scan, truth


def scenario_catalog() -> list[SyntheticScenario]:
    return [
        SyntheticScenario(
            name="positive_compact",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(SyntheticTarget("positive_compact", 8, 11, amplitude=18, sx=1.2, sy=1.2),),
            seed=1,
        ),
        SyntheticScenario(
            name="negative_cavity",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(SyntheticTarget("cavity", 21, 11, amplitude=16, sx=2.5, sy=2.5),),
            seed=2,
        ),
        SyntheticScenario(
            name="linear_tunnel",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(
                SyntheticTarget(
                    "tunnel", 15, 10, amplitude=13, sy=1.0, length=13, orientation_deg=0
                ),
            ),
            seed=3,
        ),
        SyntheticScenario(
            name="geological_broad",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(SyntheticTarget("geology", 18, 9, amplitude=12, sx=6, sy=5),),
            gradient_x=0.15,
            gradient_y=-0.05,
            seed=4,
        ),
        SyntheticScenario(
            name="mineralization_elevated",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(SyntheticTarget("positive_compact", 15, 10, amplitude=18, sx=1.2, sy=1.2),),
            mineralization_pct=45.0,
            noise_sigma=1.0,
            seed=11,
        ),
        SyntheticScenario(
            name="mineralization_high",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(SyntheticTarget("cavity", 16, 10, amplitude=17, sx=2.2, sy=2.0),),
            mineralization_pct=75.0,
            noise_sigma=1.0,
            seed=12,
        ),
        SyntheticScenario(
            name="no_target_noise",
            width_m=30,
            height_m=20,
            nx=31,
            ny=21,
            targets=(),
            gradient_x=0.0,
            gradient_y=0.0,
            noise_sigma=1.5,
            seed=5,
        ),
        SyntheticScenario(
            name="multiple_targets",
            width_m=40,
            height_m=30,
            nx=41,
            ny=31,
            targets=(
                SyntheticTarget("positive_compact", 9, 8, amplitude=20, sx=1.1, sy=1.3),
                SyntheticTarget("cavity", 27, 20, amplitude=16, sx=2.6, sy=2.0),
                SyntheticTarget(
                    "tunnel", 18, 12, amplitude=11, sy=0.8, length=12, orientation_deg=40
                ),
            ),
            noise_sigma=1.2,
            seed=6,
        ),
        SyntheticScenario(
            name="close_targets",
            width_m=30,
            height_m=24,
            nx=31,
            ny=25,
            targets=(
                SyntheticTarget(
                    "positive_compact", 10, 12, depth=3.5, amplitude=22, sx=1.0, sy=1.0
                ),
                SyntheticTarget("cavity", 14.5, 12, depth=6.0, amplitude=17, sx=2.0, sy=2.0),
            ),
            noise_sigma=1.0,
            seed=7,
        ),
        SyntheticScenario(
            name="overlapping_targets",
            width_m=32,
            height_m=26,
            nx=33,
            ny=27,
            targets=(
                SyntheticTarget(
                    "positive_compact", 13, 13, depth=3.0, amplitude=24, sx=1.6, sy=1.4
                ),
                SyntheticTarget("cavity", 15, 13.5, depth=7.0, amplitude=20, sx=2.4, sy=2.0),
            ),
            noise_sigma=1.4,
            seed=8,
        ),
        SyntheticScenario(
            name="rotated_tunnel",
            width_m=40,
            height_m=30,
            nx=41,
            ny=31,
            targets=(
                SyntheticTarget(
                    "tunnel", 20, 15, depth=8.0, amplitude=15, sy=0.9, length=16, orientation_deg=58
                ),
            ),
            noise_sigma=1.0,
            seed=9,
        ),
        SyntheticScenario(
            name="void_plus_geology",
            width_m=44,
            height_m=32,
            nx=45,
            ny=33,
            targets=(
                SyntheticTarget("geology", 22, 16, depth=10.0, amplitude=10, sx=8, sy=6),
                SyntheticTarget("cavity", 31, 18, depth=5.0, amplitude=16, sx=2.6, sy=2.2),
            ),
            gradient_x=0.08,
            gradient_y=-0.04,
            noise_sigma=1.3,
            seed=10,
        ),
    ]


def ladder_scenarios() -> list[SyntheticScenario]:
    """Deterministic depth/amplitude ladders for the science oracle.

    Same forward model as :func:`scenario_catalog` (fixed seeds 101/102);
    single compact target with one varied parameter so per-rung behavior
    is attributable. Additive fixture builder; changes no engine behavior.
    """
    cases = []
    for depth in (2.0, 6.0, 10.0):
        cases.append(
            SyntheticScenario(
                name=f"ladder_depth_{depth:g}",
                width_m=30,
                height_m=20,
                nx=31,
                ny=21,
                targets=(
                    SyntheticTarget(
                        "positive_compact",
                        15,
                        10,
                        depth=depth,
                        amplitude=18,
                        sx=1.2,
                        sy=1.2,
                    ),
                ),
                seed=101,
            )
        )
    for amplitude in (8.0, 14.0, 22.0):
        cases.append(
            SyntheticScenario(
                name=f"ladder_amp_{amplitude:g}",
                width_m=30,
                height_m=20,
                nx=31,
                ny=21,
                targets=(
                    SyntheticTarget(
                        "positive_compact",
                        15,
                        10,
                        depth=4.0,
                        amplitude=amplitude,
                        sx=1.2,
                        sy=1.2,
                    ),
                ),
                noise_sigma=1.0,
                seed=102,
            )
        )
    return cases


def write_truth(path: str | Path, truth: dict) -> None:
    Path(path).write_text(json.dumps(truth, indent=2), encoding="utf-8")

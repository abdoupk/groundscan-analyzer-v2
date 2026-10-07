"""Synthetic benchmark runner for regression testing and algorithm comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import hypot
from pathlib import Path

from ...services.config import AnalysisConfig
from ...services.single_scan import analyze_scan
from .core import SyntheticScenario, SyntheticTarget, generate_scan, scenario_catalog


@dataclass
class BenchmarkRow:
    scenario: str
    targets: int
    candidates: int
    matched_targets: int
    false_positives: int
    recall: float
    precision: float
    mean_center_error_m: float = float("nan")
    mean_depth_error_m: float = float("nan")
    depth_evaluable_matches: int = 0


def expected_patterns(target: SyntheticTarget) -> set[str]:
    if target.kind.startswith("positive"):
        # A positive target may now be represented as a material-agnostic
        # dipolar response after signed-lobe merging, or a conservative
        # linear-metal morphology refinement. These are benchmark compatibility
        # labels, not material claims.
        return {"metallic-like", "linear-metal-compatible", "dipolar-response"}
    if target.kind in {"cavity", "negative_cavity"}:
        return {"cavity-like"}
    if target.kind in {"tunnel", "linear_negative", "linear_positive"}:
        return {"tunnel-like"}
    if target.kind in {"geology", "geological"}:
        return {"geological-like"}
    return {"unknown"}


def evaluate(candidates, truth: dict, distance_tolerance_m: float = 3.0) -> BenchmarkRow:
    targets = truth["targets"]
    used = set()
    matched = 0
    for target in targets:
        candidates_for_type = [
            c
            for c in candidates
            if c.id not in used
            and c.pattern_hypothesis in expected_patterns(SyntheticTarget(**target))
        ]
        if not candidates_for_type:
            continue
        best = min(
            candidates_for_type,
            key=lambda c: hypot(c.x_center - target["x"], c.y_center - target["y"]),
        )
        if hypot(best.x_center - target["x"], best.y_center - target["y"]) <= distance_tolerance_m:
            matched += 1
            used.add(best.id)
    false_positives = max(0, len(candidates) - len(used))
    precision = matched / len(candidates) if candidates else (1.0 if not targets else 0.0)
    recall = matched / len(targets) if targets else (1.0 if not candidates else 0.0)
    matched_centers = []
    depth_errors = []
    for target in targets:
        candidates_for_type = [
            c
            for c in candidates
            if c.pattern_hypothesis in expected_patterns(SyntheticTarget(**target))
        ]
        if not candidates_for_type:
            continue
        best = min(
            candidates_for_type,
            key=lambda c: hypot(c.x_center - target["x"], c.y_center - target["y"]),
        )
        distance = hypot(best.x_center - target["x"], best.y_center - target["y"])
        if distance <= distance_tolerance_m:
            matched_centers.append(distance)
            depth_value = (
                best.depth_estimate
                if best.depth_estimate == best.depth_estimate
                else best.depth_mean
            )
            if depth_value == depth_value and "depth" in target:
                depth_errors.append(abs(depth_value - target["depth"]))
    return BenchmarkRow(
        truth["scenario"],
        len(targets),
        len(candidates),
        matched,
        false_positives,
        round(recall, 3),
        round(precision, 3),
        round(sum(matched_centers) / len(matched_centers), 3) if matched_centers else float("nan"),
        round(sum(depth_errors) / len(depth_errors), 3) if depth_errors else float("nan"),
        len(depth_errors),
    )


def run_benchmark(
    out_dir: str | Path, scenarios: list[SyntheticScenario] | None = None
) -> list[BenchmarkRow]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[BenchmarkRow] = []
    for scenario in scenarios or scenario_catalog():
        scan, truth = generate_scan(scenario)
        _, _, candidates = analyze_scan(
            scan, out_dir / scenario.name, label=scenario.name, config=AnalysisConfig()
        )
        row = evaluate(candidates, truth)
        rows.append(row)
        (out_dir / scenario.name / "ground_truth.json").write_text(
            json.dumps(truth, indent=2), encoding="utf-8"
        )

    payload = {"rows": [row.__dict__ for row in rows]}
    (out_dir / "synthetic_benchmark.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return rows


def parameterized_stress_scenarios(count: int = 128, seed: int = 2026) -> list[SyntheticScenario]:
    """Generate deterministic stress cases over noise, depth, size, orientation and separation."""
    import numpy as np

    rng = np.random.default_rng(seed)
    out: list[SyntheticScenario] = []
    kinds = ["positive_compact", "cavity", "tunnel", "geology"]
    for idx in range(int(count)):
        width, height = 40.0, 30.0
        nx = int(rng.choice([31, 41, 51, 61]))
        ny = max(25, int(round(nx * height / width)))
        kind = str(rng.choice(kinds))
        depth = float(rng.uniform(2.5, 11.0))
        amplitude = float(rng.uniform(7.0, 24.0))
        noise = float(rng.uniform(0.4, 2.3))
        angle = float(rng.uniform(0.0, 180.0))
        x = float(rng.uniform(7.0, width - 7.0))
        y = float(rng.uniform(6.0, height - 6.0))
        if kind == "tunnel":
            sx, sy, length = (
                float(rng.uniform(0.8, 2.0)),
                float(rng.uniform(0.65, 1.4)),
                float(rng.uniform(7.0, 18.0)),
            )
            target = SyntheticTarget(
                kind,
                x,
                y,
                depth=depth,
                amplitude=amplitude,
                sx=sx,
                sy=sy,
                length=length,
                orientation_deg=angle,
            )
        elif kind == "geology":
            sx, sy = float(rng.uniform(4.5, 10.0)), float(rng.uniform(3.5, 8.0))
            target = SyntheticTarget(
                kind,
                x,
                y,
                depth=depth,
                amplitude=min(amplitude, 15.0),
                sx=sx,
                sy=sy,
                orientation_deg=angle,
            )
        else:
            sx = float(rng.uniform(0.9, 3.5))
            sy = float(rng.uniform(0.9, 3.5))
            target = SyntheticTarget(
                kind, x, y, depth=depth, amplitude=amplitude, sx=sx, sy=sy, orientation_deg=angle
            )

        targets = [target]
        if idx % 4 == 0:
            # Hard multi-target case; keep targets near enough to challenge separation
            # but away from deterministic grid boundaries.
            x2 = float(np.clip(x + rng.uniform(3.0, 9.0), 6.0, width - 6.0))
            y2 = float(np.clip(y + rng.uniform(-6.0, 6.0), 5.0, height - 5.0))
            kind2 = str(rng.choice(["positive_compact", "cavity", "tunnel"]))
            targets.append(
                SyntheticTarget(
                    kind2,
                    x2,
                    y2,
                    depth=float(rng.uniform(3.0, 10.0)),
                    amplitude=float(rng.uniform(9.0, 20.0)),
                    sx=float(rng.uniform(1.0, 2.8)),
                    sy=float(rng.uniform(0.8, 2.5)),
                    length=float(rng.uniform(8.0, 15.0)),
                    orientation_deg=float(rng.uniform(0.0, 180.0)),
                )
            )
        out.append(
            SyntheticScenario(
                name=f"stress_{idx:03d}",
                width_m=width,
                height_m=height,
                nx=nx,
                ny=ny,
                targets=tuple(targets),
                noise_sigma=noise,
                gradient_x=float(rng.uniform(-0.12, 0.12)),
                gradient_y=float(rng.uniform(-0.10, 0.10)),
                depth_noise_sigma=float(rng.uniform(0.02, 0.25)),
                seed=seed + idx,
            )
        )
    return out


def run_stress_benchmark(
    out_dir: str | Path, count: int = 128, seed: int = 2026
) -> list[BenchmarkRow]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[BenchmarkRow] = []
    for scenario in parameterized_stress_scenarios(count=count, seed=seed):
        scan, truth = generate_scan(scenario)
        _, _, candidates = analyze_scan(
            scan,
            out_dir,
            label=scenario.name,
            config=AnalysisConfig(),
            write_outputs=False,
        )
        rows.append(evaluate(candidates, truth))
    payload = {
        "count": len(rows),
        "seed": seed,
        "rows": [row.__dict__ for row in rows],
        "summary": {
            "mean_recall": round(sum(r.recall for r in rows) / max(len(rows), 1), 3),
            "mean_precision": round(sum(r.precision for r in rows) / max(len(rows), 1), 3),
            "mean_depth_error_m": round(
                sum(
                    r.mean_depth_error_m
                    for r in rows
                    if r.mean_depth_error_m == r.mean_depth_error_m
                )
                / max(sum(r.mean_depth_error_m == r.mean_depth_error_m for r in rows), 1),
                3,
            ),
        },
        "note": "synthetic software stress test only; not field validation and not a calibrated probability estimate",
    }
    (out_dir / "synthetic_stress_benchmark.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    return rows

"""Large stratified synthetic benchmark for v0.2.7.

This module evaluates detection, localization, depth estimation, target-count
separation and false-positive behavior on deterministic synthetic fixtures.
It deliberately reports software-validation metrics only; no field probability
or real-instrument accuracy is inferred.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import hypot
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from ...gates.screening import DEFAULT_SCREENING_POLICY, screen_candidates
from ...services.config import AnalysisConfig
from ...services.single_scan import analyze_scan
from .benchmark import expected_patterns
from .core import SyntheticScenario, SyntheticTarget, generate_scan


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    split: str
    family: str
    targets: int
    candidates: int
    matched_targets: int
    false_positives: int
    missed_targets: int
    oversegmentation: int
    undersegmentation: int
    exact_target_count: bool
    recall: float
    precision: float
    center_error_m: float
    depth_error_m: float
    depth_evaluable_matches: int
    mean_screening_score: float


@dataclass(frozen=True)
class AggregateMetrics:
    cases: int
    targets: int
    candidates: int
    matched_targets: int
    false_positives: int
    recall: float
    precision: float
    mean_center_error_m: float
    mean_depth_error_m: float
    depth_evaluable_matches: int
    exact_target_count_rate: float
    false_positive_case_rate: float
    mean_false_positives_per_case: float


def _safe_mean(values: Iterable[float]) -> float:
    """Backward-compat alias — canonical impl is groundscan._util.safe_mean."""
    from groundscan._util import safe_mean

    return safe_mean(values, default=float("nan"))


def _compatible(candidate, target: SyntheticTarget) -> bool:
    return candidate.pattern_hypothesis in expected_patterns(target)


def match_candidates(candidates, truth_targets: list[dict], distance_tolerance_m: float = 3.0):
    """One-to-one match candidates to truth using a global assignment."""
    n_t, n_c = len(truth_targets), len(candidates)
    if not n_t or not n_c:
        return [], set(), set()
    big = 1000.0
    cost = np.full((n_t, n_c), big, dtype=float)
    for i, target in enumerate(truth_targets):
        target_obj = SyntheticTarget(**target)
        for j, candidate in enumerate(candidates):
            if not _compatible(candidate, target_obj):
                continue
            d = hypot(candidate.x_center - target["x"], candidate.y_center - target["y"])
            if d <= distance_tolerance_m:
                # Small pattern bonus keeps the assignment deterministic when two
                # candidates are equally close.
                cost[i, j] = d
    rows, cols = linear_sum_assignment(cost)
    matches = []
    for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
        if cost[i, j] < big:
            matches.append((i, j, float(cost[i, j])))
    matched_targets = {i for i, _, _ in matches}
    matched_candidates = {j for _, j, _ in matches}
    return matches, matched_targets, matched_candidates


def evaluate_case(
    candidates,
    truth: dict,
    *,
    split: str,
    case_id: str,
    family: str,
    distance_tolerance_m: float = 3.0,
) -> CaseResult:
    targets = list(truth["targets"])
    matches, matched_targets, matched_candidates = match_candidates(
        candidates, targets, distance_tolerance_m
    )
    matched = len(matches)
    false_positives = max(0, len(candidates) - len(matched_candidates))
    missed = max(0, len(targets) - matched)
    count_delta = len(candidates) - len(targets)
    oversegmentation = max(0, count_delta)
    undersegmentation = max(0, -count_delta)
    exact_count = len(candidates) == len(targets)
    recall = matched / len(targets) if targets else (1.0 if not candidates else 0.0)
    precision = matched / len(candidates) if candidates else (1.0 if not targets else 0.0)
    center_errors = [d for _, _, d in matches]
    depth_errors = []
    for ti, ci, _ in matches:
        target = targets[ti]
        c = candidates[ci]
        depth_value = c.depth_estimate if np.isfinite(c.depth_estimate) else c.depth_mean
        if np.isfinite(depth_value) and "depth" in target:
            depth_errors.append(abs(float(depth_value) - float(target["depth"])))
    screening = [float(c.screening_score) for c in candidates if np.isfinite(c.screening_score)]
    return CaseResult(
        case_id=case_id,
        split=split,
        family=family,
        targets=len(targets),
        candidates=len(candidates),
        matched_targets=matched,
        false_positives=false_positives,
        missed_targets=missed,
        oversegmentation=oversegmentation,
        undersegmentation=undersegmentation,
        exact_target_count=exact_count,
        recall=round(recall, 4),
        precision=round(precision, 4),
        center_error_m=round(_safe_mean(center_errors), 4),
        depth_error_m=round(_safe_mean(depth_errors), 4),
        depth_evaluable_matches=len(depth_errors),
        mean_screening_score=round(_safe_mean(screening), 4),
    )


def aggregate(results: list[CaseResult]) -> AggregateMetrics:
    cases = len(results)
    targets = sum(r.targets for r in results)
    candidates = sum(r.candidates for r in results)
    matched = sum(r.matched_targets for r in results)
    fps = sum(r.false_positives for r in results)
    no_target = [r for r in results if r.targets == 0]
    exact = sum(1 for r in results if r.exact_target_count) / cases if cases else 0.0
    fp_case = sum(1 for r in no_target if r.candidates > 0) / len(no_target) if no_target else 0.0
    return AggregateMetrics(
        cases=cases,
        targets=targets,
        candidates=candidates,
        matched_targets=matched,
        false_positives=fps,
        recall=round(matched / targets if targets else 1.0, 4),
        precision=round(matched / candidates if candidates else (1.0 if not targets else 0.0), 4),
        mean_center_error_m=round(_safe_mean([r.center_error_m for r in results]), 4),
        mean_depth_error_m=round(_safe_mean([r.depth_error_m for r in results]), 4),
        depth_evaluable_matches=sum(r.depth_evaluable_matches for r in results),
        exact_target_count_rate=round(exact, 4),
        false_positive_case_rate=round(fp_case, 4),
        mean_false_positives_per_case=round(fps / cases if cases else 0.0, 4),
    )


def run_large_suite_informational(
    work_dir: str | Path, *, count: int = 240, seed: int = 2027
) -> dict:
    """Full-mode breadth for the science framework: large suite, coarse invariants.

    Per-family numbers are RECORDED, not floored: no per-family floors were
    frozen at this scale, and inventing them would be calibration. Only
    integrity failures (crash / non-finite output) gate, via the
    ``integrity_failures`` list; recorded family metrics never gate.
    Operating-point provenance is attached; the threshold is read from the
    production default policy, never redefined here.
    """
    import math as _math

    from .oracles import operating_point_record as _op_record

    out = Path(work_dir) / "large"
    out.mkdir(parents=True, exist_ok=True)
    config = AnalysisConfig()
    integrity_failures: list[str] = []
    by_family: dict[str, dict[str, int]] = {}
    case_count = 0
    for scenario, _split, family in generate_suite(count=count, seed=seed):
        case_count += 1
        try:
            scan, truth = generate_scan(scenario)
            _, _, candidates = analyze_scan(
                scan,
                out / scenario.name,
                label=scenario.name,
                config=config,
                write_outputs=False,
            )
            retained = screen_candidates(candidates, DEFAULT_SCREENING_POLICY)
            _matches, matched_targets, matched_candidates = match_candidates(
                retained, list(truth["targets"]), 3.0
            )
            nonfinite = sum(1 for c in retained if not _math.isfinite(float(c.evidence_score)))
            if nonfinite:
                integrity_failures.append(f"{scenario.name}: non-finite scores")
            agg = by_family.setdefault(
                family, {"targets": 0, "matched": 0, "cases": 0, "false_positives": 0}
            )
            agg["cases"] += 1
            agg["targets"] += len(truth["targets"])
            agg["matched"] += len(matched_targets)
            agg["false_positives"] += max(0, len(retained) - len(matched_candidates))
        except Exception as exc:  # noqa: BLE001 -- crashes are integrity failures
            integrity_failures.append(f"{scenario.name}: {type(exc).__name__}: {exc}")
    families: dict[str, dict[str, object]] = {}
    for family, agg in sorted(by_family.items()):
        targets = agg["targets"]
        recall = (agg["matched"] / targets) if targets else 1.0
        families[family] = {
            "gating": False,
            "synthetic_recall": round(recall, 4),
            "synthetic_false_positives": agg["false_positives"],
            "cases": agg["cases"],
            "floored": False,
        }
    return {
        "cases": case_count,
        "seed": seed,
        "gating": False,
        "families": families,
        "integrity_failures": integrity_failures,
        "status_note": "informational breadth: numbers recorded, only integrity failures gate",
        "operating_point": _op_record(),
    }


def _scenario_family(
    rng: np.random.Generator, idx: int, family: str, seed: int
) -> SyntheticScenario:
    width, height = 40.0, 30.0
    nx = int(rng.choice([31, 41, 51]))
    ny = max(25, int(round(nx * height / width)))
    noise = float(rng.choice([0.5, 1.0, 1.8, 2.5]))
    depth_noise = float(rng.choice([0.03, 0.08, 0.18, 0.30]))
    angle = float(rng.choice([0, 20, 45, 70, 90, 120, 150, 175]))
    depth = float(rng.choice([2.5, 4.5, 7.0, 9.5, 11.0]))
    amplitude = float(rng.choice([7.0, 10.0, 14.0, 18.0, 24.0]))
    gradient_x = float(rng.uniform(-0.16, 0.16))
    gradient_y = float(rng.uniform(-0.12, 0.12))
    x = float(rng.choice([2.5, 6.0, 10.0, 16.0, 22.0, 30.0, 37.0]))
    y = float(rng.choice([2.5, 6.0, 10.0, 16.0, 23.0, 28.0]))
    x = float(np.clip(x, 2.0, width - 2.0))
    y = float(np.clip(y, 2.0, height - 2.0))

    if family == "no_target":
        return SyntheticScenario(
            f"v027_{idx:04d}",
            width,
            height,
            nx,
            ny,
            (),
            noise_sigma=noise,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            depth_noise_sigma=depth_noise,
            seed=seed + idx,
        )
    if family == "positive_compact":
        target = SyntheticTarget(
            "positive_compact",
            x,
            y,
            depth=depth,
            amplitude=amplitude,
            sx=float(rng.choice([0.9, 1.3, 2.0, 3.0])),
            sy=float(rng.choice([0.9, 1.3, 2.0, 3.0])),
            orientation_deg=angle,
        )
        return SyntheticScenario(
            f"v027_{idx:04d}",
            width,
            height,
            nx,
            ny,
            (target,),
            noise_sigma=noise,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            depth_noise_sigma=depth_noise,
            seed=seed + idx,
        )
    if family == "cavity":
        target = SyntheticTarget(
            "cavity",
            x,
            y,
            depth=depth,
            amplitude=amplitude,
            sx=float(rng.choice([1.6, 2.5, 3.5, 5.0])),
            sy=float(rng.choice([1.6, 2.5, 3.5, 5.0])),
            orientation_deg=angle,
        )
        return SyntheticScenario(
            f"v027_{idx:04d}",
            width,
            height,
            nx,
            ny,
            (target,),
            noise_sigma=noise,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            depth_noise_sigma=depth_noise,
            seed=seed + idx,
        )
    if family == "tunnel":
        target = SyntheticTarget(
            "tunnel",
            x,
            y,
            depth=depth,
            amplitude=amplitude,
            sy=float(rng.choice([0.65, 0.9, 1.2, 1.6])),
            length=float(rng.choice([7, 10, 14, 18])),
            orientation_deg=angle,
        )
        return SyntheticScenario(
            f"v027_{idx:04d}",
            width,
            height,
            nx,
            ny,
            (target,),
            noise_sigma=noise,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            depth_noise_sigma=depth_noise,
            seed=seed + idx,
        )
    if family == "geology":
        target = SyntheticTarget(
            "geology",
            x,
            y,
            depth=depth,
            amplitude=min(amplitude, 15.0),
            sx=float(rng.choice([4.5, 6.0, 8.0, 10.0])),
            sy=float(rng.choice([3.5, 5.0, 7.0, 9.0])),
            orientation_deg=angle,
        )
        return SyntheticScenario(
            f"v027_{idx:04d}",
            width,
            height,
            nx,
            ny,
            (target,),
            noise_sigma=noise,
            gradient_x=gradient_x,
            gradient_y=gradient_y,
            depth_noise_sigma=depth_noise,
            seed=seed + idx,
        )

    # mixed_multi: two or three targets, deliberately including close cases.
    t1 = SyntheticTarget(
        str(rng.choice(["positive_compact", "cavity", "tunnel"])),
        x,
        y,
        depth=depth,
        amplitude=max(9.0, amplitude),
        sx=float(rng.choice([1.0, 1.5, 2.5])),
        sy=float(rng.choice([0.8, 1.2, 2.0])),
        length=float(rng.choice([8, 12, 16])),
        orientation_deg=angle,
    )
    separation = float(rng.choice([2.5, 4.0, 6.0, 8.0]))
    theta = np.radians(float(rng.choice([0, 45, 90, 135])))
    x2 = float(np.clip(x + separation * np.cos(theta), 3.0, width - 3.0))
    y2 = float(np.clip(y + separation * np.sin(theta), 3.0, height - 3.0))
    k2 = str(rng.choice(["positive_compact", "cavity", "tunnel"]))
    t2 = SyntheticTarget(
        k2,
        x2,
        y2,
        depth=float(rng.choice([3.0, 6.0, 9.0])),
        amplitude=float(rng.choice([9.0, 14.0, 20.0])),
        sx=float(rng.choice([1.0, 1.8, 2.6])),
        sy=float(rng.choice([0.9, 1.5, 2.2])),
        length=float(rng.choice([8, 12, 15])),
        orientation_deg=float(rng.choice([0, 30, 60, 90, 120, 150])),
    )
    targets = [t1, t2]
    if idx % 3 == 0:
        t3 = SyntheticTarget(
            str(rng.choice(["positive_compact", "cavity"])),
            float(np.clip(x2 + 4.5, 4.0, width - 4.0)),
            float(np.clip(y2 - 3.5, 4.0, height - 4.0)),
            depth=float(rng.choice([3.5, 7.0, 10.0])),
            amplitude=float(rng.choice([10.0, 16.0])),
            sx=1.4,
            sy=1.4,
        )
        targets.append(t3)
    return SyntheticScenario(
        f"v027_{idx:04d}",
        width,
        height,
        nx,
        ny,
        tuple(targets),
        noise_sigma=noise,
        gradient_x=gradient_x,
        gradient_y=gradient_y,
        depth_noise_sigma=depth_noise,
        seed=seed + idx,
    )


def generate_suite(count: int = 240, seed: int = 2027) -> list[tuple[SyntheticScenario, str, str]]:
    """Return a stratified deterministic benchmark suite and split labels."""
    count = int(count)
    if count < 12:
        raise ValueError("count must be >= 12")
    families = ["positive_compact", "cavity", "tunnel", "geology", "no_target", "mixed_multi"]
    base = count // len(families)
    remainder = count % len(families)
    suite = []
    idx = 0
    for fi, family in enumerate(families):
        n = base + (1 if fi < remainder else 0)
        for _ in range(n):
            split = "calibration" if idx % 5 < 3 else "holdout"
            suite.append((
                _scenario_family(np.random.default_rng(seed + idx * 97 + fi), idx, family, seed),
                split,
                family,
            ))
            idx += 1
    return suite


def _bootstrap_ci(
    results: list[CaseResult], metric: str, seed: int = 7, n_boot: int = 400
) -> tuple[float, float]:
    if not results:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    samples = []
    n = len(results)
    for _ in range(int(n_boot)):
        sampled = [results[i] for i in rng.integers(0, n, size=n)]
        agg = aggregate(sampled)
        samples.append(float(getattr(agg, metric)))
    return (
        round(float(np.percentile(samples, 2.5)), 4),
        round(float(np.percentile(samples, 97.5)), 4),
    )


def _threshold_metrics(results_by_threshold: dict[float, list[CaseResult]]) -> dict[str, dict]:
    output = {}
    for threshold, rows in results_by_threshold.items():
        agg = aggregate(rows)
        f1 = (
            (2 * agg.precision * agg.recall / (agg.precision + agg.recall))
            if agg.precision + agg.recall
            else 0.0
        )
        output[str(threshold)] = {"aggregate": asdict(agg), "f1": round(f1, 4)}
    return output


def _screen_results(candidates, truth, split, case_id, family, threshold):
    # v0.2.38 applies the calibrated soft-rescue policy at the standard 0.70
    # operating point. Other thresholds remain direct sensitivity points.
    if abs(float(threshold) - DEFAULT_SCREENING_POLICY.primary_threshold) < 1e-9:
        selected = screen_candidates(candidates, DEFAULT_SCREENING_POLICY)
    else:
        selected = [c for c in candidates if c.screening_score >= threshold]
    return evaluate_case(selected, truth, split=split, case_id=case_id, family=family)


def run_large_benchmark(
    out_dir: str | Path,
    *,
    count: int = 240,
    seed: int = 2027,
    thresholds: tuple[float, ...] = (0.40, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80),
    bootstrap: int = 400,
) -> dict:
    """Run calibration/holdout benchmark and write a complete JSON report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suite = generate_suite(count=count, seed=seed)
    raw_results: list[CaseResult] = []
    calibration_by_threshold = {float(t): [] for t in thresholds}
    holdout_by_threshold = {float(t): [] for t in thresholds}
    family_results: dict[str, list[CaseResult]] = {}
    for scenario, split, family in suite:
        scan, truth = generate_scan(scenario)
        _, _, candidates = analyze_scan(
            scan,
            out_dir / "runs",
            label=scenario.name,
            config=AnalysisConfig(),
            write_outputs=False,
        )
        result = evaluate_case(candidates, truth, split=split, case_id=scenario.name, family=family)
        raw_results.append(result)
        family_results.setdefault(family, []).append(result)
        for threshold in thresholds:
            screened = _screen_results(candidates, truth, split, scenario.name, family, threshold)
            (calibration_by_threshold if split == "calibration" else holdout_by_threshold)[
                float(threshold)
            ].append(screened)

    calibration_report = _threshold_metrics(calibration_by_threshold)
    best_threshold = max(
        thresholds,
        key=lambda t: (
            calibration_report[str(float(t))]["f1"],
            calibration_report[str(float(t))]["aggregate"]["precision"],
            -float(t),
        ),
    )
    holdout_results = holdout_by_threshold[float(best_threshold)]
    selected_holdout = aggregate(holdout_results)
    raw_all = aggregate(raw_results)
    calibration_raw = aggregate([r for r in raw_results if r.split == "calibration"])
    holdout_raw = aggregate([r for r in raw_results if r.split == "holdout"])
    ci_recall = _bootstrap_ci(
        [r for r in raw_results if r.split == "holdout"], "recall", seed=seed + 11, n_boot=bootstrap
    )
    ci_precision = _bootstrap_ci(
        [r for r in raw_results if r.split == "holdout"],
        "precision",
        seed=seed + 13,
        n_boot=bootstrap,
    )
    family_summary = {
        family: asdict(aggregate(rows)) for family, rows in sorted(family_results.items())
    }
    payload = {
        "benchmark": "large_stratified_synthetic",
        "count": len(suite),
        "seed": seed,
        "split_rule": "3/5 calibration, 2/5 holdout, deterministic by case index",
        "families": sorted(family_results),
        "raw": {
            "all": asdict(raw_all),
            "calibration": asdict(calibration_raw),
            "holdout": asdict(holdout_raw),
        },
        "calibration": {
            "thresholds": calibration_report,
            "selected_threshold": float(best_threshold),
        },
        "holdout_at_selected_threshold": asdict(selected_holdout),
        "holdout_bootstrap_95pct_ci": {
            "recall": ci_recall,
            "precision": ci_precision,
            "bootstrap_samples": int(bootstrap),
        },
        "family_summary_raw": family_summary,
        "cases": [asdict(r) for r in raw_results],
        "interpretation": {
            "synthetic_only": True,
            "not_field_validation": True,
            "not_material_probability": True,
            "screening_score_is_heuristic": True,
            "recommended_use": "software regression, stress testing, threshold sensitivity and failure-mode discovery",
        },
    }
    (out_dir / "benchmark_large.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    (out_dir / "benchmark_large_summary.md").write_text(
        _markdown_summary(payload), encoding="utf-8"
    )
    return payload


def _markdown_summary(payload: dict) -> str:
    raw = payload["raw"]["all"]
    cal = payload["calibration"]
    ho = payload["holdout_at_selected_threshold"]
    ci = payload["holdout_bootstrap_95pct_ci"]
    lines = [
        "# GroundScan Analyzer v0.2.7 — Large Synthetic Benchmark",
        "",
        "> Synthetic software validation only. These results do not establish field accuracy or a probability of material/void/tunnel presence.",
        "",
        f"Cases: **{payload['count']}**; calibration/holdout split: **{payload['split_rule']}**; seed: **{payload['seed']}**.",
        "",
        "## Raw results",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall | {raw['recall']:.3f} |",
        f"| Precision | {raw['precision']:.3f} |",
        f"| Mean center error | {raw['mean_center_error_m']:.3f} m |",
        f"| Mean depth error | {raw['mean_depth_error_m']:.3f} m |",
        f"| Exact target count | {raw['exact_target_count_rate']:.3f} |",
        f"| No-target false-positive case rate | {raw['false_positive_case_rate']:.3f} |",
        "",
        "## Calibration",
        "",
        f"Selected synthetic operating threshold: **{cal['selected_threshold']:.2f}** (max F1 on calibration split only).",
        "",
        "## Holdout at selected threshold",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall | {ho['recall']:.3f} |",
        f"| Precision | {ho['precision']:.3f} |",
        f"| Mean center error | {ho['mean_center_error_m']:.3f} m |",
        f"| Mean depth error | {ho['mean_depth_error_m']:.3f} m |",
        f"| Exact target count | {ho['exact_target_count_rate']:.3f} |",
        f"| No-target false-positive case rate | {ho['false_positive_case_rate']:.3f} |",
        f"| Bootstrap 95% recall CI | {ci['recall'][0]:.3f} – {ci['recall'][1]:.3f} |",
        f"| Bootstrap 95% precision CI | {ci['precision'][0]:.3f} – {ci['precision'][1]:.3f} |",
        "",
        "## Families",
        "",
        "| Family | Recall | Precision | Center error | Depth error | FP case rate | Exact count |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for family, row in payload["family_summary_raw"].items():
        lines.append(
            f"| {family} | {row['recall']:.3f} | {row['precision']:.3f} | {row['mean_center_error_m']:.3f} | {row['mean_depth_error_m']:.3f} | {row['false_positive_case_rate']:.3f} | {row['exact_target_count_rate']:.3f} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Threshold selection is done on the calibration subset only.",
        "- Holdout metrics are kept separate to expose overfitting of a synthetic operating point.",
        "- Matching is one-to-one and uses global assignment with pattern compatibility plus a distance tolerance.",
        "- Synthetic targets are forward-model fixtures and are not a proxy for any specific detector's physical response.",
    ]
    return "\n".join(lines) + "\n"

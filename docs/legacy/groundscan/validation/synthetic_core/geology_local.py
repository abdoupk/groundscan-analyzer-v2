"""Deterministic geology-vs-local stress diagnostics for v0.2.55.

This suite characterizes whether a geology target is:
1. correctly localized and classified,
2. localized but assigned a non-geology label, or
3. not represented by a candidate near the truth location.

It does not alter detector thresholds, soil corrections, physical inversion,
or production scoring. Synthetic results are software diagnostics only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ...api import AnalysisConfig, analyze
from ...core.artifact import detect_artifacts
from ...core.classify import apply_local_geology_context
from ...diagnostics.dipole import (
    deblend_spatially_separated_multitarget_pairs,
    merge_dipolar_response_components,
)
from ...gates.quality import assess_candidate_quality
from ...models import ScanData
from ...site.analyze_site import ScanObservation, fuse_site_candidates
from ...site.consensus import _consensus_maps
from ...site.separation import resolve_dipole_pairs, separate_fused_candidates
from .benchmark_large import evaluate_case, expected_patterns
from .core import SyntheticScenario, SyntheticTarget, generate_scan
from .multiscan_benchmark import _identity_alignment

FAMILIES = ("geology_only", "geo_positive", "geo_cavity", "geo_tunnel", "geo_edge", "geo_overlap")


@dataclass(frozen=True)
class StressCaseResult:
    case_id: str
    family: str
    target_kinds: list[str]
    single: dict
    multi: dict
    target_diagnostics: list[dict]
    local_geology_rescues: int


def _make_scenario(i: int, family: str, rng: np.random.Generator) -> SyntheticScenario:
    width, height = 40.0, 30.0
    nx = int(rng.choice([31, 41, 51]))
    ny = int(rng.choice([25, 31]))
    noise = float(rng.choice([0.5, 1.0, 1.8, 2.5]))
    gradx = float(rng.uniform(-0.2, 0.2))
    grady = float(rng.uniform(-0.15, 0.15))
    depth = float(rng.choice([3.0, 5.0, 7.5, 10.0]))
    amp = float(rng.choice([7.0, 9.0, 11.0, 14.0, 18.0]))
    sx = float(rng.choice([4.0, 5.5, 7.0, 9.0, 11.0]))
    sy = float(rng.choice([3.0, 5.0, 6.5, 9.0]))
    geology = SyntheticTarget(
        "geology",
        20 + rng.uniform(-2, 2),
        15 + rng.uniform(-1.5, 1.5),
        depth=10.0,
        amplitude=amp,
        sx=sx,
        sy=sy,
    )

    if family == "geology_only":
        targets = (geology,)
    elif family == "geo_positive":
        x = float(np.clip(geology.x + rng.uniform(-10, 10), 2, 38))
        y = float(np.clip(geology.y + rng.uniform(-7, 7), 2, 28))
        targets = (
            geology,
            SyntheticTarget(
                "positive_compact",
                x,
                y,
                depth=depth,
                amplitude=float(rng.choice([12, 18, 24])),
                sx=float(rng.choice([0.9, 1.3, 2.0, 3.0])),
                sy=float(rng.choice([0.9, 1.3, 2.0, 3.0])),
            ),
        )
    elif family == "geo_cavity":
        x = float(np.clip(geology.x + rng.uniform(-10, 10), 2, 38))
        y = float(np.clip(geology.y + rng.uniform(-7, 7), 2, 28))
        targets = (
            geology,
            SyntheticTarget(
                "cavity",
                x,
                y,
                depth=float(rng.choice([3.5, 5.0, 7.0, 9.0])),
                amplitude=17.0,
                sx=float(rng.choice([1.8, 2.3, 2.8, 3.4])),
                sy=float(rng.choice([1.8, 2.3, 2.8, 3.4])),
            ),
        )
    elif family == "geo_tunnel":
        targets = (
            geology,
            SyntheticTarget(
                "tunnel",
                float(np.clip(geology.x + rng.uniform(-9, 9), 6, 34)),
                float(np.clip(geology.y + rng.uniform(-7, 7), 6, 24)),
                depth=6.0,
                amplitude=12.0,
                sy=0.9,
                length=float(rng.choice([9, 13, 17])),
                orientation_deg=float(rng.choice([0, 35, 70, 90, 125, 160])),
            ),
        )
    elif family == "geo_edge":
        targets = (
            SyntheticTarget(
                "geology",
                11 + rng.uniform(-3, 3),
                15 + rng.uniform(-4, 4),
                depth=10.0,
                amplitude=amp,
                sx=sx,
                sy=sy,
            ),
            SyntheticTarget(
                "positive_compact",
                3 + rng.uniform(-0.5, 1.5),
                15 + rng.uniform(-2, 2),
                depth=depth,
                amplitude=18.0,
                sx=1.4,
                sy=1.4,
            ),
        )
    elif family == "geo_overlap":
        x = float(np.clip(geology.x + rng.uniform(-3, 3), 6, 34))
        y = float(np.clip(geology.y + rng.uniform(-2.5, 2.5), 6, 24))
        targets = (
            geology,
            SyntheticTarget("positive_compact", x, y, depth=depth, amplitude=16.0, sx=1.8, sy=1.6),
        )
    else:
        raise ValueError(family)

    return SyntheticScenario(
        name=f"geo_{i:03d}_{family}",
        width_m=width,
        height_m=height,
        nx=nx,
        ny=ny,
        targets=tuple(targets),
        noise_sigma=noise,
        gradient_x=gradx,
        gradient_y=grady,
        depth_noise_sigma=float(rng.choice([0.04, 0.08, 0.16])),
        seed=100000 + i,
    )


def _clone_scan(scan: ScanData, rng: np.random.Generator, gain: float, noise: float) -> ScanData:
    signal = np.asarray(scan.signal, dtype=float).copy()
    baseline = float(np.median(signal))
    signal = baseline + gain * (signal - baseline)
    if noise:
        signal += rng.normal(0.0, noise, size=signal.shape)
    return ScanData(
        x=scan.x.copy(),
        y=scan.y.copy(),
        z=scan.z.copy(),
        signal=signal,
        twt_ns=None if scan.twt_ns is None else scan.twt_ns.copy(),
        grid_i=None if scan.grid_i is None else scan.grid_i.copy(),
        grid_j=None if scan.grid_j is None else scan.grid_j.copy(),
        latitude=None if scan.latitude is None else scan.latitude.copy(),
        longitude=None if scan.longitude is None else scan.longitude.copy(),
        coords_are_index_only=scan.coords_are_index_only,
        metadata=scan.metadata,
    )


def _fuse(spec: SyntheticScenario, case_index: int, out_dir: Path, family: str):
    base_scan, truth = generate_scan(spec)
    observations = []
    for j in range(3):
        scan = _clone_scan(
            base_scan,
            np.random.default_rng(500000 + case_index * 31 + j),
            [1.0, 0.96, 1.04][j],
            [0.0, 0.3, 0.6][j],
        )
        result = analyze(
            scan,
            out_dir / "scratch" / spec.name / str(j),
            label=f"s{j + 1}",
            config=AnalysisConfig(),
            write_outputs=False,
        )
        observations.append(
            ScanObservation(
                f"s{j + 1}",
                scan,
                result.grid,
                result.anomaly,
                detect_artifacts(result.grid, result.anomaly),
                result.candidates,
            )
        )

    single = evaluate_case(
        observations[0].candidates, truth, split="all", case_id=spec.name, family=spec.name
    )
    reference = observations[0]
    alignments = {
        obs.label: _identity_alignment(reference.anomaly, obs.anomaly, 24)
        for obs in observations[1:]
    }
    support, signed, persistence, positive, negative = _consensus_maps(
        observations, alignments, reference, 24, 3.0
    )
    fused = fuse_site_candidates(observations, reference, alignments, 0.06, support, persistence)
    fused, _ = separate_fused_candidates(
        fused,
        support,
        signed,
        reference.grid.x_centers,
        reference.grid.y_centers,
        positive_channel=positive,
        negative_channel=negative,
        persistence_map=persistence,
        anomaly_threshold=3.0,
    )
    fused = [assess_candidate_quality(c) for c in fused]
    fused = [c for c in fused if int(getattr(c, "scan_count", 1)) >= 2]
    fused = deblend_spatially_separated_multitarget_pairs(fused)
    fused = resolve_dipole_pairs(fused)
    fused = merge_dipolar_response_components(fused)
    before_methods = [c.classification_method for c in fused]
    fused = [apply_local_geology_context(c) for c in fused]
    rescues = sum(
        1
        for before, after in zip(before_methods, fused, strict=True)
        if after.classification_method == "local-geology-context"
        and before != after.classification_method
    )
    multi = evaluate_case(fused, truth, split="all", case_id=spec.name, family=spec.name)

    diagnostics = []
    for ti, target in enumerate(spec.targets):
        compatible = expected_patterns(target)
        any_near = []
        compatible_near = []
        for ci, candidate in enumerate(fused):
            distance = float(np.hypot(candidate.x_center - target.x, candidate.y_center - target.y))
            if distance <= 3.0:
                row = {
                    "candidate_index": ci,
                    "distance_m": round(distance, 4),
                    "pattern": candidate.pattern_hypothesis,
                    "method": candidate.classification_method,
                    "anomaly_score": round(float(candidate.anomaly_score), 4),
                    "broadness": round(float(candidate.broadness_score), 4),
                    "linearity": round(float(candidate.linearity_score), 4),
                }
                any_near.append(row)
                if candidate.pattern_hypothesis in compatible:
                    compatible_near.append(row)
        if compatible_near:
            status = "correct_match"
        elif any_near:
            status = "localized_wrong_pattern"
        else:
            status = "no_near_candidate"
        diagnostics.append({
            "target_index": ti,
            "kind": target.kind,
            "x": target.x,
            "y": target.y,
            "status": status,
            "compatible_patterns": sorted(compatible),
            "near_candidates": any_near,
        })
    return StressCaseResult(
        spec.name,
        family,
        [t.kind for t in spec.targets],
        asdict(single),
        asdict(multi),
        diagnostics,
        rescues,
    )


def run_geology_local_benchmark(
    out_dir: str | Path, *, count_per_family: int = 8, seed: int = 2028
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows = []
    for i, family in enumerate(
        family_name for _ in range(count_per_family) for family_name in FAMILIES
    ):
        rows.append(asdict(_fuse(_make_scenario(i, family, rng), i, out_dir, family)))

    def aggregate(rows_subset):
        targets = sum(len(r["target_kinds"]) for r in rows_subset)
        matched = sum(r["multi"]["matched_targets"] for r in rows_subset)
        candidates = sum(r["multi"]["candidates"] for r in rows_subset)
        statuses = {"correct_match": 0, "localized_wrong_pattern": 0, "no_near_candidate": 0}
        for row in rows_subset:
            for d in row["target_diagnostics"]:
                statuses[d["status"]] += 1
        return {
            "sites": len(rows_subset),
            "targets": targets,
            "matched_targets": matched,
            "candidates": candidates,
            "recall": round(matched / targets, 4) if targets else 1.0,
            "precision": round(matched / candidates, 4) if candidates else 0.0,
            "target_status": statuses,
        }

    families = {
        family: aggregate([r for r in rows if r["family"] == family]) for family in FAMILIES
    }
    wrong_pattern = {}
    no_candidate = {}
    for row in rows:
        for d in row["target_diagnostics"]:
            if d["kind"] != "geology":
                continue
            if d["status"] == "localized_wrong_pattern":
                nearest = min(d["near_candidates"], key=lambda x: x["distance_m"])
                wrong_pattern[nearest["pattern"]] = wrong_pattern.get(nearest["pattern"], 0) + 1
            elif d["status"] == "no_near_candidate":
                no_candidate[row["family"]] = no_candidate.get(row["family"], 0) + 1
    failure_analysis = {
        "localized_wrong_pattern_by_label": dict(
            sorted(wrong_pattern.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "no_near_candidate_by_family": dict(
            sorted(no_candidate.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "production_change_applied": False,
        "next_action": "separate classification conflicts from candidate-extraction misses before any threshold or scoring change",
    }
    result = {
        "benchmark": "geology_local_failure_diagnostics",
        "seed": seed,
        "count_per_family": count_per_family,
        "aggregate": aggregate(rows),
        "families": families,
        "local_geology_rescue_count": sum(r["local_geology_rescues"] for r in rows),
        "failure_analysis": failure_analysis,
        "cases": rows,
        "guardrails": {
            "synthetic_only": True,
            "not_field_validation": True,
            "detector_unchanged": True,
            "thresholds_unchanged": True,
            "soil_corrections_unchanged": True,
            "classification_behavior_changed": False,
            "purpose": "classify failure modes before production behavior changes",
        },
    }
    (out_dir / "geology_local_stress.json").write_text(
        json.dumps(result, indent=2, allow_nan=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.56 — Geological/Local Failure Diagnostics",
        "",
        "> Synthetic software diagnostics only; not field validation.",
        "",
        "| Family | Recall | Precision | Correct | Wrong pattern | No near candidate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family in FAMILIES:
        a = families[family]
        s = a["target_status"]
        lines.append(
            f"| {family} | {a['recall']:.4f} | {a['precision']:.4f} | {s['correct_match']} | {s['localized_wrong_pattern']} | {s['no_near_candidate']} |"
        )
    a = result["aggregate"]
    s = a["target_status"]
    lines += [
        "",
        f"Overall recall: **{a['recall']:.4f}**; precision: **{a['precision']:.4f}**.",
        f"Correctly classified targets: **{s['correct_match']}**; localized with wrong pattern: **{s['localized_wrong_pattern']}**; no nearby candidate: **{s['no_near_candidate']}**.",
        f"v0.2.56 baseline rescue activations in this suite: **{result['local_geology_rescue_count']}**.",
        "",
        "## Failure-mode split",
        "",
        "### Localized but wrong label",
        "",
    ]
    for label, count in failure_analysis["localized_wrong_pattern_by_label"].items():
        lines.append(f"- `{label}`: **{count}**")
    lines += ["", "### No nearby candidate"]
    for family, count in failure_analysis["no_near_candidate_by_family"].items():
        lines.append(f"- `{family}`: **{count}**")
    lines += [
        "",
        "## Interpretation",
        "",
        "The suite separates extraction failures from classification failures. No production detector, threshold, soil correction, or classification rule was changed in v0.2.56. The next engineering task is to test extraction/background behavior for `no_near_candidate` cases and classification evidence for `localized_wrong_pattern` cases separately.",
        "",
    ]
    (out_dir / "geology_local_failure_diagnostics.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return result

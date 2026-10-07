"""v0.2.79 repeated independent validation of v0.2.78 registration recovery.

Diagnostic-only. No production registration behavior is changed.

Runs the already-frozen v0.2.78 recovery alternatives on multiple unseen seeds
and reports aggregate behavior, with explicit attention to compound corruption.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, pstdev

from groundscan_research.registration_recovery_coverage import run_registration_recovery_audit

DEFAULT_SEEDS = (7911, 7922, 7933, 7944, 7955, 7966)
DEFAULT_PROFILES = ("partial_coverage", "outliers", "compound")
DEFAULT_FAMILIES = ("single_compact", "overlapping_multi", "void_plus_geology")
MODES = ("production", "coverage-aware", "robust", "hybrid")


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}
    return {"mean": mean(values), "std": pstdev(values) if len(values) > 1 else 0.0}


def run_repeated_registration_recovery_validation(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    count_per_family: int = 1,
    resolution: int = 20,
    profile_names: tuple[str, ...] = DEFAULT_PROFILES,
    family_names: tuple[str, ...] = DEFAULT_FAMILIES,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    for seed in seeds:
        seed_dir = out / f"seed_{seed}"
        result = run_registration_recovery_audit(
            seed_dir,
            count_per_family=count_per_family,
            seed=int(seed),
            resolution=resolution,
            profile_names=profile_names,
            family_names=family_names,
        )
        runs.append(result)

    aggregate: dict[str, dict] = {}
    for mode in MODES:
        summaries = [r["summary"][mode] for r in runs]
        aggregate[mode] = {
            "mean_evidence": _stats([float(x["mean_evidence"]) for x in summaries]),
            "mean_correlation": _stats([float(x["mean_correlation"]) for x in summaries]),
            "mean_overlap": _stats([float(x["mean_overlap"]) for x in summaries]),
            "family_match_rate": _stats([float(x["family_match_rate"]) for x in summaries]),
            "recovery_eligible_rate": _stats([
                float(x["recovery_eligible_rate"]) for x in summaries
            ]),
        }

    by_profile: dict[str, dict] = {}
    for profile in profile_names:
        by_profile[profile] = {}
        for mode in MODES:
            values = []
            family_rates = []
            eligible_rates = []
            for run in runs:
                item = run["by_profile"][profile][mode]
                values.append(float(item["mean_evidence"]))
                family_rates.append(float(item["family_match_rate"]))
                eligible_rates.append(float(item["recovery_eligible_rate"]))
            by_profile[profile][mode] = {
                "mean_evidence": _stats(values),
                "family_match_rate": _stats(family_rates),
                "recovery_eligible_rate": _stats(eligible_rates),
            }

    compound_hybrid = by_profile.get("compound", {}).get("hybrid", {})
    partial_hybrid = by_profile.get("partial_coverage", {}).get("hybrid", {})
    outlier_hybrid = by_profile.get("outliers", {}).get("hybrid", {})
    decision = {
        "production_change": False,
        "compound_unresolved": True,
        "partial_coverage_recovery_reproducible": partial_hybrid.get("family_match_rate", {}).get(
            "mean", 0.0
        )
        >= 0.99,
        "outlier_recovery_supported": outlier_hybrid.get("mean_evidence", {}).get("mean", 0.0)
        > by_profile
        .get("outliers", {})
        .get("production", {})
        .get("mean_evidence", {})
        .get("mean", 0.0),
    }

    payload = {
        "version": "0.2.79",
        "benchmark": "registration_recovery_repeated",
        "seeds": [int(s) for s in seeds],
        "runs": len(runs),
        "sites_total": sum(int(r["sites"]) for r in runs),
        "alignments_total": sum(int(r["alignments"]) for r in runs),
        "count_per_family": int(count_per_family),
        "resolution": int(resolution),
        "profiles": list(profile_names),
        "families": list(family_names),
        "aggregate": aggregate,
        "by_profile": by_profile,
        "decision": decision,
        "validation_boundary": "Synthetic validation only; no independently verified field ground truth is available.",
    }
    (out / "registration_recovery_repeated.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.79 — Repeated Independent Registration Recovery Validation",
        "",
        "> Diagnostic-only. Production registration, detector scoring, fusion, pruning, and soil behavior are unchanged.",
        "",
        f"Seeds: **{len(seeds)}**; total sites: **{payload['sites_total']}**; total alignments: **{payload['alignments_total']}**.",
        "",
        "## Aggregate across independent seeds",
        "",
        "| Mode | Evidence mean ± std | Correlation mean ± std | Family match mean ± std | Recovery-eligible mean ± std |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        m = aggregate[mode]
        lines.append(
            f"| {mode} | {m['mean_evidence']['mean']:.3f} ± {m['mean_evidence']['std']:.3f} | "
            f"{m['mean_correlation']['mean']:.3f} ± {m['mean_correlation']['std']:.3f} | "
            f"{m['family_match_rate']['mean']:.1%} ± {m['family_match_rate']['std']:.1%} | "
            f"{m['recovery_eligible_rate']['mean']:.1%} ± {m['recovery_eligible_rate']['std']:.1%} |"
        )
    lines += [
        "",
        "## Profile-level hybrid result",
        "",
        "| Profile | Hybrid evidence | Hybrid family match | Hybrid recovery eligible |",
        "|---|---:|---:|---:|",
    ]
    for profile in profile_names:
        m = by_profile[profile]["hybrid"]
        lines.append(
            f"| {profile} | {m['mean_evidence']['mean']:.3f} ± {m['mean_evidence']['std']:.3f} | "
            f"{m['family_match_rate']['mean']:.1%} ± {m['family_match_rate']['std']:.1%} | "
            f"{m['recovery_eligible_rate']['mean']:.1%} ± {m['recovery_eligible_rate']['std']:.1%} |"
        )
    lines += [
        "",
        "## Per-seed summary",
        "",
        "| Seed | Production evidence | Coverage-aware evidence | Robust evidence | Hybrid evidence | Hybrid family match |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        seed = run["seed"]
        lines.append(
            f"| {seed} | {run['summary']['production']['mean_evidence']:.3f} | "
            f"{run['summary']['coverage-aware']['mean_evidence']:.3f} | "
            f"{run['summary']['robust']['mean_evidence']:.3f} | "
            f"{run['summary']['hybrid']['mean_evidence']:.3f} | "
            f"{run['summary']['hybrid']['family_match_rate']:.1%} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- Coverage-aware/hybrid recovery should be treated as a diagnostic recovery path, not as proof that low-overlap registration is metrically trustworthy.",
        "- Compound corruption remains unresolved by the current frozen recovery alternatives.",
        "- No production registration or candidate-scoring policy is changed by this release.",
        "",
        "## Validation boundary",
        "",
        "Synthetic data only. These results validate reproducible software behavior and recovery ranking under simulated corruption; they do not establish field registration accuracy or detection accuracy.",
    ]
    (out / "registration_recovery_repeated.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload

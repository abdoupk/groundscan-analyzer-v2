"""Frozen OKM vendor-reference benchmark for GroundScan Analyzer.

The bundled nine CSV files are documented vendor examples.  Their expected
semantics are transcribed from the vendor notes in the CSV metadata.  They are
therefore a *documented vendor reference set*, not independently excavated or
field-verified ground truth.

The benchmark intentionally evaluates conservative pattern families rather
than material identity or exact underground geometry.  In particular, an iron
box/treasure example is evaluated as a metal-compatible response, not as proof
of gold or silver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from ..models import Candidate
from ..services.single_scan import analyze_scan, load_scan


@dataclass(frozen=True)
class VendorTruthCase:
    path: str
    split: str
    title: str
    target_present: bool
    required_any_patterns: tuple[str, ...] = ()
    min_pattern_counts: dict[str, int] = field(default_factory=dict)
    required_response_families: tuple[str, ...] = ()
    min_boundary_contact: float | None = None
    max_candidates: int | None = None
    min_candidates: int = 0
    required_hypothesis_support: tuple[tuple[str, float], ...] = ()
    paired_with: str | None = None
    pair_expectation: str | None = None
    provenance: str = "vendor-metadata-notes"


# The truth contract is derived only from the notes embedded in the nine CSVs.
# Keep this stable unless the source files or their documented answers change.
VENDOR_TRUTH: tuple[VendorTruthCase, ...] = (
    VendorTruthCase(
        path="train/Iron Treasure with Silver and Gold Coins.csv",
        split="train",
        title="Buried metal target / iron box",
        target_present=True,
        required_any_patterns=("dipolar-response", "metallic-like", "linear-metal-compatible"),
        required_response_families=("dipolar-response",),
        required_hypothesis_support=(("metallic-like", 0.50),),
    ),
    VendorTruthCase(
        path="train/Pipeline.csv",
        split="train",
        title="Metallic pipeline",
        target_present=True,
        required_any_patterns=("linear-metal-compatible",),
        min_pattern_counts={"linear-metal-compatible": 1},
        required_response_families=("linear-metal-response",),
    ),
    VendorTruthCase(
        path="train/Royal Tomb.csv",
        split="train",
        title="Tomb chamber / entrance structure",
        target_present=True,
        required_any_patterns=("cavity-like", "tunnel-like"),
    ),
    VendorTruthCase(
        path="train/Tunnel - Original Scan.csv",
        split="train",
        title="Tunnel / treasure-chamber access",
        target_present=True,
        required_any_patterns=("tunnel-like",),
        min_pattern_counts={"tunnel-like": 1},
        required_response_families=("linear-response",),
        paired_with="validation/Tunnel - Control Scan.csv",
        pair_expectation="shared tunnel-like pattern family",
    ),
    VendorTruthCase(
        path="validation/Anomaly at the Edge.csv",
        split="holdout",
        title="Incomplete boundary anomaly",
        target_present=True,
        required_any_patterns=("boundary-effect-like",),
        min_boundary_contact=0.80,
    ),
    VendorTruthCase(
        path="validation/Error Signal.csv",
        split="holdout",
        title="Instrument error signal / no object",
        target_present=False,
        max_candidates=0,
    ),
    VendorTruthCase(
        path="validation/Gallery and Tunnel.csv",
        split="holdout",
        title="Gallery and multiple tunnel structures",
        target_present=True,
        required_any_patterns=("tunnel-like",),
        min_pattern_counts={"tunnel-like": 2},
        required_response_families=("linear-response",),
    ),
    VendorTruthCase(
        path="validation/Iron Box.csv",
        split="holdout",
        title="Buried iron box",
        target_present=True,
        required_any_patterns=("dipolar-response", "metallic-like"),
        required_response_families=("dipolar-response",),
        required_hypothesis_support=(("metallic-like", 0.45),),
    ),
    VendorTruthCase(
        path="validation/Tunnel - Control Scan.csv",
        split="holdout",
        title="Control scan for potential tunnel",
        target_present=True,
        required_any_patterns=("tunnel-like",),
        min_pattern_counts={"tunnel-like": 1},
        paired_with="train/Tunnel - Original Scan.csv",
        pair_expectation="shared tunnel-like pattern family",
    ),
)


def _hypothesis_score(candidate: Candidate, hypothesis: str) -> float:
    scores = getattr(candidate, "hypothesis_scores", {}) or {}
    try:
        return float(scores.get(hypothesis, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _check_case(case: VendorTruthCase, candidates: list[Candidate]) -> dict:
    patterns = [str(getattr(c, "pattern_hypothesis", "")) for c in candidates]
    families = [str(getattr(c, "response_family", "")) for c in candidates]
    matched_any = (
        bool(set(patterns) & set(case.required_any_patterns))
        if case.required_any_patterns
        else True
    )
    count_ok = all(
        patterns.count(pattern) >= int(count) for pattern, count in case.min_pattern_counts.items()
    )
    family_ok = all(family in families for family in case.required_response_families)
    boundary_candidates = [
        float(getattr(c, "boundary_contact_ratio", 0.0) or 0.0) for c in candidates
    ]
    boundary_ok = case.min_boundary_contact is None or any(
        v >= case.min_boundary_contact for v in boundary_candidates
    )
    candidate_lower_ok = len(candidates) >= case.min_candidates
    candidate_upper_ok = case.max_candidates is None or len(candidates) <= case.max_candidates
    support_ok = all(
        any(_hypothesis_score(c, hyp) >= threshold for c in candidates)
        for hyp, threshold in case.required_hypothesis_support
    )
    passed = all((
        matched_any,
        count_ok,
        family_ok,
        boundary_ok,
        candidate_lower_ok,
        candidate_upper_ok,
        support_ok,
    ))
    return {
        "path": case.path,
        "split": case.split,
        "title": case.title,
        "target_present": case.target_present,
        "passed": passed,
        "candidate_count": len(candidates),
        "patterns": patterns,
        "response_families": families,
        "matched_any_required_pattern": matched_any,
        "required_pattern_counts_ok": count_ok,
        "required_response_families_ok": family_ok,
        "boundary_requirement_ok": boundary_ok,
        "candidate_count_lower_bound_ok": candidate_lower_ok,
        "candidate_count_upper_bound_ok": candidate_upper_ok,
        "required_support_ok": support_ok,
        "required_any_patterns": list(case.required_any_patterns),
        "min_pattern_counts": dict(case.min_pattern_counts),
        "required_response_families": list(case.required_response_families),
        "min_boundary_contact": case.min_boundary_contact,
        "max_candidates": case.max_candidates,
        "required_hypothesis_support": {
            hyp: threshold for hyp, threshold in case.required_hypothesis_support
        },
        "candidates": [
            {
                "id": int(c.id),
                "pattern": c.pattern_hypothesis,
                "response_family": getattr(c, "response_family", ""),
                "polarity": c.polarity,
                "shape_class": c.shape_class,
                "evidence_score": round(float(c.evidence_score), 3),
                "hypothesis_scores": dict(c.hypothesis_scores),
                "boundary_contact_ratio": round(float(c.boundary_contact_ratio), 3),
                "artifact_score": round(float(c.artifact_score), 3),
                "second_hypothesis": c.second_hypothesis,
                "selected_hypothesis_margin": round(float(c.selected_hypothesis_margin), 3),
            }
            for c in candidates
        ],
    }


def _pair_checks(rows: dict[str, dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[frozenset[str]] = set()
    for case in VENDOR_TRUTH:
        if not case.paired_with:
            continue
        key = frozenset((case.path, case.paired_with))
        if key in seen:
            continue
        seen.add(key)
        current = rows.get(case.path, {})
        partner = rows.get(case.paired_with, {})
        current_tunnel = "tunnel-like" in current.get("patterns", [])
        partner_tunnel = "tunnel-like" in partner.get("patterns", [])
        result.append({
            "a": case.path,
            "b": case.paired_with,
            "expectation": case.pair_expectation,
            "passed": current_tunnel and partner_tunnel,
            "a_has_tunnel": current_tunnel,
            "b_has_tunnel": partner_tunnel,
        })
    return result


def evaluate_vendor_reference(
    root: str | Path,
    *,
    out_dir: str | Path | None = None,
    threshold: float = 3.0,
    min_size: int = 3,
) -> dict:
    """Evaluate the nine frozen OKM vendor examples without changing model behavior."""
    from ..services.config import AnalysisConfig

    root = Path(root)
    output = Path(out_dir) if out_dir is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    cfg = AnalysisConfig(threshold=threshold, min_size=min_size)

    rows: dict[str, dict] = {}
    missing_cases: list[str] = []
    for case in VENDOR_TRUTH:
        path = root / case.path
        if not path.exists():
            missing_cases.append(case.path)
            continue
        scan = load_scan(path)
        run_dir = output / path.stem if output is not None else Path(".")
        if output is not None:
            run_dir.mkdir(parents=True, exist_ok=True)
        _, _, candidates = analyze_scan(
            scan,
            run_dir,
            label=path.stem,
            config=cfg,
            write_outputs=output is not None,
        )
        rows[case.path] = _check_case(case, candidates)

    all_rows = list(rows.values())
    train = [r for r in all_rows if r["split"] == "train"]
    holdout = [r for r in all_rows if r["split"] == "holdout"]
    pair_checks = _pair_checks(rows)
    result = {
        "benchmark": "okm_vendor_documented_reference",
        "version": "0.4.0",
        "provenance": "OKM vendor educational sample metadata/notes",
        "independent_field_ground_truth": False,
        "interpretation": "pattern-family reference from documented vendor answers; not material identification and not physical-depth validation",
        "cases_total": len(all_rows),
        "train_cases": len(train),
        "holdout_cases": len(holdout),
        "train_passed": sum(bool(r["passed"]) for r in train),
        "holdout_passed": sum(bool(r["passed"]) for r in holdout),
        "overall_passed": sum(bool(r["passed"]) for r in all_rows),
        "train_pass_rate": sum(bool(r["passed"]) for r in train) / max(len(train), 1),
        "holdout_pass_rate": sum(bool(r["passed"]) for r in holdout) / max(len(holdout), 1),
        "pair_checks": pair_checks,
        "pair_passed": sum(bool(p["passed"]) for p in pair_checks),
        "pair_total": len(pair_checks),
        "raw_cases_available": len(all_rows),
        "raw_cases_missing": len(missing_cases),
        "missing_raw_cases": missing_cases,
        "incomplete_raw_dataset": bool(missing_cases),
        "rows": all_rows,
        "truth_manifest": [
            {
                "path": c.path,
                "split": c.split,
                "title": c.title,
                "target_present": c.target_present,
                "required_any_patterns": list(c.required_any_patterns),
                "min_pattern_counts": dict(c.min_pattern_counts),
                "required_response_families": list(c.required_response_families),
                "min_boundary_contact": c.min_boundary_contact,
                "max_candidates": c.max_candidates,
                "required_hypothesis_support": {h: t for h, t in c.required_hypothesis_support},
                "paired_with": c.paired_with,
                "pair_expectation": c.pair_expectation,
                "provenance": c.provenance,
            }
            for c in VENDOR_TRUTH
        ],
    }

    if output is not None:
        (output / "vendor_ground_truth.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (output / "vendor_ground_truth.md").write_text(
            vendor_reference_markdown(result), encoding="utf-8"
        )
    return result


def vendor_reference_markdown(result: dict) -> str:
    title = f"# GroundScan Analyzer {__version__} — OKM Documented Reference"
    intro = (
        "This benchmark uses nine OKM educational examples. Expected semantics are "
        "transcribed from the files' own vendor notes; they are not independent field "
        "ground truth."
    )
    lines = [
        title,
        "",
        intro,
        "",
        f"Cases in manifest: **{len(result.get('truth_manifest', []))}**; raw files available: **{result.get('raw_cases_available', result.get('cases_total', 0))}**; raw files missing: **{result.get('raw_cases_missing', 0)}**.",
        "",
    ]
    if result.get("incomplete_raw_dataset"):
        lines += [
            "> **INCOMPLETE RAW DATASET:** missing CSVs are not synthesized or substituted. Add the original files before treating this benchmark as a complete 9-case run.",
            "",
        ]
    lines.append(
        f"Cases evaluated: **{result['cases_total']}**; train: **{result['train_passed']}/{result['train_cases']}**; holdout: **{result['holdout_passed']}/{result['holdout_cases']}**."
    )
    lines.append("| File | Split | Expected | Result | Candidates |")
    lines.append("|---|---|---|---|---:|")
    for row in result["rows"]:
        expected = (
            ", ".join(row["required_any_patterns"]) if row["required_any_patterns"] else "no object"
        )
        res = "PASS" if row["passed"] else "FAIL"
        lines.append(
            f"| `{row['path']}` | {row['split']} | {expected} | **{res}** | {row['candidate_count']} |"
        )
    lines += [
        "",
        "## Semantics",
        "",
        "Pattern support scores are bounded heuristics, not probabilities. Vendor material labels such as gold/silver are deliberately not used as classifier targets.",
    ]
    if result["pair_checks"]:
        lines += ["", "## Control-scan consistency", ""]
        for pair in result["pair_checks"]:
            lines.append(
                f"- `{pair['a']}` ↔ `{pair['b']}`: {'PASS' if pair['passed'] else 'FAIL'} — {pair['expectation']}"
            )
    return "\n".join(lines) + "\n"


__all__ = [
    "VendorTruthCase",
    "VENDOR_TRUTH",
    "evaluate_vendor_reference",
    "vendor_reference_markdown",
]

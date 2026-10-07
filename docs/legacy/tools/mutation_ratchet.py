"""Curated mutation ratchet for the analysis engine (audit follow-up).

Why not ``mutmut``/``cosmic-ray``: a full sweep of this codebase would run the
389-test suite thousands of times (the suite takes ~80 s), which is not viable
as a per-PR gate, and it would need a multi-day baseline-generation run before
it could block anything. This tool instead encodes a *curated* set of mutations
covering the critical paths named in the code audit -- the safety gates, the
confidence/quality computation, fusion, registration and the shared numeric
helpers -- and runs each one against a small designated test selection
(typically seconds, not minutes).

The contract is a ratchet, matching the existing coverage ratchet in CI:

  * every mutation MUST be killed by at least one test in its selection;
  * a mutation that is not killed is recorded as a *survivor*;
  * the job fails only when a mutation that is currently killed starts
    surviving (a real regression in test coverage), or when a brand-new
    survivor appears that is not present in the pinned baseline.

Baseline file: ``tools/mutation_baseline.json``. Regenerate deliberately with
``--update-baseline`` and review the diff -- a growing survivor list is a
signal that the test suite is losing grip, not a reason to re-pin silently.

Usage:
    python tools/mutation_ratchet.py                 # check against baseline
    python tools/mutation_ratchet.py --list          # show the mutation set
    python tools/mutation_ratchet.py --update-baseline
    python tools/mutation_ratchet.py -k registration  # filter by substring
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "mutation_baseline.json"

# Directories the suite needs but that are not importable source.
COPY_DIRS = ("groundscan", "tests", "tools", "docs", "scans", "groundscan_research")
COPY_FILES = ("pyproject.toml", "CONTEXT.md")


@dataclass(frozen=True)
class Mutation:
    """One deliberate defect injected into one source file."""

    ident: str
    path: str
    anchor: str
    replacement: str
    tests: tuple[str, ...]
    why: str


# ---------------------------------------------------------------------------
# The mutation set. Grouped by the subsystem each one protects.
# ---------------------------------------------------------------------------
MUTATIONS: tuple[Mutation, ...] = (
    # -- site determinism / fusion ------------------------------------------
    Mutation(
        ident="site-input-order-removed",
        path="groundscan/site/analyze_site.py",
        anchor="    scans = sorted(scans, key=lambda item: str(item[0]))",
        replacement="    pass  # mutation: canonical input order removed",
        tests=(
            "tests/unit/test_audit_regressions.py::test_site_fusion_is_independent_of_input_order",
        ),
        why="fusion must not depend on the order scans are supplied in",
    ),
    Mutation(
        ident="consensus-cluster-tiebreak",
        path="groundscan/site/consensus.py",
        anchor="            if d <= adaptive and d < best_d:",
        replacement="            if d <= adaptive and d <= best_d:",
        tests=(
            "tests/unit/test_audit_regressions.py::test_greedy_cluster_assignment_breaks_ties_toward_the_first_cluster",
        ),
        why="greedy cluster assignment must stay deterministic",
    ),
    # -- registration --------------------------------------------------------
    Mutation(
        ident="registration-sort-direction",
        path="groundscan/site/registration.py",
        anchor="    scored.sort(key=lambda row: (row[0], -abs(row[4]) - abs(row[5])), reverse=True)",
        replacement="    scored.sort(key=lambda row: (row[0], -abs(row[4]) - abs(row[5])))",
        tests=(
            "tests/unit/test_audit_regressions.py::test_flat_correlation_surface_resolves_to_zero_shift",
        ),
        why="alignment must select the best-scoring shift, not the worst",
    ),
    Mutation(
        ident="registration-zero-shift-tiebreak",
        path="groundscan/site/registration.py",
        anchor="    scored.sort(key=lambda row: (row[0], -abs(row[4]) - abs(row[5])), reverse=True)",
        replacement="    scored.sort(key=lambda row: row[0], reverse=True)",
        tests=(
            "tests/unit/test_audit_regressions.py::test_flat_correlation_surface_resolves_to_zero_shift",
        ),
        why="a flat correlation surface must resolve to the origin shift",
    ),
    Mutation(
        ident="registration-max-shift-zero",
        path="groundscan/site/registration.py",
        anchor="        for dy in range(-max_shift, max_shift + 1):",
        replacement="        for dy in range(0, max_shift + 1):",
        tests=(
            "tests/unit/test_audit_regressions.py::test_registration_recovers_a_negative_vertical_shift",
            "tests/unit/test_audit_regressions.py::test_flat_correlation_surface_resolves_to_zero_shift",
        ),
        why="the shift search must explore negative displacements",
    ),
    # -- shared numeric helpers ---------------------------------------------
    # The 5%-of-std scale floor (audit F-01) and both of its mutants were
    # removed with the floor itself. It was provably a no-op: its input was a
    # winsorized std, every winsorized value lies within 5*scale of the median,
    # so by Popoviciu floor_std <= 5*scale and 0.05*floor_std <= 0.25*scale <
    # scale -- max(scale, 0.05*floor_std) == scale identically. The mutant
    # `robust-scale-floor-removed` surviving was the evidence; the reasoning
    # and the deletion are recorded in `groundscan._util.robust_scale`.
    # -- field-quality gate --------------------------------------------------
    Mutation(
        ident="strong-artifact-caution-dropped",
        path="groundscan/gates/field_quality.py",
        anchor='            "strong-instrument-artifact-concern",\n',
        replacement="",
        tests=(
            "tests/unit/test_audit_regressions.py::test_strong_instrument_artifact_degrades_readiness",
        ),
        why="a strong instrument artifact must degrade readiness, not be ignored",
    ),
    Mutation(
        ident="field-quality-hard-block-never-fires",
        path="groundscan/gates/field_quality.py",
        anchor='    if coverage < T["grid_coverage_hard_block"]:',
        replacement="    if coverage < -1.0:",
        tests=("tests/unit/test_field_quality.py",),
        why="a severely incomplete grid must hard-block",
    ),
    # -- operational gate ----------------------------------------------------
    Mutation(
        ident="operational-artifact-block-never-fires",
        path="groundscan/gates/operational.py",
        anchor="    if artifact >= ARTIFACT_BLOCK:",
        replacement="    if artifact >= 1.01:",
        tests=(
            "tests/unit/test_audit_regressions.py::test_operational_gate_blocks_on_strong_artifact_evidence",
            "tests/unit/test_audit_regressions.py::test_operational_gate_does_not_clear_on_all_non_finite_evidence",
        ),
        why="a strong artifact must block) operational use",
    ),
    Mutation(
        ident="operational-bounded-guard-removed",
        path="groundscan/gates/operational.py",
        anchor='    registration = bounded01(getattr(candidate, "registration_consistency", 1.0))',
        replacement='    registration = float(np.clip(getattr(candidate, "registration_consistency", 1.0), 0.0, 1.0))',
        tests=(
            "tests/unit/test_audit_regressions.py::test_operational_gate_does_not_clear_on_all_non_finite_evidence",
        ),
        why="non-finite gate inputs must not read as passing",
    ),
    # -- quality / evidence --------------------------------------------------
    Mutation(
        ident="quality-evidence-guard-removed",
        path="groundscan/gates/quality.py",
        anchor='    evidence = resolve_gate_input(candidate, "evidence_score")',
        replacement="    evidence = float(np.clip(candidate.evidence_score, 0.0, 1.0))",
        tests=(
            "tests/unit/test_audit_regressions.py::test_candidate_quality_does_not_promote_unknown_evidence",
        ),
        why="unknown evidence must not reach the strongest review label",
    ),
    Mutation(
        ident="quality-insufficient-evidence-never-fires",
        path="groundscan/gates/quality.py",
        anchor="    elif quality < 0.40 or evidence < 0.30:",
        replacement="    elif quality < -1.0 or evidence < -1.0:",
        tests=(
            "tests/unit/test_audit_regressions.py::test_candidate_quality_reports_insufficient_evidence",
            "tests/unit/test_audit_regressions.py::test_candidate_quality_does_not_promote_unknown_evidence",
        ),
        why="low quality or low evidence) must be reported as insufficient",
    ),
    Mutation(
        ident="registration-evidence-nan-guard-removed",
        path="groundscan/gates/thresholds.py",
        anchor="    corr = bounded01(correlation)\n    over = bounded01(overlap)\n    marg = bounded01(margin)\n    mult = bounded01(multiscale)",
        replacement="    corr = max(0.0, min(1.0, correlation))\n    over = max(0.0, min(1.0, overlap))\n    marg = max(0.0, min(1.0, margin))\n    mult = max(0.0, min(1.0, multiscale))",
        tests=(
            "tests/unit/test_audit_regressions.py::test_registration_evidence_score_does_not_treat_unknown_as_perfect",
        ),
        why="unknown registration must not score a perfect 1.0",
    ),
    # -- shape ---------------------------------------------------------------
    Mutation(
        ident="solidity-constant-one",
        path="groundscan/core/shape.py",
        anchor="    solidity = (n_cells * dx * dy) / hull_area",
        replacement="    solidity = 1.0",
        tests=("tests/unit/test_audit_regressions.py",),
        why="solidity must remain a real shape descriptor (killed by the "
        "filled-square vs L-shape ordering test)",
    ),
    # -- ingestion: duplicate CSV headers -----------------------------------
    Mutation(
        ident="csv-duplicate-header-guard-removed",
        path="groundscan/io/generic_csv.py",
        anchor="            _reject_duplicate_headers(header, path)\n",
        replacement="",
        tests=(
            "tests/unit/test_audit_followup.py::test_duplicate_csv_headers_are_rejected_by_name",
            "tests/unit/test_audit_followup.py::test_headers_colliding_after_normalization_are_rejected",
        ),
        why="a repeated column name must be reported against the file, not "
        "surface as a ScanData arity error from models.py",
    ),
    Mutation(
        ident="csv-duplicate-guard-ignores-normalization",
        path="groundscan/io/generic_csv.py",
        anchor="        key = _norm(name)\n        if key in seen:",
        replacement="        key = name\n        if key in seen:",
        tests=(
            "tests/unit/test_audit_followup.py::test_headers_colliding_after_normalization_are_rejected",
        ),
        why="columns are looked up normalized, so X/x must collide too",
    ),
    # -- fusion: single-observation consistency ------------------------------
    Mutation(
        ident="fusion-single-obs-reads-as-perfect",
        path="groundscan/site/fusion.py",
        anchor="        return 0.5\n    center = float(np.median(v))\n    return float(np.clip(_robust_dispersion(v, floor=floor)",
        replacement="        return 0.0\n    center = float(np.median(v))\n    return float(np.clip(_robust_dispersion(v, floor=floor)",
        tests=(
            "tests/unit/test_audit_followup.py::test_single_observation_relative_dispersion_is_neutral_not_perfect",
            "tests/unit/test_audit_followup.py::test_single_member_fusion_reports_neutral_size_consistency",
        ),
        why="a one-observation cluster must not report perfect consistency",
    ),
    # -- rescue: policy knobs reachable --------------------------------------
    Mutation(
        ident="rescue-policy-defaults-hardcoded",
        path="groundscan/core/rescue.py",
        anchor="    threshold: float | None = None,\n    min_size: int | None = None,\n    scales: tuple[int, ...] | None = None,",
        replacement="    threshold: float | None = 3.0,\n    min_size: int | None = 3,\n    scales: tuple[int, ...] | None = (3, 5, 9, 15),",
        tests=(
            "tests/unit/test_audit_followup.py::test_rescue_defaults_match_the_policy_defaults",
        ),
        why="literal defaults make ExtractionRescuePolicy's own knobs unreachable",
    ),
    Mutation(
        ident="rescue-policy-indirection-dropped",
        path="groundscan/core/rescue.py",
        anchor="        threshold=float(policy.threshold if threshold is None else threshold),",
        replacement="        threshold=float(threshold),",
        tests=(
            "tests/unit/test_audit_followup.py::test_rescue_uses_policy_threshold_when_caller_defers",
        ),
        why="the policy must win when the caller defers",
    ),
    # -- classifier ----------------------------------------------------------
    # The `classify-sigmoid-clamp-widened` mutant and the code it mutated were
    # both removed. The clamp lived in `_void_hypothesis_scores()`, called only
    # from `_apply_compatibility_feature_pass()`; every field that pass wrote
    # was overwritten unconditionally by `classify_candidate()`'s single
    # `with_updates`, so no threshold in the pass could reach a returned
    # candidate. The mutant survived because the clamp was unreachable, not
    # because the suite was weak. The pass, `_void_hypothesis_scores`,
    # `_apply_multi_hypothesis_override`, `_classification_support_diagnostics`,
    # `_bounded_evidence` and `_negative_fraction` are deleted; the reasoning is
    # recorded on `classify_candidate` and in docs/adr/011.
    # -- separation ----------------------------------------------------------
    # This mutation used to sit on the `analyze_site()` call site
    # (`allow_single_scan=True` injected into the site-mode call) and was pinned
    # as a known survivor. It was unkillable there, and the reason is worth
    # recording because it is not "no test reaches the code":
    #
    #   * single-scan candidates DO reach `separate_fused_candidates` from the
    #     site path (verified by instrumenting the call), and
    #   * the single-scan branch IS live and observable when called directly
    #     (with `allow_single_scan=True` a single-scan parent splits into 4
    #     fragments; with the default it returns 1), but
    #   * the site path cannot act on the difference. It caps single-scan fused
    #     evidence at 0.45 (`analyze_site.py`, `if len(labels) == 1`), which is
    #     below `SeparationConfig.parent_evidence_min` (0.55), so the parent is
    #     rejected at the first gate before the single-scan branch is consulted;
    #     and every fragment a split would produce inherits `scan_count=1`, so
    #     `_retain_repeatable_fused_candidates` discards them regardless.
    #
    # So the site-mode policy is enforced twice over (the evidence cap and the
    # repeatability gate), which is why flipping the flag there is a no-op. The
    # mutation now pins the gate that actually decides it: dropping the
    # `scan_count < 2` check lets a single-scan parent be split at all, which is
    # observable at the function boundary and is what the site path relies on.
    Mutation(
        ident="separation-single-scan-parent-not-rejected",
        path="groundscan/site/separation.py",
        anchor="            or ((not allow_single_scan) and parent.scan_count < 2)",
        replacement="            or (False and parent.scan_count < 2)",
        tests=(
            "tests/unit/test_audit_regressions.py::test_separation_does_not_split_a_single_scan_parent_by_default",
        ),
        why="a single-scan parent must not be split unless the caller opts in",
    ),
)


def _prepare(workspace: Path) -> dict[str, str]:
    """Copy the tree into *workspace* and return pristine file contents."""
    for name in COPY_DIRS:
        src = ROOT / name
        if src.exists():
            shutil.copytree(src, workspace / name, dirs_exist_ok=True)
    for name in COPY_FILES:
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, workspace / name)
    return {
        mutation.path: (workspace / mutation.path).read_text(encoding="utf-8")
        for mutation in MUTATIONS
    }


def _run_tests(workspace: Path, tests: tuple[str, ...]) -> tuple[bool, str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            *tests,
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        timeout=1800,
    )
    tail = [line for line in result.stdout.strip().splitlines() if line.strip()]
    return result.returncode == 0, (tail[-1] if tail else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list the mutation set and exit")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the pinned survivor list (review the diff!)",
    )
    parser.add_argument("-k", dest="filter", default="", help="only run matching mutations")
    args = parser.parse_args()

    if args.list:
        for m in MUTATIONS:
            print(f"{m.ident}\n    {m.path}\n    {m.why}\n")
        print(f"{len(MUTATIONS)} mutations")
        return 0

    selected = [m for m in MUTATIONS if args.filter in m.ident]
    if not selected:
        print(f"no mutations match {args.filter!r}", file=sys.stderr)
        return 2

    # Sanity: the pristine tree must pass, otherwise every "killed" verdict is
    # meaningless. (This is the trap that made a first ratchet attempt report
    # every mutation as killed.)
    with tempfile.TemporaryDirectory(prefix="gs-mutbase-") as tmp:
        workspace = Path(tmp)
        pristine = _prepare(workspace)
        baseline_ok, baseline_tail = _run_tests(
            workspace, ("tests/unit/test_audit_regressions.py", "tests/unit/test_field_quality.py")
        )
        if not baseline_ok:
            print("PRISTINE TREE FAILS THE DESIGNATED TESTS — aborting.", file=sys.stderr)
            print(f"  {baseline_tail}", file=sys.stderr)
            return 3
        print(f"pristine baseline green: {baseline_tail}\n")

        results: dict[str, str] = {}
        print(f"{'MUTATION':<42} {'VERDICT':<10} DETAIL")
        print("-" * 100)
        for mutation in selected:
            target = workspace / mutation.path
            source = pristine[mutation.path]
            if mutation.anchor not in source:
                print(f"{mutation.ident:<42} {'SKIP':<10} anchor not found")
                results[mutation.ident] = "skip"
                continue
            target.write_text(
                source.replace(mutation.anchor, mutation.replacement, 1), encoding="utf-8"
            )
            try:
                passed, tail = _run_tests(workspace, mutation.tests)
            finally:
                target.write_text(source, encoding="utf-8")
            verdict = "survived" if passed else "killed"
            results[mutation.ident] = verdict
            print(f"{mutation.ident:<42} {verdict.upper():<10} {tail[:40]}")

    survivors = sorted(k for k, v in results.items() if v == "survived")
    killed = sorted(k for k, v in results.items() if v == "killed")
    skipped = sorted(k for k, v in results.items() if v == "skip")

    print()
    print(f"{len(killed)} killed, {len(survivors)} survived, {len(skipped)} skipped")
    if survivors:
        print()
        print("Survivors -- the suite does NOT constrain these paths:")
        by_id = {m.ident: m for m in MUTATIONS}
        for name in survivors:
            mutation = by_id[name]
            print(f"  [UNEXPECTED] {name}")
            print(f"      guards: {mutation.why}")

    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps({"survivors": survivors}, indent=2) + "\n", encoding="utf-8"
        )
        print(f"baseline updated -> {BASELINE_PATH.relative_to(ROOT)}")
        return 0

    pinned: dict[str, object] = {}
    if BASELINE_PATH.exists():
        pinned = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    known = set(pinned.get("survivors", []))

    regressed = sorted(known - set(survivors))  # was a survivor, now killed: fine
    new_survivors = sorted(set(survivors) - known)
    if skipped:
        print(f"ERROR: anchors missing (stale mutation set): {skipped}", file=sys.stderr)
        return 1
    if new_survivors:
        print(
            f"\nFAIL: {len(new_survivors)} mutation(s) no longer detected by any test:",
            file=sys.stderr,
        )
        for name in new_survivors:
            print(f"  - {name}", file=sys.stderr)
        print(
            "Add a regression test, or re-pin deliberately with --update-baseline.", file=sys.stderr
        )
        return 1
    if regressed:
        print(f"note: {len(regressed)} pinned survivor(s) are now killed: {regressed}")
    print("PASS: every new mutation is detected by the designated tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Scientific validation orchestration (P4): `groundscan validate science`.

Runs the four technical-validation layers and assembles the unified
science report. This module is orchestration only: case assembly,
engine calls through public APIs, section assembly, provenance stamping,
and verdict derivation. It contains no generators (see ``synthetic_core``),
no matching logic (see ``benchmark_large``/``oracles``), no transforms
(see ``metamorphic``), no thresholds, no scoring, and no serialization
(see ``science_reporting``).

Split applied under the documented rule: serialization
(``sanitize_json``, report writing, Markdown rendering) lives in
``science_reporting.py``, which imports nothing engine-specific.
A further split triggers if one layer ever needs imports the others do
not (e.g. private engine access): that layer leaves for a dedicated
``scientific_<layer>.py`` behind the same ``run_*`` signature.

Graduation rule (documented future criterion, NOT performed here):
science smoke may join the release contracts gate only if ALL hold --
(1) 30 consecutive days green on main with zero oracle-constant edits,
(2) at least one genuine production regression caught by a science
oracle, (3) the graduating subset runs < 60 s on the reference box,
(4) floors/allowances reviewed with provenance recorded.
Graduation status: RULE DOCUMENTED; graduation itself NOT PERFORMED.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .science_reporting import write_science_report

#: Science report schema version. Bump on any report-shape change.
SCIENCE_SCHEMA_VERSION = "1.0"

#: Evidence taxonomy. Scientific sections assert behavior; reference,
#: regression, and empirical sections point at their own gates.
EVIDENCE_KIND_SCIENTIFIC = "scientific"
EVIDENCE_KIND_REFERENCE = "reference"
EVIDENCE_KIND_REGRESSION = "regression"
EVIDENCE_KIND_EMPIRICAL = "empirical"

MATH_CONTRACT_TESTS = "tests/unit/test_math_contracts.py"


def _provenance(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "science_schema_version": SCIENCE_SCHEMA_VERSION,
    }
    if extra:
        record.update(extra)
    return record


def run_mathematical() -> dict[str, Any]:
    """Mathematical section: the frozen contract-test file is the oracle.

    Status comes from executing the contract tests, not from duplicating
    their assertions here.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", MATH_CONTRACT_TESTS, "-q"],
        capture_output=True,
        text=True,
    )
    passed = proc.returncode == 0
    return {
        "evidence_kind": EVIDENCE_KIND_SCIENTIFIC,
        "validation_domain": "mathematical_contract",
        "status": "pass" if passed else "fail",
        "gating": True,
        "contract_tests": MATH_CONTRACT_TESTS,
        "pytest_exit": proc.returncode,
        "not_evidence_for": ["field_accuracy", "detection_correctness"],
        "converts_to": [],
    }


def run_synthetic(work_dir: str | Path, *, mode: str = "smoke") -> dict[str, Any]:
    """Synthetic section: frozen oracle over catalog + ladders (+large in full)."""
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan
    from .synthetic_core.core import generate_scan, ladder_scenarios, scenario_catalog
    from .synthetic_core.oracles import (
        ORACLE_VERSION,
        check_oracle_result,
        evaluate_oracle_case,
        operating_point_record,
    )

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    config = AnalysisConfig()
    scenarios = list(scenario_catalog()) + list(ladder_scenarios())
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    for scenario in scenarios:
        scan, truth = generate_scan(scenario)
        _, _, candidates = analyze_scan(
            scan,
            work_dir / scenario.name,
            label=scenario.name,
            config=config,
            write_outputs=False,
        )
        result = evaluate_oracle_case(
            candidates, truth, case_id=scenario.name, family=scenario.name
        )
        for failure in check_oracle_result(result):
            failures.append(f"{scenario.name}: {failure}")
        cases.append(result)
    families: dict[str, dict[str, Any]] = {}
    for result in cases:
        families[str(result["family"])] = {
            "gating": True,
            "synthetic_recall": result["synthetic_recall"],
            "synthetic_precision": result["synthetic_precision"],
            "synthetic_center_error_m": result["synthetic_center_error_m"],
            "synthetic_depth_error_m": result["synthetic_depth_error_m"],
            "false_positives": result["false_positives"],
            "missed_targets": result["missed_targets"],
        }
    section: dict[str, Any] = {
        "evidence_kind": EVIDENCE_KIND_SCIENTIFIC,
        "validation_domain": "controlled_synthetic",
        "scientific_claim": "behavior under the stated controlled conditions only",
        "status": "pass" if not failures else "fail",
        "gating": True,
        "oracle_version": ORACLE_VERSION,
        "mode": mode,
        "cases": len(cases),
        "families": families,
        "failed_cases": failures,
        "matching_policy": {
            "assignment": "global one-to-one (Hungarian)",
            "pattern_compatibility": "expected_patterns() map (oracle-versioned)",
            "distance_tolerance_m": 3.0,
        },
        "operating_point": operating_point_record(),
        "not_evidence_for": [
            "field_accuracy",
            "field_recall",
            "field_precision",
            "material_identity",
        ],
        "converts_to": [],
    }
    if mode == "full":
        section["large_suite"] = _run_large_suite_informational(work_dir)
        large = section["large_suite"]
        large["gating"] = False
        integrity = list(large.get("integrity_failures", []))
        if integrity:
            # Integrity failures (crash / non-finite output) are gating
            # defects even inside informational breadth; recorded family
            # metrics never gate.
            section["status"] = "fail"
            section["failed_cases"] = list(section.get("failed_cases", [])) + [
                f"large_suite integrity: {f}" for f in integrity
            ]
    return section


def _run_large_suite_informational(work_dir: Path) -> dict[str, Any]:
    """Full-mode breadth lives in benchmark_large; orchestration only calls it."""
    from .synthetic_core.benchmark_large import run_large_suite_informational

    return dict(run_large_suite_informational(work_dir))


def run_adversarial(work_dir: str | Path) -> dict[str, Any]:
    """Adversarial section: frozen four-bin classification of hostile scans."""
    from .synthetic_core.negative import all_negative_cases, run_negative_case
    from .synthetic_core.oracles import ORACLE_VERSION, operating_point_record

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    records = [run_negative_case(case, work_dir) for case in all_negative_cases()]
    failures = [
        f"{r['case_id']}: {r['verdict']} -- {r['verdict_detail']}"
        for r in records
        if not r["passes"]
    ]
    bins: dict[str, int] = {}
    for record in records:
        bins[str(record["verdict"])] = bins.get(str(record["verdict"]), 0) + 1
    # DOCUMENTED_LIMITATION register: within-allowance known weaknesses pass
    # the gate but stay individually visible and tracked. A limitation is
    # never silently reclassified as expected behavior; exceeding the
    # allowance is a false positive, not a louder limitation.
    limitations = [
        {
            "case_id": r["case_id"],
            "family": r["family"],
            "retained_candidates": r["retained_candidates"],
            "detail": r["verdict_detail"],
        }
        for r in records
        if str(r["verdict"]) == "documented_limitation"
    ]
    return {
        "evidence_kind": EVIDENCE_KIND_SCIENTIFIC,
        "validation_domain": "controlled_adversarial",
        "scientific_claim": "robustness on stated hostile inputs only",
        "status": "pass" if not failures else "fail",
        "gating": True,
        "oracle_version": ORACLE_VERSION,
        "cases": len(records),
        "verdict_bins": bins,
        "failed_cases": failures,
        "limitations": limitations,
        "case_records": [
            {
                "case_id": r["case_id"],
                "family": r["family"],
                "gating": True,
                "retained_candidates": r["retained_candidates"],
                "retained_patterns": r["retained_patterns"],
                "verdict": r["verdict"],
            }
            for r in records
        ],
        "operating_point": operating_point_record(),
        "not_evidence_for": ["field_false_positive_rate", "field_accuracy"],
        "converts_to": [],
    }


def run_metamorphic(work_dir: str | Path) -> dict[str, Any]:
    """Metamorphic section: frozen relation specs over pipeline pairs."""
    import numpy as _np

    from ..services.config import AnalysisConfig as _Config
    from ..services.single_scan import analyze_scan as _analyze
    from .synthetic_core.core import generate_scan as _gen
    from .synthetic_core.core import scenario_catalog as _catalog
    from .synthetic_core.metamorphic import (
        RELATION_SPECS,
        evaluate_metamorphic_pair,
        flip_x_scan,
        flip_y_scan,
        index_frame_scan,
        rot90_scan,
        rot180_scan,
        translate_scan,
    )

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    config = _Config()
    pair_names = ("positive_compact", "linear_tunnel", "rotated_tunnel")
    failures: list[str] = []
    pairs: list[dict[str, Any]] = []

    def _run(scan: Any, label: str) -> list:
        _, _, candidates = _analyze(
            scan, work_dir / label, label=label, config=config, write_outputs=False
        )
        return candidates

    def _sums(scan: Any) -> tuple[float, float]:
        x = _np.asarray(scan.x, dtype=float)
        y = _np.asarray(scan.y, dtype=float)
        return float(_np.nanmin(x) + _np.nanmax(x)), float(_np.nanmin(y) + _np.nanmax(y))

    transforms = {
        "flip_x": lambda s: (flip_x_scan(s), {}),
        "flip_y": lambda s: (flip_y_scan(s), {}),
        "translate": lambda s: (translate_scan(s, 5.0, -3.0), {}),
        "rot180": lambda s: (rot180_scan(s), {}),
        "rot90": lambda s: (rot90_scan(s), {}),
        "index_frame": lambda s: (index_frame_scan(s), {}),
    }
    for name in pair_names:
        scenario = next(s for s in _catalog() if s.name == name)
        base = _run(_gen(scenario)[0], f"{name}-base")
        for transform, build in transforms.items():
            moved_scan, _ = build(_gen(scenario)[0])
            moved = _run(moved_scan, f"{name}-{transform}")
            kwargs: dict[str, Any] = {}
            if transform == "flip_x":
                (x_sum, _) = _sums(moved_scan)
                kwargs = {"x_sum": x_sum}
            elif transform == "flip_y":
                (_, y_sum) = _sums(moved_scan)
                kwargs = {"y_sum": y_sum}
            elif transform == "rot180":
                x_sum, y_sum = _sums(moved_scan)
                kwargs = {"x_sum": x_sum, "y_sum": y_sum}
            elif transform == "translate":
                kwargs = {"shift": (5.0, -3.0)}
            record = evaluate_metamorphic_pair(base, moved, transform, **kwargs)
            pairs.append({
                "scenario": name,
                "transform": transform,
                "strength": record["strength"],
                "gating": bool(RELATION_SPECS[transform]["strength"] != "review_required"),
                "passes": record["passes"],
            })
            failures.extend(f"{name}/{transform}: {f}" for f in record["failures"])
    gating = [p for p in pairs if p["gating"]]
    gating_failed = [p for p in gating if not p["passes"]]
    return {
        "evidence_kind": EVIDENCE_KIND_SCIENTIFIC,
        "validation_domain": "metamorphic_invariance",
        "scientific_claim": "implementation consistency under stated transforms only",
        "status": "pass" if not failures else "fail",
        "gating": True,
        "review_pairs_gate_on": "output integrity (finiteness) only, never relations",
        "pairs": len(pairs),
        "gating_failures": len(gating_failed),
        "failed_pairs": failures,
        "pair_records": pairs,
        "not_evidence_for": ["detection_correctness", "field_accuracy"],
        "converts_to": [],
    }


def _pointer_section(
    evidence_kind: str,
    validation_domain: str,
    gate_command: str,
    interpretation: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "evidence_kind": evidence_kind,
        "validation_domain": validation_domain,
        "status": status,
        "gating": False,
        "gate_command": gate_command,
        "interpretation": interpretation,
        "not_recomputed_here": True,
        "converts_to": [],
    }
    if extra:
        section.update(extra)
    return section


def assemble_science_report(
    mathematical: dict[str, Any],
    synthetic: dict[str, Any],
    adversarial: dict[str, Any],
    metamorphic: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the seven-section report grouped by evidence kind.

    No scores, no aggregates across evidence classes. The top-level
    verdict is a conjunction of gating sections only.
    """
    sections = {
        "mathematical": mathematical,
        "synthetic": synthetic,
        "adversarial": adversarial,
        "metamorphic": metamorphic,
        "reference_compatibility": _pointer_section(
            EVIDENCE_KIND_REFERENCE,
            "vendor_reference",
            "pytest tests/validation/test_release_gates.py -q",
            "Vendor 9/9 and hard-18 establish reference compatibility with "
            "documented vendor examples and frozen hard synthetic families. "
            "They are not field accuracy and not scientific correctness.",
            "pointer",
        ),
        "regression_protection": _pointer_section(
            EVIDENCE_KIND_REGRESSION,
            "golden_equivalence",
            "pytest tests/validation/test_golden_outputs.py "
            "tests/validation/test_equivalence.py -q",
            "Golden hashes and cross-tree equivalence establish behavioral "
            "continuity. A passing gate means protected behavior did not "
            "change; it does not prove scientific truth.",
            "pointer",
        ),
        "field_validation": _pointer_section(
            EVIDENCE_KIND_EMPIRICAL,
            "independent_field",
            "groundscan validate field <manifest.json>",
            "No independently verified field-ground-truth dataset has been "
            "evaluated. Field accuracy, field recall, field precision, and "
            "field false-positive rate are UNKNOWN. This is a scope "
            "statement, not a failure.",
            "unknown",
            extra={
                "manifest_schema": "field_ground_truth.schema.json",
                "not_evidence_for": ["anything: no field data exists"],
            },
        ),
    }
    gating = ["mathematical", "synthetic", "adversarial", "metamorphic"]
    gating = [k for k in gating if sections[k].get("gating", False)]
    verdict = "pass" if all(sections[k].get("status") == "pass" for k in gating) else "fail"
    return {
        "report": "science_validation",
        "science_schema_version": SCIENCE_SCHEMA_VERSION,
        "verdict": verdict,
        "verdict_basis": gating,
        "grouped_by_evidence_kind": {
            "scientific": ["mathematical", "synthetic", "adversarial", "metamorphic"],
            "reference": ["reference_compatibility"],
            "regression": ["regression_protection"],
            "empirical": ["field_validation"],
        },
        "operating_point": _operating_point_for_report(),
        "sections": sections,
        "provenance": _provenance(),
    }


def _operating_point_for_report() -> dict[str, Any]:
    from .synthetic_core.oracles import operating_point_record

    return operating_point_record()


def run_science(out_dir: str | Path, *, mode: str = "smoke") -> dict[str, Any]:
    """Run the science validation mode end to end and write artifacts."""
    if mode not in ("smoke", "full"):
        raise ValueError("mode must be 'smoke' or 'full'")
    out_dir = Path(out_dir)
    mathematical = run_mathematical()
    synthetic = run_synthetic(out_dir / "synthetic", mode=mode)
    adversarial = run_adversarial(out_dir / "adversarial")
    metamorphic = run_metamorphic(out_dir / "metamorphic")
    report = assemble_science_report(mathematical, synthetic, adversarial, metamorphic)
    report["mode"] = mode
    paths = write_science_report(report, out_dir)
    report["_artifacts"] = {k: str(v) for k, v in paths.items()}
    return report

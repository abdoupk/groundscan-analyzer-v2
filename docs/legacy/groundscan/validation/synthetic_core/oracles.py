"""Frozen synthetic-oracle constants and evaluation entry points (science framework).

The generator is NOT here: scans come from
:mod:`groundscan.validation.synthetic_core.core` and matching/counting
reuses :mod:`groundscan.validation.synthetic_core.benchmark_large`
(global one-to-one Hungarian assignment). This module only freezes the
*meaning* of a pass: matching policy, tolerances, operating-point
provenance, per-family floors, and auxiliary polarity/orientation rules.

Versioning rule: any change to a floor, tolerance, allowance, or the
pattern map requires bumping :data:`ORACLE_VERSION` and recording the
reason. Silent re-baselining is a contract violation, not maintenance.

Everything measured here describes behavior under stated controlled
conditions. No field claim of any kind may be derived from it.
"""

from __future__ import annotations

import math
from typing import Any

from ...gates.screening import DEFAULT_SCREENING_POLICY, screen_candidates
from .benchmark_large import evaluate_case, match_candidates

#: Oracle version. Bump on any floor/tolerance/allowance/pattern-map change.
ORACLE_VERSION = "1.0"

#: XY matching gate in meters. Same value as the field-manifest default
#: tolerance so synthetic and (future) field matching stay commensurable.
MATCH_DISTANCE_TOLERANCE_M = 3.0


def operating_point_record(policy: Any = None) -> dict[str, Any]:
    """Describe the screening operating point as provenance, not science.

    The threshold is read from the policy object (default: the production
    default policy). It is a documented software default, not a validated
    detection threshold.
    """
    active = DEFAULT_SCREENING_POLICY if policy is None else policy
    return {
        "policy_version": str(active.version),
        "primary_threshold": float(active.primary_threshold),
        "rescue_band": [float(active.rescue_lower), float(active.rescue_upper)],
        "status": "documented-default",
        "scientific_claim": "none: software retention default (see groundscan/gates/screening.py)",
    }


def expected_polarity_sign(kind: str) -> str | None:
    """Expected response sign for synthetic kinds with unambiguous polarity.

    Returns None where the engine's mixed/ambiguous output is legitimate
    (geology, multi-lobe structures) and must not be scored.
    """
    if kind.startswith("positive") or kind == "linear_positive":
        return "positive"
    if kind.startswith("negative") or kind in {"cavity", "negative_cavity"}:
        return "negative"
    if kind in {"tunnel", "linear_negative"}:
        return "negative"
    return None


def orientation_relevant(kind: str) -> bool:
    """Only linear features carry a meaningful orientation to evaluate."""
    return kind in {"tunnel", "linear_negative", "linear_positive"}


def angular_error_mod180(a_deg: float, b_deg: float) -> float:
    """Absolute angular difference modulo 180 degrees (linear features)."""
    delta = abs(float(a_deg) - float(b_deg)) % 180.0
    return float(min(delta, 180.0 - delta))


def evaluate_oracle_case(
    candidates: list,
    truth: dict,
    *,
    case_id: str,
    family: str,
    split: str = "science",
    policy: Any = None,
) -> dict[str, Any]:
    """Evaluate retained candidates against synthetic truth with the frozen oracle.

    Steps: retain at the operating point -> Hungarian one-to-one match
    (pattern-compatible, distance-gated) -> count + error metrics ->
    polarity/orientation auxiliaries on matched pairs only.
    """
    active = DEFAULT_SCREENING_POLICY if policy is None else policy
    retained = screen_candidates(candidates, active)
    row = evaluate_case(
        retained,
        truth,
        split=split,
        case_id=case_id,
        family=family,
        distance_tolerance_m=MATCH_DISTANCE_TOLERANCE_M,
    )
    targets = list(truth.get("targets", []))
    matches, _, _ = match_candidates(retained, targets, MATCH_DISTANCE_TOLERANCE_M)
    polarity_checked = 0
    polarity_correct = 0
    orientation_errors: list[float] = []
    for ti, ci, _ in matches:
        target = targets[ti]
        cand = retained[ci]
        kind = str(target.get("kind", ""))
        pattern = str(getattr(cand, "pattern_hypothesis", ""))
        expected_sign = expected_polarity_sign(kind)
        # Merged dipolar responses legitimately carry mixed polarity, so the
        # sign check applies only to non-dipole matches with unambiguous truth.
        if expected_sign is not None and pattern != "dipolar-response":
            polarity_checked += 1
            if str(getattr(cand, "polarity", "")) == expected_sign:
                polarity_correct += 1
        if orientation_relevant(str(target.get("kind", ""))):
            orientation_errors.append(
                angular_error_mod180(
                    float(getattr(cand, "orientation_deg", float("nan"))),
                    float(target.get("orientation_deg", 0.0)),
                )
            )
    finite_orientation = [e for e in orientation_errors if math.isfinite(e)]
    return {
        "oracle_version": ORACLE_VERSION,
        "case_id": case_id,
        "family": family,
        "split": split,
        "targets": row.targets,
        "candidates_retained": row.candidates,
        "matched_targets": row.matched_targets,
        "false_positives": row.false_positives,
        "missed_targets": row.missed_targets,
        "oversegmentation": row.oversegmentation,
        "undersegmentation": row.undersegmentation,
        "exact_target_count": row.exact_target_count,
        "synthetic_recall": row.recall,
        "synthetic_precision": row.precision,
        "synthetic_center_error_m": row.center_error_m,
        "synthetic_depth_error_m": row.depth_error_m,
        "depth_evaluable_matches": row.depth_evaluable_matches,
        "polarity_checked": polarity_checked,
        "polarity_correct": polarity_correct,
        "orientation_errors_deg": [round(e, 3) for e in finite_orientation],
        "operating_point": operating_point_record(active),
    }


# ---------------------------------------------------------------------------
# Frozen per-family floors (measured deterministic behavior, ORACLE_VERSION 1.0)
# ---------------------------------------------------------------------------
# Meaning: the science suite fails if a family falls below its floor.
# Recall/precision floors equal the measured seeded values exactly (any drop
# is a real behavior change); error ceilings carry explicit margin
# (+1.0 m center, +2.0 m depth, rounded to 0.5) because localization noise
# is expected to vary within the matching gate. Floors are regression
# tripwires for specified behavior, not accuracy claims.

FAMILY_FLOORS: dict[str, dict[str, float]] = {
    "positive_compact": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.5,
        "max_false_positives": 0.0,
    },
    "negative_cavity": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.0,
        "max_false_positives": 0.0,
    },
    "linear_tunnel": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 3.5,
        "max_false_positives": 0.0,
        "max_orientation_error_deg": 5.0,
    },
    "geological_broad": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 2.0,
        "max_depth_error_m": 6.0,
        "max_false_positives": 0.0,
    },
    "mineralization_elevated": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.5,
        "max_false_positives": 0.0,
    },
    "mineralization_high": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.0,
        "max_false_positives": 0.0,
    },
    "no_target_noise": {"min_recall": 1.0, "min_precision": 1.0, "max_false_positives": 0.0},
    "multiple_targets": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.0,
        "max_false_positives": 0.0,
    },
    # Known limitation, consistent with the fast synthetic-smoke pin
    # (close_targets recall >= 0.5): one of the two close targets merges.
    "close_targets": {
        "min_recall": 0.5,
        "min_precision": 1.0,
        "max_center_error_m": 4.0,
        "max_depth_error_m": 5.0,
        "max_false_positives": 0.0,
    },
    "overlapping_targets": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 2.0,
        "max_depth_error_m": 3.5,
        "max_false_positives": 0.0,
    },
    "rotated_tunnel": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 3.0,
        "max_false_positives": 0.0,
        "max_orientation_error_deg": 5.0,
    },
    "void_plus_geology": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 2.5,
        "max_depth_error_m": 3.5,
        "max_false_positives": 0.0,
    },
    "ladder_depth_2": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.5,
        "max_false_positives": 0.0,
    },
    "ladder_depth_6": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 3.5,
        "max_false_positives": 0.0,
    },
    "ladder_depth_10": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 2.5,
        "max_false_positives": 0.0,
    },
    "ladder_amp_8": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 3.5,
        "max_false_positives": 0.0,
    },
    "ladder_amp_14": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.0,
        "max_false_positives": 0.0,
    },
    "ladder_amp_22": {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "max_center_error_m": 1.5,
        "max_depth_error_m": 4.5,
        "max_false_positives": 0.0,
    },
}


def check_oracle_result(result: dict[str, Any]) -> list[str]:
    """Compare one oracle result against its frozen family floor.

    Returns failure strings (empty means the floor holds). Polarity must be
    perfect wherever the oracle checks it; orientation errors must respect
    the frozen ceiling. NaN error means (no evaluable matches) skip the
    corresponding ceiling.
    """
    failures: list[str] = []
    family = str(result.get("family", ""))
    floor = FAMILY_FLOORS.get(family)
    if floor is None:
        return [f"no frozen floor for family {family!r} (oracle {ORACLE_VERSION})"]
    if float(result.get("synthetic_recall", -1.0)) < float(floor["min_recall"]) - 1e-9:
        failures.append(f"recall {result.get('synthetic_recall')} < floor {floor['min_recall']}")
    if float(result.get("synthetic_precision", -1.0)) < float(floor["min_precision"]) - 1e-9:
        failures.append(
            f"precision {result.get('synthetic_precision')} < floor {floor['min_precision']}"
        )
    center = float(result.get("synthetic_center_error_m", float("nan")))
    if (
        "max_center_error_m" in floor
        and math.isfinite(center)
        and center > float(floor["max_center_error_m"]) + 1e-9
    ):
        failures.append(f"center error {center} > ceiling {floor['max_center_error_m']}")
    depth = float(result.get("synthetic_depth_error_m", float("nan")))
    if (
        "max_depth_error_m" in floor
        and math.isfinite(depth)
        and depth > float(floor["max_depth_error_m"]) + 1e-9
    ):
        failures.append(f"depth error {depth} > ceiling {floor['max_depth_error_m']}")
    if int(result.get("false_positives", 0)) > int(floor["max_false_positives"]):
        failures.append(
            f"false positives {result.get('false_positives')} > allowance "
            f"{floor['max_false_positives']}"
        )
    if int(result.get("polarity_correct", 0)) != int(result.get("polarity_checked", 0)):
        failures.append(
            f"polarity {result.get('polarity_correct')}/{result.get('polarity_checked')}"
        )
    orientation = [float(e) for e in result.get("orientation_errors_deg", [])]
    if "max_orientation_error_deg" in floor and orientation:
        worst = max(orientation)
        if worst > float(floor["max_orientation_error_deg"]) + 1e-9:
            failures.append(
                f"orientation error {worst} > ceiling {floor['max_orientation_error_deg']}"
            )
    return failures


# ---------------------------------------------------------------------------
# Adversarial/negative classification (ORACLE_VERSION 1.0)
# ---------------------------------------------------------------------------
# Four bins with unambiguous gate semantics:
# - EXPECTED_BEHAVIOR: silent/blocked exactly as specified. Passes.
# - DOCUMENTED_LIMITATION: specified behavior that is weaker than desired
#   (structured input retains review candidates) but stays within the
#   frozen allowance. PASSES the gate AND is entered into the report's
#   limitation register with its allowance, so it remains visible and
#   tracked. It must never be silently reclassified as EXPECTED_BEHAVIOR
#   (that would hide a known weakness), and exceeding the allowance is a
#   FALSE_POSITIVE, never "a louder limitation".
# - FALSE_POSITIVE: retention above the frozen allowance. Fails.
# - IMPLEMENTATION_REGRESSION: crash, non-finite output, or a required
#   quality-gate block that stopped firing. Fails.
# Allowances are frozen maxima from measured seeded runs; raising one
# requires an ORACLE_VERSION bump, never a silent edit.

EXPECTED_BEHAVIOR = "expected_behavior"
DOCUMENTED_LIMITATION = "documented_limitation"
FALSE_POSITIVE = "false_positive"
IMPLEMENTATION_REGRESSION = "implementation_regression"

NEGATIVE_FAMILIES: dict[str, dict[str, Any]] = {
    # Pure white noise: the engine stays silent.
    "white_noise_empty": {
        "class": EXPECTED_BEHAVIOR,
        "max_retained": 0,
        "expects_block": False,
        "notes": "Unstructured noise produces no retained candidates.",
    },
    # Extreme planar gradient: background absorbs almost everything; one
    # retained candidate was measured, so structured ramps are a documented
    # limitation, not proof of a target.
    "gradient_extreme": {
        "class": DOCUMENTED_LIMITATION,
        "max_retained": 1,
        "expects_block": False,
        "notes": "Strong gradients can leave one retained candidate for review.",
    },
    # Correlated noise: the object-mimic. Short lengths stay silent; the
    # broadest field (L8) retains review candidates within allowance.
    "smooth_noise": {
        "class": DOCUMENTED_LIMITATION,
        "max_retained": 3,
        "expects_block": False,
        "notes": "Smooth structure may read as object-like; bounded by allowance.",
    },
    "periodic_stripes": {
        "class": EXPECTED_BEHAVIOR,
        "max_retained": 0,
        "expects_block": False,
        "notes": "Periodic stripes are absorbed; no retained candidates.",
    },
    "nan_block": {
        "class": EXPECTED_BEHAVIOR,
        "max_retained": 0,
        "expects_block": False,
        "notes": "Contiguous NaN block stays finite and silent; never a crash.",
    },
    "missing_lines": {
        "class": EXPECTED_BEHAVIOR,
        "max_retained": 0,
        "expects_block": False,
        "notes": "Dropped adjacent lines degrade gracefully without candidates.",
    },
}


def classify_negative(
    family: str,
    retained: int,
    *,
    crashed: bool = False,
    blocked: bool = False,
    nonfinite_outputs: int = 0,
) -> tuple[str, str]:
    """Classify one negative-case outcome into the four-bin model.

    Returns (bin, detail). EXPECTED_BEHAVIOR and DOCUMENTED_LIMITATION
    (within allowance) pass; FALSE_POSITIVE and IMPLEMENTATION_REGRESSION
    fail. A limitation verdict additionally obliges the caller to record
    the case in the limitation register -- passing never means "no action".
    """
    spec = NEGATIVE_FAMILIES.get(family)
    if spec is None:
        return IMPLEMENTATION_REGRESSION, f"unknown negative family {family!r}"
    if crashed:
        return IMPLEMENTATION_REGRESSION, "engine raised on hostile input"
    if int(nonfinite_outputs) > 0:
        return IMPLEMENTATION_REGRESSION, "non-finite scores reached retained output"
    if bool(spec["expects_block"]) and not blocked:
        return IMPLEMENTATION_REGRESSION, "required quality-gate block did not fire"
    if int(retained) > int(spec["max_retained"]):
        return (
            FALSE_POSITIVE,
            f"retained {retained} > frozen allowance {spec['max_retained']}",
        )
    if int(retained) == 0:
        # No weakness manifested: silence is expected behavior even inside
        # a limitation-class family. LIMITATION requires retained review
        # candidates, not merely a hostile input.
        return EXPECTED_BEHAVIOR, f"silent on {family} (no weakness manifested)"
    if spec["class"] == DOCUMENTED_LIMITATION:
        return DOCUMENTED_LIMITATION, str(spec["notes"])
    return EXPECTED_BEHAVIOR, str(spec["notes"])


def negative_verdict_passes(binned: str) -> bool:
    """Pass bins for negative outcomes (allowance-respecting behavior)."""
    return binned in (EXPECTED_BEHAVIOR, DOCUMENTED_LIMITATION)

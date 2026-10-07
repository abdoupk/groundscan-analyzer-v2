"""Candidate quality, false-positive risk and review provenance.

The scores in this module are screening heuristics.  They are deliberately
separate from ``evidence_score`` and are not calibrated probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .._util import bounded01
from ..models import Candidate
from ..soil.context import (
    MINERALIZATION_FLAG_THRESHOLD,
    MINERALIZATION_HIGH_THRESHOLD,
    mineralization_risk_from_pct,
)


@dataclass(frozen=True)
class QualityAssessment:
    quality_score: float
    false_positive_risk: float
    screening_score: float
    review_status: str
    flags: tuple[str, ...]


MINERALIZATION_QUALITY_PENALTY = 0.05
MINERALIZATION_SCREENING_PENALTY = 0.03


# ---------------------------------------------------------------------------
# Stage 2 (S09 / contract K11): the declared per-field non-finite policy
# ---------------------------------------------------------------------------
# Every field a gate compares against is resolved to a *declared* value before
# any comparison, so a non-finite input can never skip its own branch. The
# defect this fixes is not a wrong number, it is a skipped decision: with
# ``np.clip`` a NaN field makes every ``field < threshold`` and
# ``field >= threshold`` test False, so the penalty branch and the flag both
# silently did not fire and the candidate was reported at its strongest
# possible outcome.
#
# Each entry is ``(role, fallback, flag)``. Roles are exactly the three the
# contract names, and the fallback is the value that role implies:
#
#   worst   absence is adverse          -> the value that scores worst
#   neutral genuinely indeterminate     -> 0.5, the midpoint
#   flagged a number is impossible without a claim -> the value plus a flag
#
# Direction matters and is stated per field: for a *support* field 0.0 is the
# adverse extreme, for a *risk* field (``artifact_score``) 1.0 is, and for an
# *adverse-high* field (``boundary_contact_ratio``) 1.0 is. Resolving a risk
# field to its favourable extreme is a policy inversion, which is why
# ``artifact_score`` declares 1.0 and not the 0.0 a bare ``unknown="worst"``
# would give.
#
# A ``flag`` marks the value as not measured, so the substitution is visible in
# the report instead of being indistinguishable from a real measurement. Flags
# never enter the score, so declaring a policy invents no weight.
NONFINITE_POLICY: dict[str, tuple[str, float, str | None]] = {
    # support fields: 0.0 is the adverse extreme
    "evidence_score": ("worst", 0.0, None),
    "multiscale_persistence": ("worst", 0.0, None),
    "geometry_quality": ("worst", 0.0, "geometry-quality-unmeasured"),
    "multiscan_signal_consistency": ("worst", 0.0, "signal-consistency-unmeasured"),
    "multi_scan_evidence_score": ("worst", 0.0, None),
    "detection_rate": ("worst", 0.0, None),
    "polarity_consistency": ("worst", 0.0, None),
    "depth_stability_score": ("worst", 0.0, None),
    # genuinely indeterminate: the midpoint
    "position_stability": ("neutral", 0.5, None),
    "registration_consistency": ("neutral", 0.5, None),
    "separation_quality": ("neutral", 0.5, None),
    # risk / adverse-high fields: 1.0 is the adverse extreme
    "artifact_score": ("worst", 1.0, "artifact-score-unmeasured"),
    "boundary_contact_ratio": ("worst", 1.0, "boundary-contact-unmeasured"),
    # adverse-high: uncertainty 1.0 is "maximum uncertainty", the worst case
    "evidence_uncertainty": ("worst", 1.0, "evidence-uncertainty-unmeasured"),
    # flagged: worst would double-penalise a data-availability problem as if it
    # were a hazard, so this one reports the midpoint plus a flag.
    "mineralization_risk": ("neutral", 0.5, "mineralization-risk-unmeasured"),
}


def resolve_gate_input(candidate: Candidate, field: str, *, derive: Any = None) -> float:
    """Resolve one gate input to a declared finite value in [0, 1].

    Every comparison in this module goes through here, so no non-finite value
    can reach a comparison. The measured value passes through unchanged; only a
    non-finite or unparseable value is replaced, and then only by the value its
    declared role implies.

    *derive* supplies the value to use when the attribute is absent entirely
    (a legacy path, e.g. mineralization risk derived from the soil percentage).
    """
    role, _fallback, _flag = NONFINITE_POLICY[field]
    raw = getattr(candidate, field, None)
    if raw is None and derive is not None:
        raw = derive()
    risk = field in (
        "artifact_score",
        "mineralization_risk",
        "boundary_contact_ratio",
        "evidence_uncertainty",
    )
    return bounded01(raw, unknown="neutral" if role == "neutral" else "worst", risk=risk)


def unmeasured_fields(candidate: Candidate) -> list[str]:
    """Names of gate inputs whose value is not a measurement.

    Drives the availability flags. Exposed so the report can distinguish
    "this candidate scored 0 because there was no persistence evidence" from
    "this candidate scored 0 because persistence was never measured".
    """
    out: list[str] = []
    for field, (_role, _fallback, flag) in NONFINITE_POLICY.items():
        if flag is None:
            continue
        raw = getattr(candidate, field, None)
        try:
            measured = raw is not None and np.isfinite(float(raw))
        except (TypeError, ValueError):
            measured = False
        if not measured:
            out.append(field)
    return out


def _finite_score(value: float, *, name: str, flags: list[str]) -> float:
    """Clip a derived score into [0, 1] and guarantee it is finite.

    Backstop for the K11 output invariant. A non-finite score would be
    uncomparable by every consumer, and the direction chosen here is the
    unevidenced one: 0.0 quality, and a flag recording that it happened.
    """
    out = float(np.clip(value, 0.0, 1.0))
    if not np.isfinite(out):
        flag = f"{name.replace('_', '-')}-non-finite"
        if flag not in flags:
            flags.append(flag)
        return 0.0
    return out


def assess_candidate_quality(candidate: Candidate) -> Candidate:
    """Attach auditable quality/risk fields without removing the candidate."""
    flags: list[str] = []
    # Audit fix: every gate input is resolved through the declared non-finite
    # policy (see NONFINITE_POLICY) instead of np.clip. Two reasons, both
    # contract-driven:
    #   1. np.clip passes NaN through, so `support`/`penalties`/the scores all
    #      became NaN.
    #   2. Worse, every `field < threshold` / `field >= threshold` test is False
    #      for NaN, so each of those fields silently skipped its own penalty
    #      branch and flag. The candidate was then reported at the strongest
    #      possible outcome for a field nobody measured.
    # `artifact_score` is a RISK (0 = clean), so its unknown resolves to 1.0, the
    # adverse extreme -- not the 0.0 a bare worst-role would give.
    # The availability flags are recorded but never scored, so declaring a policy
    # adds no weight and changes no threshold.
    unmeasured = unmeasured_fields(candidate)
    for field in unmeasured:
        flag = NONFINITE_POLICY[field][2]
        if flag is not None:
            flags.append(flag)

    artifact = resolve_gate_input(candidate, "artifact_score")
    boundary = resolve_gate_input(candidate, "boundary_contact_ratio")
    persistence = resolve_gate_input(candidate, "multiscale_persistence")
    geometry = resolve_gate_input(candidate, "geometry_quality")
    position = resolve_gate_input(candidate, "position_stability")
    registration = resolve_gate_input(candidate, "registration_consistency")
    signal = resolve_gate_input(candidate, "multiscan_signal_consistency")
    depth = resolve_gate_input(candidate, "depth_stability_score")
    separation = resolve_gate_input(candidate, "separation_quality")
    # Mineralization is now owned by the unified Soil Context layer. The legacy
    # penalty values are intentionally unchanged so the detector baseline is
    # behaviorally preserved while the source of the context is centralized.
    # The `derive` fallback is the pre-existing legacy path (attribute absent ->
    # compute from the soil percentage); it is preserved unchanged.
    mineralization_risk = resolve_gate_input(
        candidate,
        "mineralization_risk",
        derive=lambda: mineralization_risk_from_pct(getattr(candidate, "mineralization_pct", None)),
    )
    evidence = resolve_gate_input(candidate, "evidence_score")
    uncertainty = (
        resolve_gate_input(candidate, "evidence_uncertainty")
        if candidate.multi_scan_status == "multi-scan" and candidate.effective_scan_count >= 2
        else 0.0
    )
    multi_evidence = (
        resolve_gate_input(candidate, "multi_scan_evidence_score")
        if candidate.multi_scan_status == "multi-scan" and candidate.effective_scan_count >= 2
        else 0.0
    )
    detection_rate = resolve_gate_input(candidate, "detection_rate")

    # v0.4.2 (audit F-13): support deliberately carries evidence (0.45):
    # the review_status gates below judge quality AND evidence jointly, and
    # the screening formula re-weights evidence on top, so evidence enters
    # screening twice (effective weight ~0.68). Removing either occurrence
    # was measured to collapse screening selection on vendor data (9 -> 0
    # above the 0.70 primary band), i.e. it would silently de-calibrate the
    # policy bands that were tuned on synthetic data. Per the audit roadmap
    # the formula stays until bands can be recalibrated against independent
    # field data; the double count is disclosed here instead of hidden.
    from .thresholds import QUALITY_PENALTY_WEIGHTS, QUALITY_SUPPORT_WEIGHTS, SCREENING_WEIGHTS

    _sw, _pw, _scw = QUALITY_SUPPORT_WEIGHTS, QUALITY_PENALTY_WEIGHTS, SCREENING_WEIGHTS
    support = (
        _sw["evidence"] * evidence
        + _sw["persistence"] * persistence
        + _sw["geometry"] * geometry
        + _sw["position"] * position
        + _sw["signal"] * signal
        + _sw["registration"] * registration
        + _sw["multi_evidence"] * multi_evidence
    )
    penalties = (
        _pw["artifact"] * artifact
        + _pw["boundary"] * boundary
        + _pw["uncertainty"] * uncertainty
        + MINERALIZATION_QUALITY_PENALTY * mineralization_risk
    )

    if not getattr(candidate, "metric_geometry_reliable", True):
        flags.append("non-metric-geometry")
        if geometry < 0.50:
            penalties += 0.04
    if candidate.multi_scan_status == "multi-scan":
        if registration < 0.50:
            penalties += 0.12
            flags.append("weak-registration")
        elif registration < 0.70:
            penalties += 0.05
            flags.append("registration-caution")
    if mineralization_risk >= MINERALIZATION_HIGH_THRESHOLD / 100.0:
        flags.append("high-mineralization-risk")
    elif mineralization_risk >= MINERALIZATION_FLAG_THRESHOLD / 100.0:
        flags.append("elevated-mineralization-risk")
    if candidate.scan_count <= 1:
        penalties += 0.16
        flags.append("single-scan")
    if uncertainty >= 0.45:
        flags.append("high-evidence-uncertainty")
    elif detection_rate < 0.5:
        penalties += 0.11
        flags.append("low-detection-rate")
    if persistence < 0.34:
        penalties += 0.08
        flags.append("weak-multiscale-persistence")
    if artifact >= 0.50:
        flags.append("artifact-concern")
    if boundary >= 0.45:
        flags.append("boundary-contact")
    if candidate.polarity == "mixed":
        penalties += 0.04
        flags.append("mixed-polarity")
    if depth < 0.40:
        penalties += 0.04
        flags.append("unstable-depth")
    if candidate.separation_status == "decomposed-consensus":
        penalties += 0.05 * (1.0 - separation)
        flags.append("decomposition-hypothesis")
    if geometry < 0.40:
        flags.append("weak-geometry")

    # Hard output invariant (contract K11): the two scores are never non-finite.
    # Every input above is already resolved, so this is a backstop rather than
    # the mechanism -- but a score that cannot be compared cannot be gated, and a
    # NaN score would be read as "no information" by whatever consumed it. If it
    # ever fires, the candidate is treated as unevidenced rather than ideal.
    quality = _finite_score(support - penalties, name="quality_score", flags=flags)
    fp_risk = _finite_score(1.0 - quality, name="false_positive_risk", flags=flags)
    # Screening score rewards evidence and quality while explicitly discounting
    # artifact/boundary concerns. It is a sort/filter aid, not a probability.
    # v0.4.2 (audit F-13): evidence enters here directly AND through quality
    # (see the support note above). This second channel is intentional for
    # now: screening is evidence-forward by design, and the 0.70/0.65 bands
    # were calibrated on this formula's output distribution.
    screening = _finite_score(
        _scw["evidence"] * evidence
        + _scw["quality"] * quality
        + _scw["non_artifact"] * (1.0 - artifact)
        - MINERALIZATION_SCREENING_PENALTY * mineralization_risk,
        name="screening_score",
        flags=flags,
    )

    if artifact >= 0.70 or (boundary >= 0.60 and quality < 0.55):
        status = "artifact-concern"
    elif uncertainty >= 0.65:
        status = "high-uncertainty"
    elif candidate.separation_status == "decomposed-consensus":
        status = "review-decomposition"
    elif quality < 0.40 or evidence < 0.30:
        status = "insufficient-evidence"
    elif quality < 0.65 or candidate.scan_count <= 1:
        status = "review"
    else:
        status = "supported-pattern"

    # Preserve provenance markers across re-assessment so a later quality
    # pass cannot silently drop them. dipole-pair set the precedent; the
    # rescue marker is the same kind (issue #23: assess recomputation dropped
    # it before it could reach the candidate).
    for old_flag in getattr(candidate, "quality_flags", None) or []:
        if old_flag in ("dipole-pair", "secondary-extraction-rescue") and old_flag not in flags:
            flags.append(old_flag)
    # Pure transform (M7): the input candidate is never mutated.
    return candidate.with_updates(
        quality_score=round(quality, 3),
        false_positive_risk=round(fp_risk, 3),
        screening_score=round(screening, 3),
        review_status=status,
        mineralization_risk=round(mineralization_risk, 3),
        quality_flags=flags,
    )


def quality_summary(candidates: list[Candidate]) -> dict[str, object]:
    """Return aggregate screening statistics while retaining all candidates."""
    counts: dict[str, int] = {}
    operational_counts: dict[str, int] = {}
    for c in candidates:
        counts[c.review_status] = counts.get(c.review_status, 0) + 1
        op = str(getattr(c, "operational_status", "clear"))
        operational_counts[op] = operational_counts.get(op, 0) + 1
    return {
        "candidate_count": len(candidates),
        "status_counts": counts,
        "operational_status_counts": operational_counts,
        "mean_quality_score": round(
            float(np.mean([c.quality_score for c in candidates])) if candidates else 0.0, 3
        ),
        "mean_false_positive_risk": round(
            float(np.mean([c.false_positive_risk for c in candidates])) if candidates else 0.0, 3
        ),
        "semantics": "heuristic screening metrics; false_positive_risk is not a probability",
        "mean_evidence_uncertainty": round(
            float(np.mean([c.evidence_uncertainty for c in candidates])) if candidates else 0.0, 3
        ),
    }

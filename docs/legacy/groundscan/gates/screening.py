"""Auditable candidate retention policy for GroundScan Analyzer.

Screening is intentionally separate from anomaly detection.  The rescue band
only keeps a small set of candidates that narrowly miss the primary screening
threshold but retain strong local evidence and low boundary/artifact concerns.
All values are deterministic heuristics, not probabilities or field-validated
confidence intervals.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from ..models import Candidate


@dataclass(frozen=True)
class ScreeningPolicy:
    """Post-analysis candidate retention policy.

    The default values were selected on the calibration portion of the
    deterministic v0.2.7 synthetic benchmark and then evaluated unchanged on
    the holdout portion.  They are software-validation parameters only.
    """

    primary_threshold: float = 0.70
    rescue_enabled: bool = True
    rescue_lower: float = 0.65
    rescue_upper: float = 0.70
    rescue_min_persistence: float = 0.50
    rescue_max_boundary: float = 0.45
    rescue_max_artifact: float = 0.50
    rescue_min_anomaly: float = 4.5
    version: str = "rescue-screening"

    def __post_init__(self) -> None:
        if not 0.0 <= self.primary_threshold <= 1.0:
            raise ValueError("primary_threshold must be in [0, 1]")
        if not 0.0 <= self.rescue_lower <= self.rescue_upper <= 1.0:
            raise ValueError("rescue band must satisfy 0 <= lower <= upper <= 1")
        for name in ("rescue_min_persistence", "rescue_max_boundary", "rescue_max_artifact"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.rescue_min_anomaly < 0:
            raise ValueError("rescue_min_anomaly must be >= 0")


DEFAULT_SCREENING_POLICY = ScreeningPolicy()


def rescue_eligible(
    candidate: Candidate, policy: ScreeningPolicy = DEFAULT_SCREENING_POLICY
) -> bool:
    """Return whether a candidate qualifies for the calibrated rescue band."""
    if not policy.rescue_enabled:
        return False
    s = float(candidate.screening_score)
    return bool(
        policy.rescue_lower <= s < policy.rescue_upper
        and float(candidate.multiscale_persistence) >= policy.rescue_min_persistence
        and float(candidate.boundary_contact_ratio) < policy.rescue_max_boundary
        and float(candidate.artifact_score) < policy.rescue_max_artifact
        and float(candidate.anomaly_score) >= policy.rescue_min_anomaly
    )


def retention_reason(
    candidate: Candidate, policy: ScreeningPolicy = DEFAULT_SCREENING_POLICY
) -> str:
    """Explain why a candidate is retained by the screening policy."""
    if float(candidate.screening_score) >= policy.primary_threshold:
        return "primary-threshold"
    if rescue_eligible(candidate, policy):
        return "soft-rescue"
    return "below-threshold"


def screen_candidates(
    candidates: Iterable[Candidate],
    policy: ScreeningPolicy = DEFAULT_SCREENING_POLICY,
) -> list[Candidate]:
    """Return retained candidates with explicit screening provenance.

    The input candidates are not mutated.  Returned objects are shallow copies
    carrying ``screening_rescue_applied``, ``screening_selection_reason`` and
    ``screening_policy_version``.
    """
    retained: list[Candidate] = []
    for candidate in candidates:
        reason = retention_reason(candidate, policy)
        if reason == "below-threshold":
            continue
        retained.append(
            replace(
                candidate,
                screening_rescue_applied=(reason == "soft-rescue"),
                screening_selection_reason=reason,
                screening_policy_version=policy.version,
            )
        )
    return retained


def screening_summary(
    candidates: Iterable[Candidate], policy: ScreeningPolicy = DEFAULT_SCREENING_POLICY
) -> dict[str, object]:
    """Summarize retention without exposing the heuristic as probability."""
    rows = list(candidates)
    selected = screen_candidates(rows, policy)
    rescue_count = sum(1 for c in selected if c.screening_rescue_applied)
    return {
        "policy_version": policy.version,
        "primary_threshold": policy.primary_threshold,
        "rescue_enabled": policy.rescue_enabled,
        "rescue_band": [policy.rescue_lower, policy.rescue_upper],
        "input_candidates": len(rows),
        "selected_candidates": len(selected),
        "rescued_candidates": rescue_count,
        "semantics": "deterministic screening retention; not probability of a target/material",
    }

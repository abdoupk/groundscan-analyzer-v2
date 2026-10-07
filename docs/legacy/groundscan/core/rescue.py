"""Conservative secondary extraction channel for GroundScan Analyzer v0.2.60.

The default detector remains authoritative.  The optional channel uses a median-
background pass only to propose broad geological-compatible candidates that the
baseline detector did not represent locally.  It is intentionally conservative
and is off by default until validated on the frozen benchmark and field data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import hypot

from ..gates.quality import assess_candidate_quality
from ..models import Candidate
from .anomaly import detect_anomalies, detect_artifacts
from .classify import classify_candidate
from .grid import Grid2D
from .shape import extract_candidates


@dataclass(frozen=True, slots=True)
class ExtractionRescuePolicy:
    """Guardrails for the optional secondary geology extraction channel."""

    mode: str = "off"
    background_method: str = "median"
    threshold: float = 3.0
    min_size: int = 3
    scales: tuple[int, ...] = (3, 5, 9, 15)
    min_anomaly_score: float = 4.5
    min_broadness_score: float = 0.55
    max_artifact_score: float = 0.25
    max_boundary_contact_ratio: float = 0.40
    exclusion_radius: float = 3.0

    def validate(self) -> None:
        if self.mode not in {"off", "conservative-geology"}:
            raise ValueError("unsupported extraction_rescue mode")
        if self.background_method != "median":
            raise ValueError("conservative-geology currently requires median background")
        if self.threshold <= 0 or self.min_size < 1 or self.exclusion_radius <= 0:
            raise ValueError("invalid extraction rescue numeric policy")
        if not self.scales:
            raise ValueError("scales must not be empty")


DEFAULT_EXTRACTION_RESCUE_POLICY = ExtractionRescuePolicy()


def _has_near_candidate(candidate: Candidate, baseline: Iterable[Candidate], radius: float) -> bool:
    for other in baseline:
        if (
            hypot(
                float(candidate.x_center) - float(other.x_center),
                float(candidate.y_center) - float(other.y_center),
            )
            <= radius
        ):
            return True
    return False


def _mark_rescued_candidates(eligible: list[Candidate], *, start_id: int) -> list[Candidate]:
    """Stamp rescue provenance onto accepted candidates (M10: pure).

    Renumbers from *start_id*, appends the rescue note, forces the
    broad-response vocabulary, and re-assesses quality. Returns new
    copies; inputs are never mutated. Extracted from
    :func:`propose_conservative_geology_rescues` so the marking logic
    is unit-testable without engineering a full secondary detection.
    """
    rescued: list[Candidate] = []
    next_id = int(start_id)
    for candidate in eligible:
        notes = "; ".join(
            filter(
                None,
                [candidate.notes, "secondary extraction rescue; median-background geology channel"],
            )
        ).strip("; ")
        quality_flags = list(candidate.quality_flags or [])
        if "secondary-extraction-rescue" not in quality_flags:
            quality_flags = quality_flags + ["secondary-extraction-rescue"]
        rescued.append(
            assess_candidate_quality(
                candidate.with_updates(
                    id=next_id,
                    notes=notes,
                    response_family="broad-response",
                    classification_method="secondary-median-geology-rescue",
                    quality_flags=quality_flags,
                    screening_selection_reason="secondary-geology-extraction-rescue",
                )
            )
        )
        next_id += 1
    return rescued


def propose_conservative_geology_rescues(
    grid: Grid2D,
    baseline_candidates: list[Candidate],
    *,
    threshold: float | None = None,
    min_size: int | None = None,
    scales: tuple[int, ...] | None = None,
    coords_are_index_only: bool = False,
    policy: ExtractionRescuePolicy = DEFAULT_EXTRACTION_RESCUE_POLICY,
) -> tuple[list[Candidate], dict[str, object]]:
    """Return optional secondary candidates plus auditable diagnostics.

    The secondary channel never edits the baseline anomaly map.  It produces a
    candidate only when a median-background analysis finds a broad, clean,
    non-boundary, sufficiently strong geological-compatible region that has no
    nearby baseline candidate.  Index-only coordinate scans are intentionally
    excluded because the exclusion radius is a geometry-sensitive guard.

    ``threshold`` / ``min_size`` / ``scales`` default to ``None``, meaning
    "use the policy's value". They previously defaulted to literals, so the
    ``policy.X if X is None else X`` indirection below could never take its
    policy branch and the three policy fields were unreachable knobs: changing
    ``ExtractionRescuePolicy.threshold`` had no effect unless the caller
    duplicated the change as an explicit argument. The defaults here match the
    policy defaults, so deferring is behaviour-preserving.
    """
    policy.validate()
    if policy.mode == "off" or coords_are_index_only:
        return [], {
            "enabled": False,
            "reason": "disabled" if policy.mode == "off" else "index-only-coordinates",
            "candidate_count": 0,
        }

    secondary_anomaly = detect_anomalies(
        grid,
        threshold=float(policy.threshold if threshold is None else threshold),
        min_size=int(policy.min_size if min_size is None else min_size),
        background_method=policy.background_method,
        scales=tuple(policy.scales if scales is None else scales),
        connectivity=8,
    )
    secondary_artifacts = detect_artifacts(grid, secondary_anomaly)
    secondary_candidates = extract_candidates(grid, secondary_anomaly, secondary_artifacts)
    secondary_candidates = [classify_candidate(c) for c in secondary_candidates]

    eligible: list[Candidate] = []
    rejected: dict[str, int] = {}
    for candidate in secondary_candidates:
        reasons: list[str] = []
        if candidate.pattern_hypothesis != "geological-like":
            reasons.append("pattern")
        if candidate.scale_class != "broad":
            reasons.append("scale")
        if float(candidate.anomaly_score) < policy.min_anomaly_score:
            reasons.append("anomaly")
        if float(candidate.broadness_score) < policy.min_broadness_score:
            reasons.append("broadness")
        if float(candidate.artifact_score) > policy.max_artifact_score:
            reasons.append("artifact")
        if float(candidate.boundary_contact_ratio) >= policy.max_boundary_contact_ratio:
            reasons.append("boundary")
        if _has_near_candidate(candidate, baseline_candidates, policy.exclusion_radius):
            reasons.append("baseline-near")
        if reasons:
            for reason in reasons:
                rejected[reason] = rejected.get(reason, 0) + 1
            continue
        eligible.append(candidate)

    next_id = max((int(c.id) for c in baseline_candidates), default=0) + 1
    eligible = _mark_rescued_candidates(eligible, start_id=next_id)

    diagnostics = {
        "enabled": True,
        "mode": policy.mode,
        "secondary_candidate_count": len(secondary_candidates),
        "accepted_candidate_count": len(eligible),
        "rejected_by_reason": rejected,
        "guardrails": {
            "min_anomaly_score": policy.min_anomaly_score,
            "min_broadness_score": policy.min_broadness_score,
            "max_artifact_score": policy.max_artifact_score,
            "max_boundary_contact_ratio": policy.max_boundary_contact_ratio,
            "exclusion_radius": policy.exclusion_radius,
            "baseline_unchanged": True,
        },
    }
    return eligible, diagnostics

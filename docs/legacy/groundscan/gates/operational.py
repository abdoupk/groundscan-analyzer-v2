"""Final field-operational candidate gate.

This is a conservative provenance/interpretation gate. It does not modify the
anomaly map or erase candidates. Instead it records whether a candidate can be
used for an operational field interpretation without overstating registration,
depth, geometry, spacing, or edge reliability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .._util import bounded01
from ..models import Candidate
from .thresholds import OPERATIONAL_GATE_THRESHOLDS as T

REGISTRATION_CAUTION = T["registration_caution"]
REGISTRATION_BLOCK = T["registration_block"]
DEPTH_CAUTION = T["depth_caution"]
DEPTH_BLOCK = T["depth_block"]
BOUNDARY_CAUTION = T["boundary_caution"]
BOUNDARY_BLOCK = T["boundary_block"]
ARTIFACT_CAUTION = T["artifact_caution"]
ARTIFACT_BLOCK = T["artifact_block"]
GEOMETRY_CAUTION = T["geometry_caution"]
POSITION_CAUTION = T["position_caution"]
POSITION_BLOCK = T["position_block"]
SPACING_CAUTION = T["spacing_caution"]
DETECTION_CAUTION = T["detection_caution"]
UNCERTAINTY_CAUTION = T["uncertainty_caution"]
UNCERTAINTY_BLOCK = T["uncertainty_block"]


@dataclass(frozen=True)
class OperationalAssessment:
    status: str
    flags: tuple[str, ...]
    constraints: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "flags": list(self.flags),
            "constraints": list(self.constraints),
        }


def assess_operational_gate(
    candidate: Candidate, field_quality_status: str = "field-ready"
) -> OperationalAssessment:
    """Attach conservative field-use status without changing detection evidence.

    ``field_quality_status`` carries the scan-level readiness state from
    ``assess_field_quality`` (field-ready / usable-with-caution /
    insufficient-quality). Scans that are already hard-blocked never reach
    here (no candidates are extracted), so only the caution tier is handled:
    it adds a caution flag rather than suppressing the candidate, consistent
    with every other check in this function.
    """
    flags: list[str] = []
    constraints: list[str] = []
    blocked = False
    caution = False

    if field_quality_status == "usable-with-caution":
        caution = True
        flags.append("operational-field-quality-caution")
        constraints.append(
            "Scan-level field quality is degraded (see field_quality diagnostics); "
            "treat this candidate as a review target and confirm with a repeat scan."
        )

    multi = str(getattr(candidate, "multi_scan_status", "single-scan")) == "multi-scan"
    # Audit fix: bounded via bounded01() rather than np.clip, which passes NaN
    # straight through and made every comparison below False -- an all-unknown
    # candidate skipped all branches and reported "clear". Fields whose absence
    # is adverse (evidence, stability, reliability) map to 0.0; the default-1.0
    # rates keep their neutral reading when genuinely absent.
    registration = bounded01(getattr(candidate, "registration_consistency", 1.0))
    position = bounded01(getattr(candidate, "position_stability", 1.0))
    depth = bounded01(getattr(candidate, "depth_stability_score", 0.0))
    boundary = bounded01(getattr(candidate, "boundary_contact_ratio", 0.0))
    artifact = bounded01(getattr(candidate, "artifact_score", 0.0))
    geometry = bounded01(getattr(candidate, "geometry_quality", 0.0))
    uncertainty = bounded01(getattr(candidate, "evidence_uncertainty", 0.0))
    spacing = bounded01(getattr(candidate, "spacing_persistence", 1.0))
    detection = bounded01(getattr(candidate, "detection_rate", 1.0))
    metric = bool(getattr(candidate, "metric_geometry_reliable", True))

    if multi:
        # Candidate-level registration_consistency is the aggregate registration
        # evidence; position_stability separately limits fused localization.
        if registration < REGISTRATION_BLOCK:
            blocked = True
            flags.append("operational-registration-block")
            constraints.append(
                "Cross-scan registration is too weak for reliable fused localization."
            )
        elif registration < REGISTRATION_CAUTION:
            caution = True
            flags.append("operational-registration-caution")
            constraints.append(
                "Cross-scan registration is caution-level; localization should be confirmed by repeat acquisition."
            )
        if position < POSITION_BLOCK:
            blocked = True
            flags.append("operational-position-block")
            constraints.append(
                "Cross-scan position stability is too weak for reliable fused coordinates."
            )
        elif position < POSITION_CAUTION:
            caution = True
            flags.append("operational-position-caution")
            constraints.append(
                "Cross-scan position stability is limited; treat fused coordinates as approximate."
            )
        if spacing < SPACING_CAUTION:
            caution = True
            flags.append("operational-spacing-caution")
            constraints.append(
                "Persistence across line spacing variants is weak; fine spatial claims need confirmation."
            )
        if detection < DETECTION_CAUTION:
            caution = True
            flags.append("operational-detection-rate-caution")
            constraints.append(
                "The candidate is not present consistently enough across the available scans for strong repeatability claims."
            )

    if multi:
        if uncertainty >= UNCERTAINTY_BLOCK:
            blocked = True
            flags.append("operational-uncertainty-block")
            constraints.append(
                "Overall cross-scan evidence uncertainty is too high for an operationally trusted candidate."
            )
        elif uncertainty >= UNCERTAINTY_CAUTION:
            caution = True
            flags.append("operational-uncertainty-caution")
            constraints.append(
                "Evidence uncertainty is elevated; interpret the candidate as a review target, not a confirmed feature."
            )

    if depth < DEPTH_BLOCK:
        caution = True
        # v0.4.2 (audit F-20): this tier never blocked; the old
        # "operational-depth-block" name promised a block that never fired.
        # Renamed to unreliable: depth is unusable here, but the candidate
        # itself is still reported (a real block would suppress every
        # depth-less candidate, including most legitimate ones).
        flags.append("operational-depth-unreliable")
        constraints.append(
            "Depth is not operationally reliable; do not present the reported depth as a dependable measurement."
        )
    elif depth < DEPTH_CAUTION:
        caution = True
        flags.append("operational-depth-caution")
        constraints.append(
            "Depth stability is limited; report depth as an uncertain estimate only."
        )

    depth_value = getattr(candidate, "depth_estimate", float("nan"))
    depth_valid = bounded01(getattr(candidate, "depth_valid_fraction", 0.0))
    if (
        not isinstance(depth_value, (int, float)) or not math.isfinite(float(depth_value))
    ) and depth_valid <= 0:
        caution = True
        flags.append("operational-depth-unavailable")
        constraints.append("No usable depth estimate is available for this candidate.")

    if boundary >= BOUNDARY_BLOCK:
        blocked = True
        flags.append("operational-edge-block")
        constraints.append(
            "The candidate is dominated by the scan boundary; do not treat edge geometry as an underground target shape."
        )
    elif boundary >= BOUNDARY_CAUTION:
        caution = True
        flags.append("operational-edge-caution")
        constraints.append(
            "The candidate touches the scan boundary; localization and morphology are edge-sensitive."
        )

    if artifact >= ARTIFACT_BLOCK:
        blocked = True
        flags.append("operational-artifact-block")
        constraints.append(
            "Instrument/acquisition artifact evidence is too strong for an operational target interpretation."
        )
    elif artifact >= ARTIFACT_CAUTION:
        caution = True
        flags.append("operational-artifact-caution")
        constraints.append(
            "Acquisition artifact evidence is non-negligible; inspect the raw scan before interpretation."
        )

    if geometry < GEOMETRY_CAUTION:
        caution = True
        flags.append("operational-geometry-caution")
        constraints.append(
            "Candidate geometry is weakly constrained; shape and size should not be treated as precise."
        )

    if not metric:
        caution = True
        flags.append("operational-non-metric-geometry")
        constraints.append(
            "Physical spacing is not verified; distances and areas are scan-coordinate units, not confirmed meters."
        )

    status = "blocked" if blocked else ("caution" if caution else "clear")
    if not flags:
        flags.append("operational-gate-clear")
        constraints.append(
            "No operational reliability gate was triggered; interpretation remains heuristic and requires field validation."
        )

    return OperationalAssessment(
        status=status,
        flags=tuple(dict.fromkeys(flags)),
        constraints=tuple(dict.fromkeys(constraints)),
    )


def apply_operational_gate(
    candidate: Candidate, field_quality_status: str = "field-ready"
) -> Candidate:
    """Store the assessment on the candidate and preserve all existing evidence.

    Mutates in place by design: the multi-stage pipeline enriches candidates
    by identity from extract through the gates (see ``docs/architecture.md``).
    For isolated/testable transforms prefer :func:`gated_copy`.
    """
    assessment = assess_operational_gate(candidate, field_quality_status)
    candidate.operational_status = assessment.status
    candidate.operational_flags = list(assessment.flags)
    candidate.operational_constraints = list(assessment.constraints)
    if assessment.status == "blocked":
        note = "operational field-use gate blocked trusted interpretation"
    elif assessment.status == "caution":
        note = "operational field-use caution applies"
    else:
        note = ""
    if note and note not in candidate.notes:
        candidate.notes = (candidate.notes + "; " if candidate.notes else "") + note
    candidate.quality_flags = list(
        dict.fromkeys((getattr(candidate, "quality_flags", None) or []) + list(assessment.flags))
    )
    return candidate


def gated_copy(candidate: Candidate, field_quality_status: str = "field-ready") -> Candidate:
    """Pure ``with_updates()`` exemplar: return a gated copy, leave input untouched.

    Uses :meth:`Candidate.with_updates` so stage functions can avoid in-place
    mutation when a pure transform is clearer. Behavior-parity with
    :func:`apply_operational_gate` is pinned in
    ``tests/unit/test_candidate_discipline.py``.
    """
    assessment = assess_operational_gate(candidate, field_quality_status)
    if assessment.status == "blocked":
        note = "operational field-use gate blocked trusted interpretation"
    elif assessment.status == "caution":
        note = "operational field-use caution applies"
    else:
        note = ""
    notes = candidate.notes
    if note and note not in notes:
        notes = (notes + "; " if notes else "") + note
    merged_quality_flags = list(
        dict.fromkeys(
            list(getattr(candidate, "quality_flags", None) or []) + list(assessment.flags)
        )
    )
    return candidate.with_updates(
        operational_status=assessment.status,
        operational_flags=list(assessment.flags),
        operational_constraints=list(assessment.constraints),
        notes=notes,
        quality_flags=merged_quality_flags,
    )

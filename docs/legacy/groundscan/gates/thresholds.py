"""Named operational thresholds used by the field-readiness gates.

The registry is intentionally descriptive: these values are engineering policy
thresholds, not empirically calibrated accuracy cut-points.  They must not be
presented as probabilities or as field-performance estimates.
"""

from __future__ import annotations

FIELD_QUALITY_THRESHOLDS = {
    "signal_valid_hard_block": 0.60,
    "signal_valid_caution": 0.90,
    "signal_valid_complete": 0.98,
    "grid_coverage_hard_block": 0.70,
    "grid_coverage_caution": 0.95,
    "grid_min_dimension_hard_block": 4,
    "depth_valid_caution": 0.50,
    "depth_valid_partial": 0.95,
    "dynamic_range_caution": 0.40,
    "artifact_strong": 0.80,
    "artifact_caution": 0.50,
    "ready_score_insufficient": 0.55,
    "ready_score_ready": 0.82,
}

OPERATIONAL_GATE_THRESHOLDS = {
    "registration_block": 0.50,
    "registration_caution": 0.70,
    "position_block": 0.30,
    "position_caution": 0.50,
    "spacing_caution": 0.50,
    "detection_caution": 0.75,
    "uncertainty_block": 0.65,
    "uncertainty_caution": 0.45,
    "depth_block": 0.20,
    "depth_caution": 0.40,
    "boundary_block": 0.80,
    "boundary_caution": 0.45,
    "artifact_block": 0.70,
    "artifact_caution": 0.50,
    "geometry_caution": 0.40,
}


def threshold_policy() -> dict[str, dict[str, float | int]]:
    """Return a copy suitable for JSON/Markdown audit output."""
    return {
        "field_quality": dict(FIELD_QUALITY_THRESHOLDS),
        "operational_gate": dict(OPERATIONAL_GATE_THRESHOLDS),
        "scoring_weights": {
            **{f"fusion_{k}": v for k, v in FUSION_EVIDENCE_WEIGHTS.items()},
            **{f"registration_{k}": v for k, v in REGISTRATION_EVIDENCE_WEIGHTS.items()},
            **{f"quality_support_{k}": v for k, v in QUALITY_SUPPORT_WEIGHTS.items()},
            **{f"quality_penalty_{k}": v for k, v in QUALITY_PENALTY_WEIGHTS.items()},
        },
    }


# v0.5.1: centralized scoring weights (single source of truth).
# Values are behavior-preserving copies of the previously scattered literals;
# formulas that consume them are unchanged, only the import location moved.
# All weights are heuristic policy, not calibrated probabilities.
FUSION_EVIDENCE_WEIGHTS = {
    "base": 0.18,
    "detection_rate": 0.17,
    "direction": 0.10,
    "spacing": 0.10,
    "traversal": 0.08,
    "position_stability": 0.10,
    "polarity_consistency": 0.07,
    "signal_consistency": 0.07,
    "depth_consistency": 0.06,
    "registration_consistency": 0.05,
    "consensus": 0.02,
}

REGISTRATION_EVIDENCE_WEIGHTS = {
    "correlation": 0.35,
    "overlap": 0.20,
    "margin": 0.15,
    "multiscale": 0.30,
}

QUALITY_SUPPORT_WEIGHTS = {
    "evidence": 0.45,
    "persistence": 0.15,
    "geometry": 0.10,
    "position": 0.08,
    "signal": 0.07,
    "registration": 0.05,
    "multi_evidence": 0.10,
}

QUALITY_PENALTY_WEIGHTS = {
    "artifact": 0.33,
    "boundary": 0.18,
    "uncertainty": 0.15,
}

SCREENING_WEIGHTS = {
    "evidence": 0.55,
    "quality": 0.30,
    "non_artifact": 0.15,
}


def fused_evidence_score(
    *,
    base: float,
    detection_rate: float,
    direction_cov: float,
    spacing_cov: float,
    traversal_cov: float,
    position_stability: float,
    pol_cons: float,
    signal_cons: float,
    depth_cons: float,
    reg_cons: float,
    cons: float,
) -> float:
    """Site fusion evidence (bounded 0..1 heuristic, not a probability)."""
    import numpy as _np

    w = FUSION_EVIDENCE_WEIGHTS
    return float(
        _np.clip(
            w["base"] * base
            + w["detection_rate"] * detection_rate
            + w["direction"] * direction_cov
            + w["spacing"] * spacing_cov
            + w["traversal"] * traversal_cov
            + w["position_stability"] * position_stability
            + w["polarity_consistency"] * pol_cons
            + w["signal_consistency"] * signal_cons
            + w["depth_consistency"] * depth_cons
            + w["registration_consistency"] * reg_cons
            + w["consensus"] * cons,
            0,
            1,
        )
    )


def registration_evidence_score(
    *, correlation: float, overlap: float, margin: float, multiscale: float
) -> float:
    """Registration quality 0..1 (heuristic, not a probability)."""
    # Audit fix: bounded01() instead of max(0.0, min(1.0, x)). Python's
    # min(1.0, nan) returns 1.0, so non-finite inputs scored a perfect
    # registration -- indistinguishable from a flawless alignment.
    from .._util import bounded01

    w = REGISTRATION_EVIDENCE_WEIGHTS
    corr = bounded01(correlation)
    over = bounded01(overlap)
    marg = bounded01(margin)
    mult = bounded01(multiscale)
    return round(
        w["correlation"] * corr + w["overlap"] * over + w["margin"] * marg + w["multiscale"] * mult,
        3,
    )

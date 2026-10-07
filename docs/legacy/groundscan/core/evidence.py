"""Unified evidence-based pattern classification.

This module turns existing signal, morphology, geometry, quality and multi-scan
measurements into competing *pattern-support* scores.  The outputs are bounded
heuristic supports, not probabilities and not material/object identification.

The model is deliberately deterministic and auditable.  It does not change
candidate extraction, anomaly detection, soil correction, depth estimation, or
registration.  Those stages remain upstream inputs to the classifier.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..models import Candidate

HYPOTHESES: tuple[str, ...] = (
    "metallic-like",
    "linear-metal-compatible",
    "cavity-like",
    "tunnel-like",
    "geological-like",
    "boundary-effect-like",
    "irregular-anomaly",
    "unknown",
)


@dataclass(frozen=True)
class EvidenceModelConfig:
    min_support: float = 0.50
    min_margin: float = 0.02
    unknown_floor: float = 0.18
    linear_metal_min_line_support: float = 0.58
    linear_metal_min_linearity: float = 0.38
    linear_metal_min_axial: float = 0.62


DEFAULT_EVIDENCE_MODEL_CONFIG = EvidenceModelConfig()


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return low
    if not math.isfinite(value):
        return low
    return max(low, min(high, value))


def _mean(*values: float) -> float:
    vals = [_clip(v) for v in values]
    return sum(vals) / len(vals) if vals else 0.0


def _strength(anomaly_score: float) -> float:
    """Map anomaly magnitude to a bounded evidence feature without a hard gate.

    v0.4.2 (audit F-01, second pass): the previous map ``1 - exp(-|z|/5)``
    reached 0.95 at |z|=15 and 1.0 by |z|=30, so every real localized
    anomaly -- dust-collapsed (|z|~1e9 then, ~143 now) or genuinely strong
    (|z|~30-67 on vendor device data) -- was indistinguishable. The Hill
    map ``|z| / (|z| + 4)`` matches the old curve within 0.03 at and below
    the 3.0 detection threshold (1->0.20, 2->0.33, 3->0.43) so threshold
    semantics are preserved, but stays responsive across the whole bounded
    z-range the detector can report (filters.ZSCORE_CLIP = 150):
    6->0.60, 10->0.71, 15->0.79, 30->0.88, 67->0.94, 150->0.97.
    The 15-to-150 spread (~0.19) is what lets confidence carry information
    about evidence strength instead of saturating for every detection.
    """
    try:
        magnitude = abs(float(anomaly_score))
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(magnitude):
        return 1.0 if magnitude == float("inf") else 0.0
    return _clip(magnitude / (magnitude + 4.0))


def _positive_fraction(candidate: Candidate) -> float:
    pos = abs(float(candidate.positive_peak))
    neg = abs(float(candidate.negative_peak))
    total = pos + neg
    if total <= 1e-12:
        return (
            1.0
            if candidate.polarity == "positive"
            else (0.5 if candidate.polarity == "mixed" else 0.0)
        )
    return _clip(pos / total)


def _negative_fraction(candidate: Candidate) -> float:
    return 1.0 - _positive_fraction(candidate)


def _size_score(candidate: Candidate) -> float:
    return _clip(max(0.0, float(candidate.area_cells)) / 15.0)


def _aspect_compactness(candidate: Candidate) -> float:
    aspect = max(1.0, abs(float(candidate.aspect_ratio)))
    return _clip(math.exp(-(aspect - 1.0) / 1.5))


def _aspect_elongation(candidate: Candidate) -> float:
    aspect = max(1.0, abs(float(candidate.aspect_ratio)))
    return _clip((aspect - 1.0) / 2.5)


def _low(value: float) -> float:
    return 1.0 - _clip(value)


def _features(candidate: Candidate) -> dict[str, float]:
    """Evidence vector for morphology-hypothesis scoring.

    v0.4.2 (audit F-22): cross-scan confirmation fields (detection_rate,
    directional/spacing/traversal persistence, position_stability) were
    computed here but read by NO hypothesis weight table -- dead
    computation. They are removed rather than wired into morphology
    tables: the tables answer "what pattern does this response look
    like?", while confirmation ("how repeatably was it observed?") belongs
    to the site level. Confirmation reaches the final evidence number
    through the classify-time detection blend (see classify_candidate)
    and through quality/review_status -- not through morphology weights,
    where a vacuous single-scan default (detection 1.0, persistences 0.0)
    would penalize or reward candidates for information that does not
    exist. The fields themselves stay on Candidate: reports, quality,
    the operational gate and explanations read them directly.
    """
    clean = _low(candidate.artifact_score)
    return {
        "strength": _strength(candidate.anomaly_score),
        "positive": _positive_fraction(candidate),
        "negative": _negative_fraction(candidate),
        "locality": _clip(candidate.anomaly_density),
        "size": _size_score(candidate),
        "compactness": _clip(candidate.compactness),
        "continuity": _clip(candidate.continuity_score),
        "linearity": _clip(candidate.linearity_score),
        "line_support": _clip(candidate.line_support_score),
        "axial": _clip(candidate.axial_signal_continuity_score),
        "coherence": _clip(candidate.morphology_line_coherence_score),
        "axial_coverage": _clip(candidate.morphology_axial_coverage_score),
        "width_consistency": _clip(candidate.width_consistency_score),
        "broadness": _clip(candidate.broadness_score),
        "regional": _clip(candidate.regional_support_score),
        "clean": clean,
        "boundary_free": _low(candidate.boundary_contact_ratio),
        "geometry": _clip(candidate.geometry_quality),
        "solidity": _clip(candidate.solidity),
        "persistence": _clip(candidate.multiscale_persistence),
        "depth_stability": _clip(candidate.depth_stability_score or 0.0),
        "aspect_compact": _aspect_compactness(candidate),
        "aspect_elongated": _aspect_elongation(candidate),
        "scale_broad": 1.0 if candidate.scale_class == "broad" else 0.0,
        "shape_compact": 1.0 if candidate.shape_class in {"point", "compact"} else 0.0,
        "shape_linear": 1.0 if candidate.shape_class == "linear" else 0.0,
        "shape_broad": 1.0 if candidate.shape_class in {"broad", "diffuse"} else 0.0,
        "shape_boundary": 1.0 if candidate.shape_class == "boundary-like" else 0.0,
        "shape_irregular": 1.0 if candidate.shape_class == "irregular" else 0.0,
    }


def _weighted(features: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return _clip(sum(_clip(features.get(k, 0.0)) * w for k, w in weights.items()) / total)


# Public attribution metadata is the single source of truth for the weighted
# hypothesis scores below: score_hypotheses consumes this table directly, so the
# report attribution cannot drift away from the actual computation.  Keeping the
# table explicit makes reports inspectable without exposing internal
# implementation details as if they were calibrated statistical coefficients.
ATTRIBUTION_WEIGHTS: dict[str, dict[str, float]] = {
    "metallic-like": {
        "positive": 0.17,
        "strength": 0.14,
        "compactness": 0.14,
        "shape_compact": 0.07,
        "locality": 0.07,
        "persistence": 0.08,
        "clean": 0.08,
        "boundary_free": 0.08,
        "geometry": 0.08,
        "depth_stability": 0.04,
        "aspect_compact": 0.05,
    },
    "cavity-like": {
        "negative": 0.19,
        "continuity": 0.13,
        "size": 0.08,
        "persistence": 0.10,
        "clean": 0.08,
        "geometry": 0.08,
        "compactness": 0.08,
        "shape_compact": 0.07,
        "depth_stability": 0.05,
        "linearity": 0.06,
        "broadness": 0.05,
        "boundary_free": 0.05,
    },
    "tunnel-like": {
        "negative": 0.13,
        "line_support": 0.15,
        "axial": 0.15,
        "linearity": 0.13,
        "shape_linear": 0.08,
        "continuity": 0.08,
        "persistence": 0.08,
        "width_consistency": 0.07,
        "coherence": 0.05,
        "axial_coverage": 0.05,
        "aspect_elongated": 0.03,
        "boundary_free": 0.02,
    },
    "geological-like": {
        "broadness": 0.25,
        "regional": 0.18,
        "scale_broad": 0.20,
        "shape_broad": 0.04,
        "strength": 0.06,
        "linearity": 0.06,
        "clean": 0.08,
        "geometry": 0.06,
        "size": 0.06,
        "continuity": 0.05,
    },
    "irregular-anomaly": {
        "shape_irregular": 0.20,
        "solidity": 0.05,
        "clean": 0.12,
        "strength": 0.11,
        "size": 0.10,
        "continuity": 0.08,
        "geometry": 0.10,
        "broadness": 0.10,
        "linearity": 0.05,
        "persistence": 0.09,
    },
}


def score_hypotheses(candidate: Candidate) -> dict[str, float]:
    """Score all public pattern hypotheses from the same evidence vector."""
    f = _features(candidate)
    line_quality = _mean(
        f["line_support"],
        f["axial"],
        f["linearity"],
        f["coherence"],
        f["axial_coverage"],
        f["width_consistency"],
    )

    supports = {
        hypothesis: _weighted(f, weights) for hypothesis, weights in ATTRIBUTION_WEIGHTS.items()
    }
    # Boundary-effect support uses inverted features, so it keeps its explicit
    # form here; the same constants are exposed in the attribution block of
    # explain_hypothesis_support.
    supports["boundary-effect-like"] = _clip(
        0.55 * (1.0 - f["boundary_free"])
        + 0.15 * (1.0 - f["clean"])
        + 0.05 * (1.0 - f["geometry"])
        + 0.20 * f["shape_boundary"]
        + 0.05 * (1.0 - f["persistence"])
    )

    # A linear-metal response is a constrained extension of the metallic
    # pattern, not a separate material claim.
    metal = supports["metallic-like"]
    linear_metal = _mean(metal, line_quality, f["positive"], f["boundary_free"], f["clean"])
    if not (
        candidate.polarity == "positive"
        and f["line_support"] >= 0.58
        and f["linearity"] >= 0.38
        and f["axial"] >= 0.62
    ):
        linear_metal *= 0.55
    supports["linear-metal-compatible"] = _clip(linear_metal)

    # Preserve signed-response semantics explicitly. Positive/negative peaks
    # can be close in magnitude for a dipolar or mixed response, so the
    # exported polarity should act as a soft semantic factor rather than being
    # inferred only from peak magnitudes.
    if candidate.polarity == "negative":
        supports["metallic-like"] *= 0.72
        supports["linear-metal-compatible"] *= 0.70
        supports["cavity-like"] *= 1.05
        supports["tunnel-like"] *= 1.08
    elif candidate.polarity == "positive":
        supports["metallic-like"] *= 1.04
        supports["linear-metal-compatible"] *= 1.03
        supports["cavity-like"] *= 0.86
        supports["tunnel-like"] *= 0.78
    elif candidate.polarity == "mixed":
        supports["metallic-like"] *= 0.88
        supports["linear-metal-compatible"] *= 0.82
        supports["cavity-like"] *= 0.94

    supports = {k: _clip(v) for k, v in supports.items()}

    # Unknown is an explicit residual hypothesis: it stays relevant when no
    # specific pattern wins with a useful margin.
    specific_best = max(supports.values())
    supports["unknown"] = _clip(max(0.05, 0.58 - 0.45 * specific_best))

    # Avoid a false impression that the response scores sum to 100%; each score
    # is an independent support measure for a different descriptive hypothesis.
    return {k: round(_clip(v), 3) for k, v in supports.items()}


def classify_from_evidence(
    candidate: Candidate,
    *,
    config: EvidenceModelConfig = DEFAULT_EVIDENCE_MODEL_CONFIG,
) -> tuple[str, dict[str, float], float, str, str, str]:
    """Return selected hypothesis, supports, margin, runner-up, reason, method."""
    scores = score_hypotheses(candidate)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best, best_score = ranked[0]
    second, second_score = ranked[1]
    margin = round(best_score - second_score, 3)

    if best_score < config.min_support or margin < config.min_margin:
        reason = (
            f"ambiguous pattern support: {best}={best_score:.2f}, "
            f"{second}={second_score:.2f}, margin={margin:.2f}"
        )
        return "unknown", scores, margin, second, reason, "evidence-model"

    return best, scores, margin, second, "", "evidence-model"


def explain_hypothesis_support(candidate: Candidate) -> dict[str, dict[str, object]]:
    """Return auditable feature attribution for every public hypothesis.

    This is an explanation/provenance layer over the same deterministic
    evidence vector used by :func:`score_hypotheses`. It intentionally exposes
    feature values and relative weights rather than pretending the weighted
    terms are calibrated probabilities.
    """
    f = _features(candidate)
    scores = score_hypotheses(candidate)
    line_quality = _mean(
        f["line_support"],
        f["axial"],
        f["linearity"],
        f["coherence"],
        f["axial_coverage"],
        f["width_consistency"],
    )
    out: dict[str, dict[str, object]] = {}

    for hypothesis, weights in ATTRIBUTION_WEIGHTS.items():
        total = sum(weights.values())
        terms: list[dict[str, Any]] = []
        for feature, weight in weights.items():
            value = _clip(f.get(feature, 0.0))
            terms.append({
                "feature": feature,
                "value": round(value, 3),
                "weight": round(weight, 3),
                "contribution": round(value * weight / total if total else 0.0, 3),
            })
        terms.sort(key=lambda item: (-item["contribution"], item["feature"]))
        out[hypothesis] = {
            "score": scores[hypothesis],
            "top_features": terms[:5],
            "all_features": terms,
            "semantic_notes": [],
        }

    metal = scores["metallic-like"]
    linear_metal_gate = (
        candidate.polarity == "positive"
        and f["line_support"] >= 0.58
        and f["linearity"] >= 0.38
        and f["axial"] >= 0.62
    )
    linear_terms: list[dict[str, Any]] = [
        {"feature": "metallic_like_base", "value": round(metal, 3)},
        {"feature": "line_quality", "value": round(line_quality, 3)},
        {"feature": "positive", "value": round(f["positive"], 3)},
        {"feature": "boundary_free", "value": round(f["boundary_free"], 3)},
        {"feature": "clean", "value": round(f["clean"], 3)},
    ]
    out["linear-metal-compatible"] = {
        "score": scores["linear-metal-compatible"],
        "top_features": sorted(linear_terms, key=lambda x: (-x["value"], x["feature"])),
        "all_features": linear_terms,
        "gate": linear_metal_gate,
        "semantic_notes": ["positive polarity + linear morphology gate required"],
    }

    boundary_terms: list[dict[str, Any]] = [
        {
            "feature": "boundary_contact",
            "value": round(1.0 - f["boundary_free"], 3),
            "weight": 0.55,
        },
        {"feature": "artifact_presence", "value": round(1.0 - f["clean"], 3), "weight": 0.15},
        {"feature": "geometry_gap", "value": round(1.0 - f["geometry"], 3), "weight": 0.05},
        {"feature": "boundary_shape", "value": round(f["shape_boundary"], 3), "weight": 0.20},
        {"feature": "persistence_gap", "value": round(1.0 - f["persistence"], 3), "weight": 0.05},
    ]
    out["boundary-effect-like"] = {
        "score": scores["boundary-effect-like"],
        "top_features": sorted(
            boundary_terms, key=lambda x: (-x["value"] * x["weight"], x["feature"])
        ),
        "all_features": boundary_terms,
        "semantic_notes": ["boundary contact is a dominant limiter"],
    }

    specific_best = max(scores[h] for h in HYPOTHESES if h != "unknown")
    out["unknown"] = {
        "score": scores["unknown"],
        "top_features": [
            {
                "feature": "specific_best_support",
                "value": round(specific_best, 3),
                "direction": "higher lowers unknown support",
            }
        ],
        "all_features": [{"feature": "specific_best_support", "value": round(specific_best, 3)}],
        "semantic_notes": [
            "residual hypothesis; selected when no specific pattern has sufficient support/margin"
        ],
    }

    polarity_modifier = 1.0
    if candidate.polarity == "negative":
        polarity_modifier = 1.08
    elif candidate.polarity == "positive":
        polarity_modifier = 1.04
    elif candidate.polarity == "mixed":
        polarity_modifier = 0.94
    for hypothesis in ("metallic-like", "linear-metal-compatible", "cavity-like", "tunnel-like"):
        out[hypothesis]["polarity"] = candidate.polarity
        out[hypothesis]["polarity_context"] = polarity_modifier

    return out

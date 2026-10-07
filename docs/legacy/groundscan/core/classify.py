"""Conservative pattern interpretation from geometry, depth and signed-signal evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models import Candidate
from .evidence import (
    DEFAULT_EVIDENCE_MODEL_CONFIG,
    classify_from_evidence,
    explain_hypothesis_support,
)


@dataclass(frozen=True)
class ClassificationConfig:
    """Retired rule-cascade thresholds.

    Every field here gated ``_apply_compatibility_feature_pass``, the ~230-line
    morphology rule cascade that ``classify_candidate`` used to run before
    handing off to the Evidence Model. That pass was removed as dead code: each
    field it wrote was overwritten unconditionally by ``classify_candidate``'s
    single ``with_updates``, so no threshold below could reach a returned
    candidate. The dataclass and its fields are kept only because
    ``ClassificationConfig`` is part of the public ``groundscan.core`` surface
    and is threaded through ``analyze_scan(classification_config=...)``; a
    caller constructing one still gets a valid object. New calibration belongs
    in :class:`groundscan.core.evidence.EvidenceModelConfig`, which is the
    authoritative scorer.
    """

    high_score: float = 3.5
    min_linear_continuity: float = 0.55
    min_void_size: int = 6
    metal_max_aspect: float = 2.5
    metal_min_compactness: float = 0.55
    tunnel_min_line_support: float = 0.60
    tunnel_min_axial_continuity: float = 0.80
    tunnel_alt_line_support: float = 0.74
    tunnel_min_linearity: float = 0.45
    cavity_min_continuity: float = 0.45
    # v0.2.30 linear-metal refinement. This is a conservative pattern
    # refinement of an already metallic-compatible response; it does not
    # create new anomalies and does not alter baseline anomaly detection.
    linear_metal_min_anomaly: float = 5.0
    linear_metal_min_line_support: float = 0.72
    linear_metal_min_axial_continuity: float = 0.65
    linear_metal_min_linearity: float = 0.40
    linear_metal_min_coherence: float = 0.48
    linear_metal_min_axial_coverage: float = 0.80
    linear_metal_min_width_consistency: float = 0.15
    linear_metal_max_boundary_contact: float = 0.50
    linear_metal_min_clean: float = 0.55
    multi_negative_tunnel_min_linearity: float = 0.34
    multi_negative_tunnel_min_line_support: float = 0.46
    multi_negative_tunnel_min_axial_continuity: float = 0.68
    multi_negative_tunnel_min_coherence: float = 0.40
    multi_negative_tunnel_min_axial_coverage: float = 0.62
    multi_negative_tunnel_min_width_consistency: float = 0.18
    multi_positive_metal_min_anomaly: float = 4.0
    multi_positive_metal_min_compactness: float = 0.30
    multi_positive_metal_max_aspect: float = 4.0
    multi_positive_metal_max_boundary: float = 0.55
    multi_positive_metal_min_clean: float = 0.50
    # v0.2.37 multi-hypothesis scoring for ambiguous negative/mixed responses.
    # These thresholds gate only reinterpretation; anomaly detection is unchanged.
    hypothesis_min_score: float = 0.50
    hypothesis_min_margin: float = 0.04
    hypothesis_void_min_anomaly: float = 3.5
    hypothesis_void_min_negative_fraction: float = 0.55
    hypothesis_model_weight: float = 0.80


DEFAULT_CLASSIFICATION_CONFIG = ClassificationConfig()


def _depth_stability(candidate: Candidate) -> float:
    if candidate.depth_stability_score > 0:
        return candidate.depth_stability_score
    depth = (
        candidate.depth_estimate
        if math.isfinite(candidate.depth_estimate)
        else candidate.depth_mean
    )
    if not math.isfinite(depth) or abs(depth) < 1e-9:
        return 0.5
    spread = (
        candidate.depth_estimate_std
        if math.isfinite(candidate.depth_estimate_std)
        else candidate.depth_std
    )
    ratio = abs(spread) / abs(depth)
    return max(0.0, min(1.0, 1.0 - ratio / 0.5))


def apply_local_geology_context(candidate: Candidate) -> Candidate:
    """Apply the v0.2.54 conservative local-geology classification refinement.

    This helper is intentionally downstream-only. It changes only the pattern
    vocabulary for a weak, non-linear local residual whose geometry is more
    consistent with a broad/regional response than a compact target. Detection,
    anomaly values, thresholds, soil corrections, and physical inversion remain
    untouched.
    """
    clean = 1.0 - max(0.0, min(1.0, float(candidate.artifact_score)))
    if (
        candidate.pattern_hypothesis
        in {"metallic-like", "linear-metal-compatible", "unknown", "cavity-like"}
        and candidate.polarity == "positive"
        and candidate.scale_class == "local"
        and candidate.anomaly_score < 4.5
        and candidate.broadness_score >= 0.12
        and candidate.linearity_score < 0.35
        and candidate.multiresolution_consensus <= 0.40
        and candidate.area_cells >= 7
        and candidate.boundary_contact_ratio < 0.35
        and clean >= 0.65
        and candidate.solidity <= 0.75
    ):
        # Pure (M8): return a copy; the input is never mutated.
        return candidate.with_updates(
            pattern_hypothesis="geological-like",
            response_family="broad-response",
            classification_method="local-geology-context",
        )
    return candidate


def classify_candidate(
    candidate: Candidate, config: ClassificationConfig | None = None
) -> Candidate:
    """Select the public pattern hypothesis from the unified Evidence Model.

    Single authoritative scorer: ``core.evidence.score_hypotheses`` /
    ``classify_from_evidence`` (Evidence Model v1).

    This function used to call ``_apply_compatibility_feature_pass`` first, a
    ~230-line rule cascade that derived an intermediate label from morphology
    thresholds. It was removed as dead code: every field the pass wrote
    (``hypothesis_scores``, ``selected_hypothesis_margin``, ``second_hypothesis``,
    ``classification_method``) was overwritten unconditionally by the
    ``with_updates`` below, and its ``hypothesis`` local never escaped the
    function. Verified by neutralising the whole pass and confirming
    byte-identical output for single-scan, negative-polarity and site
    candidates. The mutation ratchet is what surfaced it: the
    ``classify-sigmoid-clamp-widened`` mutant survived because the clamp it
    mutated lived in a function whose return value nothing read.
    """
    # `config` is accepted and ignored: the rule cascade whose thresholds it
    # carried is gone, and the authoritative scorer below is configured by
    # DEFAULT_EVIDENCE_MODEL_CONFIG. The parameter stays because
    # `analyze_scan(classification_config=...)` passes it positionally by
    # keyword at two call sites and is part of the public surface.
    del config
    depth_stability = _depth_stability(candidate)
    polarity = candidate.polarity
    (model_hypothesis, model_scores, model_margin, model_second, model_reason, model_method) = (
        classify_from_evidence(candidate, config=DEFAULT_EVIDENCE_MODEL_CONFIG)
    )
    # Pure (M8): every selection below lands in locals; the single
    # with_updates at the end is the only copy. Reads below touch the
    # `hypothesis` local plus fields this function never changes, except
    # where noted.
    hypothesis = model_hypothesis
    evidence_score = round(float(model_scores.get(model_hypothesis, 0.0)), 3)
    # v0.4.2 (audit F-16): cross-scan confirmation used to die here -- the
    # fusion blend (detection_rate et al.) was overwritten by the
    # morphology-only hypothesis score, so "detected in 3/3 scans" never
    # reached the final evidence number. For fused multi-scan candidates the
    # morphology support is now blended with detection repeatability
    # (0.8/0.2): full confirmation lifts the number, partial detection cuts
    # it. Single-scan candidates are untouched (byte-identical): with one
    # scan there is no confirmation information, and detection_rate's 1.0
    # default would otherwise reward the absence of evidence. Diversity
    # coverages are deliberately NOT blended -- they are self-relative to
    # the site's own scan set (audit F-02) and would re-inflate duplicates.
    if (
        int(getattr(candidate, "scan_count", 1)) >= 2
        and str(getattr(candidate, "multi_scan_status", "single-scan")) == "multi-scan"
    ):
        confirmed = min(max(float(candidate.detection_rate), 0.0), 1.0)
        evidence_score = round(min(max(0.8 * evidence_score + 0.2 * confirmed, 0.0), 1.0), 3)
    confidence = round(min(max(evidence_score, 0.1), 0.95), 2)
    # explain_hypothesis_support reads feature-level fields only (never the
    # hypothesis selections above), so calling it on the input is identical.
    hypothesis_evidence = explain_hypothesis_support(candidate)
    if hypothesis == "tunnel-like" and candidate.linearity_score >= 0.45:
        response_family = "linear-response"
    elif hypothesis == "linear-metal-compatible":
        response_family = "linear-metal-response"
    elif (
        hypothesis == "metallic-like"
        and candidate.line_support_score >= 0.70
        and candidate.axial_signal_continuity_score >= 0.65
        and candidate.linearity_score >= 0.40
    ):
        response_family = "linear-response"
    elif hypothesis == "metallic-like" or hypothesis == "cavity-like":
        response_family = "monopolar-response"
    elif hypothesis == "geological-like":
        response_family = "broad-response"
    elif hypothesis == "boundary-effect-like":
        response_family = (
            "edge-limited" if candidate.boundary_contact_ratio >= 0.80 else "unclassified"
        )
    elif hypothesis == "irregular-anomaly":
        response_family = "irregular-response"
    else:
        response_family = "unclassified"
    notes: list[str] = []
    # Preserve decomposition provenance across (re-)classification. The
    # pipeline classifies once before separation and again after; rebuilding
    # notes from scratch used to silently drop the "separated from parent /
    # decomposition hypothesis" record. Only provenance markers are carried
    # over (never stale metric notes), without duplication.
    previous_notes = candidate.notes or ""
    if previous_notes:
        for part in [p.strip() for p in previous_notes.split(";")]:
            low = part.lower()
            if (
                part
                and ("separat" in low or "dipole" in low or "parent candidate" in low)
                and part not in notes
            ):
                notes.append(part)
    depth_value = (
        candidate.depth_estimate
        if math.isfinite(candidate.depth_estimate)
        else candidate.depth_mean
    )
    if not math.isfinite(depth_value):
        notes.append("no usable depth estimate in this component")
    elif depth_stability < 0.4:
        notes.append("depth varies substantially within this cluster")
    if candidate.depth_valid_fraction < 0.8 and math.isfinite(depth_value):
        notes.append(f"depth coverage is only {candidate.depth_valid_fraction:.0%}")
    if candidate.multiscale_persistence < 0.34:
        notes.append("weak multiscale persistence")
    if candidate.artifact_score >= 0.5:
        notes.append("artifact-prone geometry or sparse neighborhood")
    if candidate.boundary_contact_ratio >= 0.45:
        notes.append("candidate touches or closely follows the scan boundary")
    if candidate.solidity < 0.5:
        notes.append("irregular/concave geometry")
    if polarity == "mixed":
        notes.append("mixed signed response")
    if candidate.scale_class == "broad":
        notes.append("regional/broad-scale channel contributed")
    if candidate.line_support_score >= 0.58:
        notes.append(f"line-support evidence {candidate.line_support_score:.2f}")
    if candidate.axial_signal_continuity_score >= 0.70:
        notes.append(f"axial continuity evidence {candidate.axial_signal_continuity_score:.2f}")
    if hypothesis in {"metallic-like", "linear-metal-compatible", "cavity-like", "tunnel-like"}:
        notes.append("pattern compatibility only; not material identification or proof of a void")
    if hypothesis == "linear-metal-compatible":
        notes.append(
            "linear-metal refinement supported by line support, axial continuity, and morphology coherence"
        )
    if hypothesis == "tunnel-like" and candidate.depth_stability_score < 0.45:
        notes.append("linear pattern has limited depth stability")

    classified = candidate.with_updates(
        hypothesis_scores=model_scores,
        selected_hypothesis_margin=model_margin,
        second_hypothesis=model_second,
        classification_method=model_method,
        pattern_hypothesis=hypothesis,
        evidence_score=evidence_score,
        confidence=confidence,
        classification_alternatives=model_scores.copy(),
        hypothesis_evidence=hypothesis_evidence,
        classification_conflict_score=round(max(0.0, min(1.0, (0.15 - model_margin) / 0.15)), 3),
        classification_conflict_reason=model_reason,
        response_family=response_family,
        notes="; ".join(notes),
    )
    from ..gates.quality import assess_candidate_quality

    return assess_candidate_quality(classified)

"""Polarity-conflict verdicts: preserve disagreement as disagreement.

Deepened module owning the full conflict lifecycle behind a two-function
interface: :func:`build_conflict_candidates` reunites contradicting
single-scan fragments into conflict records, and :func:`apply_conflict_verdict`
forces the residual unknown hypothesis on them. Descriptor fusion
(``fusion``), uncertainty (``uncertainty``), and quality re-assessment
(``gates.quality``) live behind this seam; callers pass a
:class:`ConflictBuildContext` plus candidates and never import those modules
for conflict purposes.

Behavior is byte-identical to the former ``verdicts`` trio (audit F-03);
frozen gates prove it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import ndimage

from ..gates.quality import assess_candidate_quality
from ..models import Candidate
from .consensus import _scan_extent
from .fusion import fuse_depth, fuse_geometry
from .registration import AlignmentResult
from .separation import DEFAULT_SEPARATION_CONFIG
from .uncertainty import compute_uncertainty_profile
from .verdicts import _majority

if TYPE_CHECKING:
    from .analyze_site import ScanObservation


@dataclass(frozen=True)
class ConflictBuildContext:
    """Everything the conflict build needs beyond the dropped fragments."""

    observations: list[ScanObservation]
    alignments: dict[str, AlignmentResult]
    reference: ScanObservation
    resolution: int
    support: np.ndarray[Any, Any]
    sign_consistency: np.ndarray[Any, Any]
    multires_persistence: np.ndarray[Any, Any] | None
    min_size: int
    distance_threshold: float


def _contested_components(
    support: np.ndarray[Any, Any],
    sign_consistency: np.ndarray[Any, Any],
    *,
    min_size: int,
) -> tuple[np.ndarray[Any, Any], int]:
    """Connected map zones where the scans disagree (audit F-03).

    A contested cell shows anomaly-level response in at least half the
    covering scans (``support >= 0.5``) with no clear majority sign
    (``sign_consistency <= 0.5``). There is deliberately NO per-side energy
    gate: under weak registration the opposing lobes separate, and each
    side's peak sits in single-sign territory -- requiring both signs to be
    independently strong in the same cell would blind the detector to
    exactly the misregistered contradictions it exists for. Evidentiary
    weight comes from the candidate-level gates instead (opposing strong
    fragments from different scans sharing the zone); the zone is only the
    spatial coincidence test. The component size floor keeps speckle out.
    """
    finite = np.isfinite(support) & np.isfinite(sign_consistency)
    contested = finite & (support >= 0.5) & (sign_consistency <= 0.5)
    structure = ndimage.generate_binary_structure(2, 2)
    labels, n = ndimage.label(contested, structure=structure)
    if n and min_size > 1:
        sizes = ndimage.sum(contested, labels, index=range(1, int(n) + 1))
        keep = [i + 1 for i, size in enumerate(sizes) if size >= min_size]
        mask = np.isin(labels, keep) if keep else np.zeros_like(contested)
        labels, n = ndimage.label(mask, structure=structure)
    return labels.astype(int), int(n)


def _merge_conflict_group(
    members: list[Candidate],
    positions: list[tuple[float, float]],
    labels: list[str],
    *,
    ctx: ConflictBuildContext,
) -> Candidate:
    """Fuse contradicting fragments into one conflict record (audit F-03).

    Descriptor fusion mirrors :func:`fuse_site_candidates` (evidence-weighted
    means, fused depth/geometry, full uncertainty profile) with two deliberate
    differences: ``polarity_consistency`` is 0.0 (total disagreement, not a
    measurement gap) and ``cross_scan_agreement`` stays None -- an agreement
    number for contradicting scans would masquerade as support. Morphology
    here is only an input to the classifier; the verdict pass later forces
    the residual unknown hypothesis with capped confidence.
    """
    observations = ctx.observations
    alignments = ctx.alignments
    reference = ctx.reference
    resolution = ctx.resolution
    multires_persistence = ctx.multires_persistence
    distance_threshold = ctx.distance_threshold
    weights = [max(float(getattr(c, "evidence_score", 0.0) or 0.0), 1e-3) for c in members]
    total_w = sum(weights)

    def _wavg(values: list[float]) -> float:
        return float(sum(v * w for v, w in zip(values, weights, strict=True)) / max(total_w, 1e-9))

    base = max(members, key=lambda c: float(getattr(c, "evidence_score", 0.0) or 0.0))
    x = _wavg([c.x_center for c in members])
    y = _wavg([c.y_center for c in members])
    n_obs = len(observations)
    detection_rate = len(labels) / max(n_obs, 1)
    member_obs = [
        observations[[o.label for o in observations].index(lab)]
        for lab in labels
        if lab in {o.label for o in observations}
    ]
    all_dirs = {o.direction_key for o in observations}
    all_spaces = {o.spacing_key for o in observations}
    all_patterns = {o.pattern_key for o in observations}
    direction_cov = len({o.direction_key for o in member_obs}) / max(len(all_dirs), 1)
    spacing_cov = len({o.spacing_key for o in member_obs}) / max(len(all_spaces), 1)
    traversal_cov = len({o.pattern_key for o in member_obs}) / max(len(all_patterns), 1)
    pos_spread = float(np.std([p[0] for p in positions]))
    pos_spread_v = float(np.std([p[1] for p in positions]))
    position_stability = float(
        np.clip(1.0 - np.hypot(pos_spread, pos_spread_v) / max(distance_threshold * 2, 0.05), 0, 1)
    )
    registration_values = [
        alignments[lab].registration_evidence for lab in labels if lab in alignments
    ]
    # v0.4.2 (audit F-10): absent registration is unknown (0.5), not perfect.
    reg_cons = float(np.mean(registration_values)) if registration_values else 0.5
    signal_values = [c.anomaly_score for c in members if np.isfinite(c.anomaly_score)]
    signal_cons = (
        float(
            np.clip(
                1.0
                - np.std(signal_values) / max(float(np.mean(np.abs(signal_values))) * 0.35, 1e-9),
                0,
                1,
            )
        )
        if len(signal_values) > 1
        else 1.0
    )
    rx0, rx1, ry0, ry1 = _scan_extent(reference.grid)
    u = float(np.clip((x - rx0) / max(rx1 - rx0, 1e-9), 0, 1))
    v = float(np.clip((y - ry0) / max(ry1 - ry0, 1e-9), 0, 1))
    multi = 0.0
    if multires_persistence is not None:
        rr = int(np.clip(round(v * (resolution - 1)), 0, resolution - 1))
        cc = int(np.clip(round(u * (resolution - 1)), 0, resolution - 1))
        r = max(
            2,
            int(
                round(
                    np.median([max(c.width, c.height) for c in members])
                    / (max(rx1 - rx0, 1e-9))
                    * resolution
                    / 2
                )
            ),
        )
        patch = multires_persistence[
            max(0, rr - r) : min(resolution, rr + r + 1),
            max(0, cc - r) : min(resolution, cc + r + 1),
        ]
        multi = float(np.nanmean(patch)) if patch.size and np.any(np.isfinite(patch)) else 0.0
    depth_fusion = fuse_depth(members)
    geometry_fusion = fuse_geometry(members)
    sizes = [max(c.major_extent, c.minor_extent) for c in members]
    geometry_cons = float(np.clip(1.0 - np.std(sizes) / max(float(np.mean(sizes)), 1e-9), 0, 1))
    uncertainty = compute_uncertainty_profile(
        members,
        positions,
        registration_values,
        detection_rate=detection_rate,
        direction_persistence=direction_cov,
        spacing_persistence=spacing_cov,
        traversal_persistence=traversal_cov,
        polarity_consistency=0.0,
        position_stability=position_stability,
        multiscan_signal_consistency=signal_cons,
        multiresolution_consensus=multi,
        depth_cross_scan_consistency=float(depth_fusion.consistency),
        geometry_consistency=float(
            np.clip(0.5 * geometry_cons + 0.5 * geometry_fusion.geometry_size_consistency, 0, 1)
        ),
    )
    metric_ok = all(getattr(c, "metric_geometry_reliable", True) for c in members)
    return replace(
        base,
        x_center=x,
        y_center=y,
        depth_mean=float(np.mean([c.depth_mean for c in members if np.isfinite(c.depth_mean)]))
        if any(np.isfinite(c.depth_mean) for c in members)
        else float("nan"),
        depth_std=float(depth_fusion.std),
        n_points=int(round(np.mean([c.n_points for c in members]))),
        area_cells=int(round(np.mean([c.area_cells for c in members]))),
        width=float(geometry_fusion.width),
        height=float(geometry_fusion.height),
        aspect_ratio=float(geometry_fusion.aspect_ratio),
        orientation_deg=float(geometry_fusion.orientation_deg),
        peak_signal=float(np.median([c.peak_signal for c in members])),
        mean_signal=float(np.mean([c.mean_signal for c in members])),
        anomaly_score=float(np.max([abs(c.anomaly_score) for c in members])),
        shape_class=_majority([c.shape_class for c in members]),
        pattern_hypothesis="unclassified",
        confidence=0.0,
        notes="",
        signed_anomaly_mean=_wavg([c.signed_anomaly_mean for c in members]),
        positive_peak=float(np.max([c.positive_peak for c in members])),
        negative_peak=float(np.min([c.negative_peak for c in members])),
        polarity="mixed",
        anomaly_density=float(np.mean([c.anomaly_density for c in members])),
        compactness=_wavg([c.compactness for c in members]),
        continuity_score=float(np.mean([c.continuity_score for c in members])),
        artifact_score=float(np.mean([c.artifact_score for c in members])),
        multiscale_persistence=float(np.mean([c.multiscale_persistence for c in members])),
        evidence_score=0.0,
        scan_count=len(labels),
        detection_rate=round(detection_rate, 3),
        directional_persistence=round(direction_cov, 3),
        spacing_persistence=round(spacing_cov, 3),
        traversal_persistence=round(traversal_cov, 3),
        polarity_consistency=0.0,
        position_stability=round(position_stability, 3),
        contributing_scans=sorted(labels),
        multi_scan_status="multi-scan",
        major_extent=float(geometry_fusion.major_extent),
        minor_extent=float(geometry_fusion.minor_extent),
        elongation_ratio=float(geometry_fusion.elongation_ratio),
        linearity_score=float(geometry_fusion.linearity_score),
        solidity=float(geometry_fusion.solidity),
        boundary_contact_ratio=float(geometry_fusion.boundary_contact_ratio),
        broadness_score=float(geometry_fusion.broadness_score),
        centroid_weighted_x=float(np.mean([c.centroid_weighted_x for c in members])),
        centroid_weighted_y=float(np.mean([c.centroid_weighted_y for c in members])),
        geometry_quality=float(geometry_fusion.geometry_fusion_quality),
        width_consistency_score=float(
            np.average([c.width_consistency_score for c in members], weights=weights)
        ),
        orientation_stability_score=float(
            np.average([c.orientation_stability_score for c in members], weights=weights)
        ),
        morphology_line_coherence_score=float(
            np.average([c.morphology_line_coherence_score for c in members], weights=weights)
        ),
        morphology_axial_coverage_score=float(
            np.average([c.morphology_axial_coverage_score for c in members], weights=weights)
        ),
        depth_estimate=float(depth_fusion.estimate),
        depth_estimate_std=float(depth_fusion.std),
        depth_min=float(depth_fusion.minimum),
        depth_max=float(depth_fusion.maximum),
        depth_range=float(depth_fusion.value_range),
        depth_valid_fraction=float(
            np.average([c.depth_valid_fraction for c in members], weights=weights)
        ),
        depth_stability_score=float(depth_fusion.consistency),
        depth_relative_dispersion=float(depth_fusion.relative_dispersion),
        depth_cross_scan_consistency=float(depth_fusion.consistency),
        geometry_consistency=float(
            np.clip(0.5 * geometry_cons + 0.5 * geometry_fusion.geometry_size_consistency, 0, 1)
        ),
        multiscan_signal_consistency=signal_cons,
        multiresolution_consensus=multi,
        registration_consistency=reg_cons,
        scale_class=_majority([c.scale_class for c in members]),
        multi_scan_evidence_score=uncertainty.evidence_score,
        evidence_uncertainty=uncertainty.evidence_uncertainty,
        depth_uncertainty=uncertainty.depth_uncertainty,
        geometry_uncertainty=uncertainty.geometry_uncertainty,
        signal_uncertainty=uncertainty.signal_uncertainty,
        position_uncertainty=uncertainty.position_uncertainty,
        registration_uncertainty=uncertainty.registration_uncertainty,
        leave_one_out_stability=uncertainty.leave_one_out_stability,
        effective_scan_count=uncertainty.effective_scan_count,
        uncertainty_flags=list(uncertainty.flags),
        evidence_components=uncertainty.components,
        fused_depth_iqr=float(depth_fusion.iqr),
        fused_depth_consistency=float(depth_fusion.consistency),
        fused_depth_quality=float(depth_fusion.quality),
        depth_measurement_count=int(depth_fusion.measurement_count),
        orientation_dispersion_deg=float(geometry_fusion.orientation_dispersion_deg),
        orientation_consistency=float(geometry_fusion.orientation_consistency),
        geometry_size_consistency=float(geometry_fusion.geometry_size_consistency),
        geometry_fusion_quality=float(geometry_fusion.geometry_fusion_quality),
        geometry_measurement_count=int(geometry_fusion.measurement_count),
        metric_geometry_reliable=metric_ok,
        geometry_reliability_reason=(
            "all contributing scans have physical/metric coordinates"
            if metric_ok
            else "at least one contributing scan uses non-metric/index-only coordinates; metric geometry is not verified"
        ),
        dielectric_constant=(
            float(
                np.median([
                    c.dielectric_constant
                    for c in members
                    if c.dielectric_constant is not None and np.isfinite(c.dielectric_constant)
                ])
            )
            if any(
                c.dielectric_constant is not None and np.isfinite(c.dielectric_constant)
                for c in members
            )
            else None
        ),
        relative_permeability=(
            float(
                np.median([
                    c.relative_permeability
                    for c in members
                    if c.relative_permeability is not None and np.isfinite(c.relative_permeability)
                ])
            )
            if any(
                c.relative_permeability is not None and np.isfinite(c.relative_permeability)
                for c in members
            )
            else None
        ),
        mineralization_risk=float(np.median([c.mineralization_risk for c in members]))
        if members
        else 0.0,
        cross_scan_agreement=None,
        hypothesis_scores={},
        response_family="unclassified",
        polarity_conflict=True,
    )


def build_conflict_candidates(
    dropped: list[Candidate],
    ctx: ConflictBuildContext,
) -> list[Candidate]:
    """Reunite contradicting fragments into conflict records (audit F-03).

    Strong opposite-sign fragments that the repeatability gate drops (each
    seen in one scan) are grouped by contested map component. A group spanning
    at least two scans with both polarities present becomes ONE conflict
    candidate instead of vanishing -- or worse, resurfacing as two confident
    opposite conclusions. Groups from a single scan, without both signs, or
    with weak signal are left dropped: contradiction requires independent
    witnesses on both sides.
    """
    min_anomaly = float(DEFAULT_SEPARATION_CONFIG.single_scan_min_anomaly_score)
    strong = [
        c
        for c in dropped
        if int(getattr(c, "scan_count", 1)) < 2
        and abs(float(getattr(c, "anomaly_score", 0.0) or 0.0)) >= min_anomaly
        and c.polarity in ("positive", "negative")
    ]
    if len(strong) < 2:
        return []
    comp_labels, n_comp = _contested_components(
        ctx.support,
        ctx.sign_consistency,
        min_size=int(ctx.min_size),
    )
    if not n_comp:
        return []
    rx0, rx1, ry0, ry1 = _scan_extent(ctx.reference.grid)
    resolution = ctx.resolution
    groups: dict[int, list[tuple[Candidate, tuple[float, float]]]] = {}
    for cand in strong:
        # Assign via footprint overlap, not center lookup: under weak
        # registration the members' peaks sit in single-sign territory while
        # the contested zone bridges their footprints (verified Iron Box
        # geometry: peaks 4.5 cells apart, footprints share component 1).
        u0 = (cand.x_center - cand.width / 2.0 - rx0) / max(rx1 - rx0, 1e-9)
        u1 = (cand.x_center + cand.width / 2.0 - rx0) / max(rx1 - rx0, 1e-9)
        v0 = (cand.y_center - cand.height / 2.0 - ry0) / max(ry1 - ry0, 1e-9)
        v1 = (cand.y_center + cand.height / 2.0 - ry0) / max(ry1 - ry0, 1e-9)
        r0 = int(np.clip(np.floor(v0 * (resolution - 1)), 0, resolution - 1))
        r1 = int(np.clip(np.ceil(v1 * (resolution - 1)), 0, resolution - 1))
        c0 = int(np.clip(np.floor(u0 * (resolution - 1)), 0, resolution - 1))
        c1 = int(np.clip(np.ceil(u1 * (resolution - 1)), 0, resolution - 1))
        patch = comp_labels[r0 : r1 + 1, c0 : c1 + 1]
        present = [int(v) for v in np.unique(patch) if int(v) > 0]
        if not present:
            continue
        comp = max(present, key=lambda cid: int(np.count_nonzero(patch == cid)))
        u = float(np.clip((cand.x_center - rx0) / max(rx1 - rx0, 1e-9), 0, 1))
        v = float(np.clip((cand.y_center - ry0) / max(ry1 - ry0, 1e-9), 0, 1))
        groups.setdefault(comp, []).append((cand, (u, v)))
    out: list[Candidate] = []
    for comp in sorted(groups):
        members = [c for c, _ in groups[comp]]
        positions = [p for _, p in groups[comp]]
        labels = sorted({lab for c in members for lab in (c.contributing_scans or [])})
        if len(labels) < 2:
            continue
        pols = {c.polarity for c in members}
        if "positive" not in pols or "negative" not in pols:
            continue
        out.append(_merge_conflict_group(members, positions, labels, ctx=ctx))
    return out


def apply_conflict_verdict(candidates: list[Candidate]) -> list[Candidate]:
    """Force the residual unknown hypothesis on contradicting candidates.

    Applies to conflict-built records (``polarity_conflict`` marker) and to
    retained fused candidates whose members split on polarity
    (``polarity_consistency <= 0.5`` with at least two scans) -- the
    good-registration shape of the same failure. Merged dipoles are exempt:
    opposite lobes reunited by the dipole machinery are one signed response,
    not a contradiction. The verdict keeps the classifier's full support
    table as audit trail but selects unknown at its residual support, which
    caps confidence; quality is re-assessed from the capped evidence so the
    review status follows. Pure at element level (M9): matching candidates
    are replaced by verdict copies; inputs are never mutated (verified by
    test_apply_conflict_verdict_replaces_not_mutates). The returned list is
    a new list object.
    """
    out: list[Candidate] = []
    for c in candidates:
        if c.pattern_hypothesis == "dipolar-response" or c.response_family == "dipolar-response":
            out.append(c)
            continue
        marked = bool(getattr(c, "polarity_conflict", False))
        split_members = (
            int(getattr(c, "scan_count", 1)) >= 2
            and float(getattr(c, "polarity_consistency", 1.0)) <= 0.5
        )
        if not (marked or split_members):
            out.append(c)
            continue
        scores = dict(getattr(c, "hypothesis_scores", {}) or {})
        unknown_ev = round(float(scores.get("unknown", 0.0)), 3)
        confidence = round(min(max(unknown_ev, 0.1), 0.95), 2)
        scans = (
            ", ".join(c.contributing_scans)
            if getattr(c, "contributing_scans", None)
            else "contributing scans"
        )
        assessed = assess_candidate_quality(
            c.with_updates(
                polarity_conflict=True,
                pattern_hypothesis="unknown",
                evidence_score=unknown_ev,
                confidence=confidence,
                response_family="unclassified",
                classification_conflict_score=1.0,
                classification_conflict_reason=(
                    f"polarity conflict across scans ({scans}): opposite-sign responses "
                    f"(+{c.positive_peak:.1f}/-{abs(c.negative_peak):.1f}) at the same site response; "
                    "the evidence argues against itself, so no specific pattern conclusion is warranted"
                ),
            )
        )
        quality_flags = list(assessed.quality_flags or [])
        if "polarity-conflict" not in quality_flags:
            quality_flags = quality_flags + ["polarity-conflict"]
        sentence = (
            f"polarity conflict across scans ({scans}): opposite-sign strong responses "
            f"(+{c.positive_peak:.1f}/-{abs(c.negative_peak):.1f}); specific-pattern "
            f"conclusions withheld, confidence capped at {confidence:.2f}"
        )
        notes = assessed.notes or ""
        # Unconditional append, matching the original in-place version
        # exactly (no idempotency guard added here: behavior parity first).
        notes = ((notes + "; ") if notes else "") + sentence
        out.append(assessed.with_updates(quality_flags=quality_flags, notes=notes))
    return out


__all__ = [
    "ConflictBuildContext",
    "apply_conflict_verdict",
    "build_conflict_candidates",
]

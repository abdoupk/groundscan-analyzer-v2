"""Site-level multi-scan registration, multiresolution fusion and candidate consensus."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..core.anomaly import AnomalyMap
from ..core.artifact import ArtifactMap, detect_artifacts
from ..core.classify import apply_local_geology_context
from ..core.grid import Grid2D
from ..gates.operational import gated_copy
from ..gates.quality import assess_candidate_quality, quality_summary
from ..models import Candidate, ScanData, is_metric_coordinates
from ..services.machine_contract import write_candidates_csv
from .conflict_verdicts import (
    ConflictBuildContext,
    apply_conflict_verdict,
    build_conflict_candidates,
)
from .consensus import _cluster_items, _consensus_maps, _scan_extent
from .fusion import fuse_depth, fuse_geometry
from .registration import AlignmentResult, align_grids
from .separation import resolve_dipole_pairs, separate_fused_candidates
from .uncertainty import compute_uncertainty_profile
from .verdicts import (
    _candidate_observation_point,
    _duplicate_scan_groups,
    _majority,
    _prune_repeatability_fused_candidates,
    _retain_repeatable_fused_candidates,
)


@dataclass
class ScanObservation:
    label: str
    scan: ScanData
    grid: Grid2D
    anomaly: AnomalyMap
    artifacts: ArtifactMap
    candidates: list[Candidate]

    @property
    def orientation_deg(self) -> float | None:
        value = self.scan.metadata.orientation_deg
        if value is None:
            value = self.scan.metadata.extra.get("orientation_deg")
        if value is None:
            return None
        try:
            number = float(value)
            return number if np.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @property
    def spacing_key(self) -> str:
        value = self.scan.metadata.line_spacing_m
        if value is None:
            value = self.scan.metadata.extra.get("line_spacing_m")
        if value is None:
            return "unknown"
        try:
            number = float(value)
            return f"{number:.3f}m" if np.isfinite(number) else "unknown"
        except (TypeError, ValueError):
            return "unknown"

    @property
    def pattern_key(self) -> str:
        value = self.scan.metadata.scan_pattern
        if not value:
            value = self.scan.metadata.extra.get("scan_pattern") or self.scan.metadata.extra.get(
                "scan_mode"
            )
        value = str(value).strip().lower() if value is not None else "unknown"
        if "zig" in value:
            return "zigzag"
        if "par" in value or "line" in value:
            return "parallel"
        return value or "unknown"

    @property
    def direction_key(self) -> str:
        value = self.orientation_deg
        if value is None:
            return "unknown"
        axis = round((value % 180.0) / 22.5) * 22.5
        return f"{axis % 180:g}deg"

    @property
    def field_quality(self) -> dict[str, Any]:
        value = (self.scan.metadata.extra or {}).get("field_quality", {})
        return dict(value) if isinstance(value, dict) else {}

    @property
    def field_quality_blocked(self) -> bool:
        policy = (self.scan.metadata.extra or {}).get("field_quality_policy", {})
        return bool(isinstance(policy, dict) and policy.get("candidate_extraction_blocked", False))


@dataclass
class SiteRegistration:
    reference_label: str
    alignments: dict[str, AlignmentResult]
    registration_consistency: float
    status: str = "strong"
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


@dataclass
class MultiScanResult:
    observations: list[ScanObservation]
    fused_candidates: list[Candidate]
    reference_label: str
    registration: SiteRegistration | None = None
    consensus_support: np.ndarray[Any, Any] | None = None
    consensus_signed: np.ndarray[Any, Any] | None = None
    consensus_persistence: np.ndarray[Any, Any] | None = None
    consensus_positive: np.ndarray[Any, Any] | None = None
    consensus_negative: np.ndarray[Any, Any] | None = None
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    @property
    def scan_count(self) -> int:
        return len(self.observations)


def fuse_site_candidates(
    observations: list[ScanObservation],
    reference: ScanObservation | None = None,
    alignments: dict[str, AlignmentResult] | None = None,
    distance_threshold: float = 0.06,
    consensus_support: np.ndarray[Any, Any] | None = None,
    multires_persistence: np.ndarray[Any, Any] | None = None,
) -> list[Candidate]:
    if not observations:
        return []
    reference = reference or observations[0]
    alignments = alignments or {}
    resolution = int(consensus_support.shape[0]) if consensus_support is not None else 40
    items = []
    for obs in observations:
        alignment = None if obs.label == reference.label else alignments.get(obs.label)
        for cand in obs.candidates:
            u, v, scale = _candidate_observation_point(cand, obs, reference, alignment, resolution)
            items.append({
                "obs": obs,
                "candidate": cand,
                "u": u,
                "v": v,
                "scale": scale,
                "alignment": alignment,
            })
    clusters = _cluster_items(items, distance_threshold)

    all_dirs = {o.direction_key for o in observations}
    all_spaces = {o.spacing_key for o in observations}
    all_patterns = {o.pattern_key for o in observations}
    out = []
    rx0, rx1, ry0, ry1 = _scan_extent(reference.grid)
    for idx, cluster in enumerate(clusters, 1):
        # A scan can contribute more than one nearby fragment. For site-level
        # evidence, count each observation once and retain the strongest fragment
        # from that scan to avoid over-weighting a single acquisition.
        best_by_label: dict[str, dict[str, Any]] = {}
        for q in cluster:
            key = q["obs"].label
            current = best_by_label.get(key)
            if (
                current is None
                or q["candidate"].evidence_score > current["candidate"].evidence_score
            ):
                best_by_label[key] = q
        cluster = list(best_by_label.values())
        members = [q["candidate"] for q in cluster]
        obs_members = [q["obs"] for q in cluster]
        weights = [
            max(
                1e-3,
                0.55 * float(np.clip(getattr(c, "geometry_quality", 0.5), 0, 1))
                + 0.45 * float(np.clip(getattr(c, "evidence_score", 0.0), 0, 1)),
            )
            for c in members
        ]
        labels = {o.label for o in obs_members}
        u = float(np.mean([q["u"] for q in cluster]))
        v = float(np.mean([q["v"] for q in cluster]))
        x = rx0 + u * (rx1 - rx0)
        y = ry0 + v * (ry1 - ry0)
        detection_rate = len(labels) / len(observations)
        direction_cov = len({o.direction_key for o in obs_members}) / max(len(all_dirs), 1)
        spacing_cov = len({o.spacing_key for o in obs_members}) / max(len(all_spaces), 1)
        traversal_cov = len({o.pattern_key for o in obs_members}) / max(len(all_patterns), 1)
        pols = [c.polarity for c in members if c.polarity != "mixed"]
        majority_pol = _majority(pols) if pols else "mixed"
        # No opposing-sign evidence (all mixed / empty): no contradiction
        # observed → full consistency, never a false conflict.
        pol_cons = sum(p == majority_pol for p in pols) / len(pols) if pols else 1.0
        # Single observation: repeatability is not estimable → neutral 0.5
        # (unknown, never perfect), matching the uncertainty module and the
        # absent-registration precedent below. std([x]) == 0 must not read
        # as perfect stability.
        single_obs = len(cluster) < 2
        pos_spread = float(np.std([q["u"] for q in cluster]))
        pos_spread_v = float(np.std([q["v"] for q in cluster]))
        position_stability = (
            0.5
            if single_obs
            else float(
                np.clip(
                    1.0 - np.hypot(pos_spread, pos_spread_v) / max(distance_threshold * 2, 0.05),
                    0,
                    1,
                )
            )
        )
        depth_fusion = fuse_depth(members)
        geometry_fusion = fuse_geometry(members)
        depth_est = float(depth_fusion.estimate)
        depth_std = float(depth_fusion.std)
        depth_cons = float(depth_fusion.consistency)
        registration_values = [
            q["alignment"].registration_evidence for q in cluster if q["alignment"] is not None
        ]
        # v0.4.2 (audit F-10): no registration info is unknown (0.5), never
        # perfect. Treating absent evidence as 1.0 inflated single-cluster
        # evidence pre-cap and misled any consumer without the retain rule.
        reg_cons = float(np.mean(registration_values)) if registration_values else 0.5
        signal_values = [c.anomaly_score for c in members if np.isfinite(c.anomaly_score)]
        signal_cons = (
            float(
                np.clip(
                    1.0 - np.std(signal_values) / max(np.mean(np.abs(signal_values)) * 0.35, 1e-9),
                    0,
                    1,
                )
            )
            if len(signal_values) > 1
            else 1.0
        )
        cons = 0.0
        multi = 0.0
        if consensus_support is not None:
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
            patch = consensus_support[
                max(0, rr - r) : min(resolution, rr + r + 1),
                max(0, cc - r) : min(resolution, cc + r + 1),
            ]
            # All-NaN windows: nanmean warns and returns NaN → neutral 0.0.
            cons = float(np.nanmean(patch)) if patch.size and np.any(np.isfinite(patch)) else 0.0
            if multires_persistence is not None:
                mp = multires_persistence[
                    max(0, rr - r) : min(resolution, rr + r + 1),
                    max(0, cc - r) : min(resolution, cc + r + 1),
                ]
                multi = float(np.nanmean(mp)) if mp.size and np.any(np.isfinite(mp)) else 0.0
        geometry_cons = (
            0.5
            if single_obs
            else float(
                np.clip(
                    1.0
                    - np.std([max(c.major_extent, c.minor_extent) for c in members])
                    / max(np.mean([max(c.major_extent, c.minor_extent) for c in members]), 1e-9),
                    0,
                    1,
                )
            )
        )
        base = float(np.mean([c.evidence_score for c in members]))
        from ..gates.thresholds import fused_evidence_score

        evidence = fused_evidence_score(
            base=base,
            detection_rate=detection_rate,
            direction_cov=direction_cov,
            spacing_cov=spacing_cov,
            traversal_cov=traversal_cov,
            position_stability=position_stability,
            pol_cons=pol_cons,
            signal_cons=signal_cons,
            depth_cons=depth_cons,
            reg_cons=reg_cons,
            cons=cons,
        )
        if len(labels) == 1:
            evidence = min(evidence, 0.45)
        shape = _majority([c.shape_class for c in members])
        pattern = _majority([c.pattern_hypothesis for c in members])
        positions = [(q["u"], q["v"]) for q in cluster]
        uncertainty = compute_uncertainty_profile(
            members,
            positions,
            registration_values,
            detection_rate=detection_rate,
            direction_persistence=direction_cov,
            spacing_persistence=spacing_cov,
            traversal_persistence=traversal_cov,
            polarity_consistency=pol_cons,
            position_stability=position_stability,
            multiscan_signal_consistency=signal_cons,
            multiresolution_consensus=multi,
            depth_cross_scan_consistency=depth_cons,
            geometry_consistency=geometry_cons,
        )
        # Keep the existing evidence score for backward compatibility, while
        # exposing the new uncertainty-aware aggregate separately.
        fused = Candidate(
            id=idx,
            x_center=x,
            y_center=y,
            depth_mean=float(
                np.mean([c.depth_mean for c in members if np.isfinite(c.depth_mean)])
                if any(np.isfinite(c.depth_mean) for c in members)
                else float("nan")
            ),
            depth_std=depth_std,
            n_points=int(round(np.mean([c.n_points for c in members]))),
            area_cells=int(round(np.mean([c.area_cells for c in members]))),
            width=float(geometry_fusion.width),
            height=float(geometry_fusion.height),
            aspect_ratio=float(geometry_fusion.aspect_ratio),
            orientation_deg=float(geometry_fusion.orientation_deg),
            peak_signal=float(np.median([c.peak_signal for c in members])),
            mean_signal=float(np.mean([c.mean_signal for c in members])),
            anomaly_score=float(np.median([c.anomaly_score for c in members])),
            shape_class=shape,
            pattern_hypothesis=pattern,
            confidence=round(min(max(evidence, 0.1), 0.95), 2),
            cross_scan_agreement=round(
                float(0.5 * detection_rate + 0.25 * cons + 0.25 * position_stability), 3
            )
            if len(labels) > 1
            else None,
            notes=f"site-fused candidate; detected in {len(labels)}/{len(observations)} scans",
            signed_anomaly_mean=float(np.mean([c.signed_anomaly_mean for c in members])),
            positive_peak=float(np.median([c.positive_peak for c in members])),
            negative_peak=float(np.median([c.negative_peak for c in members])),
            polarity=majority_pol,
            anomaly_density=float(np.mean([c.anomaly_density for c in members])),
            compactness=float(np.average([c.compactness for c in members], weights=weights)),
            continuity_score=float(np.mean([c.continuity_score for c in members])),
            artifact_score=float(np.mean([c.artifact_score for c in members])),
            multiscale_persistence=float(np.mean([c.multiscale_persistence for c in members])),
            evidence_score=round(evidence, 3),
            scan_count=len(labels),
            detection_rate=round(detection_rate, 3),
            directional_persistence=round(direction_cov, 3),
            spacing_persistence=round(spacing_cov, 3),
            traversal_persistence=round(traversal_cov, 3),
            polarity_consistency=round(pol_cons, 3),
            position_stability=round(position_stability, 3),
            contributing_scans=sorted(labels),
            multi_scan_status="multi-scan" if len(labels) > 1 else "single-scan",
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
            depth_estimate=depth_est,
            depth_estimate_std=depth_std,
            depth_min=float(depth_fusion.minimum),
            depth_max=float(depth_fusion.maximum),
            depth_range=float(depth_fusion.value_range),
            depth_valid_fraction=float(
                np.average(
                    [c.depth_valid_fraction for c in members],
                    weights=[max(1e-3, c.evidence_score) for c in members],
                )
            ),
            depth_stability_score=float(depth_fusion.consistency),
            depth_relative_dispersion=float(depth_fusion.relative_dispersion),
            depth_cross_scan_consistency=depth_cons,
            geometry_consistency=float(
                np.clip(0.5 * geometry_cons + 0.5 * geometry_fusion.geometry_size_consistency, 0, 1)
            ),
            multiscan_signal_consistency=signal_cons,
            multiresolution_consensus=cons,
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
            metric_geometry_reliable=all(
                getattr(c, "metric_geometry_reliable", True) for c in members
            ),
            geometry_reliability_reason=(
                "all contributing scans have physical/metric coordinates"
                if all(getattr(c, "metric_geometry_reliable", True) for c in members)
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
                        if c.relative_permeability is not None
                        and np.isfinite(c.relative_permeability)
                    ])
                )
                if any(
                    c.relative_permeability is not None and np.isfinite(c.relative_permeability)
                    for c in members
                )
                else None
            ),
            mineralization_pct=(
                float(
                    np.median([
                        c.mineralization_pct
                        for c in members
                        if c.mineralization_pct is not None and np.isfinite(c.mineralization_pct)
                    ])
                )
                if any(
                    c.mineralization_pct is not None and np.isfinite(c.mineralization_pct)
                    for c in members
                )
                else None
            ),
            humidity_pct=(
                float(
                    np.median([
                        c.humidity_pct
                        for c in members
                        if c.humidity_pct is not None and np.isfinite(c.humidity_pct)
                    ])
                )
                if any(c.humidity_pct is not None and np.isfinite(c.humidity_pct) for c in members)
                else None
            ),
            homogeneity_pct=(
                float(
                    np.median([
                        c.homogeneity_pct
                        for c in members
                        if c.homogeneity_pct is not None and np.isfinite(c.homogeneity_pct)
                    ])
                )
                if any(
                    c.homogeneity_pct is not None and np.isfinite(c.homogeneity_pct)
                    for c in members
                )
                else None
            ),
            soil_context_completeness=float(np.mean([c.soil_context_completeness for c in members]))
            if members
            else 0.0,
        )
        fused.mineralization_risk = (
            float(np.median([c.mineralization_risk for c in members])) if members else 0.0
        )
        fused.notes += f"; directions={direction_cov:.0%}; spacings={spacing_cov:.0%}; patterns={traversal_cov:.0%}; position={position_stability:.0%}; signal-consistency={signal_cons:.0%}; registration={reg_cons:.0%}; multiresolution-consensus={cons:.0%}; uncertainty={uncertainty.evidence_uncertainty:.0%}."
        if uncertainty.flags:
            fused.notes += " flags=" + ",".join(uncertainty.flags) + "."
        if len(labels) == 1:
            fused.notes += " single-scan; no cross-scan confirmation."
        fused = apply_local_geology_context(fused)
        out.append(fused)
    return sorted(out, key=lambda c: c.evidence_score, reverse=True)


def analyze_site(
    scans: list[tuple[str, ScanData]],
    out_dir: str | Path,
    *,
    reference_label: str | None = None,
    threshold: float = 3.0,
    min_size: int = 3,
    zigzag: str = "auto",
    background_method: str = "multiscale",
    scales: tuple[int, ...] = (3, 5, 9, 15),
    connectivity: int = 8,
    distance_threshold: float = 0.06,
    resolution: int = 40,
    soil_mode: str = "diagnostic",
    extraction_rescue: str = "off",
    fusion_pruning: str = "off",
    field_quality_mode: str = "enforce-hard-block",
    # Remediation Design v2 §11 (Wave 1): forwarded to every per-scan config so
    # the shadow runs for each observation. Off by default; decides nothing.
    shadow_measurement: str = "off",
) -> MultiScanResult:
    if len(scans) < 2:
        raise ValueError("analyze_site requires at least two scans")
    # Canonical input order (audit fix): fusion clusters greedily and updates
    # cluster centroids as items are appended, so the supplied order decided
    # which observations fused together. The same scan set in a different order
    # produced a different candidate count, position and evidence score. Sorting
    # by label here makes the result a function of the data, not of the order a
    # caller happened to pass it in (e.g. filesystem enumeration). An explicit
    # ``reference_label`` still wins, so the reference choice is unchanged.
    scans = sorted(scans, key=lambda item: str(item[0]))
    from .._util import artifact_identity as _artifact_identity
    from .._util import output_dir as _output_dir
    from .._util import sanitize_label as _sanitize_label
    from .._util import scan_fingerprint as _scan_fingerprint
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan

    out_dir = Path(out_dir)
    # Stage 2 (S11 / contract K9): the site writer always runs, so this mkdir is
    # legitimate -- but it now goes through the same choke point as the
    # single-scan path so "no output" has exactly one implementation. A separate
    # local name keeps the parameter's declared ``str | Path`` type intact.
    created = _output_dir(out_dir, enabled=True)
    assert created is not None  # enabled=True always creates
    out_dir_path: Path = created

    per_scan_config = AnalysisConfig(
        threshold=threshold,
        min_size=min_size,
        zigzag=zigzag,
        background_method=background_method,
        scales=scales,
        connectivity=connectivity,
        soil_mode=soil_mode,
        extraction_rescue=extraction_rescue,
        field_quality_mode=field_quality_mode,
        shadow_measurement=shadow_measurement,
    )
    observations = []
    for label, scan in scans:
        scan.metadata.extra.setdefault("site_scan_label", label)
        # Stage 2 (S10): the scan directory is named from the artifact identity,
        # not from the sanitized label alone. Two distinct labels that sanitize
        # alike ("Pass 1" / "pass_1", "a/b" / "a_b") used to write into the same
        # directory and silently overwrite each other. The stem keeps a
        # human-readable sanitized prefix and appends a content digest, so the
        # directory is still recognisable and is now distinct per scan.
        # Order-independence follows: the stem is a function of content, not of
        # enumeration order.
        identity = _artifact_identity(label, fingerprint=_scan_fingerprint(scan))
        safe_label = _sanitize_label(identity.display_label)
        grid, anomaly, candidates = analyze_scan(
            scan,
            out_dir_path / "scans" / identity.filesystem_stem,
            label=safe_label,
            config=per_scan_config,
        )
        observations.append(
            ScanObservation(label, scan, grid, anomaly, detect_artifacts(grid, anomaly), candidates)
        )
    blocked_labels = [o.label for o in observations if o.field_quality_blocked]
    fusion_observations = [o for o in observations if not o.field_quality_blocked]
    warnings: list[str] = []
    if blocked_labels:
        warnings.append(
            "Field-quality enforcement excluded "
            + ", ".join(blocked_labels)
            + " from cross-scan fusion because the critical data-quality gate failed."
        )
    # v0.4.2 (audit F-02): identical duplicate exports of one acquisition must
    # not be counted as independent cross-scan confirmation. Each duplicate
    # group keeps only its first member for fusion; the warning makes the
    # exclusion explicit in every report.
    duplicate_groups = [g for g in _duplicate_scan_groups(fusion_observations) if len(g) > 1]
    duplicate_labels = {label for group in duplicate_groups for label in group[1:]}
    if duplicate_labels:
        for group in duplicate_groups:
            warnings.append(
                "Scans " + ", ".join(group) + " have identical measurement content "
                "(duplicate acquisition). Only '" + group[0] + "' contributes to "
                "cross-scan fusion evidence; duplicate scans are not independent confirmation."
            )
        fusion_observations = [o for o in fusion_observations if o.label not in duplicate_labels]
    if len(fusion_observations) < 2:
        reference = fusion_observations[0] if fusion_observations else observations[0]
        registration = SiteRegistration(reference.label, {}, 0.0, "insufficient", list(warnings))
        result = MultiScanResult(
            observations, [], reference.label, registration, None, None, None, None, None, warnings
        )
        _write_site_outputs(result, out_dir_path)
        return result

    reference = next(
        (o for o in fusion_observations if o.label == reference_label), fusion_observations[0]
    )
    alignments = {}
    quality = []
    for obs in observations:
        if obs is reference:
            continue
        al = align_grids(
            reference.anomaly.zscore,
            obs.anomaly.zscore,
            resolution=resolution,
            orientation_a_deg=reference.orientation_deg,
            orientation_b_deg=obs.orientation_deg,
        )
        alignments[obs.label] = al
        quality.append(al.registration_evidence)
    reg_consistency = float(np.mean(quality)) if quality else 1.0
    for label, alignment in alignments.items():
        if alignment.status == "weak":
            warnings.append(
                f"Weak registration for {label}: {alignment.registration_evidence:.0%} evidence, {alignment.overlap_fraction:.0%} overlap. Fusion may be unreliable."
            )
        elif alignment.status == "caution":
            warnings.append(
                f"Registration caution for {label}: {alignment.registration_evidence:.0%} evidence, {alignment.overlap_fraction:.0%} overlap."
            )
    if scans and any(not is_metric_coordinates(scan) for _, scan in scans):
        warnings.append(
            "At least one scan's metric geometry is not independently verified "
            "(index-only or derived coordinates). Cross-scan signal/pattern fusion "
            "remains available, but metric geometry is not verified."
        )
    reg_status = (
        "weak"
        if any(al.status == "weak" for al in alignments.values())
        else ("caution" if any(al.status == "caution" for al in alignments.values()) else "strong")
    )
    registration = SiteRegistration(
        reference.label, alignments, reg_consistency, reg_status, warnings
    )
    support, signed, persist, positive, negative, sign_consistency = _consensus_maps(
        fusion_observations,
        alignments,
        reference,
        resolution,
        threshold,
        return_sign_consistency=True,
    )
    fused = fuse_site_candidates(
        fusion_observations, reference, alignments, distance_threshold, support, persist
    )
    fused, _separation_counts = separate_fused_candidates(
        fused,
        support,
        signed,
        reference.grid.x_centers,
        reference.grid.y_centers,
        positive_channel=positive,
        negative_channel=negative,
        persistence_map=persist,
        anomaly_threshold=float(threshold),
    )
    fused = [assess_candidate_quality(c) for c in fused]
    # v0.4.2 (audit F-03): contradicting single-scan fragments would vanish
    # in the repeatability gate below. Reunite them into conflict records
    # first, so disagreement is preserved as disagreement.
    dropped_singles = [c for c in fused if int(getattr(c, "scan_count", 1)) < 2]
    fused = _retain_repeatable_fused_candidates(fused)
    conflicts = build_conflict_candidates(
        dropped_singles,
        ConflictBuildContext(
            observations=fusion_observations,
            alignments=alignments,
            reference=reference,
            resolution=resolution,
            support=support,
            sign_consistency=sign_consistency,
            multires_persistence=persist,
            min_size=int(min_size),
            distance_threshold=distance_threshold,
        ),
    )
    for idx, candidate in enumerate(conflicts, len(fused) + 1):
        candidate.id = idx
    fused = list(fused) + conflicts
    from ..diagnostics.dipole import (
        deblend_spatially_separated_multitarget_pairs,
        merge_dipolar_response_components,
    )

    fused = deblend_spatially_separated_multitarget_pairs(fused)
    fused = resolve_dipole_pairs(fused)
    fused = merge_dipolar_response_components(fused)
    fused = [apply_local_geology_context(c) for c in fused]
    # The fusion constructor creates fresh candidates, so their final pattern
    # classification must run after fused morphology/depth/geometry are known.
    # Merged dipoles remain a response-morphology result and are intentionally
    # not reclassified into a material-oriented hypothesis.
    from ..core.classify import classify_candidate

    fused = [
        c
        if c.pattern_hypothesis == "dipolar-response" or c.response_family == "dipolar-response"
        else classify_candidate(c)
        for c in fused
    ]
    if fusion_pruning == "conservative-repeatability":
        fused = _prune_repeatability_fused_candidates(fused)
    elif fusion_pruning != "off":
        raise ValueError("fusion_pruning must be one of: off, conservative-repeatability")
    # v0.4.2 (audit F-03): contradicting evidence must not surface as a
    # specific pattern conclusion. Force the residual unknown hypothesis with
    # capped confidence on conflict records and polarity-split fused
    # candidates (merged dipoles exempt: reunited lobes are one response).
    fused = apply_conflict_verdict(fused)
    if any(bool(getattr(c, "polarity_conflict", False)) for c in fused):
        warnings.append(
            "Polarity conflict across scans: opposite-sign strong responses at the same "
            "site response. Specific-pattern conclusions are withheld for the conflicted "
            "response (see the polarity-conflict candidate); re-acquire before interpreting."
        )
    fused = [gated_copy(c) for c in fused]
    result = MultiScanResult(
        observations,
        fused,
        reference.label,
        registration,
        support,
        signed,
        persist,
        positive,
        negative,
        warnings,
    )
    _write_site_outputs(result, out_dir_path)
    return result


def _write_site_outputs(result: MultiScanResult, out_dir: Path) -> None:
    """Write the frozen machine contracts for one site run (golden-pinned)."""
    rows = [asdict(c) for c in result.fused_candidates]
    payload = {
        "reference_label": result.reference_label,
        "scan_count": result.scan_count,
        "quality": quality_summary(result.fused_candidates),
        "registration_status": (result.registration.status if result.registration else "unknown"),
        "warnings": list(result.warnings or []),
        "registration": {
            k: {
                "label": v.label,
                "correlation": v.correlation,
                "multiscale_correlation": v.multiscale_correlation,
                "overlap_fraction": v.overlap_fraction,
                "ambiguity_margin": v.ambiguity_margin,
                "registration_evidence": v.registration_evidence,
                "status": v.status,
                "status_reason": v.status_reason,
            }
            for k, v in (result.registration.alignments.items() if result.registration else [])
        },
        "candidates": rows,
    }
    (out_dir / "site_fused_candidates.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    if result.consensus_support is not None:
        # Invariant: consensus maps are built (or skipped) as a group —
        # _consensus_maps never returns a partial set, and both
        # MultiScanResult construction sites pass all five together.
        # The asserts below only narrow types for checking; today a partial
        # set would already fail inside savez with a cryptic error.
        support, signed = result.consensus_support, result.consensus_signed
        positive, negative = result.consensus_positive, result.consensus_negative
        persist = result.consensus_persistence
        assert signed is not None and positive is not None
        assert negative is not None and persist is not None
        np.savez_compressed(
            out_dir / "site_fusion_maps.npz",
            consensus_support=support,
            consensus_signed=signed,
            consensus_positive=positive,
            consensus_negative=negative,
            multiresolution_persistence=persist,
        )

    write_candidates_csv(result.fused_candidates, out_dir / "site_fused_candidates.csv")

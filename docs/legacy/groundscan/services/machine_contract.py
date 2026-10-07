"""Frozen machine-contract writers (CSV + analysis JSON).

Both writers are pinned by the golden validation gate and must stay
byte-stable: ``write_candidates_csv`` (legacy wide table) and
``write_analysis_json``. They emit the engine's structured result only --
no presentation, no rendering, no viewer payload.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..gates.quality import quality_summary
from ..models import Candidate, ScanMetadata


def write_candidates_csv(candidates: list[Candidate], out_path: str | Path) -> None:
    fields = [
        "id",
        "x_center",
        "y_center",
        "depth_mean",
        "depth_std",
        "n_points",
        "area_cells",
        "width",
        "height",
        "aspect_ratio",
        "orientation_deg",
        "peak_signal",
        "mean_signal",
        "anomaly_score",
        "signed_anomaly_mean",
        "positive_peak",
        "negative_peak",
        "polarity",
        "anomaly_density",
        "compactness",
        "continuity_score",
        "artifact_score",
        "multiscale_persistence",
        "scale_class",
        "broadness_score",
        "shape_class",
        "pattern_hypothesis",
        "confidence",
        "evidence_score",
        "cross_scan_agreement",
        "scan_count",
        "detection_rate",
        "directional_persistence",
        "spacing_persistence",
        "traversal_persistence",
        "polarity_consistency",
        "position_stability",
        "contributing_scans",
        "multi_scan_status",
        "quality_score",
        "false_positive_risk",
        "screening_score",
        "review_status",
        "quality_flags",
        "operational_status",
        "operational_flags",
        "operational_constraints",
        "screening_rescue_applied",
        "screening_selection_reason",
        "screening_policy_version",
        "multi_scan_evidence_score",
        "evidence_uncertainty",
        "depth_uncertainty",
        "geometry_uncertainty",
        "signal_uncertainty",
        "position_uncertainty",
        "registration_uncertainty",
        "leave_one_out_stability",
        "effective_scan_count",
        "uncertainty_flags",
        "evidence_components",
        "major_extent",
        "minor_extent",
        "elongation_ratio",
        "linearity_score",
        "solidity",
        "width_consistency_score",
        "orientation_stability_score",
        "morphology_line_coherence_score",
        "morphology_axial_coverage_score",
        "boundary_contact_ratio",
        "geometry_quality",
        "metric_geometry_reliable",
        "geometry_reliability_reason",
        "dielectric_constant",
        "relative_permeability",
        "mineralization_pct",
        "humidity_pct",
        "homogeneity_pct",
        "soil_context_completeness",
        "mineralization_risk",
        "orientation_dispersion_deg",
        "orientation_consistency",
        "geometry_size_consistency",
        "geometry_fusion_quality",
        "geometry_measurement_count",
        "hypothesis_scores",
        "selected_hypothesis_margin",
        "second_hypothesis",
        "classification_method",
        "classification_conflict_score",
        "classification_conflict_reason",
        "classification_alternatives",
        "unresolved_overlap_score",
        "unresolved_overlap_distance_px",
        "unresolved_overlap_reason",
        "undersegmentation_score",
        "undersegmentation_peak_count",
        "undersegmentation_peak_ratio",
        "undersegmentation_distance_px",
        "undersegmentation_depth_delta_m",
        "undersegmentation_depth_layer_supported",
        "undersegmentation_channel",
        "undersegmentation_reason",
        "depth_estimate",
        "depth_estimate_std",
        "depth_min",
        "depth_max",
        "depth_range",
        "depth_valid_fraction",
        "depth_stability_score",
        "depth_relative_dispersion",
        "soil_twt_depth_estimate",
        "soil_twt_depth_std",
        "soil_twt_depth_min",
        "soil_twt_depth_max",
        "soil_twt_depth_valid_fraction",
        "soil_depth_delta_m",
        "soil_depth_channel_status",
        "fused_depth_iqr",
        "fused_depth_consistency",
        "fused_depth_quality",
        "depth_measurement_count",
        "depth_cross_scan_consistency",
        "geometry_consistency",
        "multiscan_signal_consistency",
        "multiresolution_consensus",
        "registration_consistency",
        "response_family",
        "response_component_ids",
        "separation_status",
        "separation_parent_id",
        "separation_fragment_count",
        "separation_quality",
        "notes",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for candidate in candidates:
            row = {k: getattr(candidate, k) for k in fields}
            for key in (
                "contributing_scans",
                "quality_flags",
                "operational_flags",
                "uncertainty_flags",
                "response_component_ids",
            ):
                if isinstance(row.get(key), list):
                    row[key] = ";".join(str(x) for x in row[key])
            if isinstance(row.get("operational_constraints"), list):
                row["operational_constraints"] = " | ".join(row["operational_constraints"])
            for key in ("evidence_components", "hypothesis_scores", "classification_alternatives"):
                if isinstance(row.get(key), dict):
                    row[key] = json.dumps(row[key], sort_keys=True)
            writer.writerow(row)


def write_analysis_json(
    candidates: list[Candidate],
    metadata: ScanMetadata,
    out_path: str | Path,
    geometry: str,
    anomaly_threshold: float,
    scales: tuple[int, ...],
    zigzag: Any | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    def serialize(value: Any) -> dict[str, Any]:
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        raise TypeError(f"Cannot serialize {type(value)!r}")

    payload = {
        "metadata": asdict(metadata),
        "geometry": geometry,
        "analysis": {
            "anomaly_threshold": anomaly_threshold,
            "background_scales": list(scales),
            "score_semantics": "bounded heuristic pattern evidence; not probability",
            "quality_semantics": "quality_score, screening_score and false_positive_risk are heuristic screening metrics; false_positive_risk is not a probability",
            "geometry_depth_semantics": "v0.2.6 depth/geometry fusion uses robust multi-scan aggregation; fused measurements remain estimates in the input coordinate/depth model and are not physical inversion results",
        },
        "zigzag": serialize(zigzag) if zigzag is not None else None,
        "data_quality": diagnostics or {},
        "quality_summary": quality_summary(candidates),
        "candidates": [asdict(c) for c in candidates],
    }
    Path(out_path).write_text(json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8")


__all__ = ["write_candidates_csv", "write_analysis_json"]

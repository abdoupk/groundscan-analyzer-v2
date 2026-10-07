"""Stage helpers for the single-scan pipeline (split from single_scan.py).

Moved verbatim from :func:`single_scan.analyze_scan`, which keeps the
orchestration order. The largest win is ``apply_candidate_enrichment``:
the soil/geometry enrichment loop it holds was copy-pasted three times
in the orchestrator. Behavior is identical; goldens pin the outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..core.anomaly import AnomalyMap
from ..core.classify import ClassificationConfig, classify_candidate
from ..core.grid import Grid2D
from ..core.rescue import ExtractionRescuePolicy, propose_conservative_geology_rescues
from ..core.zigzag import (
    ZigzagDiagnosis,
    correct_zigzag,
    diagnose_zigzag,
    has_independent_positioning,
)
from ..diagnostics.dipole import merge_dipolar_response_components
from ..models import (
    Candidate,
    ScanData,
    is_derived_coordinates,
    is_index_only_coordinates,
    is_metric_coordinates,
)
from ..site import diagnose_undersegmentation, resolve_dipole_pairs, separate_fused_candidates
from ..site.separation import SeparationConfig
from ..soil import (
    attach_soil_model_diagnostics,
    compare_depth_channels,
    integrated_soil_model,
    mineralization_risk_from_pct,
    soil_background_factor_sweep,
    soil_confounder_context,
    soil_context,
    soil_depth_diagnostic,
    soil_twt_depth_grid,
)
from .config import AnalysisConfig
from .machine_contract import write_analysis_json, write_candidates_csv


@dataclass(frozen=True)
class CandidateEnrichment:
    """Soil/geometry context stamped onto candidates (diagnostic-only)."""

    soil_factors: dict[str, Any]
    soil_completeness: float
    mineralization_pct: float | None
    metric_geometry_reliable: bool
    geometry_reason: str


def build_enrichment(scan: ScanData) -> CandidateEnrichment:
    """Read enrichment context from the scan (pure; no mutation)."""
    metric_geometry_reliable = is_metric_coordinates(scan)
    geometry_reason = {
        "measured": "physical/metric coordinates available",
        "derived": (
            "coordinates derived from self-reported field dimensions or unlabeled columns; "
            "metric geometry is not independently verified"
        ),
        "index": "x/y are raw grid indices; metric distances/areas are not verified",
    }[getattr(scan, "effective_coordinate_provenance", "measured")]
    mineralization_pct = scan.metadata.mineralization_pct
    soil_context = scan.metadata.extra.get("soil_context", {}) if scan.metadata.extra else {}
    soil_factors = soil_context.get("factors", {}) if isinstance(soil_context, dict) else {}
    soil_completeness = (
        float(soil_context.get("completeness", 0.0)) if isinstance(soil_context, dict) else 0.0
    )
    return CandidateEnrichment(
        soil_factors=soil_factors,
        soil_completeness=soil_completeness,
        mineralization_pct=mineralization_pct,
        metric_geometry_reliable=metric_geometry_reliable,
        geometry_reason=geometry_reason,
    )


def apply_candidate_enrichment(
    candidates: list[Candidate], scan: ScanData, enrichment: CandidateEnrichment
) -> list[Candidate]:
    """Stamp soil/geometry context onto candidates, returning new copies (M4).

    Pure: inputs are never mutated; the enriched list replaces the input
    downstream. Values are identical to the former in-place version.
    """
    out: list[Candidate] = []
    for candidate in candidates:
        mineralization_pct = enrichment.soil_factors.get(
            "mineralization_pct", enrichment.mineralization_pct
        )
        out.append(
            candidate.with_updates(
                metric_geometry_reliable=enrichment.metric_geometry_reliable,
                geometry_reliability_reason=enrichment.geometry_reason,
                dielectric_constant=enrichment.soil_factors.get(
                    "dielectric_constant", scan.metadata.dielectric_constant
                ),
                relative_permeability=enrichment.soil_factors.get(
                    "relative_permeability", scan.metadata.relative_permeability
                ),
                mineralization_pct=mineralization_pct,
                humidity_pct=enrichment.soil_factors.get(
                    "humidity_pct", scan.metadata.humidity_pct
                ),
                homogeneity_pct=enrichment.soil_factors.get(
                    "homogeneity_pct", scan.metadata.homogeneity_pct
                ),
                soil_context_completeness=enrichment.soil_completeness,
                mineralization_risk=mineralization_risk_from_pct(mineralization_pct),
            )
        )
    return out


def separate_single_scan_candidates(
    candidates: list[Candidate],
    *,
    config: AnalysisConfig,
    anomaly: AnomalyMap,
    artifacts: Any,
    grid: Grid2D,
    separation_config: SeparationConfig | None,
    classification_config: ClassificationConfig | None,
    enrichment: CandidateEnrichment,
    scan: ScanData,
) -> list[Candidate]:
    """Decompose fused same-sign peaks + resolve dipoles (single scan).

    v0.2.8: conservatively decompose locally fused same-sign peaks even in a
    single scan. This is a response-separation hypothesis, not proof of objects.
    """
    if not candidates:
        return candidates
    threshold = config.threshold
    peak = float(max(np.nanmax(np.abs(anomaly.zscore)), 1e-9))
    support = np.clip(np.nan_to_num(np.abs(anomaly.zscore), nan=0.0) / peak, 0.0, 1.0)
    signed = np.nan_to_num(anomaly.zscore, nan=0.0)
    pos = np.clip(signed, 0.0, None)
    neg = np.clip(-signed, 0.0, None)
    # Fragment cells are recorded so the dipole merge below can describe the union
    # of a pair rather than averaging its lobes. They are a side channel: the
    # fragment's own metrics were already computed from these cells upstream.
    fragment_cells: dict[int, tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]] = {}
    candidates, _ = separate_fused_candidates(
        candidates,
        support,
        signed,
        grid.x_centers,
        grid.y_centers,
        positive_channel=pos,
        negative_channel=neg,
        min_distance_px=3,
        support_threshold=0.28,
        max_seeds_per_parent=4,
        allow_single_scan=True,
        config=separation_config,
        depth_grid=np.asarray(grid.depth),
        persistence_map=np.asarray(anomaly.persistence),
        artifact_map=np.asarray(artifacts.score),
        signal_grid=np.asarray(grid.signal),
        anomaly_threshold=float(threshold),
        fragment_cells=fragment_cells,
    )
    candidates = apply_candidate_enrichment(candidates, scan, enrichment)
    candidates = [classify_candidate(c, config=classification_config) for c in candidates]
    # Dipole fix (train-data driven): re-classification is per-candidate and
    # cannot see that opposite-polarity fragments share one fused parent.
    # Resolve bipolar pairs so a metal dipole is not reported as
    # "metal + independent cavity".
    candidates = resolve_dipole_pairs(candidates)
    candidates = merge_dipolar_response_components(
        candidates,
        fragment_cells=fragment_cells,
        field_shape=(
            int(np.asarray(anomaly.labels).shape[0]),
            int(np.asarray(anomaly.labels).shape[1]),
        ),
    )
    # v0.2.46: final-pass diagnostic for same-sign multi-peak structure that
    # survived production decomposition. Diagnostic-only; no candidate changes.
    candidates = diagnose_undersegmentation(
        candidates,
        support,
        signed,
        grid.x_centers,
        grid.y_centers,
        depth_grid=np.asarray(grid.depth),
        min_distance_px=3,
    )
    for candidate in candidates:
        candidate.response_component_ids = candidate.response_component_ids or [candidate.id]
    return candidates


def run_extraction_rescue(
    candidates: list[Candidate],
    *,
    config: AnalysisConfig,
    grid: Grid2D,
    anomaly: AnomalyMap,
    scan: ScanData,
    field_quality_blocked: bool,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Optional conservative secondary extraction channel (off by default).

    It never edits the baseline anomaly map; accepted candidates are appended
    only when a clean broad geological response is missing from the baseline.
    Returns the (possibly extended) candidates plus the rescue diagnostic.
    """
    extraction_rescue = str(config.extraction_rescue or "off").lower()
    threshold = config.threshold
    min_size = config.min_size
    scales = config.scales
    rescue_diag: dict[str, Any] = {
        "mode": str(extraction_rescue).lower(),
        "candidate_extraction_blocked": field_quality_blocked,
        "accepted_count": 0,
    }
    if not field_quality_blocked:
        rescue_policy = ExtractionRescuePolicy(
            mode=str(extraction_rescue).lower(),
            threshold=threshold,
            min_size=min_size,
            scales=scales,
        )
        rescue_candidates, rescue_diag = propose_conservative_geology_rescues(
            grid,
            candidates,
            threshold=threshold,
            min_size=min_size,
            scales=scales,
            # v0.4.2 (audit F-05): the rescue channel places candidates using
            # coordinate-space radii; it stays off unless metric geometry is
            # measured-verified (derived coordinates included in the ban).
            coords_are_index_only=not is_metric_coordinates(scan),
            policy=rescue_policy,
        )
        if rescue_candidates:
            candidates.extend(rescue_candidates)
    return candidates, rescue_diag


def write_single_scan_outputs(
    candidates: list[Candidate],
    *,
    scan: ScanData,
    out_dir: str | Path,
    label: str,
    threshold: float,
    scales: tuple[int, ...],
    zigzag_diag: Any,
    scan_diagnostics: dict[str, Any],
    geometry: Any,
) -> None:
    """Write the frozen machine contracts for one scan (golden-pinned)."""
    from .._util import contained_path, sanitize_label

    out_dir = Path(out_dir)
    label = sanitize_label(label)
    write_candidates_csv(candidates, contained_path(out_dir, f"{label}_candidates.csv"))
    write_analysis_json(
        candidates=candidates,
        metadata=scan.metadata,
        out_path=contained_path(out_dir, f"{label}_analysis.json"),
        geometry=geometry.describe(),
        anomaly_threshold=threshold,
        scales=scales,
        zigzag=zigzag_diag,
        diagnostics=scan_diagnostics,
    )


def apply_zigzag_policy(
    scan: ScanData, grid: Grid2D, *, zigzag: str
) -> tuple[Grid2D, ZigzagDiagnosis]:
    """Diagnose, decide, record, and conditionally apply zigzag correction (M5).

    Moved verbatim from :func:`single_scan.analyze_scan`: the GPS-anchored
    never-mirror rule (F-09), the explicit-force override, and the
    machine-readable ``zigzag_correction`` record keep identical semantics;
    only the location changed (orchestrator → named stage).
    """
    zigzag_diag = diagnose_zigzag(grid, reported_scan_mode=scan.metadata.extra.get("scan_mode"))
    # v0.4.2 (audit F-09): never auto-mirror independently positioned (GPS)
    # samples -- each sample already sits where it was taken. Explicit
    # "force" still overrides; the decision is recorded machine-readably
    # below and in the human report note.
    gps_anchored = has_independent_positioning(scan.latitude, scan.longitude)
    zigzag_applied = zigzag == "force" or (
        zigzag == "auto" and zigzag_diag.recommend_correction and not gps_anchored
    )
    zigzag_skipped_for_gps = bool(
        zigzag == "auto" and zigzag_diag.recommend_correction and gps_anchored
    )
    scan.metadata.extra["zigzag_correction"] = {
        "mode": zigzag,
        "recommended": bool(zigzag_diag.recommend_correction),
        "margin": zigzag_diag.margin,
        "applied": bool(zigzag_applied),
        "skipped_for_independent_positioning": zigzag_skipped_for_gps,
    }
    if zigzag_applied:
        grid = correct_zigzag(grid)
    return grid, zigzag_diag


def assemble_soil_model(
    *,
    scan: ScanData,
    grid: Grid2D,
    baseline_z: np.ndarray[Any, Any],
    soil_aware_z: np.ndarray[Any, Any] | None,
    soil_weights: np.ndarray[Any, Any] | None,
    threshold: float,
    soil_mode: str,
    scales: tuple[int, ...],
) -> tuple[dict[str, Any], Grid2D | None]:
    """Assemble the diagnostic soil-model payload + TWT grid (stage helper).

    Moved verbatim from :func:`single_scan.analyze_scan` (M2 stage-boundary
    migration): identical calls in identical order, so the payload stored
    in ``scan.metadata.extra["soil_model"]`` is unchanged. Soil channels
    stay diagnostic/provenance-only — this helper never alters detection,
    scoring, or geometry.
    """
    soil_model_result = attach_soil_model_diagnostics(
        scan.metadata,
        baseline_z=baseline_z,
        soil_z=soil_aware_z,
        soil_weights=soil_weights,
        threshold=threshold,
        soil_mode=soil_mode,
    )
    soil_model_result["soil_context"] = soil_context(scan.metadata)
    soil_model_result["confounder_context"] = soil_confounder_context(scan.metadata)
    soil_model_result["depth_diagnostic"] = soil_depth_diagnostic(scan, scan.metadata)
    soil_twt_grid = soil_twt_depth_grid(scan, scan.metadata)
    soil_model_result["depth_comparison"] = (
        compare_depth_channels(grid, soil_twt_grid)
        if soil_twt_grid is not None
        else {"available": False, "reason": "No usable explicit TWT-derived depth channel."}
    )
    soil_model_result["background_factor_sweep"] = soil_background_factor_sweep(
        grid, scan.metadata, scales=scales, threshold=threshold
    )
    soil_model_result["integrated"] = integrated_soil_model(
        scan.metadata,
        soil_model=soil_model_result,
        depth_channel=soil_model_result.get("depth_diagnostic", {}),
        background_sweep=soil_model_result.get("background_factor_sweep", {}),
    )
    return soil_model_result, soil_twt_grid


def write_provenance_note(out_dir: str | Path, label: str, scan: ScanData) -> None:
    """Write the index/derived coordinate caveat file when applicable."""
    from .._util import contained_path, sanitize_label

    out_dir = Path(out_dir)
    label = sanitize_label(label)
    if is_index_only_coordinates(scan):
        note_path = contained_path(out_dir, f"{label}_IMPORTANT_index_only_coordinates.txt")
        note_path.write_text(
            "This scan's x/y are raw grid indices, not verified meters. Distances and areas "
            "are therefore reported in grid-coordinate units. Provide real field dimensions "
            "or known line/point spacing before treating geometry as metric.",
            encoding="utf-8",
        )
    elif is_derived_coordinates(scan):
        note_path = contained_path(out_dir, f"{label}_IMPORTANT_derived_coordinates.txt")
        note_path.write_text(
            "This scan's metric coordinates were derived from self-reported field dimensions "
            "(the metric columns themselves were not usable), or from unlabeled columns. They "
            "are not independently verified measurements: distances and areas are only as "
            "accurate as the reported field dimensions. Confirm with known line/point spacing "
            "before treating geometry as metric.",
            encoding="utf-8",
        )


__all__ = [
    "CandidateEnrichment",
    "apply_candidate_enrichment",
    "apply_zigzag_policy",
    "assemble_soil_model",
    "build_enrichment",
    "run_extraction_rescue",
    "separate_single_scan_candidates",
    "write_provenance_note",
    "write_single_scan_outputs",
]

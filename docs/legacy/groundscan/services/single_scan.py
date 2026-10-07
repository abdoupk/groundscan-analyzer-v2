"""High-level device-agnostic analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from .._util import axis_spacing as _axis_spacing
from .._util import output_dir
from ..core import (
    classify_candidate,
    detect_anomalies,
    detect_artifacts,
    extract_candidates,
    reconstruct_grid,
)
from ..core.anomaly import AnomalyMap
from ..core.classify import ClassificationConfig
from ..core.grid import Grid2D
from ..diagnostics.quality_probe import detect_scan_quality_diagnostics
from ..diagnostics.shadow import (
    ShadowMeasurement,
    measure_roles,
    measure_scale,
    measure_solidity,
)
from ..gates.field_quality import assess_field_quality
from ..gates.geometry import summarize_geometry
from ..gates.operational import gated_copy
from ..gates.screening import DEFAULT_SCREENING_POLICY, screening_summary
from ..io import ScannerAdapter, detect_adapter
from ..models import Candidate, ScanData, normalise_coordinate_units
from ..site.separation import SeparationConfig
from ..soil import attach_soil_context, soil_aware_background_zscore
from .config import AnalysisConfig
from .single_scan_stages import (
    apply_candidate_enrichment,
    apply_zigzag_policy,
    assemble_soil_model,
    build_enrichment,
    run_extraction_rescue,
    separate_single_scan_candidates,
    write_provenance_note,
    write_single_scan_outputs,
)


def load_scan(path: str | Path, adapter: ScannerAdapter | None = None) -> ScanData:
    resolved = adapter or detect_adapter(path)
    return resolved.read(path)


def analyze_scan(
    scan: ScanData,
    out_dir: str | Path,
    label: str = "scan",
    config: AnalysisConfig | None = None,
    separation_config: SeparationConfig | None = None,
    classification_config: ClassificationConfig | None = None,
    write_outputs: bool = True,
) -> tuple[Grid2D, AnomalyMap, list[Candidate]]:
    """Run grid reconstruction, quality checks, anomaly analysis and optional output writing.

    Takes the shared :class:`AnalysisConfig` knob object; the two
    ``*_config`` overrides stay direct (rarely-touched objects, not scalar
    policy).

    Mutation contract: ``scan.metadata.extra`` is enriched in place
    (``analysis_diagnostics``, ``field_quality``, ``soil_context_baseline``,
    …). Callers re-analyzing one ScanData object must expect accumulated
    keys; :func:`groundscan.api.analyze` reads ``field_quality`` back from
    the same object. Pass a copy if the input must stay pristine.
    """
    cfg = config or AnalysisConfig()
    threshold = cfg.threshold
    min_size = cfg.min_size
    zigzag = cfg.zigzag
    background_method = cfg.background_method
    scales = cfg.scales
    connectivity = cfg.connectivity
    soil_mode = cfg.soil_mode
    field_quality_mode = str(cfg.field_quality_mode or "enforce-hard-block").lower()
    if field_quality_mode not in {"enforce-hard-block", "report-only"}:
        raise ValueError("field_quality_mode must be one of: enforce-hard-block, report-only")
    out_dir = Path(out_dir)
    # Stage 2 (S11 / contract K9): the ONE place a directory is created for
    # analysis output. Previously the mkdir sat outside the flag, so
    # ``analyze_scan(scan, out_dir, write_outputs=False)`` created the whole
    # output tree and wrote nothing -- "no output" that left a directory behind.
    # Two earlier audit passes missed it because they looked for *files*, and an
    # already-existing out_dir masked the mkdir. With the flag off, nothing is
    # created at all.
    created_out_dir = output_dir(out_dir, enabled=write_outputs)

    # Remediation Design v2 §5.4 (Wave 0): convert declared non-metre
    # coordinates to metres once, here, before the grid is built. A strict no-op
    # for an undeclared unit or "m", so every pre-existing scan is unaffected;
    # the original unit stays on ``scan.coordinate_unit`` for auditability.
    normalise_coordinate_units(scan)

    grid = reconstruct_grid(scan)
    # v0.4.2 (audit F-11): the geometry text must describe the grid the
    # analysis actually runs on, not just the raw export columns.
    geometry = summarize_geometry(scan, grid)
    scan_diagnostics = detect_scan_quality_diagnostics(grid)
    scan.metadata.extra = dict(scan.metadata.extra or {})
    scan.metadata.extra["analysis_diagnostics"] = scan_diagnostics
    field_quality = assess_field_quality(scan, grid, geometry, scan_diagnostics)
    field_quality_blocked = bool(
        field_quality.hard_block and field_quality_mode == "enforce-hard-block"
    )
    scan.metadata.extra["field_quality"] = field_quality.to_dict()
    scan.metadata.extra["field_quality_policy"] = {
        "mode": field_quality_mode,
        "candidate_extraction_blocked": field_quality_blocked,
        "reason": (
            "Critical field-quality gate failure; candidate extraction was blocked."
            if field_quality_blocked
            else "Candidate extraction permitted; field-quality status remains advisory."
        ),
    }
    # Soil channels are diagnostic/provenance-only: attach_soil_context (v1
    # baseline factors) + soil_context_v2/confounder/depth/TWT/background-sweep/
    # integrated below never alter detection, scoring, or geometry. They are
    # recorded in the machine contract's metadata block so a reader can see soil
    # completeness without implying a calibrated correction.
    soil_context = attach_soil_context(scan.metadata)
    scan.metadata.extra["soil_context_baseline"] = {
        "mode": "metadata_only",
        "correction_applied": False,
        "reason": "Soil-aware signal/depth correction is not calibrated yet; current analysis remains the baseline.",
        "completeness": soil_context.get("completeness", 0.0),
    }

    grid, zigzag_diag = apply_zigzag_policy(scan, grid, zigzag=zigzag)

    anomaly = detect_anomalies(
        grid,
        threshold=threshold,
        min_size=min_size,
        background_method=background_method,
        scales=scales,
        connectivity=connectivity,
    )
    # Soil-aware A/B channel: deliberately parallel to the baseline detector.
    # It never replaces anomaly/candidate extraction in this release.
    soil_aware_z = None
    soil_weights = None
    if str(soil_mode).lower() == "experimental" and scan.metadata.homogeneity_pct is not None:
        soil_aware_z, soil_weights, _ = soil_aware_background_zscore(
            grid, scales=scales, homogeneity_pct=scan.metadata.homogeneity_pct
        )
    soil_model_result, soil_twt_grid = assemble_soil_model(
        scan=scan,
        grid=grid,
        baseline_z=anomaly.zscore,
        soil_aware_z=soil_aware_z,
        soil_weights=soil_weights,
        threshold=threshold,
        soil_mode=soil_mode,
        scales=scales,
    )
    scan.metadata.extra["soil_model"] = soil_model_result

    artifacts = detect_artifacts(grid, anomaly)
    if field_quality_blocked:
        candidates: list[Candidate] = []
    else:
        candidates = extract_candidates(
            grid,
            anomaly,
            artifacts,
            auxiliary_depth=(soil_twt_grid.depth if soil_twt_grid is not None else None),
        )
    enrichment = build_enrichment(scan)
    candidates = apply_candidate_enrichment(candidates, scan, enrichment)
    candidates = [classify_candidate(c, config=classification_config) for c in candidates]

    candidates = separate_single_scan_candidates(
        candidates,
        config=cfg,
        anomaly=anomaly,
        artifacts=artifacts,
        grid=grid,
        separation_config=separation_config,
        classification_config=classification_config,
        enrichment=enrichment,
        scan=scan,
    )
    # Gate pass 1/2: baseline + separated/dipole-resolved candidates.
    # A second pass runs after the optional rescue channel below so rescued
    # candidates are gated too; baseline candidates are idempotent under
    # re-gating (gate only sets operational_* fields). Pure copies (M11).
    candidates = [gated_copy(c, field_quality.status) for c in candidates]

    candidates, rescue_diag = run_extraction_rescue(
        candidates,
        config=cfg,
        grid=grid,
        anomaly=anomaly,
        scan=scan,
        field_quality_blocked=field_quality_blocked,
    )
    scan.metadata.extra["extraction_rescue"] = rescue_diag
    # Gate pass 2/2 (see above): covers rescue-appended candidates.
    candidates = [gated_copy(c, field_quality.status) for c in candidates]

    # v0.2.38: expose the post-analysis screening policy in machine-readable
    # metadata without filtering the raw candidate list returned by analyze_scan.
    scan.metadata.extra["screening_policy"] = {
        **screening_summary(candidates, DEFAULT_SCREENING_POLICY),
        "selection_is_applied_to_returned_candidates": False,
    }

    # Remediation Design v2 §11 (Wave 1, shadow measurement). Computes the
    # corrected S01/S02/S03 values beside the shipped ones and records the
    # delta. Opt-in, off by default, and it decides nothing: no gate, score,
    # classification or candidate field reads the result. The ledger rides on
    # `anomaly` (never serialised) and is never promoted to a candidate field,
    # so the golden set and the machine contract cannot be perturbed.
    if str(cfg.shadow_measurement).lower() == "diagnostics":
        shadow = ShadowMeasurement(enabled=True)
        # S03: the scale the z threshold actually applied to.
        shadow.scale = measure_scale(getattr(anomaly, "residual", None))
        # S01: roles over the final findings, plus the within-response
        # separation distribution that `d_res` calibration needs.
        shadow.roles = measure_roles(candidates)
        # S02: exact vs shipped solidity, propagated through the whole chain.
        shadow.solidity = measure_solidity(
            labels=anomaly.labels,
            n_components=anomaly.n_components,
            x_centers=grid.x_centers,
            y_centers=grid.y_centers,
            cell_dx=_axis_spacing(grid.x_centers),
            cell_dy=_axis_spacing(grid.y_centers),
            candidates=candidates,
        )
        anomaly.shadow = shadow

    if created_out_dir is not None:
        write_single_scan_outputs(
            candidates,
            scan=scan,
            out_dir=created_out_dir,
            label=label,
            threshold=threshold,
            scales=scales,
            zigzag_diag=zigzag_diag,
            scan_diagnostics=scan_diagnostics,
            geometry=geometry,
        )
        # Stage 2 (S11): the provenance note used to be written outside the
        # `write_outputs` guard, so a run that asked for no output still wrote
        # one file. It is an output artifact and belongs inside the guard.
        write_provenance_note(created_out_dir, label, scan)

    return grid, anomaly, candidates

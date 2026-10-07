"""Field-operational scan quality gate.

This module does not alter anomaly detection or candidate selection. It evaluates
the input/reconstructed scan for conditions that make field interpretation
unreliable, and exposes a conservative readiness state plus explicit reasons.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ..core.grid import Grid2D
from ..models import ScanData, is_metric_coordinates
from .geometry import GeometrySummary
from .thresholds import FIELD_QUALITY_THRESHOLDS as T


@dataclass(frozen=True)
class FieldQualityAssessment:
    status: str
    score: float
    field_ready: bool
    hard_block: bool
    flags: tuple[str, ...]
    reasons: tuple[str, ...]
    recommendations: tuple[str, ...]
    signal_valid_fraction: float
    grid_coverage: float
    depth_valid_fraction: float
    signal_dynamic_range_score: float
    metric_geometry_available: bool
    rectangular_grid: bool
    instrument_artifact_score: float
    reason_messages: tuple[tuple[str, dict[str, object]], ...] = ()
    recommendation_messages: tuple[tuple[str, dict[str, object]], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _robust_scale(values: np.ndarray[Any, Any]) -> float:
    """Local robust scale WITHOUT the _util floor.

    Intentionally diverges from groundscan._util.robust_scale: dynamic-range
    scoring needs 0.0 on degenerate input (<3 values), while _util returns
    1.0 + 5% std floor for detection. Do not unify without re-baselining
    field-quality scores and goldens.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        return 0.0
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    if mad > 1e-12:
        return 1.4826 * mad
    q1, q3 = np.percentile(values, [25.0, 75.0])
    return float((q3 - q1) / 1.349)


def _grid_coverage(grid: Grid2D) -> float:
    counts = np.asarray(grid.counts, dtype=float)
    if counts.size == 0:
        return 0.0
    return float(np.mean(counts > 0))


def _dynamic_range_score(signal: np.ndarray[Any, Any]) -> float:
    values = np.asarray(signal, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 5:
        return 0.0
    scale = _robust_scale(values)
    median = float(np.median(values))
    magnitude = float(np.percentile(values, 90.0) - np.percentile(values, 10.0))
    if magnitude <= 1e-12 or scale <= 1e-12:
        # A nearly constant channel can still be valid data, but it provides
        # little dynamic information for anomaly interpretation.
        return 0.15
    ratio = scale / max(abs(median), 1e-9)
    # Broadly tolerant scoring; this is a readiness aid, not a device model.
    if ratio < 1e-5:
        return 0.25
    if ratio < 1e-4:
        return 0.55
    return float(np.clip(0.70 + 0.30 * min(magnitude / max(scale, 1e-9) / 20.0, 1.0), 0.0, 1.0))


def assess_field_quality(
    scan: ScanData,
    grid: Grid2D,
    geometry: GeometrySummary,
    scan_diagnostics: dict[str, Any] | None = None,
) -> FieldQualityAssessment:
    """Assess field-operational data quality without changing analysis outputs."""
    signal = np.asarray(grid.signal, dtype=float)
    depth = np.asarray(grid.depth, dtype=float)
    total = max(int(signal.size), 1)
    signal_valid_fraction = float(np.count_nonzero(np.isfinite(signal)) / total)
    depth_valid_fraction = float(np.count_nonzero(np.isfinite(depth)) / total)
    coverage = _grid_coverage(grid)
    min_dim = min(signal.shape) if signal.ndim == 2 and signal.size else 0
    rectangular = (
        bool(geometry.is_clean_rectangle)
        if geometry.n_unique_lines is not None
        else coverage >= 0.95
    )
    # v0.4.2 (audit F-05): metric-geometry honesty follows the scan's declared
    # coordinate provenance, not self-reported field-dimension metadata. The
    # previous AND-test ("field dims present AND not index-only") flagged
    # genuine meter coordinates from generic CSVs as non-metric while accepting
    # rover coordinates that were merely rescaled from those same header dims.
    metric = is_metric_coordinates(scan)
    diagnostics = scan_diagnostics or {}
    artifact_score = float(
        np.clip(diagnostics.get("instrument_artifact_score", 0.0) or 0.0, 0.0, 1.0)
    )
    dynamic = _dynamic_range_score(signal)

    flags: list[str] = []
    reasons: list[str] = []
    recommendations: list[str] = []
    reason_messages: list[tuple[str, dict[str, object]]] = []
    recommendation_messages: list[tuple[str, dict[str, object]]] = []
    hard_block = False

    def add_reason(message_id: str, text: str, **variables: object) -> None:
        reasons.append(text)
        reason_messages.append((message_id, dict(variables)))

    def add_recommendation(message_id: str, text: str, **variables: object) -> None:
        recommendations.append(text)
        recommendation_messages.append((message_id, dict(variables)))

    if signal_valid_fraction < T["signal_valid_hard_block"]:
        hard_block = True
        flags.append("insufficient-valid-signal")
        add_reason(
            "fq_signal_finite_only",
            f"Only {signal_valid_fraction:.0%} of reconstructed cells contain finite signal values.",
            pct=signal_valid_fraction,
        )
        add_recommendation(
            "fq_repeat_complete_grid",
            "Repeat or re-export the scan with a complete measurement grid.",
        )
    elif signal_valid_fraction < T["signal_valid_caution"]:
        flags.append("low-valid-signal")
        add_reason(
            "fq_signal_finite_low",
            f"Only {signal_valid_fraction:.0%} of reconstructed cells contain finite signal values; treat candidates as caution-level pending confirmation.",
            pct=signal_valid_fraction,
        )
        add_recommendation(
            "fq_confirm_low_signal",
            "Confirm any reported candidates with a repeat scan before relying on them; signal coverage is degraded.",
        )
    elif signal_valid_fraction < T["signal_valid_complete"]:
        flags.append("missing-signal-cells")
        add_reason(
            "fq_signal_coverage_incomplete",
            f"Signal coverage is incomplete ({signal_valid_fraction:.0%} finite cells).",
            pct=signal_valid_fraction,
        )
        add_recommendation(
            "fq_check_dropped_measurements",
            "Check for dropped impulses/scan lines before relying on fine-scale localization.",
        )

    if coverage < T["grid_coverage_hard_block"]:
        hard_block = True
        flags.append("severely-incomplete-grid")
        add_reason(
            "fq_grid_coverage_severe",
            f"Only {coverage:.0%} of the reconstructed grid contains measurements.",
            pct=coverage,
        )
        add_recommendation(
            "fq_repeat_continuous_coverage",
            "Repeat the scan with continuous coverage and without unexplained gaps.",
        )
    elif coverage < T["grid_coverage_caution"]:
        flags.append("incomplete-grid")
        add_reason(
            "fq_grid_coverage_partial",
            f"Grid coverage is {coverage:.0%}, so some spatial areas are unsampled.",
            pct=coverage,
        )
        add_recommendation(
            "fq_inspect_scan_path",
            "Inspect the scan path and consider repeating the survey to close gaps.",
        )

    if min_dim < T["grid_min_dimension_hard_block"]:
        hard_block = True
        flags.append("too-small-grid")
        rows = int(signal.shape[0]) if signal.ndim == 2 else 0
        cols = int(signal.shape[1]) if signal.ndim == 2 else 0
        add_reason(
            "fq_grid_size",
            f"The reconstructed grid is only {cols}x{rows} cells.",
            rows=rows,
            cols=cols,
        )
        add_recommendation(
            "fq_larger_grid", "Use a larger survey grid before interpreting spatial morphology."
        )

    if geometry.n_unique_lines is not None and not rectangular:
        flags.append("irregular-grid-geometry")
        add_reason(
            "fq_irregular_grid", "The export does not form a clean rectangular impulse/line grid."
        )
        add_recommendation(
            "fq_verify_scan_continuity",
            "Verify whether the scan was interrupted, resumed, or concatenated from multiple sessions.",
        )

    if not metric:
        flags.append("non-metric-geometry")
        add_reason("fq_non_metric", "Physical x/y spacing is not verified as metric in the input.")
        add_recommendation(
            "fq_provide_metric_spacing",
            "Provide field dimensions or known line/point spacing before using distances/areas as measurements.",
        )

    # v0.4.2 (audit F-12): headerless x/y/third-column files are ambiguous. The
    # third numeric column is mapped to the signal channel by pinned adapter
    # semantics, but it may actually be a depth channel (x,y,z), in which case
    # the analysis would run on depth values as signal. The mapping itself is
    # kept; the guess must never be silent.
    if bool((scan.metadata.extra or {}).get("headerless_xyz")):
        flags.append("headerless-source-ambiguity")
        add_reason(
            "fq_headerless_source",
            "The file has no header row: the first three numeric columns were mapped to x, y and the signal channel. If the third column is a depth channel, the analysis is running on depth values as signal.",
        )
        add_recommendation(
            "fq_headerless_reexport",
            "Re-export the file with column headers (x, y, signal, depth) so every channel is unambiguous.",
        )

    if depth_valid_fraction < T["depth_valid_caution"]:
        flags.append("weak-depth-channel")
        add_reason(
            "fq_depth_coverage_low",
            f"Only {depth_valid_fraction:.0%} of reconstructed cells have a finite depth value.",
            pct=depth_valid_fraction,
        )
        add_recommendation(
            "fq_confirm_depth_repeat",
            "Treat depth estimates as especially uncertain and confirm with repeat scans when possible.",
        )
    elif depth_valid_fraction < T["depth_valid_partial"]:
        flags.append("partial-depth-channel")
        add_reason(
            "fq_depth_coverage_partial",
            f"Depth coverage is {depth_valid_fraction:.0%} of reconstructed cells.",
            pct=depth_valid_fraction,
        )

    if dynamic < T["dynamic_range_caution"]:
        flags.append("low-signal-dynamic-range")
        add_reason(
            "fq_dynamic_range_low",
            "The signal channel has very low robust dynamic range for spatial anomaly interpretation.",
        )
        add_recommendation(
            "fq_repeat_if_constant",
            "Check acquisition settings and repeat the scan if the signal is nearly constant.",
        )

    if artifact_score >= T["artifact_strong"]:
        flags.append("strong-instrument-artifact-concern")
        add_reason(
            "fq_artifact_strong",
            "The existing acquisition diagnostic found a strong isolated instrument/boundary artifact signature.",
        )
        add_recommendation(
            "fq_move_artifact_boundary",
            "Repeat the scan with the affected boundary/corner moved away from the suspected artifact before relying on that region.",
        )
    elif artifact_score >= T["artifact_caution"]:
        flags.append("instrument-artifact-concern")
        add_reason(
            "fq_artifact_non_negligible",
            "The scan contains a non-negligible acquisition artifact signature.",
        )

    # Conservative scalar readiness score. This summarizes evidence already
    # measured by the gate; it is not accuracy or confidence.
    score = (
        0.25 * signal_valid_fraction
        + 0.20 * coverage
        + 0.15 * depth_valid_fraction
        + 0.15 * dynamic
        + 0.10 * (1.0 if rectangular else 0.55)
        + 0.10 * (1.0 if metric else 0.50)
        + 0.05 * (1.0 - artifact_score)
    )
    score = float(np.clip(score, 0.0, 1.0))

    caution_only = any(
        f in flags
        for f in (
            "low-valid-signal",
            "missing-signal-cells",
            "incomplete-grid",
            "irregular-grid-geometry",
            "non-metric-geometry",
            "weak-depth-channel",
            "partial-depth-channel",
            "low-signal-dynamic-range",
            "instrument-artifact-concern",
            # Audit fix: the strong tier was raised as a flag but omitted here,
            # so a scan the probe flagged as artifact-prone still reported
            # field-ready -- its readiness-score contribution is only 0.005 and
            # never reaches the caution band on its own. Artifact severity must
            # degrade readiness in proportion to the severity, so the strong tier
            # counts too (it still never hard-blocks, matching the threshold
            # table's "artifact_strong" scoring intent).
            "strong-instrument-artifact-concern",
            "headerless-source-ambiguity",
        )
    )
    if hard_block or score < T["ready_score_insufficient"]:
        status = "insufficient-quality"
        field_ready = False
    elif caution_only or score < T["ready_score_ready"]:
        status = "usable-with-caution"
        field_ready = False
    else:
        status = "field-ready"
        field_ready = True

    if not flags:
        flags.append("no-critical-quality-flags")
        add_reason(
            "fq_no_critical_problem",
            "No critical scan-quality problem was detected by the conservative gate.",
        )

    return FieldQualityAssessment(
        status=status,
        score=round(score, 3),
        field_ready=field_ready,
        hard_block=hard_block,
        flags=tuple(flags),
        reasons=tuple(reasons),
        recommendations=tuple(dict.fromkeys(recommendations)),
        signal_valid_fraction=round(signal_valid_fraction, 4),
        grid_coverage=round(coverage, 4),
        depth_valid_fraction=round(depth_valid_fraction, 4),
        signal_dynamic_range_score=round(dynamic, 4),
        metric_geometry_available=metric,
        rectangular_grid=rectangular,
        instrument_artifact_score=round(artifact_score, 4),
        reason_messages=tuple(reason_messages),
        recommendation_messages=tuple(recommendation_messages),
    )

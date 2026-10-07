"""Stable public API for GroundScan Analyzer.

Small typed surface for applications. There is no ``compare`` entry point:
two-scan work goes through :func:`analyze_site`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import Candidate, ScanData
from .services.config import AnalysisConfig
from .services.single_scan import analyze_scan as _analyze_scan
from .services.single_scan import load_scan
from .site import MultiScanResult
from .site.analyze_site import analyze_site as _analyze_site

if TYPE_CHECKING:
    from .core.anomaly import AnomalyMap
    from .core.grid import Grid2D


__all__ = ["AnalysisConfig", "ScanAnalysisResult", "analyze", "analyze_site", "load_scan"]


@dataclass(frozen=True, slots=True)
class ScanAnalysisResult:
    """Stable typed wrapper around the legacy scan-analysis tuple."""

    grid: Grid2D
    anomaly: AnomalyMap
    candidates: list[Candidate]
    _field_quality: dict[str, Any] | None = None

    @property
    def field_quality(self) -> dict[str, Any]:
        """Return scan-level field-operational quality assessment."""
        return dict(getattr(self, "_field_quality", {}) or {})


def analyze(
    scan: ScanData,
    out_dir: str | Path = "groundscan_output",
    *,
    label: str = "scan",
    config: AnalysisConfig | None = None,
    write_outputs: bool = True,
) -> ScanAnalysisResult:
    """Analyze one normalized scan with a stable configuration object."""
    cfg = config or AnalysisConfig()
    grid, anomaly, candidates = _analyze_scan(
        scan,
        out_dir,
        label=label,
        config=cfg,
        write_outputs=write_outputs,
    )
    return ScanAnalysisResult(
        grid, anomaly, candidates, dict(scan.metadata.extra.get("field_quality", {}) or {})
    )


def analyze_site(
    scans: Sequence[tuple[str, ScanData]],
    out_dir: str | Path,
    *,
    config: AnalysisConfig | None = None,
    reference_label: str | None = None,
) -> MultiScanResult:
    """Analyze and fuse two or more scans with one stable configuration."""
    cfg = config or AnalysisConfig()
    return _analyze_site(
        list(scans),
        out_dir,
        reference_label=reference_label,
        threshold=cfg.threshold,
        min_size=cfg.min_size,
        zigzag=cfg.zigzag,
        background_method=cfg.background_method,
        scales=cfg.scales,
        connectivity=cfg.connectivity,
        distance_threshold=cfg.distance_threshold,
        resolution=cfg.fusion_resolution,
        soil_mode=cfg.soil_mode,
        extraction_rescue=cfg.extraction_rescue,
        fusion_pruning=cfg.fusion_pruning,
        field_quality_mode=cfg.field_quality_mode,
    )

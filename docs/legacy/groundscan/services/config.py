"""Pipeline configuration: one validated knob object for the analysis modules.

Moved verbatim from :mod:`groundscan.api` so that
:func:`groundscan.services.single_scan.analyze_scan` and its stage helpers
can take the config directly without an ``api -> services -> api`` import
cycle. :mod:`groundscan.api` re-exports this class; ``from groundscan.api
import AnalysisConfig`` keeps working.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Validated configuration shared by single-scan and site analysis."""

    threshold: float = 3.0
    min_size: int = 3
    zigzag: str = "auto"
    background_method: str = "multiscale"
    scales: tuple[int, ...] = (3, 5, 9, 15)
    connectivity: int = 8
    fusion_resolution: int = 40
    distance_threshold: float = 0.06
    soil_mode: str = "diagnostic"
    extraction_rescue: str = "off"
    fusion_pruning: str = "off"
    field_quality_mode: str = "enforce-hard-block"
    # Remediation Design v2 §11 (Wave 1, shadow measurement). Off by default:
    # the shadow computes the corrected value beside the shipped one and records
    # the delta, but decides nothing. "diagnostics" turns on the S02 solidity,
    # S03 scale-status and S01 role measurements and records the diagnostic
    # ledger on ``anomaly`` -- never a candidate field, and never
    # ``metadata.extra`` (both golden-hashed via ``analysis.json``).
    shadow_measurement: str = "off"

    def __post_init__(self) -> None:
        # Normalize (not just validate) so use sites never re-derive:
        # lowercase all mode strings, store scales as a tuple.
        object.__setattr__(self, "zigzag", str(self.zigzag).lower())
        object.__setattr__(self, "background_method", str(self.background_method).lower())
        object.__setattr__(self, "soil_mode", str(self.soil_mode).lower())
        object.__setattr__(self, "extraction_rescue", str(self.extraction_rescue).lower())
        object.__setattr__(self, "fusion_pruning", str(self.fusion_pruning).lower())
        object.__setattr__(self, "field_quality_mode", str(self.field_quality_mode).lower())
        object.__setattr__(self, "shadow_measurement", str(self.shadow_measurement).lower())
        object.__setattr__(self, "scales", tuple(int(s) for s in self.scales))
        if not np.isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("threshold must be a finite value > 0")
        if int(self.min_size) < 1:
            raise ValueError("min_size must be >= 1")
        if self.zigzag not in {"auto", "force", "off"}:
            raise ValueError("zigzag must be one of: auto, force, off")
        if self.background_method not in {"multiscale", "median", "none"}:
            raise ValueError("unsupported background_method")
        if not self.scales:
            raise ValueError("scales must not be empty")
        normalized = tuple(int(s) for s in self.scales if int(s) > 0)
        if normalized != tuple(self.scales) or any(s < 1 for s in normalized):
            raise ValueError("scales must contain positive integers")
        if int(self.connectivity) not in {4, 8}:
            raise ValueError("connectivity must be 4 or 8")
        if int(self.fusion_resolution) < 8:
            raise ValueError("fusion_resolution must be >= 8")
        if not np.isfinite(self.distance_threshold) or self.distance_threshold <= 0:
            raise ValueError("distance_threshold must be a finite value > 0")
        if str(self.soil_mode).lower() not in {"diagnostic", "experimental"}:
            raise ValueError("soil_mode must be one of: diagnostic, experimental")
        if str(self.extraction_rescue).lower() not in {"off", "conservative-geology"}:
            raise ValueError("extraction_rescue must be one of: off, conservative-geology")
        if str(self.fusion_pruning).lower() not in {"off", "conservative-repeatability"}:
            raise ValueError("fusion_pruning must be one of: off, conservative-repeatability")
        if str(self.field_quality_mode).lower() not in {"enforce-hard-block", "report-only"}:
            raise ValueError("field_quality_mode must be one of: enforce-hard-block, report-only")
        if str(self.shadow_measurement).lower() not in {"off", "diagnostics"}:
            raise ValueError("shadow_measurement must be one of: off, diagnostics")


__all__ = ["AnalysisConfig"]

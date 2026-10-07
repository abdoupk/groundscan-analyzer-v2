"""Cross-scan evidence research facade (non-gating).

Frozen multidimensional ranking score plus repeated-holdout runners for
diagnostic synthetic evaluation only. This package never gates production,
never changes detector/fusion/scoring defaults, and never authorizes
production use — synthetic results alone cannot validate field accuracy.
"""

from __future__ import annotations

from groundscan_research.cross_scan_evidence_audit import run_cross_scan_evidence_audit
from groundscan_research.cross_scan_evidence_calibration import run_cross_scan_evidence_calibration
from groundscan_research.cross_scan_evidence_repeated_holdouts import run_repeated_holdouts
from groundscan_research.cross_scan_evidence_stability import run_stability_audit
from groundscan_research.extraction_rescue_discriminants import (
    run_extraction_rescue_discriminant_audit,
)
from groundscan_research.spatial_context_audit import run_spatial_context_audit

__all__ = [
    "run_cross_scan_evidence_audit",
    "run_cross_scan_evidence_calibration",
    "run_repeated_holdouts",
    "run_stability_audit",
    "run_extraction_rescue_discriminant_audit",
    "run_spatial_context_audit",
]

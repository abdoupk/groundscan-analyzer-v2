"""Background-separation facade (research-only, non-gating).

Background separation vs oracle ceiling: practical background estimators are
compared against the oracle true-background-removed ceiling to attribute
broad/geological extraction loss to background estimation without creating
broad false components.

Diagnostic-only: nothing here changes production detection, classification,
thresholds, registration, fusion, scoring, or screening behavior, and no CLI
path imports this package.
"""

from groundscan_research.adaptive_scale_separation import run_adaptive_scale_separation_audit
from groundscan_research.background_decomposition import run_background_decomposition_audit
from groundscan_research.background_factor_attribution import run_background_factor_attribution
from groundscan_research.background_independent_separation import (
    run_background_independent_separation_audit,
)
from groundscan_research.background_separation_audit import run_background_separation_audit

__all__ = [
    "run_background_separation_audit",
    "run_adaptive_scale_separation_audit",
    "run_background_factor_attribution",
    "run_background_decomposition_audit",
    "run_background_independent_separation_audit",
]

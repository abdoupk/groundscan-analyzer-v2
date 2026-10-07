"""Registration failure atlas facade (research-only, non-gating).

Failure taxonomy studied here: no_valid_alignment, no_overlap,
insufficient_overlap, low_correlation, low_multiscale_correlation,
ambiguous_transform_margin, weak_evidence, plus orientation-frame
(0 vs 90 deg) and compound-corruption interactions.

Diagnostic-only: nothing here changes production registration, fusion,
scoring, or detector behavior, and no CLI path imports this package.
"""

from .compound_interaction_analysis import run_compound_interaction_analysis
from .registration_compound_atlas import run_registration_compound_atlas
from .registration_failure_semantics import run_registration_failure_analysis
from .registration_semantics import run_registration_semantics_benchmark

__all__ = [
    "run_registration_failure_analysis",
    "run_registration_compound_atlas",
    "run_compound_interaction_analysis",
    "run_registration_semantics_benchmark",
]

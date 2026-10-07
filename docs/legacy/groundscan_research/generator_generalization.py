"""Generator-generalization facade (research-only, non-gating).

Independent forward-model investigation: the same ground-truth target plans
rendered through independent synthetic forward models (A/B/C) to evaluate the
current analyzer under generator shift rather than seed variation alone.

Diagnostic-only: nothing here changes production detection, classification,
thresholds, registration, fusion, scoring, or screening behavior, and no CLI
path imports this package.
"""

from groundscan_research.broad_response_representation import (
    run_broad_response_representation_audit,
)
from groundscan_research.forward_background_interaction import (
    run_forward_background_interaction_audit,
)
from groundscan_research.generator_c_mechanism import run_generator_c_mechanism_isolation
from groundscan_research.generator_shift_analysis import run_generator_shift_analysis
from groundscan_research.geology_extraction_independence import run_geology_extraction_independence
from groundscan_research.geology_extraction_shift import run_geology_extraction_shift
from groundscan_research.synthetic_generator_independence import (
    run_synthetic_generator_independence,
)

__all__ = [
    "run_synthetic_generator_independence",
    "run_generator_shift_analysis",
    "run_geology_extraction_shift",
    "run_geology_extraction_independence",
    "run_broad_response_representation_audit",
    "run_forward_background_interaction_audit",
    "run_generator_c_mechanism_isolation",
]

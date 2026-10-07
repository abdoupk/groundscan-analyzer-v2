"""Registration recovery facade (research-only, non-gating).

Re-exports the controlled recovery experiments: winsorized/robust scoring,
coverage-aware (relaxed-overlap) search, hybrid and consensus-recovery
agreement checks, repeated-seed validation, and the robustness audit.

Diagnostic-only: production registration is unchanged; recovery is reported
separately from production status. No CLI path imports this package.
"""

from .registration_compound_recovery import run_registration_compound_recovery
from .registration_recovery_coverage import (
    run_registration_recovery_audit as run_registration_recovery_coverage,
)
from .registration_recovery_experiments import (
    run_registration_recovery_audit as run_registration_recovery_experiments,
)
from .registration_recovery_repeated import run_repeated_registration_recovery_validation
from .registration_robustness import run_registration_robustness_audit

__all__ = [
    "run_registration_recovery_experiments",
    "run_registration_recovery_coverage",
    "run_repeated_registration_recovery_validation",
    "run_registration_compound_recovery",
    "run_registration_robustness_audit",
]

"""Response diagnostics: OKM signal characterization, scan quality, dipoles.

``diagnostics.okm`` is deliberately NOT re-exported here: it needs
``services.single_scan`` inside its baseline-signature helpers, so importing it
at package scope would create a cycle. Consumers import it by module path
(``from ..diagnostics.okm import characterize_okm``).
"""

from .dipole import (
    DEFAULT_DIPOLE_MERGE_CONFIG,
    DipoleMergeConfig,
    deblend_spatially_separated_multitarget_pairs,
    merge_dipolar_response_components,
)
from .quality_probe import detect_scan_quality_diagnostics

__all__ = [
    "DEFAULT_DIPOLE_MERGE_CONFIG",
    "DipoleMergeConfig",
    "deblend_spatially_separated_multitarget_pairs",
    "detect_scan_quality_diagnostics",
    "merge_dipolar_response_components",
]

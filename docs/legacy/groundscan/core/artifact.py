"""Public artifact-analysis helpers kept separate from target interpretation.

This module is the canonical public re-export for artifact analysis
(``ArtifactMap``, ``detect_artifacts``). The implementation lives in
:mod:`groundscan.core.anomaly` to keep detection + artifact scoring
together; import from here to avoid coupling to detector internals.
"""

from .anomaly import ArtifactMap, detect_artifacts

__all__ = ["ArtifactMap", "detect_artifacts"]

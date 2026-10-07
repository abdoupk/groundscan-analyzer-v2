"""Pipeline config seam pins (fast).

The single-scan orchestration takes one validated config object instead of
fifteen flat knobs. These tests pin the seam itself: legacy defaults,
re-export identity, and a default-config run through the new signature.
"""

from __future__ import annotations

import numpy as np


def test_config_defaults_match_legacy_signature():
    from groundscan.services.config import AnalysisConfig

    cfg = AnalysisConfig()
    assert cfg.threshold == 3.0
    assert cfg.min_size == 3
    assert cfg.zigzag == "auto"
    assert cfg.background_method == "multiscale"
    assert cfg.scales == (3, 5, 9, 15)
    assert cfg.connectivity == 8
    assert cfg.soil_mode == "diagnostic"
    assert cfg.extraction_rescue == "off"
    assert cfg.field_quality_mode == "enforce-hard-block"


def test_api_reexports_services_config():
    import groundscan.api as api
    from groundscan.services.config import AnalysisConfig

    assert api.AnalysisConfig is AnalysisConfig


def test_analyze_scan_runs_on_default_config(tmp_path):
    from groundscan import ScanData, ScanMetadata
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    n = 12
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = np.zeros((n, n))
    signal[5:7, 5:7] = 12.0
    scan = ScanData(
        x=x.ravel(), y=y.ravel(), z=np.zeros(n * n), signal=signal.ravel(), metadata=ScanMetadata()
    )
    grid, anomaly, candidates = analyze_scan(
        scan,
        tmp_path,
        label="scan",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert grid.signal.shape == (n, n)
    assert anomaly.zscore.shape == (n, n)
    assert isinstance(candidates, list)

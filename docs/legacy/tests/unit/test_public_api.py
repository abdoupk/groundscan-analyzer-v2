"""Public API contract for the refactored layout (fast)."""

import numpy as np
import pytest

import groundscan
from groundscan import AnalysisConfig, ScanData, ScanMetadata, analyze


def _synthetic_scan(n=20):
    rng = np.random.default_rng(0)
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    signal[9:12, 9:12] += 12.0
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


def test_config_validation_and_defaults():
    cfg = AnalysisConfig()
    assert cfg.threshold == 3.0
    with pytest.raises(ValueError):
        AnalysisConfig(threshold=0)
    with pytest.raises(ValueError):
        AnalysisConfig(zigzag="nope")


def test_stable_single_scan_api_without_outputs():
    scan = _synthetic_scan()
    res = analyze(scan, out_dir="unused", write_outputs=False)
    assert len(res.candidates) >= 1


def test_stable_public_version_and_import_surface():
    assert groundscan.__version__.startswith("0.5.")
    for name in ["analyze", "analyze_site", "load_scan", "ScanData", "Candidate"]:
        assert hasattr(groundscan, name)
    assert not hasattr(groundscan, "compare_scans")

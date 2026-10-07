"""Single-scan integration against the frozen vendor fixture (slow-ok)."""

import pytest

from groundscan.validation.fixtures import VENDOR_TRAIN

ORIG = VENDOR_TRAIN / "Pipeline.csv"


@pytest.mark.slow
def test_vendor_pipeline_single_scan(tmp_path):
    if not ORIG.exists():
        pytest.fail("vendor fixture missing: scans/vendor_demo/train/Pipeline.csv must be tracked")
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan, load_scan

    out = tmp_path / "single"
    scan = load_scan(ORIG)
    _, _, cands = analyze_scan(scan, out, label="scan", config=AnalysisConfig())
    assert len(cands) >= 1
    assert (out / "scan_analysis.json").exists()
    assert (out / "scan_candidates.csv").exists()

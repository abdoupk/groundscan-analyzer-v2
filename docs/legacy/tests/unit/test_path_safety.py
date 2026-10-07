"""Path-traversal regression: labels/case_ids cannot escape out_dir."""

from __future__ import annotations

import pytest

from groundscan._util import contained_path, sanitize_label


def test_sanitize_label_strips_traversal():
    assert sanitize_label("../../evil") == "evil"
    assert sanitize_label("/tmp/evil") == "evil"
    assert sanitize_label("a/b") == "b"
    assert sanitize_label("..") == "scan"
    assert sanitize_label(".") == "scan"
    assert sanitize_label("") == "scan"
    assert "/" not in sanitize_label("parent/base")
    assert "\\" not in sanitize_label("a\\b")


def test_contained_path_rejects_escape(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError):
        contained_path(out, "../../evil.csv")
    with pytest.raises(ValueError):
        contained_path(out, "/tmp/evil.csv")
    with pytest.raises(ValueError):
        contained_path(out, "..", "evil.csv")
    ok = contained_path(out, "scan_candidates.csv")
    assert ok.parent.resolve() == out.resolve()


def test_single_scan_outputs_stay_contained(tmp_path):
    import numpy as np

    from groundscan import ScanData, ScanMetadata
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    n = 8
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    scan = ScanData(
        x=x.ravel(), y=y.ravel(), z=np.zeros(n * n), signal=np.zeros(n * n), metadata=ScanMetadata()
    )
    out = tmp_path / "out"
    # Traversal label must be sanitized, never written outside out/.
    analyze_scan(scan, out, label="../../evil", config=AnalysisConfig())
    assert (out.resolve() / "..").resolve() != out
    written = sorted(p.name for p in out.iterdir())
    assert written, "expected sanitized outputs inside out_dir"
    assert not ((tmp_path / "evil_candidates.csv").exists())


def test_field_manifest_scan_path_contained(tmp_path):
    import json

    from groundscan.validation.field import evaluate_field_dataset

    manifest = {
        "independent_field_ground_truth": True,
        "cases": [{"case_id": "ok", "scan_path": "/etc/passwd"}],
    }
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="scan_path"):
        evaluate_field_dataset(mp, out_dir=tmp_path / "fld")

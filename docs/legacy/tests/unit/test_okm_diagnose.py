"""OKM diagnostics: characterize/fingerprint + diagnose CLI surface (fast).

Covers groundscan/diagnostics/okm.py (previously 0% in coverage) and the
`groundscan diagnose` handler. Vendor fixtures keep runs deterministic;
`run_baseline=False` variants skip the detector for speed.
"""

from __future__ import annotations

import argparse

import pytest

from groundscan.cli.diagnose import cmd_okm
from groundscan.diagnostics.okm import (
    _numeric_vector,
    characterize_file,
    characterize_okm,
    fingerprint_okm,
    load_okm_export,
)

VALIDATION = "scans/vendor_demo/validation"
IRON_BOX = f"{VALIDATION}/Iron Box.csv"


def test_characterize_single_file_record_shape():
    record = characterize_file(IRON_BOX, run_baseline=False)
    assert record["file"] == "Iron Box.csv"
    for key in (
        "geometry",
        "signal",
        "depth",
        "source_device_mentions",
        "project_title",
        "baseline_analysis",
    ):
        assert key in record
    assert record["baseline_analysis"] is None  # skipped without baseline


def test_characterize_directory_writes_json_and_markdown(tmp_path):
    report = characterize_okm([VALIDATION], tmp_path / "out", run_baseline=False)
    assert report["files"] >= 4
    assert report["version"] == "0.2.95"
    assert "limitations" in report and report["limitations"]
    assert (tmp_path / "out" / "okm_signal_characterization.json").is_file()
    assert (tmp_path / "out" / "okm_signal_characterization.md").is_file()


def test_characterize_with_baseline_reports_candidate_counts(tmp_path):
    report = characterize_okm([IRON_BOX], tmp_path / "out", run_baseline=True)
    assert report["files"] == 1
    record = report["records"][0]
    assert record["baseline_analysis"] is not None
    assert "candidate_count" in record["baseline_analysis"]


def test_fingerprint_directory_groups_and_reports(tmp_path):
    report = fingerprint_okm([VALIDATION], tmp_path / "out", run_baseline=False)
    assert report["files"] >= 4
    assert "device_groups" in report
    assert (tmp_path / "out" / "okm_signal_fingerprint.json").is_file()
    assert (tmp_path / "out" / "okm_signal_fingerprint.md").is_file()


def test_characterize_empty_inputs_writes_empty_report(tmp_path):
    report = characterize_okm([tmp_path / "missing-dir"], tmp_path / "out")
    assert report["files"] == 0
    assert report["records"] == []


def _namespace(**kwargs):
    defaults = dict(inputs=[IRON_BOX], out="okm_out", mode="characterize", no_baseline=True)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_cli_characterize_mode(tmp_path, capsys):
    rc = cmd_okm(_namespace(out=str(tmp_path / "diag")))
    assert rc == 0
    out = capsys.readouterr().out
    assert "OKM characterization complete" in out


def test_cli_fingerprint_mode(tmp_path, capsys):
    rc = cmd_okm(_namespace(out=str(tmp_path / "diag"), mode="fingerprint"))
    assert rc == 0
    assert "OKM fingerprint complete" in capsys.readouterr().out


def test_cli_parser_wires_diagnose_modes():
    from groundscan.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["diagnose", "--mode", "fingerprint", IRON_BOX])
    assert args.mode == "fingerprint"
    assert args.inputs == [IRON_BOX]
    with pytest.raises(SystemExit):
        parser.parse_args(["diagnose", "--mode", "bogus", IRON_BOX])


def _record(**overrides):
    base = {
        "scale_free_signal": {
            "robust_z_p95": 3.0,
            "robust_z_p99": 4.0,
            "robust_z_std": 1.0,
            "skew_proxy": 0.5,
        },
        "spatial": {
            "neighbor_corr_x": 0.9,
            "neighbor_corr_y": 0.8,
            "gradient_anisotropy": 1.2,
            "laplacian_energy_ratio": 0.1,
        },
        "depth_signal_correlation": 0.3,
    }
    base.update(overrides)
    return base


def test_numeric_vector_identical_records_align():
    import numpy as np

    a = _numeric_vector(_record())
    b = _numeric_vector(_record())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    assert denom > 1e-12
    assert float(np.dot(a, b) / denom) == pytest.approx(1.0)


def test_numeric_vector_missing_fields_fall_back():
    import numpy as np

    v = _numeric_vector({"scale_free_signal": {}, "spatial": {}})
    assert v.shape == (9,)
    assert bool(np.all(np.isfinite(v)))


def test_fingerprint_record_loads_file_once(monkeypatch):
    import groundscan.diagnostics.okm as okm_mod
    from groundscan.services import single_scan as svc

    loads = {"load": 0, "grid": 0}
    real_svc_load = svc.load_scan
    real_grid = okm_mod.reconstruct_grid

    def _count_load(*args, **kwargs):
        loads["load"] += 1
        return real_svc_load(*args, **kwargs)

    def _count_grid(*args, **kwargs):
        loads["grid"] += 1
        return real_grid(*args, **kwargs)

    monkeypatch.setattr(svc, "load_scan", _count_load)
    monkeypatch.setattr(okm_mod, "reconstruct_grid", _count_grid)
    record = okm_mod._fingerprint_record(IRON_BOX, run_baseline=False)
    assert record["file"] == "Iron Box.csv"
    assert loads == {"load": 1, "grid": 1}


def test_preloaded_characterize_matches_direct():
    preloaded = load_okm_export(IRON_BOX)
    direct = characterize_file(IRON_BOX, run_baseline=False)
    via_preload = characterize_file(IRON_BOX, run_baseline=False, _preloaded=preloaded)
    assert via_preload == direct

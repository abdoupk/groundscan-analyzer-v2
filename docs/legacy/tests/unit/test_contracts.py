"""Data-contract regression (Phase 4): CSV caps, delimiter agreement,
finite numerics, config normalization, mutation contract, provenance."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- AnalysisConfig normalization --------------------------------------------


def test_config_normalizes_modes_and_scales():
    from groundscan.services.config import AnalysisConfig

    cfg = AnalysisConfig(soil_mode="Diagnostic", zigzag="AUTO", scales=[3, 5, 9])
    assert cfg.soil_mode == "diagnostic"
    assert cfg.zigzag == "auto"
    assert cfg.scales == (3, 5, 9)
    assert isinstance(cfg.scales, tuple)


def test_config_still_rejects_invalid():
    from groundscan.services.config import AnalysisConfig

    with pytest.raises(ValueError):
        AnalysisConfig(soil_mode="xx")
    with pytest.raises(ValueError):
        AnalysisConfig(scales=[3, 0])


# --- ScanData mutation contract -------------------------------------------------


def test_analyze_scan_enriches_extra_in_place(tmp_path):
    import numpy as np

    from groundscan import ScanData, ScanMetadata
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    n = 8
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    scan = ScanData(
        x=x.ravel(), y=y.ravel(), z=np.zeros(n * n), signal=np.zeros(n * n), metadata=ScanMetadata()
    )
    assert "field_quality" not in (scan.metadata.extra or {})
    analyze_scan(scan, tmp_path / "out", label="m", config=AnalysisConfig(), write_outputs=False)
    assert "field_quality" in scan.metadata.extra


# --- CSV hardening -----------------------------------------------------------------


def test_semicolon_headerless_can_read_agrees_with_read(tmp_path):
    from groundscan.io.generic_csv import GenericCSVAdapter

    adapter = GenericCSVAdapter()
    lines = ["0;0;3", "1;0;4", "0;1;5", "1;1;6"]
    path = _write(tmp_path, "semi.csv", "\n".join(lines) + "\n")
    assert adapter.can_read(path) is True
    scan = adapter.read(path)
    assert len(scan.signal) == 4
    assert list(scan.signal) == [3.0, 4.0, 5.0, 6.0]


def test_inf_coerced_to_nan_generic(tmp_path):
    from groundscan.io.generic_csv import GenericCSVAdapter

    adapter = GenericCSVAdapter()
    path = _write(tmp_path, "inf.csv", "x [m],y [m],Scan Value\n0,0,inf\n1,0,-inf\n2,0,5\n")
    scan = adapter.read(path)
    assert all(np.isnan(scan.signal[:2]))
    assert scan.signal[2] == 5.0
    assert np.all(np.isfinite(scan.signal[np.isfinite(scan.signal)]))


def test_inf_coerced_to_nan_rover(tmp_path):
    from groundscan.io.rover import RoverAdapter

    adapter = RoverAdapter()
    body = (
        "+++ Characteristics +++\n"
        "Field Length: 4.00 m\n"
        "Field Width: 2.00 m\n"
        "+++ Measuring Values +++\n"
        "Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Scan Value\n"
        "0,0,0.0,0.0,inf\n"
        "1,0,0.5,0.0,5\n"
        "2,0,1.0,0.0,6\n"
    )
    path = _write(tmp_path, "mini.csv", body)
    assert adapter.can_read(path) is True
    scan = adapter.read(path)
    assert np.isnan(scan.signal[0])
    assert scan.signal[1] == 5.0
    assert scan.signal[2] == 6.0


def test_oversize_input_refused(tmp_path, monkeypatch):
    import groundscan.io.base as base
    from groundscan.io.generic_csv import GenericCSVAdapter

    monkeypatch.setattr(base, "MAX_INPUT_BYTES", 10)
    path = _write(tmp_path, "big.csv", "x,y,signal\n0,0,1\n")
    with pytest.raises(ValueError, match="exceeds"):
        GenericCSVAdapter().read(path)


def test_huge_field_maps_to_value_error(tmp_path):
    import csv

    from groundscan.io.generic_csv import GenericCSVAdapter

    old_limit = csv.field_size_limit()
    csv.field_size_limit(100)
    try:
        path = _write(tmp_path, "wide.csv", "x,y,signal\n0,0," + "9" * 500 + "\n")
        with pytest.raises(ValueError, match="[Cc][Ss][Vv]"):
            GenericCSVAdapter().read(path)
    finally:
        csv.field_size_limit(old_limit)


def test_measured_metric_coordinates_pass_through(tmp_path):
    from groundscan.io.generic_csv import GenericCSVAdapter

    path = _write(tmp_path, "m.csv", "x_m,y_m,signal\n0.0,0.0,1\n2.5,0.0,2\n")
    scan = GenericCSVAdapter().read(path)
    assert scan.coordinate_provenance == "measured"
    assert list(scan.x) == [0.0, 2.5]
    assert list(scan.y) == [0.0, 0.0]

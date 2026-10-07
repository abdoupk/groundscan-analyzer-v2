"""GenericCSV adapter: delimiters, aliases, provenance, robustness (fast)."""

from __future__ import annotations

import numpy as np
import pytest

from groundscan.io import detect_adapter
from groundscan.io.generic_csv import GenericCSVAdapter

ADAPTER = GenericCSVAdapter()


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_headerless_xyz_signal_from_third_column(tmp_path):
    path = _write(tmp_path, "grid.csv", "0,0,10\n1,0,11\n0,1,12\n1,1,40\n")
    assert ADAPTER.can_read(path) is True
    scan = ADAPTER.read(path)
    assert list(scan.signal) == [10.0, 11.0, 12.0, 40.0]
    assert scan.coordinate_provenance == "derived"
    assert scan.metadata.extra["headerless_xyz"] is True
    assert scan.metadata.device == "generic_csv"


def test_headerless_with_metadata_tail_columns(tmp_path):
    path = _write(tmp_path, "prof.txt", "0,0,5,profile-A\n1,0,6,profile-A\n")
    assert ADAPTER.can_read(path) is True
    scan = ADAPTER.read(path)
    assert list(scan.signal) == [5.0, 6.0]


def test_header_aliases_and_measured_provenance(tmp_path):
    path = _write(
        tmp_path,
        "survey.csv",
        "x [m],y [m],Scan Value,depth [m]\n0,0,10,1.0\n2,0,11,1.2\n",
    )
    assert ADAPTER.can_read(path) is True
    scan = ADAPTER.read(path)
    assert list(scan.signal) == [10.0, 11.0]
    assert scan.coordinate_provenance == "measured"


def test_bare_xy_is_derived_and_impulse_is_index(tmp_path):
    bare = _write(tmp_path, "bare.csv", "x,y,signal\n0,0,1\n1,0,2\n")
    assert ADAPTER.read(bare).coordinate_provenance == "derived"
    index = _write(tmp_path, "rover_like.csv", "Impulse X,Scan Line Y,signal\n0,0,1\n1,0,2\n")
    scan = ADAPTER.read(index)
    assert scan.coordinate_provenance == "index"
    assert scan.coords_are_index_only is True


def test_semicolon_delimiter_and_aux_columns(tmp_path):
    path = _write(
        tmp_path,
        "semi.csv",
        "x;y;amplitude;lat;lon;twt\n0;0;3;48.1;11.0;12.5\n1;0;4;48.2;11.1;13.5\n",
    )
    scan = ADAPTER.read(path)
    assert list(scan.signal) == [3.0, 4.0]
    assert scan.latitude is not None and scan.longitude is not None
    assert scan.twt_ns is not None
    assert list(scan.twt_ns) == [12.5, 13.5]


def test_malformed_cells_become_nan_not_crash(tmp_path):
    path = _write(tmp_path, "bad.csv", "x,y,signal\n0,0,ok\n1,0,2\n")
    scan = ADAPTER.read(path)
    assert np.isnan(scan.signal[0])
    assert scan.signal[1] == 2.0


def test_constant_soil_columns_land_in_metadata(tmp_path):
    path = _write(
        tmp_path,
        "soil.csv",
        "x,y,signal,dielectric constant\n0,0,1,8.0\n1,0,2,8.0\n",
    )
    scan = ADAPTER.read(path)
    assert scan.metadata.dielectric_constant == pytest.approx(8.0)


def test_missing_signal_column_rejected(tmp_path):
    assert ADAPTER.can_read(tmp_path / "nope.csv") is False
    path = _write(tmp_path, "nonsense.csv", "foo,bar\n1,2\n")
    assert ADAPTER.can_read(path) is False
    with pytest.raises(ValueError):
        ADAPTER.read(path)


def test_empty_and_wrong_suffix_rejected(tmp_path):
    empty = _write(tmp_path, "empty.csv", "")
    assert ADAPTER.can_read(empty) is False
    dat = _write(tmp_path, "scan.dat", "x,y,signal\n0,0,1\n")
    assert ADAPTER.can_read(dat) is False


def test_detect_adapter_routes_generic_files(tmp_path):
    path = _write(tmp_path, "generic.csv", "x,y,signal\n0,0,1\n1,0,2\n0,1,3\n1,1,4\n")
    adapter = detect_adapter(path)
    assert adapter.name == "generic_csv"

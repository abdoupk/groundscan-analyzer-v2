"""Fallback adapter for delimited text with recognizable spatial/signal columns."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import numpy as np

from ..models import ScanData, ScanMetadata
from .base import PathLike, ScannerAdapter, check_input_size

_COLUMN_ALIASES = {
    "x": ["x", "x [m]", "x_m", "pos_x", "impulse x [m]", "impulse x"],
    "y": ["y", "y [m]", "y_m", "pos_y", "scan line y [m]", "scan line y"],
    "z": ["z", "depth", "depth [m]", "depth_m", "depth z [m]"],
    "twt_ns": [
        "twt",
        "twt [ns]",
        "two way travel time [ns]",
        "two-way travel time [ns]",
        "two way travel time",
    ],
    "signal": ["signal", "value", "scan value", "amplitude", "reading"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng"],
    "dielectric_constant": ["dielectric constant", "dielectric", "soil dielectric constant"],
    "relative_permeability": [
        "relative permeability",
        "permeability",
        "soil relative permeability",
    ],
    "mineralization_pct": ["mineralization", "mineralization %", "soil mineralization"],
    "humidity_pct": ["humidity", "humidity %", "soil humidity"],
    "homogeneity_pct": ["homogeneity", "homogeneity %", "soil homogeneity"],
}


def _norm(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("_", " ").split())


def _find_column(columns_lower: dict[str, str], aliases: list[str]) -> str | None:
    for alias in aliases:
        if _norm(alias) in columns_lower:
            return columns_lower[_norm(alias)]
    return None


def _reject_duplicate_headers(header: list[str], path: Path) -> None:
    """Raise if a column name repeats, literally or after normalization.

    A repeat used to collapse silently: the ``{name: [] for name in header}``
    comprehension kept one key for both occurrences, so the header claimed four
    columns while the data carried three and the file then failed far away in
    ``ScanData.__post_init__`` with an arity message ("must be an array of
    length 3 (len(signal)), got 6") that named the model rather than the file.

    Normalization is checked as well as the literal text because the reader
    looks columns up through :func:`_norm`, so ``X`` and ``x`` are the same
    lookup key and one would silently shadow the other.
    """
    seen: dict[str, str] = {}
    for name in header:
        key = _norm(name)
        if key in seen:
            raise ValueError(
                f"{path}: duplicate column name {name!r} in the header row "
                f"(column {header.index(name) + 1} repeats column "
                f"{header.index(seen[key]) + 1}, {seen[key]!r}); every column "
                f"must have a unique name"
            )
        seen[key] = name


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _float_array(cells: list[str]) -> np.ndarray[Any, Any]:
    """Parse a column of strings to finite-or-NaN floats.

    Unparseable cells become NaN (a few malformed cells must not abort the
    whole read; the field-quality gate reports them). Non-finite parses
    (±Inf) are also coerced to NaN per the adapter numeric contract, so no
    infinity reaches grid/statistics code.
    """
    out = np.empty(len(cells), dtype=float)
    for i, value in enumerate(cells):
        try:
            parsed = float(str(value).strip())
        except (TypeError, ValueError):
            out[i] = np.nan
        else:
            out[i] = parsed if np.isfinite(parsed) else np.nan
    return out


class GenericCSVAdapter(ScannerAdapter):
    name = "generic_csv"

    @staticmethod
    def _looks_headerless_xyz(rows: list[list[str]]) -> bool:
        """Recognize raw XYZ-like CSV/TXT without a header.

        Accept exactly 3 columns, or 3 numeric leading columns followed by
        non-numeric metadata columns (e.g. profile/probe). This is intentionally
        conservative so timestamped 4-column logs are not silently mis-mapped.
        """
        sample = [r for r in rows if any(cell.strip() for cell in r)][:8]
        if not sample or len(sample[0]) < 3:
            return False

        def is_number(value: str) -> bool:
            try:
                float(value.strip())
                return True
            except (TypeError, ValueError):
                return False

        if any(len(r) < 3 or not all(is_number(v) for v in r[:3]) for r in sample):
            return False

        widths = {len(r) for r in sample}
        if widths == {3}:
            return True
        if any(len(r) < 4 for r in sample):
            return False
        return all(not is_number(r[3]) for r in sample)

    def can_read(self, path: PathLike) -> bool:
        try:
            path = Path(path)
            if path.suffix.lower() not in (".csv", ".txt", ".tsv"):
                return False
            head = path.read_text(encoding="utf-8-sig", errors="replace")[:8000]
            if not head.strip():
                return False
            delimiter = _detect_delimiter(head)
            # The headerless probe must use the same dialect as read();
            # the default comma dialect mis-split semicolon/tab/pipe files
            # so can_read could claim (or reject) what read() parses
            # differently.
            rows = list(csv.reader(io.StringIO(head), delimiter=delimiter))
            if self._looks_headerless_xyz(rows):
                return True
            first_line = head.splitlines()[0]
            cols = [_norm(c) for c in first_line.split(delimiter)]
            has_signal = any(_norm(alias) in cols for alias in _COLUMN_ALIASES["signal"])
            has_xy = any(_norm(alias) in cols for alias in _COLUMN_ALIASES["x"]) and any(
                _norm(alias) in cols for alias in _COLUMN_ALIASES["y"]
            )
            return has_signal and has_xy
        except (OSError, UnicodeError, ValueError, csv.Error, IndexError):
            return False

    def read(self, path: PathLike) -> ScanData:
        path = Path(path)
        check_input_size(path)
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{path}: cannot read scan file: {exc}") from exc
        delimiter = _detect_delimiter(text)
        try:
            rows = [
                r
                for r in csv.reader(io.StringIO(text), delimiter=delimiter)
                if any(cell.strip() for cell in r)
            ]
        except csv.Error as exc:
            raise ValueError(
                f"{path}: CSV parse failed ({exc}); check delimiter/field sizes"
            ) from exc
        if not rows:
            raise ValueError(f"{path}: file contains no data rows")
        headerless = self._looks_headerless_xyz(rows)
        soil_values: dict[str, float | None] = {
            name: None
            for name in (
                "dielectric_constant",
                "relative_permeability",
                "mineralization_pct",
                "humidity_pct",
                "homogeneity_pct",
            )
        }
        if headerless:
            header: list[str] = []
            data_rows = rows
            columns: dict[str, list[str]] = {}
        else:
            header = [c.strip() for c in rows[0]]
            data_rows = rows[1:]
            _reject_duplicate_headers(header, path)
            columns = {name: [] for name in header}
            for row in data_rows:
                for i, name in enumerate(header):
                    columns[name].append(row[i] if i < len(row) else "")
        columns_lower = {_norm(c): c for c in header}

        def col(field: str) -> np.ndarray[Any, Any] | None:
            found = _find_column(columns_lower, _COLUMN_ALIASES[field])
            if found is None:
                return None
            return _float_array(columns[found])

        if headerless:
            x: np.ndarray[Any, Any] | None = _float_array([r[0] for r in data_rows])
            y: np.ndarray[Any, Any] | None = _float_array([r[1] for r in data_rows])
            z: np.ndarray[Any, Any] | None = None
            signal: np.ndarray[Any, Any] | None = _float_array([r[2] for r in data_rows])
            latitude = None
            longitude = None
            twt_ns = None
            # v0.4.2 (audit F-05): positional columns carry no stated units or
            # role; their metric semantics are not verified.
            coordinate_provenance = "derived"
        else:
            x, y, z, signal = col("x"), col("y"), col("z"), col("signal")
            twt_ns = col("twt_ns")
            latitude = col("latitude")
            longitude = col("longitude")

            # v0.4.2 (audit F-05): coordinate provenance follows the matched
            # header names. Unit-bearing headers ("x [m]", "x_m") verify metric
            # geometry; bare names ("x", "y") and device index columns
            # ("Impulse X", "Scan Line Y") do not.
            def _axis_provenance(found_name: str | None) -> str | None:
                if found_name is None:
                    return None
                normalized = _norm(found_name)
                # NOTE: `_norm` turns "x_m" into "x m", so the "_m" suffix
                # must be tested on the raw header, not the normalized one
                # (previously dead code: normalized text never ends with
                # "_m", and x_m/y_m fell through to "derived" against the
                # documented intent).
                raw = str(found_name).strip().lower()
                if "[m]" in normalized or raw.endswith("_m"):
                    return "measured"
                if normalized in ("impulse x", "scan line y"):
                    return "index"
                return "derived"

            axis_states = [
                state
                for state in (
                    _axis_provenance(_find_column(columns_lower, _COLUMN_ALIASES["x"])),
                    _axis_provenance(_find_column(columns_lower, _COLUMN_ALIASES["y"])),
                )
                if state is not None
            ]
            if "index" in axis_states:
                coordinate_provenance = "index"
            elif axis_states and all(state == "measured" for state in axis_states):
                coordinate_provenance = "measured"
            else:
                coordinate_provenance = "derived"

            def constant_value(field: str) -> float | None:
                found = _find_column(columns_lower, _COLUMN_ALIASES[field])
                if found is None:
                    return None
                vals = _float_array(columns[found])
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    return None
                first = float(vals[0])
                return first if bool(np.allclose(vals, first, rtol=0.0, atol=1e-9)) else None

            soil_values = {
                "dielectric_constant": constant_value("dielectric_constant"),
                "relative_permeability": constant_value("relative_permeability"),
                "mineralization_pct": constant_value("mineralization_pct"),
                "humidity_pct": constant_value("humidity_pct"),
                "homogeneity_pct": constant_value("homogeneity_pct"),
            }
        if x is None or y is None or signal is None:
            raise ValueError(
                f"{path}: could not identify x/y/signal columns among {header or ['<headerless>']}"
            )
        if z is None:
            z = np.full_like(x, np.nan)

        return ScanData(
            x=x,
            y=y,
            z=z,
            signal=signal,
            twt_ns=twt_ns,
            latitude=latitude,
            longitude=longitude,
            coords_are_index_only=(coordinate_provenance == "index"),
            coordinate_provenance=coordinate_provenance,
            metadata=ScanMetadata(
                device="generic_csv",
                source_file=str(path),
                dielectric_constant=soil_values.get("dielectric_constant"),
                relative_permeability=soil_values.get("relative_permeability"),
                mineralization_pct=soil_values.get("mineralization_pct"),
                humidity_pct=soil_values.get("humidity_pct"),
                homogeneity_pct=soil_values.get("homogeneity_pct"),
                extra={"headerless_xyz": headerless},
            ),
        )

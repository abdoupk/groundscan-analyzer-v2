"""
Adapter for OKM Rover-family exports (Rover C, Rover C II, Rover UC, ...).

The export format is NOT a plain CSV: it's a sequence of
    +++ SectionName +++
    Key: Value
    ...
sections (Characteristics, Meta Data, Soil Type, ...) followed by one
final section, "Measuring Values", which *is* a normal CSV table.

Important, hard-won detail (seen in real exports): the metric columns
`Impulse X [m]` / `Scan Line Y [m]` are all 0.0000 whenever the operator
never entered the scan field's Length/Width in the OKM software before
exporting. This adapter therefore:
  1. Always keeps the raw grid indices (`grid_i`, `grid_j`).
  2. Uses the metric columns only if they actually vary; otherwise
     reconstructs metric coordinates from `field_length_m` /
     `field_width_m` in the Characteristics section (if present), and
     otherwise falls back to raw indices, flagging
     `coords_are_index_only=True` so downstream code (and reports)
     know the "meters" are really just grid cells.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

import numpy as np

from ..models import ScanData, ScanMetadata
from .base import PathLike, ScannerAdapter, check_input_size

_SECTION_RE = re.compile(r"^\+\+\+\s*(.+?)\s*\+\+\+$")


def _to_float(text: str | None) -> float | None:
    """Parse things like '10.00 m', '0 %', '3.9203' -> float, else None.

    v0.4.2 (audit F-04): when both '.' and ',' appear, the rightmost one is the
    decimal separator and the other is a thousands separator, so
    '1,234.5 m' -> 1234.5 and '1.234,5 m' -> 1234.5. Previously the regex
    matched only the leading digit group, silently truncating '1,234.5 m' to
    1.234 and corrupting field dimensions plus every coordinate rescaled from
    them. Single-separator strings keep the historical interpretation
    (',' treated as a decimal mark); mixed groups like '0.0000' and '10.00'
    are unaffected.
    """
    if text is None:
        return None
    cleaned = text.strip()
    has_dot = "." in cleaned
    has_comma = "," in cleaned
    if has_dot and has_comma:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    else:
        match = re.search(r"-?\d+(?:[.,]\d+)?", cleaned)
        if match:
            return float(match.group(0).replace(",", "."))
        return None
    if not match:
        return None
    return float(match.group(0))


class RoverAdapter(ScannerAdapter):
    name = "rover"

    def __init__(self, line_spacing_m: float | None = None, point_spacing_m: float | None = None):
        """
        line_spacing_m  : real distance between adjacent scan lines (the
                            "Scan Line Y" axis), in meters, if you know it
                            from how you actually walked the grid. Overrides
                            guessing it from Field Width / number of lines.
        point_spacing_m  : real distance between adjacent impulses along a
                            single line (the "Impulse X" axis), in meters.
                            Overrides guessing it from Field Length / count.

        Both are optional — leave them out and the adapter falls back to
        the metric columns, then Field Length/Width, then raw indices,
        exactly as before.
        """
        self.line_spacing_m = line_spacing_m
        self.point_spacing_m = point_spacing_m

    def can_read(self, path: PathLike) -> bool:
        try:
            text = self._read_text(path)[:6000]
        except (OSError, UnicodeError, ValueError):
            return False
        return "+++ measuring values +++" in text.lower() or (
            "rover" in text.lower() and "impulse x" in text.lower()
        )

    def read(self, path: PathLike) -> ScanData:
        check_input_size(path)
        try:
            text = self._read_text(path)
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{path}: cannot read scan file: {exc}") from exc
        lines = text.splitlines()

        header_idx = self._find_measurement_header(lines)
        sections = self._parse_sections(lines[:header_idx])
        metadata = self._build_metadata(sections, source_file=str(path))

        table_text = "\n".join(lines[header_idx:])
        try:
            rows = list(csv.reader(io.StringIO(table_text)))
        except csv.Error as exc:
            raise ValueError(f"{path}: Rover table parse failed ({exc})") from exc
        rows = [r for r in rows if any(cell.strip() for cell in r)]
        header = [c.strip().strip('"') for c in rows[0]]
        data_rows = rows[1:]

        col_idx = {name: i for i, name in enumerate(header)}

        def col(name: str) -> np.ndarray[Any, Any]:
            i = col_idx.get(name)
            if i is None:
                return np.full(len(data_rows), np.nan)
            out = np.empty(len(data_rows), dtype=float)
            for r, row in enumerate(data_rows):
                try:
                    parsed = float(row[i]) if row[i].strip() else np.nan
                except (ValueError, IndexError):
                    out[r] = np.nan
                else:
                    # Finite-or-NaN adapter contract: no infinities downstream.
                    out[r] = parsed if np.isfinite(parsed) else np.nan
            return out

        grid_i = col("Impulse X")
        grid_j = col("Scan Line Y")
        x_m = col("Impulse X [m]")
        y_m = col("Scan Line Y [m]")
        z = col("Depth Z [m]")
        signal = col("Scan Value")
        lat = col("Latitude")
        lon = col("Longitude")

        x, y, provenance = self._resolve_coordinates(grid_i, grid_j, x_m, y_m, metadata)

        # v0.4.2 (audit F-21): count distinct positions instead of max().
        # Device exports may be 0-based (0..4 has max 4 for 5 impulses) or
        # 1-based, so max() is off by one for one of them; distinct-count is
        # correct for both. An all-NaN index column yields None instead of
        # crashing np.nanmax with ValueError.
        def _distinct_count(values: np.ndarray[Any, Any]) -> int | None:
            finite = np.asarray(values, dtype=float)
            finite = finite[np.isfinite(finite)]
            return int(np.unique(finite).size) if finite.size else None

        metadata.extra["n_impulses"] = _distinct_count(grid_i) if len(grid_i) else None
        metadata.extra["n_scan_lines"] = _distinct_count(grid_j) if len(grid_j) else None

        return ScanData(
            x=x,
            y=y,
            z=z,
            signal=signal,
            grid_i=grid_i,
            grid_j=grid_j,
            latitude=lat if np.any(~np.isnan(lat)) else None,
            longitude=lon if np.any(~np.isnan(lon)) else None,
            coords_are_index_only=(provenance == "index"),
            coordinate_provenance=provenance,
            metadata=metadata,
        )

    # -- internals ---------------------------------------------------

    @staticmethod
    def _find_measurement_header(lines: list[str]) -> int:
        for i, line in enumerate(lines):
            cleaned = line.strip().strip('"')
            if cleaned.lower().startswith("impulse x,scan line y") or (
                cleaned.lower().startswith("impulse x") and "scan value" in cleaned.lower()
            ):
                return i
        raise ValueError("Could not locate the 'Measuring Values' table header in this file.")

    @staticmethod
    def _parse_sections(lines: list[str]) -> dict[str, dict[str, str]]:
        sections: dict[str, dict[str, str]] = {}
        current = "General"
        sections[current] = {}
        for raw in lines:
            line = raw.strip().strip('"')
            if not line:
                continue
            section_match = _SECTION_RE.match(line)
            if section_match:
                current = section_match.group(1)
                sections.setdefault(current, {})
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                sections[current][key.strip()] = value.strip()
        return sections

    @staticmethod
    def _build_metadata(sections: dict[str, dict[str, str]], source_file: str) -> ScanMetadata:
        chars = sections.get("Characteristics", {})
        soil = sections.get("Soil Type", {})
        meta = sections.get("Meta Data", {})

        # Device name is often buried inside the "Notes" value, e.g.
        # "Notes: Device: Rover C II" -> Notes value is "Device: Rover C II".
        device = None
        notes_value = chars.get("Notes", "")
        dev_match = re.search(r"Device:\s*(.+)", notes_value)
        if dev_match:
            device = dev_match.group(1).strip()

        metadata = ScanMetadata(
            device=device,
            date=chars.get("Date") or meta.get("Date / Time"),
            time=chars.get("Time"),
            soil_type=soil.get("Title"),
            dielectric_constant=_to_float(soil.get("Dielectric Constant")),
            relative_permeability=_to_float(soil.get("Relative Permeability")),
            mineralization_pct=_to_float(soil.get("Mineralization")),
            humidity_pct=_to_float(soil.get("Humidity")),
            homogeneity_pct=_to_float(soil.get("Homogeneity")),
            field_length_m=_to_float(chars.get("Field Length")),
            field_width_m=_to_float(chars.get("Field Width")),
            notes=notes_value or None,
            source_file=source_file,
            extra={
                "operating_mode": chars.get("Operating Mode"),
                "scan_mode": chars.get("Scan Mode"),
                "impulse_mode": chars.get("Impulse Mode"),
                "soil_dielectric_constant": _to_float(soil.get("Dielectric Constant")),
                "soil_relative_permeability": _to_float(soil.get("Relative Permeability")),
                "soil_humidity_pct": _to_float(soil.get("Humidity")),
                "soil_homogeneity_pct": _to_float(soil.get("Homogeneity")),
            },
        )
        return metadata

    def _resolve_coordinates(
        self,
        grid_i: np.ndarray[Any, Any],
        grid_j: np.ndarray[Any, Any],
        x_m: np.ndarray[Any, Any],
        y_m: np.ndarray[Any, Any],
        metadata: ScanMetadata,
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], str]:
        """
        Decide what to actually use as spatial x/y.

        Priority:
          1. Explicit line_spacing_m / point_spacing_m passed to the
             adapter's constructor — you told us the real spacing, so
             that wins over anything guessed from the file.
          2. Metric columns, if they show real variation (not all 0/NaN).
          3. Grid indices rescaled to field_length/field_width, if those
             were entered in the OKM software (assumes uniform spacing
             across the whole field — fine unless you walked uneven lines).
          4. Raw grid indices as-is, flagged as index-only.
        """
        if self.point_spacing_m is not None or self.line_spacing_m is not None:
            i0 = np.nanmin(grid_i) if len(grid_i) else 0.0
            j0 = np.nanmin(grid_j) if len(grid_j) else 0.0
            x = (grid_i - i0) * (self.point_spacing_m if self.point_spacing_m is not None else 1.0)
            y = (grid_j - j0) * (self.line_spacing_m if self.line_spacing_m is not None else 1.0)
            # v0.4.2 (audit F-05): user-asserted real spacing is accepted as
            # measured only when BOTH spacings were provided; a single asserted
            # axis leaves the other one in raw cell units (index-only).
            if self.point_spacing_m is not None and self.line_spacing_m is not None:
                return x, y, "measured"
            return x, y, "index"

        metric_varies_x = bool(len(x_m)) and np.nanstd(x_m) > 1e-9
        metric_varies_y = bool(len(y_m)) and np.nanstd(y_m) > 1e-9

        # v0.4.2 (audit F-11): partial metric entry (e.g. Field Length entered
        # but not Field Width) leaves one metric axis all-zero while the device
        # index grid still has multiple positions. The previous "x varies OR
        # y varies" test accepted such columns, silently collapsing that axis
        # during grid reconstruction (a measured 8x5 scan became an 8x1 grid
        # with cross-line averaging) while the geometry summary, which reads
        # the index columns, still reported the full rectangle. Accept the
        # metric columns only when BOTH axes vary AND each axis's distinct
        # metric positions match the device index partition; otherwise fall
        # through to the index-based strategies.
        def _distinct_positions(values: np.ndarray[Any, Any]) -> int:
            finite = values[np.isfinite(values)]
            return int(np.unique(np.round(finite, 6)).size) if finite.size else 0

        index_lines = int(np.unique(grid_j[~np.isnan(grid_j)]).size) if len(grid_j) else 0
        index_impulses = int(np.unique(grid_i[~np.isnan(grid_i)]).size) if len(grid_i) else 0
        metric_consistent = (
            metric_varies_x
            and metric_varies_y
            and _distinct_positions(x_m) == index_impulses
            and _distinct_positions(y_m) == index_lines
        )
        if metric_consistent:
            return x_m, y_m, "measured"

        if metadata.coordinates_are_metric:
            # v0.4.2 (audit F-21): without any finite grid indices there is
            # nothing to rescale -- fall through to index fallback instead of
            # propagating NaN coordinates labeled as derived-metric.
            if not (bool(np.any(np.isfinite(grid_i))) and bool(np.any(np.isfinite(grid_j)))):
                return (
                    np.asarray(grid_i, dtype=float).copy(),
                    np.asarray(grid_j, dtype=float).copy(),
                    "index",
                )
            i_range = np.nanmax(grid_i) - np.nanmin(grid_i) or 1
            j_range = np.nanmax(grid_j) - np.nanmin(grid_j) or 1
            x = (grid_i - np.nanmin(grid_i)) / i_range * metadata.field_length_m
            y = (grid_j - np.nanmin(grid_j)) / j_range * metadata.field_width_m
            # v0.4.2 (audit F-05): coordinates reconstructed from self-reported
            # header dimensions are DERIVED, not independently verified metric
            # measurements.
            return x, y, "derived"

        # Last resort: index-only coordinates. Still usable for shape/
        # cross-scan analysis, just not real meters.
        return grid_i.copy(), grid_j.copy(), "index"

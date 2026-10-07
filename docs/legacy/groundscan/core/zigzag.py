"""
Zigzag vs. parallel scan pattern handling.

Context: OKM devices (and similar) can be walked in "Parallel" mode
(every line walked in the same direction, operator returns to the
start each time) or "Zigzag" mode (alternating direction — faster to
walk). The exported "Scan Mode" field is *supposed* to record which one
was used, but in real exports we've seen it come back "N/A", and this
library has no independent way to confirm whether the device's own
`Impulse X` index was already corrected for walking direction before
export or not.

So instead of trusting either the metadata field or an assumption, this
module runs a **data-driven diagnostic**: physically, a real ground
scan's signal tends to vary smoothly between geographically adjacent
scan lines (soil trend + real targets both span more than one line).
If every other line needs to be reversed to restore that smoothness,
that's reasonably strong evidence the raw data is zigzag-ordered and
uncorrected. This is a heuristic, not a certainty — very short lines,
very noisy data, or a genuinely line-by-line-changing target can fool
it. `diagnose_zigzag` always reports both scores so you can judge for
yourself.

Correction policy lives with the caller: `correct_zigzag` flips
unconditionally when called, while the pipeline applies it in "force"
mode or in "auto" mode when the margin fires -- except for
independently positioned (GPS) samples (see
`has_independent_positioning`), where mirroring rows would corrupt real
positions and auto-correction stays off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .grid import Grid2D


@dataclass
class ZigzagDiagnosis:
    continuity_as_is: float  # mean correlation between adjacent lines, as exported
    continuity_if_flipped: float  # mean correlation if every other line is reversed
    recommend_correction: bool
    margin: float  # continuity_if_flipped - continuity_as_is
    reported_scan_mode: str | None  # whatever the device's own "Scan Mode" metadata said


def _mean_adjacent_correlation(signal: np.ndarray[Any, Any]) -> float:
    ny = signal.shape[0]
    scores = []
    for j in range(ny - 1):
        row_a, row_b = signal[j], signal[j + 1]
        valid = ~np.isnan(row_a) & ~np.isnan(row_b)
        if valid.sum() < 3:
            continue
        a, b = row_a[valid], row_b[valid]
        if np.std(a) < 1e-9 or np.std(b) < 1e-9:
            continue
        scores.append(np.corrcoef(a, b)[0, 1])
    return float(np.mean(scores)) if scores else 0.0


def diagnose_zigzag(
    grid: Grid2D, reported_scan_mode: str | None = None, margin_threshold: float = 0.15
) -> ZigzagDiagnosis:
    as_is = _mean_adjacent_correlation(grid.signal)

    flipped = grid.signal.copy()
    flipped[1::2] = flipped[1::2, ::-1]
    if_flipped = _mean_adjacent_correlation(flipped)

    margin = if_flipped - as_is
    return ZigzagDiagnosis(
        continuity_as_is=round(as_is, 3),
        continuity_if_flipped=round(if_flipped, 3),
        recommend_correction=margin > margin_threshold,
        margin=round(margin, 3),
        reported_scan_mode=reported_scan_mode,
    )


def has_independent_positioning(
    latitude: np.ndarray[Any, Any] | None,
    longitude: np.ndarray[Any, Any] | None,
    *,
    min_std: float = 1e-9,
) -> bool:
    """True when per-sample coordinates vary enough to anchor sample positions.

    v0.4.2 (audit F-09): row-order zigzag correction assumes grid rows are
    acquisition lines whose direction may need mirroring. With independently
    positioned samples (GPS), each sample already sits where it was taken,
    so mirroring rows would corrupt real positions and auto-correction must
    stay off. All-zero or constant coordinate columns do not count: they
    carry no per-sample information.
    """
    try:
        lat = np.asarray(latitude, dtype=float)
        lon = np.asarray(longitude, dtype=float)
    except (TypeError, ValueError):
        return False
    if lat.shape != lon.shape or lat.size < 2:
        return False
    finite = np.isfinite(lat) & np.isfinite(lon)
    if int(np.count_nonzero(finite)) < 2:
        return False
    return bool(float(np.std(lat[finite])) > min_std or float(np.std(lon[finite])) > min_std)


def correct_zigzag(grid: Grid2D) -> Grid2D:
    """Reverse every other line (odd row index) along X. Returns a new Grid2D."""
    signal = grid.signal.copy()
    depth = grid.depth.copy()
    counts = grid.counts.copy()
    signal[1::2] = signal[1::2, ::-1]
    depth[1::2] = depth[1::2, ::-1]
    counts[1::2] = counts[1::2, ::-1]
    return Grid2D(
        x_centers=grid.x_centers,
        y_centers=grid.y_centers,
        signal=signal,
        depth=depth,
        counts=counts,
    )

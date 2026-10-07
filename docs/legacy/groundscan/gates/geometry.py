"""
Scan geometry sanity check.

This exists for one specific, recurring problem: a device export claims
a certain grid shape (N impulses x M lines), but that doesn't always
match what the operator actually remembers walking. Rather than trust
either side blindly, this module just reports the *raw facts* found in
the data — unique line count, points per line, whether it forms a
clean rectangle — so the operator can compare it against their own
memory of the walk and decide what to trust.

It deliberately does not try to guess which side (file vs. memory) is
right. A big mismatch is a signal to go look at the source file more
closely (timestamps, whether multiple sessions got exported together,
whether "Scan Line" incremented on a pause/restart) — not something
this library can resolve on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.grid import Grid2D
from ..models import ScanData


@dataclass
class GeometrySummary:
    n_points: int
    n_unique_lines: int | None  # unique Scan Line Y values, if the device reports a grid
    n_unique_impulses: int | None  # unique Impulse X values
    points_per_line_min: int | None
    points_per_line_max: int | None
    points_per_line_median: float | None
    is_clean_rectangle: bool  # every line has the same point count == n_unique_impulses
    # v0.4.2 (audit F-11): the raw-column facts above describe the export,
    # but analysis runs on the BUILT grid, which can differ (parsed axes
    # collapsing, scatter fallback). When the caller passes the grid, its
    # shape is recorded here so reports cannot claim a clean rectangle the
    # analysis never saw. All three default to None (unknown) for callers
    # without a grid; existing readers of the raw fields are unaffected.
    grid_nx: int | None = None
    grid_ny: int | None = None
    grid_matches_raw_rectangle: bool | None = None

    def describe(self) -> str:
        if self.n_unique_lines is None:
            return f"{self.n_points} point(s); this device/file doesn't report a line/impulse grid."

        lines = [
            f"{self.n_points} point(s) total.",
            f"Unique scan lines (Scan Line Y): {self.n_unique_lines}.",
            f"Unique impulse positions (Impulse X): {self.n_unique_impulses}.",
            f"Points per line: min={self.points_per_line_min}, "
            f"max={self.points_per_line_max}, median={self.points_per_line_median}.",
        ]
        if self.is_clean_rectangle:
            # Invariant: a clean rectangle is only recorded with concrete
            # impulse/line counts (see summarize_geometry); the assert
            # narrows the Optional types for the product below.
            assert self.n_unique_impulses is not None and self.n_unique_lines is not None
            lines.append(
                f"Forms a clean {self.n_unique_impulses} x {self.n_unique_lines} rectangle "
                f"({self.n_unique_impulses * self.n_unique_lines} expected points)."
            )
        else:
            lines.append(
                "Does NOT form a clean rectangle — line lengths vary, which usually means "
                "either an interrupted/resumed scan, or more than one scan session ended up "
                "in this export."
            )
        # v0.4.2 (audit F-11): the analysis runs on the built grid, so its
        # shape is reported alongside the raw-column claim above. A clean
        # raw rectangle that the grid does not reproduce is stated plainly
        # instead of letting the rectangle sentence imply grid geometry.
        if self.grid_nx is not None and self.grid_ny is not None:
            lines.append(f"Analysis grid built as {self.grid_nx} x {self.grid_ny} cells.")
            if self.grid_matches_raw_rectangle is False:
                lines.append(
                    "WARNING: the built grid does not reproduce the raw-column "
                    "rectangle above -- geometry figures (distances, areas) come "
                    "from the built grid, not the claimed rectangle."
                )
        return " ".join(lines)


def _grid_shape_match(
    is_rect: bool,
    n_impulses: int | None,
    n_lines: int | None,
    grid_nx: int | None,
    grid_ny: int | None,
) -> bool | None:
    """Whether the built grid reproduces a clean raw-column rectangle claim."""
    if not is_rect or n_impulses is None or n_lines is None:
        return None
    if grid_nx is None or grid_ny is None:
        return None
    return bool(grid_nx == n_impulses and grid_ny == n_lines)


def summarize_geometry(scan: ScanData, grid: Grid2D | None = None) -> GeometrySummary:
    """Summarize export geometry, optionally cross-checked against the grid.

    The raw-column facts keep their meaning (file claims for operator
    comparison). When the built ``grid`` is passed, its shape is recorded
    and checked against a clean raw rectangle claim (audit F-11): callers
    that analyze the grid -- like the pipeline -- must pass it so reports
    cannot imply grid geometry the analysis never saw.
    """
    # Prefer explicit exported grid indices, but fall back to x/y coordinates.
    # Some callers construct ScanData positionally using x/y as the grid, and
    # older fixtures populated grid-like values before the twt_ns field was
    # inserted into the dataclass. Geometry diagnostics should still report
    # the observable line/impulse facts instead of returning an uninformative
    # all-None summary.
    gi = scan.grid_i
    gj = scan.grid_j
    fallback_to_xy = gi is None or gj is None
    if fallback_to_xy:
        gi = scan.x
        gj = scan.y
    if gi is None or gj is None:
        return GeometrySummary(
            n_points=len(scan),
            n_unique_lines=None,
            n_unique_impulses=None,
            points_per_line_min=None,
            points_per_line_max=None,
            points_per_line_median=None,
            is_clean_rectangle=False,
        )

    if fallback_to_xy:
        # x/y are floating-point physical coordinates: cluster them with the
        # same tolerance used by grid reconstruction so harmless coordinate
        # jitter is not misreported as one line/impulse per sample.
        from ..core.grid import cluster_axis_coordinates

        finite_j = ~np.isnan(gj)
        finite_i = ~np.isnan(gi)
        unique_lines, line_labels = cluster_axis_coordinates(np.asarray(gj, dtype=float)[finite_j])
        unique_impulses, _ = cluster_axis_coordinates(np.asarray(gi, dtype=float)[finite_i])
        counts_per_line = [int(c) for c in np.bincount(line_labels, minlength=len(unique_lines))]
    else:
        unique_lines = np.unique(gj[~np.isnan(gj)])
        unique_impulses = np.unique(gi[~np.isnan(gi)])
        counts_per_line = [int(np.sum(gj == line)) for line in unique_lines]
    is_rect = bool(counts_per_line) and all(c == len(unique_impulses) for c in counts_per_line)

    grid_nx = grid_ny = None
    if grid is not None:
        try:
            signal = getattr(grid, "signal", None)
            if signal is None:
                raise TypeError("grid has no signal channel")
            grid_ny, grid_nx = (int(v) for v in np.shape(signal))
        except (TypeError, ValueError):
            grid_nx = grid_ny = None

    return GeometrySummary(
        n_points=len(scan),
        n_unique_lines=len(unique_lines),
        n_unique_impulses=len(unique_impulses),
        points_per_line_min=int(min(counts_per_line)) if counts_per_line else None,
        points_per_line_max=int(max(counts_per_line)) if counts_per_line else None,
        points_per_line_median=float(np.median(counts_per_line)) if counts_per_line else None,
        is_clean_rectangle=is_rect,
        grid_nx=grid_nx,
        grid_ny=grid_ny,
        grid_matches_raw_rectangle=_grid_shape_match(
            is_rect, len(unique_impulses), len(unique_lines), grid_nx, grid_ny
        ),
    )

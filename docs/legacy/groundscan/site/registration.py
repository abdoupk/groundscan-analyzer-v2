"""Robust cross-scan registration with valid-data masks and ambiguity reporting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

REGISTRATION_WEAK_THRESHOLD = 0.50
REGISTRATION_CAUTION_THRESHOLD = 0.70
REGISTRATION_STRONG_OVERLAP_THRESHOLD = 0.70

_TRANSFORMS: list[tuple[str, Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]]]] = [
    ("rot0", lambda a: a),
    ("rot90", lambda a: np.rot90(a, 1)),
    ("rot180", lambda a: np.rot90(a, 2)),
    ("rot270", lambda a: np.rot90(a, 3)),
    ("flip_rot0", lambda a: np.fliplr(a)),
    ("flip_rot90", lambda a: np.rot90(np.fliplr(a), 1)),
    ("flip_rot180", lambda a: np.rot90(np.fliplr(a), 2)),
    ("flip_rot270", lambda a: np.rot90(np.fliplr(a), 3)),
]


@dataclass
class AlignmentResult:
    transform_name: str
    shift_dy: int
    shift_dx: int
    correlation: float
    overlap_fraction: float
    b_resampled: np.ndarray[Any, Any]
    b_valid: np.ndarray[Any, Any]
    second_best_correlation: float = 0.0
    ambiguity_margin: float = 0.0
    multiscale_correlation: float = 0.0
    candidate_count: int = 0

    @property
    def status(self) -> str:
        """Descriptive registration status; not a probability."""
        if self.registration_evidence < REGISTRATION_WEAK_THRESHOLD or self.overlap_fraction < 0.50:
            return "weak"
        if (
            self.registration_evidence < REGISTRATION_CAUTION_THRESHOLD
            or self.overlap_fraction < REGISTRATION_STRONG_OVERLAP_THRESHOLD
        ):
            return "caution"
        return "strong"

    @property
    def status_reason(self) -> str:
        reasons = []
        if self.registration_evidence < REGISTRATION_WEAK_THRESHOLD:
            reasons.append(
                f"registration evidence {self.registration_evidence:.0%} < {REGISTRATION_WEAK_THRESHOLD:.0%}"
            )
        elif self.registration_evidence < REGISTRATION_CAUTION_THRESHOLD:
            reasons.append(
                f"registration evidence {self.registration_evidence:.0%} < {REGISTRATION_CAUTION_THRESHOLD:.0%}"
            )
        if self.overlap_fraction < 0.50:
            reasons.append(f"overlap {self.overlap_fraction:.0%} < 50%")
        elif self.overlap_fraction < REGISTRATION_STRONG_OVERLAP_THRESHOLD:
            reasons.append(
                f"overlap {self.overlap_fraction:.0%} < {REGISTRATION_STRONG_OVERLAP_THRESHOLD:.0%}"
            )
        return (
            "; ".join(reasons)
            if reasons
            else "registration metrics are within the strong-status range"
        )

    @property
    def label(self) -> str:
        return f"{self.transform_name}(dy={self.shift_dy:+d},dx={self.shift_dx:+d})"

    @property
    def registration_evidence(self) -> float:
        """0..1 heuristic registration quality; not a probability."""
        from ..gates.thresholds import registration_evidence_score

        return registration_evidence_score(
            correlation=self.correlation,
            overlap=self.overlap_fraction,
            margin=self.ambiguity_margin / 0.25,
            multiscale=self.multiscale_correlation,
        )


def _resample_to(
    array: np.ndarray[Any, Any], shape: tuple[int, int]
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    valid = np.isfinite(array)
    values = np.nan_to_num(array, nan=0.0)
    zoom_factors = (shape[0] / values.shape[0], shape[1] / values.shape[1])
    resized = ndimage.zoom(values, zoom_factors, order=1)
    mask = ndimage.zoom(valid.astype(float), zoom_factors, order=1) >= 0.5
    resized[~mask] = np.nan
    return resized, mask


def _shift_with_mask(
    values: np.ndarray[Any, Any], valid: np.ndarray[Any, Any], dy: int, dx: int
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Integer-cell shift without interpolation. Faster and exact for registration search."""
    h, w = values.shape
    out = np.full_like(values, np.nan, dtype=float)
    out_mask = np.zeros((h, w), dtype=bool)
    src_y0, src_y1 = max(0, -dy), min(h, h - dy)
    dst_y0, dst_y1 = max(0, dy), min(h, h + dy)
    src_x0, src_x1 = max(0, -dx), min(w, w - dx)
    dst_x0, dst_x1 = max(0, dx), min(w, w + dx)
    if src_y1 <= src_y0 or src_x1 <= src_x0:
        return out, out_mask
    src_values = values[src_y0:src_y1, src_x0:src_x1]
    src_mask = valid[src_y0:src_y1, src_x0:src_x1]
    out[dst_y0:dst_y1, dst_x0:dst_x1] = src_values
    out_mask[dst_y0:dst_y1, dst_x0:dst_x1] = src_mask
    return out, out_mask


def _shift_array_integer(values: np.ndarray[Any, Any], dy: int, dx: int) -> np.ndarray[Any, Any]:
    shifted, _ = _shift_with_mask(values, np.isfinite(values), dy, dx)
    return np.asarray(np.nan_to_num(shifted, nan=0.0), dtype=float)


def _multiscale_maps(array: np.ndarray[Any, Any]) -> list[np.ndarray[Any, Any]]:
    base = np.nan_to_num(array, nan=0.0)
    return [base] + [ndimage.gaussian_filter(base, sigma=sigma) for sigma in (1.0, 2.0, 4.0)]


def _multiscale_correlation_from_maps(
    a_maps: list[np.ndarray[Any, Any]],
    b_maps: list[np.ndarray[Any, Any]],
    valid: np.ndarray[Any, Any],
) -> float:
    """Average correlation over precomputed spatial scales."""
    if int(valid.sum()) < 12:
        return 0.0
    values = [max(0.0, _safe_correlation(aa, bb)) for aa, bb in zip(a_maps, b_maps, strict=True)]
    return float(np.mean(values)) if values else 0.0


def _apply_transform_to_point(
    transform_name: str, row: float, col: float, size: int
) -> tuple[float, float]:
    """Map a normalized/resampled (row,col) point through the same rigid transform as the map."""
    last = float(size - 1)
    name = transform_name
    if name.startswith("flip_"):
        col = last - col
        name = name[5:]
    if name == "rot90":
        row, col = last - col, row
    elif name == "rot180":
        row, col = last - row, last - col
    elif name == "rot270":
        row, col = col, last - row
    return row, col


def map_point_to_aligned(
    x: float,
    y: float,
    source_x: np.ndarray[Any, Any],
    source_y: np.ndarray[Any, Any],
    alignment: AlignmentResult,
) -> tuple[float, float]:
    """Map a source-grid point into the aligned reference array's coordinates."""
    src_x0, src_x1 = float(np.nanmin(source_x)), float(np.nanmax(source_x))
    src_y0, src_y1 = float(np.nanmin(source_y)), float(np.nanmax(source_y))
    size = alignment.b_resampled.shape[0]
    col = (float(x) - src_x0) / max(src_x1 - src_x0, 1e-12) * (size - 1)
    row = (float(y) - src_y0) / max(src_y1 - src_y0, 1e-12) * (size - 1)
    row, col = _apply_transform_to_point(alignment.transform_name, row, col, size)
    return row + alignment.shift_dy, col + alignment.shift_dx


def align_grids(
    zscore_a: np.ndarray[Any, Any],
    zscore_b: np.ndarray[Any, Any],
    resolution: int = 40,
    max_shift: int = 6,
    min_overlap_fraction: float = 0.5,
    orientation_a_deg: float | None = None,
    orientation_b_deg: float | None = None,
    allow_reflections_when_unknown: bool = True,
) -> AlignmentResult:
    """Search rigid transforms + integer cell shifts while respecting valid masks.

    v0.2 also reports the runner-up correlation so a nearly tied alignment can be
    treated as ambiguous instead of being presented as uniquely correct.
    """
    common_shape = (resolution, resolution)
    a, a_mask = _resample_to(zscore_a, common_shape)
    b_base, b_mask_base = _resample_to(zscore_b, common_shape)
    min_overlap_cells = int(min_overlap_fraction * resolution * resolution)

    scored: list[
        tuple[float, float, float, str, int, int, float, np.ndarray[Any, Any], np.ndarray[Any, Any]]
    ] = []
    a_maps = _multiscale_maps(a)
    b_maps_base = _multiscale_maps(b_base)
    transforms = _TRANSFORMS
    if orientation_a_deg is not None and orientation_b_deg is not None:
        delta = (float(orientation_b_deg) - float(orientation_a_deg)) % 180.0
        if min(delta, 180.0 - delta) < 22.5:
            allowed = {"rot0", "rot180"}
        elif abs(delta - 90.0) < 22.5:
            allowed = {"rot90", "rot270"}
        else:
            allowed = {"rot0", "rot90", "rot180", "rot270"}
        transforms = [(n, f) for n, f in _TRANSFORMS if n in allowed]
    elif not allow_reflections_when_unknown:
        transforms = [(n, f) for n, f in _TRANSFORMS if not n.startswith("flip_")]
    for name, transform in transforms:
        b_t = transform(b_base)
        mask_t = transform(b_mask_base)
        b_maps_t = [transform(m) for m in b_maps_base]
        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                b_s, mask_s = _shift_with_mask(b_t, mask_t, dy, dx)
                valid = a_mask & mask_s & np.isfinite(a) & np.isfinite(b_s)
                if int(valid.sum()) < min_overlap_cells:
                    continue
                av, bv = a[valid], b_s[valid]
                correlation = _safe_correlation(av, bv)
                overlap = valid.sum() / float(resolution * resolution)
                # Integer shifts preserve exact cell correspondence; no interpolation needed.
                shifted_scale_maps = [_shift_array_integer(m, dy, dx) for m in b_maps_t]
                multiscale = _multiscale_correlation_from_maps(
                    [m[valid] for m in a_maps],
                    [m[valid] for m in shifted_scale_maps],
                    np.ones(int(valid.sum()), dtype=bool),
                )
                score = 0.55 * correlation + 0.45 * multiscale
                scored.append((
                    score,
                    correlation,
                    multiscale,
                    name,
                    dy,
                    dx,
                    float(overlap),
                    b_s,
                    mask_s,
                ))

    if not scored:
        b_s, mask_s = _shift_with_mask(b_base, b_mask_base, 0, 0)
        valid = a_mask & mask_s & np.isfinite(a) & np.isfinite(b_s)
        correlation = _safe_correlation(a[valid], b_s[valid]) if int(valid.sum()) >= 3 else 0.0
        return AlignmentResult(
            transform_name="rot0",
            shift_dy=0,
            shift_dx=0,
            correlation=correlation,
            overlap_fraction=float(np.mean(valid)),
            b_resampled=b_s,
            b_valid=mask_s,
        )

    # Rank by composite score, then prefer the smallest displacement. Python's
    # sort is stable, so without this tiebreak a flat (zero-correlation) surface
    # resolved to the first candidate enumerated -- (-max_shift, -max_shift) --
    # and displaced the scan by twelve cells on both axes. Ties now resolve to
    # the origin, which is the only shift that is defensible when the data
    # cannot distinguish the candidates.
    scored.sort(key=lambda row: (row[0], -abs(row[4]) - abs(row[5])), reverse=True)
    best = scored[0]
    # second-best and margin are reported in raw Pearson-correlation units
    # (comparable with `correlation`), not in composite-score units: the
    # ranking score blends correlation with multiscale structure, but the
    # ambiguity contract is "how much worse is the runner-up correlation".
    # Runner-up is the best correlation among strictly different transforms
    # (same-transform ±1-cell shifts are the same alignment, not ambiguity).
    runner_ups = [row for row in scored[1:] if row[3] != best[3]]
    runner = max(runner_ups, key=lambda row: row[1]) if runner_ups else None
    second_corr = float(runner[1]) if runner is not None else float(best[1])
    margin = float(best[1]) - second_corr
    return AlignmentResult(
        transform_name=best[3],
        shift_dy=best[4],
        shift_dx=best[5],
        correlation=float(best[1]),
        overlap_fraction=float(best[6]),
        b_resampled=best[7],
        b_valid=best[8],
        second_best_correlation=second_corr,
        ambiguity_margin=float(max(margin, 0.0)),
        multiscale_correlation=float(best[2]),
        candidate_count=len(scored),
    )


def _safe_correlation(a: np.ndarray[Any, Any], b: np.ndarray[Any, Any]) -> float:
    if a.size < 3 or b.size < 3:
        return 0.0
    valid = np.isfinite(a) & np.isfinite(b)
    a, b = a[valid], b[valid]
    if a.size < 3 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    value = float(np.corrcoef(a, b)[0, 1])
    return value if np.isfinite(value) else 0.0

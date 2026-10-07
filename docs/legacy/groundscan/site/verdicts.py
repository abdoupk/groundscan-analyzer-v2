"""Repeatability gates for fused site candidates.

Duplicate-acquisition detection, the two-scan support gate, and the
conservative repeatability prune. Polarity-conflict verdicts live in
:mod:`groundscan.site.conflict_verdicts` behind their own interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from ..models import Candidate, ScanData
from .consensus import _normalized_dims, _reference_xy_from_aligned_point, _scan_extent
from .registration import AlignmentResult, map_point_to_aligned

if TYPE_CHECKING:
    from .analyze_site import ScanObservation


def _candidate_observation_point(
    candidate: Candidate,
    obs: ScanObservation,
    reference: ScanObservation,
    alignment: AlignmentResult | None,
    resolution: int,
) -> tuple[float, float, float]:
    if alignment is None:
        x0, x1, y0, y1 = _scan_extent(reference.grid)
        sx0, sx1, sy0, sy1 = _scan_extent(obs.grid)
        u = (candidate.x_center - sx0) / max(sx1 - sx0, 1e-9)
        v = (candidate.y_center - sy0) / max(sy1 - sy0, 1e-9)
        return (
            float(np.clip(u, 0, 1)),
            float(np.clip(v, 0, 1)),
            max(*_normalized_dims(candidate, obs.grid)),
        )
    row, col = map_point_to_aligned(
        candidate.x_center, candidate.y_center, obs.grid.x_centers, obs.grid.y_centers, alignment
    )
    x, y = _reference_xy_from_aligned_point(row, col, reference.grid, resolution)
    rx0, rx1, ry0, ry1 = _scan_extent(reference.grid)
    return (
        float(np.clip((x - rx0) / max(rx1 - rx0, 1e-9), 0, 1)),
        float(np.clip((y - ry0) / max(ry1 - ry0, 1e-9), 0, 1)),
        max(*_normalized_dims(candidate, obs.grid)),
    )


def _majority(values: list[str]) -> str:
    """Return the most frequent value with deterministic first-seen tie-breaking."""
    if not values:
        return "unknown"
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, value in enumerate(values):
        counts[value] = counts.get(value, 0) + 1
        first_seen.setdefault(value, index)
    return max(counts, key=lambda value: (counts[value], -first_seen[value]))


def _scans_content_identical(a: ScanData, b: ScanData) -> bool:
    """True when two scans carry the same measurement content.

    v0.4.2 (audit F-02): row order is normalized first, so a re-exported file
    with permuted rows is still recognized as the same acquisition. The
    comparison is deliberately strict (coordinates to 1e-9, values to ~1e-9
    relative), so only true duplicates group together; genuinely re-acquired
    scans always differ by measurement noise.
    """
    if len(a) != len(b):
        return False

    def _sorted(
        scan: ScanData,
    ) -> tuple[
        np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]
    ]:
        xk = np.nan_to_num(np.asarray(scan.x, dtype=float), nan=0.0)
        yk = np.nan_to_num(np.asarray(scan.y, dtype=float), nan=0.0)
        zk = np.nan_to_num(np.asarray(scan.z, dtype=float), nan=0.0)
        order = np.lexsort((zk, yk, xk))
        return (
            np.asarray(scan.x, dtype=float)[order],
            np.asarray(scan.y, dtype=float)[order],
            np.asarray(scan.z, dtype=float)[order],
            np.asarray(scan.signal, dtype=float)[order],
        )

    ax, ay, az, asg = _sorted(a)
    bx, by, bz, bsg = _sorted(b)
    if not (
        np.allclose(ax, bx, rtol=0.0, atol=1e-9, equal_nan=True)
        and np.allclose(ay, by, rtol=0.0, atol=1e-9, equal_nan=True)
    ):
        return False
    return np.allclose(az, bz, rtol=1e-9, atol=1e-9, equal_nan=True) and np.allclose(
        asg, bsg, rtol=1e-9, atol=1e-9, equal_nan=True
    )


def _duplicate_scan_groups(observations: list[ScanObservation]) -> list[list[str]]:
    """Group observation labels whose scans carry identical measurement content.

    v0.4.2 (audit F-02): duplicate exports of one acquisition must not be
    counted as independent cross-scan confirmation. Each group lists labels in
    input order; the first member is the fusion representative.
    """
    groups: list[list[str]] = []
    representatives: list[ScanObservation] = []
    for obs in observations:
        for index, rep in enumerate(representatives):
            if _scans_content_identical(rep.scan, obs.scan):
                groups[index].append(obs.label)
                break
        else:
            representatives.append(obs)
            groups.append([obs.label])
    return groups


def _retain_repeatable_fused_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Keep only site-level candidates supported by at least two scans."""
    kept = [c for c in candidates if int(getattr(c, "scan_count", 1)) >= 2]
    for idx, candidate in enumerate(kept, 1):
        candidate.id = idx
    return kept


def _prune_repeatability_fused_candidates(
    candidates: list[Candidate],
    *,
    min_detection_rate: float = 0.75,
    min_cross_scan_agreement: float = 0.63,
    min_registration_consistency: float = 0.60,
    spatial_radius_m: float = 2.5,
) -> list[Candidate]:
    """Conservatively prune over-generated fused candidates.

    This is intentionally a post-fusion gate, not a detector change. It uses
    only cross-scan evidence already computed by the fusion layer. Spatial
    non-maximum suppression is used only when candidate geometry is metric.
    """
    kept: list[Candidate] = []
    for c in candidates:
        detection_rate = float(getattr(c, "detection_rate", 0.0) or 0.0)
        agreement = getattr(c, "cross_scan_agreement", None)
        agreement = float(agreement) if agreement is not None else 0.0
        registration = float(getattr(c, "registration_consistency", 0.0) or 0.0)
        if (
            detection_rate >= min_detection_rate
            and agreement >= min_cross_scan_agreement
            and registration >= min_registration_consistency
        ):
            kept.append(c)

    metric_reliable = all(bool(getattr(c, "metric_geometry_reliable", False)) for c in kept)
    if metric_reliable and spatial_radius_m > 0 and len(kept) > 1:
        selected: list[Candidate] = []
        for c in sorted(
            kept,
            key=lambda x: (
                float(getattr(x, "evidence_score", 0.0)),
                float(getattr(x, "quality_score", 0.0)),
            ),
            reverse=True,
        ):
            too_close = any(
                float(
                    np.hypot(
                        float(c.x_center) - float(k.x_center), float(c.y_center) - float(k.y_center)
                    )
                )
                <= spatial_radius_m
                for k in selected
            )
            if not too_close:
                selected.append(c)
        kept = selected

    for idx, candidate in enumerate(kept, 1):
        candidate.id = idx
        candidate.notes = (
            (candidate.notes + "; " if candidate.notes else "")
            + "conservative repeatability gate applied after cross-scan fusion; metric NMS="
            + ("on" if metric_reliable else "off")
            + "."
        )
    return kept

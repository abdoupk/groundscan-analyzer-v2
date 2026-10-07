"""Diagnostic attach helpers for target separation (split from separation.py).

Diagnostic-only: these functions never change the candidate set. They expose
possible fused responses that the peak-separation stage cannot safely split.
Imports seed ROI helper from separation_seeds (no import from separation.py).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..models import Candidate
from .separation_seeds import _patch_for_candidate


def _unresolved_overlap_diagnostic(
    field: np.ndarray[Any, Any], mask: np.ndarray[Any, Any], *, min_distance: int
) -> tuple[float, float, str]:
    """Estimate a strong secondary shoulder after suppressing the primary peak.

    Diagnostic only: this function never changes the candidate set. It exists to
    expose possible fused responses that the current peak-separation stage cannot
    safely split into independently supported components.
    """
    work = np.where(mask & np.isfinite(field), np.asarray(field, dtype=float), 0.0)
    peak = float(np.max(work)) if work.size else 0.0
    if peak <= 0:
        return 0.0, float("nan"), ""
    idx = int(np.argmax(work))
    r, c = np.unravel_index(idx, work.shape)
    radius = max(1, int(round(max(min_distance, 1) * 0.70)))
    yy, xx = np.ogrid[: work.shape[0], : work.shape[1]]
    residual = work.copy()
    residual[((yy - r) ** 2 + (xx - c) ** 2) <= radius * radius] = 0.0
    second = float(np.max(residual)) if residual.size else 0.0
    if second <= 0:
        return 0.0, float("nan"), ""
    sidx = int(np.argmax(residual))
    sr, sc = np.unravel_index(sidx, residual.shape)
    distance = float(math.hypot(sr - r, sc - c))
    ratio = second / max(peak, 1e-9)
    if distance < max(2.0, 0.85 * max(min_distance, 1)) or ratio < 0.30:
        return 0.0, distance, ""
    # Prefer a high shoulder ratio and a clearly separated secondary location.
    score = float(
        np.clip(0.65 * ratio + 0.35 * min(distance / (2.0 * max(min_distance, 1)), 1.0), 0.0, 1.0)
    )
    reason = "strong secondary response shoulder remains after primary-peak suppression"
    return round(score, 3), distance, reason


def _attach_unresolved_overlap_diagnostic(
    candidate: Candidate,
    *,
    pos_field: np.ndarray[Any, Any],
    neg_field: np.ndarray[Any, Any],
    local_mask: np.ndarray[Any, Any],
    min_distance: int,
) -> Candidate:
    """Attach overlap diagnostics to an unchanged candidate."""
    pos_score, pos_dist, pos_reason = _unresolved_overlap_diagnostic(
        pos_field, local_mask & (pos_field > 0), min_distance=min_distance
    )
    neg_score, neg_dist, neg_reason = _unresolved_overlap_diagnostic(
        neg_field, local_mask & (neg_field > 0), min_distance=min_distance
    )
    if pos_score >= neg_score:
        score, dist, reason = pos_score, pos_dist, pos_reason
    else:
        score, dist, reason = neg_score, neg_dist, neg_reason
    # Pure transform (M3): the input candidate is never mutated.
    quality_flags = list(candidate.quality_flags or [])
    notes = candidate.notes or ""
    if score >= 0.55:
        flag = "possible-unresolved-overlap"
        if flag not in quality_flags:
            quality_flags = quality_flags + [flag]
        note = f"possible unresolved overlap (score {score:.2f}, separation {dist:.1f}px); diagnostic only"
        if note not in notes:
            notes = ((notes + "; ") if notes else "") + note
    return candidate.with_updates(
        unresolved_overlap_score=float(score),
        unresolved_overlap_distance_px=(
            float(dist) if math.isfinite(float(dist)) else float("nan")
        ),
        unresolved_overlap_reason=str(reason),
        quality_flags=quality_flags,
        notes=notes,
    )


def diagnose_undersegmentation(
    candidates: list[Candidate],
    consensus_support: np.ndarray[Any, Any] | None,
    consensus_signed: np.ndarray[Any, Any] | None,
    reference_x: np.ndarray[Any, Any],
    reference_y: np.ndarray[Any, Any],
    *,
    depth_grid: np.ndarray[Any, Any] | None = None,
    min_distance_px: int = 3,
) -> list[Candidate]:
    """Attach selective under-segmentation diagnostics to final candidates.

    This pass intentionally runs after response merging/classification. It records
    possible same-sign multi-peak structure that survived the production pipeline,
    without changing the candidate set, scores, screening, or response family.
    """
    if not candidates or consensus_support is None:
        return candidates
    support = np.nan_to_num(np.asarray(consensus_support, dtype=float), nan=0.0)
    signed = np.nan_to_num(
        np.asarray(
            consensus_signed if consensus_signed is not None else np.zeros_like(support),
            dtype=float,
        ),
        nan=0.0,
    )
    if support.ndim != 2 or signed.shape != support.shape:
        return candidates
    peak = float(np.max(np.abs(signed))) if signed.size else 0.0
    if peak <= 0:
        return candidates
    pos = np.clip(signed, 0.0, None)
    neg = np.clip(-signed, 0.0, None)
    x = np.asarray(reference_x, dtype=float)
    y = np.asarray(reference_y, dtype=float)
    site_width = float(np.nanmax(x) - np.nanmin(x)) if x.size else 1.0
    site_height = float(np.nanmax(y) - np.nanmin(y)) if y.size else 1.0
    x0 = float(np.nanmin(x)) if x.size else 0.0
    y0 = float(np.nanmin(y)) if y.size else 0.0
    out: list[Candidate] = []
    for candidate in candidates:
        # A merged bipolar response is intentionally excluded: its two lobes are
        # expected by design, so a same-sign shoulder is not evidence for a second
        # independent target.
        if (
            candidate.response_family == "dipolar-response"
            or candidate.separation_status == "merged-dipole"
        ):
            out.append(candidate)
            continue
        rs, cs = _patch_for_candidate(
            candidate,
            field_shape=(support.shape[0], support.shape[1]),
            x0=x0,
            y0=y0,
            site_width=site_width,
            site_height=site_height,
        )
        local_support = support[rs, cs]
        local_mask = local_support >= 0.28
        depth_patch = None
        if depth_grid is not None and np.shape(depth_grid) == support.shape:
            depth_patch = np.asarray(depth_grid)[rs, cs]
        # Explicit data flow (M3): the attach helper is pure, so the
        # diagnosed copy replaces the input in the output list.
        out.append(
            _attach_undersegmentation_diagnostic(
                candidate,
                pos_field=pos[rs, cs],
                neg_field=neg[rs, cs],
                local_mask=local_mask,
                min_distance=max(int(min_distance_px), 3),
                depth_field=depth_patch,
            )
        )
    return out


def _undersegmentation_diagnostic(
    field: np.ndarray[Any, Any],
    mask: np.ndarray[Any, Any],
    *,
    min_distance: int,
    depth_field: np.ndarray[Any, Any] | None = None,
) -> dict[str, Any]:
    """Describe a plausible second same-sign peak inside an unsplit parent.

    Diagnostic-only: no candidate splitting or scoring change is performed. The
    secondary location is found after suppressing a compact disk around the
    strongest peak, which is intentionally less permissive than changing the
    production seed threshold.
    """
    work = np.where(mask & np.isfinite(field), np.asarray(field, dtype=float), 0.0)
    peak = float(np.max(work)) if work.size else 0.0
    if peak <= 0.0:
        return {
            "score": 0.0,
            "peak_count": 0,
            "ratio": 0.0,
            "distance": float("nan"),
            "depth_delta": float("nan"),
            "reason": "",
            "channel": "",
        }
    idx = int(np.argmax(work))
    # Plain ints: unravel_index yields numpy integers, which are not valid
    # static slice bounds once the arrays carry precise ndarray types.
    _r, _c = np.unravel_index(idx, work.shape)
    r, c = int(_r), int(_c)
    radius = max(1, int(round(max(int(min_distance), 2) * 0.70)))
    yy, xx = np.ogrid[: work.shape[0], : work.shape[1]]
    residual = work.copy()
    residual[((yy - r) ** 2 + (xx - c) ** 2) <= radius * radius] = 0.0
    second = float(np.max(residual)) if residual.size else 0.0
    if second <= 0.0:
        return {
            "score": 0.0,
            "peak_count": 1,
            "ratio": 0.0,
            "distance": float("nan"),
            "depth_delta": float("nan"),
            "reason": "",
            "channel": "",
        }
    sidx = int(np.argmax(residual))
    _sr, _sc = np.unravel_index(sidx, residual.shape)
    sr, sc = int(_sr), int(_sc)
    distance = float(math.hypot(sr - r, sc - c))
    ratio = float(second / max(peak, 1e-9))
    if ratio < 0.30 or distance < max(2.0, 0.75 * max(int(min_distance), 2)):
        return {
            "score": 0.0,
            "peak_count": 1,
            "ratio": ratio,
            "distance": distance,
            "depth_delta": float("nan"),
            "reason": "",
            "channel": "",
        }

    depth_delta = float("nan")
    if depth_field is not None and np.shape(depth_field) == np.shape(work):
        depths = []
        for pr, pc in ((r, c), (sr, sc)):
            r0 = max(0, pr - 1)
            r1 = min(work.shape[0], pr + 2)
            c0 = max(0, pc - 1)
            c1 = min(work.shape[1], pc + 2)
            patch = np.asarray(depth_field[r0:r1, c0:c1], dtype=float)
            finite = patch[np.isfinite(patch)]
            depths.append(float(np.median(finite)) if finite.size else float("nan"))
        if all(np.isfinite(v) for v in depths):
            depth_delta = abs(depths[0] - depths[1])

    ratio_factor = float(np.clip((ratio - 0.30) / 0.45, 0.0, 1.0))
    distance_factor = float(np.clip(distance / (2.0 * max(int(min_distance), 2)), 0.0, 1.0))
    depth_factor = float(np.clip(depth_delta / 3.0, 0.0, 1.0)) if np.isfinite(depth_delta) else 0.0
    score = float(
        np.clip(0.68 * ratio_factor + 0.22 * distance_factor + 0.10 * depth_factor, 0.0, 1.0)
    )
    reason = "secondary same-sign peak remains after primary-peak suppression"
    if np.isfinite(depth_delta) and depth_delta >= 0.75:
        reason += "; distinct local depth layer may support later 3D deblending"
    return {
        "score": round(score, 3),
        "peak_count": 2,
        "ratio": round(ratio, 3),
        "distance": distance,
        "depth_delta": depth_delta,
        "reason": reason,
        "channel": "same-sign",
    }


def _attach_undersegmentation_diagnostic(
    candidate: Candidate,
    *,
    pos_field: np.ndarray[Any, Any],
    neg_field: np.ndarray[Any, Any],
    local_mask: np.ndarray[Any, Any],
    min_distance: int,
    depth_field: np.ndarray[Any, Any] | None = None,
) -> Candidate:
    """Attach a selective under-segmentation diagnostic to an unchanged parent."""
    # Diagnostic scope: broad-response geology and a strongly supported linear
    # tunnel commonly produce benign shoulders, so do not label them as targets.
    if candidate.response_family in ("broad-response", "dipolar-response"):
        return candidate
    if candidate.pattern_hypothesis == "geological-like":
        return candidate
    if (
        candidate.pattern_hypothesis == "tunnel-like"
        and candidate.line_support_score >= 0.80
        and candidate.axial_signal_continuity_score >= 0.90
    ):
        return candidate
    if candidate.artifact_score >= 0.55 or candidate.anomaly_score < 3.5:
        return candidate

    pos = _undersegmentation_diagnostic(
        pos_field, local_mask & (pos_field > 0), min_distance=min_distance, depth_field=depth_field
    )
    neg = _undersegmentation_diagnostic(
        neg_field, local_mask & (neg_field > 0), min_distance=min_distance, depth_field=depth_field
    )
    best = pos if float(pos.get("score", 0.0)) >= float(neg.get("score", 0.0)) else neg
    score = float(best.get("score", 0.0) or 0.0)
    # Broadness is a weak prior only: it raises diagnostic visibility but does not
    # influence production candidate scoring or screening.
    broad_prior = float(np.clip(0.65 + 0.35 * candidate.broadness_score, 0.65, 1.0))
    score = float(np.clip(score * broad_prior, 0.0, 1.0))
    # Pure transform (M3): compute every diagnostic into locals, then return
    # one copy. The input candidate is never mutated.
    peak_count = int(best.get("peak_count", 0) or 0)
    peak_ratio = float(best.get("ratio", 0.0) or 0.0)
    dist = best.get("distance", float("nan"))
    dd = best.get("depth_delta", float("nan"))
    distance_px = float(dist) if dist is not None and math.isfinite(float(dist)) else float("nan")
    depth_delta_m = float(dd) if dd is not None and math.isfinite(float(dd)) else float("nan")
    depth_layer_supported = bool(math.isfinite(depth_delta_m) and depth_delta_m >= 0.75)
    quality_flags = list(candidate.quality_flags or [])
    notes = candidate.notes or ""
    if score >= 0.58 and peak_count >= 2 and depth_layer_supported:
        flag = "possible-undersegmentation"
        if flag not in quality_flags:
            quality_flags = quality_flags + [flag]
        note = (
            f"possible under-segmentation (score {score:.2f}, secondary/primary ratio "
            f"{peak_ratio:.2f}, separation "
            f"{distance_px:.1f}px, depth-layer delta "
            f"{depth_delta_m:.2f}m); diagnostic only"
        )
        if note not in notes:
            notes = ((notes + "; ") if notes else "") + note
    return candidate.with_updates(
        undersegmentation_score=score,
        undersegmentation_peak_count=peak_count,
        undersegmentation_peak_ratio=peak_ratio,
        undersegmentation_distance_px=distance_px,
        undersegmentation_depth_delta_m=depth_delta_m,
        undersegmentation_depth_layer_supported=depth_layer_supported,
        undersegmentation_channel=str(best.get("channel", "")),
        undersegmentation_reason=str(best.get("reason", "")),
        quality_flags=quality_flags,
        notes=notes,
    )


def _clone_with_diagnostics(
    parent: Candidate,
    next_id: int,
    *,
    pos_field: np.ndarray[Any, Any],
    neg_field: np.ndarray[Any, Any],
    local_mask: np.ndarray[Any, Any],
    min_distance: int,
    depth_patch: np.ndarray[Any, Any] | None = None,
) -> Candidate:
    """Clone *parent* with a fresh id + unresolved-overlap/undersegmentation diagnostics.

    v0.5.1: single helper for the four early-exit paths in
    :func:`separate_fused_candidates` that previously copy-pasted the
    clone + attach + id-bump sequence. Behavior is identical.
    """
    from dataclasses import replace

    cloned = replace(parent, id=next_id)
    cloned = _attach_unresolved_overlap_diagnostic(
        cloned,
        pos_field=pos_field,
        neg_field=neg_field,
        local_mask=local_mask,
        min_distance=min_distance,
    )
    return _attach_undersegmentation_diagnostic(
        cloned,
        pos_field=pos_field,
        neg_field=neg_field,
        local_mask=local_mask,
        min_distance=min_distance,
        depth_field=depth_patch,
    )


__all__ = [
    "_unresolved_overlap_diagnostic",
    "_attach_unresolved_overlap_diagnostic",
    "diagnose_undersegmentation",
    "_undersegmentation_diagnostic",
    "_attach_undersegmentation_diagnostic",
    "_clone_with_diagnostics",
]

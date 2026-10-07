"""Dipolar response merging and multi-target deblending.

Split from ``groundscan.analysis.realworld``: this module holds the
conservative opposite-sign lobe pairing logic (:func:`merge_dipolar_response_components`,
:func:`deblend_spatially_separated_multitarget_pairs` and
:class:`DipoleMergeConfig`). Scan-quality acquisition diagnostics live in
:mod:`groundscan.diagnostics.quality_probe`.

The heuristics are deliberately generic (no vendor/device names or rules).
Merging/deblending describes the signed response geometry only; it never
proves physical objects or material identity.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from scipy import ndimage

from ..models import Candidate


def union_mask_metrics(
    cells_a: tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]] | None,
    cells_b: tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]] | None,
    *,
    field_shape: tuple[int, int] | None = None,
) -> dict[str, float] | None:
    """Compactness and solidity of the **union** of two fragment cell sets.

    A merged dipole's morphology should describe the shape the two lobes form
    together, not an average of the shapes they form separately. Per-lobe
    averaging is inconsistent with the rest of the merge: ``width`` / ``height`` /
    ``major_extent`` / ``minor_extent`` / ``aspect_ratio`` / ``linearity_score`` are
    already derived from the union bounding box, and ``area_cells`` is already the
    sum, while ``compactness`` / ``solidity`` / ``geometry_quality`` were averaged
    over the lobes. This function supplies the cell-level union for the latter
    three.

    Both estimators are the production ones, applied to the union mask:

    * ``compactness`` -- ``_util.digital_compactness`` over the erosion
      boundary-cell count, so the value stays on the same (proxy) scale every
      other ``Candidate.compactness`` is on. Using a different estimator here
      would make the merged value incomparable with every other candidate in the
      payload, which is a worse defect than the one being fixed.
    * ``solidity`` -- ``core.shape._convex_hull_solidity``, so the union's
      dimensionless ratio is used rather than ``min`` of the two lobes.

    Returns ``None`` when either cell set is empty, or when the two sets fall
    outside the field, so a caller can fall back rather than fabricate a value. An
    empty set is treated as a failure rather than as a neutral element: a lobe with
    no recorded cells means the record is incomplete, and silently reporting the
    *other* lobe's metrics as the pair's union would understate how spread out the
    pair is.
    """
    if cells_a is None or cells_b is None:
        return None
    rows_a = np.asarray(cells_a[0], dtype=int)
    cols_a = np.asarray(cells_a[1], dtype=int)
    rows_b = np.asarray(cells_b[0], dtype=int)
    cols_b = np.asarray(cells_b[1], dtype=int)
    if rows_a.size == 0 or cols_a.size == 0 or rows_b.size == 0 or cols_b.size == 0:
        return None
    rows = np.concatenate([rows_a, rows_b])
    cols = np.concatenate([cols_a, cols_b])
    if field_shape is not None:
        # Drop cells outside the field rather than only clamping the bounding box,
        # so a fragment on the last row cannot both index past the mask and
        # inflate it.
        n_rows, n_cols = int(field_shape[0]), int(field_shape[1])
        if n_rows <= 0 or n_cols <= 0:
            return None
        in_field = (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
        rows, cols = rows[in_field], cols[in_field]
        if rows.size == 0:
            return None
    r0, r1 = int(rows.min()), int(rows.max())
    c0, c1 = int(cols.min()), int(cols.max())
    height, width = r1 - r0 + 1, c1 - c0 + 1
    if height <= 0 or width <= 0:
        return None
    mask = np.zeros((height, width), dtype=bool)
    mask[rows - r0, cols - c0] = True
    n_cells = int(np.count_nonzero(mask))
    if n_cells == 0:
        return None

    from .._util import digital_compactness

    eroded = ndimage.binary_erosion(mask)
    perimeter = float(np.count_nonzero(mask & ~eroded))
    compactness = digital_compactness(float(n_cells), perimeter)

    from ..core.shape import _convex_hull_solidity

    ys, xs = np.nonzero(mask)
    # The union is a cell set, so its solidity needs only the pitch -- and by the
    # S02 algebra the pitch cancels, so a unit pitch is the dimensionless answer.
    solidity = float(_convex_hull_solidity(xs.astype(float), ys.astype(float), 1.0, 1.0))
    bbox_area = float(height * width)
    return {
        "compactness": float(compactness),
        "solidity": solidity,
        "area_cells": float(n_cells),
        "bbox_area": bbox_area,
        "fill": n_cells / bbox_area,
        "boundary_contact_ratio": 0.0,
    }


def _union_geometry_quality(
    union: Mapping[str, float],
    *,
    n_cells: float,
    boundary_contact_ratio: float,
) -> float:
    """``geometry_quality`` recomputed on the union mask.

    The formula is the production one from ``core.shape._shape_metrics`` -- same
    four terms, same order -- with the solidity term applied to the union's own
    solidity rather than to the lobes' weighted average.

    The weights are duplicated here rather than imported because
    ``core.shape._shape_metrics`` writes them as inline literals at their
    comparison site and does not name them (recorded as an open issue). The
    duplication is deliberate and temporary; a drift guard
    (``tests/unit/test_dipole_union_metrics.py``) pins these five values against
    the literals in ``core.shape`` so the two copies cannot diverge silently while
    the literals are still unnamed.
    """
    value = (
        0.30 * min(n_cells / _GEOMETRY_QUALITY_CELL_SATURATION, 1.0)
        + 0.25 * min(float(union["fill"]), 1.0)
        + 0.25 * float(union["solidity"])
        + 0.20 * (1.0 - min(float(boundary_contact_ratio), 1.0))
    )
    return float(min(1.0, max(0.0, value)))


#: The cell count at which ``geometry_quality``'s first term saturates, mirroring
#: the ``/ 10.0`` literal in ``core.shape._shape_metrics``.
_GEOMETRY_QUALITY_CELL_SATURATION = 10.0


def _lobe_cells(
    candidate: Candidate,
    fragment_cells: Mapping[int, tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]] | None,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]] | None:
    """Look up a fragment's recorded cells, or ``None`` when unavailable.

    A fragment's ids are the ``response_component_ids`` it reports, which is what
    the merge unions into the merged candidate's own list. Keying on the candidate
    id as well covers a fragment that never declared component ids.
    """
    if not fragment_cells:
        return None
    for key in (int(candidate.id), *(int(v) for v in (candidate.response_component_ids or []))):
        cells = fragment_cells.get(key)
        if cells is not None:
            return cells
    return None


@dataclass(frozen=True)
class DipoleMergeConfig:
    """Conservative controls for pairing opposite-sign response lobes."""

    min_peak: float = 4.0
    min_peak_balance: float = 0.40
    max_artifact: float = 0.55
    max_boundary_contact: float = 0.75
    max_distance_ratio: float = 0.70
    min_pair_score: float = 0.62
    require_shared_parent: bool = True
    protect_linear_metal_cavity_pair: bool = True
    # v0.2.44: do not merge opposite-sign lobes when their independent depth
    # estimates are materially inconsistent. This is a deblending safeguard,
    # not proof that two lobes are two physical objects.
    max_depth_delta_for_dipole_merge_m: float = 3.0


DEFAULT_DIPOLE_MERGE_CONFIG = DipoleMergeConfig()


def _candidate_distance(a: Candidate, b: Candidate) -> float:
    return math.hypot(float(a.x_center - b.x_center), float(a.y_center - b.y_center))


@dataclass(frozen=True)
class DipolePairAssessment:
    """Pure scorer result for one opposite-sign lobe pair.

    ``blocked_reason`` carries the note text for the two loud guards (depth
    inconsistency, spatial separation); it is None on success and on silent
    rejections. The scorer never mutates candidates -- callers write notes.
    """

    pair_score: float
    peak_balance: float
    lobe_distance: float
    blocked_reason: str | None = None


def _dipole_pair_metrics(
    a: Candidate,
    b: Candidate,
    config: DipoleMergeConfig | None = None,
) -> DipolePairAssessment | None:
    """Assess a conservative dipole pair without mutating either candidate."""
    config = config or DEFAULT_DIPOLE_MERGE_CONFIG
    if {a.polarity, b.polarity} != {"positive", "negative"}:
        return None
    if max(a.artifact_score, b.artifact_score) >= config.max_artifact:
        return None
    if max(a.boundary_contact_ratio, b.boundary_contact_ratio) >= config.max_boundary_contact:
        return None
    if config.require_shared_parent and (
        a.separation_parent_id is None or a.separation_parent_id != b.separation_parent_id
    ):
        return None

    # v0.2.42 multi-target guard: a structured positive linear response adjacent
    # to a cavity-like negative response is a known ambiguity in synthetic
    # multi-target fixtures. Do not collapse the two into one dipole when the
    # positive lobe already carries strong linear-metal morphology evidence.
    # This preserves the generic dipole merger for ordinary bipolar responses.
    # v0.2.44 deblending safeguard: a large lobe-to-lobe depth mismatch
    # is inconsistent with the ordinary dipole pairing model. Keep the lobes
    # separate rather than forcing a dipolar merge. Missing/non-finite depth
    # does not block a merge, preserving legacy behavior when depth is absent.
    depth_delta = None
    if math.isfinite(float(a.depth_estimate)) and math.isfinite(float(b.depth_estimate)):
        depth_delta = abs(float(a.depth_estimate) - float(b.depth_estimate))
        if depth_delta > float(config.max_depth_delta_for_dipole_merge_m):
            return DipolePairAssessment(
                pair_score=0.0,
                peak_balance=0.0,
                lobe_distance=_candidate_distance(a, b),
                blocked_reason=(
                    f"dipole merge blocked by depth inconsistency (lobe depth delta "
                    f"{depth_delta:.2f} m > {float(config.max_depth_delta_for_dipole_merge_m):.2f} m); "
                    "deblending safeguard, not physical-object proof"
                ),
            )

    # v0.2.49: protect clearly separated opposite-sign lobes from being
    # collapsed back into one dipole when they originated from the same
    # multi-scan parent. This is deliberately conservative and only applies
    # to decomposed multi-scan fragments with metric geometry.
    if (
        a.separation_parent_id is not None
        and a.separation_parent_id == b.separation_parent_id
        and a.separation_status == "decomposed-consensus"
        and b.separation_status == "decomposed-consensus"
        and min(int(a.scan_count), int(b.scan_count)) >= 2
        and bool(a.metric_geometry_reliable and b.metric_geometry_reliable)
    ):
        spatial_distance = _candidate_distance(a, b)
        if spatial_distance >= 1.50:
            return DipolePairAssessment(
                pair_score=0.0,
                peak_balance=0.0,
                lobe_distance=spatial_distance,
                blocked_reason=(
                    f"dipole merge blocked by spatially separated multi-target guard "
                    f"(lobe distance {spatial_distance:.2f} m >= 1.50 m); "
                    "response deblending hypothesis, not physical-object proof"
                ),
            )

    if config.protect_linear_metal_cavity_pair:
        patterns = {a.pattern_hypothesis, b.pattern_hypothesis}
        if patterns == {"linear-metal-compatible", "cavity-like"}:
            positive = a if a.pattern_hypothesis == "linear-metal-compatible" else b
            if (
                float(positive.linearity_score) >= 0.40
                and float(positive.line_support_score) >= 0.70
                and float(positive.morphology_line_coherence_score) >= 0.40
            ):
                return None

    pos = a if a.polarity == "positive" else b
    neg = b if a.polarity == "positive" else a
    p = max(float(pos.positive_peak), 0.0)
    n = max(abs(float(neg.negative_peak)), 0.0)
    if p < config.min_peak or n < config.min_peak:
        return None
    balance = min(p, n) / max(p, n)
    if balance < config.min_peak_balance:
        return None

    distance = _candidate_distance(a, b)
    parent_scale = max(float(a.major_extent + b.major_extent), 1e-9)
    proximity = 1.0 - min(distance / (config.max_distance_ratio * parent_scale), 1.0)
    if proximity <= 0.0:
        return None

    shape_bonus = (
        0.10
        if (a.shape_class in {"compact", "elongated"} and b.shape_class in {"compact", "elongated"})
        else 0.0
    )
    parent_bonus = (
        0.15
        if a.separation_parent_id is not None and a.separation_parent_id == b.separation_parent_id
        else 0.0
    )
    score = float(np.clip(0.70 * balance + 0.30 * proximity + parent_bonus + shape_bonus, 0.0, 1.0))
    return DipolePairAssessment(
        pair_score=score, peak_balance=float(balance), lobe_distance=distance
    )


def _append_note_once(candidate: Candidate, note: str) -> None:
    """Append a provenance note unless already present (idempotent re-runs)."""
    if note not in (candidate.notes or ""):
        candidate.notes = ((candidate.notes + "; ") if candidate.notes else "") + note


def _clean_dipole_notes(notes: str) -> list[str]:
    """Drop pairing/merge provenance that will be regenerated once."""
    kept: list[str] = []
    for part in (notes or "").split(";"):
        text = part.strip()
        low = text.lower()
        if not text:
            continue
        if (
            "bipolar dipole pair" in low
            or "merged bipolar response" in low
            or "bipolar-dipole parent" in low
            or "dipole companion" in low
            or "opposite-sign lobes are treated as one dipolar response" in low
            or "separated from parent candidate" in low
        ):
            continue
        if text not in kept:
            kept.append(text)
    return kept


def _weighted_average(a: float, b: float, wa: float, wb: float) -> float:
    denom = wa + wb
    if denom <= 1e-12:
        return float(np.nanmean([a, b]))
    return float((a * wa + b * wb) / denom)


def _axial_weighted_average(a: float, b: float, wa: float, wb: float) -> float:
    """Axial (doubling-angle) weighted mean of two [0, 180) orientations.

    Stage 2 (S07 / contract K10). A bipolar lobe pair is exactly where a linear
    mean is most wrong: the two lobes sit on *opposite* sides of the same axis,
    so their orientations straddle the 0/180 wrap, and the linear mean points
    perpendicular to the true axis. Mean(5, 175) is 90; the axis is 0.

    Applies to ``orientation_deg`` only. Every other field averaged in this
    module (centres, mean signal, signed mean, weighted centroids) is a genuinely
    linear quantity and keeps :func:`_weighted_average` -- changing those would
    be an unrelated behaviour change.
    """
    from .._util import axial_mean_deg

    if not (math.isfinite(a) and math.isfinite(b)):
        return float("nan")
    return axial_mean_deg([a, b], [wa, wb])


def deblend_spatially_separated_multitarget_pairs(
    candidates: list[Candidate], *, min_distance_m: float = 1.50, max_distance_m: float = 6.50
) -> list[Candidate]:
    """Relabel a conservative subset of decomposed multi-scan bipolar lobes as separate response types.

    This is a response-deblending heuristic: it does not prove two physical objects. It only applies to
    opposite-sign fragments from the same multi-scan parent when their metric XY separation is well beyond
    the lobe spacing observed in the packaged single-scan OKM dipole regressions.

    Returns a new list; inputs are never mutated.
    """
    if len(candidates) < 2:
        return list(candidates)
    touched: dict[int, Candidate] = {}
    for i, a in enumerate(candidates):
        if (
            a.separation_parent_id is None
            or a.separation_status != "decomposed-consensus"
            or int(a.scan_count) < 2
            or not a.metric_geometry_reliable
        ):
            continue
        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            if (
                b.separation_parent_id != a.separation_parent_id
                or b.separation_status != "decomposed-consensus"
                or int(b.scan_count) < 2
                or not b.metric_geometry_reliable
            ):
                continue
            if {a.polarity, b.polarity} != {"positive", "negative"}:
                continue
            distance = _candidate_distance(a, b)
            if not (float(min_distance_m) <= distance <= float(max_distance_m)):
                continue
            pos = a if a.polarity == "positive" else b
            neg = b if a.polarity == "positive" else a
            # Require a non-linear positive lobe and a compact negative lobe.
            # These are morphology guards, not material identification.
            if float(pos.linearity_score) >= 0.70 and float(pos.line_support_score) >= 0.80:
                continue
            if float(neg.compactness) < 0.35:
                continue
            note = (
                f"kept as spatially separated multi-target response pair; lobe distance {distance:.2f} m; "
                "deblending hypothesis, not physical-object proof"
            )
            for idx, c in ((i, a), (j, b)):
                base = touched.get(idx, c)
                flags = list(
                    dict.fromkeys((base.quality_flags or []) + ["spatial-multitarget-deblend"])
                )
                touched[idx] = replace(
                    base,
                    notes=((base.notes + "; ") if base.notes else "") + note,
                    quality_flags=flags,
                    separation_quality=float(np.clip(max(base.separation_quality, 0.55), 0.0, 1.0)),
                )
            pos_idx, neg_idx = (i, j) if a.polarity == "positive" else (j, i)
            touched[pos_idx] = replace(touched[pos_idx], pattern_hypothesis="metallic-like")
            touched[neg_idx] = replace(touched[neg_idx], pattern_hypothesis="cavity-like")
    return [touched.get(idx, c) for idx, c in enumerate(candidates)]


def merge_dipolar_response_components(
    candidates: list[Candidate],
    config: DipoleMergeConfig | None = None,
    *,
    fragment_cells: Mapping[int, tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]] | None = None,
    field_shape: tuple[int, int] | None = None,
) -> list[Candidate]:
    """Merge adjacent positive/negative lobes that form one bipolar response.

    This removes the common failure mode where one physical response is reported as
    two independent objects. It never merges edge-heavy or weak lobes, and it records
    the source candidate IDs in the merged candidate for auditability.

    ``fragment_cells`` carries each fragment's ``(rows, cols)`` as recorded by
    ``site.separation.separate_fused_candidates``. When both lobes of a pair are
    present, the merged candidate's ``compactness``, ``solidity``,
    ``geometry_quality`` and ``area_cells`` are recomputed on the **union** of their
    cells instead of being combined per lobe. Without it the merge falls back to the
    historical per-lobe average and the candidate's notes say so, so a payload is
    never silently ambiguous about which rule produced its numbers.
    """
    config = config or DEFAULT_DIPOLE_MERGE_CONFIG
    if len(candidates) < 2:
        return candidates

    candidates = list(candidates)
    used: set[int] = set()
    merged: list[Candidate] = []
    next_id = 1

    # Prefer same-parent pairs, then score any remaining nearby opposite-polarity pair.
    # Each pair is scored once; the assessment is threaded into make_merged so
    # blocked notes are written exactly once per pair (idempotent on re-runs).
    assessments: dict[tuple[int, int], DipolePairAssessment] = {}
    pairs: list[tuple[float, int, int]] = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            assessment = _dipole_pair_metrics(candidates[i], candidates[j], config)
            if assessment is None:
                continue
            if assessment.blocked_reason is not None:
                _append_note_once(candidates[i], assessment.blocked_reason)
                _append_note_once(candidates[j], assessment.blocked_reason)
                continue
            if assessment.pair_score >= config.min_pair_score:
                assessments[(i, j)] = assessment
                pairs.append((assessment.pair_score, i, j))
    pairs.sort(reverse=True)

    pair_for: dict[int, int] = {}
    for _score, i, j in pairs:
        if i in used or j in used:
            continue
        pair_for[i] = j
        pair_for[j] = i
        used.add(i)
        used.add(j)

    def make_merged(a: Candidate, b: Candidate, assessment: DipolePairAssessment) -> Candidate:
        weight_a = max(float(abs(a.anomaly_score)), 1e-6)
        weight_b = max(float(abs(b.anomaly_score)), 1e-6)
        # A merged dipole's cell-level morphology describes the set the two lobes
        # form together. When both lobes' cells were recorded, recompute
        # compactness / solidity / geometry_quality on that union; otherwise fall
        # back to the historical per-lobe combination, which is the only option
        # when the fragments did not come from `separate_fused_candidates` (the
        # site-level fusion path builds its candidates from a fusion grid and
        # carries no per-fragment cells). The fallback is recorded in the
        # candidate's notes so the two cases are distinguishable downstream.
        cells_a = _lobe_cells(a, fragment_cells)
        cells_b = _lobe_cells(b, fragment_cells)
        union = (
            union_mask_metrics(cells_a, cells_b, field_shape=field_shape)
            if cells_a is not None and cells_b is not None
            else None
        )
        boundary_contact_ratio = max(
            float(a.boundary_contact_ratio), float(b.boundary_contact_ratio)
        )
        if union is not None:
            compactness = float(union["compactness"])
            solidity = float(union["solidity"])
            area_cells = int(union["area_cells"])
            geometry_quality = _union_geometry_quality(
                union,
                n_cells=area_cells,
                boundary_contact_ratio=boundary_contact_ratio,
            )
            morphology_provenance = "union-mask"
        else:
            compactness = float(
                np.clip(
                    (a.compactness * weight_a + b.compactness * weight_b) / (weight_a + weight_b),
                    0.0,
                    1.0,
                )
            )
            solidity = min(a.solidity, b.solidity)
            area_cells = int(a.area_cells + b.area_cells)
            geometry_quality = float(
                np.clip(
                    (a.geometry_quality * weight_a + b.geometry_quality * weight_b)
                    / (weight_a + weight_b),
                    0.0,
                    1.0,
                )
            )
            morphology_provenance = "lobe-average"
        xmin = min(a.x_center - a.width / 2.0, b.x_center - b.width / 2.0)
        xmax = max(a.x_center + a.width / 2.0, b.x_center + b.width / 2.0)
        ymin = min(a.y_center - a.height / 2.0, b.y_center - b.height / 2.0)
        ymax = max(a.y_center + a.height / 2.0, b.y_center + b.height / 2.0)
        width = max(xmax - xmin, 1e-9)
        height = max(ymax - ymin, 1e-9)
        major = max(width, height)
        minor = min(width, height)
        aspect = major / max(minor, 1e-9)
        linearity = float(np.clip(1.0 - minor / max(major, 1e-9), 0.0, 1.0))
        # Axial, not linear: a bipolar pair's lobe orientations straddle the
        # 0/180 wrap (contract K10). The other averages below stay linear.
        orientation = _axial_weighted_average(
            a.orientation_deg, b.orientation_deg, weight_a, weight_b
        )
        depth_values = [x for x in (a.depth_estimate, b.depth_estimate) if math.isfinite(x)]
        depth = float(np.median(depth_values)) if depth_values else float("nan")
        depth_min = min(
            [x for x in (a.depth_min, b.depth_min) if math.isfinite(x)], default=float("nan")
        )
        depth_max = max(
            [x for x in (a.depth_max, b.depth_max) if math.isfinite(x)], default=float("nan")
        )
        pair_score, peak_balance, lobe_distance = (
            assessment.pair_score,
            assessment.peak_balance,
            assessment.lobe_distance,
        )
        lobe_ids = sorted([a.id, b.id])
        note_parts = _clean_dipole_notes(a.notes) + _clean_dipole_notes(b.notes)
        note_parts = list(dict.fromkeys(note_parts))
        note_parts.append(
            f"merged bipolar response from lobes #{lobe_ids[0]} and #{lobe_ids[1]} "
            f"(pair score {pair_score:.2f}, peak balance {peak_balance:.2f}, separation {lobe_distance:.3g})"
        )
        notes = "; ".join(note_parts)
        flags = list(
            dict.fromkeys(
                (a.quality_flags or []) + (b.quality_flags or []) + ["dipole-pair", "dipole-merged"]
            )
        )
        merged = replace(
            a,
            id=min(a.id, b.id),
            x_center=_weighted_average(a.x_center, b.x_center, weight_a, weight_b),
            y_center=_weighted_average(a.y_center, b.y_center, weight_a, weight_b),
            depth_mean=depth,
            depth_std=float(np.nanmedian([a.depth_std, b.depth_std]))
            if all(math.isfinite(x) for x in (a.depth_std, b.depth_std))
            else a.depth_std,
            n_points=int(a.n_points + b.n_points),
            area_cells=area_cells,
            width=width,
            height=height,
            aspect_ratio=aspect,
            orientation_deg=orientation,
            peak_signal=max(a.peak_signal, b.peak_signal),
            mean_signal=_weighted_average(a.mean_signal, b.mean_signal, weight_a, weight_b),
            anomaly_score=max(a.anomaly_score, b.anomaly_score),
            shape_class="compact" if aspect < 1.6 else "elongated",
            # A dipole describes the signed response geometry only. It must not
            # force a material-oriented hypothesis such as metallic-like.
            pattern_hypothesis="dipolar-response",
            confidence=float(np.clip(max(a.evidence_score, b.evidence_score), 0.1, 0.95)),
            signed_anomaly_mean=_weighted_average(
                a.signed_anomaly_mean, b.signed_anomaly_mean, weight_a, weight_b
            ),
            positive_peak=max(a.positive_peak, b.positive_peak),
            negative_peak=min(a.negative_peak, b.negative_peak),
            polarity="mixed",
            anomaly_density=max(a.anomaly_density, b.anomaly_density),
            continuity_score=max(a.continuity_score, b.continuity_score),
            compactness=compactness,
            artifact_score=max(a.artifact_score, b.artifact_score),
            multiscale_persistence=float(
                np.clip(
                    (a.multiscale_persistence * weight_a + b.multiscale_persistence * weight_b)
                    / (weight_a + weight_b),
                    0.0,
                    1.0,
                )
            ),
            evidence_score=max(a.evidence_score, b.evidence_score),
            major_extent=major,
            minor_extent=minor,
            elongation_ratio=aspect,
            linearity_score=linearity,
            solidity=solidity,
            boundary_contact_ratio=boundary_contact_ratio,
            broadness_score=max(a.broadness_score, b.broadness_score),
            centroid_weighted_x=_weighted_average(
                a.centroid_weighted_x, b.centroid_weighted_x, weight_a, weight_b
            ),
            centroid_weighted_y=_weighted_average(
                a.centroid_weighted_y, b.centroid_weighted_y, weight_a, weight_b
            ),
            geometry_quality=geometry_quality,
            depth_estimate=depth,
            depth_min=depth_min,
            depth_max=depth_max,
            depth_range=(depth_max - depth_min)
            if math.isfinite(depth_min) and math.isfinite(depth_max)
            else float("nan"),
            depth_valid_fraction=min(a.depth_valid_fraction, b.depth_valid_fraction),
            depth_stability_score=min(a.depth_stability_score, b.depth_stability_score),
            separation_status="merged-dipole",
            separation_parent_id=(
                a.separation_parent_id if a.separation_parent_id == b.separation_parent_id else None
            ),
            separation_fragment_count=2,
            separation_quality=float(
                np.clip(0.5 + 0.5 * max(a.separation_quality, b.separation_quality), 0.0, 1.0)
            ),
            quality_flags=flags,
            notes=(
                f"{notes}; merged morphology from {morphology_provenance}"
                if notes
                else f"merged morphology from {morphology_provenance}"
            ),
            response_family="dipolar-response",
            response_component_ids=sorted(
                set((a.response_component_ids or [a.id]) + (b.response_component_ids or [b.id]))
            ),
            dipole_pair_score=pair_score,
            dipole_peak_balance=peak_balance,
            dipole_lobe_distance=lobe_distance,
            dipole_pair_count=2,
        )
        return merged

    for i, c in enumerate(candidates):
        if i in used:
            if i < pair_for[i]:
                j = pair_for[i]
                key = (i, j) if i < j else (j, i)
                merged.append(make_merged(c, candidates[j], assessments[key]))
            continue
        merged.append(replace(c, id=next_id))
        next_id += 1

    # Re-index deterministically after merging so reports have stable IDs.
    for idx, c in enumerate(merged, 1):
        c.id = idx
    return merged


__all__ = [
    "DEFAULT_DIPOLE_MERGE_CONFIG",
    "DipoleMergeConfig",
    "DipolePairAssessment",
    "deblend_spatially_separated_multitarget_pairs",
    "merge_dipolar_response_components",
]

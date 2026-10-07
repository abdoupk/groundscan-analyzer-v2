"""Patch-based cross-scan evidence rather than single-cell lookup.

v0.4.2 (audit F-07): the agreement score is a diagnostic derived from the same
z-score maps that produced the candidates. It is never allowed to modify
``confidence``; cross-scan confirmation semantics exist only in the site-level
fusion path (``compare.multiscan``).
"""

from __future__ import annotations

import numpy as np

from ..core.grid import Grid2D
from ..models import Candidate
from .registration import AlignmentResult


def _candidate_patch_indices(
    candidate: Candidate, grid_a: Grid2D, resolution: int
) -> tuple[slice, slice]:
    x_min, x_max = np.nanmin(grid_a.x_centers), np.nanmax(grid_a.x_centers)
    y_min, y_max = np.nanmin(grid_a.y_centers), np.nanmax(grid_a.y_centers)
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0
    col = int(np.clip((candidate.x_center - x_min) / x_span * (resolution - 1), 0, resolution - 1))
    row = int(np.clip((candidate.y_center - y_min) / y_span * (resolution - 1), 0, resolution - 1))

    rx = max(1, int(round(candidate.width / x_span * resolution / 2)))
    ry = max(1, int(round(candidate.height / y_span * resolution / 2)))
    rows = slice(max(0, row - ry), min(resolution, row + ry + 1))
    cols = slice(max(0, col - rx), min(resolution, col + rx + 1))
    return rows, cols


def cross_scan_agreement(
    candidates_a: list[Candidate],
    grid_a: Grid2D,
    alignment: AlignmentResult,
) -> list[Candidate]:
    resolution = alignment.b_resampled.shape[0]
    for candidate in candidates_a:
        rows, cols = _candidate_patch_indices(candidate, grid_a, resolution)
        b_patch = alignment.b_resampled[rows, cols]
        valid_patch = alignment.b_valid[rows, cols] & np.isfinite(b_patch)
        if not np.any(valid_patch):
            candidate.cross_scan_agreement = None
            candidate.notes = _append_note(
                candidate.notes, "cross-scan region not evaluable after alignment"
            )
            continue

        values = b_patch[valid_patch]
        candidate_sign = np.sign(candidate.signed_anomaly_mean)
        if candidate_sign == 0:
            candidate_sign = np.sign(candidate.positive_peak + candidate.negative_peak)
        same_sign_fraction = (
            float(np.mean(np.sign(values) == candidate_sign)) if candidate_sign else 0.5
        )
        abs_values = np.abs(values)
        matched_abs = float(np.percentile(abs_values, 90))
        matched_mean_abs = float(np.mean(abs_values))
        matched_peak = float(np.max(abs_values))
        scale = max(candidate.anomaly_score, 1e-6)
        strength = min(matched_abs / scale, 1.0)
        local_overlap = float(np.mean(valid_patch))
        registration = alignment.registration_evidence

        signed_agreement = (2.0 * same_sign_fraction - 1.0) if candidate_sign else 0.0
        raw = strength * max(0.0, signed_agreement) * min(local_overlap / 0.75, 1.0) * registration
        candidate.cross_scan_agreement = round(float(np.clip(raw, 0.0, 1.0)), 3)

        # v0.4.2 (audit F-07): cross-scan agreement is computed from the same
        # z-score maps that produced the candidate, so it is correlated, not
        # independent evidence. It is reported as a diagnostic field and note
        # only; it must never raise confidence above the evidence-model value.
        if candidate.cross_scan_agreement > 0.5:
            candidate.notes = _append_note(
                candidate.notes,
                f"cross-scan support (diagnostic only; does not raise confidence): patch 90th-percentile |z|={matched_abs:.2f}, mean |z|={matched_mean_abs:.2f}, sign agreement={same_sign_fraction:.0%}.",
            )
        elif same_sign_fraction < 0.4:
            candidate.notes = _append_note(
                candidate.notes,
                "second scan shows conflicting signed response in the candidate region",
            )

        candidate.notes = _append_note(
            candidate.notes,
            f"alignment evidence={alignment.registration_evidence:.2f}, peak |z| in B={matched_peak:.2f}.",
        )
    return candidates_a


def _append_note(current: str, note: str) -> str:
    return f"{current}; {note}" if current else note

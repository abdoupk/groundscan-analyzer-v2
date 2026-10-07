"""Extraction false-positive counting helpers for GroundScan Analyzer.

Small measurement primitives kept separate from the audit that used to drive
them (``run_extraction_audit``, removed with the rest of that audit -- it had no
caller outside its own tests). What remains is the distance-to-target counting
the unit gate still pins.
"""

from __future__ import annotations

from math import hypot

from .synthetic_core.core import SyntheticTarget


def _near_candidates(candidates, target: SyntheticTarget, radius: float = 3.0) -> list[dict]:
    rows = []
    for idx, candidate in enumerate(candidates):
        distance = float(hypot(candidate.x_center - target.x, candidate.y_center - target.y))
        if distance <= radius:
            rows.append({
                "candidate_index": idx,
                "distance_m": round(distance, 4),
                "pattern": candidate.pattern_hypothesis,
                "anomaly_score": round(float(candidate.anomaly_score), 4),
                "scale_class": candidate.scale_class,
                "broadness": round(float(candidate.broadness_score), 4),
            })
    return sorted(rows, key=lambda r: r["distance_m"])


def _false_positives(candidates, targets: tuple[SyntheticTarget, ...], radius: float = 3.0) -> int:
    count = 0
    for candidate in candidates:
        nearest = min(
            (hypot(candidate.x_center - t.x, candidate.y_center - t.y) for t in targets),
            default=float("inf"),
        )
        if nearest > radius:
            count += 1
    return count

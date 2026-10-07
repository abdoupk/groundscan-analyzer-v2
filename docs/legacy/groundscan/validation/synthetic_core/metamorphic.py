"""Metamorphic/invariance relations for the science framework (P3).

ScanData-space transform helpers plus the frozen relation specifications.
Helpers copy (never mutate) public ScanData objects; evaluation runs the
public pipeline. Array-space transform algebra is pinned separately in
tests/unit/test_math_contracts.py.

Strengths: EXACT (pure-function identities), TOLERANCE (pipeline relations
with justified numeric bounds), FLAGS_ONLY (coordinate-frame provenance),
REVIEW_REQUIRED (recorded for inspection, crash-freedom only).

Exact-vs-tolerance audit (measured, seeded synthetic pairs):
- Pipeline relations are TOLERANCE, never EXACT: the pipeline contains
  data-dependent stages (background estimation, zigzag auto-diagnosis,
  absolute screening thresholds) that no contract forces to commute with
  transforms. Measured deviations are 0.0 (positions to ~1e-14,
  scores bit-identical, orientations to ~1e-3 deg), but the bounds below
  encode the justification, not the measurement.
- MIRROR_POSITION_TOLERANCE_M (0.01 m): mirrors route through identical
  binning on mirrored coordinates; absorbs last-ulp platform noise only.
- Evidence-score bound (1e-9): background statistics are
  permutation-invariant over the mirrored sample multiset, so scores
  coincide bit-identically on lattice-preserving inputs.
- MIRROR_ORIENTATION_TOLERANCE_DEG (5 deg, mod 180): mirrors negate
  linear-feature orientation; the bound covers estimator discretization,
  not definition drift.
- Pairing is by mirrored proximity with pattern equality (Hungarian),
  never by candidate id: detection order follows scan order, which flips
  legitimately reverse (verified on multiple_targets, where id-order
  pairing falsely reported dx ~ 18 m on perfectly mirrored sets).
- flip_y/rot180 carry the row-order caveat (zigzag auto-diagnosis reads
  row order); measured identical here, specified as tolerance regardless.
- rot90 is REVIEW_REQUIRED: nx/ny swap changes line structure, so no
  pipeline relation is asserted; array-level algebra is pinned in P0.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

EXACT = "exact"
TOLERANCE = "tolerance"
FLAGS_ONLY = "flags_only"
REVIEW_REQUIRED = "review_required"

#: Position mirror tolerance (m). Lattice-preserving mirrors route through
#: identical binning on mirrored coordinates with permutation-invariant
#: background statistics, so mirrored outputs coincide to float precision;
#: the bound exists only to absorb last-ulp platform noise.
MIRROR_POSITION_TOLERANCE_M = 0.01

#: Orientation acceptance for linear features under mirroring (deg, mod 180).
MIRROR_ORIENTATION_TOLERANCE_DEG = 5.0


def flip_x_scan(scan: Any) -> Any:
    """Mirror physical x about the scan extent. Grid indices preserved."""
    out = copy.copy(scan)
    x = np.asarray(scan.x, dtype=float)
    lo, hi = float(np.nanmin(x)), float(np.nanmax(x))
    out.x = lo + hi - x
    return out


def flip_y_scan(scan: Any) -> Any:
    """Mirror physical y about the scan extent. Grid indices preserved.

    NOTE: mirroring y flips acquisition row order, so row-order heuristics
    (zigzag auto-diagnosis) may legitimately respond differently. Relations
    using this transform carry TOLERANCE strength with that caveat, never
    EXACT.
    """
    out = copy.copy(scan)
    y = np.asarray(scan.y, dtype=float)
    lo, hi = float(np.nanmin(y)), float(np.nanmax(y))
    out.y = lo + hi - y
    return out


def translate_scan(scan: Any, dx_m: float, dy_m: float) -> Any:
    """Shift physical coordinates by a constant offset."""
    out = copy.copy(scan)
    out.x = np.asarray(scan.x, dtype=float) + float(dx_m)
    out.y = np.asarray(scan.y, dtype=float) + float(dy_m)
    return out


def rot180_scan(scan: Any) -> Any:
    """180-degree rotation: mirror both axes (row order flips; see flip_y)."""
    return flip_y_scan(flip_x_scan(scan))


def rot90_scan(scan: Any) -> Any:
    """90-degree rotation: swap axes (line structure changes).

    REVIEW_REQUIRED only: nx/ny swap, line continuity and zigzag semantics
    change, so no pipeline relation is asserted beyond crash-freedom.
    """
    out = copy.copy(scan)
    out.x, out.y = np.asarray(scan.y, dtype=float).copy(), np.asarray(scan.x, dtype=float).copy()
    gi = None if scan.grid_i is None else np.asarray(scan.grid_j, dtype=float).copy()
    gj = None if scan.grid_j is None else np.asarray(scan.grid_i, dtype=float).copy()
    out.grid_i, out.grid_j = gi, gj
    return out


def index_frame_scan(scan: Any) -> Any:
    """Same samples as index-only coordinates (provenance flip, not geometry)."""
    out = copy.copy(scan)
    out.coords_are_index_only = True
    out.coordinate_provenance = "index"
    return out


RELATION_SPECS: dict[str, dict[str, Any]] = {
    "flip_x": {
        "strength": TOLERANCE,
        "position_rule": "x mirrors about the scan x-extent; y unchanged",
        "notes": "Row order preserved; zigzag diagnosis unaffected by construction.",
    },
    "translate": {
        "strength": TOLERANCE,
        "position_rule": "positions shift by exactly (dx, dy)",
        "notes": "Constant offsets commute with binning and background estimation.",
    },
    "flip_y": {
        "strength": TOLERANCE,
        "position_rule": "y mirrors about the scan y-extent; x unchanged",
        "notes": "Row order flips: zigzag auto-diagnosis may respond; "
        "positions/scores still stable on lattice-preserving inputs.",
    },
    "rot180": {
        "strength": TOLERANCE,
        "position_rule": "both axes mirror; linear orientation compared mod 180",
        "notes": "Composes flip_x + flip_y; inherits the flip_y row-order caveat.",
    },
    "rot90": {
        "strength": REVIEW_REQUIRED,
        "position_rule": "none asserted at pipeline level",
        "notes": "Line structure changes; array-level algebra is pinned in P0.",
    },
    "index_frame": {
        "strength": FLAGS_ONLY,
        "position_rule": "none asserted on values",
        "notes": "Only provenance flags may change (metric_geometry_reliable False).",
    },
}


def _finite_scores(candidates: list) -> bool:
    return all(
        math.isfinite(float(c.evidence_score)) and math.isfinite(float(c.screening_score))
        for c in candidates
    )


def evaluate_metamorphic_pair(
    base_candidates: list,
    transformed_candidates: list,
    transform: str,
    *,
    x_sum: float | None = None,
    y_sum: float | None = None,
    shift: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Check one transformed run against its base run per the frozen spec."""
    spec = RELATION_SPECS[transform]
    failures: list[str] = []
    detail: dict[str, Any] = {
        "transform": transform,
        "strength": spec["strength"],
        "base_count": len(base_candidates),
        "transformed_count": len(transformed_candidates),
        "finite_scores": _finite_scores(transformed_candidates),
    }
    if not _finite_scores(transformed_candidates):
        failures.append("non-finite scores in transformed output")
    if transform == "index_frame":
        flags = [bool(c.metric_geometry_reliable) for c in transformed_candidates]
        detail["metric_flags"] = flags
        if any(flags):
            failures.append("index-frame candidates claim metric geometry")
        return {"passes": not failures, "failures": failures, **detail}
    if transform == "rot90":
        detail["note"] = "review-only: counts/patterns recorded, not asserted"
        detail["patterns"] = sorted({c.pattern_hypothesis for c in transformed_candidates})
        return {"passes": not failures, "failures": failures, **detail}
    if len(base_candidates) != len(transformed_candidates):
        failures.append(f"count changed {len(base_candidates)} -> {len(transformed_candidates)}")
        return {"passes": False, "failures": failures, **detail}
    from scipy.optimize import linear_sum_assignment

    from .oracles import angular_error_mod180

    def _expected_position(base: Any) -> tuple[float, float]:
        exp_x, exp_y = float(base.x_center), float(base.y_center)
        if transform == "flip_x" and x_sum is not None:
            exp_x = float(x_sum) - exp_x
        elif transform == "flip_y" and y_sum is not None:
            exp_y = float(y_sum) - exp_y
        elif transform == "rot180" and x_sum is not None and y_sum is not None:
            exp_x = float(x_sum) - exp_x
            exp_y = float(y_sum) - exp_y
        elif transform == "translate" and shift is not None:
            exp_x = exp_x + float(shift[0])
            exp_y = exp_y + float(shift[1])
        return exp_x, exp_y

    # Pair across the transform by mirrored proximity with pattern equality,
    # never by id order: detection order follows scan order, which a flip
    # legitimately reverses. Unpaired candidates are appearance/disappearance
    # failures, not pairing noise.
    expected = [_expected_position(b) for b in base_candidates]
    big = 1e9
    cost = np.full((len(base_candidates), len(transformed_candidates)), big)
    for i, base in enumerate(base_candidates):
        for j, moved in enumerate(transformed_candidates):
            if base.pattern_hypothesis != moved.pattern_hypothesis:
                continue
            cost[i, j] = math.hypot(
                float(moved.x_center) - expected[i][0],
                float(moved.y_center) - expected[i][1],
            )
    rows, cols = linear_sum_assignment(np.asarray(cost))
    assigned: dict[int, int] = {}
    for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
        if cost[i, j] > MIRROR_POSITION_TOLERANCE_M:
            failures.append(
                f"no mirrored counterpart for base candidate #{base_candidates[i].id} "
                f"({base_candidates[i].pattern_hypothesis})"
            )
        else:
            assigned[i] = j
    if len(assigned) != len(base_candidates):
        return {"passes": False, "failures": failures, **detail}
    for i, j in sorted(assigned.items()):
        base = base_candidates[i]
        moved = transformed_candidates[j]
        if base.polarity != moved.polarity:
            failures.append(f"polarity changed {base.polarity} -> {moved.polarity}")
        if abs(float(base.evidence_score) - float(moved.evidence_score)) > 1e-9:
            failures.append("evidence score changed under lattice-preserving transform")
        base_ori = float(getattr(base, "orientation_deg", float("nan")))
        moved_ori = float(getattr(moved, "orientation_deg", float("nan")))
        if math.isfinite(base_ori) and math.isfinite(moved_ori):
            # Mirrors negate orientation; rotations/translations preserve it
            # (all compared mod 180 for linear features).
            expected_ori = (-base_ori) % 180.0 if transform.startswith("flip_") else base_ori
            err = angular_error_mod180(moved_ori, expected_ori)
            if err > MIRROR_ORIENTATION_TOLERANCE_DEG:
                failures.append(f"orientation changed mod-180 by {err:.3f} deg")
    return {"passes": not failures, "failures": failures, **detail}

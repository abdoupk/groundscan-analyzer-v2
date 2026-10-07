"""Shadow measurement: compute both answers, decide nothing (Remediation Design v2 §11).

Three of the four scientific workstreams in v2 are blocked on *measurement*, not
on design. This module is the measurement instrument. It computes the corrected
value alongside the shipped one, propagates it through the whole decision chain
**without using it for any decision**, and records the delta.

Stage 3 note (S02 activated). The S02 columns changed meaning when production
adopted the corrected formula, and the module was relabelled rather than
repurposed: ``solidity_production`` is what the pipeline emitted,
``solidity_oracle`` is the independent 4N-corner implementation the shadow has
always computed, and ``solidity_legacy`` is the retired ``N / hull(centres)``
formula. The oracle-versus-production comparison is now a *standing cross-check
of two implementations of the same quantity* rather than a proposal, and the
legacy column is the standing record of the defect's size.

Three rules make the shadow safe to run, and each is enforced structurally rather
than by convention:

1. **It is off by default.** ``AnalysisConfig.shadow_measurement`` defaults to
   ``"off"``; nothing is computed unless a caller opts in.
2. **It writes only to the in-memory diagnostics ledger.** Results live on a
   :class:`ShadowMeasurement` ledger carried beside the anomaly map, never on a
   ``Candidate`` field and never in ``ScanMetadata.extra``. That matters: both of
   those are serialised into ``analysis.json``, which is golden-hashed, so a
   shadow field written there would be a behaviour change wearing a diagnostics
   label. ``AnomalyMap`` is never serialised, which is why it is the carrier.
3. **The corrected values influence no decision.** ``exact_solidity`` and
   :func:`assign_role` are computed and reported, never consumed. The S01 roles
   remain diagnostics pending their own activation; the S02 oracle is a
   cross-check, and the equality it reports is a defect signal rather than a
   proposal.

Ordering rule (v2 §10): nothing in this module is allowed to influence a gate, a
score, a classification, or a candidate field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import ConvexHull

from .._util import ScaleEstimate, robust_scale, robust_scale_with_status

# ---------------------------------------------------------------------------
# Roles (v2 §4.3)
# ---------------------------------------------------------------------------
# There is deliberately **no** "exactly one primary finding per component" rule
# (withdrawn in v2 §1.2 as too strong). Instead every finding declares a role.
# `decomposition` and `unresolved` are *nested* by default and are promoted to top
# level only when spatially distinguishable -- a promotion whose threshold `d_res`
# is a calibration parameter that does not exist yet, so the shadow always reports
# the conservative answer. There is no `alternative` role: the §4.6 model gap it
# would cover is reported by `structural_alternative_unmodelled` instead, never
# converted into a role change.
ROLE_RESPONSE = "response"
ROLE_DECOMPOSITION = "decomposition"
ROLE_UNRESOLVED = "unresolved"
ROLE_CONFLICT = "conflict"

#: Roles that are top-level in the output. `decomposition` / `unresolved` are
#: nested unless promoted by the (uncalibrated) `d_res` rule.
TOP_LEVEL_ROLES: frozenset[str] = frozenset({ROLE_RESPONSE, ROLE_CONFLICT})

#: `separation_status` values that mean "this record is a subdivision of another".
_SEPARATION_DECOMPOSED = frozenset({"decomposed-consensus", "decomposed-depth-layer"})


# ---------------------------------------------------------------------------
# S02 -- solidity (contract K4)
# ---------------------------------------------------------------------------


def exact_solidity(
    rows: np.ndarray[Any, Any],
    cols: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
) -> float:
    """Dimensionless solidity of a cell set: ``A_object / A_hull``, in (0, 1].

    The hull is taken over the **4N cell corners**, which is exact: the convex
    hull of a union equals the convex hull of the extreme points of its members.
    This is what makes the value

    * dimensionless (the ``dx * dy`` in the numerator cancels the pitch out of
      the hull area),
    * invariant under uniform rescaling and under re-sampling at fixed physical
      shape, and
    * **defined for every cell count >= 2**, including corner-touching diagonals
      and disconnected sets. The shipped formula has no such property: it
      divides a *count* by an *area* (units of 1/area) and falls back to 1.0
      whenever the cell *centres* are collinear, conflating "a line of adjacent
      cells" (a rectangle, genuinely solid) with "a diagonal run" (not a
      rectangle, genuinely not solid).

    Unreachable from any decision site by design; activation is a separate,
    measured step (v2 §14 PR-10).
    """
    count = int(len(rows))
    if count == 0:
        return 1.0
    dx = float(cell_dx)
    dy = float(cell_dy)
    if not (math.isfinite(dx) and math.isfinite(dy)) or dx <= 0.0 or dy <= 0.0:
        return float("nan")
    xs = np.asarray(cols, dtype=float) * dx
    ys = np.asarray(rows, dtype=float) * dy
    half_x = dx / 2.0
    half_y = dy / 2.0
    corners = np.column_stack([
        np.concatenate([xs - half_x, xs + half_x, xs + half_x, xs - half_x]),
        np.concatenate([ys - half_y, ys - half_y, ys + half_y, ys + half_y]),
    ])
    hull_area = _hull_area(corners)
    if not math.isfinite(hull_area) or hull_area <= 1e-12:
        # Fewer than 3 distinct corners: the union is a point or a segment, and
        # its own convex hull *is* the union, so solidity is 1.0 by definition.
        return 1.0
    return float(np.clip((count * dx * dy) / hull_area, 0.0, 1.0))


def legacy_solidity(
    rows: np.ndarray[Any, Any],
    cols: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
) -> float:
    """The **retired** pre-Stage-3 formula, kept only as the measured baseline.

    ``N_cells / hull(centres)``. A cell count divided by an area, so its units
    are 1/area and it is not a shape ratio: it collapses to 0.02 for a 6-cell L
    at a pitch of 10 and to 3e-6 at 1000, and its ``QhullError -> 1.0`` branch
    reported a corner-touching diagonal run as perfectly solid. Production
    implements the corrected formula in ``core.shape._convex_hull_solidity`` as
    of Stage 3; this function is the *history* of the defect, not a second
    opinion on the value.

    It is retained because the shadow's job is to state, on every run, how far
    the retired formula sat from the truth -- a number that must be able to be
    looked at when a calibration question comes up -- and because the test suite
    pins its failure modes so it cannot quietly return.
    """
    count = int(len(rows))
    if count < 3:
        return 1.0
    points = np.column_stack([
        np.asarray(cols, dtype=float) * float(cell_dx),
        np.asarray(rows, dtype=float) * float(cell_dy),
    ])
    hull_area = _hull_area(points)
    if not math.isfinite(hull_area) or hull_area <= 1e-9:
        return 1.0
    return float(np.clip(count / max(hull_area, 1e-9), 0.0, 1.0))


def _hull_area(points: np.ndarray[Any, Any]) -> float:
    if len(points) < 3:
        return float("nan")
    try:
        return float(ConvexHull(points).volume)
    except Exception:
        # QhullError: collinear or degenerate. The caller decides what that
        # means -- which is precisely the decision the shipped code gets wrong.
        return float("nan")


def _shadow_geometry_quality(
    *,
    n_cells: int,
    local_fraction: float,
    solidity: float,
    boundary_contact_ratio: float,
) -> float:
    """The ``geometry_quality`` formula from ``core.shape`` with a given solidity.

    Re-derived rather than imported so the shadow can substitute a solidity
    without mutating the live metric dict. Kept in step with ``shape.py:255-264``
    by ``tests/unit/test_shadow_measurement.py::test_shadow_geometry_quality_matches_production``.
    """
    return float(
        np.clip(
            0.30 * min(n_cells / 10.0, 1.0)
            + 0.25 * min(local_fraction, 1.0)
            + 0.25 * solidity
            + 0.20 * (1.0 - min(boundary_contact_ratio, 1.0)),
            0.0,
            1.0,
        )
    )


# ---------------------------------------------------------------------------
# S01 -- role assignment (contract K1/K2)
# ---------------------------------------------------------------------------


def assign_role(candidate: Any) -> str:
    """Classify one candidate's role in the six-level model (v2 §4.3).

    Read-only: it inspects fields the pipeline already populates
    (``polarity_conflict``, ``separation_status``, ``separation_parent_id``,
    ``unresolved_overlap_*``) and never writes. It does **not** resolve
    ``separation_parent_id`` against the emitted candidate list, because that
    pointer is recorded against pre-renumbering ids and collides with the
    emitted ids after separation re-indexes them; deriving the role from the
    candidate's own fields is the only stable option.

    ``unresolved`` is a *resolvability* role, and it is deliberately ranked
    below ``decomposition``: a record the separation stage produced is a
    fragment, and saying so is the more useful structural fact for the
    multiplicity defect. The overlap diagnostic firing on a record the
    separation path never touched is likewise **not** folded in -- §4.6 records
    that case ("this region may be two targets, or one target with a strong
    shoulder") as a **model gap**, and filling it with a demotion would invent a
    nesting decision the engine never made. It is surfaced separately as
    :func:`structural_alternative_unmodelled` instead.
    """
    if bool(getattr(candidate, "polarity_conflict", False)):
        return ROLE_CONFLICT
    status = str(getattr(candidate, "separation_status", "none") or "none")
    if status in _SEPARATION_DECOMPOSED or _decomposition_engaged(candidate):
        return ROLE_DECOMPOSITION
    if status == "unresolved-undersegmented":
        # Seeds existed and none survived the size gate: sub-structure detected,
        # explicitly not resolvable at this sampling.
        return ROLE_UNRESOLVED
    if _separation_context(candidate) and _overlap_detected(candidate):
        return ROLE_UNRESOLVED
    return ROLE_RESPONSE


def _decomposition_engaged(candidate: Any) -> bool:
    """Whether this record *is* a product of the decomposition stage."""
    if str(getattr(candidate, "separation_status", "none") or "none") in _SEPARATION_DECOMPOSED:
        return True
    return getattr(candidate, "separation_parent_id", None) is not None


def _separation_context(candidate: Any) -> bool:
    """Whether the separation path engaged on this record at all."""
    if _decomposition_engaged(candidate):
        return True
    if str(getattr(candidate, "separation_status", "none") or "none") != "none":
        return True
    return int(getattr(candidate, "separation_fragment_count", 1) or 1) > 1


def structural_alternative_unmodelled(candidate: Any) -> bool:
    """True when the overlap diagnostic fires and separation never engaged.

    This is the §4.6 model gap: a live "possible-unresolved-overlap" signal that
    the current object model has no way to express as a competing *structural*
    reading ("two targets" vs "one target with a strong shoulder"). Recorded as a
    known limitation and counted, never silently converted into a role change.
    """
    return _overlap_detected(candidate) and not _separation_context(candidate)


def _overlap_detected(candidate: Any) -> bool:
    score = float(getattr(candidate, "unresolved_overlap_score", 0.0) or 0.0)
    reason = str(getattr(candidate, "unresolved_overlap_reason", "") or "")
    if reason:
        return True
    return math.isfinite(score) and score > 0.0


def is_top_level(role: str) -> bool:
    """Whether *role* is presented as a top-level finding by default."""
    return role in TOP_LEVEL_ROLES


# ---------------------------------------------------------------------------
# Ledger records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolidityShadow:
    """One component's S02 comparison, plus the decision-chain delta.

    After Stage 3 the two solidity columns answer different questions and both
    are worth keeping:

    * ``solidity_production`` -- what the pipeline actually emitted this run.
    * ``solidity_oracle`` -- the 4N-corner independent implementation. It is a
      *second implementation of the corrected quantity*, not an alternative
      opinion: agreement between them to round-off is the standing cross-check
      that the production identity ``hull(cells) = hull(centres) (+) cell`` is
      still true (v2 ?5.2).
    * ``solidity_legacy`` -- what the retired ``N / hull(centres)`` formula
      produced. This is the defect measurement, and it is the number that
      changes nothing and should stay visible.
    """

    component_id: int
    n_cells: int
    solidity_oracle: float
    solidity_production: float
    solidity_legacy: float
    shape_class_shipped: str
    shape_class_shadow: str
    shape_branch: str
    geometry_quality_shipped: float
    geometry_quality_shadow: float
    hypothesis_shipped: str
    hypothesis_shadow: str
    confidence_shipped: float
    confidence_shadow: float
    margin_shipped: float
    margin_shadow: float
    report_fields_changed: tuple[str, ...] = ()

    @property
    def solidity_delta(self) -> float:
        """Production vs the independent oracle: zero up to round-off."""
        return float(self.solidity_oracle - self.solidity_production)

    @property
    def legacy_delta(self) -> float:
        """Oracle vs the retired formula: the size of the S02 defect."""
        return float(self.solidity_oracle - self.solidity_legacy)

    @property
    def agrees_with_oracle(self) -> bool:
        return abs(self.solidity_delta) <= 1e-9

    @property
    def would_change_shape_class(self) -> bool:
        return self.shape_class_shipped != self.shape_class_shadow

    @property
    def would_change_hypothesis(self) -> bool:
        return self.hypothesis_shipped != self.hypothesis_shadow

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "n_cells": self.n_cells,
            "solidity_oracle": self.solidity_oracle,
            "solidity_production": self.solidity_production,
            "solidity_legacy": self.solidity_legacy,
            "oracle_delta_vs_production": self.solidity_delta,
            "agrees_with_oracle": self.agrees_with_oracle,
            "legacy_delta": self.legacy_delta,
            "would_change_shape_class": self.would_change_shape_class,
            "shape_class_shipped": self.shape_class_shipped,
            "shape_class_shadow": self.shape_class_shadow,
            "shape_branch": self.shape_branch,
            "geometry_quality_shipped": self.geometry_quality_shipped,
            "geometry_quality_shadow": self.geometry_quality_shadow,
            "geometry_quality_delta": self.geometry_quality_shadow - self.geometry_quality_shipped,
            "would_change_hypothesis": self.would_change_hypothesis,
            "hypothesis_shipped": self.hypothesis_shipped,
            "hypothesis_shadow": self.hypothesis_shadow,
            "confidence_delta": self.confidence_shadow - self.confidence_shipped,
            "margin_delta": self.margin_shadow - self.margin_shipped,
            "report_fields_changed": list(self.report_fields_changed),
        }


@dataclass(frozen=True)
class ScaleShadow:
    """One residual's S03 status record."""

    scale_shipped: float
    estimate: ScaleEstimate

    @property
    def ratio(self) -> float:
        """``scale_exact / scale_shipped``; NaN when indeterminate."""
        if not math.isfinite(self.estimate.scale) or not math.isfinite(self.scale_shipped):
            return float("nan")
        if self.scale_shipped == 0.0:
            return float("nan")
        return float(self.estimate.scale / self.scale_shipped)

    def to_dict(self) -> dict[str, Any]:
        payload = self.estimate.to_dict()
        payload["scale_shipped"] = float(self.scale_shipped)
        ratio = self.ratio
        payload["ratio_shadow_over_shipped"] = None if ratio != ratio else ratio
        return payload


@dataclass(frozen=True)
class RoleShadow:
    """One finding's S01 role record plus its response-region peers."""

    candidate_id: int
    role: str
    top_level: bool
    response_component_ids: tuple[int, ...]
    separation_status: str
    separation_parent_id: int | None
    separation_fragment_count: int
    polarity_conflict: bool
    unresolved_overlap_score: float
    unresolved_overlap_reason: str
    structural_alternative_unmodelled: bool = False
    within_response_separations: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "top_level": self.top_level,
            "response_component_ids": list(self.response_component_ids),
            "separation_status": self.separation_status,
            "separation_parent_id": self.separation_parent_id,
            "separation_fragment_count": self.separation_fragment_count,
            "polarity_conflict": self.polarity_conflict,
            "unresolved_overlap_score": self.unresolved_overlap_score,
            "unresolved_overlap_reason": self.unresolved_overlap_reason,
            "structural_alternative_unmodelled": self.structural_alternative_unmodelled,
            "within_response_separations": [
                None if s != s else s for s in self.within_response_separations
            ],
        }


@dataclass
class ShadowMeasurement:
    """Accumulator for one run. Never influences a decision (v2 §11)."""

    enabled: bool = False
    solidity: list[SolidityShadow] = field(default_factory=list)
    scale: ScaleShadow | None = None
    roles: list[RoleShadow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "solidity": [r.to_dict() for r in self.solidity],
            "scale": self.scale.to_dict() if self.scale is not None else None,
            "roles": [r.to_dict() for r in self.roles],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        """Run-level census: the numbers the activation gate is decided on."""
        n_solidity = len(self.solidity)
        shape_changes = sum(1 for r in self.solidity if r.would_change_shape_class)
        hypothesis_changes = sum(1 for r in self.solidity if r.would_change_hypothesis)
        # The design's blocking criterion: a large shape_class change rate means
        # activation is blocked pending calibration (v2 §11.2, decision 4).
        shape_change_rate = shape_changes / n_solidity if n_solidity else 0.0
        separations = sorted(
            s
            for record in self.roles
            for s in record.within_response_separations
            if math.isfinite(s)
        )
        return {
            "component_count": n_solidity,
            "shape_class_change_count": shape_changes,
            "shape_class_change_rate": shape_change_rate,
            "hypothesis_change_count": hypothesis_changes,
            "finding_count": len(self.roles),
            "top_level_count": sum(1 for r in self.roles if r.top_level),
            "nested_count": sum(1 for r in self.roles if not r.top_level),
            "role_counts": _role_counts(self.roles),
            # v2 §4.6 model gap: findings whose live overlap signal the object
            # model cannot express. Counted, never silently converted to a role.
            "structural_alternative_unmodelled": sum(
                1 for r in self.roles if r.structural_alternative_unmodelled
            ),
            "indeterminate_scale": bool(
                self.scale is not None and self.scale.estimate.is_indeterminate
            ),
            "scale_status": self.scale.estimate.status if self.scale is not None else None,
            "scale_method": self.scale.estimate.method if self.scale is not None else None,
            "separation_count": len(separations),
            "separation_min_m": separations[0] if separations else None,
            "separation_median_m": _median(separations),
            "separation_max_m": separations[-1] if separations else None,
        }


def _role_counts(roles: list[RoleShadow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in roles:
        counts[record.role] = counts.get(record.role, 0) + 1
    return dict(sorted(counts.items()))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.median(np.asarray(values, dtype=float)))


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def measure_scale(residual: np.ndarray[Any, Any] | None) -> ScaleShadow | None:
    """S03 shadow: run the status estimate beside the shipped single number."""
    if residual is None:
        return None
    finite = np.asarray(residual, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None
    shipped = robust_scale(finite)
    return ScaleShadow(scale_shipped=float(shipped), estimate=robust_scale_with_status(finite))


def measure_roles(candidates: list[Any]) -> list[RoleShadow]:
    """S01 shadow: assign roles and measure within-response separations.

    The separation distribution is the single most valuable artefact this wave
    produces: it is the only route to a *measured* ``d_res`` rather than a
    guessed one. Two findings are treated as belonging to the same response
    region when they share a ``response_component_ids`` entry, which is the
    multi-region membership the engine already records.
    """
    records = [
        RoleShadow(
            candidate_id=int(getattr(c, "id", 0)),
            role=assign_role(c),
            top_level=is_top_level(assign_role(c)),
            response_component_ids=tuple(
                int(v) for v in (getattr(c, "response_component_ids", None) or [])
            ),
            separation_status=str(getattr(c, "separation_status", "none") or "none"),
            separation_parent_id=(
                None
                if getattr(c, "separation_parent_id", None) is None
                else int(c.separation_parent_id)
            ),
            separation_fragment_count=int(getattr(c, "separation_fragment_count", 1) or 1),
            polarity_conflict=bool(getattr(c, "polarity_conflict", False)),
            unresolved_overlap_score=float(getattr(c, "unresolved_overlap_score", 0.0) or 0.0),
            unresolved_overlap_reason=str(getattr(c, "unresolved_overlap_reason", "") or ""),
            structural_alternative_unmodelled=structural_alternative_unmodelled(c),
        )
        for c in candidates
    ]
    return _attach_within_response_separations(records, candidates)


def _attach_within_response_separations(
    records: list[RoleShadow], candidates: list[Any]
) -> list[RoleShadow]:
    """Pairwise distances between findings that share a response region.

    Grouped on shared ``response_component_ids``, so a record with no shared
    region (the site path never populates the field) contributes no separation
    rather than a fabricated one.
    """
    groups: dict[int, list[int]] = {}
    for index, record in enumerate(records):
        for component in record.response_component_ids:
            groups.setdefault(component, []).append(index)

    per_record: dict[int, list[float]] = {i: [] for i in range(len(records))}
    for members in groups.values():
        for a_index in members:
            for b_index in members:
                if a_index >= b_index:
                    continue
                distance = _distance(candidates[a_index], candidates[b_index])
                if distance is None:
                    continue
                per_record[a_index].append(distance)
                per_record[b_index].append(distance)

    return [
        RoleShadow(**{
            **record.__dict__,
            "within_response_separations": tuple(sorted(per_record[index])),
        })
        for index, record in enumerate(records)
    ]


def _distance(a: Any, b: Any) -> float | None:
    ax = getattr(a, "centroid_weighted_x", None)
    ay = getattr(a, "centroid_weighted_y", None)
    bx = getattr(b, "centroid_weighted_x", None)
    by = getattr(b, "centroid_weighted_y", None)
    if ax is None or ay is None or bx is None or by is None:
        return None
    try:
        return float(math.hypot(float(ax) - float(bx), float(ay) - float(by)))
    except (TypeError, ValueError):
        return None


def measure_solidity(
    *,
    labels: np.ndarray[Any, Any],
    n_components: int,
    x_centers: np.ndarray[Any, Any],
    y_centers: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
    candidates: list[Any],
) -> list[SolidityShadow]:
    """S02 shadow: the oracle against production, and the legacy defect size.

    The shadow value is always computed from the **scientifically correct
    geometry** -- ``A_object / hull_of_cell_regions`` -- never from
    ``N * dx * dy / hull_of_centres``, which is arithmetically impossible
    (units of 1/area) and was already rejected in v1.

    Since Stage 3 production computes that same quantity by a different route
    (the centre hull grown by one cell), so this function has become a standing
    cross-check of two independent implementations rather than a proposal. It
    still propagates the oracle value through the whole decision chain on a
    *copy* of the candidate, because a disagreement is then a defect report
    rather than a silent difference.
    """
    from dataclasses import replace

    from ..core.classify import classify_candidate
    from ..core.shape import _classify_shape  # local: keeps core out of import time

    by_component: dict[int, Any] = {}
    for candidate in candidates:
        component_id = int(getattr(candidate, "id", 0))
        by_component.setdefault(component_id, candidate)

    records: list[SolidityShadow] = []
    for component_id in range(1, int(n_components) + 1):
        rows, cols = np.where(labels == component_id)
        if len(rows) == 0:
            continue
        xs = x_centers[cols]
        ys = y_centers[rows]
        oracle = exact_solidity(rows, cols, cell_dx, cell_dy)
        legacy = legacy_solidity(rows, cols, cell_dx, cell_dy)

        candidate = by_component.get(component_id)
        if candidate is None:
            # A component that never became a finding (e.g. sub-``min_size``).
            # The geometry comparison is still worth recording; the downstream
            # chain has nothing to compare.
            records.append(
                SolidityShadow(
                    component_id=component_id,
                    n_cells=int(len(rows)),
                    solidity_oracle=oracle,
                    solidity_production=float("nan"),
                    solidity_legacy=legacy,
                    shape_class_shipped="",
                    shape_class_shadow="",
                    shape_branch="no-candidate",
                    geometry_quality_shipped=float("nan"),
                    geometry_quality_shadow=float("nan"),
                    hypothesis_shipped="",
                    hypothesis_shadow="",
                    confidence_shipped=float("nan"),
                    confidence_shadow=float("nan"),
                    margin_shipped=float("nan"),
                    margin_shadow=float("nan"),
                )
            )
            continue

        boundary = float(getattr(candidate, "boundary_contact_ratio", 0.0) or 0.0)
        broadness = float(getattr(candidate, "broadness_score", 0.0) or 0.0)
        major = float(getattr(candidate, "major_extent", 0.0) or 0.0)
        minor = float(getattr(candidate, "minor_extent", 0.0) or 0.0)
        n_cells = int(len(rows))
        local_fraction = n_cells / max(
            int(rows.max() - rows.min() + 1) * int(cols.max() - cols.min() + 1), 1
        )

        production = float(getattr(candidate, "solidity", float("nan")))
        shape_shipped = str(getattr(candidate, "shape_class", "") or "")
        shape_shadow, _orient, _ratio, _lin = _classify_shape(
            xs, ys, major, minor, boundary, broadness, oracle
        )
        branch = _shape_branch(shape_shipped, shape_shadow, oracle)

        quality_shipped = float(getattr(candidate, "geometry_quality", 0.0) or 0.0)
        quality_shadow = _shadow_geometry_quality(
            n_cells=n_cells,
            local_fraction=local_fraction,
            solidity=oracle,
            boundary_contact_ratio=boundary,
        )

        # Propagate through the real classifier on a *copy*: the live candidate
        # is never touched, and the hypothesis/margin/confidence delta is the
        # number the activation gate was decided on.
        shadow_candidate = replace(
            candidate,
            solidity=oracle,
            geometry_quality=quality_shadow,
            shape_class=shape_shadow,
        )
        try:
            shadow_classified = classify_candidate(shadow_candidate)
        except Exception:
            shadow_classified = shadow_candidate

        records.append(
            SolidityShadow(
                component_id=component_id,
                n_cells=n_cells,
                solidity_oracle=oracle,
                solidity_production=production,
                solidity_legacy=legacy,
                shape_class_shipped=shape_shipped,
                shape_class_shadow=str(shape_shadow),
                shape_branch=branch,
                geometry_quality_shipped=quality_shipped,
                geometry_quality_shadow=quality_shadow,
                hypothesis_shipped=str(getattr(candidate, "pattern_hypothesis", "") or ""),
                hypothesis_shadow=str(getattr(shadow_classified, "pattern_hypothesis", "") or ""),
                confidence_shipped=float(getattr(candidate, "confidence", 0.0) or 0.0),
                confidence_shadow=float(getattr(shadow_classified, "confidence", 0.0) or 0.0),
                margin_shipped=float(getattr(candidate, "selected_hypothesis_margin", 0.0) or 0.0),
                margin_shadow=float(
                    getattr(shadow_classified, "selected_hypothesis_margin", 0.0) or 0.0
                ),
                report_fields_changed=_changed_report_fields(candidate, shadow_classified),
            )
        )
    return records


def _shape_branch(shipped: str, shadow: str, solidity: float) -> str:
    """Which shipped gate the shadow solidity would land on (v2 §11.2).

    Recorded so an activation review can see the specific threshold a changed
    value would trip, not merely that something changed.
    """
    if shipped == shadow:
        return "unchanged"
    crossings = []
    if solidity < 0.48:
        crossings.append("shape.irregular<0.48")
    if solidity <= 0.75:
        crossings.append("classify.metal<=0.75")
    if solidity < 0.5:
        crossings.append("classify.recovery<0.5")
    return ",".join(crossings) if crossings else "no-gate-crossed"


def _changed_report_fields(shipped: Any, shadow: Any) -> tuple[str, ...]:
    """Report and machine-contract fields the shadow value would move."""
    watched = (
        "solidity",
        "shape_class",
        "geometry_quality",
        "pattern_hypothesis",
        "second_hypothesis",
        "classification_method",
        "selected_hypothesis_margin",
        "confidence",
        "evidence_score",
        "quality_score",
        "review_status",
    )
    return tuple(
        field for field in watched if getattr(shipped, field, None) != getattr(shadow, field, None)
    )


__all__ = [
    "ROLE_RESPONSE",
    "ROLE_DECOMPOSITION",
    "ROLE_UNRESOLVED",
    "ROLE_CONFLICT",
    "TOP_LEVEL_ROLES",
    "RoleShadow",
    "ScaleShadow",
    "ShadowMeasurement",
    "SolidityShadow",
    "assign_role",
    "exact_solidity",
    "is_top_level",
    "legacy_solidity",
    "measure_roles",
    "measure_scale",
    "measure_solidity",
    "structural_alternative_unmodelled",
]

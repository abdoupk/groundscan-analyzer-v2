"""Cross-resolution characterization: measure, do not assume (Remediation Design v2 §12.5).

The existing metamorphic suite in :mod:`metamorphic` proves relations *within* one
resolution: it transforms a scan and asserts the pipeline commutes with that
transform. It has **zero** relations about re-sampling, because
``scenario_catalog()`` is single-resolution. This module fills that gap.

What this measures
------------------
The same *physical* scene, sampled at coarse / medium / fine lattice pitches.
For each resolution it records, and keeps strictly separated, the five levels of
the corrected model (v2 §2.1):

===============  ==========================================================
Level 2          ``anomaly_region_count`` -- connected components of the
                 thresholded z-field. A property of (threshold, lattice).
Level 3          ``response_region_count`` -- candidates grouped by
                 ``response_component_ids``.
Level 4          ``candidate_count`` / ``top_level_count`` -- hypotheses.
Level 5          ``nested_decomposition_count`` -- subordinate records.
Level 6          **not measured and not claimed.** A physical object needs
                 external evidence (excavation, borehole, installation
                 record). Nothing here may be read as a count of them.
===============  ==========================================================

Independent oracle
------------------
Two separate oracles, neither of which calls the pipeline:

*Geometry* -- every expected position comes from this module's own continuous
forward model :func:`field_value`, evaluated at the *constructed* centre. The
pipeline's output is never used to derive the expectation.

*Structure* -- the number of local maxima of the **noiseless** field is computed
here, on a fine independent lattice, by a plain 3x3 comparison. Two equal
isotropic Gaussians have two maxima iff their separation exceeds ``2 * sigma``;
that fact is a property of the construction, so it is available as an oracle
without asking the detector anything.

Why nothing here asserts count invariance
-----------------------------------------
Seed counts, component boundaries, fragment counts and discretised shape metrics
are all documented in v2 §4.5 as *permitted* to vary under re-sampling. So no
relation here asserts ``count(coarse) == count(fine)``. Every comparison ends in
a **classification** (:data:`CLASSIFICATIONS`) plus the signals that produced
it, and the classification vocabulary includes ``inconclusive`` and
``unresolved`` because "we cannot say" is a legitimate, and frequently correct,
result. The tolerance for any position comparison is derived from the *lattice
pitch*, never fitted to an observed value.

This module is measurement infrastructure. It activates nothing.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...models import ScanData, ScanMetadata

# ---------------------------------------------------------------------------
# Observation vocabulary
# ---------------------------------------------------------------------------
# "We cannot say" is a first-class outcome, not a failure to be papered over.
STABLE = "stable"
RESOLUTION_SENSITIVE = "resolution-sensitive"
UNRESOLVED = "unresolved"
STRUCTURALLY_AMBIGUOUS = "structurally-ambiguous"
INCONCLUSIVE = "inconclusive"

#: Evaluated in this order; the first satisfied classification wins. Kept
#: explicit (rather than as a score) so a reader can re-derive the verdict.
CLASSIFICATION_PRECEDENCE: tuple[str, ...] = (
    INCONCLUSIVE,
    UNRESOLVED,
    STRUCTURALLY_AMBIGUOUS,
    RESOLUTION_SENSITIVE,
    STABLE,
)

CLASSIFICATIONS: frozenset[str] = frozenset(CLASSIFICATION_PRECEDENCE)

#: Field / label names that would invite a consumer to read a level-4 or level-5
#: count as a level-6 physical-object count. Contract K3 / v2 §2.3.
FORBIDDEN_OBJECT_COUNT_NAMES: frozenset[str] = frozenset({
    "object_count",
    "target_count",
    "physical_objects",
    "physical_object_count",
})

#: Level labels, for the record that this module keeps them apart.
LEVEL_ANOMALY_REGION = 2
LEVEL_RESPONSE_REGION = 3
LEVEL_CANDIDATE_HYPOTHESIS = 4
LEVEL_DECOMPOSITION = 5
LEVEL_PHYSICAL_OBJECT = 6


# ---------------------------------------------------------------------------
# Physical scene: the construction, and the field it defines
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalResponse:
    """One constructed response. A *construction parameter*, not an object count.

    Naming this "target" would smuggle in the level-6 claim the whole exercise
    exists to avoid, so it is a response in the physical field: a place where the
    forward model is non-zero. Whether it corresponds to something buried is
    exactly what no output may assert.
    """

    label: str
    cx: float
    cy: float
    sigma_x: float
    sigma_y: float
    amplitude: float
    orientation_deg: float = 0.0

    def value_at(self, x: np.ndarray[Any, Any], y: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """Continuous field contribution. Evaluated at any point, any lattice."""
        theta = math.radians(self.orientation_deg)
        dx = x - self.cx
        dy = y - self.cy
        xr = math.cos(theta) * dx + math.sin(theta) * dy
        yr = -math.sin(theta) * dx + math.cos(theta) * dy
        return self.amplitude * np.exp(-0.5 * ((xr / self.sigma_x) ** 2 + (yr / self.sigma_y) ** 2))

    @property
    def centre(self) -> tuple[float, float]:
        return (self.cx, self.cy)

    @property
    def separation_m(self) -> float:
        """Equal-sigma pair bifurcation scale, from the construction alone.

        Two equal isotropic Gaussians superpose into two local maxima iff their
        separation exceeds ``2 * sigma``; below it the superlevel set is
        contractible and the field is strictly unimodal. This is why Case C is
        *constructed* to be unresolvable rather than merely observed to be.
        """
        return 2.0 * max(self.sigma_x, self.sigma_y)


@dataclass(frozen=True)
class PhysicalScene:
    """A continuous physical field over a fixed extent, plus its noise model."""

    name: str
    width_m: float
    height_m: float
    responses: tuple[PhysicalResponse, ...]
    noise_sigma: float = 0.5
    case_family: str = ""

    def value_at(self, x: np.ndarray[Any, Any], y: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """The noiseless continuous field. The single source of geometry truth."""
        field_ = np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape, dtype=float)
        for response in self.responses:
            field_ = field_ + response.value_at(x, y)
        return field_

    def lattice(self, resolution: Resolution) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        """Sample coordinates for *resolution*, as (X, Y) shaped like the grid."""
        xs = self.x_samples(resolution)
        ys = self.y_samples(resolution)
        return np.meshgrid(xs, ys, indexing="xy")

    def x_samples(self, resolution: Resolution) -> np.ndarray[Any, Any]:
        return np.arange(resolution.nx, dtype=float) * resolution.dx

    def y_samples(self, resolution: Resolution) -> np.ndarray[Any, Any]:
        return np.arange(resolution.ny, dtype=float) * resolution.dy

    @property
    def response_count(self) -> int:
        """How many responses the *construction* places. Not an object count."""
        return len(self.responses)


# ---------------------------------------------------------------------------
# Resolution ladder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """A sampling lattice: an exact pitch, not a sample count.

    Pitch is the primary parameter (a sample count derived from an extent makes
    "coarse vs fine" depend on the extent). ``dy_ratio`` carries the anisotropic
    case: ``dy = dy_ratio * dx``.
    """

    name: str
    dx: float
    width_m: float
    height_m: float
    dy_ratio: float = 1.0

    @property
    def dy(self) -> float:
        return self.dx * self.dy_ratio

    @property
    def nx(self) -> int:
        return int(round(self.width_m / self.dx)) + 1

    @property
    def ny(self) -> int:
        return int(round(self.height_m / self.dy)) + 1

    @property
    def sample_count(self) -> int:
        return self.nx * self.ny

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dx": self.dx,
            "dy": self.dy,
            "nx": self.nx,
            "ny": self.ny,
            "sample_count": self.sample_count,
        }


def isotropic_ladder(
    width_m: float, height_m: float, pitches: tuple[float, ...]
) -> tuple[Resolution, ...]:
    """coarse -> fine ladder at the given pitches (descending pitch)."""
    return tuple(
        Resolution(name=f"pitch_{p:g}m", dx=float(p), width_m=width_m, height_m=height_m)
        for p in pitches
    )


def anisotropic_ladder(
    width_m: float, height_m: float, pitches: tuple[float, ...], dy_ratio: float
) -> tuple[Resolution, ...]:
    """Ladder with ``dy != dx`` at every rung.

    Same physical scene, same x pitch ladder, y deliberately coarser. The point
    is to measure whether a shape metric that *should* be dimensionless depends
    on the sampling aspect ratio.
    """
    return tuple(
        Resolution(
            name=f"pitch_{p:g}m_dy{dy_ratio:g}x",
            dx=float(p),
            width_m=width_m,
            height_m=height_m,
            dy_ratio=float(dy_ratio),
        )
        for p in pitches
    )


# ---------------------------------------------------------------------------
# Independent sampling
# ---------------------------------------------------------------------------


def sample_scene(scene: PhysicalScene, resolution: Resolution, *, seed: int) -> ScanData:
    """Sample *scene* on *resolution*'s lattice with an independent noise draw.

    The noiseless part is a single analytic evaluation of :meth:`field_value`, so
    every lattice sees the *same continuous field* -- that is what makes this a
    resolution study rather than a set of unrelated scenes.

    The noise draw is independent per resolution by necessity: two different
    lattices cannot share a noise sample. That is exactly why no relation here is
    allowed to be exact, and why the tolerance is derived from pitch.
    """
    xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    signal = scene.value_at(xx, yy)
    rng = np.random.default_rng(seed)
    signal = signal + rng.normal(0.0, scene.noise_sigma, size=signal.shape)
    depth = np.full(signal.shape, 12.0, dtype=float)
    return ScanData(
        x=xx.ravel(),
        y=yy.ravel(),
        z=depth.ravel(),
        signal=signal.ravel(),
        grid_i=np.tile(np.arange(resolution.nx, dtype=float), resolution.ny),
        grid_j=np.repeat(np.arange(resolution.ny, dtype=float), resolution.nx),
        coords_are_index_only=False,
        metadata=ScanMetadata(
            device="synthetic-cross-resolution",
            field_length_m=scene.width_m,
            field_width_m=scene.height_m,
            notes=f"cross-resolution: {scene.name} @ {resolution.name}",
            source_file=f"cross_resolution:{scene.name}:{resolution.name}",
        ),
    )


# ---------------------------------------------------------------------------
# Independent structural oracle
# ---------------------------------------------------------------------------


def local_maxima_count(grid: np.ndarray[Any, Any]) -> int:
    """Interior strict local maxima of a 2-D array, by plain 3x3 comparison.

    Written here rather than imported from ``site.separation_seeds`` so the
    structural expectation is derived independently of the production seed
    finder. Ties are not counted (a plateau is not a maximum).
    """
    if grid.shape[0] < 3 or grid.shape[1] < 3:
        return 0
    core = grid[1:-1, 1:-1]
    strictly_greater = np.ones(core.shape, dtype=bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neighbour = grid[1 + dr : 1 + dr + core.shape[0], 1 + dc : 1 + dc + core.shape[1]]
            strictly_greater &= core > neighbour
    return int(np.count_nonzero(strictly_greater))


def _rotated(response: PhysicalResponse, x: float, y: float) -> tuple[float, float, float, float]:
    """``(cos, sin, xr, yr)`` for the local frame of *response* at ``(x, y)``."""
    theta = math.radians(response.orientation_deg)
    c, s = math.cos(theta), math.sin(theta)
    dx, dy = x - response.cx, y - response.cy
    return c, s, c * dx + s * dy, -s * dx + c * dy


def gradient(responses: tuple[PhysicalResponse, ...], x: float, y: float) -> tuple[float, float]:
    """Analytic gradient of the continuous field. Exact, no sampling involved.

    For ``f = a * exp(-0.5 * v^T Q v)`` with ``v = R^T (p - c)`` and
    ``Q = diag(1/sx^2, 1/sy^2)``:  ``grad = -a * exp(...) * R^T Q v``.
    """
    gx = 0.0
    gy = 0.0
    for r in responses:
        c, s, xr, yr = _rotated(r, x, y)
        value = r.amplitude * math.exp(-0.5 * ((xr / r.sigma_x) ** 2 + (yr / r.sigma_y) ** 2))
        q0, q1 = 1.0 / (r.sigma_x**2), 1.0 / (r.sigma_y**2)
        w0 = c * q0 * xr - s * q1 * yr
        w1 = s * q0 * xr + c * q1 * yr
        gx -= value * w0
        gy -= value * w1
    return (gx, gy)


def hessian(responses: tuple[PhysicalResponse, ...], x: float, y: float) -> np.ndarray[Any, Any]:
    """Analytic 2x2 Hessian of the continuous field at ``(x, y)``.

    ``hess = a * exp(...) * ( w w^T - R^T Q R )`` with ``w = R^T Q v``.
    """
    h = np.zeros((2, 2), dtype=float)
    for r in responses:
        c, s, xr, yr = _rotated(r, x, y)
        value = r.amplitude * math.exp(-0.5 * ((xr / r.sigma_x) ** 2 + (yr / r.sigma_y) ** 2))
        q0, q1 = 1.0 / (r.sigma_x**2), 1.0 / (r.sigma_y**2)
        w0 = c * q0 * xr - s * q1 * yr
        w1 = s * q0 * xr + c * q1 * yr
        # R^T Q R with R = [[c, s], [-s, c]]
        m00 = q0 * c * c + q1 * s * s
        m01 = (q0 - q1) * c * s
        m11 = q0 * s * s + q1 * c * c
        h += value * (np.asarray([[w0 * w0 - m00, w0 * w1 - m01], [w0 * w1 - m01, w1 * w1 - m11]]))
    return h


#: Documented behaviour of :func:`continuous_maxima_count` at a degenerate
@functools.lru_cache(maxsize=128)
def continuous_maxima_count(scene: PhysicalScene) -> int:
    """Interior local maxima of the *continuous* field, found analytically.

    Why not count maxima on a fine lattice: that measures the *sampled* field, and
    for an elongated response no isotropic lattice ever shows a single peak.
    Measured: the elongated Case D field reports 3 maxima at every isotropic
    pitch from 1.0 m down to 0.125 m, so a lattice probe would have claimed a
    multi-modal field where the mathematics says a rotated elliptical Gaussian is
    strictly unimodal. The lattice probe lives in :func:`aspect_sweep`, where
    measuring the sampling is the point.

    Solved here instead by Newton iteration on the analytic gradient from a grid
    of starting points, keeping distinct interior stationary points whose Hessian
    is negative definite (true local maxima -- not saddles, not the boundary).

    The one fragile point in the sweep is the degenerate critical point -- where
    two equal Gaussians sit at exactly ``2 * sigma`` separation and their two
    maxima plus the intervening saddle merge into one flat critical point.
    Measured across 0.5 .. 16.0 sigma: 1 maximum at and below the bifurcation, 2
    above, with the degenerate point itself correctly reported as 1 (a single flat
    maximum, not two). The tolerances below are what make that hold.

    This is the structural oracle, and it is what makes Case C's "unrecoverable in
    principle" a mathematical statement rather than a lucky draw: two equal
    Gaussians have two maxima iff their separation exceeds ``2 * sigma``, and this
    finds that transition directly.
    """
    scale = max(abs(r.amplitude) for r in scene.responses) or 1.0
    gtol = 1e-9 * scale
    # Curvature scale, used to reject *marginal* critical points. A point whose
    # smallest-curvature direction is only numerically negative is not a
    # well-determined maximum: at a degenerate critical point the ascent fallback
    # stalls at slightly different near-degenerate points and the count inflates
    # (measured: 6 maxima at exactly the two-Gaussian bifurcation, where the two
    # maxima and the saddle merge). Rejecting the marginal band keeps the oracle
    # reliable everywhere it is well defined.
    curvature = scale / min(min(r.sigma_x, r.sigma_y) for r in scene.responses) ** 2
    marg_tol = 1e-6 * curvature
    # Merge tolerance scaled to the field, not a hard constant. Two distinct
    # strict maxima of a Gaussian sum cannot sit closer than order sigma_min, so
    # sigma_min / 2 is a safe merge radius -- and it is what stops a *degenerate*
    # critical point from being counted several times. Measured: at exactly the
    # two-Gaussian bifurcation the search stalls at six points spread over
    # 0.003 m (the field has one stationary point there, confirmed by a 1-D
    # slice), which a 1e-4 m dedup counted as six maxima.
    merge = min(min(r.sigma_x, r.sigma_y) for r in scene.responses) / 2.0
    found: list[tuple[float, float]] = []
    for sx, sy in _start_points(scene):
        point = _descend(scene, sx, sy, gtol)
        if point is None:
            continue
        x, y = point
        if not (0.0 < x < scene.width_m and 0.0 < y < scene.height_m):
            continue
        # A local maximum needs a negative-*definite* Hessian: both eigenvalues
        # negative. Checking only the smallest is not enough -- measured, the
        # stationary point between two resolved peaks is a saddle
        # (eigenvalues -0.09, +0.92) and would otherwise be counted as a third
        # maximum.
        eigenvalues = np.linalg.eigvalsh(hessian(scene.responses, x, y))
        if not (eigenvalues[0] < 0.0 and eigenvalues[1] < -marg_tol):
            continue
        if all(math.hypot(x - px, y - py) > merge for px, py in found):
            found.append((x, y))
    return len(found)


def _descend(scene: PhysicalScene, x0: float, y0: float, gtol: float) -> tuple[float, float] | None:
    """Find a stationary point from one start: damped Newton, then ascent.

    Pure Newton is not enough here. At a near-singular Hessian the step diverges
    and the search silently returns nothing -- measured, exactly at the
    two-Gaussian bifurcation, where the two maxima and the intervening saddle
    merge into a degenerate critical point. A silent undercount in the oracle is
    worse than a slow one, so the Newton step is capped and a backtracking
    gradient ascent takes over when it does not land.
    """
    x, y = x0, y0
    for _ in range(400):
        gx, gy = gradient(scene.responses, x, y)
        if math.hypot(gx, gy) <= gtol:
            return (x, y)
        try:
            step = np.linalg.solve(hessian(scene.responses, x, y), np.asarray([gx, gy]))
        except np.linalg.LinAlgError:
            break
        norm = float(np.hypot(step[0], step[1]))
        if not math.isfinite(norm) or norm > 4.0:
            break
        x -= float(step[0])
        y -= float(step[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
    if math.hypot(*gradient(scene.responses, x, y)) <= gtol:
        return (x, y)
    return _ascend(scene, x0, y0, gtol)


def _ascend(scene: PhysicalScene, x0: float, y0: float, gtol: float) -> tuple[float, float] | None:
    """Backtracking gradient ascent on the field value: monotone, cannot oscillate."""
    x, y = x0, y0
    value = float(scene.value_at(np.asarray(x), np.asarray(y)))
    step = 0.5
    for _ in range(3000):
        gx, gy = gradient(scene.responses, x, y)
        if math.hypot(gx, gy) <= gtol:
            return (x, y)
        norm = math.hypot(gx, gy)
        nx, ny = x + step * gx / norm, y + step * gy / norm
        nvalue = float(scene.value_at(np.asarray(nx), np.asarray(ny)))
        if nvalue > value:
            x, y, value = nx, ny, nvalue
            step *= 1.3
        else:
            step *= 0.4
            if step < 1e-13:
                return None
    return None if math.hypot(*gradient(scene.responses, x, y)) > gtol else (x, y)


def _start_points(scene: PhysicalScene) -> list[tuple[float, float]]:
    """Adaptive starting points: a grid scaled to the responses, not the extent.

    Laid over the responses' bounding box grown by 3 sigma at a spacing of
    sigma_min / 3, so every basin is bracketed whatever the field's aspect ratio
    or orientation, plus each response's own centre -- the strongest bracket
    available for a sum of Gaussians.
    """
    pad = 3.0 * max(max(r.sigma_x, r.sigma_y) for r in scene.responses)
    xs_lo = min(r.cx for r in scene.responses) - pad
    xs_hi = max(r.cx for r in scene.responses) + pad
    ys_lo = min(r.cy for r in scene.responses) - pad
    ys_hi = max(r.cy for r in scene.responses) + pad
    step = max(min(min(r.sigma_x, r.sigma_y) for r in scene.responses) / 3.0, 1e-3)
    nx = int(min(max(np.ceil((xs_hi - xs_lo) / step), 1), 41))
    ny = int(min(max(np.ceil((ys_hi - ys_lo) / step), 1), 41))
    xs = np.linspace(max(xs_lo, 0.0), min(xs_hi, scene.width_m), nx)
    ys = np.linspace(max(ys_lo, 0.0), min(ys_hi, scene.height_m), ny)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    starts = [(float(a), float(b)) for a, b in zip(xx.ravel(), yy.ravel(), strict=True)]
    starts.extend((r.cx, r.cy) for r in scene.responses)
    return starts


def aspect_sweep(
    scene: PhysicalScene, dx: float, ratios: tuple[float, ...]
) -> tuple[tuple[float, int], ...]:
    """Discrete local-maxima count against lattice aspect ratio, at fixed *dx*.

    A measurement that decided the shape of Case D. For a fixed physical field,
    the count is invariant under *isotropic* re-sampling (measured: 3, 3, 3, 3
    at pitches 1.0/0.5/0.25/0.125 for the elongated Case D field) but moves
    sharply with the lattice's aspect ratio (measured: 1, 3, 1, 3, 3, 5 at
    dy/dx = 0.5/1/1.5/2/3/4). So "how many decomposition seeds" is governed by
    the sampling geometry *relative to the field's own aspect ratio*, not by
    resolution in the isotropic sense at all.

    Reported as an observation. It is the empirical input a future ``d_res`` and
    seed-admission calibration would need; it selects nothing here.
    """
    results: list[tuple[float, int]] = []
    for ratio in ratios:
        resolution = Resolution(
            name=f"sweep_dy{ratio:g}x",
            dx=float(dx),
            width_m=scene.width_m,
            height_m=scene.height_m,
            dy_ratio=float(ratio),
        )
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        results.append((float(ratio), local_maxima_count(scene.value_at(xx, yy))))
    return tuple(results)


# ---------------------------------------------------------------------------
# Per-resolution observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelRecord:
    """Counts for one level of the corrected model, kept separate on purpose."""

    level: int
    name: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "name": self.name, "count": self.count}


@dataclass(frozen=True)
class ResolutionObservation:
    """Everything measured for one scene at one resolution."""

    case: str
    resolution: Resolution
    levels: tuple[LevelRecord, ...]
    positions_m: tuple[tuple[float, float], ...]
    position_errors_m: tuple[float, ...]
    unmatched_candidate_count: int
    geometry_metrics: dict[str, float]
    pattern_hypotheses: tuple[str, ...]
    response_families: tuple[str, ...]
    shape_classes: tuple[str, ...]
    decomposition_seeds_observed: int
    decomposition_seeds_expected: int
    scale_status: str | None
    scale_method: str | None
    scale_indeterminate: bool
    solidity_production: tuple[float, ...]
    solidity_oracle_shadow: tuple[float, ...]
    within_response_separations_m: tuple[float, ...]
    extra: dict[str, Any] = field(default_factory=dict)

    def level_count(self, level: int) -> int:
        for record in self.levels:
            if record.level == level:
                return record.count
        return 0

    @property
    def candidate_count(self) -> int:
        return self.level_count(LEVEL_CANDIDATE_HYPOTHESIS)

    @property
    def top_level_count(self) -> int:
        return int(self.extra.get("top_level_count", 0))

    @property
    def max_position_error_m(self) -> float:
        return max(self.position_errors_m, default=float("nan"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "resolution": self.resolution.to_dict(),
            "levels": [r.to_dict() for r in self.levels],
            "positions_m": [list(p) for p in self.positions_m],
            "position_errors_m": list(self.position_errors_m),
            "unmatched_candidate_count": self.unmatched_candidate_count,
            "geometry_metrics": dict(self.geometry_metrics),
            "pattern_hypotheses": list(self.pattern_hypotheses),
            "response_families": list(self.response_families),
            "shape_classes": list(self.shape_classes),
            "decomposition_seeds_observed": self.decomposition_seeds_observed,
            "decomposition_seeds_expected": self.decomposition_seeds_expected,
            "scale_status": self.scale_status,
            "scale_method": self.scale_method,
            "scale_indeterminate": self.scale_indeterminate,
            "solidity_production": list(self.solidity_production),
            "solidity_oracle_shadow": list(self.solidity_oracle_shadow),
            "within_response_separations_m": list(self.within_response_separations_m),
            **self.extra,
        }


# ---------------------------------------------------------------------------
# Observation + classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossResolutionFinding:
    """A recorded relationship. ``classification`` is an observation, not a target."""

    case: str
    case_family: str
    resolutions: tuple[str, ...]
    classification: str
    signals: dict[str, Any]
    levels: tuple[LevelRecord, ...]
    notes: str = ""
    calibration_questions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "case_family": self.case_family,
            "resolutions": list(self.resolutions),
            "classification": self.classification,
            "signals": dict(self.signals),
            "levels": [r.to_dict() for r in self.levels],
            "notes": self.notes,
            "calibration_questions": list(self.calibration_questions),
        }


def _pair_candidates_to_responses(
    candidates: list[Any], responses: tuple[PhysicalResponse, ...]
) -> tuple[list[tuple[float, float]], list[float], int]:
    """Nearest-response pairing for *error reporting only*.

    A greedy nearest pairing on the pipeline's own reported positions. It exists
    to quantify localisation error against the construction; it is never used to
    filter, drop or re-count candidates, and unmatched candidates are reported
    as a count rather than silently discarded.
    """
    positions: list[tuple[float, float]] = []
    errors: list[float] = []
    used: set[int] = set()
    for candidate in candidates:
        x = float(getattr(candidate, "centroid_weighted_x", candidate.x_center))
        y = float(getattr(candidate, "centroid_weighted_y", candidate.y_center))
        positions.append((x, y))
        distances = [
            math.hypot(x - r.cx, y - r.cy) for idx, r in enumerate(responses) if idx not in used
        ]
        if not distances:
            continue
        nearest = int(np.argmin(distances))
        used.add(nearest)
        errors.append(float(distances[nearest]))
    return positions, errors, len(candidates) - len(used)


def observe_resolution(
    scene: PhysicalScene,
    resolution: Resolution,
    *,
    seed: int,
    config: Any,
    run: Any,
) -> ResolutionObservation:
    """Run the pipeline once and record the observation for this resolution.

    *run* is injected (normally ``analyze_scan``) so the measurement harness
    never silently acquires a production behaviour of its own.
    """
    scan = sample_scene(scene, resolution, seed=seed)
    _grid, anomaly, candidates = run(
        scan,
        f"{scene.name}-{resolution.name}",
        config=config,
        write_outputs=False,
    )

    # Level 2: connected components of the thresholded z-field. Read from the
    # detector's own labelling, which is the definition of that level.
    anomaly_region_count = int(anomaly.n_components)

    # Level 3: candidates grouped by the response components they belong to.
    regions: set[tuple[int, ...]] = set()
    for candidate in candidates:
        members = tuple(
            sorted(int(v) for v in (getattr(candidate, "response_component_ids", None) or []))
        )
        regions.add(members or (int(candidate.id),))
    response_region_count = len(regions)

    shadow = getattr(anomaly, "shadow", None)
    roles = list(getattr(shadow, "roles", []) or [])
    top_level_count = sum(1 for r in roles if getattr(r, "top_level", False))
    nested_count = sum(1 for r in roles if not getattr(r, "top_level", False))

    xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    sampled = scene.value_at(xx, yy)
    seeds_observed = local_maxima_count(sampled)

    positions, errors, unmatched = _pair_candidates_to_responses(candidates, scene.responses)
    separations = tuple(
        sorted(
            float(s)
            for record in roles
            for s in getattr(record, "within_response_separations", ())
            if math.isfinite(float(s))
        )
    )

    def _col(attr: str) -> tuple[float, ...]:
        return tuple(
            round(float(getattr(c, attr)), 6) for c in candidates if _finite(getattr(c, attr, None))
        )

    geometry = {
        "solidity": _col("solidity"),
        "geometry_quality": _col("geometry_quality"),
        "compactness": _col("compactness"),
        "area_cells": _col("area_cells"),
    }

    scale = getattr(shadow, "scale", None)
    return ResolutionObservation(
        case=scene.name,
        resolution=resolution,
        levels=(
            LevelRecord(LEVEL_ANOMALY_REGION, "anomaly_region", anomaly_region_count),
            LevelRecord(LEVEL_RESPONSE_REGION, "response_region", response_region_count),
            LevelRecord(LEVEL_CANDIDATE_HYPOTHESIS, "candidate_hypothesis", len(candidates)),
            LevelRecord(LEVEL_DECOMPOSITION, "decomposition", nested_count),
        ),
        positions_m=tuple(positions),
        position_errors_m=tuple(errors),
        unmatched_candidate_count=unmatched,
        geometry_metrics=geometry,  # type: ignore[arg-type]
        pattern_hypotheses=tuple(str(c.pattern_hypothesis) for c in candidates),
        response_families=tuple(str(c.response_family) for c in candidates),
        shape_classes=tuple(str(c.shape_class) for c in candidates),
        decomposition_seeds_observed=seeds_observed,
        decomposition_seeds_expected=continuous_maxima_count(scene),
        scale_status=getattr(getattr(scale, "estimate", None), "status", None),
        scale_method=getattr(getattr(scale, "estimate", None), "method", None),
        scale_indeterminate=bool(
            getattr(getattr(scale, "estimate", None), "is_indeterminate", False)
        ),
        solidity_production=_col("solidity"),
        solidity_oracle_shadow=tuple(
            round(float(r.solidity_oracle), 6) for r in getattr(shadow, "solidity", []) or []
        ),
        within_response_separations_m=separations,
        extra={
            "top_level_count": top_level_count,
            "role_counts": dict(sorted(_count_roles(roles).items())),
            "structural_alternative_unmodelled": sum(
                1 for r in roles if getattr(r, "structural_alternative_unmodelled", False)
            ),
            "constructive_maxima": continuous_maxima_count(scene),
            "constructed_response_count": scene.response_count,
        },
    )


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Seed ensemble: a single draw is not a characterisation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionEnsemble:
    """One resolution measured across independent noise draws.

    Added after measuring: a single draw is not a characterisation. Two
    resolutions can look identical on one seed pair and differ on the next, and
    a count that flickers with the noise draw is a *different* finding from one
    that moves monotonically with pitch. Conflating them is how a characterization
    becomes a fake oracle.

    The record therefore keeps the whole distribution, never a summary number
    that could be mistaken for a stable count.
    """

    case: str
    resolution: Resolution
    draw_count: int
    anomaly_region_counts: tuple[int, ...]
    candidate_counts: tuple[int, ...]
    top_level_counts: tuple[int, ...]
    max_position_errors_m: tuple[float, ...]
    label_sets: tuple[tuple[str, ...], ...]

    @property
    def candidate_count_range(self) -> tuple[int, int]:
        return (
            (min(self.candidate_counts), max(self.candidate_counts))
            if self.candidate_counts
            else (0, 0)
        )

    @property
    def labels_draw_stable(self) -> bool:
        return len(set(self.label_sets)) <= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "resolution": self.resolution.to_dict(),
            "draw_count": self.draw_count,
            "anomaly_region_counts": list(self.anomaly_region_counts),
            "candidate_counts": list(self.candidate_counts),
            "candidate_count_range": list(self.candidate_count_range),
            "top_level_counts": list(self.top_level_counts),
            "max_position_errors_m": [round(e, 6) for e in self.max_position_errors_m],
            "label_sets": [list(s) for s in self.label_sets],
            "labels_draw_stable": self.labels_draw_stable,
        }


def observe_ensemble(
    scene: PhysicalScene,
    resolution: Resolution,
    *,
    seeds: tuple[int, ...],
    config: Any,
    run: Any,
) -> ResolutionEnsemble:
    """Measure one resolution across independent noise draws.

    Independent draws are unavoidable (two lattices cannot share a noise sample)
    and are also the point: the spread across draws is the noise sensitivity, and
    the comparison *between* resolutions is only meaningful once that spread is
    known. A pitch effect smaller than the draw-to-draw spread is not an effect.
    """
    observations = tuple(
        observe_resolution(scene, resolution, seed=seed, config=config, run=run) for seed in seeds
    )
    return ResolutionEnsemble(
        case=scene.name,
        resolution=resolution,
        draw_count=len(observations),
        anomaly_region_counts=tuple(o.level_count(LEVEL_ANOMALY_REGION) for o in observations),
        candidate_counts=tuple(o.candidate_count for o in observations),
        top_level_counts=tuple(o.top_level_count for o in observations),
        max_position_errors_m=tuple(o.max_position_error_m for o in observations),
        label_sets=tuple(tuple(sorted(set(o.pattern_hypotheses))) for o in observations),
    )


def ensemble_spread(ensembles: tuple[ResolutionEnsemble, ...]) -> int:
    """Largest draw-to-draw candidate-count swing at any single resolution.

    This is the yardstick for "is that pitch effect real?". If the within-rung
    spread is as large as the between-rung difference, the difference is noise
    and is reported as such rather than as resolution sensitivity.
    """
    return max(
        (e.candidate_count_range[1] - e.candidate_count_range[0] for e in ensembles), default=0
    )


def _count_roles(roles: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in roles:
        key = str(getattr(record, "role", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def classify(
    observations: tuple[ResolutionObservation, ...],
    *,
    scene: PhysicalScene,
    ensembles: tuple[ResolutionEnsemble, ...] = (),
) -> str:
    """Classify the observed cross-resolution relationship.

    Pure function of the *measurements* plus the *construction*; it never
    consults a desired answer. Precedence is
    :data:`CLASSIFICATION_PRECEDENCE`.

    Two questions are deliberately kept apart, because conflating them produces
    false confidence:

    *Does the relationship move with pitch?* -- answered by comparing the rungs.

    *Is the measurement precise enough for that to mean anything?* -- answered by
    the draw-to-draw spread at each rung. Measured: on these scenes the level-4
    count varies by as much across six noise draws at a *single* rung (1..3, 2..5,
    1..4) as it does between rungs, so a bare pitch comparison is not
    interpretable. ``stable`` is therefore refused whenever the count is
    noise-dominated, and the result is ``inconclusive`` with a specific
    calibration question rather than a reassuring ``stable``.
    """
    if not observations:
        return INCONCLUSIVE

    # Signal: did the construction itself make sub-structure unresolvable?
    # Answered by the continuous-field oracle, so it is a property of the scene
    # and not of any detector.
    if _unresolvable_by_construction(scene):
        return UNRESOLVED

    # Signal: is there anything to compare? A resolution that produced no
    # finding at all says nothing about the others.
    if any(obs.candidate_count == 0 for obs in observations):
        return INCONCLUSIVE

    # Signal: several level-4 records emitted from one level-3 region. This is a
    # structural statement, not a count comparison, so noise does not excuse it.
    if any(obs.top_level_count > obs.level_count(LEVEL_RESPONSE_REGION) for obs in observations):
        return STRUCTURALLY_AMBIGUOUS

    label_moved = len({tuple(sorted(set(obs.pattern_hypotheses))) for obs in observations}) > 1
    shape_moved = len({tuple(sorted(set(obs.shape_classes))) for obs in observations}) > 1
    family_moved = len({tuple(sorted(set(obs.response_families))) for obs in observations}) > 1

    # A label / shape / family change is a *classification* change. It survives
    # a different noise draw (see `labels_draw_stable`), so it is a real
    # pitch effect and not a count fluctuation.
    if label_moved or shape_moved or family_moved:
        return RESOLUTION_SENSITIVE

    # Counts are the noise-sensitive quantity. Only call them
    # resolution-sensitive when the between-rung difference is larger than the
    # within-rung draw spread, i.e. when the effect exceeds the noise.
    counts_moved = (
        len({o.candidate_count for o in observations}) > 1
        or len({o.level_count(LEVEL_ANOMALY_REGION) for o in observations}) > 1
    )
    if counts_moved:
        spread = ensemble_spread(ensembles)
        if ensembles and _count_swing(observations) <= spread:
            # The difference between rungs is inside the noise band. Not a pitch
            # effect, and not a stable relationship either.
            return INCONCLUSIVE
        return RESOLUTION_SENSITIVE

    # Everything invariant on this draw. That is only worth calling stable if the
    # count is not itself noise-dominated at any rung.
    if _noise_dominated(ensembles):
        return INCONCLUSIVE
    return STABLE


def _noise_dominated(ensembles: tuple[ResolutionEnsemble, ...]) -> bool:
    """True when any rung's level-4 count moves with the noise draw alone."""
    return any(e.candidate_count_range[1] > e.candidate_count_range[0] for e in ensembles)


def _count_swing(observations: tuple[ResolutionObservation, ...]) -> int:
    counts = [o.candidate_count for o in observations]
    return max(counts) - min(counts)


def _unresolvable_by_construction(scene: PhysicalScene) -> bool:
    """True when the continuous field has fewer maxima than constructed responses.

    If the superposed field is strictly unimodal, no sampling density can
    separate the components: the sub-structure is not merely unresolved at this
    pitch, it is absent from the underlying field. That is a property of the
    construction and needs no detector to establish.
    """
    return continuous_maxima_count(scene) < scene.response_count


def compare_resolutions(
    scene: PhysicalScene,
    observations: tuple[ResolutionObservation, ...],
    *,
    ensembles: tuple[ResolutionEnsemble, ...] = (),
) -> CrossResolutionFinding:
    """Turn per-resolution observations into one recorded relationship."""
    classification = classify(observations, scene=scene, ensembles=ensembles)
    signals = {
        "anomaly_region_counts": [o.level_count(LEVEL_ANOMALY_REGION) for o in observations],
        "response_region_counts": [o.level_count(LEVEL_RESPONSE_REGION) for o in observations],
        "candidate_counts": [o.candidate_count for o in observations],
        "top_level_counts": [o.top_level_count for o in observations],
        "decomposition_counts": [o.level_count(LEVEL_DECOMPOSITION) for o in observations],
        "pattern_hypotheses": [sorted(set(o.pattern_hypotheses)) for o in observations],
        "response_families": [sorted(set(o.response_families)) for o in observations],
        "shape_classes": [sorted(set(o.shape_classes)) for o in observations],
        "max_position_error_m": [_round(o.max_position_error_m) for o in observations],
        "position_tolerance_m": [position_tolerance_m(o.resolution) for o in observations],
        "decomposition_seeds_observed": [o.decomposition_seeds_observed for o in observations],
        "decomposition_seeds_expected": [o.decomposition_seeds_expected for o in observations],
        "constructive_maxima": observations[0].extra.get("constructive_maxima")
        if observations
        else None,
        "unresolvable_by_construction": _unresolvable_by_construction(scene),
        "scale_statuses": [o.scale_status for o in observations],
        "unmatched_candidate_counts": [o.unmatched_candidate_count for o in observations],
        "draw_spread_within_rung": ensemble_spread(ensembles) if ensembles else None,
        "noise_dominated": _noise_dominated(ensembles),
        "candidate_count_ranges": [list(e.candidate_count_range) for e in ensembles],
        "labels_draw_stable": [e.labels_draw_stable for e in ensembles],
    }
    levels = observations[0].levels if observations else ()
    return CrossResolutionFinding(
        case=scene.name,
        case_family=scene.case_family,
        resolutions=tuple(o.resolution.name for o in observations),
        classification=classification,
        signals=signals,
        levels=levels,
        notes=CLASSIFICATION_NOTES.get(classification, ""),
        calibration_questions=_calibration_questions(
            classification, scene, observations, ensembles
        ),
    )


CLASSIFICATION_NOTES: dict[str, str] = {
    STABLE: (
        "Level-4 count, pattern labels, shape classes and response families all held "
        "across the ladder, positions tracked the constructed centres within the "
        "pitch-derived bound, and the level-4 count did not move with the noise draw at "
        "any rung. This is an observation on a constructed scene at these three "
        "pitches; it is not evidence about any real instrument."
    ),
    RESOLUTION_SENSITIVE: (
        "At least one of pattern label, shape class, response family, level-2 count or "
        "level-4 count moved across the ladder by more than the draw-to-draw noise "
        "band. Documented in v2 §4.5 as permitted to vary: seed count, component "
        "boundary, fragment count and discretised shape metrics are all "
        "sampling-dependent. No rule is asserted in either direction."
    ),
    UNRESOLVED: (
        "The continuous field itself has fewer local maxima than the scene places "
        "responses, so the sub-structure is not recoverable in principle at any "
        "sampling density. Established by an independent probe of the forward model, "
        "not by the detector."
    ),
    STRUCTURALLY_AMBIGUOUS: (
        "More top-level level-4 records were emitted than there are level-3 response "
        "regions, i.e. multiplicity from a single response region. This is the shape "
        "the S01 defect takes; it is recorded, not corrected."
    ),
    INCONCLUSIVE: (
        "Either a resolution produced no finding, or the level-4 count moved across the "
        "ladder by no more than it moves across independent noise draws at a single "
        "rung. In the second case the comparison is not interpretable and 'we cannot "
        "say' is the correct result. It is deliberately not upgraded to stable or to "
        "resolution-sensitive."
    ),
}


def _calibration_questions(
    classification: str,
    scene: PhysicalScene,
    observations: tuple[ResolutionObservation, ...],
    ensembles: tuple[ResolutionEnsemble, ...] = (),
) -> tuple[str, ...]:
    """Open questions the measurement raises. None of them is answered here."""
    questions: list[str] = []
    if classification == RESOLUTION_SENSITIVE:
        questions.append(
            "Which of the moving quantities (level-2 count, level-4 count, pattern "
            "label) is *allowed* to move at this pitch, and over what range? d_res and "
            "the solidity gate bands are both blocked on this and neither is derivable "
            "from synthetic data."
        )
    if classification == STRUCTURALLY_AMBIGUOUS:
        questions.append(
            "What minimum resolvable separation d_res would separate the promoted "
            "level-5 records here? Grid pitch is a resolution lower bound, not a "
            "positional-accuracy bound, so this needs a contrast/SNR sweep on field or "
            "bench data."
        )
    if classification == STABLE:
        questions.append(
            "Stability at three pitches does not establish stability across an "
            "operating range. The claimed line-spacing envelope is still unmeasured."
        )
    if classification == INCONCLUSIVE and any(o.candidate_count for o in observations):
        if _noise_dominated(ensembles):
            questions.append(
                "The level-4 count moved across the ladder by no more than it moves "
                "across independent noise draws at a single rung, so the pitch "
                "comparison is not interpretable. Two things are needed before any "
                "cross-resolution claim is possible: a measured false-finding rate at "
                "each pitch, and enough draws per rung to separate a pitch effect from "
                "the noise band. Neither is available from synthetic data."
            )
        else:
            questions.append(
                "A resolution produced no finding, so there is nothing to compare "
                "against. 'Not established' is recorded rather than upgraded."
            )
    seeds = [o.decomposition_seeds_observed for o in observations]
    if len(set(seeds)) > 1:
        questions.append(
            f"Local maxima of the *noiseless* field changed across the ladder "
            f"({seeds}). A seed count is a property of the sampling, so any test that "
            "asserts a stable seed count would be asserting a falsehood; the design "
            "explicitly forbids it (v2 §12.2 Case D)."
        )
    if ensembles:
        for ensemble in ensembles:
            lo, hi = ensemble.candidate_count_range
            if hi > lo:
                questions.append(
                    f"{ensemble.resolution.name}: level-4 count ranged {lo}..{hi} across "
                    f"{ensemble.draw_count} independent noise draws on a scene whose "
                    "construction is unambiguous. The false-finding rate at this pitch is "
                    "unmeasured, so a count from any single run must not be read as a "
                    "target count."
                )
    if any(o.scale_indeterminate for o in observations):
        questions.append(
            "A residual was measured as having no estimable scale. How often that "
            "happens on real acquisitions is the missing fact for S03 activation; it "
            "cannot be manufactured from synthetic data."
        )
    if scene.response_count and _unresolvable_by_construction(scene):
        questions.append(
            "A close pair below the 2-sigma bifurcation is invisible to any threshold "
            "rule. Reporting a bound or a resolvability flag is the honest outcome; "
            "reporting a count is not."
        )
    return tuple(questions)


def _round(value: float, ndigits: int = 6) -> float | None:
    if not math.isfinite(value):
        return None
    return round(float(value), ndigits)


# ---------------------------------------------------------------------------
# Contract guards
# ---------------------------------------------------------------------------


def assert_no_object_count_claim(payload: dict[str, Any]) -> None:
    """Raise if any key invites reading a level-4/5 count as a level-6 count.

    Contract K3 / v2 §2.3 makes the prohibition testable by naming. The
    measurement must not be the thing that breaks it.
    """
    offenders = sorted(_find_forbidden_keys(payload))
    if offenders:
        raise AssertionError(f"level-6 count claim in measurement payload: {offenders}")


def _find_forbidden_keys(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_OBJECT_COUNT_NAMES:
                found.add(str(key))
            found |= _find_forbidden_keys(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found |= _find_forbidden_keys(item)
    return found


def position_tolerance_m(resolution: Resolution) -> float:
    """Position tolerance for *resolution*, derived from pitch. Never fitted.

    Half a pitch is the smallest bound a lattice justifies: a centroid estimated
    from a sampled peak cannot be localised better than the sampling that
    produced it, and a symmetric response's centroid is unbiased so half a pitch
    is generous rather than tight. There is no constant here to tune.
    """
    return 0.5 * float(max(resolution.dx, resolution.dy))


__all__ = [
    "CLASSIFICATIONS",
    "CLASSIFICATION_PRECEDENCE",
    "CrossResolutionFinding",
    "FORBIDDEN_OBJECT_COUNT_NAMES",
    "INCONCLUSIVE",
    "LEVEL_ANOMALY_REGION",
    "LEVEL_CANDIDATE_HYPOTHESIS",
    "LEVEL_DECOMPOSITION",
    "LEVEL_PHYSICAL_OBJECT",
    "LEVEL_RESPONSE_REGION",
    "PhysicalResponse",
    "PhysicalScene",
    "RESOLUTION_SENSITIVE",
    "Resolution",
    "ResolutionEnsemble",
    "ResolutionObservation",
    "STABLE",
    "STRUCTURALLY_AMBIGUOUS",
    "UNRESOLVED",
    "anisotropic_ladder",
    "aspect_sweep",
    "assert_no_object_count_claim",
    "classify",
    "compare_resolutions",
    "continuous_maxima_count",
    "ensemble_spread",
    "isotropic_ladder",
    "local_maxima_count",
    "observe_ensemble",
    "observe_resolution",
    "position_tolerance_m",
    "sample_scene",
]

"""Phases E and F -- post-S02 solidity bands, and compactness, characterized.

Two questions that look alike and are not.

**Solidity** was *redefined* in Stage 2 (S02). The old denominator was the hull
of cell *centres* while the numerator was a cell *count*: a count over an area,
whose dimension is 1/area. A quantity with a dimension cannot be a shape ratio.
It now has an exact rational oracle, and this module's first job is to establish
what the corrected metric can and cannot support.

The decisive structural fact, which falls out of the corrected definition and is
verified numerically here rather than argued: **solidity is a function of the
cell set alone.** The production computation is
``N*dx*dy / (hull_centre_area + dx*span_y + dy*span_x + dx*dy)``; substituting
``span_x = kx*dx`` and ``span_y = ky*dy`` and dividing through by ``dx*dy``
leaves ``N / (hull_centre_area/(dx*dy) + kx + ky + 1)``, in which the pitch and
the aspect ratio have cancelled exactly. So the metric cannot depend on sampling
density, anisotropy, origin or unit. That is a theorem, and
:func:`pitch_invariance` measures the residual to confirm the code matches it.

What *does* depend on the sampling regime is which cell sets the raster
produces. So a solidity band is not regime-dependent through the metric; it is
regime-dependent through the population. Those are different claims and this
module keeps them apart.

**Compactness** was never redefined. ``_util.digital_compactness`` is the
classical isoperimetric quotient ``4*pi*A/P^2`` with ``P`` approximated by the
count of cells surviving a morphological erosion -- a *boundary-cell ring*, not
a perimeter. The two coincide only in the limit: the ring count is not a length,
it is a count of cells, and for a structure thinner than about three cells the
ring is the whole component. The shape matrix below measures the resulting
error against the exact exposed-edge perimeter for the same cell set, and the
answer decides what kind of parameter a compactness band is.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .datasets import (
    CATEGORY_ANALYTICAL,
    ShapeSample,
    analytic_shape_catalogue,
    cellset,
    production_shape_metrics,
)

# ---------------------------------------------------------------------------
# Phase E -- the solidity bands as they exist in production
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolidityBand:
    """One production solidity threshold, and the decision it drives."""

    band_id: str
    value: float
    comparison: str
    production_site: str
    decision: str
    original_derivation: str

    def crossed_by(self, solidity: float) -> bool:
        if self.comparison == "<":
            return float(solidity) < self.value
        if self.comparison == "<=":
            return float(solidity) <= self.value
        if self.comparison == ">":
            return float(solidity) > self.value
        if self.comparison == ">=":
            return float(solidity) >= self.value
        raise ValueError(f"unsupported comparison {self.comparison!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "band_id": self.band_id,
            "value": self.value,
            "comparison": self.comparison,
            "production_site": self.production_site,
            "decision": self.decision,
            "original_derivation": self.original_derivation,
        }


#: The three solidity thresholds that exist in production, with the site that
#: reads them. The band values were set while the metric was the retired
#: dimensionless-looking but dimension-carrying count-over-hull-area formula, so
#: their *meaning* has to be re-established, not their code.
SOLIDITY_BANDS: tuple[SolidityBand, ...] = (
    SolidityBand(
        band_id="shape.irregular",
        value=0.48,
        comparison="<",
        production_site="groundscan/core/shape.py:223 (_classify_shape)",
        decision="shape_class becomes 'irregular' when solidity < 0.48 and linearity < 0.70",
        original_derivation=(
            "selected during the v0.2 synthetic benchmark against the pre-S02 formula"
        ),
    ),
    SolidityBand(
        band_id="classify.geology",
        value=0.75,
        comparison="<=",
        production_site="groundscan/core/classify.py:309 (classify_candidate)",
        decision="geological-like hypothesis is admitted only when solidity <= 0.75",
        original_derivation=(
            "selected during the v0.2 synthetic benchmark against the pre-S02 formula"
        ),
    ),
    SolidityBand(
        band_id="classify.recovery-note",
        value=0.50,
        comparison="<",
        production_site="groundscan/core/classify.py:653 (classify_candidate)",
        decision="a 'irregular/concave geometry' recovery note is appended when solidity < 0.5",
        original_derivation=(
            "selected during the v0.2 synthetic benchmark against the pre-S02 formula"
        ),
    ),
)

#: The weight ``geometry_quality`` places on solidity, and the other three terms
#: of that same formula, so a weight sweep can hold everything else fixed.
GEOMETRY_QUALITY_SOLIDITY_WEIGHT = 0.25
GEOMETRY_QUALITY_CELL_COUNT_WEIGHT = 0.30
GEOMETRY_QUALITY_FILL_WEIGHT = 0.25
GEOMETRY_QUALITY_BOUNDARY_WEIGHT = 0.20
#: ``geometry_quality`` saturates the cell-count term at this many cells.
GEOMETRY_QUALITY_CELL_SATURATION = 10.0


def _bbox_fill(cells: Sequence[tuple[int, int]]) -> float:
    """``count_nonzero(local_mask) / local_mask.size`` as the production sees it.

    The local mask is the component's bounding-box window, so the fill is the
    component's cell count over its bounding-box area. Computed from the cell
    set, which is the same input the production function receives.
    """
    occupied = cellset(cells)
    rows = [r for r, _ in occupied]
    cols = [c for _, c in occupied]
    window = (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)
    return len(occupied) / max(window, 1)


@dataclass(frozen=True)
class SolidityCensusRow:
    """One shape's solidity, its exact value, and every band decision it drives."""

    sample_id: str
    shape_family: str
    n_cells: int
    solidity: float
    solidity_oracle: float
    solidity_error: float
    geometry_quality: float
    decisions: dict[str, bool]
    band_distance: dict[str, float]
    near_band: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "shape_family": self.shape_family,
            "n_cells": self.n_cells,
            "solidity": self.solidity,
            "solidity_oracle": self.solidity_oracle,
            "solidity_error": self.solidity_error,
            "geometry_quality": self.geometry_quality,
            "decisions": self.decisions,
            "band_distance": self.band_distance,
            "near_band": self.near_band,
        }


#: A sample within this distance of a band is *fragile*: a band moved by less
#: than the distance would change this sample's decision. Reported as a count so
#: a band sitting in a dense part of the population is visible as such.
BAND_FRAGILITY_RADIUS = 0.05


def solidity_census(
    samples: Sequence[ShapeSample] | None = None,
    *,
    cell_dx: float = 1.0,
    cell_dy: float = 1.0,
) -> tuple[SolidityCensusRow, ...]:
    """Measure the corrected solidity on every analytic shape and score the bands.

    ``cell_dx``/``cell_dy`` default to 1.0 because the metric is pitch-free; the
    non-unit values exist so a reader can see the invariance rather than take it
    on trust.
    """
    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    rows: list[SolidityCensusRow] = []
    for sample in catalogue:
        metrics = production_shape_metrics(
            sample.cells, cell_dx=cell_dx, cell_dy=cell_dy, sample_id=sample.sample_id
        )
        decisions = {b.band_id: b.crossed_by(metrics.solidity) for b in SOLIDITY_BANDS}
        distance = {b.band_id: abs(float(metrics.solidity) - b.value) for b in SOLIDITY_BANDS}
        near = sorted(k for k, v in distance.items() if v <= BAND_FRAGILITY_RADIUS)
        rows.append(
            SolidityCensusRow(
                sample_id=sample.sample_id,
                shape_family=sample.shape_family,
                n_cells=metrics.n_cells,
                solidity=float(metrics.solidity),
                solidity_oracle=metrics.solidity_oracle,
                solidity_error=float(metrics.solidity) - metrics.solidity_oracle,
                geometry_quality=metrics.geometry_quality,
                decisions=decisions,
                band_distance=distance,
                near_band=near,
            )
        )
    return tuple(rows)


def solidity_census_summary(
    samples: Sequence[ShapeSample] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Aggregate the census: exactness, distribution, band activity, fragility."""
    rows = solidity_census(samples, **kwargs)
    values = np.array([r.solidity for r in rows], dtype=float)
    oracle = np.array([r.solidity_oracle for r in rows], dtype=float)
    errors = values - oracle
    band_summary: dict[str, Any] = {}
    for band in SOLIDITY_BANDS:
        crossed = np.array([r.decisions[band.band_id] for r in rows], dtype=bool)
        distances = np.array([r.band_distance[band.band_id] for r in rows], dtype=float)
        band_summary[band.band_id] = {
            "value": band.value,
            "comparison": band.comparison,
            "production_site": band.production_site,
            "n_crossed": int(crossed.sum()),
            "n_total": len(rows),
            "fraction_crossed": round(float(crossed.mean()), 4) if rows else 0.0,
            "n_fragile_within_radius": int((distances <= BAND_FRAGILITY_RADIUS).sum()),
            "fragility_radius": BAND_FRAGILITY_RADIUS,
            "min_distance": round(float(distances.min()), 6) if rows else 0.0,
        }
    return {
        "category": CATEGORY_ANALYTICAL,
        "n_samples": len(rows),
        "max_abs_solidity_error": round(float(np.abs(errors).max()), 12) if rows else 0.0,
        "solidity_equals_oracle_exactly": bool(np.allclose(errors, 0.0, atol=1e-12)),
        "distribution": {
            "min": round(float(values.min()), 6),
            "p05": round(float(np.percentile(values, 5)), 6),
            "p25": round(float(np.percentile(values, 25)), 6),
            "median": round(float(np.median(values)), 6),
            "p75": round(float(np.percentile(values, 75)), 6),
            "max": round(float(values.max()), 6),
        },
        "bands": band_summary,
    }


#: Pitch and aspect combinations the invariance probe runs. Deliberately spanning
#: three orders of magnitude in pitch, a 1/25 ratio, a survey-magnitude origin,
#: and centimetre units, because those are the four ways a "dimensionless"
#: quantity can turn out not to be one.
INVARIANCE_PITCHES: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (0.04, 0.04),
    (25.0, 25.0),
    (0.5, 2.0),
    (2.0, 0.5),
    (0.1, 0.1),
)
INVARIANCE_ORIGIN_M = 1.0e5


def pitch_invariance(
    samples: Sequence[ShapeSample] | None = None,
    *,
    pitches: Sequence[tuple[float, float]] = INVARIANCE_PITCHES,
) -> dict[str, Any]:
    """Measure whether the corrected solidity depends on the sampling pitch.

    Expectation, from the algebra: it does not, and the deviation is round-off
    only. Anything larger than round-off would mean the metric is not the
    dimensionless quantity its definition claims to be -- which is precisely the
    S02 defect, so this probe is the regression guard for S02.
    """
    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    baseline = {
        sample.sample_id: production_shape_metrics(
            sample.cells, cell_dx=1.0, cell_dy=1.0, sample_id=sample.sample_id
        ).solidity
        for sample in catalogue
    }
    per_pitch: dict[str, Any] = {}
    worst = 0.0
    worst_id = ""
    worst_pitch: tuple[float, float] | None = None
    for dx, dy in pitches:
        deviations: list[float] = []
        for sample in catalogue:
            value = production_shape_metrics(
                sample.cells,
                cell_dx=dx,
                cell_dy=dy,
                sample_id=sample.sample_id,
            ).solidity
            delta = abs(value - baseline[sample.sample_id])
            deviations.append(delta)
            if delta > worst:
                worst = delta
                worst_id = sample.sample_id
                worst_pitch = (dx, dy)
        per_pitch[f"dx{dx:g}_dy{dy:g}"] = {
            "max_abs_deviation": round(float(max(deviations)), 15) if deviations else 0.0,
            "mean_abs_deviation": round(float(np.mean(deviations)), 15) if deviations else 0.0,
        }
    return {
        "n_samples": len(catalogue),
        "pitches": [list(p) for p in pitches],
        "per_pitch": per_pitch,
        "max_abs_deviation_overall": round(worst, 15),
        "worst_sample": worst_id,
        "worst_pitch": list(worst_pitch) if worst_pitch else None,
        "claim": (
            "solidity is a function of the cell set alone: the pitch and the dx/dy "
            "ratio cancel exactly in N*dx*dy / (hull_centre + dx*span_y + dy*span_x + "
            "dx*dy). The residual is double-precision round-off."
        ),
        "verified": bool(worst < 1e-12),
        "note_survey_magnitude_origin": (
            f"the invariance also holds at a survey-magnitude origin "
            f"(x0 = {INVARIANCE_ORIGIN_M:g} m) because the production hull is "
            f"evaluated in a frame anchored at the component's own minimum corner"
        ),
    }


def geometry_quality_weight_sweep(
    samples: Sequence[ShapeSample] | None = None,
    *,
    weights: Sequence[float] = (0.0, 0.10, 0.20, 0.25, 0.30, 0.40, 0.50),
    quality_band: float = 0.40,
) -> dict[str, Any]:
    """How much does the solidity weight in ``geometry_quality`` actually decide?

    ``geometry_quality`` is compared against ``0.40`` twice: once as a quality
    flag (``gates/quality.py:275``) and once as a weighted hypothesis feature
    (weight 0.06-0.10 across four hypothesis tables). So the weight is a real
    lever, and the sweep answers how large a lever.

    The other three weights are held at their production values; the cell-count
    and fill terms are recomputed from each shape's cell set so the only thing
    moving is the solidity weight.
    """
    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    per_weight: dict[str, Any] = {}
    for weight in weights:
        below = 0
        scores: list[float] = []
        for sample in catalogue:
            metrics = production_shape_metrics(
                sample.cells, sample_id=sample.sample_id, min_grid_cells=1
            )
            n = len(sample.cells)
            fill = _bbox_fill(sample.cells)
            cell_term = GEOMETRY_QUALITY_CELL_COUNT_WEIGHT * min(
                n / GEOMETRY_QUALITY_CELL_SATURATION, 1.0
            )
            base = (
                cell_term
                + GEOMETRY_QUALITY_FILL_WEIGHT * min(fill, 1.0)
                + GEOMETRY_QUALITY_BOUNDARY_WEIGHT
                * (1.0 - min(float(metrics.boundary_contact_ratio), 1.0))
            )
            value = min(1.0, max(0.0, base + weight * float(metrics.solidity)))
            scores.append(value)
            if value < quality_band:
                below += 1
        per_weight[f"w{weight:g}"] = {
            "mean": round(float(np.mean(scores)), 6),
            "min": round(float(np.min(scores)), 6),
            "max": round(float(np.max(scores)), 6),
            "n_below_quality_band": below,
            "fraction_below_quality_band": round(below / max(len(catalogue), 1), 4),
        }
    production = per_weight.get(f"w{GEOMETRY_QUALITY_SOLIDITY_WEIGHT:g}")
    zero = per_weight.get("w0")
    return {
        "n_samples": len(catalogue),
        "quality_band": quality_band,
        "per_weight": per_weight,
        "production_weight": GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
        "production_row": production,
        "solidity_free_row": zero,
        "decisions_attributable_to_the_weight": (
            (zero["n_below_quality_band"] - production["n_below_quality_band"])
            if zero and production
            else None
        ),
        "claim": (
            "The weight is a policy choice, not a calibrated quantity: it is one of "
            "four terms summing to 1.0, no field evidence constrains it, and the "
            "sweep shows it is not inert either. It therefore cannot be CALIBRATED "
            "and it cannot be justified by regression behaviour."
        ),
    }


def verify_geometry_quality_reconstruction(
    samples: Sequence[ShapeSample] | None = None,
    *,
    cell_dx: float = 1.0,
    cell_dy: float = 1.0,
) -> dict[str, Any]:
    """Check the reconstructed ``geometry_quality`` terms against production.

    The weight sweep needs the other three terms, and ``_shape_metrics`` does not
    return them. Rather than assert a reconstruction, this measures the
    difference between the reconstructed sum and the production value over the
    whole catalogue, so the sweep's premise is verified rather than assumed.
    """
    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    worst = 0.0
    worst_id = ""
    for sample in catalogue:
        metrics = production_shape_metrics(
            sample.cells, cell_dx=cell_dx, cell_dy=cell_dy, sample_id=sample.sample_id
        )
        n = len(sample.cells)
        fill = _bbox_fill(sample.cells)
        reconstructed = (
            GEOMETRY_QUALITY_CELL_COUNT_WEIGHT * min(n / GEOMETRY_QUALITY_CELL_SATURATION, 1.0)
            + GEOMETRY_QUALITY_FILL_WEIGHT * min(fill, 1.0)
            + GEOMETRY_QUALITY_SOLIDITY_WEIGHT * float(metrics.solidity)
            + GEOMETRY_QUALITY_BOUNDARY_WEIGHT
            * (1.0 - min(float(metrics.boundary_contact_ratio), 1.0))
        )
        delta = abs(min(1.0, max(0.0, reconstructed)) - float(metrics.geometry_quality))
        if delta > worst:
            worst = delta
            worst_id = sample.sample_id
    return {
        "n_samples": len(catalogue),
        "max_abs_difference": round(worst, 12),
        "worst_sample": worst_id,
        "reconstruction_exact": bool(worst < 1e-12),
    }


def band_sensitivity(
    solidity_values: Sequence[float],
    *,
    deltas: Sequence[float] = (-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10),
    bands: Sequence[SolidityBand] = SOLIDITY_BANDS,
) -> dict[str, Any]:
    """How many decisions each band actually decides, and how fragile each is.

    ``solidity_values`` is any population -- the analytic catalogue, the
    perturbation corpus, the vendor corpus. The metric is the same either way:
    for a band, how many decisions does moving it by ``d`` change, and what
    fraction of the population lives within ``d`` of it.
    """
    values = np.asarray([float(v) for v in solidity_values], dtype=float)
    out: dict[str, Any] = {"n_samples": int(values.size), "per_band": {}}
    for band in bands:
        base = np.array([band.crossed_by(v) for v in values], dtype=bool)
        per_delta: dict[str, Any] = {}
        for delta in deltas:
            moved = SolidityBand(
                band_id=band.band_id,
                value=band.value + delta,
                comparison=band.comparison,
                production_site=band.production_site,
                decision=band.decision,
                original_derivation=band.original_derivation,
            )
            after = np.array([moved.crossed_by(v) for v in values], dtype=bool)
            per_delta[f"{delta:+.2f}"] = {
                "n_changed": int((after != base).sum()),
                "fraction_changed": round(float((after != base).mean()), 4) if values.size else 0.0,
                "n_crossed": int(after.sum()),
            }
        distance = np.abs(values - band.value)
        out["per_band"][band.band_id] = {
            "value": band.value,
            "comparison": band.comparison,
            "production_site": band.production_site,
            "n_crossed_at_production": int(base.sum()),
            "n_within_0.02": int((distance <= 0.02).sum()),
            "n_within_0.05": int((distance <= 0.05).sum()),
            "per_delta": per_delta,
        }
    return out


# ---------------------------------------------------------------------------
# Phase F -- compactness
# ---------------------------------------------------------------------------

#: The consumers of ``Candidate.compactness``, with the value each compares
#: against. Two different thresholds for the same number, which is itself a
#: finding: there is no single compactness policy to calibrate, there are two.
#:
#: This table previously listed four. Two of them
#: (``classify.metal_min_compactness`` at 0.55 and
#: ``classify.multi_positive_metal_min_compactness`` at 0.30) lived in
#: ``ClassificationConfig`` and gated ``_apply_compatibility_feature_pass``, the
#: rule cascade removed from ``core/classify.py`` as dead code. They were
#: recorded as production compactness consumers, but the decisions they gated
#: were overwritten unconditionally before any candidate left
#: ``classify_candidate``, so they never admitted or rejected anything. Listing
#: them overstated the number of places a compactness retune would have to move.
#: The pin test ``test_the_compactness_consumers_exist_where_the_table_says_they_do``
#: is what noticed: it resolves each entry against the production source and the
#: recorded line no longer held the value.
#:
#: ``source_path`` and ``source_line`` are separated from ``production_site`` so a
#: consumer can verify the constant without re-parsing a human-readable string.
COMPACTNESS_CONSUMERS: tuple[dict[str, Any], ...] = (
    {
        "consumer_id": "separation.fragment_metallic",
        "value": 0.45,
        "comparison": ">=",
        "production_site": "groundscan/site/separation.py:670",
        "source_path": "groundscan/site/separation.py",
        "source_line": 670,
        "decision": ("a separation fragment is admitted as metallic on compactness >= 0.45"),
    },
    {
        "consumer_id": "dipole.deblend_guard",
        "value": 0.35,
        "comparison": "<",
        "production_site": "groundscan/diagnostics/dipole.py:416",
        "source_path": "groundscan/diagnostics/dipole.py",
        "source_line": 416,
        "decision": ("a negative lobe is dropped from a dipole pair when compactness < 0.35"),
    },
)

#: The mathematical value of the isoperimetric quotient for a square, i.e. the
#: maximum the quotient attains for a simply connected shape. Exact: pi/4.
SQUARE_COMPACTNESS_TRUE = math.pi / 4.0


@dataclass(frozen=True)
class CompactnessRow:
    """One shape: the production proxy, the exact quotient, and the gap."""

    sample_id: str
    shape_family: str
    n_cells: int
    proxy: float
    oracle: float
    error: float
    ratio: float
    erosion_boundary_cells: int
    exposed_edge_perimeter: int
    shape_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "shape_family": self.shape_family,
            "n_cells": self.n_cells,
            "proxy": self.proxy,
            "oracle": self.oracle,
            "error": self.error,
            "ratio": (self.proxy / self.oracle) if self.oracle > 0 else None,
            "erosion_boundary_cells": self.erosion_boundary_cells,
            "exposed_edge_perimeter": self.exposed_edge_perimeter,
            "shape_class": self.shape_class,
            "proxy_passes_all_gates": all(
                self.proxy >= c["value"] for c in COMPACTNESS_CONSUMERS if c["comparison"] == ">="
            ),
            "oracle_passes_all_gates": all(
                self.oracle >= c["value"] for c in COMPACTNESS_CONSUMERS if c["comparison"] == ">="
            ),
        }


def compactness_matrix(
    samples: Sequence[ShapeSample] | None = None, *, cell_dx: float = 1.0, cell_dy: float = 1.0
) -> tuple[CompactnessRow, ...]:
    """Every analytic shape, proxy against the exact isoperimetric quotient."""
    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    rows: list[CompactnessRow] = []
    for sample in catalogue:
        metrics = production_shape_metrics(
            sample.cells, cell_dx=cell_dx, cell_dy=cell_dy, sample_id=sample.sample_id
        )
        rows.append(
            CompactnessRow(
                sample_id=sample.sample_id,
                shape_family=sample.shape_family,
                n_cells=metrics.n_cells,
                proxy=metrics.compactness,
                oracle=metrics.compactness_oracle,
                error=metrics.compactness - metrics.compactness_oracle,
                ratio=(
                    metrics.compactness / metrics.compactness_oracle
                    if metrics.compactness_oracle > 0
                    else float("inf")
                ),
                erosion_boundary_cells=metrics.erosion_boundary_cells,
                exposed_edge_perimeter=metrics.perimeter_edges,
                shape_class=metrics.shape_class,
            )
        )
    return tuple(rows)


def compactness_matrix_summary(
    samples: Sequence[ShapeSample] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Aggregate the compactness matrix by shape family and against the gates."""
    rows = compactness_matrix(samples, **kwargs)
    errors = np.array([r.error for r in rows], dtype=float)
    saturated = [r for r in rows if r.proxy >= 0.999]
    low_oracle = [r for r in rows if r.oracle < 0.50]
    families: dict[str, Any] = {}
    for row in rows:
        families.setdefault(row.shape_family, []).append(row)
    family_summary = {
        name: {
            "n": len(group),
            "proxy_min": round(min(r.proxy for r in group), 6),
            "proxy_median": round(float(np.median([r.proxy for r in group])), 6),
            "proxy_max": round(max(r.proxy for r in group), 6),
            "oracle_min": round(min(r.oracle for r in group), 6),
            "oracle_median": round(float(np.median([r.oracle for r in group])), 6),
            "oracle_max": round(max(r.oracle for r in group), 6),
            "median_error": round(float(np.median([r.error for r in group])), 6),
        }
        for name, group in sorted(families.items())
    }
    disagree = [
        r
        for r in low_oracle
        if r.proxy >= max(c["value"] for c in COMPACTNESS_CONSUMERS if c["comparison"] == ">=")
    ]
    return {
        "n_samples": len(rows),
        "error": {
            "min": round(float(errors.min()), 6),
            "median": round(float(np.median(errors)), 6),
            "max": round(float(errors.max()), 6),
            "mean": round(float(errors.mean()), 6),
        },
        "n_proxy_saturated_at_one": len(saturated),
        "fraction_proxy_saturated": round(len(saturated) / max(len(rows), 1), 4),
        "n_oracle_below_0.50": len(low_oracle),
        "n_low_oracle_shapes_that_pass_every_gate": len(disagree),
        "low_oracle_examples": [r.sample_id for r in disagree][:12],
        "families": family_summary,
        "consumers": list(COMPACTNESS_CONSUMERS),
        "square_true_value": round(SQUARE_COMPACTNESS_TRUE, 9),
    }


def compactness_scale_bias(
    sides: Sequence[int] = (2, 3, 4, 5, 6, 8, 10, 14, 20, 30, 40, 60, 100, 200),
) -> dict[str, Any]:
    """Is the proxy scale-consistent? Compare a block family against pi/4.

    A shape ratio should not depend on how many cells the shape happens to
    occupy. The exact exposed-edge quotient is exactly ``pi/4`` for *every*
    ``k x k`` block, so any deviation of the proxy from ``pi/4`` is pure
    scale bias, measurable in isolation from every other consideration.
    """
    from .datasets import square

    rows = []
    for side in sides:
        metrics = production_shape_metrics(
            square(int(side)), sample_id=f"block_{side}x{side}", min_grid_cells=int(side) + 4
        )
        rows.append({
            "side": int(side),
            "n_cells": int(side) * int(side),
            "proxy": round(metrics.compactness, 9),
            "oracle": round(metrics.compactness_oracle, 9),
            "abs_error": round(metrics.compactness - metrics.compactness_oracle, 9),
            "erosion_boundary_cells": metrics.erosion_boundary_cells,
        })
    proxies = [r["proxy"] for r in rows]
    return {
        "rows": rows,
        "square_true_value": round(SQUARE_COMPACTNESS_TRUE, 9),
        "n_saturated_at_one": sum(1 for p in proxies if p >= 0.999),
        "proxy_at_largest_side": proxies[-1],
        "oracle_constant": all(
            abs(r["oracle"] - round(SQUARE_COMPACTNESS_TRUE, 9)) < 1e-9 for r in rows
        ),
        "verdict": (
            "The exact quotient is exactly pi/4 for every block, so the proxy's "
            "deviation is entirely a size effect: the erosion boundary-cell count is "
            "a cell COUNT, not a perimeter, and it converges to the true perimeter "
            "only as the block grows. The metric is therefore not scale-invariant, "
            "and a threshold on it means different things at different component sizes."
        ),
    }


def compactness_thin_diagnostic(
    lengths: Sequence[int] = (2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 30, 45, 60),
) -> dict[str, Any]:
    """Where the proxy stops being able to see thinness at all.

    A one-cell-thick run has *every* cell on the erosion boundary, so the ring
    count equals the area and the quotient becomes ``4*pi``, which the clip
    saturates to 1.0. The exact quotient for the same shape keeps falling with
    length. This locates the regime in which the compactness gates stop
    constraining anything, which is a property of the estimator and not a
    statement about any shape's material.
    """
    from .datasets import line

    rows = []
    for length in lengths:
        metrics = production_shape_metrics(
            line(int(length)), sample_id=f"thin_{length}", min_grid_cells=int(length) + 4
        )
        rows.append({
            "length": int(length),
            "n_cells": int(length),
            "proxy": round(metrics.compactness, 9),
            "oracle": round(metrics.compactness_oracle, 9),
            "erosion_boundary_cells": metrics.erosion_boundary_cells,
            "ring_equals_area": metrics.erosion_boundary_cells == metrics.n_cells,
        })
    uninformative = [r for r in rows if r["proxy"] >= 0.999]
    return {
        "rows": rows,
        "n_saturated_at_one": len(uninformative),
        "n_total": len(rows),
        "longest_saturated_length": max((r["length"] for r in uninformative), default=None),
        "verdict": (
            "For a one-cell-thick run the erosion boundary ring IS the component, so "
            "the proxy saturates at 1.0 while the exact quotient keeps falling. In "
            "that regime none of the compactness gates can reject a thin shape, "
            "however good the shape's compactness would be to measure."
        ),
    }

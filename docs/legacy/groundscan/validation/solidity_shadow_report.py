"""Shadow comparison for S02: the oracle against production on real inputs.

The reference table in :mod:`groundscan.validation.solidity_reference` proves the
corrected formula is *right* on constructed geometry. It says nothing about what
that does to real analyses. This module answers the second question -- the blast
radius -- by running the independent oracle over every component of a real scan
and classifying each disagreement with the retired formula.

## Why classification, and not a diff

"Production changed" is not a finding. A difference can mean very different
things, and pretending they are the same is how a correction gets reverted.

The first thing to get right is **which quantity each number is**. The oracle
and the retired formula are both evaluated on the *same* cell set, so their
difference is, in its entirety, a formula difference -- there is no raster term
in it to subtract. That is why ``legacy_delta`` is reported as a formula error
without a raster allowance.

Raster sensitivity is the *separate* question, and it is reported separately
(``oracle_offset_delta``): how much the **corrected** value itself moves when
the same physical footprint is re-rasterised at twice the density with a
quarter-cell offset. That is a caveat on how the corrected number should be
*read* (a solidity is a property of the raster, not only of the target), and it
is emphatically not a defence of the retired number. Mixing the two would let a
raster effect excuse a formula error, which is the failure mode this module
exists to prevent.

Categories, for the legacy-vs-oracle gap:

``formula-error:clipped-to-one``
    The collinear-centre branch reported a non-solid shape as perfectly solid.
    A large, obvious error, and the least dangerous kind: it saturates in the
    direction of "regular".

``formula-error:unsaturated-wrong``
    A plausible number in the middle of the decision bands -- the dangerous kind,
    because it *drives* classification while looking reasonable.

``+ calibration``
    Appended when the corrected value lands on a different decision band
    (0.48 irregular, 0.75 geology, 0.5 recovery note). The bands are
    uncalibrated -- they sit in the design's calibration register -- so a
    crossing is a question for calibration, never a reason to bend the value
    back.

``none``
    The retired formula happened to be right here (convex, lattice-stable
    components). Recorded so the summary is complete rather than a list of
    complaints.

Separately, for **every** component, ``oracle_agrees_with_production`` is
checked: after activation the two are independent derivations of the same
quantity, so a disagreement is a defect in the production identity, not a
finding.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .._util import axis_spacing
from ..core.shape import _convex_hull_solidity
from .solidity_reference import physical_reference

#: Agreement tolerance between two implementations of the same quantity. Round-off
#: only: the measured worst case over the reference table x 7 pitches x 4 origins
#: is 4.5e-16, and a real disagreement is >= 1e-3 on any shape in the table.
AGREEMENT_TOLERANCE = 1e-9

#: A gap larger than this is a real difference, not round-off.
MATERIAL_DELTA = 1e-6

#: The decision gates solidity feeds (v2 §11.2), each with the direction it runs
#: in. They do **not** all run the same way, and pretending otherwise would
#: mislabel every calibration question:
#:
#: * ``shape.irregular`` -- triggered *below* 0.48 (``shape.py``: ``solidity < 0.48``
#:   and the shape is not already linear);
#: * ``classify.geology`` -- *refused above* 0.75 (``classify.py`` requires
#:   ``solidity <= 0.75`` for a geological-like reading), so the value lands
#:   outside the band on the high side;
#: * ``classify.recovery-note`` -- triggered *below* 0.5 (``classify.py`` adds an
#:   "irregular/concave geometry" note).
#:
#: Bands are calibration-register items, not code constants: a value crossing
#: one is a question for calibration, never a reason to bend the value back.
SOLIDITY_GATES: tuple[tuple[str, str, float, str], ...] = (
    ("shape.irregular", "<", 0.48, "shape_class becomes 'irregular' below this"),
    ("classify.geology", ">", 0.75, "geological-like is refused above this"),
    ("classify.recovery-note", "<", 0.50, "an 'irregular/concave' note is added below this"),
)

CATEGORY_CLIPPED = "formula-error:clipped-to-one"
CATEGORY_UNSATURATED = "formula-error:unsaturated-wrong"
CATEGORY_CALIBRATION = "calibration"
CATEGORY_NONE = "none"


@dataclass(frozen=True)
class ComponentComparison:
    """One component's production / oracle / legacy comparison."""

    component_id: int
    n_cells: int
    cell_dx: float
    cell_dy: float
    n_components_in_mask: int
    production: float
    oracle: float
    legacy: float
    oracle_at_aligned_refinement: float
    oracle_at_coarsened_pitch: float
    oracle_at_non_dividing_pitch: float
    gates_legacy: tuple[str, ...]
    gates_oracle: tuple[str, ...]

    @property
    def production_delta(self) -> float:
        return float(self.oracle - self.production)

    @property
    def legacy_delta(self) -> float:
        """Same cell set on both sides, so this is a pure formula difference."""
        return float(self.oracle - self.legacy)

    @property
    def oracle_agrees_with_production(self) -> bool:
        return abs(self.production_delta) <= AGREEMENT_TOLERANCE

    @property
    def aligned_refinement_drift(self) -> float:
        """Must be zero: a lattice of pitch h/2 always refines one of pitch h."""
        return abs(float(self.oracle_at_aligned_refinement) - self.oracle)

    @property
    def coarsened_pitch_drift(self) -> float:
        """Same region, twice the pitch. Not a refinement in general."""
        return abs(float(self.oracle_at_coarsened_pitch) - self.oracle)

    @property
    def non_dividing_pitch_drift(self) -> float:
        """Same region at 1.5x pitch: the honest raster-sensitivity figure.

        This is the number that says how much a solidity belongs to the sampling
        rather than to the target, and it is reported *next to* the formula error
        rather than folded into it. A raster effect must never be allowed to
        excuse a wrong formula.
        """
        return abs(float(self.oracle_at_non_dividing_pitch) - self.oracle)

    def category(self) -> str:
        if abs(self.legacy_delta) <= MATERIAL_DELTA:
            return CATEGORY_NONE
        base = (
            CATEGORY_CLIPPED if self.legacy >= 1.0 - AGREEMENT_TOLERANCE else CATEGORY_UNSATURATED
        )
        if self.gates_legacy != self.gates_oracle:
            # The value is wrong *and* it lands somewhere else: that is the case
            # a calibration question has to be asked about, so it is named.
            return f"{base} + {CATEGORY_CALIBRATION}"
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "n_cells": self.n_cells,
            "cell_dx": self.cell_dx,
            "cell_dy": self.cell_dy,
            "components_in_mask": self.n_components_in_mask,
            "production": self.production,
            "oracle": self.oracle,
            "legacy": self.legacy,
            "production_delta": self.production_delta,
            "legacy_delta": self.legacy_delta,
            "oracle_agrees_with_production": self.oracle_agrees_with_production,
            "oracle_at_aligned_refinement": self.oracle_at_aligned_refinement,
            "aligned_refinement_drift": self.aligned_refinement_drift,
            "oracle_at_coarsened_pitch": self.oracle_at_coarsened_pitch,
            "coarsened_pitch_drift": self.coarsened_pitch_drift,
            "oracle_at_non_dividing_pitch": self.oracle_at_non_dividing_pitch,
            "non_dividing_pitch_drift": self.non_dividing_pitch_drift,
            "category": self.category(),
            "gates_legacy": list(self.gates_legacy),
            "gates_oracle": list(self.gates_oracle),
        }


@dataclass
class SolidityShadowReport:
    """The blast-radius map for one input."""

    source: str
    comparisons: list[ComponentComparison] = field(default_factory=list)
    impacts: list[ClassificationImpact] = field(default_factory=list)

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.comparisons:
            counts[record.category()] = counts.get(record.category(), 0) + 1
        return dict(sorted(counts.items()))

    @property
    def disagreements(self) -> int:
        return sum(1 for r in self.comparisons if abs(r.legacy_delta) > MATERIAL_DELTA)

    @property
    def production_disagreements(self) -> int:
        return sum(1 for r in self.comparisons if not r.oracle_agrees_with_production)

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "component_count": len(self.comparisons),
            "legacy_disagreements": self.disagreements,
            "legacy_disagreement_rate": (
                self.disagreements / len(self.comparisons) if self.comparisons else 0.0
            ),
            "oracle_vs_production_disagreements": self.production_disagreements,
            "categories": self.categories(),
            "hypothesis_change_count": sum(1 for r in self.impacts if r.hypothesis_changed),
            "shape_class_change_count": sum(1 for r in self.impacts if r.shape_class_changed),
            "max_abs_legacy_delta": max(
                (abs(r.legacy_delta) for r in self.comparisons), default=0.0
            ),
            "max_abs_production_delta": max(
                (abs(r.production_delta) for r in self.comparisons), default=0.0
            ),
            "max_aligned_refinement_drift": max(
                (r.aligned_refinement_drift for r in self.comparisons), default=0.0
            ),
            "max_coarsened_pitch_drift": max(
                (r.coarsened_pitch_drift for r in self.comparisons), default=0.0
            ),
            "max_non_dividing_pitch_drift": max(
                (r.non_dividing_pitch_drift for r in self.comparisons), default=0.0
            ),
            "components_with_multiple_parts": sum(
                1 for r in self.comparisons if r.n_components_in_mask > 1
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "impact_summary": impact_summary(self.impacts),
            "components": [r.to_dict() for r in self.comparisons],
            "impacts": [r.to_dict() for r in self.impacts],
        }


def gates_for(solidity: float) -> tuple[str, ...]:
    """Which solidity gates this value trips, in their own directions."""
    if not math.isfinite(solidity):
        return ()
    tripped: list[str] = []
    for name, direction, threshold, _note in SOLIDITY_GATES:
        if (solidity < threshold) if direction == "<" else (solidity > threshold):
            tripped.append(f"{name}{direction}{threshold:g}")
    return tuple(tripped)


def _cells_of(labels: np.ndarray[Any, Any], component_id: int) -> set[tuple[int, int]]:
    rows, cols = np.where(labels == component_id)
    return {(int(r), int(c)) for r, c in zip(rows, cols, strict=True)}


def _count_components(labels: np.ndarray[Any, Any], component_id: int) -> int:
    """8-connected components inside one label (the production default)."""
    cells = _cells_of(labels, component_id)
    seen: set[tuple[int, int]] = set()
    count = 0
    for start in cells:
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            row, col = stack.pop()
            for drow in (-1, 0, 1):
                for dcol in (-1, 0, 1):
                    neighbour = (row + drow, col + dcol)
                    if neighbour in cells and neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
    return count


def _refine_aligned(cells: Iterable[tuple[int, int]]) -> set[tuple[int, int]]:
    """The same physical footprint at twice the density on the *same* lattice.

    Each cell becomes a 2x2 block, so the result is the same integer pattern at a
    different scale -- and its solidity must be *identical*, not merely close.
    That is not a lucky measurement: a lattice of pitch ``h/2`` always refines a
    lattice of pitch ``h`` (every ``h`` boundary is an ``h/2`` boundary,
    whatever the offset), so the refined cell set is always exactly the blow-up
    and the ratio is always the same rational number. This is the one resampling
    claim K4 can make, and the report asserts it per component.
    """
    return {(r * 2 + dr, c * 2 + dc) for r, c in cells for dr in (0, 1) for dc in (0, 1)}


def _resample_ratio(
    cells: set[tuple[int, int]], cell_dx: float, cell_dy: float, factor: float
) -> set[tuple[int, int]]:
    """Re-rasterise the same physical footprint at ``factor`` times the pitch.

    New cell ``(kr, kc)`` is centred on the old lattice's cell-0 centre plus
    ``factor`` pitches, and is occupied when its centre falls in the old
    footprint (the standard nearest-cell rule that defines a lattice rectangle's
    region). With ``factor = 2`` or ``1/2`` the new lattice still refines or is
    refined by the old one, so the pattern is a clean coarsening/thinning and the
    value is invariant. With ``factor = 1.5`` it is **not** a refinement -- some
    old cells are covered by two new cells and some by one -- and that is the
    honest measurement of how much a solidity belongs to the raster.
    """
    occupied = set(cells)
    min_row = min(r for r, _ in occupied)
    max_row = max(r for r, _ in occupied)
    min_col = min(c for _, c in occupied)
    max_col = max(c for _, c in occupied)
    refined: set[tuple[int, int]] = set()
    for kc in range(int(np.floor((min_col - 1) / factor)) - 1, int(max_col / factor) + 3):
        x = kc * factor * cell_dx
        col = int(np.floor(x / cell_dx + 0.5))
        for kr in range(int(np.floor((min_row - 1) / factor)) - 1, int(max_row / factor) + 3):
            y = kr * factor * cell_dy
            row = int(np.floor(y / cell_dy + 0.5))
            if (row, col) in occupied:
                refined.add((kr, kc))
    return refined


def compare_components(
    labels: np.ndarray[Any, Any],
    n_components: int,
    x_centers: np.ndarray[Any, Any],
    y_centers: np.ndarray[Any, Any],
    cell_dx: float,
    cell_dy: float,
    source: str = "<inline>",
) -> SolidityShadowReport:
    """Compare production, the oracle and the retired formula per component.

    Production's value is recomputed here from the same centres and pitch rather
    than read off a candidate, so the comparison isolates the *formula*: any
    disagreement is a formula disagreement, not a plumbing one.
    """
    from ..diagnostics.shadow import legacy_solidity

    report = SolidityShadowReport(source=source)
    for component_id in range(1, int(n_components) + 1):
        cells = _cells_of(labels, component_id)
        if not cells:
            continue
        xs = np.asarray([c for _r, c in cells], dtype=float)
        ys = np.asarray([r for r, _c in cells], dtype=float)
        production = _convex_hull_solidity(xs * cell_dx, ys * cell_dy, cell_dx, cell_dy)
        reference = physical_reference(cells, cell_dx, cell_dy)
        aligned = physical_reference(_refine_aligned(cells), cell_dx / 2.0, cell_dy / 2.0)
        coarsened = physical_reference(
            _resample_ratio(cells, cell_dx, cell_dy, 2.0), cell_dx * 2.0, cell_dy * 2.0
        )
        odd = physical_reference(
            _resample_ratio(cells, cell_dx, cell_dy, 1.5), cell_dx * 1.5, cell_dy * 1.5
        )
        legacy = legacy_solidity(
            np.asarray([r for r, _c in cells]),
            np.asarray([c for _r, c in cells]),
            cell_dx,
            cell_dy,
        )
        report.comparisons.append(
            ComponentComparison(
                component_id=component_id,
                n_cells=len(cells),
                cell_dx=float(cell_dx),
                cell_dy=float(cell_dy),
                n_components_in_mask=_count_components(labels, component_id),
                production=float(production),
                oracle=float(reference.solidity),
                legacy=float(legacy),
                oracle_at_aligned_refinement=float(aligned.solidity),
                oracle_at_coarsened_pitch=float(coarsened.solidity),
                oracle_at_non_dividing_pitch=float(odd.solidity),
                gates_legacy=gates_for(legacy),
                gates_oracle=gates_for(reference.solidity),
            )
        )
    return report


def compare_scan(
    scan: Any,
    source: str,
    config: Any = None,
) -> SolidityShadowReport:
    """Run one scan through the pipeline and compare every component's solidity.

    The classification impact is measured on candidates **rebuilt from the
    anomaly map** through the same two public functions the pipeline uses
    (``extract_candidates`` then ``classify_candidate``) rather than on the
    final finding list. Two reasons, both about not measuring the wrong thing:

    * the final list is post-separation, so its candidates are fragments whose
      cell sets are not the component's -- comparing those would measure S01's
      decomposition rather than S02's solidity;
    * the optional channels (artifact score, soil TWT depth) are not replayed, so
      this is a controlled comparison of the two solidity hypotheses on identical
      inputs, not a reproduction of the run. Every field except ``solidity`` and
      the ``geometry_quality`` derived from it is identical by construction.
    """
    import tempfile
    from pathlib import Path

    from ..core.classify import classify_candidate
    from ..core.shape import extract_candidates
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan

    cfg = config if config is not None else AnalysisConfig()
    with tempfile.TemporaryDirectory() as tmp:
        grid, anomaly, _final = analyze_scan(
            scan, Path(tmp), label="shadow", config=cfg, write_outputs=False
        )
    cell_dx = axis_spacing(grid.x_centers)
    cell_dy = axis_spacing(grid.y_centers)
    report = compare_components(
        labels=anomaly.labels,
        n_components=anomaly.n_components,
        x_centers=grid.x_centers,
        y_centers=grid.y_centers,
        cell_dx=cell_dx,
        cell_dy=cell_dy,
        source=source,
    )
    parents = [classify_candidate(c) for c in extract_candidates(grid, anomaly)]
    report.impacts = classification_impact_for_components(
        labels=anomaly.labels,
        n_components=anomaly.n_components,
        candidates=parents,
        cell_dx=cell_dx,
        cell_dy=cell_dy,
    )
    return report


# ---------------------------------------------------------------------------
# The activation-gate measurement: does the corrected value change any decision?
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationImpact:
    """What the corrected solidity did to one candidate's decision chain."""

    candidate_id: int
    solidity_corrected: float
    solidity_retired: float
    geometry_quality_corrected: float
    geometry_quality_retired: float
    hypothesis_corrected: str
    hypothesis_retired: str
    evidence_corrected: float
    evidence_retired: float
    shape_class_corrected: str
    shape_class_retired: str
    selected_hypothesis_margin_corrected: float
    selected_hypothesis_margin_retired: float
    gates_corrected: tuple[str, ...]
    gates_retired: tuple[str, ...]

    @property
    def hypothesis_changed(self) -> bool:
        return self.hypothesis_corrected != self.hypothesis_retired

    @property
    def shape_class_changed(self) -> bool:
        return self.shape_class_corrected != self.shape_class_retired

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "solidity_corrected": self.solidity_corrected,
            "solidity_retired": self.solidity_retired,
            "geometry_quality_corrected": self.geometry_quality_corrected,
            "geometry_quality_retired": self.geometry_quality_retired,
            "hypothesis_corrected": self.hypothesis_corrected,
            "hypothesis_retired": self.hypothesis_retired,
            "hypothesis_changed": self.hypothesis_changed,
            "shape_class_corrected": self.shape_class_corrected,
            "shape_class_retired": self.shape_class_retired,
            "shape_class_changed": self.shape_class_changed,
            "evidence_corrected": self.evidence_corrected,
            "evidence_retired": self.evidence_retired,
            "selected_hypothesis_margin_corrected": self.selected_hypothesis_margin_corrected,
            "selected_hypothesis_margin_retired": self.selected_hypothesis_margin_retired,
            "gates_corrected": list(self.gates_corrected),
            "gates_retired": list(self.gates_retired),
        }


def _impact_from_pair(corrected: Any, retired: Any) -> ClassificationImpact:
    """Build the record from two already-classified copies of one candidate."""
    return ClassificationImpact(
        candidate_id=int(getattr(corrected, "id", 0)),
        solidity_corrected=float(getattr(corrected, "solidity", float("nan"))),
        solidity_retired=float(getattr(retired, "solidity", float("nan"))),
        geometry_quality_corrected=float(getattr(corrected, "geometry_quality", float("nan"))),
        geometry_quality_retired=float(getattr(retired, "geometry_quality", float("nan"))),
        hypothesis_corrected=str(getattr(corrected, "pattern_hypothesis", "")),
        hypothesis_retired=str(getattr(retired, "pattern_hypothesis", "")),
        evidence_corrected=float(getattr(corrected, "evidence_score", float("nan"))),
        evidence_retired=float(getattr(retired, "evidence_score", float("nan"))),
        shape_class_corrected=str(getattr(corrected, "shape_class", "")),
        shape_class_retired=str(getattr(retired, "shape_class", "")),
        selected_hypothesis_margin_corrected=float(
            getattr(corrected, "selected_hypothesis_margin", float("nan"))
        ),
        selected_hypothesis_margin_retired=float(
            getattr(retired, "selected_hypothesis_margin", float("nan"))
        ),
        gates_corrected=gates_for(float(getattr(corrected, "solidity", float("nan")))),
        gates_retired=gates_for(float(getattr(retired, "solidity", float("nan")))),
    )


def classification_impact_for_components(
    labels: np.ndarray[Any, Any],
    n_components: int,
    candidates: list[Any],
    cell_dx: float,
    cell_dy: float,
) -> list[ClassificationImpact]:
    """Per-candidate impact of the correction on the whole decision chain.

    The retired solidity is computed from the candidate's **own cell set**, and
    the matching ``geometry_quality`` (``solidity`` enters it with weight 0.25)
    is derived from the production formula rather than re-invented. Both copies
    then go through the real classifier, so the recorded hypothesis, evidence
    and margin are the ones production would have produced.

    This is v2 §11.2 decision criterion 2 ("the measured ``shape_class`` change
    rate is quantified and reviewed") and 4 ("a large change rate blocks
    activation pending calibration"). It is the number the activation decision
    rests on, so it is computed on demand rather than left implicit in a diff.
    """
    from dataclasses import replace

    from ..core.classify import classify_candidate
    from ..diagnostics.shadow import legacy_solidity

    by_id = {int(getattr(c, "id", 0)): c for c in candidates}
    impacts: list[ClassificationImpact] = []
    for component_id in range(1, int(n_components) + 1):
        candidate = by_id.get(component_id)
        if candidate is None:
            continue
        cells = _cells_of(labels, component_id)
        if not cells:
            continue
        rows = np.asarray([r for r, _c in cells], dtype=int)
        cols = np.asarray([c for _r, c in cells], dtype=int)
        retired_solidity = float(legacy_solidity(rows, cols, cell_dx, cell_dy))
        # `geometry_quality` is a linear function of solidity with weight 0.25,
        # so its retired value is derived rather than recomputed from scratch --
        # asserted against the production formula in the test suite.
        n_cells = float(len(cells))
        row0, col0 = min(r for r, _c in cells), min(c for _r, c in cells)
        row1, col1 = max(r for r, _c in cells), max(c for _r, c in cells)
        local_fraction = n_cells / max((row1 - row0 + 1) * (col1 - col0 + 1), 1)
        retired_quality = float(
            np.clip(
                0.30 * min(n_cells / 10.0, 1.0)
                + 0.25 * min(local_fraction, 1.0)
                + 0.25 * retired_solidity
                + 0.20 * (1.0 - min(float(getattr(candidate, "boundary_contact_ratio", 0.0)), 1.0)),
                0.0,
                1.0,
            )
        )
        retired = classify_candidate(
            replace(candidate, solidity=retired_solidity, geometry_quality=retired_quality)
        )
        corrected = classify_candidate(candidate)
        impacts.append(_impact_from_pair(corrected, retired))
    return impacts


def impact_summary(impacts: Iterable[ClassificationImpact]) -> dict[str, Any]:
    """The activation-gate census over a set of candidates."""
    impacts = list(impacts)
    changed = [i for i in impacts if i.hypothesis_changed]
    return {
        "candidate_count": len(impacts),
        "hypothesis_change_count": len(changed),
        "hypothesis_change_rate": len(changed) / len(impacts) if impacts else 0.0,
        "shape_class_change_count": sum(1 for i in impacts if i.shape_class_changed),
        "gate_change_count": sum(1 for i in impacts if i.gates_corrected != i.gates_retired),
        "changed": [i.to_dict() for i in changed],
    }


def aggregate(reports: Iterable[SolidityShadowReport]) -> dict[str, Any]:
    reports = list(reports)
    components = [record for report in reports for record in report.comparisons]
    categories: dict[str, int] = {}
    for record in components:
        categories[record.category()] = categories.get(record.category(), 0) + 1
    return {
        "inputs": len(reports),
        "component_count": len(components),
        "oracle_vs_production_disagreements": sum(
            1 for r in components if not r.oracle_agrees_with_production
        ),
        "legacy_disagreements": sum(1 for r in components if abs(r.legacy_delta) > MATERIAL_DELTA),
        "max_abs_production_delta": max((abs(r.production_delta) for r in components), default=0.0),
        "max_abs_legacy_delta": max((abs(r.legacy_delta) for r in components), default=0.0),
        # Must be exactly 0: a lattice of pitch h/2 refines one of pitch h, so
        # this is the K4 claim and not a tolerance claim.
        "max_aligned_refinement_drift": max(
            (r.aligned_refinement_drift for r in components), default=0.0
        ),
        # The raster caveat, in two flavours: a coarsening that is not a
        # refinement, and a pitch ratio that divides nothing.
        "max_coarsened_pitch_drift": max(
            (r.coarsened_pitch_drift for r in components), default=0.0
        ),
        "max_non_dividing_pitch_drift": max(
            (r.non_dividing_pitch_drift for r in components), default=0.0
        ),
        "components_with_multiple_parts": sum(1 for r in components if r.n_components_in_mask > 1),
        "categories": dict(sorted(categories.items())),
        "by_source": {report.source: report.summary() for report in reports},
    }


__all__ = [
    "AGREEMENT_TOLERANCE",
    "MATERIAL_DELTA",
    "SOLIDITY_GATES",
    "ClassificationImpact",
    "ComponentComparison",
    "SolidityShadowReport",
    "aggregate",
    "classification_impact_for_components",
    "compare_components",
    "compare_scan",
    "gates_for",
    "impact_summary",
]

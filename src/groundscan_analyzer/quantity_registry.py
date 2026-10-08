"""The quantity registry: one home, one owner, one definition per quantity.

Every quantity the engine computes is entered here with its definition,
its derivation, its unit, its population and its definitional bounds. It
exists because the column registry cannot hold a fact about a number
rather than a column, and without it a name like coverage would be
claimed by two decisions at once.

It is the only home of a definitional bound, so the engine, the
validation tests and the compatibility gate read one definition rather
than each restating it. Its version travels once at the document root,
beside the contract version. A bound end carried as None is
scan-dependent and stated per record: field-area ends follow the scan's
own pitches and measured extent, and count ends follow the entering
cells and the connectivity graph.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Final

QUANTITY_REGISTRY_VERSION: Final[int] = 4


class QuantityEntry(NamedTuple):
    """One quantity: what it is, how it is derived, and what bounds it."""

    name: str
    definition: str
    derivation: str
    unit: str
    population: str
    lower: float | None
    lower_inclusive: bool
    upper: float | None
    upper_inclusive: bool
    owner: str


QUANTITIES: Final[tuple[QuantityEntry, ...]] = (
    QuantityEntry(
        name="solidity",
        definition="Occupied cells over the convex hull of cell corners.",
        derivation="Andrew monotone chain on doubled integer corners with "
        "the shoelace sum kept exact, then eight times the count over "
        "that sum in one division, with no tolerance anywhere.",
        unit="ratio",
        population="detection cells",
        lower=0.0,
        lower_inclusive=False,
        upper=1.0,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="compactness",
        definition="Four pi times area over squared exposed lattice-edge perimeter.",
        derivation="Area as the occupied count in cell units with perimeter "
        "counted over exposed lattice edges including hole boundaries, "
        "then one division, with no tolerance anywhere.",
        unit="ratio",
        population="detection cells",
        lower=0.0,
        lower_inclusive=False,
        upper=math.pi / 4,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="field-area",
        definition="Occupied measured cells times the along-line pitch "
        "times the across-line pitch.",
        derivation="Each pitch read by citation from the field position's "
        "own scales with the homogeneity gate on the pair, multiplied "
        "with the detection's own cells, never the hull, with no "
        "tolerance anywhere.",
        unit="square-declared-unit",
        population="detection cells over scan measured cells",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="depth-interval",
        definition="Minimum to maximum over the covered samples' device values.",
        derivation="Spanned, never aggregated, over the samples carrying a "
        "value, and absent where none does, with nothing derived from "
        "travel time or soil factors.",
        unit="as-declared",
        population="detection cells carrying a depth value",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="lattice-boundary-contact",
        definition="Detection cells lying on the measured lattice's own boundary.",
        derivation="Membership of the observed index minima and maxima, "
        "carried as cells with no threshold.",
        unit="cells",
        population="detection cells",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="padding-adjacency-contact",
        definition="Detection cells adjacent inside the lattice bounds to "
        "a coordinate with nothing measured.",
        derivation="Four-neighbourhood membership against the in-bounds "
        "unmeasured set, carried as cells with no threshold.",
        unit="cells",
        population="detection cells",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.descriptors",
    ),
    QuantityEntry(
        name="component-size-in-cells",
        definition="A detection's occupied cell count.",
        derivation="Counted over the detection's own cells.",
        unit="cells",
        population="detection cells over scan measured cells",
        lower=1.0,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.hierarchy",
    ),
    QuantityEntry(
        name="detection-count",
        definition="Nodes of the hierarchy holding one polarity.",
        derivation="Tallied over the emitted tree with no cross-polarity "
        "total and no derived ratio.",
        unit="detections",
        population="detections over scan measured cells",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.hierarchy",
    ),
    QuantityEntry(
        name="component-count",
        definition="Tree nodes alive at one level of one polarity.",
        derivation="Alive exactly while the cut lies at or below the "
        "birth and strictly above the parent's birth, with a "
        "connectivity-dependent independence bound stated per record.",
        unit="components",
        population="components over scan measured cells",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.hierarchy",
    ),
    QuantityEntry(
        name="scan-local-position",
        definition="Exact integer impulse indices within the contributing "
        "scan's own lattice and frame.",
        derivation="The detection's lattice-first cell carried verbatim, "
        "never re-based, with device-reported indices.",
        unit="index",
        population="detection representative cell",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.reader",
    ),
    QuantityEntry(
        name="field-position",
        definition="Index minus one times span over count minus one per axis, in declared units.",
        derivation="One pitch_span per axis with the series origin at "
        "index one, withheld with cause where no extent was declared or "
        "no pitch is definable.",
        unit="declared-unit",
        population="detection representative cell",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.positions",
    ),
    QuantityEntry(
        name="shared-frame-position",
        definition="A detection re-expressed in its shared frame with its "
        "scan-local position retained.",
        derivation="Quarter-turn rows from the versioned mapping table "
        "about the scan center into the reference center, with scales "
        "from the contributing scan's own declaration, swapped across "
        "odd relations.",
        unit="declared-unit",
        population="detection representative cell",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.frames",
    ),
    QuantityEntry(
        name="robust-scale",
        definition="Gaussian-equivalent sigma from median-based estimators "
        "under one shared calibration.",
        derivation="Median absolute deviation over the calibration constant "
        "with the interquartile range over twice it, both from the same "
        "Phi-inverse at three quarters, estimated per scan from the "
        "residual field, never per detection.",
        unit="residual-unit",
        population="finite residuals",
        lower=0.0,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.scale",
    ),
    QuantityEntry(
        name="median-atom-fraction",
        definition="Fraction of the residual field exactly equal to its median.",
        derivation="Exact numerator over exact denominator with no threshold, "
        "carried as evidence in its own right rather than inferred from "
        "two estimates sharing the blind spot.",
        unit="fraction",
        population="residual cells equal to the median over finite residuals",
        lower=0.0,
        lower_inclusive=True,
        upper=1.0,
        upper_inclusive=True,
        owner="groundscan_analyzer.scale",
    ),
    QuantityEntry(
        name="scale-disagreement",
        definition="Pinned relative gap between the two sigma estimates.",
        derivation="Absolute difference over the larger estimate, "
        "dimensionless and in the unit interval identically, symmetric, "
        "and exactly invariant to the calibration constant.",
        unit="ratio",
        population="scale estimates over finite residuals",
        lower=0.0,
        lower_inclusive=True,
        upper=1.0,
        upper_inclusive=True,
        owner="groundscan_analyzer.scale",
    ),
    QuantityEntry(
        name="scale-tie-tolerance",
        definition="Derived tolerance deciding tie against disagreement.",
        derivation="Unit roundoff times a parity and modulus term plus the "
        "field own spread-to-magnitude ratio, never chosen, catching "
        "exact coincidence and nothing else.",
        unit="ratio",
        population="scale estimates over finite residuals",
        lower=0.0,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.scale",
    ),
    QuantityEntry(
        name="scale-normalised-level",
        definition="Hierarchy level in sigma units under the agreed scale.",
        derivation="Raw residual magnitude over the larger estimate where "
        "the estimates tie within tolerance, withheld otherwise rather "
        "than emitted with a caveat.",
        unit="sigma",
        population="hierarchy levels over finite residuals",
        lower=None,
        lower_inclusive=True,
        upper=None,
        upper_inclusive=True,
        owner="groundscan_analyzer.scale",
    ),
)

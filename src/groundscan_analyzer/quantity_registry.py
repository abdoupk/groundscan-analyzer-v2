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

QUANTITY_REGISTRY_VERSION: Final[int] = 1


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
        derivation="Each pitch its declared span over its observed count "
        "less one, multiplied with the detection's own cells, never the "
        "hull, under a bitwise homogeneity gate, with no tolerance "
        "anywhere.",
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
)

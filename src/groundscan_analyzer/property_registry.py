"""The property registry: closed vocabularies, entries and the output census.

The shipped, versioned home of every closed vocabulary the contract has,
plus the stated properties themselves. The module is the single source of
truth the property suite imports, so no test hard-codes a property the
registry does not hold.

Five closed vocabularies ship here together: the nine output classes, the
five scope footprint groups, the transform vocabulary with its refusal
register, the eight contract conventions, and the output census. Three
further closed sets travel beside them: the two grades, the eight warrant
kinds, and the three evidence-coverage values.

One entry per triple of transform, scope and output class. Each entry
carries the transform, the scope, the output class, the grade, its
preconditions, its bound derivation, its zero bound condition, its
governed and excluded outputs, and its evidence coverage recorded apart
from the grade. A fourth coordinate is refused: a scope declares its
feeder conventions and an entry records its exclusions per feeder, so
two feeders moving one class differently share one entry rather than
splitting into two.

A placement is a test with a negative case. An output enters a class only
by meeting all three clauses: decided from the computation, carried on
the record, and withheld rather than a caveat. Failing the test is an
answer rather than a gap: the output is registered as a non-output
carrying which of the three clauses it failed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Final

__all__ = [
    "CONTRACT_VERSION",
    "CONVENTIONS",
    "CONVENTION_PARTS",
    "CONVENTION_SURFACES",
    "EVIDENCE_COVERAGE",
    "GRADES",
    "NON_OUTPUTS",
    "NON_OUTPUT_MARKER",
    "OUTPUT_CENSUS",
    "OUTPUT_CLASSES",
    "PLACEMENT_FAILURE_CLAUSES",
    "PROPERTY_ENTRIES",
    "REFUSED_TRANSFORMS",
    "REGISTRY_VERSION",
    "SCOPES_WITH_LOCALITY",
    "SCOPE_FEEDERS",
    "SCOPE_GROUPS",
    "TRANSFORMS",
    "WARRANT_KINDS",
    "CensusEntry",
    "FeederExclusion",
    "NonOutputEntry",
    "PropertyEntry",
]

CONTRACT_VERSION: Final[int] = 1
REGISTRY_VERSION: Final[int] = 2

OUTPUT_CLASSES: Final[tuple[str, ...]] = (
    "identity",
    "lattice-structure",
    "analysis-quantity",
    "hierarchy-structure",
    "positional-expression",
    "numbered-presentation",
    "boundary-evidence",
    "recorded-fact",
    "limitation",
)

SCOPE_GROUPS: Final[tuple[str, ...]] = (
    "residual-field",
    "effective-amplitude",
    "scale-agreement",
    "field-position",
    "frame-relation",
)

TRANSFORMS: Final[tuple[str, ...]] = (
    "identity",
    "reflect-along-line",
    "reflect-across-lines",
    "reflect-both",
    "index-relabelling",
    "row-permutation",
    "survey-reordering",
    "padding-addition",
    "non-load-bearing-field-substitution",
    "context-column-substitution",
    "metric-echo-substitution",
    "unframed-position-value-substitution",
    "dialect-substitution",
    "re-rooting",
    "level-cut",
    "convention-bump",
)

REFUSED_TRANSFORMS: Final[tuple[str, ...]] = (
    "rot90",
    "padding-relocation",
    "sub-lattice-resampling",
    "perturbation",
    "physical-reading",
)

CONVENTIONS: Final[tuple[str, ...]] = (
    "quantile-v1",
    "background-model-v1",
    "scale-agreement-v1",
    "anchor-rule-v1",
    "field-position-v1",
    "relative-turn-v1",
    "canonical-reference-v1",
    "default-numeric-reading-v1",
)

GRADES: Final[tuple[str, ...]] = (
    "exact",
    "bounded",
)

WARRANT_KINDS: Final[tuple[str, ...]] = (
    "shared-order-statistic",
    "transitive-closure",
    "monotonicity",
    "dominance",
    "non-constancy-in-metric-scale",
    "direct-dependence-on-declared-data",
    "reference-relativity",
    "route-independence",
)

EVIDENCE_COVERAGE: Final[tuple[str, ...]] = (
    "real-data",
    "synthetic-only",
    "unexercised",
)

NON_OUTPUT_MARKER: Final[str] = "non-output"

PLACEMENT_FAILURE_CLAUSES: Final[tuple[str, ...]] = (
    "decided-from-computation",
    "carried-on-record",
    "withheld-state-not-caveat",
)

SCOPE_FEEDERS: Final[dict[str, tuple[str, ...]]] = {
    "residual-field": ("background-model-v1",),
    "effective-amplitude": ("background-model-v1", "anchor-rule-v1"),
    "scale-agreement": ("scale-agreement-v1", "quantile-v1"),
    "field-position": (
        "field-position-v1",
        "relative-turn-v1",
        "canonical-reference-v1",
    ),
    "frame-relation": ("relative-turn-v1", "canonical-reference-v1"),
}

SCOPES_WITH_LOCALITY: Final[tuple[str, ...]] = (
    "residual-field",
    "field-position",
    "frame-relation",
)

CONVENTION_PARTS: Final[dict[str, tuple[str, ...]]] = {
    "quantile-v1": ("interpolation-type", "plotting-position"),
    "background-model-v1": ("window-ladder", "support-rule", "combination"),
    "scale-agreement-v1": (
        "estimator-pair",
        "calibration-constant",
        "disagreement-normalisation",
        "tolerance-form",
    ),
    "anchor-rule-v1": ("anchor-branch",),
    "field-position-v1": (
        "divisor",
        "series-origin",
        "per-axis-independence",
    ),
    "relative-turn-v1": ("coding", "mapping-table"),
    "canonical-reference-v1": (
        "order",
        "payload-encoding",
        "hash-function",
    ),
    "default-numeric-reading-v1": ("separator-assumption",),
}

CONVENTION_SURFACES: Final[dict[str, tuple[str, ...]]] = {
    "default-numeric-reading-v1": (
        "response-column",
        "declared-extent-block",
    ),
}


class CensusEntry(NamedTuple):
    """One registry output with its class and strict-subset members."""

    output: str
    output_class: str
    members: tuple[str, ...]


class NonOutputEntry(NamedTuple):
    """One named non-output with the placement clause it failed."""

    output: str
    clause: str


class FeederExclusion(NamedTuple):
    """One feeder's answer inside a shared entry."""

    feeder: str
    excluded: tuple[str, ...]
    governed: tuple[str, ...]


class PropertyEntry(NamedTuple):
    """One stated property over a transform, scope and output class."""

    transform: str
    scope: str
    output_class: str
    grade: str
    warrant: str
    warrant_non_general: bool
    preconditions: str
    bound_derivation: str
    zero_bound_condition: str
    governed: tuple[str, ...]
    excluded: tuple[str, ...]
    evidence_coverage: str
    feeders: tuple[str, ...]
    feeder_exclusions: tuple[FeederExclusion, ...]
    bump_carries: tuple[str, ...]


OUTPUT_CENSUS: Final[tuple[CensusEntry, ...]] = (
    CensusEntry("solidity", "analysis-quantity", ()),
    CensusEntry("compactness", "analysis-quantity", ()),
    CensusEntry("field-area", "analysis-quantity", ("Field area",)),
    CensusEntry("depth-interval", "analysis-quantity", ()),
    CensusEntry("lattice-boundary-contact", "boundary-evidence", ()),
    CensusEntry("padding-adjacency-contact", "boundary-evidence", ()),
    CensusEntry("component-size-in-cells", "analysis-quantity", ()),
    CensusEntry("detection-count", "hierarchy-structure", ()),
    CensusEntry("component-count", "hierarchy-structure", ()),
    CensusEntry("scan-local-position", "positional-expression", ("Scan-local position",)),
    CensusEntry(
        "field-position",
        "positional-expression",
        ("Field position", "Survey position", "Shared-frame position"),
    ),
    CensusEntry(
        "shared-frame-position",
        "positional-expression",
        ("Survey position", "Shared-frame position"),
    ),
    CensusEntry("robust-scale", "analysis-quantity", ()),
    CensusEntry("median-atom-fraction", "analysis-quantity", ()),
    CensusEntry("scale-disagreement", "analysis-quantity", ()),
    CensusEntry("scale-tie-tolerance", "analysis-quantity", ()),
    CensusEntry("scale-normalised-level", "analysis-quantity", ()),
    CensusEntry("payload-hash", "identity", ()),
    CensusEntry("frame-identity", "identity", ("Shared frame",)),
    CensusEntry("lattice", "lattice-structure", ()),
    CensusEntry("parent-map", "hierarchy-structure", ()),
    CensusEntry("detection-number", "numbered-presentation", ()),
    CensusEntry("mask-invariance", "recorded-fact", ("Effective amplitude",)),
    CensusEntry("frame-relation", "recorded-fact", ("Frame relation",)),
    CensusEntry("aspect-consistency", "recorded-fact", ("Aspect consistency",)),
    CensusEntry(
        "requires-declared-extent",
        "limitation",
        ("requires-declared-extent",),
    ),
    CensusEntry(
        "requires-homogeneous-axes",
        "limitation",
        ("requires-homogeneous-axes",),
    ),
    CensusEntry(
        "requires-bounded-perturbation",
        "limitation",
        ("requires-bounded-perturbation",),
    ),
    CensusEntry(
        "requires-recorded-perturbation-bound",
        "limitation",
        ("requires-recorded-perturbation-bound",),
    ),
    CensusEntry(
        "missing-orientation-path",
        "limitation",
        ("missing-orientation-path",),
    ),
    CensusEntry("scale-not-warranted", "limitation", ("scale-not-warranted",)),
    CensusEntry(
        "scale-not-positive-finite",
        "limitation",
        ("scale-not-positive-finite",),
    ),
)

NON_OUTPUTS: Final[tuple[NonOutputEntry, ...]] = (
    NonOutputEntry("travelling-caveat", "withheld-state-not-caveat"),
    NonOutputEntry("characterisation", "decided-from-computation"),
    NonOutputEntry("readiness-state", "decided-from-computation"),
    NonOutputEntry("support-score", "decided-from-computation"),
    NonOutputEntry("confidence-aggregate", "decided-from-computation"),
    NonOutputEntry("corrected-value", "carried-on-record"),
    NonOutputEntry("line-order", "withheld-state-not-caveat"),
)

PROPERTY_ENTRIES: Final[tuple[PropertyEntry, ...]] = (
    PropertyEntry(
        transform="convention-bump",
        scope="residual-field",
        output_class="analysis-quantity",
        grade="exact",
        warrant="dominance",
        warrant_non_general=False,
        preconditions="measured cells only with clipped centred windows",
        bound_derivation="no bound, identity of thresholded sets",
        zero_bound_condition="",
        governed=(),
        excluded=("Residual", "Solidity", "Compactness"),
        evidence_coverage="real-data",
        feeders=("background-model-v1",),
        feeder_exclusions=(
            FeederExclusion(
                feeder="background-model-v1",
                excluded=("Residual", "Solidity", "Compactness"),
                governed=(),
            ),
        ),
        bump_carries=("window-ladder", "support-rule", "combination"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="residual-field",
        output_class="hierarchy-structure",
        grade="exact",
        warrant="dominance",
        warrant_non_general=False,
        preconditions="hierarchy over non-zero residuals per polarity",
        bound_derivation="no bound, thresholded-set identity",
        zero_bound_condition="",
        governed=(),
        excluded=("Component hierarchy", "Detection count", "Parent map"),
        evidence_coverage="real-data",
        feeders=("background-model-v1",),
        feeder_exclusions=(
            FeederExclusion(
                feeder="background-model-v1",
                excluded=("Component hierarchy", "Detection count", "Parent map"),
                governed=(),
            ),
        ),
        bump_carries=("window-ladder", "support-rule", "combination"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="effective-amplitude",
        output_class="recorded-fact",
        grade="exact",
        warrant="monotonicity",
        warrant_non_general=False,
        preconditions="effective-amplitude-positive",
        bound_derivation="raising a_eff removes satisfying gaps only",
        zero_bound_condition="effective-amplitude-positive",
        governed=(),
        excluded=("Effective amplitude",),
        evidence_coverage="unexercised",
        feeders=("background-model-v1", "anchor-rule-v1"),
        feeder_exclusions=(
            FeederExclusion(
                feeder="background-model-v1",
                excluded=("Effective amplitude",),
                governed=(),
            ),
            FeederExclusion(
                feeder="anchor-rule-v1",
                excluded=("Effective amplitude",),
                governed=(),
            ),
        ),
        bump_carries=("anchor-branch",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="scale-agreement",
        output_class="analysis-quantity",
        grade="exact",
        warrant="shared-order-statistic",
        warrant_non_general=False,
        preconditions="finite residuals with shared calibration Z_75",
        bound_derivation="disagreement in [0, 1] identically",
        zero_bound_condition="",
        governed=(),
        excluded=("Scale status",),
        evidence_coverage="real-data",
        feeders=("scale-agreement-v1", "quantile-v1"),
        feeder_exclusions=(
            FeederExclusion(
                feeder="scale-agreement-v1",
                excluded=("Scale status",),
                governed=(),
            ),
            FeederExclusion(
                feeder="quantile-v1",
                excluded=("Scale status",),
                governed=(),
            ),
        ),
        bump_carries=("estimator-pair", "tolerance-form"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="field-position",
        output_class="positional-expression",
        grade="exact",
        warrant="non-constancy-in-metric-scale",
        warrant_non_general=True,
        preconditions="declared span with observed count of at least two",
        bound_derivation="no bound, criterion over enumerable scalar readings",
        zero_bound_condition="",
        governed=("Scan-local position",),
        excluded=("Field position", "Survey position", "Shared-frame position"),
        evidence_coverage="unexercised",
        feeders=(
            "field-position-v1",
            "relative-turn-v1",
            "canonical-reference-v1",
        ),
        feeder_exclusions=(
            FeederExclusion(
                feeder="field-position-v1",
                excluded=(
                    "Field position",
                    "Survey position",
                    "Shared-frame position",
                ),
                governed=("Scan-local position",),
            ),
            FeederExclusion(
                feeder="relative-turn-v1",
                excluded=("Survey position", "Shared-frame position"),
                governed=("Scan-local position", "Field position"),
            ),
            FeederExclusion(
                feeder="canonical-reference-v1",
                excluded=("Survey position", "Shared-frame position"),
                governed=("Scan-local position", "Field position"),
            ),
        ),
        bump_carries=("divisor", "series-origin", "per-axis-independence"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="field-position",
        output_class="analysis-quantity",
        grade="exact",
        warrant="non-constancy-in-metric-scale",
        warrant_non_general=True,
        preconditions="declared rectangle with homogeneous axes",
        bound_derivation="no bound, area moves with divisor and per-axis dials",
        zero_bound_condition="",
        governed=(),
        excluded=("Field area",),
        evidence_coverage="unexercised",
        feeders=("field-position-v1",),
        feeder_exclusions=(
            FeederExclusion(
                feeder="field-position-v1",
                excluded=("Field area",),
                governed=(),
            ),
        ),
        bump_carries=("divisor", "per-axis-independence"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="field-position",
        output_class="limitation",
        grade="exact",
        warrant="non-constancy-in-metric-scale",
        warrant_non_general=True,
        preconditions="withheld state emitted by its quantity",
        bound_derivation="no bound, state moves with existence",
        zero_bound_condition="",
        governed=(),
        excluded=("requires-homogeneous-axes",),
        evidence_coverage="unexercised",
        feeders=("field-position-v1",),
        feeder_exclusions=(
            FeederExclusion(
                feeder="field-position-v1",
                excluded=("requires-homogeneous-axes",),
                governed=(),
            ),
        ),
        bump_carries=("per-axis-independence",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="frame-relation",
        output_class="recorded-fact",
        grade="exact",
        warrant="direct-dependence-on-declared-data",
        warrant_non_general=True,
        preconditions="declared relations present with shared encoding",
        bound_derivation="no bound, reading of declared data",
        zero_bound_condition="coincidence-set",
        governed=("Aspect consistency",),
        excluded=("Frame relation",),
        evidence_coverage="unexercised",
        feeders=("relative-turn-v1", "canonical-reference-v1"),
        feeder_exclusions=(
            FeederExclusion(
                feeder="relative-turn-v1",
                excluded=("Frame relation",),
                governed=("Aspect consistency",),
            ),
            FeederExclusion(
                feeder="canonical-reference-v1",
                excluded=("Frame relation",),
                governed=("Aspect consistency",),
            ),
        ),
        bump_carries=("coding", "mapping-table"),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="frame-relation",
        output_class="positional-expression",
        grade="exact",
        warrant="direct-dependence-on-declared-data",
        warrant_non_general=True,
        preconditions="shared frame with reference root",
        bound_derivation="no bound, table applied at a point",
        zero_bound_condition="coincidence-set",
        governed=("Scan-local position", "Field position"),
        excluded=("Survey position", "Shared-frame position"),
        evidence_coverage="unexercised",
        feeders=("relative-turn-v1", "canonical-reference-v1"),
        feeder_exclusions=(
            FeederExclusion(
                feeder="relative-turn-v1",
                excluded=("Survey position", "Shared-frame position"),
                governed=("Scan-local position", "Field position"),
            ),
            FeederExclusion(
                feeder="canonical-reference-v1",
                excluded=("Survey position", "Shared-frame position"),
                governed=("Scan-local position", "Field position"),
            ),
        ),
        bump_carries=("mapping-table",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="frame-relation",
        output_class="identity",
        grade="exact",
        warrant="reference-relativity",
        warrant_non_general=True,
        preconditions="frame named after its root",
        bound_derivation="no bound, renaming under re-rooting",
        zero_bound_condition="path-composes-to-identity",
        governed=(),
        excluded=("Shared frame",),
        evidence_coverage="unexercised",
        feeders=("canonical-reference-v1",),
        feeder_exclusions=(
            FeederExclusion(
                feeder="canonical-reference-v1",
                excluded=("Shared frame",),
                governed=(),
            ),
        ),
        bump_carries=("order",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="identity",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("identity",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="lattice-structure",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="dimensions are observed counts, never declared",
        bound_derivation="no bound, unreachable on either surface",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("lattice-structure",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="analysis-quantity",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("analysis-quantity",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="hierarchy-structure",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("hierarchy-structure",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="positional-expression",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("positional-expression",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="numbered-presentation",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("numbered-presentation",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="boundary-evidence",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("boundary-evidence",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="recorded-fact",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("recorded-fact",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
    PropertyEntry(
        transform="convention-bump",
        scope="",
        output_class="limitation",
        grade="exact",
        warrant="route-independence",
        warrant_non_general=True,
        preconditions="reads nothing the convention acts on, on any route",
        bound_derivation="no bound, governed on both surfaces",
        zero_bound_condition="no-numeric-token-carries-character",
        governed=("limitation",),
        excluded=(),
        evidence_coverage="unexercised",
        feeders=(),
        feeder_exclusions=(),
        bump_carries=("separator-assumption",),
    ),
)

"""The contract vocabulary module: every closed set the contract has.

This is the property registry's vocabulary half, shipped as a typed and
versioned module inside the package. It holds the five closed vocabularies
in one place so a later slice adds into a set that already fails when wrong:
the nine output classes, the five scope footprint groups, the transform
vocabulary with its refusal register, the eight contract conventions, and
the output census.

It ships with its checks in place and its sets declared, but with no
registry entries yet. That is prefactoring on purpose: later slices add
entries into closed sets that already reject an unknown name, and the
placement test below decides what is a registry output at all.

A placement is a test with a negative case. An output enters a class only
by meeting all three clauses: decided from the computation, carried on the
record, and withheld rather than a caveat. Failing the test is an answer
rather than a gap: the output is registered as a non-output carrying which
of the three clauses it failed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Final

__all__ = [
    "CONTRACT_VERSION",
    "CONVENTIONS",
    "NON_OUTPUT_MARKER",
    "OUTPUT_CENSUS",
    "OUTPUT_CLASSES",
    "PLACEMENT_FAILURE_CLAUSES",
    "REFUSED_TRANSFORMS",
    "REGISTRY_VERSION",
    "SCOPE_GROUPS",
    "TRANSFORMS",
]

CONTRACT_VERSION: Final[int] = 1
REGISTRY_VERSION: Final[int] = 1

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

NON_OUTPUT_MARKER: Final[str] = "non-output"

PLACEMENT_FAILURE_CLAUSES: Final[tuple[str, ...]] = (
    "decided-from-computation",
    "carried-on-record",
    "withheld-state-not-caveat",
)

OUTPUT_CENSUS: Final[tuple[tuple[str, str], ...]] = ()

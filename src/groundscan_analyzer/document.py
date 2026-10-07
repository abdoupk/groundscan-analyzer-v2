"""The versioned document: one scan export in, one document out.

The document is the engine's entire observable surface. It declares its
contract version as a monotonic integer at the root before anything
version-dependent is read, carries no path, filename, timestamp or
hostname, represents padding as a structural null rather than a numeric
sentinel, and round-trips losslessly in both directions with float
equality bit-for-bit.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Literal, NoReturn

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from groundscan_analyzer import background, dialect, hierarchy, quantity_registry
from groundscan_analyzer.property_registry import CONTRACT_VERSION, REGISTRY_VERSION


def _reject_non_finite[T](value: T) -> T:
    """Refuse a non-finite float while letting every other value through.

    Args:
        value: The candidate field value before coercion.

    Returns:
        The value unchanged.

    Raises:
        ValueError: When the value is a non-finite float.
    """
    if isinstance(value, float) and not math.isfinite(value):
        msg = "non-finite values are unrepresentable"
        raise ValueError(msg)
    return value


FiniteFloat = Annotated[float, BeforeValidator(_reject_non_finite)]
FiniteOptionalFloat = Annotated[float | None, BeforeValidator(_reject_non_finite)]

WithheldReason = Literal["requires-declared-extent", "requires-homogeneous-axes"]

RefusalReason = Literal[
    "unknown-column-name",
    "duplicate-normalised-name",
    "missing-required-column",
    "unparseable-row",
    "invalid-index-value",
    "duplicate-coordinate",
    "unparseable-under-assumed-reading",
]

RowReason = Literal["unparseable-row", "invalid-index-value", "duplicate-coordinate"]

DiscrepancyKind = Literal["index-origin", "metric-origin", "short-line"]

PresenceState = Literal["absent", "present-but-empty", "present-with-value"]


class Lattice(BaseModel):
    """The observed lattice: exactly the set of indices the file contains."""

    model_config = ConfigDict(extra="forbid")

    impulses: list[int]
    scan_lines: list[int]


class Cell(BaseModel):
    """One observed coordinate with its response and residual, null where padding."""

    model_config = ConfigDict(extra="forbid")

    impulse: int = Field(ge=0)
    scan_line: int = Field(ge=0)
    response: FiniteOptionalFloat = None
    residual: FiniteOptionalFloat = None


class BackgroundModel(BaseModel):
    """Processing metadata describing the background computation.

    This is scan context, not configuration: the convention is pinned and
    versioned, and the engine exposes no knob for it. Windows, support rule
    and combination describe the computation and never a claim about the
    ground. The three windows are odd-sized on purpose, and the ladder count
    of three is odd and load-bearing: an even ladder's median would average
    two order statistics rather than returning one. No trend term is removed,
    recorded here as none rather than left as an absence, since the largest
    window already is the low-frequency removal and a fitted trend would be
    a geometric ground claim that double-counts. Support is derived per scale
    and never stored, so no per-scale set travels.
    """

    model_config = ConfigDict(extra="forbid")

    convention: Literal["background-model-v1"] = background.CONVENTION  # type: ignore[assignment]
    windows: tuple[Literal[3], Literal[5], Literal[9]] = background.WINDOWS  # type: ignore[assignment]
    support: Literal["measured-cells-only"] = background.SUPPORT_RULE  # type: ignore[assignment]
    combination: Literal["median"] = background.COMBINATION  # type: ignore[assignment]
    trend: Literal["none"] = background.TREND  # type: ignore[assignment]


class Extent(BaseModel):
    """The declared extent, absent where the operator declared nothing."""

    model_config = ConfigDict(extra="forbid")

    field_length: FiniteOptionalFloat = None
    field_width: FiniteOptionalFloat = None


class DetectionCell(BaseModel):
    """One lattice coordinate belonging to a detection, in lattice order."""

    model_config = ConfigDict(extra="forbid")

    impulse: int = Field(ge=0)
    scan_line: int = Field(ge=0)


class Scale(BaseModel):
    """One field axis pitch with both its inputs named and provenanced.

    The declared span as an operator assertion with the observed count as
    a device index, and the scale their quotient, which tells a reader
    which input to distrust. The scale travels inside the position and
    nowhere else: a bare figure in units with no frame attached is
    impossible in the type.
    """

    model_config = ConfigDict(extra="forbid")

    span: FiniteFloat
    span_provenance: Literal["operator-asserted"] = "operator-asserted"
    count: int = Field(ge=1)
    count_provenance: Literal["device-index"] = "device-index"
    quotient: FiniteFloat


class ScanLocalAxis(BaseModel):
    """One canonical axis: a device-reported index with its provenance."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["along-line", "across-lines"]
    index: int = Field(ge=0)
    provenance: Literal["device-index"] = "device-index"


class ScanLocalPosition(BaseModel):
    """The canonical position: exact integer indices in the scan's frame.

    Always available and never replaced by a derived expression. The
    frame is part of the identity, and the origin is the operator's
    marked starting point with its limitation carried on every position.
    """

    model_config = ConfigDict(extra="forbid")

    frame: Literal["scan-local"]
    origin: Literal["operator-marked-starting-point"]
    origin_limitation: Literal["origin-unverifiable-and-unlocatable"]
    along_line: ScanLocalAxis
    across_lines: ScanLocalAxis


class FieldAxis(BaseModel):
    """One derived axis: an engine-constructed coordinate with its scale."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["along-line", "across-lines"]
    coordinate: FiniteFloat
    scale: Scale
    provenance: Literal["engine-constructed"] = "engine-constructed"


class FieldPosition(BaseModel):
    """A position in the operator-declared extent, in their own units.

    Derived and emitted alongside the scan-local position, never
    replacing it, and only where an extent was declared. True only to
    the extent the declaration was true. Never converted: a declaration
    in feet yields feet.
    """

    model_config = ConfigDict(extra="forbid")

    frame: Literal["scan-local"]
    origin: Literal["operator-marked-starting-point"]
    origin_limitation: Literal["origin-unverifiable-and-unlocatable"]
    along_line: FieldAxis
    across_lines: FieldAxis


class DepthInterval(BaseModel):
    """A device-reported depth interval spanning the covered samples.

    The minimum to the maximum over the samples carrying a device value,
    never a point invented by aggregation, and absent where no sample
    carries one, never zero. Evidence with a provenance, not a statement
    that anything is at that depth, and never presented as verified
    physical depth. Nothing is derived from travel time or soil factors.
    """

    model_config = ConfigDict(extra="forbid")

    minimum: FiniteFloat
    maximum: FiniteFloat
    kind: Literal["device-reported"] = "device-reported"


class Detection(BaseModel):
    """One node of the component hierarchy.

    A detection is a node, not a choice from the tree, and it carries its
    birth level as a recorded fact. Identity is the birth, never the cell
    set: the identity string encodes polarity, birth level and sibling
    rank, so a cell set that vanishes and later returns is a second
    detection. Numbering is presentation in lattice order starting at one
    and excluding padding, so moving or adding padding renumbers nothing.
    Solidity, compactness, field area, depth and boundary contact are
    carried together as pitch-invariant index-space ratios, each
    computable where no extent was declared except field area, which is
    withheld with its cause where it cannot be stated.
    """

    model_config = ConfigDict(extra="forbid")

    identity: str
    number: int = Field(ge=1)
    polarity: Literal["positive", "negative"]
    birth_level: FiniteFloat
    cells: list[DetectionCell]
    cell_count: int = Field(ge=1)
    scan_local_position: ScanLocalPosition
    field_position: FieldPosition | None
    no_field_position_reason: WithheldReason | None = None
    solidity: FiniteFloat
    compactness: FiniteFloat
    field_area: FiniteOptionalFloat = None
    field_area_withheld: WithheldReason | None = None
    depth: DepthInterval | None = None
    lattice_boundary_cells: list[DetectionCell] = Field(default_factory=list)
    padding_adjacent_cells: list[DetectionCell] = Field(default_factory=list)


class DetectionCount(BaseModel):
    """A detection count over one polarity with its named denominator.

    No cross-polarity total is emitted and no derived ratio ships: the
    numerator and the scan's measured cells travel together, and the
    quotient is the consumer's.
    """

    model_config = ConfigDict(extra="forbid")

    polarity: Literal["positive", "negative"]
    count: int = Field(ge=0)
    denominator: int = Field(ge=0)
    connectivity: Literal["4-connectivity"] = hierarchy.CONNECTIVITY  # type: ignore[assignment]


class ComponentCount(BaseModel):
    """A component count at one level of one polarity.

    The level and the connectivity convention travel with the count,
    without which neither its bound nor its reproduction holds, with the
    scan's measured cells as the named denominator. No cross-polarity
    total is emitted and no derived ratio ships.
    """

    model_config = ConfigDict(extra="forbid")

    polarity: Literal["positive", "negative"]
    level: FiniteFloat
    count: int = Field(ge=0)
    denominator: int = Field(ge=0)
    connectivity: Literal["4-connectivity"] = hierarchy.CONNECTIVITY  # type: ignore[assignment]


class Hierarchy(BaseModel):
    """The per-polarity component tree shipped as four arrays.

    The four arrays are the positive levels, the negative levels, the
    detections and the parent map. Every node of the hierarchy is a
    detection carrying its birth level. Levels are raw residuals, never
    scale-normalised, so the tree exists whenever the residual field
    does. Connectivity is fixed in the contract and recorded. The record
    states both populations, measured cells and cells entering the
    hierarchy, so a detection count is never read as covering the whole
    scan. A cut at any level moves no engine output. A node is alive at
    a cut exactly while the cut lies at or below its birth and strictly
    above its parent's birth, so the alive count at a cut is the
    component count there.
    """

    model_config = ConfigDict(extra="forbid")

    connectivity: Literal["4-connectivity"] = hierarchy.CONNECTIVITY  # type: ignore[assignment]
    level_kind: Literal["raw-residual"] = hierarchy.LEVEL_KIND  # type: ignore[assignment]
    cut_guarantee: Literal["you may cut anywhere and lose nothing the engine computed"] = (
        hierarchy.CUT_GUARANTEE  # type: ignore[assignment]
    )
    measured_cells: int = Field(ge=0)
    cells_in_hierarchy: int = Field(ge=0)
    levels_positive: list[FiniteFloat]
    levels_negative: list[FiniteFloat]
    detections: list[Detection]
    parents: list[int | None]
    detection_counts: list[DetectionCount]
    component_counts: list[ComponentCount]


class MetricMismatch(BaseModel):
    """One vendor echo value disagreeing with the derived series."""

    model_config = ConfigDict(extra="forbid")

    axis: Literal["impulse", "scan-line"]
    impulse: int = Field(ge=0)
    scan_line: int = Field(ge=0)
    expected: FiniteFloat
    observed: FiniteFloat


class MetricCheck(BaseModel):
    """The cross-check of the vendor echo, never read as an input."""

    model_config = ConfigDict(extra="forbid")

    checked: bool
    tolerance: FiniteOptionalFloat = None
    mismatches: list[MetricMismatch] = Field(default_factory=list)


class Discrepancy(BaseModel):
    """An observed fact recorded rather than repaired or refused."""

    model_config = ConfigDict(extra="forbid")

    kind: DiscrepancyKind
    detail: str


class RowIssue(BaseModel):
    """One failing row carrying exactly one reason."""

    model_config = ConfigDict(extra="forbid")

    line: int = Field(ge=1)
    reason: RowReason


class ScanRead(BaseModel):
    """A scan the contract accepted, carrying its lattice and responses.

    Line order travels exactly as exported, never corrected, with its
    absence from every export version stated rather than inferred.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["read"] = "read"
    position: int = Field(ge=0)
    sections: list[str]
    columns: list[str]
    lattice: Lattice
    cells: list[Cell]
    background_model: BackgroundModel
    hierarchy: Hierarchy
    extent: Extent
    latitude_presence: PresenceState
    longitude_presence: PresenceState
    line_order: Literal["absent-from-export"] = "absent-from-export"
    metric_check: MetricCheck
    discrepancies: list[Discrepancy]


class ScanRefused(BaseModel):
    """A scan the contract declined, carrying its reason."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["refused"] = "refused"
    position: int = Field(ge=0)
    reason: RefusalReason
    detail: str
    rows: list[RowIssue] = Field(default_factory=list)


class Document(BaseModel):
    """The survey document: contract version first, content-addressed always."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = CONTRACT_VERSION  # type: ignore[assignment]
    registry_version: Literal[1] = REGISTRY_VERSION  # type: ignore[assignment]
    quantity_registry_version: Literal[2] = quantity_registry.QUANTITY_REGISTRY_VERSION  # type: ignore[assignment]
    decimal_separator: Literal["."] = dialect.DECIMAL_SEPARATOR  # type: ignore[assignment]
    convention: Literal["default-numeric-reading-v1"] = dialect.CONVENTION  # type: ignore[assignment]
    scans: list[Annotated[ScanRead | ScanRefused, Field(discriminator="status")]]


def dumps(doc: Document) -> str:
    """Serialise a document to deterministic bytes-friendly text.

    Args:
        doc: The validated document to serialise.

    Returns:
        Canonical JSON with sorted keys and a trailing newline, so two
        fresh processes on the same input emit identical bytes.
    """
    payload = doc.model_dump(mode="json")
    return (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _reject_constant(value: str) -> NoReturn:
    """Refuse the non-standard JSON constants instead of reading them.

    Args:
        value: The offending constant text.

    Raises:
        ValueError: Always, since the writer can never emit it.
    """
    msg = f"non-standard constant is unrepresentable: {value}"
    raise ValueError(msg)


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse duplicate keys instead of letting the last one win.

    Args:
        pairs: The object pairs in file order.

    Returns:
        The object mapping.

    Raises:
        ValueError: On the first repeated key.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            msg = f"duplicate key is unrepresentable: {key}"
            raise ValueError(msg)
        result[key] = value
    return result


def loads(text: str) -> Document:
    """Read a document back, rejecting what the writer can never emit.

    Duplicate keys, non-standard constants and shapes outside the current
    contract version are all refused with a ValueError.

    Args:
        text: The candidate document text.

    Returns:
        The validated document, with floats equal bit-for-bit.
    """
    payload = json.loads(
        text,
        parse_constant=_reject_constant,
        object_pairs_hook=_reject_duplicates,
    )
    return Document.model_validate(payload)

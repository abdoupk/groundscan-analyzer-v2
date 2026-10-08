"""Shared frames: relations over whole lattices, never merged grids.

Two scans walked across each other give a relation, and a survey of any
shape gives one fused expression each: not a merged grid, which would
manufacture values that are not measurements. The engine keeps both
lattices whole, relates them, and stops.

The four declared relations are exactly the cyclic group of order four,
so composition is exact arithmetic and a cycle either closes or it does
not. No transform matrix is ever an assertion and no rotation is applied
at the last moment. Declared clockwise and counter-clockwise are
preserved exactly and never repaired into one another.

The frame's reference is a convention, not an assertion: a total order
ascending over the payload hash, reading nothing about what any
operator declared. The result has an unintelligible name because a hash
chose it, and a human-readable label travels beside it without ever
participating in selection. Each connected component is rooted
independently. A missing link withholds only the shared-frame position;
a contradictory cycle withdraws its component, and every scan in it
falls back to its implicit local frame.

The canonical payload is the measurement content reduced to what the
engine measures: responses with positions relative to the minimum
measured-cell position, normalised per reflection-orbit candidate so the
unsigned encoding stays total. Absolute index labels, declared lattice
dimensions, padding, every operator-typed value, the dialect and the
record's own text are all invisible to it. The identity comparison runs
over numbers rather than encoded bytes; the encoding version rides in
the preimage as well as at the document root.

The mapping table for the turn is versioned contract data read by the
implementation rather than prose formulas. Rotation runs about the scan
lattice's own center, so centered content maps identically under both
quarter turns: that agreement is the stated coincidence set, pointwise
the center and setwise every half-turn-symmetric region. A shared-frame
index may therefore be half-integral on even lattices, which is exact in
binary64 and never a rounding. Re-rooting preserves every pairwise
frame relation while re-expressing coordinates, and moves no detection
and no conclusion: pairwise differences are root-independent by
construction.
"""

from __future__ import annotations

import hashlib
import struct
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Final, Literal

# A frame needs two scans: singletons stay implicit, never recorded.
MIN_FRAME_MEMBERS: Final[int] = 2

RELATION_WORDS: Final[tuple[str, str, str, str]] = (
    "same",
    "opposite",
    "90-clockwise",
    "90-counter-clockwise",
)

PAYLOAD_ENCODING: Final[str] = "payload-encoding-v1"

TURN_TABLE_VERSION: Final[str] = "relative-turn-v1"


class TurnRow(NamedTuple):
    """One quarter-turn row: axis swap with per-axis signs."""

    swap: bool
    signs: tuple[int, int]


TURN_TABLE: Final[dict[int, TurnRow]] = {
    0: TurnRow(swap=False, signs=(1, 1)),
    1: TurnRow(swap=True, signs=(1, -1)),
    2: TurnRow(swap=False, signs=(-1, -1)),
    3: TurnRow(swap=True, signs=(-1, 1)),
}


class Relation(NamedTuple):
    """One declared relation over sorted intake positions."""

    first: int
    second: int
    word: str


class ScanFrame(NamedTuple):
    """One scan's frame inputs: identity, lattice bounds and counts."""

    payload: str
    min_impulse: int
    max_impulse: int
    min_line: int
    max_line: int
    impulse_count: int
    line_count: int


class FrameMember(NamedTuple):
    """One member scan with its class from the canonical reference."""

    scan: int
    relation_class: int


class FrameData(NamedTuple):
    """One viable shared frame: hash name, label and membership."""

    name: str
    label: str
    members: tuple[int, ...]
    relations: tuple[FrameMember, ...]


class ContradictionData(NamedTuple):
    """One non-closing edge in canonical edge order."""

    first: int
    second: int
    word: str
    expected_class: int
    declared_class: int


class AspectData(NamedTuple):
    """One long-short verdict over a declared relation."""

    first: int
    second: int
    word: str
    verdict: Literal["consistent", "contradictory", "not-informative"]


class ScanState(NamedTuple):
    """One scan's frame outcome: frame, missing path or withdrawal."""

    kind: Literal["frame", "missing", "withdrawn"]
    frame: str | None
    relation_class: int | None


class FramesData(NamedTuple):
    """A survey's frames with contradictions and canonical echoes."""

    frames: tuple[FrameData, ...]
    states: tuple[ScanState, ...]
    contradictions: tuple[ContradictionData, ...]
    declared: tuple[Relation, ...]
    aspects: tuple[AspectData, ...]
    centers: dict[str, tuple[float, float]]


def word_to_class(word: str) -> int:
    """Encode one declared word as its cyclic class.

    Same is zero, clockwise quarter is one, opposite is two and
    counter-clockwise quarter is three. The encoding is read from this
    table, never inferred, and a declared word is never repaired into
    its mirror: an unknown word fails rather than becoming another.

    Args:
        word: The declared relation word, exactly as declared.

    Returns:
        The cyclic class from zero to three.

    Raises:
        ValueError: When the word names no declared relation.
    """
    classes = {"same": 0, "90-clockwise": 1, "opposite": 2, "90-counter-clockwise": 3}
    if word not in classes:
        msg = f"unknown relation word: {word!r}"
        raise ValueError(msg)
    return classes[word]


def _reflect(
    triples: set[tuple[int, int, float]], *, flip_impulse: bool, flip_line: bool
) -> set[tuple[int, int, float]]:
    """Reflect one triple set about the origin on either axis.

    Args:
        triples: Relative index-and-response triples.
        flip_impulse: Whether to negate impulse offsets.
        flip_line: Whether to negate scan-line offsets.

    Returns:
        The reflected triples.
    """
    return {
        ((-impulse) if flip_impulse else impulse, (-line) if flip_line else line, value)
        for impulse, line, value in triples
    }


def _normalise(triples: set[tuple[int, int, float]]) -> tuple[tuple[int, int, float], ...]:
    """Shift one triple set to its own minimum and order it.

    Per-candidate normalisation keeps the unsigned encoding total while
    leaving distinct shapes distinct: translation is bijective, so no two
    orbit members merge, and identical normal forms encode identically.

    Args:
        triples: Relative index-and-response triples.

    Returns:
        The minimum-relative triples in lexicographic order.
    """
    low_impulse = min(impulse for impulse, _, _ in triples)
    low_line = min(line for _, line, _ in triples)
    return tuple(
        sorted((impulse - low_impulse, line - low_line, value) for impulse, line, value in triples)
    )


def _canonical_triples(
    responses: Mapping[tuple[int, int], float],
) -> tuple[tuple[int, int, float], ...]:
    """Reduce measured responses to their canonical triple form.

    Args:
        responses: Responses keyed by lattice coordinate, measured only.

    Returns:
        The lexicographically smallest normalised reflection form.
    """
    measured = set(responses)
    low_impulse = min(key[0] for key in measured)
    low_line = min(key[1] for key in measured)
    relative = {
        (impulse - low_impulse, line - low_line, value)
        for (impulse, line), value in responses.items()
    }
    candidates = [
        _normalise(_reflect(relative, flip_impulse=flip_impulse, flip_line=flip_line))
        for flip_impulse in (False, True)
        for flip_line in (False, True)
    ]
    return min(candidates)


def payload_hash(responses: Mapping[tuple[int, int], float]) -> str:
    """Hash one scan's canonical measurement payload.

    The payload covers responses with relative positions only: never
    residuals, which depend on conventions the hash must not read, and
    never absolute labels, dimensions, padding, operator values, the
    dialect or the record's own text. Comparison runs over numbers; the
    version-tagged encoding runs after the representative is chosen.

    Args:
        responses: Responses keyed by lattice coordinate, measured only.

    Returns:
        The SHA-256 hex digest of the versioned encoding.
    """
    triples = _canonical_triples(responses) if responses else ()
    preimage = PAYLOAD_ENCODING.encode("utf-8") + b"\x00"
    for impulse, line, value in triples:
        preimage += struct.pack("<Q", impulse)
        preimage += struct.pack("<Q", line)
        preimage += struct.pack("<d", value)
    return hashlib.sha256(preimage).hexdigest()


def express(
    relation_class: int,
    scan_center: tuple[float, float],
    ref_center: tuple[float, float],
    impulse: int,
    scan_line: int,
) -> tuple[float, float]:
    """Re-express one lattice position in its shared frame.

    Rotation runs about the scan lattice's own center with the frame
    origin at the reference center, reading the quarter-turn rows from
    the versioned table rather than prose formulas. Halves are exact in
    binary64 and never a rounding.

    Args:
        relation_class: The scan's class from the canonical reference.
        scan_center: The scan lattice center as index halves.
        ref_center: The reference lattice center as index halves.
        impulse: The lattice impulse index.
        scan_line: The lattice scan-line index.

    Returns:
        The frame index pair, integral or half-integral.

    Raises:
        ValueError: When the class names no quarter turn.
    """
    if relation_class not in TURN_TABLE:
        msg = f"unknown relation class: {relation_class!r}"
        raise ValueError(msg)
    row = TURN_TABLE[relation_class]
    dx, dy = impulse - scan_center[0], scan_line - scan_center[1]
    ordered = (dx, dy) if not row.swap else (dy, dx)
    return (
        ordered[0] * row.signs[0] + ref_center[0],
        ordered[1] * row.signs[1] + ref_center[1],
    )


class _Forest:
    """Disjoint sets with cyclic offsets for exact closure checks."""

    def __init__(self, count: int) -> None:
        """Start each scan in its own component with zero offset.

        Args:
            count: The scan count.
        """
        self.parent = list(range(count))
        self.offset = [0] * count

    def find(self, scan: int) -> tuple[int, int]:
        """Return one scan's root with its offset from that root.

        Offsets compose modulo four along parent links with path
        compression, so repeated finds stay consistent.

        Args:
            scan: The intake position to locate.

        Returns:
            The root with the scan-minus-root class.
        """
        if self.parent[scan] == scan:
            return scan, 0
        root, below = self.find(self.parent[scan])
        self.offset[scan] = (self.offset[scan] + below) % 4
        self.parent[scan] = root
        return root, self.offset[scan]

    def join(self, first: int, second: int, declared: int) -> None:
        """Constrain second minus first to the declared class.

        A self-union is a no-op: consistency was decided by the caller.

        Args:
            first: One endpoint intake position.
            second: The other endpoint intake position.
            declared: The declared cyclic class between them.
        """
        root_first, off_first = self.find(first)
        root_second, off_second = self.find(second)
        if root_first == root_second:
            return
        self.parent[root_first] = root_second
        self.offset[root_first] = (off_second - off_first - declared) % 4


def _edge_key(edge: Relation, hashes: Sequence[str]) -> tuple[str, str, str, int, int]:
    """Order one declared edge canonically by endpoint hashes.

    Intake positions break remaining ties: they are stable under
    declaration reordering, so the order stays total and
    permutation-invariant. Fully identical declarations share the whole
    key and emit identical bytes in any order.

    Args:
        edge: The declared relation with intake positions.
        hashes: Payload hashes in intake order, empty where refused.

    Returns:
        Minimum hash, maximum hash, word, then intake positions.
    """
    first_hash = hashes[edge.first]
    second_hash = hashes[edge.second]
    low, high = (
        (first_hash, second_hash) if first_hash <= second_hash else (second_hash, first_hash)
    )
    return (low, high, edge.word, edge.first, edge.second)


def _check_edge(forest: _Forest, edge: Relation, declared: int) -> ContradictionData | None:
    """Check one edge against the partition, joining where consistent.

    Args:
        forest: The disjoint sets with cyclic offsets.
        edge: The declared relation with intake positions.
        declared: The declared cyclic class, second minus first.

    Returns:
        The contradiction where the cycle fails to close, else None.
    """
    root_first, off_first = forest.find(edge.first)
    root_second, off_second = forest.find(edge.second)
    if root_first == root_second:
        expected = (off_second - off_first) % 4
        if expected == declared:
            return None
        return ContradictionData(edge.first, edge.second, edge.word, expected, declared)
    forest.join(edge.first, edge.second, declared)
    return None


def _components(forest: _Forest, count: int) -> dict[int, list[int]]:
    """Group intake positions by component root.

    Args:
        forest: The joined disjoint sets.
        count: The scan count.

    Returns:
        Member positions per root in intake order.
    """
    groups: dict[int, list[int]] = {}
    for position in range(count):
        root, _ = forest.find(position)
        groups.setdefault(root, []).append(position)
    return groups


def _classes(
    forest: _Forest, members: list[int], reference: int, hashes: Sequence[str]
) -> dict[int, int]:
    """Read every member's class from the canonical reference.

    Args:
        forest: The joined disjoint sets.
        members: The component member positions.
        reference: The reference position holding class zero.
        hashes: Payload hashes in intake order.

    Returns:
        Relation classes keyed by member position.
    """
    _, off_reference = forest.find(reference)
    found: dict[int, int] = {}
    for position in sorted(members, key=lambda p: hashes[p]):
        _, offset = forest.find(position)
        found[position] = (offset - off_reference) % 4
    return found


def _long_short(
    min_impulse: int, max_impulse: int, min_line: int, max_line: int
) -> tuple[int, int]:
    """Reduce one lattice to its long and short extents.

    Args:
        min_impulse: The smallest observed impulse index.
        max_impulse: The largest observed impulse index.
        min_line: The smallest observed scan-line index.
        max_line: The largest observed scan-line index.

    Returns:
        Long extent with short extent, structurally compared.
    """
    extent_x = max_impulse - min_impulse
    extent_y = max_line - min_line
    return (extent_x, extent_y) if extent_x >= extent_y else (extent_y, extent_x)


def _aspect(
    first: ScanFrame, second: ScanFrame, word: str
) -> Literal["consistent", "contradictory", "not-informative"]:
    """Judge one declared relation by long-short axis roles.

    An even relation expects both lattices long on the same axis; an odd
    relation expects the roles exchanged. Either structurally square
    endpoint is not-informative, decided by structural equality rather
    than tolerance. Parity alone decides, so clockwise and
    counter-clockwise are indistinguishable here by construction.

    Args:
        first: One endpoint scan's frame inputs.
        second: The other endpoint scan's frame inputs.
        word: The declared relation word.

    Returns:
        Consistent, contradictory or not-informative.
    """
    long_first, short_first = _long_short(
        first.min_impulse, first.max_impulse, first.min_line, first.max_line
    )
    long_second, short_second = _long_short(
        second.min_impulse, second.max_impulse, second.min_line, second.max_line
    )
    if long_first == short_first or long_second == short_second:
        return "not-informative"
    long_axis_first = first.max_impulse - first.min_impulse == long_first
    long_axis_second = second.max_impulse - second.min_impulse == long_second
    if is_even_class(word_to_class(word)):
        return "consistent" if long_axis_first == long_axis_second else "contradictory"
    return "consistent" if long_axis_first != long_axis_second else "contradictory"


def is_even_class(relation_class: int) -> bool:
    """Report whether one cyclic class keeps lattice axis roles.

    Same and opposite preserve roles; the quarter turns exchange them.
    Parity alone decides, so clockwise and counter-clockwise are
    indistinguishable here by construction.

    Args:
        relation_class: The cyclic class from zero to three.

    Returns:
        True for the even classes.
    """
    return relation_class % 2 == 0


def center_of_bounds(
    min_impulse: int, max_impulse: int, min_line: int, max_line: int
) -> tuple[float, float]:
    """Return one lattice center as index halves, exact in binary64.

    Args:
        min_impulse: The smallest observed impulse index.
        max_impulse: The largest observed impulse index.
        min_line: The smallest observed scan-line index.
        max_line: The largest observed scan-line index.

    Returns:
        The impulse and scan-line midpoints.
    """
    return ((min_impulse + max_impulse) / 2, (min_line + max_line) / 2)


def _viable_edges(ordered: list[Relation], scans: Sequence[ScanFrame | None]) -> list[Relation]:
    """Keep declared edges whose endpoints both hold measurements.

    Edges touching a refused scan constrain nothing, while their
    declarations still echo verbatim.

    Args:
        ordered: Declared edges in canonical order.
        scans: Frame inputs per intake position, None where refused.

    Returns:
        The viable edges in canonical order.
    """
    return [
        edge for edge in ordered if scans[edge.first] is not None and scans[edge.second] is not None
    ]


def _center_of(scan: ScanFrame) -> tuple[float, float]:
    """Return one scan lattice center as index halves.

    Args:
        scan: One frame input carrying lattice bounds.

    Returns:
        The impulse and scan-line midpoints.
    """
    return center_of_bounds(scan.min_impulse, scan.max_impulse, scan.min_line, scan.max_line)


def _order_relations(relations: Sequence[Relation], hashes: Sequence[str]) -> list[Relation]:
    """Order declared edges canonically by endpoint hashes.

    Args:
        relations: Declared relations over intake positions.
        hashes: Payload hashes in intake order, empty where refused.

    Returns:
        The edges with words verbatim in canonical order.
    """
    return sorted(relations, key=lambda edge: _edge_key(edge, hashes))


def _check_all(forest: _Forest, viable: list[Relation]) -> list[ContradictionData]:
    """Check every viable edge in order, joining where the cycle closes.

    Args:
        forest: The disjoint sets with cyclic offsets.
        viable: Declared edges in canonical order, dangling dropped.

    Returns:
        Non-closing edges in canonical edge order.
    """
    contradictions: list[ContradictionData] = []
    for edge in viable:
        found = _check_edge(forest, edge, word_to_class(edge.word))
        if found is not None:
            contradictions.append(found)
    return contradictions


def _frame_record(
    forest: _Forest,
    members: list[int],
    reference: int,
    label: str,
    scans: Sequence[ScanFrame | None],
) -> tuple[FrameData, dict[int, ScanState], tuple[float, float]]:
    """Record one viable frame with its member states and center.

    Args:
        forest: The joined disjoint sets.
        members: The component member positions.
        reference: The reference position holding class zero.
        label: The human-readable label beside the hash name.
        scans: Frame inputs per intake position, None where refused.

    Returns:
        The frame record with member states and reference center.

    Raises:
        ValueError: When the reference names no measured scan, which
            viable membership forbids.
    """
    hashes = [scan.payload if scan is not None else "" for scan in scans]
    classes = _classes(forest, members, reference, hashes)
    name = hashes[reference]
    ref_scan = scans[reference]
    if ref_scan is None:
        msg = f"frame names no measured scan: {name!r}"
        raise ValueError(msg)
    states = {position: ScanState("frame", name, classes[position]) for position in members}
    record = FrameData(
        name=name,
        label=label,
        members=tuple(sorted(members)),
        relations=tuple(FrameMember(scan, classes[scan]) for scan in sorted(members)),
    )
    return record, states, _center_of(ref_scan)


def _collect_aspects(viable: list[Relation], live: dict[int, ScanFrame]) -> list[AspectData]:
    """Judge every viable declared edge by long-short axis roles.

    Args:
        viable: Declared edges in canonical order, dangling dropped.
        live: Frame inputs keyed by intake position.

    Returns:
        Verdicts in canonical edge order.
    """
    aspects: list[AspectData] = []
    for edge in viable:
        first_scan = live[edge.first]
        second_scan = live[edge.second]
        aspects.append(
            AspectData(
                edge.first, edge.second, edge.word, _aspect(first_scan, second_scan, edge.word)
            )
        )
    return aspects


def _tainted_roots(forest: _Forest, contradictions: list[ContradictionData]) -> set[int]:
    """Collect component roots holding a contradiction.

    Args:
        forest: The joined disjoint sets.
        contradictions: Non-closing edges in canonical edge order.

    Returns:
        Roots withdrawing their whole component.
    """
    tainted = set()
    for found in contradictions:
        root, _ = forest.find(found.first)
        tainted.add(root)
    return tainted


def _label_viable(
    groups: dict[int, list[int]], tainted: set[int], hashes: list[str]
) -> dict[int, tuple[int, str]]:
    """Root viable components independently with human labels.

    Args:
        groups: Member positions per component root.
        tainted: Roots holding a contradiction.
        hashes: Payload hashes in intake order, empty where refused.

    Returns:
        Reference position with label per viable root.
    """
    viable = {
        root: min(members, key=lambda p: (hashes[p], p))
        for root, members in groups.items()
        if root not in tainted and len(members) >= MIN_FRAME_MEMBERS
    }
    labels = {
        reference: f"frame-{number}"
        for number, reference in enumerate(
            sorted(viable.values(), key=lambda p: (hashes[p], p)), start=1
        )
    }
    return {root: (reference, labels[reference]) for root, reference in viable.items()}


def _assemble_frames(
    groups: dict[int, list[int]],
    tainted: set[int],
    labeled: dict[int, tuple[int, str]],
    forest: _Forest,
    scans: Sequence[ScanFrame | None],
) -> tuple[list[FrameData], list[ScanState], dict[str, tuple[float, float]]]:
    """Record viable frames, marking the rest missing or withdrawn.

    Args:
        groups: Member positions per component root.
        tainted: Roots holding a contradiction.
        labeled: Reference position with label per viable root.
        forest: The joined disjoint sets.
        scans: Frame inputs per intake position, None where refused.

    Returns:
        Frame records with member states and reference centers.
    """
    frames: list[FrameData] = []
    states: list[ScanState] = [ScanState("missing", None, None)] * len(scans)
    centers: dict[str, tuple[float, float]] = {}
    for root, members in groups.items():
        if root in tainted or len(members) < MIN_FRAME_MEMBERS:
            kind: Literal["withdrawn", "missing"] = "withdrawn" if root in tainted else "missing"
            for position in members:
                states[position] = ScanState(kind, None, None)
            continue
        reference, label = labeled[root]
        record, owned, center = _frame_record(forest, members, reference, label, scans)
        frames.append(record)
        centers[record.name] = center
        for position, state in owned.items():
            states[position] = state
    frames.sort(key=lambda frame: frame.name)
    return frames, states, centers


def build_frames(scans: Sequence[ScanFrame | None], relations: Sequence[Relation]) -> FramesData:
    """Relate whole lattices into shared frames without merging any.

    Components join over declared edges regardless of direction; each is
    rooted independently at its minimum payload hash, with intake
    position breaking exact ties. Refused scans enter as placeholders:
    edges touching them are dropped, since a scan with no measurements
    constrains nothing, while their declarations still echo verbatim
    under the empty identity. Contradictory edges are reported in
    canonical edge order and withdraw their whole component. Declared
    words echo verbatim in canonical order, so shuffled inputs emit
    identical bytes.

    Args:
        scans: Frame inputs per intake position, None where refused.
        relations: Declared relations over intake positions.

    Returns:
        Frames with per-scan states, contradictions, echoes and verdicts.
    """
    hashes = [scan.payload if scan is not None else "" for scan in scans]
    ordered = _order_relations(relations, hashes)
    live = {position: scan for position, scan in enumerate(scans) if scan is not None}
    viable = _viable_edges(ordered, scans)
    forest = _Forest(len(scans))
    contradictions = _check_all(forest, viable)
    aspects = _collect_aspects(viable, live)
    groups = _components(forest, len(scans))
    tainted = _tainted_roots(forest, contradictions)
    labeled = _label_viable(groups, tainted, hashes)
    frames, states, centers = _assemble_frames(groups, tainted, labeled, forest, scans)
    return FramesData(
        frames=tuple(frames),
        states=tuple(states),
        contradictions=tuple(contradictions),
        declared=tuple(ordered),
        aspects=tuple(aspects),
        centers=centers,
    )

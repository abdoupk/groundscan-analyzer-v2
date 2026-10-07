"""The component hierarchy: a threshold-free tree over the residual field.

The hierarchy is built per polarity over the cells whose residual is
non-zero, with one level per distinct residual magnitude per polarity. A
magnitude occurring on both sides of the background is two levels, not
one. Every node qualifies as a detection and carries its birth level.

No level ever enters as an input: the builder takes the residual field
only. Cells sharing a magnitude enter simultaneously as siblings, since
the components at a level are determined by the thresholded set rather
than by entry order. An ordering rule would manufacture intermediate
nodes matching no thresholded set at all.

A node's identity is its birth, never its cell set: a region that
vanishes and later returns is a second detection. Levels are raw
residuals, never scale-normalised, so the tree exists whenever the
residual field exists. Connectivity is fixed in the contract and
recorded rather than exposed.

A node is alive at a cut through its polarity exactly while the cut
lies at or below its birth and strictly above its parent's birth: its
own birth magnitude reaches the cut's, and its parent (if any) was born
strictly fainter. The number of alive nodes at a cut is the component
count there, and the parent map composes by following parent pointers.
Cell sets at a cut are served together with the residual field the
document carries on every cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Final, Literal

CONNECTIVITY: Final[str] = "4-connectivity"
LEVEL_KIND: Final[str] = "raw-residual"
CUT_GUARANTEE: Final[str] = "you may cut anywhere and lose nothing the engine computed"


class DetectionData(NamedTuple):
    """One node ready for the record, in birth order position."""

    identity: str
    number: int
    polarity: Literal["positive", "negative"]
    birth: float
    cells: tuple[tuple[int, int], ...]


class HierarchyData(NamedTuple):
    """The full tree as four arrays plus its two populations."""

    measured_cells: int
    cells_in_hierarchy: int
    levels_positive: tuple[float, ...]
    levels_negative: tuple[float, ...]
    detections: tuple[DetectionData, ...]
    parents: tuple[int | None, ...]


@dataclass
class _Node:
    """One growing region during construction."""

    polarity: Literal["positive", "negative"]
    birth: float
    cells: set[tuple[int, int]]
    birth_rep: tuple[int, int]
    parent: int | None = None


@dataclass
class _Forest:
    """Disjoint sets over the active coordinates with member tracking."""

    parent: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    size: dict[tuple[int, int], int] = field(default_factory=dict)
    members: dict[tuple[int, int], set[tuple[int, int]]] = field(default_factory=dict)

    def add(self, key: tuple[int, int]) -> None:
        """Introduce one coordinate as its own set.

        Args:
            key: The lattice coordinate to introduce.
        """
        self.parent[key] = key
        self.size[key] = 1
        self.members[key] = {key}

    def find(self, key: tuple[int, int]) -> tuple[int, int]:
        """Return the representative of one coordinate's set.

        Args:
            key: The lattice coordinate to locate.

        Returns:
            The set representative.
        """
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != root:
            staged = self.parent[key]
            self.parent[key] = root
            key = staged
        return root

    def union(self, first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
        """Merge two coordinates' sets, keeping the larger representative.

        Args:
            first: One lattice coordinate.
            second: Another lattice coordinate.

        Returns:
            The surviving representative.
        """
        root = self.find(first)
        other = self.find(second)
        if root == other:
            return root
        if self.size[root] < self.size[other]:
            root, other = other, root
        self.parent[other] = root
        self.size[root] += self.size[other]
        self.members[root] |= self.members[other]
        del self.size[other]
        del self.members[other]
        return root


@dataclass
class _Construction:
    """Mutable state while one polarity's tree grows."""

    polarity: Literal["positive", "negative"]
    forest: _Forest = field(default_factory=_Forest)
    nodes: list[_Node] = field(default_factory=list)
    owner: dict[tuple[int, int], int] = field(default_factory=dict)


def _lattice_order_key(key: tuple[int, int]) -> tuple[int, int]:
    """Return the lattice-order sort key for one coordinate.

    Lattice order is scan-line major: the scan line decides before the
    impulse does, so file row order never decides numbering.

    Args:
        key: The coordinate as an impulse and scan-line pair.

    Returns:
        The scan line first, then the impulse.
    """
    impulse, scan_line = key
    return (scan_line, impulse)


def _neighbours(key: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    """Return the four edge-adjacent coordinates in a fixed order.

    Connectivity is fixed in the contract: edge adjacency only, so cells
    touching at a corner alone never connect. The order is fixed so the
    union sequence is deterministic; the resulting components do not
    depend on it.

    Args:
        key: The centre coordinate as an impulse and scan-line pair.

    Returns:
        The four neighbours: left, right, below and above.
    """
    impulse, scan_line = key
    return (
        (impulse - 1, scan_line),
        (impulse + 1, scan_line),
        (impulse, scan_line - 1),
        (impulse, scan_line + 1),
    )


def _admit_fresh(state: _Construction, fresh: list[tuple[int, int]]) -> None:
    """Add one magnitude's cells and union them with the active set.

    Args:
        state: The growing polarity tree to extend.
        fresh: The entering coordinates in lattice order.
    """
    for key in fresh:
        state.forest.add(key)
    for key in fresh:
        for neighbour in _neighbours(key):
            if neighbour in state.forest.parent:
                state.forest.union(key, neighbour)


def _touched_roots(state: _Construction, fresh: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """List the active components touched by the entering magnitude.

    Args:
        state: The growing polarity tree under extension.
        fresh: The entering coordinates in lattice order.

    Returns:
        Touched representatives ordered by their representative cell.
    """
    roots = {state.forest.find(key) for key in fresh}
    return sorted(
        roots,
        key=lambda root: min(_lattice_order_key(item) for item in state.forest.members[root]),
    )


def _new_node(state: _Construction, level: float, members: set[tuple[int, int]]) -> int:
    """Append one node born now and return its position.

    The birth representative is snapshotted from the entering members, so
    a later growth never moves the birth's lattice order.

    Args:
        state: The growing polarity tree to extend.
        level: The raw residual magnitude entering now.
        members: The new node's coordinates.

    Returns:
        The node's position.
    """
    rep = min(_lattice_order_key(item) for item in members)
    state.nodes.append(_Node(polarity=state.polarity, birth=level, cells=members, birth_rep=rep))
    return len(state.nodes) - 1


def _take_ownership(state: _Construction, members: set[tuple[int, int]], index: int) -> None:
    """Point every member coordinate at its region's node.

    Args:
        state: The growing polarity tree to extend.
        members: The region's coordinates.
        index: The owning node's position.
    """
    for item in members:
        state.owner[item] = index


def _birth_region(state: _Construction, level: float, members: set[tuple[int, int]]) -> None:
    """Record a de novo birth for a region with no previous owner.

    Args:
        state: The growing polarity tree to extend.
        level: The raw residual magnitude entering now.
        members: The new region's coordinates.
    """
    _take_ownership(state, members, _new_node(state, level, members))


def _grow_region(state: _Construction, survivor: int, members: set[tuple[int, int]]) -> None:
    """Extend the surviving region with the entering coordinates.

    Args:
        state: The growing polarity tree to extend.
        survivor: The surviving region's node position.
        members: The region's expanded coordinates.
    """
    state.nodes[survivor].cells = members
    _take_ownership(state, members, survivor)


def _merge_regions(
    state: _Construction, level: float, members: set[tuple[int, int]], previous: list[int]
) -> None:
    """Record one parent where several regions meet at the entering level.

    Args:
        state: The growing polarity tree to extend.
        level: The raw residual magnitude entering now.
        members: The merged region's coordinates.
        previous: The meeting regions' node positions.
    """
    index = _new_node(state, level, members)
    for old in previous:
        state.nodes[old].parent = index
    _take_ownership(state, members, index)


def _absorb_root(state: _Construction, level: float, root: tuple[int, int]) -> None:
    """Fold one touched component into births, growth or a merge.

    Args:
        state: The growing polarity tree to extend.
        level: The raw residual magnitude entering now.
        root: The touched component's representative.
    """
    members = set(state.forest.members[root])
    previous = sorted({state.owner[item] for item in members if item in state.owner})
    if not previous:
        _birth_region(state, level, members)
    elif len(previous) == 1:
        _grow_region(state, previous[0], members)
    else:
        _merge_regions(state, level, members, previous)


def _enter_level(state: _Construction, level: float, fresh: list[tuple[int, int]]) -> None:
    """Enter one magnitude's cells simultaneously as siblings.

    All cells sharing the magnitude join the active set before any union
    runs, so no ordering among them can manufacture an intermediate node
    matching no thresholded set.

    Args:
        state: The growing polarity tree to extend.
        level: The raw residual magnitude entering now.
        fresh: The entering coordinates in lattice order.
    """
    _admit_fresh(state, fresh)
    for root in _touched_roots(state, fresh):
        _absorb_root(state, level, root)


def _build_one_polarity(
    by_level: dict[float, list[tuple[int, int]]],
    ordered: tuple[float, ...],
    polarity: Literal["positive", "negative"],
) -> list[_Node]:
    """Grow one polarity's tree from its most extreme level downwards.

    Args:
        by_level: Entering coordinates per residual magnitude.
        ordered: The magnitudes from most extreme to faintest.
        polarity: The polarity under construction.

    Returns:
        The polarity's nodes in creation order.
    """
    state = _Construction(polarity=polarity)
    for level in ordered:
        _enter_level(state, level, by_level[level])
    return state.nodes


def _ordered_levels(values: set[float]) -> tuple[float, ...]:
    """Order distinct magnitudes from most extreme to faintest.

    Args:
        values: The distinct raw residuals of one polarity.

    Returns:
        The magnitudes with the largest absolute value first.
    """
    return tuple(sorted(values, key=abs, reverse=True))


def _group_by_level(
    values: Mapping[tuple[int, int], float],
) -> tuple[tuple[float, ...], dict[float, list[tuple[int, int]]]]:
    """Group coordinates by residual magnitude in lattice order.

    Args:
        values: Residuals of one polarity keyed by lattice coordinate.

    Returns:
        The ordered magnitudes with the entering coordinates per level.
    """
    by_level: dict[float, list[tuple[int, int]]] = {}
    for key in sorted(values, key=_lattice_order_key):
        by_level.setdefault(values[key], []).append(key)
    return _ordered_levels(set(values.values())), by_level


def _representative(cells: set[tuple[int, int]]) -> tuple[int, int]:
    """Return the lattice-first coordinate of one cell set.

    Args:
        cells: The detection's coordinates.

    Returns:
        The minimum under lattice order.
    """
    return min(_lattice_order_key(item) for item in cells)


def _ranks(nodes: list[_Node]) -> list[int]:
    """Rank simultaneous siblings by their birth representative.

    The order is snapshotted at birth, so a later growth never re-ranks
    an earlier birth.

    Args:
        nodes: The combined nodes in birth order.

    Returns:
        The sibling rank per node position.
    """
    groups: dict[tuple[str, float], list[int]] = {}
    for position, node in enumerate(nodes):
        groups.setdefault((node.polarity, node.birth), []).append(position)
    ordering: dict[int, int] = {}
    for positions in groups.values():
        ranked = sorted(positions, key=lambda p: nodes[p].birth_rep)
        ordering.update({position: rank for rank, position in enumerate(ranked)})
    return [ordering[position] for position in range(len(nodes))]


def _presentation_order(nodes: list[_Node]) -> list[int]:
    """Order node positions for presentation numbering.

    Numbering follows lattice order of the representative, with the more
    extreme birth first where representatives coincide, so a child sorts
    before the parent containing it.

    Args:
        nodes: The combined nodes in birth order.

    Returns:
        Node positions from first numbered to last.
    """
    return sorted(
        range(len(nodes)),
        key=lambda p: (
            _representative(nodes[p].cells),
            -abs(nodes[p].birth),
            nodes[p].polarity,
        ),
    )


def _combined_parents(pos_nodes: list[_Node], neg_nodes: list[_Node]) -> list[int | None]:
    """Join the per-polarity parent maps with the negative block offset.

    Args:
        pos_nodes: The positive nodes in birth order.
        neg_nodes: The negative nodes in birth order.

    Returns:
        The parent position per combined position, None for roots.
    """
    offset = len(pos_nodes)
    parents: list[int | None] = [node.parent for node in pos_nodes]
    parents.extend(None if node.parent is None else node.parent + offset for node in neg_nodes)
    return parents


def _finalise(
    nodes: list[_Node],
    parents: list[int | None],
    pos_levels: tuple[float, ...],
    neg_levels: tuple[float, ...],
    counts: tuple[int, int],
) -> HierarchyData:
    """Assign birth identities and presentation numbers to the nodes.

    Args:
        nodes: The combined nodes in birth order.
        parents: The parent position per combined position.
        pos_levels: The positive magnitudes most extreme first.
        neg_levels: The negative magnitudes most extreme first.
        counts: Measured cells with cells entering the hierarchy.

    Returns:
        The tree as four arrays with its two populations.
    """
    measured, in_hierarchy = counts
    ranks = _ranks(nodes)
    numbers = [0] * len(nodes)
    for number, position in enumerate(_presentation_order(nodes), start=1):
        numbers[position] = number
    detections: list[DetectionData] = []
    for position, node in enumerate(nodes):
        identity = f"{node.polarity}@{node.birth!r}#{ranks[position]}"
        ordered_cells = tuple(sorted(node.cells, key=_lattice_order_key))
        detections.append(
            DetectionData(
                identity=identity,
                number=numbers[position],
                polarity=node.polarity,
                birth=node.birth,
                cells=ordered_cells,
            )
        )
    return HierarchyData(
        measured_cells=measured,
        cells_in_hierarchy=in_hierarchy,
        levels_positive=pos_levels,
        levels_negative=neg_levels,
        detections=tuple(detections),
        parents=tuple(parents),
    )


def build(residuals: Mapping[tuple[int, int], float]) -> HierarchyData:
    """Build the per-polarity component hierarchy over the residual field.

    Args:
        residuals: Residuals keyed by lattice coordinate, measured cells
            only, with exact zeros belonging to neither polarity.

    Returns:
        The tree as four arrays with its two populations: measured cells
        and cells entering the hierarchy.
    """
    positives = {key: value for key, value in residuals.items() if value > 0.0}
    negatives = {key: value for key, value in residuals.items() if value < 0.0}
    pos_levels, pos_by_level = _group_by_level(positives)
    neg_levels, neg_by_level = _group_by_level(negatives)
    pos_nodes = _build_one_polarity(pos_by_level, pos_levels, "positive")
    neg_nodes = _build_one_polarity(neg_by_level, neg_levels, "negative")
    return _finalise(
        pos_nodes + neg_nodes,
        _combined_parents(pos_nodes, neg_nodes),
        pos_levels,
        neg_levels,
        (len(residuals), len(positives) + len(negatives)),
    )

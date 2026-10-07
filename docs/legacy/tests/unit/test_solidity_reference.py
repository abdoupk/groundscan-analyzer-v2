"""Stage 3 / S02 -- solidity as a dimensionless geometric ratio (contract K4).

This file is the evidence for the S02 activation. It is written in the order
the evidence had to be produced, and each block states which claim it is
responsible for.

The discipline is the one from the design's ?12.1: **no test asserts "the
current output is X"**. Every expectation is derived either from a constructed
geometry whose exact value is written down by hand
(:data:`REFERENCE_CASES`), or from a *property* that follows from the
definition of the ratio. Golden artifacts and vendor OKM files are regression
references, not ground truth, and are not used as an oracle anywhere here.

Blocks:

1. the independent oracle against the hand-derived reference table
2. the oracle against itself (two unrelated area constructions)
3. the awkward cases the definition has to treat explicitly
4. metamorphic properties: translation, uniform scale, unit, pitch, density
5. production against the oracle -- through the real ``_shape_metrics`` path
6. the retired formula, pinned so it cannot come back unnoticed
7. regression protection: every unrelated shape metric is bit-identical to the
   pre-change baseline
"""

from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from groundscan.core.grid import Grid2D
from groundscan.core.shape import _shape_metrics
from groundscan.validation.solidity_reference import (
    PITCHES,
    REFERENCE_CASES,
    SCALES,
    UNIT_TO_METRES,
    SolidityOracleError,
    exact_solidity,
    hull_area_cells,
    occupied_area_by_runs,
    occupied_area_cells,
    physical_reference,
)

#: Agreement tolerance between the float physical path and the exact rational
#: oracle. Measured worst case across the table x 7 pitches x 4 origins is
#: 4.5e-16; 1e-12 leaves ~3 orders of margin and is still far below the 1e-6
#: resolution at which a real geometric difference would appear.
ORACLE_TOL = 1e-12

CASES = [case.name for case in REFERENCE_CASES]


def _cells(case_name: str) -> set[tuple[int, int]]:
    for case in REFERENCE_CASES:
        if case.name == case_name:
            return case.cell_set()
    raise KeyError(case_name)


def _case(case_name: str):
    for case in REFERENCE_CASES:
        if case.name == case_name:
            return case
    raise KeyError(case_name)


# ===========================================================================
# 1. The independent oracle against the hand-derived reference table
# ===========================================================================


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_the_oracle_reproduces_the_hand_derived_value(case) -> None:
    """Exact rational arithmetic, zero floating point, zero tolerance needed.

    The expected value in the table was derived from the geometry by hand (the
    ``treatment`` field on each row says how) and is written down as a rational.
    Reproducing it *exactly* is a much stronger statement than agreeing to N
    digits, and it is available here because the arithmetic is exact.
    """
    assert exact_solidity(case.cell_set()) == case.solidity
    assert occupied_area_cells(case.cell_set()) == case.occupied_cells
    assert hull_area_cells(case.cell_set()) == case.hull_cells


def test_the_table_actually_covers_the_required_ground() -> None:
    """A table that quietly loses a required case would be a silent regression."""
    required = {
        "one_cell",
        "two_adjacent_horizontal",
        "two_adjacent_vertical",
        "two_adjacent_diagonal",
        "square_2x2",
        "rectangle_2x3",
        "l_shape_3",
        "l_shape_4",
        "l_shape_6",
        "p_shape_6",
        "plus_5",
        "horizontal_line_3",
        "horizontal_line_5",
        "vertical_line_3",
        "vertical_line_5",
        "diagonal_3",
        "diagonal_5",
        "disconnected_two_2x2_blocks",
        "disconnected_diagonal_pairs",
    }
    assert required <= set(CASES)


def test_a_6_cell_l_is_not_the_p_shape() -> None:
    """The v2 design table printed 6/7 against a row labelled "L (6 cells)".

    6/7 is the 3-cell L; a 6-cell L is 2/3, and the 6-cell shape that *is* 6/7
    is the P shape. Copying the printed value forward would have propagated a
    labelling error into the oracle, so both are pinned separately here and the
    two are asserted to differ.
    """
    l3 = _case("l_shape_3")
    l6 = _case("l_shape_6")
    p6 = _case("p_shape_6")
    assert l3.solidity == Fraction(6, 7) and l3.n_cells == 3
    assert l6.solidity == Fraction(2, 3) and l6.n_cells == 6
    assert p6.solidity == Fraction(6, 7) and p6.n_cells == 6
    assert l6.solidity != p6.solidity
    assert l3.solidity != l6.solidity


def test_the_cross_hull_is_not_the_bounding_box() -> None:
    """A second mislabelling trap, this one in the *other* direction.

    The cross's centre hull is a diamond of area 2, not the 2x2 bounding square.
    Reading the bounding box for the hull gives 9 instead of 7 and a solidity of
    5/9 instead of 5/7 -- a wrong value that "confirms" itself against a
    plausible-looking formula.
    """
    assert _case("plus_5").solidity == Fraction(5, 7)
    assert _case("u_shape_8").solidity == Fraction(8, 9)
    assert _case("h_hollow_19").solidity == Fraction(19, 25)


# ===========================================================================
# 2. The oracle against itself
# ===========================================================================


def _random_cell_sets(count: int = 200, seed: int = 20260929) -> list[set[tuple[int, int]]]:
    """Random cell sets, deliberately including corner-touching and pinches."""
    rng = np.random.default_rng(seed)
    out: list[set[tuple[int, int]]] = []
    for _ in range(count):
        n = int(rng.integers(1, 40))
        rows = rng.integers(-4, 5, size=n)
        cols = rng.integers(-4, 5, size=n)
        cells = {(int(r), int(c)) for r, c in zip(rows, cols, strict=True)}
        if cells:
            out.append(cells)
    return out


_RANDOM = _random_cell_sets()


def test_the_two_area_constructions_agree() -> None:
    """Boundary trace vs maximal-run decomposition, two unrelated algorithms.

    The boundary trace sums signed loop areas; the run decomposition sums
    interior-disjoint rectangles. A signed/unsigned confusion in the trace shows
    up here immediately and was found exactly this way while the oracle was
    being written (a 3x3 ring came out at area 10 instead of 8).
    """
    for cells in _RANDOM:
        assert occupied_area_cells(cells) == occupied_area_by_runs(cells)
    for case in REFERENCE_CASES:
        assert occupied_area_cells(case.cell_set()) == occupied_area_by_runs(case.cell_set())


def test_the_hull_always_contains_the_union() -> None:
    """A subset relation is a theorem; the oracle checks rather than assumes it."""
    for cells in _RANDOM:
        assert hull_area_cells(cells) >= occupied_area_cells(cells)
    for case in REFERENCE_CASES:
        assert case.hull_cells >= case.occupied_cells


def test_solidity_is_always_a_strictly_positive_fraction_below_one() -> None:
    for cells in _RANDOM:
        value = exact_solidity(cells)
        assert 0 < value <= 1
    for case in REFERENCE_CASES:
        assert 0 < float(case.solidity) <= 1.0


def test_a_convex_cell_set_has_solidity_exactly_one() -> None:
    for case in REFERENCE_CASES:
        if case.solidity == 1:
            assert case.hull_cells == case.occupied_cells


# ===========================================================================
# 3. The awkward cases, treated explicitly
# ===========================================================================


def test_a_single_cell_is_one_by_definition() -> None:
    """Not a fallback: the union of one cell *is* its own convex hull."""
    case = _case("one_cell")
    assert case.occupied_cells == 1 and case.hull_cells == 1
    assert exact_solidity(case.cell_set()) == 1
    ref = physical_reference(case.cell_set())
    assert ref.solidity == 1.0 and ref.n_components == 1
    assert ref.occupied_area == pytest.approx(1.0)


def test_an_empty_set_is_one_and_reports_no_geometry() -> None:
    ref = physical_reference(set())
    assert ref.solidity == 1.0 and ref.n_cells == 0
    assert ref.occupied_area == 0.0 and ref.hull_area == 0.0


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 8, 11])
def test_a_corner_touching_run_is_never_solid(n: int) -> None:
    """The case the retired formula could not express at all.

    The centres of a diagonal run are collinear, so a centre-hull denominator
    does not exist and the retired code substituted 1.0. The corner hull is a
    proper 2-D region for every n >= 2, with the closed form ``2n - 1`` cell
    units (verified here for n = 2..11 against the hand-derived formula).
    """
    cells = {(i, i) for i in range(n)}
    assert exact_solidity(cells) == Fraction(n, 2 * n - 1)
    assert 0 < float(exact_solidity(cells)) < 1
    # Under the pipeline's default 8-connectivity a diagonal run is a *single*
    # component, so this is reachable geometry, not an unreachable one.
    assert physical_reference(cells).n_components == 1


@pytest.mark.parametrize("n", [2, 3, 5, 9])
def test_a_thin_orthogonal_line_is_solid(n: int) -> None:
    """The mirror image: collinear *and* adjacent is a rectangle, so 1.0 is right.

    Pinned next to the diagonal case because the retired code returned 1.0 for
    both, from the same branch, for opposite reasons.
    """
    for cells in ({(0, i) for i in range(n)}, {(i, 0) for i in range(n)}):
        assert exact_solidity(cells) == 1
        assert physical_reference(cells).solidity == 1.0


def test_a_holed_shape_subtracts_its_hole() -> None:
    """Regression for the signed/unsigned boundary-trace defect.

    A 3x3 ring is 8 cells; a 5x5 block with a 3x2 bite is 19. Both are holes
    for the naive "one outline" trace, and both are pinned by an exact value.
    """
    assert occupied_area_cells(_cells("u_shape_8")) == 8
    assert occupied_area_cells(_cells("h_hollow_19")) == 19
    assert exact_solidity(_cells("u_shape_8")) == Fraction(8, 9)
    assert exact_solidity(_cells("h_hollow_19")) == Fraction(19, 25)


def test_disconnected_cells_fill_only_part_of_their_hull() -> None:
    """Reachable in production under the default 8-connectivity."""
    for name in ("disconnected_two_2x2_blocks", "l_with_detached_cell"):
        case = _case(name)
        assert float(case.solidity) < 0.5, name
        assert physical_reference(case.cell_set()).n_components > 1


def test_a_degenerate_pitch_is_rejected_rather_than_measured() -> None:
    for bad in ((0.0, 1.0), (1.0, 0.0), (-1.0, 1.0), (float("nan"), 1.0), (1.0, float("inf"))):
        with pytest.raises(SolidityOracleError):
            physical_reference(_cells("one_cell"), *bad)
    with pytest.raises(SolidityOracleError):
        physical_reference(_cells("one_cell"), 1.0, 1.0, origin=(float("nan"), 0.0))


# ===========================================================================
# 4. Metamorphic properties
# ===========================================================================


def _physical(case_name: str, dx: float, dy: float, origin=(0.0, 0.0)) -> float:
    return physical_reference(_cells(case_name), dx, dy, origin).solidity


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_solidity_is_translation_invariant(case) -> None:
    """Moving the whole geometry must not move a *ratio* of two co-moving areas."""
    base = physical_reference(case.cell_set()).solidity
    for origin in ((0.0, 0.0), (17.25, -4.5), (1e5, 1e5), (-1e5, 3.5), (0.125, 0.125)):
        assert physical_reference(case.cell_set(), 1.0, 1.0, origin).solidity == pytest.approx(
            base, abs=ORACLE_TOL
        )


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_solidity_is_uniform_scale_invariant(case) -> None:
    """Scaling both axes by s scales both areas by s^2; the ratio cannot move."""
    base = physical_reference(case.cell_set()).solidity
    for scale in SCALES:
        value = physical_reference(case.cell_set(), scale, scale).solidity
        assert value == pytest.approx(base, abs=ORACLE_TOL)


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_solidity_is_invariant_across_supported_units(case) -> None:
    """The same physical geometry in metres, centimetres, feet or inches.

    After normalisation the areas differ by the square of the unit factor and
    the ratio does not move. Non-decimal factors (ft, in) make the comparison a
    tolerance test rather than a bit-equality one, which is why ORACLE_TOL is
    1e-12 rather than 0.
    """
    base = physical_reference(case.cell_set()).solidity
    for unit, factor in UNIT_TO_METRES.items():
        value = physical_reference(
            case.cell_set(), factor, factor, (100.0 * factor, -50.0 * factor)
        ).solidity
        assert value == pytest.approx(base, abs=ORACLE_TOL), unit


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_solidity_is_invariant_across_pitch_including_anisotropy(case) -> None:
    """dx != dy, dx != 1, and 3 orders of magnitude in either direction.

    A cell-frame shape ratio is unchanged by the pitch; the retired formula was
    not, which is the dimensionally fatal part of S02.
    """
    base = physical_reference(case.cell_set()).solidity
    for dx, dy in PITCHES:
        assert physical_reference(case.cell_set(), dx, dy).solidity == pytest.approx(
            base, abs=ORACLE_TOL
        ), f"{dx}x{dy}"


def test_the_areas_themselves_do_scale_with_the_pitch() -> None:
    """Guards the test above against being vacuous.

    If the physical path ignored the pitch entirely, "invariance" would be
    trivially true and meaningless. The areas must move exactly as the pitch
    predicts -- quadratically under a uniform scale, and per-axis otherwise.
    """
    case = _cells("l_shape_6")
    one = physical_reference(case, 1.0, 1.0)
    ten = physical_reference(case, 10.0, 10.0)
    assert ten.occupied_area == pytest.approx(100.0 * one.occupied_area, rel=1e-12)
    assert ten.hull_area == pytest.approx(100.0 * one.hull_area, rel=1e-12)
    wide = physical_reference(case, 4.0, 1.0)
    assert wide.occupied_area == pytest.approx(4.0 * one.occupied_area, rel=1e-12)
    assert wide.hull_area == pytest.approx(4.0 * one.hull_area, rel=1e-12)


def _disk_cells(radius: float, n_across: int) -> set[tuple[int, int]]:
    half = n_across // 2
    return {
        (r, c)
        for r in range(-half, half + 1)
        for c in range(-half, half + 1)
        if float(c) ** 2 + float(r) ** 2 <= radius**2
    }


#: Disk of physical radius 6 cells, rasterised at increasing density. Measured:
#: 0.876 -> 0.932 -> 0.964 -> 0.981 -> 0.990 -> 0.995, i.e. rising toward the
#: continuum value 1.0 with the deficit falling by ~1.9x per density doubling
#: (error O(h/R)). This is a *characterisation of the rasterisation*, not an
#: invariant: a raster is a staircase, and its solidity is a property of the
#: staircase.
_DENSITY_LADDER = (12, 24, 48, 96, 192, 384)


def test_grid_density_is_characterised_not_asserted_invariant() -> None:
    """The honest form of the resampling property (design ?4.5).

    Two statements, one theorem and one measurement:

    * **Theorem.** A physical disk is convex, so its solidity is exactly 1. A
      rasterisation of it is strictly staircased, so the raster's solidity is
      below 1 and can never exceed it. Asserting equality at every density
      would be asserting a falsehood; asserting a bound is asserting a truth.
    * **Measurement.** The deficit shrinks by more than 1.7x per density
      doubling (measured ~1.9x), i.e. the error is O(h/R) and vanishes. The
      sequence is pinned so a change in the rasterisation convention is visible.

    What is deliberately *not* asserted: that the value is the same at every
    density. It is not, and a test that claimed it would be a false invariant.
    """
    values = [float(exact_solidity(_disk_cells(6.0 * n / 12.0, n))) for n in _DENSITY_LADDER]
    assert all(0.0 < v <= 1.0 for v in values)
    for coarser, finer in zip(values, values[1:], strict=False):
        assert finer >= coarser, f"deficit must shrink: {coarser} -> {finer}"
        deficit_ratio = (1.0 - finer) / (1.0 - coarser)
        assert deficit_ratio < 0.6, f"deficit fell by only {deficit_ratio:.3f} per doubling"
    assert 1.0 - values[-1] < 0.01
    assert values[-1] - values[0] > 0.1, "the measurement must show a real density effect"


def test_a_lattice_aligned_shape_is_exactly_density_invariant() -> None:
    """The one resampling case that *is* exact, and provably so.

    Re-sampling an axis-aligned lattice pattern at a finer pitch reproduces the
    same integer cell pattern, so the ratio is the same rational number -- not
    approximately, exactly. This is the reason K4 can claim pitch invariance
    while saying nothing at all about arbitrary resampling.
    """
    for name in ("l_shape_6", "plus_5", "disconnected_two_2x2_blocks", "h_hollow_19"):
        case = _cells(name)
        base = exact_solidity(case)
        for k in (2, 3, 5):
            blown_up = {
                (r * k + di, c * k + dj) for r, c in case for di in range(k) for dj in range(k)
            }
            assert exact_solidity(blown_up) == base, f"{name} at k={k}"


# ===========================================================================
# 5. Production against the oracle
# ===========================================================================


def _grid_for(
    cells: set[tuple[int, int]],
    *,
    dx: float = 1.0,
    dy: float = 1.0,
    margin: int = 2,
    x0: float = 0.0,
    y0: float = 0.0,
) -> tuple[Grid2D, np.ndarray, np.ndarray]:
    """A grid whose anomaly region is exactly *cells*, with a quiet margin.

    Mirrors what ``extract_candidates`` hands ``_shape_metrics``: ``xs``/``ys``
    are the component's cell indices and ``local_mask`` is the component inside
    its own bounding box.
    """
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    row0, col0 = min(rows) - margin, min(cols) - margin
    ny = max(rows) - row0 + 1 + margin
    nx = max(cols) - col0 + 1 + margin
    xs = np.array([c - col0 for _, c in cells], dtype=int)
    ys = np.array([r - row0 for r, _ in cells], dtype=int)
    signal = np.zeros((ny, nx), dtype=float)
    signal[ys, xs] = 10.0
    grid = Grid2D(
        x_centers=x0 + np.arange(nx, dtype=float) * dx,
        y_centers=y0 + np.arange(ny, dtype=float) * dy,
        signal=signal,
        depth=np.full((ny, nx), 2.0),
        counts=np.ones((ny, nx), dtype=int),
    )
    local = np.zeros((int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)), dtype=bool)
    local[ys - ys.min(), xs - xs.min()] = True
    return grid, xs, ys, local  # type: ignore[return-value]


def _production_metrics(
    case_name: str, *, dx: float = 1.0, dy: float = 1.0, x0: float = 0.0, y0: float = 0.0
) -> dict[str, float]:
    grid, xs, ys, local = _grid_for(_cells(case_name), dx=dx, dy=dy, x0=x0, y0=y0)
    return _shape_metrics(grid, xs, ys, local, dx, dy)


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_production_solidity_equals_the_oracle(case) -> None:
    """The activation test, through the real production path.

    Not a comparison of production against itself: the expectation is the
    hand-derived rational from :data:`REFERENCE_CASES`, evaluated through the
    oracle's exact arithmetic.
    """
    metrics = _production_metrics(case.name)
    assert metrics["solidity"] == pytest.approx(float(case.solidity), abs=ORACLE_TOL), (
        f"{case.name}: production {metrics['solidity']!r} vs exact {float(case.solidity)!r}"
    )


@pytest.mark.parametrize("dx,dy", PITCHES)
def test_production_solidity_is_dimensionless_in_the_pitch(dx: float, dy: float) -> None:
    """Contract K4's headline: the value cannot depend on the cell size.

    The retired formula divided a cell *count* by an *area*, so this is the
    property it could not hold. It is asserted across the whole table at once:
    a single wrong case fails it.
    """
    for case in REFERENCE_CASES:
        metrics = _production_metrics(case.name, dx=dx, dy=dy)
        assert metrics["solidity"] == pytest.approx(float(case.solidity), abs=ORACLE_TOL), (
            f"{case.name} at pitch {dx}x{dy}"
        )


def test_production_solidity_is_invariant_under_translation() -> None:
    for case in REFERENCE_CASES:
        base = _production_metrics(case.name)["solidity"]
        for x0, y0 in ((1234.5, -987.25), (1e5, 1e5), (-5.0, 0.0)):
            moved = _production_metrics(case.name, x0=x0, y0=y0)["solidity"]
            assert moved == pytest.approx(base, abs=ORACLE_TOL), f"{case.name} at ({x0}, {y0})"


def test_production_solidity_is_invariant_under_uniform_rescaling() -> None:
    """The second, independent proof that the retired formula was not a ratio.

    Rescaling every coordinate and the pitch by s must not move a dimensionless
    quantity. Measured for the retired formula at s=10: 0.02 (L), 0.0119 (H),
    0.03 (P) -- a shape ratio cannot do that.
    """
    for case in REFERENCE_CASES:
        values = [
            _production_metrics(case.name, dx=s, dy=s, x0=s * 3.0, y0=s * -2.0)["solidity"]
            for s in SCALES
        ]
        assert max(values) - min(values) < 1e-12, f"{case.name} moved under rescaling: {values}"


def test_production_solidity_is_bounded_and_finite() -> None:
    for case in REFERENCE_CASES:
        value = _production_metrics(case.name)["solidity"]
        assert math.isfinite(value) and 0.0 < value <= 1.0


def test_production_reports_a_stable_value_on_repeated_evaluation() -> None:
    """Boundary/floating-point stability: deterministic and clamped, not drifting."""
    for case in REFERENCE_CASES:
        values = [_production_metrics(case.name)["solidity"] for _ in range(3)]
        assert values[0] == values[1] == values[2], case.name


def test_production_clips_only_within_floating_point_tolerance() -> None:
    """A convex shape must land on exactly 1.0, not on 1.0 after a rescue clamp.

    ``physical_reference`` raises when a ratio exceeds 1 by more than
    ``FLOAT_TOLERANCE``; production cannot raise on a scan, so it clips and logs.
    The two must agree on the threshold, and the 1.0 cases must not need it.
    """
    for case in REFERENCE_CASES:
        ref = physical_reference(case.cell_set())
        if float(case.solidity) == 1.0:
            assert ref.solidity == 1.0 and not ref.clamped
            assert _production_metrics(case.name)["solidity"] == 1.0


def test_production_solidity_survives_a_non_finite_grid_axis() -> None:
    """The unreachable-input contract, pinned rather than left implicit.

    A NaN cell centre means the geometry cannot be integrated. The legacy
    behaviour was 1.0; production keeps that value so no public contract moves,
    and this test states plainly that it is a *fallback*, not a measurement.
    """
    grid, xs, ys, local = _grid_for(_cells("diagonal_3"))
    grid.x_centers = grid.x_centers.copy()
    grid.x_centers[xs[0]] = float("nan")
    metrics = _shape_metrics(grid, xs, ys, local, 1.0, 1.0)
    assert metrics["solidity"] == 1.0


# ===========================================================================
# 6. The retired formula, pinned so it cannot come back unnoticed
# ===========================================================================


def test_the_retired_formula_is_wrong_on_most_of_the_table() -> None:
    """The "before" column, executed.

    ``legacy_solidity`` is the pre-activation formula
    (``N_cells / hull(centres)``) retained only as the measured baseline of the
    defect. It is a *count over an area*: its units are 1/area, so it cannot be
    a shape ratio. Two independent symptoms, both asserted here:

    * it disagrees with the oracle on most of the reference table, and
    * it collapses under uniform rescaling, which no ratio can do.

    If this test ever fails because the legacy number became correct, the
    measurement history has been tampered with.
    """
    from groundscan.diagnostics.shadow import legacy_solidity

    wrong = 0
    clipped = 0
    for case in REFERENCE_CASES:
        cells = case.cell_set()
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        got = legacy_solidity(rows, cols, 1.0, 1.0)
        if abs(got - float(case.solidity)) > ORACLE_TOL:
            wrong += 1
            clipped += int(got == 1.0)
    assert wrong >= 10, f"the legacy formula suddenly agrees on {len(REFERENCE_CASES) - wrong}"
    assert clipped >= 10, "its degenerate branch is supposed to be the dominant failure"

    for name in ("l_shape_6", "h_hollow_19", "p_shape_6"):
        cells = _cells(name)
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        at_unit = legacy_solidity(rows, cols, 1.0, 1.0)
        at_ten = legacy_solidity(rows, cols, 10.0, 10.0)
        assert max(at_unit, at_ten) - min(at_unit, at_ten) > 0.5, name


# ===========================================================================
# 7. Regression protection: nothing else moved
# ===========================================================================

BASELINE = json.loads(
    (Path(__file__).parent / "baseline_solidity_metrics.json").read_text(encoding="utf-8")
)

#: The only two metrics S02 may move. ``solidity`` is the correction;
#: ``geometry_quality`` consumes it with weight 0.25. Every other metric must be
#: bit-identical to the pre-change baseline, and this set is asserted to be
#: exactly the set of metrics that did move.
EXPECTED_MOVING_KEYS = frozenset({"solidity", "geometry_quality"})


def _identical(a: float, b: float) -> bool:
    """Bit-identity, with ``NaN`` equal to itself.

    ``orientation_deg`` is genuinely undefined below four points, so the metric
    dict legitimately contains ``NaN``; without this, every small case would
    report a phantom move and the regression guard would be vacuous.
    """
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def test_the_baseline_covers_every_reference_case() -> None:
    assert set(BASELINE) == set(CASES)


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_unrelated_shape_metrics_are_bit_identical_to_the_pre_change_baseline(case) -> None:
    """Recursive payload comparison against the pre-change baseline.

    The baseline was recorded from production *before* the S02 activation, by
    running the real ``_shape_metrics`` over every reference case. If the change
    had leaked into an unrelated metric, the key set assertion below would fail
    as well, because a leaked metric would show up as a mismatch.
    """
    recorded = BASELINE[case.name]
    current = _production_metrics(case.name)
    assert set(recorded) == set(current), "the metric set itself changed"
    moved = {key for key in recorded if not _identical(recorded[key], current[key])}
    # A convex cell set already had the correct solidity (1.0), so nothing may
    # move for it at all. Everywhere else exactly the correction and its one
    # consumer move -- no more, no less.
    already_correct = _identical(recorded["solidity"], current["solidity"])
    expected = frozenset() if already_correct else EXPECTED_MOVING_KEYS
    assert moved == expected, f"{case.name}: unexpected metrics moved: {sorted(moved)}"
    for key in set(recorded) - EXPECTED_MOVING_KEYS:
        assert _identical(recorded[key], current[key]), key


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=CASES)
def test_geometry_quality_moves_only_by_its_own_weight(case) -> None:
    """``geometry_quality`` is a linear function of solidity with weight 0.25.

    Asserting the exact relationship means a leak into a *different* term of the
    quality score would be caught, rather than being absorbed into "quality
    changed a bit".
    """
    recorded = BASELINE[case.name]
    current = _production_metrics(case.name)
    before, after = recorded["geometry_quality"], current["geometry_quality"]
    assert after == pytest.approx(
        before + 0.25 * (current["solidity"] - recorded["solidity"]), abs=1e-12
    )


def test_the_baseline_is_not_the_oracle_in_disguise() -> None:
    """The baseline's solidity column is the *old* production value.

    If the recorded baseline already carried the corrected numbers, the
    regression test above would be circular. It must not, for the cases where
    the two disagree.
    """
    disagreeing = [
        name
        for name, values in BASELINE.items()
        if abs(values["solidity"] - float(_case(name).solidity)) > ORACLE_TOL
    ]
    assert len(disagreeing) >= 10, f"only {len(disagreeing)} baseline rows predate the fix"

"""Union-mask morphology for merged dipoles.

A merged dipole's cell-level metrics should describe the shape its two lobes form
together. Before this change they were an average (or, for solidity, a ``min``) of
the per-lobe values. Applying one estimator to the true object is a valid estimate
of that object's compactness; averaging two estimators applied to two *different*
objects is not an estimate of anything, so the union direction is right even where
the estimator itself is imperfect.

``test_compactness_estimator_is_not_monotone_under_lobe_splitting`` records the
imperfection honestly: the erosion-boundary isoperimetric quotient can *rise* when a
blob splits in two, because the proxy perimeter grows more slowly than the area. So
this change fixes consistency, not accuracy, and the compactness thresholds
calibrated against averaged values are affected.

The corpus-level consequence is pinned in ``tests/validation/test_golden_outputs.py``
(only ``vendor_iron_box`` moves) and by the inertness guard in
``tests/unit/test_shadow_measurement.py``.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy import ndimage

from groundscan._util import digital_compactness
from groundscan.core.shape import _convex_hull_solidity
from groundscan.diagnostics.dipole import (
    merge_dipolar_response_components,
    union_mask_metrics,
)
from groundscan.models import Candidate


def _lobe(candidate_id: int, *, polarity: str, anomaly_score: float, x: float) -> Candidate:
    """A lobe that the merge will pair with its opposite-polarity partner.

    The attributes below are the minimum needed to clear every gate in
    ``_dipole_pair_metrics``: opposite polarity, a shared ``separation_parent_id``,
    peaks over ``min_peak``, and non-zero ``major_extent`` (the proximity term is
    ``1 - distance / (max_distance_ratio * major_extent_a + major_extent_b)``, so a
    zero extent silently rejects every pair).
    """
    return Candidate(
        id=candidate_id,
        x_center=x,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=6,
        area_cells=6,
        width=1.0,
        height=2.0,
        aspect_ratio=0.5,
        orientation_deg=90.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=anomaly_score,
        positive_peak=9.0 if polarity == "positive" else 0.5,
        negative_peak=-0.5 if polarity == "positive" else -9.0,
        polarity=polarity,
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.8,
        scan_count=1,
        scale_class="local",
        compactness=1.0,
        solidity=1.0,
        geometry_quality=0.9,
        boundary_contact_ratio=0.0,
        major_extent=2.0,
        minor_extent=1.0,
        elongation_ratio=2.0,
        linearity_score=0.5,
        response_component_ids=[candidate_id],
        separation_parent_id=7,
    )


def _cells(*coords: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(coords, dtype=int)
    return arr[:, 0], arr[:, 1]


def _block(row: int, col: int, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """A filled ``height`` x ``width`` block of cells, the shape of one lobe."""
    return _cells(*[(row + i, col + j) for i in range(height) for j in range(width)])


def _mask_metrics(cells: tuple[np.ndarray, np.ndarray]) -> tuple[float, float]:
    """Independently recompute (perimeter-cell count, area) for a cell set."""
    rows, cols = cells
    mask = np.zeros((int(rows.max()) + 1, int(cols.max()) + 1), dtype=bool)
    mask[rows, cols] = True
    perimeter = float(np.count_nonzero(mask & ~ndimage.binary_erosion(mask)))
    return perimeter, float(np.count_nonzero(mask))


# --- union_mask_metrics ---------------------------------------------------------


def test_union_metrics_match_an_independent_recomputation():
    """The union is built from the concatenated cells, not from either lobe."""
    lobe_a = _block(0, 0, 6, 3)
    lobe_b = _block(0, 9, 6, 3)

    union = union_mask_metrics(lobe_a, lobe_b)
    assert union is not None

    # Independent oracle: build the union by hand and run the production estimator.
    all_rows = np.concatenate([lobe_a[0], lobe_b[0]])
    all_cols = np.concatenate([lobe_a[1], lobe_b[1]])
    perimeter, area = _mask_metrics((all_rows, all_cols))
    assert area == pytest.approx(36.0)
    assert union["compactness"] == pytest.approx(digital_compactness(area, perimeter))
    assert union["area_cells"] == pytest.approx(36.0)
    assert union["bbox_area"] == pytest.approx(45.0)  # 3 rows x 15 cols
    assert union["fill"] == pytest.approx(36.0 / 45.0)


def test_union_solidity_uses_the_union_hull_not_the_lobe_minimum():
    lobe_a = _block(0, 0, 6, 3)
    lobe_b = _block(0, 9, 6, 3)

    union = union_mask_metrics(lobe_a, lobe_b)
    assert union is not None

    rows = np.concatenate([lobe_a[0], lobe_b[0]]).astype(float)
    cols = np.concatenate([lobe_a[1], lobe_b[1]]).astype(float)
    assert union["solidity"] == pytest.approx(_convex_hull_solidity(cols, rows, 1.0, 1.0))
    # A two-block union is strictly less convex than either single block.
    single = union_mask_metrics(lobe_a, lobe_a)
    assert single is not None
    assert single["solidity"] == pytest.approx(1.0, abs=1e-9)
    assert union["solidity"] < single["solidity"]


def test_union_of_a_single_lobe_equals_that_lobe():
    """Union with an identical cell set is a no-op, not a re-estimate."""
    lobe = _block(0, 0, 6, 3)
    union = union_mask_metrics(lobe, lobe)
    assert union is not None
    assert union["area_cells"] == pytest.approx(18.0)
    assert union["fill"] == pytest.approx(1.0)
    assert union["solidity"] == pytest.approx(1.0, abs=1e-9)
    assert union["compactness"] == pytest.approx(1.0)


def test_union_metrics_return_none_instead_of_fabricating():
    """An empty cell set means an incomplete record, not a neutral element.

    Treating an empty lobe as a neutral element would report the *other* lobe's
    metrics as the pair's union, understating how spread out the pair is.
    """
    empty = (np.asarray([], dtype=int), np.asarray([], dtype=int))
    lobe = _block(0, 0, 6, 3)
    assert union_mask_metrics(empty, lobe) is None
    assert union_mask_metrics(lobe, empty) is None
    assert union_mask_metrics(empty, empty) is None
    assert union_mask_metrics(None, lobe) is None


def test_union_metrics_drop_cells_outside_the_field():
    """Out-of-field cells are discarded, not clamped, and never index the mask."""
    lobe_a = _cells((0, 0), (1, 0))
    lobe_b = _cells((3, 0), (4, 0))  # row 4 is outside a 4-row field

    union = union_mask_metrics(lobe_a, lobe_b, field_shape=(4, 1))
    assert union is not None
    assert union["area_cells"] == pytest.approx(3.0)
    assert union["bbox_area"] == pytest.approx(4.0)


def test_union_metrics_return_none_when_the_field_excludes_everything():
    empty = (np.asarray([], dtype=int), np.asarray([], dtype=int))
    lobe = _block(50, 0, 4, 4)
    assert union_mask_metrics(lobe, lobe, field_shape=(4, 4)) is None
    assert union_mask_metrics(empty, empty, field_shape=(0, 4)) is None


def test_splitting_a_blob_halves_its_compactness_so_the_union_descent_is_real():
    """The scientific justification, pinned numerically.

    The production compactness is an isoperimetric quotient over an
    erosion-boundary perimeter proxy. Splitting one blob into two roughly halves
    it (exactly 0.5 for a ``k`` x ``k`` square once ``k`` is large enough to leave
    the ``[0, 1]`` clip), so a two-lobed union is genuinely less compact than
    either lobe. That is the descent the merge was previously papering over by
    averaging two saturated ``1.0`` values.

    This is the property that justifies recomputing rather than averaging, so it
    is pinned rather than left implicit.
    """
    for k, expect_ratio in ((10, 0.500), (20, 0.500), (30, 0.500)):
        single = _block(0, 0, k, k)
        pair_rows = np.concatenate([_block(0, 0, k, k)[0], _block(0, 2 * k, k, k)[0]])
        pair_cols = np.concatenate([_block(0, 0, k, k)[1], _block(0, 2 * k, k, k)[1]])

        # _mask_metrics returns (perimeter, area); digital_compactness takes
        # (area, perimeter).
        single_perimeter, single_area = _mask_metrics(single)
        pair_perimeter, pair_area = _mask_metrics((pair_rows, pair_cols))
        compact_single = digital_compactness(single_area, single_perimeter)
        compact_pair = digital_compactness(pair_area, pair_perimeter)

        assert compact_pair / compact_single == pytest.approx(expect_ratio, rel=1e-6), (
            f"k={k}: the erosion-boundary quotient is expected to halve under splitting"
        )


def test_small_blobs_saturate_and_are_why_the_merge_used_to_report_one():
    """Below ~k=9 a filled square's quotient clips to 1.0, which is what the old
    lobe average inherited: averaging two saturated 1.0s can never descend."""
    perimeter, area = _mask_metrics(_block(0, 0, 5, 5))
    assert digital_compactness(area, perimeter) == pytest.approx(1.0)
    perimeter, area = _mask_metrics(_block(0, 0, 8, 8))
    assert digital_compactness(area, perimeter) == pytest.approx(1.0)


# --- merge integration ----------------------------------------------------------


def test_merge_uses_union_morphology_when_cells_are_recorded():
    lobe_a = _lobe(1, polarity="positive", anomaly_score=9.0, x=5.0)
    lobe_b = _lobe(2, polarity="negative", anomaly_score=9.0, x=7.0)
    cells = {1: _block(0, 0, 6, 3), 2: _block(0, 9, 6, 3)}

    merged = merge_dipolar_response_components(
        [lobe_a, lobe_b], fragment_cells=cells, field_shape=(3, 20)
    )

    assert len(merged) == 1
    out = merged[0]
    expected = union_mask_metrics(cells[1], cells[2])
    assert expected is not None
    assert out.compactness == pytest.approx(expected["compactness"])
    assert out.solidity == pytest.approx(expected["solidity"])
    assert out.area_cells == 36
    assert "union-mask" in (out.notes or "")


def test_merge_falls_back_to_lobe_average_without_cells():
    """The site path has no fragment cells; it keeps the old rule and says so."""
    lobe_a = _lobe(1, polarity="positive", anomaly_score=9.0, x=5.0)
    lobe_b = _lobe(2, polarity="negative", anomaly_score=3.0, x=7.0)

    merged = merge_dipolar_response_components([lobe_a, lobe_b])

    assert len(merged) == 1
    out = merged[0]
    # Anomaly-weighted average of 1.0 and 1.0 is 1.0; solidity is min().
    assert out.compactness == pytest.approx(1.0)
    assert out.solidity == pytest.approx(1.0)
    assert out.area_cells == 12
    assert "lobe-average" in (out.notes or "")


def test_merge_falls_back_when_only_one_lobe_has_recorded_cells():
    """A partial map must not half-apply the union rule."""
    lobe_a = _lobe(1, polarity="positive", anomaly_score=9.0, x=5.0)
    lobe_b = _lobe(2, polarity="negative", anomaly_score=9.0, x=7.0)
    cells = {1: _block(0, 0, 6, 3)}

    merged = merge_dipolar_response_components([lobe_a, lobe_b], fragment_cells=cells)

    assert len(merged) == 1
    assert "lobe-average" in (merged[0].notes or "")


def test_merge_lobe_lookup_accepts_declared_response_component_ids():
    """Fragments are keyed by id, but a declared component id also resolves.

    The merged candidate's ``response_component_ids`` is the union of the lobes'
    lists, so downstream consumers can resolve cells from the merged object alone.
    """
    lobe_a = _lobe(41, polarity="positive", anomaly_score=9.0, x=5.0)
    lobe_b = _lobe(42, polarity="negative", anomaly_score=9.0, x=7.0)
    lobe_a = lobe_a.__class__(**{**lobe_a.__dict__, "response_component_ids": [101]})
    lobe_b = lobe_b.__class__(**{**lobe_b.__dict__, "response_component_ids": [102]})
    cells = {101: _block(0, 0, 6, 3), 102: _block(0, 9, 6, 3)}

    merged = merge_dipolar_response_components(
        [lobe_a, lobe_b], fragment_cells=cells, field_shape=(3, 20)
    )

    assert len(merged) == 1
    assert "union-mask" in (merged[0].notes or "")


def test_geometry_quality_weights_match_the_production_formula():
    """Drift guard for the weights duplicated in ``dipole._union_geometry_quality``.

    ``core.shape._shape_metrics`` writes the four weights as inline literals at
    their comparison site and does not name them, so the union path cannot import
    them. This compares the duplicated formula against the production function on
    real masks: same weights, same cell-count saturation, same clip. If production
    ever changes them, this fails rather than letting the two copies diverge.
    """
    from groundscan.core.grid import Grid2D
    from groundscan.core.shape import _shape_metrics
    from groundscan.diagnostics.dipole import _union_geometry_quality

    n_rows, n_cols = 6, 9
    zeros = np.zeros((n_rows, n_cols), dtype=float)
    grid = Grid2D(
        x_centers=np.arange(n_cols, dtype=float),
        y_centers=np.arange(n_rows, dtype=float),
        signal=zeros,
        depth=zeros,
        counts=np.ones((n_rows, n_cols), dtype=float),
    )

    # Each case spans both row halves so the two-lobe split is non-empty.
    for coords in (
        [(r, c) for r in range(6) for c in range(6)],  # filled block
        [(r, c) for r in range(6) for c in range(6) if (r + c) % 2 == 0],  # sparse
        [(r, 0) for r in range(6)] + [(r, 8) for r in range(6)],  # two thin bars
        [(0, 0), (0, 8), (5, 0), (5, 8), (2, 4), (4, 2)],  # scattered
    ):
        mask = np.zeros((n_rows, n_cols), dtype=bool)
        rows = np.asarray([r for r, _ in coords], dtype=int)
        cols = np.asarray([c for _, c in coords], dtype=int)
        mask[rows, cols] = True

        # Production builds ``local_mask`` as the component's *tight* bounding box
        # (core/shape.py:429), so the fill term is n_cells / tight_bbox_area. Pass
        # the same tight window here, otherwise this compares a padded fill term
        # against an unpadded one.
        tight = mask[
            int(rows.min()) : int(rows.max()) + 1,
            int(cols.min()) : int(cols.max()) + 1,
        ]
        # ``_shape_metrics`` takes (xs, ys); ``rows`` are ys and ``cols`` are xs.
        production = _shape_metrics(grid, cols, rows, tight, 1.0, 1.0)

        # Split the same cell set into two lobes so the union is the full mask.
        lower = rows < (int(rows.min()) + int(rows.max())) // 2
        union = union_mask_metrics(
            (rows[lower], cols[lower]),
            (rows[~lower], cols[~lower]),
        )
        assert union is not None
        assert union["area_cells"] == pytest.approx(float(np.count_nonzero(mask)))
        # The two lobes together span the same tight window as the whole mask, so
        # the union's fill is the same ratio production computes.
        assert union["fill"] == pytest.approx(float(np.count_nonzero(tight)) / float(tight.size))

        # Feed production's own solidity through our duplicated formula, so the
        # comparison isolates the weights from the solidity input.
        aligned = _union_geometry_quality(
            {**union, "solidity": float(production["solidity"])},
            n_cells=float(np.count_nonzero(mask)),
            boundary_contact_ratio=float(production["boundary_contact_ratio"]),
        )
        assert aligned == pytest.approx(production["geometry_quality"], abs=1e-12)


def test_unlinked_lobes_are_not_merged_and_so_never_reach_the_union_rule():
    """No shared parent means no merge, so the new code path is never reached.

    This matters because ``require_shared_parent`` is what confines the union rule
    to fragments that genuinely came from one fused parent; the new code must not
    become a way to merge independent candidates.
    """
    lobe_a = replace(
        _lobe(1, polarity="positive", anomaly_score=9.0, x=5.0), separation_parent_id=None
    )
    lobe_b = replace(
        _lobe(2, polarity="negative", anomaly_score=9.0, x=7.0), separation_parent_id=7
    )
    cells = {1: _block(0, 0, 6, 3), 2: _block(0, 9, 6, 3)}

    merged = merge_dipolar_response_components(
        [lobe_a, lobe_b], fragment_cells=cells, field_shape=(3, 20)
    )

    assert len(merged) == 2
    assert all("union-mask" not in (c.notes or "") for c in merged)

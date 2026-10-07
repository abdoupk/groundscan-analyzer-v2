"""Wave 1 / Stage 1 (PR-2, PR-3, PR-4): shadow measurement.

Shadow measurement computes the corrected S01/S02/S03 values beside the shipped
ones and records the delta. It decides nothing. This file pins both halves of
that promise:

* the corrected values are *right* -- the S02 oracle is the 19-geometry
  reference table from v2 §5.3, a set of shapes with known exact values, so
  correctness is verifiable without judgement;
* the shadow is *inert* -- with the flag on, every golden hash is unchanged and
  nothing new reaches ``analysis.json`` or the machine contract.

Evidence discipline (v2 §12.1): every oracle derives from the synthetic
construction and its known mathematical structure. No test asserts "the current
output is X", which is the discipline whose absence let S01, S02 and S03 reach
production.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from groundscan.diagnostics.shadow import (
    ROLE_CONFLICT,
    ROLE_DECOMPOSITION,
    ROLE_RESPONSE,
    ROLE_UNRESOLVED,
    ShadowMeasurement,
    assign_role,
    exact_solidity,
    is_top_level,
    legacy_solidity,
    measure_roles,
    measure_scale,
    structural_alternative_unmodelled,
)
from groundscan.models import Candidate, ScanData, ScanMetadata
from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan

# ---------------------------------------------------------------------------
# The S02 reference table (v2 §5.3) -- the shadow's oracle
# ---------------------------------------------------------------------------
# Each row is a named cell set plus its *exact* solidity, derived from the
# geometry (hull of the 4N cell corners), and the value the **retired** formula
# produced for the same set. The exact column is the specification; the legacy
# column is the defect being measured, not a target.
#
# Provenance of these numbers: 18 of the 19 rows reproduce the values printed in
# v2 §5.3 exactly. The one exception is `l_shape_6`, documented in
# `test_l_shape_six_row_disagrees_with_the_design_table` below -- a 6-cell L has
# exact solidity 2/3, not the 6/7 the table prints, though the table's *verdict*
# for that row (the legacy formula clips it to 1.0) is correct either way.
#
# Stage 3 note: the table is duplicated in
# `groundscan.validation.solidity_reference.REFERENCE_CASES`, which additionally
# carries the hand-derived *rational* for every row plus the extra geometries the
# brief requires. `test_solidity_reference.py` pins production against that
# table; this file keeps the shadow-side view of the same rows.
REFERENCE_TABLE: tuple[tuple[str, tuple[tuple[int, int], ...], float, float], ...] = (
    ("one_cell", ((0, 0),), 1.000000, 1.000000),
    ("two_adjacent_horizontal", ((0, 0), (0, 1)), 1.000000, 1.000000),
    ("two_adjacent_vertical", ((0, 0), (1, 0)), 1.000000, 1.000000),
    ("straight_line_3", ((0, 0), (0, 1), (0, 2)), 1.000000, 1.000000),
    ("straight_line_5_vertical", ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0)), 1.000000, 1.000000),
    # Corner-touching: the centre hull is degenerate, which is what the retired
    # QhullError branch silently reported as "perfectly solid".
    ("diagonal_3", ((0, 0), (1, 1), (2, 2)), 0.600000, 1.000000),
    ("diagonal_5", ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4)), 0.555556, 1.000000),
    ("square_2x2", tuple((r, c) for r in range(2) for c in range(2)), 1.000000, 1.000000),
    ("square_3x3", tuple((r, c) for r in range(3) for c in range(3)), 1.000000, 1.000000),
    ("square_5x5", tuple((r, c) for r in range(5) for c in range(5)), 1.000000, 1.000000),
    ("rectangle_5x2", tuple((r, c) for r in range(2) for c in range(5)), 1.000000, 1.000000),
    (
        "l_shape_6",
        ((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (2, 0)),
        0.666667,
        1.000000,
    ),
    (
        "u_shape_8",
        ((0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)),
        0.888889,
        1.000000,
    ),
    ("plus_5", ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1)), 0.714286, 1.000000),
    (
        "h_hollow_19",
        tuple(
            set((r, c) for r in range(5) for c in range(5))
            - {(3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3)}
        ),
        0.760000,
        1.000000,
    ),
    (
        "t_shape_7",
        ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 2)),
        0.636364,
        1.000000,
    ),
    # Disconnected cell sets in one component: the retired formula did not even
    # clip here, it returned a plausible wrong number that drives classification.
    (
        "disconnected_two_2x2_blocks",
        ((0, 0), (0, 1), (1, 0), (1, 1), (5, 5), (5, 6), (6, 5), (6, 6)),
        0.333333,
        0.727273,
    ),
    ("disconnected_one_plus_two", ((0, 0), (0, 1), (1, 0)), 0.857143, 1.000000),
    (
        "l_with_detached_cell",
        ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 0), (5, 5)),
        0.333333,
        0.700000,
    ),
)

#: Five pitches, including anisotropic and extreme-scale ones: the exact value
#: must not move for any of them (contract K4).
PITCHES: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (0.5, 0.5),
    (0.5, 0.25),
    (2.0, 0.5),
    (1000.0, 1000.0),
)


def _arrays(cells):
    rows = np.asarray([r for r, _ in cells], dtype=int)
    cols = np.asarray([c for _, c in cells], dtype=int)
    return rows, cols


@pytest.mark.parametrize("name, cells, want_exact, want_legacy", REFERENCE_TABLE)
def test_exact_solidity_matches_the_reference_table(name, cells, want_exact, want_legacy):
    rows, cols = _arrays(cells)
    exact = exact_solidity(rows, cols, 1.0, 1.0)
    assert round(exact, 6) == pytest.approx(want_exact, abs=5e-7), (
        f"{name}: exact solidity must match the §5.3 oracle"
    )
    # The defect being measured: the retired formula and the exact value disagree
    # on these geometries.
    assert round(legacy_solidity(rows, cols, 1.0, 1.0), 6) == pytest.approx(
        want_legacy, abs=5e-7
    ), f"{name}: legacy column drifted from the measured baseline"


@pytest.mark.parametrize("name, cells, want_exact, want_legacy", REFERENCE_TABLE)
@pytest.mark.parametrize("dx, dy", PITCHES)
def test_exact_solidity_is_invariant_across_pitch(name, cells, want_exact, want_legacy, dx, dy):
    """Contract K4: dimensionless, so re-sampling cannot move it."""
    rows, cols = _arrays(cells)
    exact = exact_solidity(rows, cols, dx, dy)
    assert 0.0 < exact <= 1.0
    assert round(exact, 6) == pytest.approx(want_exact, abs=5e-7), f"{name} at pitch {dx}x{dy}"


def test_the_design_headline_claim_holds_exactly():
    """ "10 of 19 wrong at unit pitch: 8 clipped, 2 wrong-but-not-clipped" (v2 §5.3).

    This is the *retired* formula's failure census, kept as the measurement the
    activation decision was made on. Production no longer uses it (Stage 3); the
    test remains because the number is the reason the correction was necessary.
    """
    wrong = []
    clipped = []
    for name, cells, _want_exact, want_legacy in REFERENCE_TABLE:
        rows, cols = _arrays(cells)
        if round(exact_solidity(rows, cols, 1.0, 1.0), 6) != round(want_legacy, 6):
            wrong.append(name)
            if want_legacy == 1.0:
                clipped.append(name)
    assert len(REFERENCE_TABLE) == 19
    assert len(wrong) == 10, f"expected 10 wrong cases, got {wrong}"
    assert len(clipped) == 8, f"expected 8 clipped to 1.0, got {clipped}"
    # The two that are wrong *without* being clipped are the dangerous ones:
    # a plausible number that actively drives classification.
    assert set(wrong) - set(clipped) == {
        "disconnected_two_2x2_blocks",
        "l_with_detached_cell",
    }


def test_l_shape_six_row_disagrees_with_the_design_table():
    """Record the one §5.3 row that does not reproduce, rather than fudge it.

    The v2 table prints 0.857143 = 6/7 against a row labelled "L (6 cells)". That
    value belongs to a 3-cell L (and to the 6-cell P shape); a 6-cell L of this
    arm layout is 6 of the 9 cells of its corner hull, i.e. 2/3. The table's
    *verdict* for the row is unaffected: the retired formula returns 1.0 either
    way, so the row was still wrong. The value is pinned from the geometry.
    Stage 3 extends the same discipline to the whole table -- see
    ``validation.solidity_reference.REFERENCE_CASES`` and
    ``test_solidity_reference.py::test_a_6_cell_l_is_not_the_p_shape``.
    """
    rows, cols = _arrays(((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (2, 0)))
    assert exact_solidity(rows, cols, 1.0, 1.0) == pytest.approx(2 / 3, abs=1e-12)
    assert legacy_solidity(rows, cols, 1.0, 1.0) == 1.0


def test_exact_solidity_is_invariant_under_uniform_rescaling():
    """The retired formula is NOT; that is a second, independent defect."""
    for name, cells, _exact, _legacy in REFERENCE_TABLE:
        rows, cols = _arrays(cells)
        values = [exact_solidity(rows, cols, s, s) for s in (0.01, 0.1, 1.0, 10.0, 1000.0)]
        assert max(values) - min(values) < 1e-12, f"{name}: exact moved under rescaling"
    # ...and the retired one demonstrably collapses, which is why it could not be
    # a shape ratio at all.
    rows, cols = _arrays(((0, 0), (0, 1), (0, 2), (1, 0), (2, 0)))
    legacy = [legacy_solidity(rows, cols, s, s) for s in (0.01, 1.0, 10.0, 1000.0)]
    assert max(legacy) - min(legacy) > 0.5


def test_exact_solidity_is_defined_where_the_retired_one_had_no_degenerate_case():
    """Cell counts >= 2 never degenerate, including corner-touching runs."""
    for n in range(2, 8):
        rows, cols = _arrays(tuple((i, i) for i in range(n)))
        exact = exact_solidity(rows, cols, 1.0, 1.0)
        assert 0.0 < exact < 1.0, f"diagonal {n} must be a proper 2-D corner hull"
        assert legacy_solidity(rows, cols, 1.0, 1.0) == 1.0


def test_exact_solidity_rejects_a_degenerate_pitch():
    rows, cols = _arrays(((0, 0), (0, 1)))
    assert np.isnan(exact_solidity(rows, cols, 0.0, 1.0))
    assert np.isnan(exact_solidity(rows, cols, float("nan"), 1.0))


def test_exact_solidity_of_an_empty_set_is_one():
    assert exact_solidity(np.array([], dtype=int), np.array([], dtype=int), 1.0, 1.0) == 1.0


def test_production_now_agrees_with_the_shadow_oracle_on_every_row():
    """The cross-check Stage 3 turned the S02 shadow into.

    Production computes the corner hull through the identity
    ``hull(cells) = hull(centres) (+) cell``; the shadow computes it directly from
    the 4N corners. Two unrelated derivations of the same quantity must agree on
    every row of the table, or one of them is wrong.
    """
    from groundscan.core.shape import _convex_hull_solidity

    for name, cells, want_exact, _legacy in REFERENCE_TABLE:
        rows, cols = _arrays(cells)
        production = _convex_hull_solidity(cols.astype(float), rows.astype(float), 1.0, 1.0)
        oracle = exact_solidity(rows, cols, 1.0, 1.0)
        assert production == pytest.approx(oracle, abs=1e-12), name
        assert round(production, 6) == pytest.approx(want_exact, abs=5e-7), name


def test_the_legacy_column_is_not_the_production_formula_any_more():
    """Guards the rename: the legacy helper must not silently track production.

    If someone "fixed" ``legacy_solidity`` to delegate to production, the defect
    census would become vacuous -- it would report that the retired formula
    agreed with the oracle on everything, which is false and would hide the
    history. The value below is the retired formula's, pinned.
    """
    rows, cols = _arrays(((0, 0), (0, 1), (1, 0)))
    assert legacy_solidity(rows, cols, 1.0, 1.0) == 1.0  # 3-cell L is 6/7, not 1.0
    assert exact_solidity(rows, cols, 1.0, 1.0) == pytest.approx(6 / 7, abs=1e-12)


def test_shadow_geometry_quality_matches_production():
    """The shadow re-derives geometry_quality; it must not drift from shape.py."""
    from groundscan.diagnostics.shadow import _shadow_geometry_quality

    for n_cells, fraction, solidity, boundary in (
        (5, 0.5, 0.8, 0.0),
        (40, 0.9, 0.42, 0.5),
        (3, 0.2, 1.0, 1.0),
        (120, 1.0, 0.6, 0.1),
    ):
        want = float(
            np.clip(
                0.30 * min(n_cells / 10.0, 1.0)
                + 0.25 * min(fraction, 1.0)
                + 0.25 * solidity
                + 0.20 * (1.0 - min(boundary, 1.0)),
                0.0,
                1.0,
            )
        )
        got = _shadow_geometry_quality(
            n_cells=n_cells,
            local_fraction=fraction,
            solidity=solidity,
            boundary_contact_ratio=boundary,
        )
        assert got == pytest.approx(want, abs=1e-12)


# ---------------------------------------------------------------------------
# S01 -- role assignment (contracts K1 / K2)
# ---------------------------------------------------------------------------


def _candidate(**overrides) -> Candidate:
    base = dict(
        id=1,
        x_center=0.0,
        y_center=0.0,
        depth_mean=float("nan"),
        depth_std=float("nan"),
        n_points=3,
        area_cells=3,
        width=1.0,
        height=1.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=1.0,
        mean_signal=1.0,
        anomaly_score=5.0,
        shape_class="compact",
        pattern_hypothesis="unclassified",
        confidence=0.0,
    )
    base.update(overrides)
    return Candidate(**base)


def test_a_plain_finding_is_a_top_level_response():
    candidate = _candidate()
    assert assign_role(candidate) == ROLE_RESPONSE
    assert is_top_level(assign_role(candidate))


def test_a_decomposed_fragment_is_nested():
    """v2 §1.2: the loss of the level-5/level-6 distinction is the defect."""
    candidate = _candidate(id=3, separation_status="decomposed-consensus", separation_parent_id=2)
    assert assign_role(candidate) == ROLE_DECOMPOSITION
    assert not is_top_level(assign_role(candidate))


def test_an_unsplittable_parent_is_unresolved():
    candidate = _candidate(
        separation_status="unresolved-undersegmented", separation_fragment_count=3
    )
    assert assign_role(candidate) == ROLE_UNRESOLVED
    assert not is_top_level(assign_role(candidate))


def test_a_polarity_conflict_is_a_top_level_conflict():
    candidate = _candidate(polarity_conflict=True)
    assert assign_role(candidate) == ROLE_CONFLICT
    assert is_top_level(assign_role(candidate))


def test_the_overlap_diagnostic_alone_is_recorded_as_a_model_gap_not_a_demotion():
    """v2 §4.6: a structural alternative is a model gap, recorded not filled.

    Folding this into `unresolved` would invent a nesting decision the engine
    never made, and would make the multiplicity census vacuous.
    """
    candidate = _candidate(
        unresolved_overlap_score=0.92,
        unresolved_overlap_reason="strong secondary response shoulder",
    )
    assert assign_role(candidate) == ROLE_RESPONSE
    assert structural_alternative_unmodelled(candidate)


def test_decomposition_outranks_unresolved_when_both_apply():
    """Precedence, pinned: `decomposition` is the structural fact that matters.

    A fragment produced by the separation stage stays a fragment even when the
    overlap diagnostic also fires, because "this is a fragment of a response
    region" is exactly the level-5/level-6 distinction the defect is about.
    """
    candidate = _candidate(
        separation_status="decomposed-consensus",
        separation_parent_id=2,
        separation_fragment_count=2,
        unresolved_overlap_score=0.8,
    )
    assert assign_role(candidate) == ROLE_DECOMPOSITION
    assert not structural_alternative_unmodelled(candidate)


def test_overlap_with_separation_context_but_no_fragment_is_unresolved():
    candidate = _candidate(
        separation_status="unresolved-undersegmented",
        separation_fragment_count=3,
        unresolved_overlap_score=0.8,
        unresolved_overlap_reason="shoulder remains",
    )
    assert assign_role(candidate) == ROLE_UNRESOLVED
    assert not structural_alternative_unmodelled(candidate)


def test_an_unmeasured_overlap_score_is_not_treated_as_a_measurement():
    """0.0 means "not measured"; the shadow must not read it as "no overlap"."""
    candidate = _candidate(unresolved_overlap_score=0.0, unresolved_overlap_reason="")
    assert not structural_alternative_unmodelled(candidate)
    assert assign_role(candidate) == ROLE_RESPONSE


# ---------------------------------------------------------------------------
# S01 -- the within-response separation distribution (the d_res input)
# ---------------------------------------------------------------------------


def test_separations_are_measured_only_within_one_response_region():
    same = [_candidate(id=i, centroid_weighted_x=float(i)) for i in (1, 2, 3)]
    for c in same:
        c.response_component_ids = [7]
    records = measure_roles(same)
    assert [r.candidate_id for r in records] == [1, 2, 3]
    for record in records:
        assert len(record.within_response_separations) == 2
    # 3 points 1 apart on a line: each has a neighbour at 1.0 and one at 2.0.
    assert records[0].within_response_separations == (1.0, 2.0)


def test_findings_in_different_response_regions_produce_no_separation():
    a = _candidate(id=1, response_component_ids=[1])
    b = _candidate(id=2, response_component_ids=[2])
    records = measure_roles([a, b])
    assert all(not r.within_response_separations for r in records)


def test_the_coincident_position_case_is_visible_in_the_distribution():
    """The measured S01 defect: several findings at the *same* coordinates."""
    coincident = [_candidate(id=i, x_center=1.8889, y_center=4.0) for i in (1, 2, 3, 4)]
    for c in coincident:
        c.response_component_ids = [11]
    records = measure_roles(coincident)
    distances = [d for r in records for d in r.within_response_separations]
    assert distances, "the coincident case must produce measurements"
    assert max(distances) == pytest.approx(0.0, abs=1e-9)


def test_a_site_finding_with_no_region_membership_yields_no_separation():
    """The site path never populates response_component_ids; nothing is invented."""
    records = measure_roles([_candidate(id=1), _candidate(id=2)])
    assert all(not r.within_response_separations for r in records)


# ---------------------------------------------------------------------------
# S03 -- the scale-status shadow
# ---------------------------------------------------------------------------


def test_scale_shadow_records_the_status_without_changing_the_number():
    rng = np.random.default_rng(21)
    residual = rng.normal(0.0, 1.0, 4000)
    shadow = measure_scale(residual)
    assert shadow is not None
    assert shadow.estimate.status == "valid"
    # No caller switched: the shipped and shadow values are the same magnitude.
    assert shadow.ratio == pytest.approx(1.0, rel=1e-12)


def test_scale_shadow_flags_the_degenerate_regime():
    """The census the activation decision needs: how often is scale unmeasurable."""
    shadow = measure_scale(np.zeros(4000))
    assert shadow is not None
    assert shadow.estimate.is_indeterminate
    assert not np.isfinite(shadow.ratio)
    assert shadow.to_dict()["scale"] is None
    assert shadow.to_dict()["status"] == "indeterminate"


def test_scale_shadow_is_none_for_an_empty_residual():
    assert measure_scale(None) is None
    assert measure_scale(np.array([np.nan, np.nan])) is None


# ---------------------------------------------------------------------------
# The shadow is inert
# ---------------------------------------------------------------------------


def _two_bump_scan(n: int = 40, seed: int = 5) -> ScanData:
    rng = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0.0, 1.0, size=(n, n))
    signal += 12.0 * np.exp(-(((gx - 12) ** 2 + (gy - 12) ** 2) / (2 * 4.0**2)))
    signal += 12.0 * np.exp(-(((gx - 27) ** 2 + (gy - 20) ** 2) / (2 * 4.0**2)))
    return ScanData(
        x=gx.ravel(),
        y=gy.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


def test_shadow_is_off_by_default_and_computes_nothing(tmp_path):
    grid, anomaly, _candidates = analyze_scan(
        _two_bump_scan(),
        tmp_path / "off",
        label="s",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert anomaly.shadow is None


def test_the_flag_is_rejected_rather_than_silently_ignored():
    with pytest.raises(ValueError, match="shadow_measurement"):
        AnalysisConfig(shadow_measurement="on")


def _nan_aware(value):
    """Compare payloads treating NaN as equal to NaN.

    ``Candidate`` dataclass equality is already ``False`` for two identical runs
    because ``nan != nan``; every candidate carries NaN depth fields. Asserting
    on ``__eq__`` would therefore fail even with the shadow off.
    """
    if isinstance(value, float):
        return "nan" if value != value else value
    if isinstance(value, dict):
        return {k: _nan_aware(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_nan_aware(v) for v in value]
    return value


def test_enabling_the_shadow_does_not_change_a_single_candidate(tmp_path):
    """The strongest inertness claim: the findings are bit-identical."""
    scan = _two_bump_scan()
    _g1, _a1, off = analyze_scan(
        scan,
        tmp_path / "off",
        label="s",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    _g2, anomaly, on = analyze_scan(
        scan,
        tmp_path / "on",
        label="s",
        config=AnalysisConfig(shadow_measurement="diagnostics"),
        write_outputs=False,
    )
    assert anomaly.shadow is not None and anomaly.shadow.enabled
    assert len(off) == len(on)
    for a, b in zip(off, on, strict=True):
        assert _nan_aware(asdict(a)) == _nan_aware(asdict(b)), (
            f"candidate {a.id} changed because the shadow was enabled"
        )


def test_enabling_the_shadow_does_not_change_analysis_json_or_the_csv(tmp_path):
    """`metadata.extra` and Candidate fields are both golden-hashed; neither moves."""
    scan = _two_bump_scan()
    artifacts = {}
    for mode in ("off", "diagnostics"):
        out = tmp_path / mode
        analyze_scan(
            scan,
            out,
            label="s",
            config=AnalysisConfig(shadow_measurement=mode),
        )
        artifacts[mode] = {
            "analysis": json.loads((out / "s_analysis.json").read_text(encoding="utf-8")),
            "csv": (out / "s_candidates.csv").read_text(encoding="utf-8"),
        }
    assert artifacts["off"]["analysis"] == artifacts["diagnostics"]["analysis"]
    assert artifacts["off"]["csv"] == artifacts["diagnostics"]["csv"]


def test_the_shadow_is_absent_from_the_machine_contract(tmp_path):
    """The shadow rides on the in-memory AnomalyMap; it never reaches a contract."""
    scan = _two_bump_scan()
    out = tmp_path / "on"
    analyze_scan(
        scan,
        out,
        label="s",
        config=AnalysisConfig(shadow_measurement="diagnostics"),
    )
    analysis = json.loads((out / "s_analysis.json").read_text(encoding="utf-8"))
    assert "shadow" not in json.dumps(analysis)
    assert "shadow" not in (out / "s_candidates.csv").read_text(encoding="utf-8")


def test_every_golden_hash_is_unchanged_with_the_shadow_on(tmp_path):
    """R2's mitigation, executed: a shadow run may not perturb what it measures."""
    from groundscan.validation.golden import GOLDEN_CASE_IDS, compute_golden_case

    baseline = json.loads((Path("tests/validation/golden.hashes")).read_text(encoding="utf-8"))
    config = AnalysisConfig(shadow_measurement="diagnostics")
    original = AnalysisConfig

    # compute_golden_case builds its own config; patch the default so every case
    # runs with the shadow enabled without editing the frozen harness.
    import groundscan.validation.golden as golden_mod

    def _patched(*args, **kwargs):
        return original(*args, **{**kwargs, "shadow_measurement": "diagnostics"})

    golden_mod.AnalysisConfig = _patched if hasattr(golden_mod, "AnalysisConfig") else None
    try:
        import groundscan.services.single_scan as single_scan_mod

        real_analyze = single_scan_mod.analyze_scan

        def _analyze_with_shadow(scan_data, out, **kwargs):
            kwargs.setdefault("config", config)
            return real_analyze(scan_data, out, **kwargs)

        single_scan_mod.analyze_scan = _analyze_with_shadow
        for case_id in GOLDEN_CASE_IDS:
            fresh = compute_golden_case(tmp_path / case_id, case_id)
            for artifact, digest in fresh.items():
                assert digest == baseline[artifact], (
                    f"{case_id}/{artifact} moved with the shadow enabled; the shadow is not inert"
                )
    finally:
        single_scan_mod.analyze_scan = real_analyze


# ---------------------------------------------------------------------------
# K2 -- d_res must not be invented
# ---------------------------------------------------------------------------


def test_the_default_promotion_rule_is_the_conservative_one():
    """Until d_res is calibrated the shadow reports "nest", never "promote"."""
    from groundscan.diagnostics.shadow import TOP_LEVEL_ROLES

    assert frozenset({ROLE_CONFLICT, ROLE_RESPONSE}) == TOP_LEVEL_ROLES
    for nested in (ROLE_DECOMPOSITION, ROLE_UNRESOLVED):
        assert not is_top_level(nested)


def test_duplicate_locations_are_visible_for_review(tmp_path):
    """K2's unconditional half: the *measurements* must expose the duplication."""
    _grid, anomaly, _candidates = analyze_scan(
        _two_bump_scan(),
        tmp_path / "dup",
        label="s",
        config=AnalysisConfig(shadow_measurement="diagnostics"),
        write_outputs=False,
    )
    records = anomaly.shadow.roles
    assert records
    assert all(r.role == ROLE_RESPONSE for r in records)
    assert all(not r.within_response_separations for r in records), (
        "well-separated responses must not be paired; the census would be noise"
    )


def test_summary_reports_the_numbers_the_activation_gate_is_decided_on():
    ledger = ShadowMeasurement(
        enabled=True,
        scale=measure_scale(np.zeros(100)),
        roles=measure_roles([_candidate(id=1, response_component_ids=[1])]),
    )
    summary = ledger.summary()
    for key in (
        "shape_class_change_rate",
        "top_level_count",
        "nested_count",
        "role_counts",
        "indeterminate_scale",
        "separation_median_m",
        "structural_alternative_unmodelled",
    ):
        assert key in summary
    assert summary["indeterminate_scale"] is True
    assert ledger.to_dict()["enabled"] is True

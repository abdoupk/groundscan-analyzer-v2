"""P3 pins: separation split + engine coverage (fast, deterministic)."""

from __future__ import annotations

import numpy as np

from groundscan import Candidate, ScanMetadata


def _cand(**overrides) -> Candidate:
    base = dict(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=3.0,
        height=3.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=9.0,
        positive_peak=9.0,
        negative_peak=-1.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.8,
        scan_count=2,
        scale_class="local",
    )
    base.update(overrides)
    return Candidate(**base)


# --- separation split: import parity ---------------------------------------


def test_separation_split_import_parity():
    from groundscan.site import separation as sep
    from groundscan.site import separation_diagnostics as diag
    from groundscan.site import separation_dipole as dip
    from groundscan.site import separation_fragments as frag
    from groundscan.site import separation_seeds as seeds

    assert sep._find_seeds is seeds._find_seeds
    assert sep._patch_for_candidate is seeds._patch_for_candidate
    assert sep._parent_is_bipolar is seeds._parent_is_bipolar
    assert sep._depth_layer_seed_pair is seeds._depth_layer_seed_pair
    assert sep._finite_peak is seeds._finite_peak
    assert sep._fragment_stats is frag._fragment_stats
    assert sep._fragment_full_descriptors is frag._fragment_full_descriptors
    assert sep._clone_with_diagnostics is diag._clone_with_diagnostics
    assert sep.diagnose_undersegmentation is diag.diagnose_undersegmentation
    assert sep.resolve_dipole_pairs is dip.resolve_dipole_pairs


# --- seeds ------------------------------------------------------------------


def test_find_seeds_flat_returns_empty():
    from groundscan.site.separation_seeds import _find_seeds

    field = np.zeros((12, 12))
    mask = np.ones((12, 12), dtype=bool)
    assert _find_seeds(field, mask, min_distance=3) == []


def test_find_seeds_two_bumps_finds_two():
    from groundscan.site.separation_seeds import _find_seeds

    field = np.zeros((20, 20))
    field[5, 5] = 10.0
    field[14, 14] = 9.0
    mask = np.ones_like(field, dtype=bool)
    seeds = _find_seeds(field, mask, min_distance=3)
    assert len(seeds) >= 2
    # Ranked strongest-first
    assert seeds[0][2] >= seeds[1][2]


def test_parent_is_bipolar_true_false():
    from groundscan.site.separation_seeds import _parent_is_bipolar

    assert _parent_is_bipolar(_cand(positive_peak=10.0, negative_peak=-9.0)) is True
    assert _parent_is_bipolar(_cand(positive_peak=10.0, negative_peak=-1.0)) is False
    assert _parent_is_bipolar(_cand(positive_peak=1.0, negative_peak=-1.0)) is False


def test_depth_layer_seed_pair_none_depth():
    from groundscan.site.separation_seeds import _depth_layer_seed_pair

    field = np.ones((10, 10))
    mask = np.ones((10, 10), dtype=bool)
    assert _depth_layer_seed_pair(field, mask, None) == []


def test_patch_for_candidate_square_mapping():
    from groundscan.site.separation_seeds import _patch_for_candidate

    c = _cand(x_center=5.0, y_center=5.0, width=4.0, height=4.0, major_extent=4.0, minor_extent=4.0)
    rs, cs = _patch_for_candidate(
        c, field_shape=(30, 40), x0=0.0, y0=0.0, site_width=10.0, site_height=10.0
    )
    assert 0 <= rs.start < rs.stop <= 30
    assert 0 <= cs.start < cs.stop <= 40


# --- fragments ---------------------------------------------------------------


def test_fragment_stats_empty():
    from groundscan.site.separation_fragments import _fragment_stats

    assert (
        _fragment_stats(
            np.zeros((4, 4), bool),
            np.arange(4.0),
            np.arange(4.0),
            np.array([], dtype=int),
            np.array([], dtype=int),
        )
        == {}
    )


def test_fragment_descriptors_recompute_from_cells():
    from groundscan.site.separation_fragments import _fragment_full_descriptors

    signed = np.zeros((10, 10))
    signed[4, 4] = 8.0
    signed[4, 5] = 7.0
    stats = {"aspect_ratio": 1.0, "major_extent": 2.0, "minor_extent": 2.0}
    out = _fragment_full_descriptors(
        mask=np.ones((10, 10), bool),
        frag_rr=np.array([4, 4]),
        frag_cc=np.array([4, 5]),
        local_x_axis=np.arange(10.0),
        local_y_axis=np.arange(10.0),
        field_shape=(10, 10),
        signed_patch=signed,
        stats=stats,
        total_cells=100,
        row_offset=0,
        col_offset=0,
    )
    assert out["anomaly_score"] == 8.0
    assert out["positive_peak"] == 8.0
    assert "shape_class" in out


# --- diagnostics + determinism -----------------------------------------------


def _site_fields(n=30):
    support = np.zeros((n, n))
    support[10:14, 10:14] = 0.9
    support[18:22, 18:22] = 0.85
    signed = np.zeros((n, n))
    signed[11, 11] = 9.0
    signed[19, 19] = 8.0
    x = np.linspace(0, 10, n)
    y = np.linspace(0, 10, n)
    return support, signed, x, y


def test_separate_is_deterministic_and_ids_monotonic():
    from groundscan.site.separation import separate_fused_candidates

    support, signed, x, y = _site_fields()
    parent = _cand(
        id=42,
        x_center=5.0,
        y_center=5.0,
        width=6.0,
        height=6.0,
        major_extent=6.0,
        minor_extent=6.0,
        evidence_score=0.9,
        scan_count=2,
        anomaly_score=12.0,
    )
    first, _ = separate_fused_candidates([parent], support, signed, x, y)
    # Fresh parent copy for second run (function mutates diagnostics in place)
    parent2 = _cand(
        id=42,
        x_center=5.0,
        y_center=5.0,
        width=6.0,
        height=6.0,
        major_extent=6.0,
        minor_extent=6.0,
        evidence_score=0.9,
        scan_count=2,
        anomaly_score=12.0,
    )
    second, _ = separate_fused_candidates([parent2], support, signed, x, y)
    assert [(c.x_center, c.y_center) for c in first] == [(c.x_center, c.y_center) for c in second]
    ids = [c.id for c in first]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_separate_single_weak_parent_unchanged_but_diagnosed():
    from groundscan.site.separation import separate_fused_candidates

    support = np.ones((12, 12)) * 0.9
    signed = np.ones((12, 12)) * 4.0
    x = np.linspace(0, 5, 12)
    y = np.linspace(0, 5, 12)
    parent = _cand(evidence_score=0.1, scan_count=1, anomaly_score=2.0)
    out, counts = separate_fused_candidates([parent], support, signed, x, y)
    assert counts[parent.id] == 1
    assert len(out) == 1


def test_resolve_dipole_pairs_flags_pair():
    from groundscan.site.separation_dipole import resolve_dipole_pairs

    a = _cand(
        id=1,
        polarity="positive",
        positive_peak=8.0,
        negative_peak=-1.0,
        separation_status="decomposed-consensus",
        separation_parent_id=9,
    )
    b = _cand(
        id=2,
        polarity="negative",
        positive_peak=1.0,
        negative_peak=-8.0,
        separation_status="decomposed-consensus",
        separation_parent_id=9,
    )
    out = resolve_dipole_pairs([a, b])
    assert all("dipole-pair" in (c.quality_flags or []) for c in out)


# --- evidence / classify ------------------------------------------------------


def test_evidence_scores_keys_and_range():
    from groundscan.core.evidence import HYPOTHESES, score_hypotheses

    scores = score_hypotheses(_cand())
    assert set(scores) == set(HYPOTHESES)
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scores.values())


def test_evidence_polarity_shifts_metal_vs_cavity():
    from groundscan.core.evidence import score_hypotheses

    pos = score_hypotheses(_cand(polarity="positive", positive_peak=9.0, negative_peak=-1.0))
    neg = score_hypotheses(_cand(polarity="negative", positive_peak=1.0, negative_peak=-9.0))
    assert pos["metallic-like"] > neg["metallic-like"]
    assert neg["cavity-like"] >= pos["cavity-like"]


def test_classify_from_evidence_returns_known_hypothesis():
    from groundscan.core.evidence import HYPOTHESES, classify_from_evidence

    hyp, scores, margin, second, method, _ = classify_from_evidence(_cand())
    assert hyp in HYPOTHESES
    assert second in HYPOTHESES
    assert margin >= 0.0
    assert isinstance(method, str)


# --- fusion / registration -----------------------------------------------------


def test_fuse_geometry_two_members():
    from groundscan.site.fusion import fuse_geometry

    out = fuse_geometry([_cand(width=2.0, height=2.0), _cand(width=4.0, height=4.0)])
    assert 2.0 <= out.width <= 4.0
    assert 2.0 <= out.height <= 4.0
    assert out.measurement_count == 2


def test_fuse_depth_two_members():
    from groundscan.site.fusion import fuse_depth

    out = fuse_depth([_cand(depth_mean=2.0), _cand(depth_mean=4.0)])
    assert 2.0 <= out.estimate <= 4.0
    assert out.measurement_count == 2


def test_registration_identical_grids_strong():
    from groundscan.site.registration import align_grids

    rng = np.random.default_rng(0)
    z = rng.normal(0, 1, size=(24, 24))
    z[10:14, 10:14] += 8.0
    res = align_grids(z, z.copy(), resolution=24)
    assert res.overlap_fraction >= 0.9


# --- dipole merge ---------------------------------------------------------------


def test_dipole_merge_single_keeps_candidate():
    from groundscan.diagnostics.dipole import merge_dipolar_response_components

    out = merge_dipolar_response_components([_cand()])
    assert len(out) == 1


def test_dipole_scorer_is_pure_and_stable():
    from groundscan.diagnostics.dipole import _dipole_pair_metrics

    a = _cand(
        id=1,
        x_center=4.0,
        y_center=5.0,
        polarity="positive",
        positive_peak=9.0,
        negative_peak=-1.0,
        separation_parent_id=7,
        major_extent=3.0,
        minor_extent=2.0,
    )
    b = _cand(
        id=2,
        x_center=6.0,
        y_center=5.0,
        polarity="negative",
        positive_peak=1.0,
        negative_peak=-8.5,
        separation_parent_id=7,
        major_extent=3.0,
        minor_extent=2.0,
    )
    notes_before = (a.notes, b.notes)
    first = _dipole_pair_metrics(a, b)
    second = _dipole_pair_metrics(a, b)
    assert first is not None and second is not None
    assert first == second  # deterministic, computed from inputs only
    assert (a.notes, b.notes) == notes_before  # no mutation as a side effect
    assert first.blocked_reason is None
    assert first.pair_score > 0.0


def test_dipole_blocked_assessment_carries_reason_without_mutation():
    from groundscan.diagnostics.dipole import _dipole_pair_metrics

    a = _cand(
        id=1, polarity="positive", positive_peak=9.0, depth_estimate=1.0, separation_parent_id=7
    )
    b = _cand(
        id=2, polarity="negative", negative_peak=-8.5, depth_estimate=9.0, separation_parent_id=7
    )
    out = _dipole_pair_metrics(a, b)
    assert out is not None
    assert out.pair_score == 0.0
    assert out.blocked_reason is not None and "depth inconsistency" in out.blocked_reason
    assert a.notes == "" and b.notes == ""


def test_deblend_returns_new_list_leaving_inputs_untouched():
    from groundscan.diagnostics.dipole import deblend_spatially_separated_multitarget_pairs

    a = _cand(
        id=1,
        x_center=4.0,
        y_center=5.0,
        polarity="positive",
        pattern_hypothesis="custom-pos",
        separation_parent_id=7,
        separation_status="decomposed-consensus",
        scan_count=2,
        metric_geometry_reliable=True,
        linearity_score=0.1,
        line_support_score=0.1,
        compactness=0.8,
    )
    b = _cand(
        id=2,
        x_center=7.0,
        y_center=5.0,
        polarity="negative",
        pattern_hypothesis="custom-neg",
        separation_parent_id=7,
        separation_status="decomposed-consensus",
        scan_count=2,
        metric_geometry_reliable=True,
        linearity_score=0.1,
        line_support_score=0.1,
        compactness=0.8,
    )
    out = deblend_spatially_separated_multitarget_pairs([a, b])
    assert len(out) == 2
    assert a.pattern_hypothesis == "custom-pos" and b.pattern_hypothesis == "custom-neg"
    assert a.notes == "" and b.notes == ""
    assert out[0].pattern_hypothesis == "metallic-like"
    assert out[1].pattern_hypothesis == "cavity-like"
    assert "spatial-multitarget-deblend" in out[0].quality_flags


# --- soil ------------------------------------------------------------------------


def test_soil_context_diagnostic_only():
    from groundscan.soil.context import build_soil_context

    ctx = build_soil_context(ScanMetadata())
    assert ctx["used_for_signal_correction"] is False
    assert ctx["used_for_depth_correction"] is False


def test_mineralization_risk_bounds():
    from groundscan.soil.context import mineralization_risk_from_pct

    assert mineralization_risk_from_pct(None) == 0.0
    r = mineralization_risk_from_pct(50.0)
    assert 0.0 <= r <= 1.0


def test_soil_twt_depth_math():
    from groundscan.soil.experimental import depth_from_twt_ns

    meta = ScanMetadata(dielectric_constant=9.0, relative_permeability=1.0)
    d = depth_from_twt_ns(np.array([10.0]), meta)
    assert float(d[0]) > 0.0


def test_soil_depth_diagnostic_no_twt():
    from groundscan.soil.experimental import soil_depth_diagnostic

    class _Scan:
        twt_ns = None

    out = soil_depth_diagnostic(_Scan(), ScanMetadata())
    assert out["available"] is False


# --- rover edge --------------------------------------------------------------------


def test_rover_can_read_rejects_random_csv(tmp_path):
    from groundscan.io.rover import RoverAdapter

    p = tmp_path / "random.csv"
    p.write_text("x,y,signal\n1,2,3\n", encoding="utf-8")
    assert RoverAdapter().can_read(p) is False


def test_generic_csv_headerless_xyz_flag(tmp_path):
    from groundscan.io.generic_csv import GenericCSVAdapter

    p = tmp_path / "plain.csv"
    p.write_text("1.0,2.0,3.0\n4.0,5.0,6.0\n7.0,8.0,9.0\n", encoding="utf-8")
    scan = GenericCSVAdapter().read(p)
    assert scan.metadata.extra.get("headerless_xyz") is True

"""Site verdicts: duplicates, repeatability, conflicts, pruning (fast)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from groundscan import Candidate, ScanData, ScanMetadata
from groundscan.core.grid import Grid2D
from groundscan.site.conflict_verdicts import (
    ConflictBuildContext,
    _contested_components,
    _merge_conflict_group,
    apply_conflict_verdict,
    build_conflict_candidates,
)
from groundscan.site.verdicts import (
    _duplicate_scan_groups,
    _majority,
    _prune_repeatability_fused_candidates,
    _retain_repeatable_fused_candidates,
    _scans_content_identical,
)


def _cand(**overrides) -> Candidate:
    base = dict(
        id=0,
        x_center=5.0,
        y_center=5.0,
        depth_mean=1.0,
        depth_std=0.1,
        n_points=8,
        area_cells=8,
        width=2.0,
        height=2.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=6.0,
        mean_signal=5.0,
        anomaly_score=9.0,
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        confidence=0.8,
    )
    base.update(overrides)
    return Candidate(**base)


def _scan_data(signal_value=10.0, n=16, seed=0) -> ScanData:
    rng = np.random.default_rng(seed)
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=rng.normal(signal_value, 1.0, size=n * n),
        metadata=ScanMetadata(),
    )


def _grid(n=16) -> Grid2D:
    x = np.arange(n, dtype=float)
    return Grid2D(
        x_centers=x,
        y_centers=x.copy(),
        signal=np.ones((n, n)),
        depth=np.ones((n, n)),
        counts=np.ones((n, n), dtype=int),
    )


def _obs(label, scan=None):
    scan = scan if scan is not None else _scan_data()
    return SimpleNamespace(
        label=label,
        scan=scan,
        grid=_grid(),
        direction_key="h",
        spacing_key="1.000m",
        pattern_key="parallel",
    )


def _ctx(obs_a, obs_b, support, sign, resolution=20):
    return ConflictBuildContext(
        observations=[obs_a, obs_b],
        alignments={},
        reference=obs_a,
        resolution=resolution,
        support=support,
        sign_consistency=sign,
        multires_persistence=None,
        min_size=2,
        distance_threshold=0.06,
    )


# --- _majority ---------------------------------------------------------------


def test_majority_empty_tie_and_win():
    assert _majority([]) == "unknown"
    assert _majority(["b", "a"]) == "b"  # first-seen tie-break
    assert _majority(["a", "b", "a"]) == "a"


# --- duplicate detection (F-02) ----------------------------------------------


def test_identical_and_permuted_scans_match():
    a = _scan_data()
    assert _scans_content_identical(a, a) is True
    b = _scan_data()
    order = np.random.default_rng(7).permutation(len(b.signal))
    c = ScanData(
        x=b.x[order], y=b.y[order], z=b.z[order], signal=b.signal[order], metadata=ScanMetadata()
    )
    assert _scans_content_identical(b, c) is True


def test_different_scans_do_not_match():
    assert _scans_content_identical(_scan_data(seed=1), _scan_data(seed=2)) is False
    short = _scan_data(n=8)
    assert _scans_content_identical(_scan_data(), short) is False


def test_duplicate_groups_keep_first_representative():
    dup = _scan_data()
    groups = _duplicate_scan_groups([
        _obs("a", dup),
        _obs("b", dup),
        _obs("c", _scan_data(seed=99)),
    ])
    assert groups == [["a", "b"], ["c"]]


# --- repeatability gates -----------------------------------------------------


def test_repeatability_retain_filters_and_renumbers():
    kept = _retain_repeatable_fused_candidates([
        _cand(id=5, scan_count=1),
        _cand(id=9, scan_count=3),
        _cand(id=7, scan_count=2),
    ])
    assert [c.scan_count for c in kept] == [3, 2]
    assert [c.id for c in kept] == [1, 2]


def test_prune_gate_keeps_strong_repeatables():
    strong = _cand(
        scan_count=3,
        detection_rate=1.0,
        cross_scan_agreement=0.9,
        registration_consistency=0.9,
        metric_geometry_reliable=False,
    )
    weak = _cand(
        scan_count=1,
        detection_rate=0.2,
        cross_scan_agreement=0.1,
        registration_consistency=0.2,
        metric_geometry_reliable=False,
    )
    kept = _prune_repeatability_fused_candidates([strong, weak])
    assert [c.evidence_score for c in kept] == [strong.evidence_score]
    assert kept[0].notes != ""
    assert kept[0].id == 1


def test_prune_metric_nms_suppresses_close_duplicates():
    first = _cand(
        x_center=5.0,
        evidence_score=0.8,
        scan_count=3,
        detection_rate=1.0,
        cross_scan_agreement=0.9,
        registration_consistency=0.9,
        metric_geometry_reliable=True,
    )
    second = _cand(
        x_center=6.0,
        evidence_score=0.5,
        scan_count=3,
        detection_rate=1.0,
        cross_scan_agreement=0.9,
        registration_consistency=0.9,
        metric_geometry_reliable=True,
    )
    kept = _prune_repeatability_fused_candidates([second, first])
    assert [c.evidence_score for c in kept] == [0.8]
    assert "metric NMS=on" in kept[0].notes


# --- contested components (F-03) ---------------------------------------------


def test_contested_components_find_disagreement_zone():
    support = np.zeros((10, 10))
    support[3:6, 3:6] = 0.8
    sign = np.ones((10, 10))
    sign[3:6, 3:6] = 0.2
    labels, n = _contested_components(support, sign, min_size=2)
    assert n == 1
    assert labels[4, 4] == 1
    assert labels[0, 0] == 0


def test_contested_components_empty_without_disagreement():
    labels, n = _contested_components(np.full((6, 6), 0.9), np.ones((6, 6)), min_size=1)
    assert n == 0
    assert labels.sum() == 0


def test_contested_min_size_filters_speckle():
    support = np.zeros((8, 8))
    support[2, 2] = 0.9
    sign = np.full((8, 8), 0.1)
    _, n = _contested_components(support, sign, min_size=4)
    assert n == 0


# --- polarity-conflict verdict -------------------------------------------------


def test_conflict_verdict_forces_unknown_and_caps():
    c = _cand(
        pattern_hypothesis="metallic-like",
        confidence=0.9,
        evidence_score=0.8,
        polarity_conflict=True,
        positive_peak=9.0,
        negative_peak=-8.0,
        hypothesis_scores={"unknown": 0.35, "metallic-like": 0.8},
        contributing_scans=["a", "b"],
    )
    out = apply_conflict_verdict([c])
    assert out[0].pattern_hypothesis == "unknown"
    assert out[0].evidence_score == 0.35
    assert out[0].classification_conflict_score == 1.0
    assert "polarity-conflict" in out[0].quality_flags


def test_verdict_splits_members_but_spares_dipoles():
    split = _cand(
        scan_count=2,
        polarity_consistency=0.2,
        pattern_hypothesis="cavity-like",
        hypothesis_scores={"unknown": 0.4},
        contributing_scans=["a", "b"],
    )
    dipole = _cand(
        scan_count=2,
        polarity_consistency=0.2,
        pattern_hypothesis="dipolar-response",
        response_family="dipolar-response",
    )
    # Pure contract (M9): the verdict returns verdict copies; inputs stay put.
    split_out, dipole_out = apply_conflict_verdict([split, dipole])
    assert split_out.pattern_hypothesis == "unknown"
    assert dipole_out.pattern_hypothesis == "dipolar-response"
    assert split.pattern_hypothesis == "cavity-like"

    clean = _cand(scan_count=3, polarity_consistency=0.9)
    (clean_out,) = apply_conflict_verdict([clean])
    assert clean_out.pattern_hypothesis == "metallic-like"
    assert clean_out.polarity_conflict is False


# --- conflict-group fusion -----------------------------------------------------


def test_merge_conflict_group_marks_and_blends():
    members = [
        _cand(
            id=1,
            x_center=4.0,
            y_center=5.0,
            anomaly_score=9.0,
            polarity="positive",
            positive_peak=9.0,
            negative_peak=-1.0,
            evidence_score=0.7,
            contributing_scans=["a"],
            scan_count=1,
        ),
        _cand(
            id=2,
            x_center=6.0,
            y_center=5.0,
            anomaly_score=-8.5,
            polarity="negative",
            positive_peak=1.0,
            negative_peak=-8.5,
            evidence_score=0.65,
            contributing_scans=["b"],
            scan_count=1,
        ),
    ]
    obs_a, obs_b = _obs("a"), _obs("b")
    fused = _merge_conflict_group(
        members,
        [(4.0, 5.0), (6.0, 5.0)],
        ["a", "b"],
        ctx=_ctx(obs_a, obs_b, np.zeros((20, 20)), np.ones((20, 20)), resolution=40),
    )
    assert fused.polarity_conflict is True
    assert fused.pattern_hypothesis == "unclassified"
    assert fused.polarity == "mixed"
    assert fused.multi_scan_status == "multi-scan"
    assert fused.cross_scan_agreement is None
    assert sorted(fused.contributing_scans) == ["a", "b"]
    assert 4.0 <= fused.x_center <= 6.0


def test_build_conflict_candidates_reunites_opposite_signs():
    obs_a, obs_b = _obs("a"), _obs("b")
    support = np.zeros((20, 20))
    support[4:12, 4:12] = 0.8
    sign = np.ones((20, 20))
    sign[4:12, 4:12] = 0.2
    ctx = _ctx(obs_a, obs_b, support, sign)
    dropped = [
        _cand(
            id=1,
            x_center=5.0,
            y_center=5.0,
            anomaly_score=9.0,
            polarity="positive",
            positive_peak=9.0,
            negative_peak=-1.0,
            evidence_score=0.7,
            contributing_scans=["a"],
            scan_count=1,
        ),
        _cand(
            id=2,
            x_center=6.0,
            y_center=5.0,
            anomaly_score=-8.5,
            polarity="negative",
            positive_peak=1.0,
            negative_peak=-8.5,
            evidence_score=0.65,
            contributing_scans=["b"],
            scan_count=1,
        ),
    ]
    out = build_conflict_candidates(dropped, ctx)
    assert len(out) == 1
    assert out[0].polarity_conflict is True
    assert out[0].polarity == "mixed"
    assert sorted(out[0].contributing_scans) == ["a", "b"]


def test_build_conflict_candidates_ignores_single_scan_groups():
    obs_a, obs_b = _obs("a"), _obs("b")
    support = np.zeros((20, 20))
    support[4:12, 4:12] = 0.8
    sign = np.ones((20, 20))
    sign[4:12, 4:12] = 0.2
    ctx = _ctx(obs_a, obs_b, support, sign)
    lone = _cand(
        id=1,
        x_center=5.0,
        y_center=5.0,
        anomaly_score=9.0,
        polarity="positive",
        contributing_scans=["a"],
        scan_count=1,
    )
    assert build_conflict_candidates([lone], ctx) == []
    assert build_conflict_candidates([], ctx) == []

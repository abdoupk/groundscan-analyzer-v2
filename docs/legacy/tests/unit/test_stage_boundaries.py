"""Stage-boundary migration regression (Phases 9-12, incremental).

M2: soil-model assembly lives in services.single_scan_stages as a pure
stage helper (same inputs/outputs as the inline orchestrator block).
M3: undersegmentation/overlap diagnostic attach is pure (input
unchanged; diagnostics carried by the returned copy).
"""

from __future__ import annotations

import dataclasses

import numpy as np


def _assert_unchanged(candidate, snapshot: dict) -> None:
    """NaN-aware equality: dataclass == is False whenever NaN fields exist."""
    live = dataclasses.asdict(candidate)
    assert set(live) == set(snapshot)
    for key, old in snapshot.items():
        new = live[key]
        if isinstance(old, float) and isinstance(new, float) and old != old and new != new:
            continue
        assert new == old, f"input mutated at {key}: {old!r} -> {new!r}"


def _scan(n: int = 16, seed: int = 3):
    from groundscan import ScanData, ScanMetadata

    rng = np.random.default_rng(seed)
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    signal[7:10, 7:10] += 12.0
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


def test_assemble_soil_model_keys_and_types():
    from groundscan.core.grid import reconstruct_grid
    from groundscan.services.single_scan_stages import assemble_soil_model

    scan = _scan()
    grid = reconstruct_grid(scan)
    model, twt_grid = assemble_soil_model(
        scan=scan,
        grid=grid,
        baseline_z=grid.signal,
        soil_aware_z=None,
        soil_weights=None,
        threshold=3.0,
        soil_mode="diagnostic",
        scales=(3, 5, 9, 15),
    )
    assert isinstance(model, dict)
    for key in (
        "soil_context",
        "confounder_context",
        "depth_diagnostic",
        "depth_comparison",
        "background_factor_sweep",
        "integrated",
    ):
        assert key in model, f"soil model missing {key}"
    assert twt_grid is None or hasattr(twt_grid, "depth")


def test_apply_candidate_enrichment_is_pure():
    from groundscan.models import Candidate
    from groundscan.services.single_scan_stages import apply_candidate_enrichment, build_enrichment

    scan = _scan()
    enrichment = build_enrichment(scan)
    cand = Candidate(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    before = dataclasses.asdict(cand)
    out = apply_candidate_enrichment([cand], scan, enrichment)
    _assert_unchanged(cand, before)
    assert len(out) == 1 and out[0] is not cand
    assert out[0].metric_geometry_reliable == enrichment.metric_geometry_reliable
    assert out[0].soil_context_completeness == enrichment.soil_completeness


def test_apply_zigzag_policy_records_and_applies():
    from groundscan.core.grid import reconstruct_grid
    from groundscan.services.single_scan_stages import apply_zigzag_policy

    scan = _scan()
    grid = reconstruct_grid(scan)
    out_grid, diag = apply_zigzag_policy(scan, grid, zigzag="off")
    assert "zigzag_correction" in scan.metadata.extra
    assert out_grid is grid  # off: grid untouched
    assert isinstance(diag.recommend_correction, bool)
    assert isinstance(diag.margin, float)
    _, _ = apply_zigzag_policy(scan, grid, zigzag="force")
    assert scan.metadata.extra["zigzag_correction"]["applied"] is True
    assert scan.metadata.extra["zigzag_correction"]["mode"] == "force"


def test_classify_candidate_is_pure():
    from groundscan.core.classify import classify_candidate
    from groundscan.models import Candidate

    cand = Candidate(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    before = dataclasses.asdict(cand)
    out = classify_candidate(cand)
    _assert_unchanged(cand, before)
    assert out is not cand
    assert out.pattern_hypothesis in (
        "metallic-like",
        "cavity-like",
        "tunnel-like",
        "geological-like",
        "irregular-anomaly",
        "boundary-effect-like",
        "linear-metal-compatible",
        "unknown",
    )
    assert out.classification_method == "evidence-model"


def test_apply_conflict_verdict_replaces_not_mutates():
    from groundscan.models import Candidate
    from groundscan.site.conflict_verdicts import apply_conflict_verdict

    cand = Candidate(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=9.0,
        mean_signal=5.0,
        anomaly_score=9.0,
        positive_peak=9.0,
        negative_peak=-8.0,
        signed_anomaly_mean=0.5,
        polarity="mixed",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.9,
        evidence_score=0.8,
        scan_count=2,
        scale_class="local",
        polarity_conflict=True,
        contributing_scans=["a", "b"],
        hypothesis_scores={"unknown": 0.35, "metallic-like": 0.8},
    )
    before = dataclasses.asdict(cand)
    out = apply_conflict_verdict([cand])
    _assert_unchanged(cand, before)
    assert out[0] is not cand
    assert out[0].pattern_hypothesis == "unknown"
    assert out[0].polarity_conflict is True
    assert "polarity-conflict" in (out[0].quality_flags or [])


def test_assess_candidate_quality_is_pure():
    from groundscan.gates.quality import assess_candidate_quality
    from groundscan.models import Candidate

    cand = Candidate(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    before = dataclasses.asdict(cand)
    out = assess_candidate_quality(cand)
    _assert_unchanged(cand, before)
    assert out is not cand
    assert out.review_status in (
        "artifact-concern",
        "high-uncertainty",
        "review-decomposition",
        "insufficient-evidence",
        "review",
        "supported-pattern",
    )
    assert 0.0 <= out.quality_score <= 1.0


def test_mark_rescued_candidates_is_pure():
    from groundscan.core.rescue import _mark_rescued_candidates
    from groundscan.models import Candidate

    def _cand(cid, **over):
        base = dict(
            id=cid,
            x_center=5.0,
            y_center=5.0,
            depth_mean=2.0,
            depth_std=0.2,
            n_points=12,
            area_cells=12,
            width=4.0,
            height=4.0,
            aspect_ratio=1.0,
            orientation_deg=0.0,
            peak_signal=10.0,
            mean_signal=8.0,
            anomaly_score=8.0,
            positive_peak=8.0,
            negative_peak=-1.0,
            signed_anomaly_mean=8.0,
            polarity="positive",
            shape_class="compact",
            pattern_hypothesis="geological-like",
            response_family="broad-response",
            confidence=0.8,
            evidence_score=0.9,
            scan_count=1,
            scale_class="local",
        )
        base.update(over)
        return Candidate(**base)

    eligible = [_cand(3), _cand(7)]
    before = [dataclasses.asdict(c) for c in eligible]
    out = _mark_rescued_candidates(eligible, start_id=10)
    for cand, snap in zip(eligible, before, strict=True):
        _assert_unchanged(cand, snap)
    assert [c.id for c in out] == [10, 11]
    for c in out:
        assert c.response_family == "broad-response"
        assert c.classification_method == "secondary-median-geology-rescue"
        assert c.screening_selection_reason == "secondary-geology-extraction-rescue"
        assert "secondary extraction rescue" in (c.notes or "")
        # Issue #23 contract: the rescue provenance marker survives the
        # quality re-assessment (same precedent as dipole-pair).
        assert "secondary-extraction-rescue" in (c.quality_flags or [])


def test_gate_passes_use_pure_gated_copy():
    # M11: pipeline gate passes must not mutate their inputs. gated_copy
    # parity with apply_operational_gate is pinned in
    # test_candidate_discipline.py; this pins the call-site contract.
    import inspect

    import groundscan.services.single_scan as single_scan_mod
    import groundscan.site.analyze_site as site_mod

    for mod in (single_scan_mod, site_mod):
        source = inspect.getsource(mod)
        assert "apply_operational_gate(" not in source, (
            f"{mod.__name__} still calls the mutating gate"
        )
        assert "gated_copy(" in source, f"{mod.__name__} does not use the pure gate"


def test_provenance_flags_survive_quality_reassessment():
    # Issue #23 contract: provenance markers (dipole-pair precedent) must
    # survive assess recomputation so they remain on the candidate; the rescue
    # flag is the same kind of marker.
    from groundscan.gates.quality import assess_candidate_quality
    from groundscan.models import Candidate

    cand = Candidate(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
        quality_flags=["secondary-extraction-rescue"],
    )
    out = assess_candidate_quality(cand)
    assert "secondary-extraction-rescue" in (out.quality_flags or [])


def test_attach_undersegmentation_is_pure():
    from groundscan.models import Candidate
    from groundscan.site.separation_diagnostics import _attach_undersegmentation_diagnostic

    base = dict(
        id=1,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    cand = Candidate(**base)
    before = dataclasses.asdict(cand)
    pos = np.zeros((6, 6))
    pos[1, 1] = 9.0
    pos[4, 4] = 5.0
    out = _attach_undersegmentation_diagnostic(
        cand,
        pos_field=pos,
        neg_field=np.zeros((6, 6)),
        local_mask=np.ones((6, 6), bool),
        min_distance=3,
    )
    _assert_unchanged(cand, before)
    assert out is not cand
    assert isinstance(out.undersegmentation_score, float)


def test_attach_overlap_is_pure():
    from groundscan.models import Candidate
    from groundscan.site.separation_diagnostics import _attach_unresolved_overlap_diagnostic

    base = dict(
        id=2,
        x_center=5.0,
        y_center=5.0,
        depth_mean=2.0,
        depth_std=0.2,
        n_points=12,
        area_cells=12,
        width=4.0,
        height=4.0,
        aspect_ratio=1.0,
        orientation_deg=0.0,
        peak_signal=10.0,
        mean_signal=8.0,
        anomaly_score=8.0,
        positive_peak=8.0,
        negative_peak=-1.0,
        signed_anomaly_mean=8.0,
        polarity="positive",
        shape_class="compact",
        pattern_hypothesis="metallic-like",
        response_family="isolated",
        confidence=0.8,
        evidence_score=0.9,
        scan_count=1,
        scale_class="local",
    )
    cand = Candidate(**base)
    before = dataclasses.asdict(cand)
    pos = np.zeros((6, 6))
    pos[1, 1] = 9.0
    pos[4, 4] = 5.0
    out = _attach_unresolved_overlap_diagnostic(
        cand,
        pos_field=pos,
        neg_field=np.zeros((6, 6)),
        local_mask=np.ones((6, 6), bool),
        min_distance=3,
    )
    _assert_unchanged(cand, before)
    assert out is not cand

"""Candidate mutation discipline pins (fast).

Decision (evaluated, kept): the pipeline enriches candidates in place and
each stage documents its own contract. A wholesale freeze to
``with_updates()`` was rejected — stages rely on object identity (the same
objects flow extract -> classify -> separate -> gate) and goldens pin the
outputs. ``with_updates()`` stays as the escape hatch for
isolated/testable transforms; these tests pin both sides so any future
change of discipline is deliberate, not silent.
"""

from __future__ import annotations

import numpy as np

from groundscan import Candidate, ScanMetadata
from groundscan.core.grid import Grid2D


def _cand(**overrides) -> Candidate:
    base = dict(
        id=1,
        x_center=8.0,
        y_center=8.0,
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
        anomaly_score=9.0,
        positive_peak=9.0,
        negative_peak=-1.0,
        signed_anomaly_mean=9.0,
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


def test_with_updates_is_copy_on_write():
    c = _cand()
    c2 = c.with_updates(pattern_hypothesis="cavity-like", evidence_score=0.1)
    assert c2.pattern_hypothesis == "cavity-like"
    assert c.pattern_hypothesis == "metallic-like"  # original untouched
    assert c.evidence_score == 0.8


def test_operational_gate_mutates_and_returns_same_object():
    from groundscan.gates.operational import apply_operational_gate

    c = _cand()
    out = apply_operational_gate(c, "field-ready")
    assert out is c
    assert c.operational_status != ""


def test_gated_copy_parity_and_purity():
    from groundscan.gates.operational import apply_operational_gate, gated_copy

    for status in ("field-ready", "usable-with-caution", "insufficient-quality"):
        c_mut = _cand(artifact_score=0.9)
        c_pure = _cand(artifact_score=0.9)
        mutated = apply_operational_gate(c_mut, status)
        copied = gated_copy(c_pure, status)
        assert mutated is c_mut
        assert copied is not c_pure
        assert c_pure.operational_status == "clear"  # input untouched
        assert copied.operational_status == mutated.operational_status
        assert copied.operational_flags == mutated.operational_flags
        assert copied.operational_constraints == mutated.operational_constraints
        assert copied.notes == mutated.notes
        assert copied.quality_flags == mutated.quality_flags


def test_screening_returns_copies_leaves_inputs_untouched():
    from groundscan.gates.screening import screen_candidates

    c = _cand(evidence_score=0.85, screening_score=0.9)
    before = c.screening_selection_reason
    out = screen_candidates([c])
    assert len(out) == 1
    assert out[0] is not c
    assert c.screening_selection_reason == before
    assert out[0].screening_selection_reason != ""


def test_agreement_mutates_same_objects():
    from groundscan.site.agreement import cross_scan_agreement
    from groundscan.site.registration import AlignmentResult

    n = 16
    x = np.arange(n, dtype=float)
    grid = Grid2D(
        x_centers=x,
        y_centers=x.copy(),
        signal=np.ones((n, n)),
        depth=np.ones((n, n)),
        counts=np.ones((n, n), dtype=int),
    )
    alignment = AlignmentResult(
        transform_name="translation",
        shift_dy=0,
        shift_dx=0,
        correlation=0.9,
        overlap_fraction=1.0,
        b_resampled=np.full((20, 20), 7.0),
        b_valid=np.ones((20, 20), dtype=bool),
    )
    c = _cand()
    out = cross_scan_agreement([c], grid, alignment)
    assert out[0] is c
    assert c.cross_scan_agreement is not None


def test_metadata_scan_constructs():
    assert ScanMetadata().extra == {} or isinstance(ScanMetadata().extra, dict)

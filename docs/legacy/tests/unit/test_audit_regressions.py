"""Audit-driven regression pins (fast).

Each test here reproduces a defect confirmed by independent audit verification
and fails on the pre-fix code. They exist because mutation testing showed the
suite did not constrain these paths: reversing the registration sort direction,
hard-coding solidity to 1.0, flipping the "neutral value" conventions, or
inflating the robust scale on a heavy tail all left the suite green.

Groups:
  * site determinism  -- fusion must not depend on input order; cluster ties
                         must resolve deterministically
  * robust scale      -- outliers must not inflate the detection threshold
  * field quality     -- a strong instrument artifact must degrade readiness
  * registration      -- a flat correlation surface must resolve to (0, 0)
  * bounded evidence  -- non-finite gate inputs must not read as strong
  * separation        -- a single-scan parent must not be split by default
"""

from __future__ import annotations

import math
import tempfile

import numpy as np
import pytest

from groundscan import Candidate, ScanData, ScanMetadata
from groundscan._util import robust_scale
from groundscan.core.grid import reconstruct_grid
from groundscan.diagnostics.quality_probe import detect_scan_quality_diagnostics
from groundscan.gates.field_quality import assess_field_quality
from groundscan.gates.geometry import summarize_geometry
from groundscan.gates.operational import assess_operational_gate
from groundscan.gates.quality import assess_candidate_quality
from groundscan.gates.thresholds import registration_evidence_score
from groundscan.site.registration import align_grids

NAN = float("nan")


# --------------------------------------------------------------------------
# site determinism
# --------------------------------------------------------------------------
def _site_scan(label: str, seed: int, shift: float = 0.0, n: int = 50):
    rng = np.random.default_rng(seed)
    x = np.repeat(np.arange(n, dtype=float), n) + shift
    y = np.tile(np.arange(n, dtype=float), n)
    signal = rng.normal(0.0, 1.0, n * n)
    cy = cx = n // 2
    signal[(y >= cy - 3) & (y <= cy + 3) & (x >= cx - 3) & (x <= cx + 3)] += 7.0
    return (
        label,
        ScanData(
            x=x,
            y=y,
            z=np.ones(n * n),
            signal=signal,
            metadata=ScanMetadata(field_length_m=float(n - 1), field_width_m=float(n - 1)),
        ),
    )


def _fused_signature(scans) -> tuple:
    from groundscan.api import analyze_site

    with tempfile.TemporaryDirectory(prefix="gs_order_") as tmp:
        result = analyze_site(scans, out_dir=tmp)
    return tuple(
        sorted(
            (
                round(float(c.x_center), 2),
                round(float(c.y_center), 2),
                round(float(c.evidence_score), 3),
                c.pattern_hypothesis,
            )
            for c in result.fused_candidates
        )
    )


def test_site_fusion_is_independent_of_input_order():
    """Permuting the input scan list must not change the fused result.

    The fusion path uses greedy clustering whose centroids are updated as items
    are appended, so a caller that supplies scans in filesystem order got a
    different candidate count, position and evidence score for the same data.
    """
    scans = [
        _site_scan("s1", 1, 0.0),
        _site_scan("s2", 2, 0.0),
        _site_scan("s3", 3, 0.0),
        _site_scan("s4", 4, 0.35),
    ]
    baseline = _fused_signature(scans)
    assert baseline, "expected at least one fused candidate"

    for order in ([1, 0, 2, 3], [3, 2, 1, 0], [2, 3, 0, 1], [0, 3, 1, 2]):
        permuted = [scans[i] for i in order]
        assert _fused_signature(permuted) == baseline, (
            f"fusion result changed when scans were supplied in order {order}"
        )


def test_greedy_cluster_assignment_breaks_ties_toward_the_first_cluster():
    """An exactly equidistant item must join the earlier cluster, not the later one.

    ``_cluster_items`` walks the existing clusters in index order and keeps the
    closest one, guarded by a strict ``d < best_d``. Strictness is what makes the
    assignment deterministic: with ``d <= best_d`` a later cluster at the *same*
    distance would overwrite the earlier one, so which cluster wins would depend
    on how many clusters happened to exist -- i.e. on the order unrelated items
    arrived in. The synthetic site scans never produce equidistant centroids
    (floats essentially never tie), which is why this needed a purpose-built
    fixture rather than a site-level one.
    """
    from groundscan.site.consensus import _cluster_items

    def item(u: float, v: float) -> dict:
        return {"u": u, "v": v, "scale": 0.01}

    # Two singleton clusters 1.0 apart, then an item exactly between them.
    clusters = _cluster_items(
        [item(0.0, 0.0), item(1.0, 0.0), item(0.5, 0.0)], distance_threshold=0.5
    )

    assert [[(q["u"], q["v"]) for q in c] for c in clusters] == [
        [(0.0, 0.0), (0.5, 0.0)],
        [(1.0, 0.0)],
    ], (
        "the equidistant item joined the later cluster; the tie-break is not "
        "resolving toward the first cluster and assignment depends on the "
        "accidental cluster count"
    )


# --------------------------------------------------------------------------
# robust scale
# --------------------------------------------------------------------------
def test_robust_scale_does_not_let_outliers_exceed_suppress_genuine_anomalies():
    """A mostly-quiet residual plus one extreme spike must keep real signal.

    ``robust_scale`` fell through to the standard deviation when MAD and IQR
    were both zero, so a single acquisition spike pushed the 3-sigma detection
    threshold above every genuine anomaly and the scan reported nothing.
    """
    rng = np.random.default_rng(7)
    residual = rng.normal(0.0, 0.1, 4000)
    genuine = [500, 1500, 2500]
    for index in genuine:
        residual[index] = 3.0

    clean_scale = robust_scale(residual)
    spiked = np.concatenate([residual, [1e5]])
    spiked_scale = robust_scale(spiked)

    assert spiked_scale < 100 * clean_scale, (
        f"a single outlier inflated the robust scale from {clean_scale:.4g} to {spiked_scale:.4g}"
    )

    threshold = 3.0 * spiked_scale
    found = np.where(np.abs(residual) > threshold)[0]
    missing = [i for i in genuine if i not in found]
    assert not missing, (
        f"genuine anomalies at {missing} fell below the inflated threshold "
        f"{threshold:.4g} and would be silently dropped"
    )


def test_robust_scale_is_not_inflated_by_a_heavy_tail():
    """The spread estimate must not inherit the raw tail's magnitude.

    A broadly quiet channel with a small fraction of extreme cells is the shape
    this estimator must stay robust on. This used to be pinned as a property of
    a 5%-of-std *floor*; the floor is gone (it was provably a no-op, since its
    winsorized input is bounded by Popoviciu at 5*scale), so the property is now
    pinned where it actually lives: rungs 1 and 2 of the MAD -> IQR -> std ladder
    are high-breakdown and never take the tail's value. Pin that the tail is
    treated as outliers rather than as the definition of "normal".
    """
    rng = np.random.default_rng(3)
    values = np.concatenate([rng.normal(0.0, 0.3, 900), np.full(100, 1.0e4)])
    scale = robust_scale(values)

    # The quiet bulk is ~N(0, 0.3), so a robust estimate sits near 0.33. The raw
    # std of this sample is ~3000, so an estimator that fell through to it (or
    # to a floor derived from it) would land far above 5.0 and the 1e4 cells
    # would fall below the 3-sigma threshold, i.e. be called normal.
    assert scale < 5.0, (
        f"a 1% tail of 1e4 inflated the robust scale to {scale:.4g}; the extreme "
        f"cells are being absorbed into the definition of normal"
    )

    # And the tail must actually be detectable as an outlier.
    threshold = 3.0 * scale
    tail = np.where(np.abs(values) > threshold)[0]
    assert len(tail) >= 90, (
        f"only {len(tail)}/100 tail cells exceeded the 3-sigma threshold {threshold:.4g}"
    )


def test_registration_recovers_a_negative_vertical_shift():
    """The shift search must cover negative displacements, not just positive.

    Restricting the search to ``dy >= 0`` silently fails to realign any scan
    that sits above its reference, which is exactly the half of the offset
    space the search exists to resolve.
    """
    size = 40
    rng = np.random.default_rng(11)
    reference = rng.normal(0.0, 1.0, (size, size))
    shifted = np.roll(reference, 4, axis=0)  # content moved +4 rows

    result = align_grids(reference, shifted, resolution=size, max_shift=6)
    assert result.shift_dy == -4, (
        f"a +4 row displacement was reported as dy={result.shift_dy} "
        f"(expected -4); the search is not covering negative shifts"
    )


# --------------------------------------------------------------------------
# field quality
# --------------------------------------------------------------------------
def test_strong_instrument_artifact_degrades_readiness():
    """A scan with a detected instrument artifact must not stay field-ready.

    ``strong-instrument-artifact-concern`` was raised but omitted from the
    ``caution_only`` set, and its readiness-score contribution is only 0.005, so
    a scan the probe flagged at 0.90 still reported ``field-ready``.
    """
    n = 60
    x = np.repeat(np.arange(n, dtype=float), n)
    y = np.tile(np.arange(n, dtype=float), n)
    signal = np.random.default_rng(1).normal(0.0, 1.0, n * n)
    cy = cx = n // 2
    signal[(y >= cy - 4) & (y <= cy + 4) & (x >= cx - 4) & (x <= cx + 4)] += 8.0
    depth = np.full(n * n, 1.5)
    depth[0] = 500.0  # isolated boundary excursion -> instrument artifact
    scan = ScanData(
        x=x,
        y=y,
        z=depth,
        signal=signal,
        metadata=ScanMetadata(field_length_m=59.0, field_width_m=59.0),
    )

    grid = reconstruct_grid(scan)
    diagnostics = detect_scan_quality_diagnostics(grid)
    assert diagnostics["instrument_artifact_score"] >= 0.80, (
        "precondition: the probe should flag this scan as artifact-prone"
    )

    assessment = assess_field_quality(
        scan, grid, summarize_geometry(scan, grid), scan_diagnostics=diagnostics
    )
    assert "strong-instrument-artifact-concern" in assessment.flags
    assert assessment.status != "field-ready", (
        f"a scan with a strong instrument artifact reported {assessment.status!r}"
    )
    assert assessment.field_ready is False


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------
def test_flat_correlation_surface_resolves_to_zero_shift():
    """A tie across all shifts must resolve to (0, 0), not the first candidate.

    The shift search iterated dy/dx from -6 and relied on sort stability, so a
    flat (zero-correlation) surface selected (-6, -6) and displaced the scan by
    twelve cells in both axes.
    """
    size = 40
    flat = np.zeros((size, size))
    result = align_grids(flat, flat.copy(), resolution=size, max_shift=6)

    assert (result.shift_dy, result.shift_dx) == (0, 0), (
        f"flat surface resolved to shift ({result.shift_dy}, {result.shift_dx})"
    )


# --------------------------------------------------------------------------
# bounded evidence
# --------------------------------------------------------------------------
def _candidate(**overrides) -> Candidate:
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


#: Every input healthy apart from ``evidence_score``, so a test can vary only
#: that one field and be sure the review label moved because of it.
_STRONG_EVIDENCE = dict(
    artifact_score=0.0,
    boundary_contact_ratio=0.0,
    geometry_quality=0.9,
    position_stability=0.95,
    multiscale_persistence=0.9,
    registration_consistency=0.95,
    multiscan_signal_consistency=0.9,
    depth_stability_score=0.9,
    separation_quality=0.9,
    scan_count=3,
    multi_scan_status="multi-scan",
    effective_scan_count=3,
    evidence_uncertainty=0.0,
    multi_scan_evidence_score=0.9,
    detection_rate=1.0,
    mineralization_risk=0.0,
    metric_geometry_reliable=True,
)


def test_operational_gate_does_not_clear_on_all_non_finite_evidence():
    """Every gate input unknown must not read as "clear".

    ``np.clip(nan, 0, 1)`` returns NaN, and every ``nan < threshold`` comparison
    is False, so a candidate with no measured evidence skipped all branches and
    was reported as the strongest possible operational status.
    """
    candidate = _candidate(
        multi_scan_status="multi-scan",
        registration_consistency=NAN,
        position_stability=NAN,
        depth_stability_score=NAN,
        boundary_contact_ratio=NAN,
        artifact_score=NAN,
        geometry_quality=NAN,
        evidence_uncertainty=NAN,
        spacing_persistence=NAN,
        detection_rate=NAN,
        depth_valid_fraction=NAN,
        depth_estimate=NAN,
    )
    assessment = assess_operational_gate(candidate, "field-ready")
    assert assessment.status != "clear", f"all-unknown candidate reported {assessment.status!r}"
    assert assessment.flags != ("operational-gate-clear",)


def test_registration_evidence_score_does_not_treat_unknown_as_perfect():
    """Non-finite registration inputs must not score 1.0.

    ``min(1.0, nan)`` returns ``1.0`` in Python, so a fully unknown registration
    scored a perfect 1.0 -- identical to a flawless alignment.
    """
    unknown = registration_evidence_score(correlation=NAN, overlap=NAN, margin=NAN, multiscale=NAN)
    perfect = registration_evidence_score(correlation=1.0, overlap=1.0, margin=1.0, multiscale=1.0)
    assert unknown != perfect, (
        f"unknown registration scored {unknown}, identical to a perfect {perfect}"
    )


def test_candidate_quality_does_not_promote_unknown_evidence():
    """A NaN evidence score must not yield the strongest review label.

    NaN propagated through ``support`` into ``quality`` and ``screening``, and
    because ``nan < 0.30`` is False the gate skipped the insufficient-evidence
    branch and fell through to ``supported-pattern``.
    """
    assessed = assess_candidate_quality(_candidate(evidence_score=NAN, **_STRONG_EVIDENCE))

    assert assessed.review_status != "supported-pattern", (
        f"unknown evidence produced the strongest label {assessed.review_status!r}"
    )
    for name in ("quality_score", "screening_score", "false_positive_risk"):
        value = getattr(assessed, name)
        assert not math.isnan(value), f"{name} propagated NaN ({value})"

    # The resolution must happen at the *input*, through the declared non-finite
    # policy, rather than being caught downstream by the K11 `_finite_score`
    # backstop. Both routes yield a finite, correctly-penalised score, so the
    # assertions above alone cannot tell them apart -- but only the input guard
    # resolves the value; if NaN reaches the formula the backstop fires and says
    # so. This is the assertion that pins the guard rather than the backstop.
    non_finite = [f for f in (assessed.quality_flags or ()) if f.endswith("-non-finite")]
    assert not non_finite, (
        "evidence NaN reached the quality formula and was caught by the output "
        f"backstop instead of resolved at the input: {non_finite}"
    )
    # Resolved to the declared adverse extreme, which is what the policy for a
    # support field means by "worst".
    finite_equivalent = assess_candidate_quality(_candidate(evidence_score=0.0, **_STRONG_EVIDENCE))
    assert assessed.quality_score == pytest.approx(finite_equivalent.quality_score), (
        f"NaN evidence scored {assessed.quality_score}, not the policy's worst-case "
        f"{finite_equivalent.quality_score}"
    )


def test_candidate_quality_reports_insufficient_evidence():
    """The insufficient-evidence branch must actually be reachable.

    The band is the gate that keeps weak candidates out of the review queue;
    with every other input healthy, a low evidence score alone must trip it.
    """
    weak = dict(_STRONG_EVIDENCE)
    weak["evidence_score"] = 0.05
    assessed = assess_candidate_quality(_candidate(**weak))

    # The band trips on `quality < 0.40 or evidence < 0.30`; with the other
    # channels healthy it is the evidence term that fires, which is exactly the
    # branch this pins.
    assert assessed.review_status == "insufficient-evidence", (
        f"low evidence reported {assessed.review_status!r}"
    )
    assert weak["evidence_score"] < 0.30
    assert assessed.screening_score < 0.45, (
        f"a weak-evidence candidate still screened highly: {assessed.screening_score}"
    )


def test_operational_gate_blocks_on_strong_artifact_evidence():
    """A high artifact score must block, not merely warn.

    The block branch sits above the caution branch; a candidate dominated by
    acquisition-artifact evidence must not remain usable for field
    interpretation.
    """
    candidate = _candidate(
        artifact_score=0.95,
        boundary_contact_ratio=0.0,
        geometry_quality=0.9,
        depth_stability_score=0.9,
        metric_geometry_reliable=True,
    )
    assessment = assess_operational_gate(candidate, "field-ready")

    assert assessment.status == "blocked", f"artifact_score=0.95 produced {assessment.status!r}"
    assert "operational-artifact-block" in assessment.flags


def test_separation_does_not_split_a_single_scan_parent_by_default():
    """One scan cannot corroborate a split; the default must refuse to try.

    Site mode depends on this. ``analyze_site`` calls ``separate_fused_candidates``
    with the default ``allow_single_scan=False`` and relies on a single-scan
    parent coming back whole, so that the repeatability gate downstream sees one
    un-split candidate rather than several single-scan fragments it would
    discard. The opt-in exists for the single-scan pipeline, which has no
    cross-scan evidence at all and therefore needs the opposite behaviour.

    Pinned at the function boundary rather than through ``analyze_site`` because
    the site path cannot observe the difference: it caps single-scan fused
    evidence at 0.45, below ``SeparationConfig.parent_evidence_min`` (0.55), so a
    site-mode single-scan parent is rejected before this gate is consulted.
    """
    from groundscan.site.separation import separate_fused_candidates

    def parent(**kwargs):
        base = dict(
            id=1,
            x_center=20.0,
            y_center=20.0,
            depth_mean=2.0,
            depth_std=0.2,
            n_points=12,
            area_cells=12,
            width=9.0,
            height=7.0,
            aspect_ratio=1.0,
            orientation_deg=0.0,
            peak_signal=10.0,
            mean_signal=8.0,
            anomaly_score=11.49,
            positive_peak=11.49,
            negative_peak=-9.2,
            signed_anomaly_mean=1.0,
            polarity="positive",
            shape_class="compact",
            pattern_hypothesis="dipolar-response",
            response_family="dipolar-response",
            confidence=0.8,
            evidence_score=0.90,
            scale_class="local",
        )
        base.update(kwargs)
        return Candidate(**base)

    n = 41
    axis = np.arange(n, dtype=float)
    # A clearly bipolar two-lobe support field centred on the parent, so the
    # split is available if the policy allows it.
    support = np.zeros((n, n))
    support[17:24, 14:20] = 1.0
    support[17:24, 21:27] = 1.0
    signed = np.zeros((n, n))
    signed[17:24, 14:20] = 8.0
    signed[17:24, 21:27] = -8.0

    kwargs = {}
    default_out, _ = separate_fused_candidates(
        [parent(scan_count=1)], support.copy(), signed.copy(), axis, axis, **kwargs
    )
    assert len(default_out) == 1, (
        f"a single-scan parent was split into {len(default_out)} fragments by "
        f"default; site mode relies on it coming back whole"
    )
    assert default_out[0].separation_status == "none"

    # And the opt-in still works, so this pins the policy rather than a bug: the
    # single-scan pipeline is entitled to the opposite behaviour.
    opted_in, _ = separate_fused_candidates(
        [parent(scan_count=1)],
        support.copy(),
        signed.copy(),
        axis,
        axis,
        allow_single_scan=True,
        **kwargs,
    )
    assert len(opted_in) > 1, (
        "allow_single_scan=True did not split a splittable single-scan parent; "
        "the opt-in the single-scan pipeline depends on is broken"
    )


# --------------------------------------------------------------------------
# shape
# --------------------------------------------------------------------------
def test_solidity_is_a_real_shape_descriptor():
    """Solidity must fall for a concave footprint and hold for a convex one.

    Solidity is the occupied-cell-area-over-hull-area ratio. Hard-coding it to
    1.0 (or returning 1.0 whenever the hull degenerates) removes the only signal
    that distinguishes a compact blob from a crescent or an L.

    The values below are **derived from the geometry, not from the current
    output** (S02). A filled ``n x n`` block is convex, so its cells *are* its
    convex hull and the ratio is exactly 1 at every pitch. The L is a 6x6 block
    with a 3x3 quadrant removed: 27 cells, and a hull that is the 6x6 square less
    the right triangle the missing corner cuts off, i.e. 36 - 9/2 = 31.5, so
    27/31.5 = 6/7. (It is the 2x blow-up of the 3-cell L, and a blown-up
    lattice pattern has the same ratio -- the same fact K4 relies on.)
    Before S02 the estimator divided a *cell count* by a hull area in coordinate
    units, so it was only strictly below 1.0 once the hull exceeded the cell
    count -- a dimensional defect, documented in the same file history and
    closed in `groundscan.core.shape._convex_hull_solidity`. The coordinates are
    still scaled by 2 here, so a pitch-dependent answer would fail: the ratio is
    dimensionless.
    """
    from groundscan.core.shape import _convex_hull_solidity

    scale = 2.0
    xs, ys = np.meshgrid(np.arange(4, dtype=float) * scale, np.arange(4, dtype=float) * scale)
    solid = _convex_hull_solidity(xs.ravel(), ys.ravel(), scale, scale)

    # L-shape: the missing quadrant is outside the hull.
    cells = [(i, j) for i in range(6) for j in range(6) if not (i >= 3 and j >= 3)]
    lx = np.array([c[0] for c in cells], dtype=float) * scale
    ly = np.array([c[1] for c in cells], dtype=float) * scale
    concave = _convex_hull_solidity(lx, ly, scale, scale)

    assert solid == pytest.approx(1.0, abs=1e-12), "a convex block is its own hull"
    assert concave == pytest.approx(27.0 / 31.5, abs=1e-12), "27 cells in a 31.5-cell hull"
    assert concave < solid
    assert 0.0 <= concave <= 1.0

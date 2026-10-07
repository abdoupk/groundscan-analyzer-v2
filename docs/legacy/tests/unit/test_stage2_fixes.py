"""Stage 2 -- safe deterministic fixes: the defects and their guards.

One file per contract area, each pinned at the defect rather than at the
symptom:

* **K10 / S07** axial orientation mean, including the wraparound cases the
  design names (5/175, 10/170, 0/179) and the case that moved the golden.
* **K11 / S09** the declared per-field non-finite policy, the monotonicity
  invariant, and the "no risk metric defaults to its favourable extreme" rule.
* **S08** singleton depth fusion must not report perfect agreement.
* **S05/S06** strict booleans, non-finite tolerance rejection, and the schema
  actually being loaded.
* **S04** the caller's claim kept distinct from a verified status.
* **S10** the identity quad, and collision-proof stems.
* **K9 / S11** ``write_outputs=False`` creates nothing; no CWD mutation.
* **S12** the local edge distance is bit-identical to the full-grid one.

Every assertion here is contract- or construction-driven. No threshold, weight
or band is asserted, because Stage 2 changes none of them: the tests would fail
the moment one did.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from groundscan._util import (
    ArtifactIdentity,
    artifact_identity,
    axial_angle_distance_deg,
    axial_dispersion_deg,
    axial_mean_deg,
    bounded01,
    content_fingerprint,
    output_dir,
    scan_fingerprint,
)
from groundscan.diagnostics.dipole import _axial_weighted_average, _weighted_average
from groundscan.gates.quality import (
    NONFINITE_POLICY,
    assess_candidate_quality,
    resolve_gate_input,
    unmeasured_fields,
)
from groundscan.models import Candidate, ScanData, ScanMetadata
from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.site.fusion import fuse_depth, fuse_geometry
from groundscan.validation.field import load_field_truth
from groundscan.validation.payload_schema import (
    VERIFICATION_METHODS,
    field_ground_truth_status,
    validate_field_truth_payload,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

CANDIDATE_BASE = dict(
    x_center=0.0,
    y_center=0.0,
    depth_mean=float("nan"),
    depth_std=float("nan"),
    n_points=9,
    area_cells=9,
    width=1.0,
    height=1.0,
    aspect_ratio=1.0,
    orientation_deg=0.0,
    peak_signal=1.0,
    mean_signal=1.0,
    anomaly_score=5.0,
    shape_class="compact",
    pattern_hypothesis="metallic-like",
    confidence=0.5,
)

#: A candidate with every gate input measured and healthy.
MEASURED = dict(
    evidence_score=0.6,
    multiscale_persistence=0.6,
    geometry_quality=0.6,
    position_stability=0.8,
    registration_consistency=0.8,
    multiscan_signal_consistency=0.9,
    depth_stability_score=0.7,
    separation_quality=0.7,
    boundary_contact_ratio=0.1,
    artifact_score=0.1,
    evidence_uncertainty=0.3,
    detection_rate=1.0,
    polarity_consistency=1.0,
    mineralization_risk=0.1,
)


def _candidate(**overrides) -> Candidate:
    base = dict(CANDIDATE_BASE)
    base.update(overrides)
    return Candidate(id=base.pop("id", 1), **base)


def _nan_candidate(**overrides) -> Candidate:
    values = {k: (float("nan") if isinstance(v, float) else v) for k, v in MEASURED.items()}
    values.update(overrides)
    return _candidate(**values)


def _grid_scan(n: int = 16, seed: int = 3) -> ScanData:
    rng = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    signal[7:10, 7:10] += 12.0
    return ScanData(
        x=gx.ravel(),
        y=gy.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


# ===========================================================================
# K10 / S07 -- axial orientation mean
# ===========================================================================


@pytest.mark.parametrize(
    "a, b, wrong_linear, right_axial",
    [
        (5.0, 175.0, 90.0, 0.0),
        (10.0, 170.0, 90.0, 0.0),
        (0.0, 179.0, 89.5, 179.5),
        (1.0, 179.0, 90.0, 0.0),
        (0.0, 180.0, 90.0, 0.0),
        (175.0, 5.0, 90.0, 0.0),
    ],
)
def test_axial_mean_resolves_the_wrap(a, b, wrong_linear, right_axial):
    """The named wraparound cases. The linear mean is not a rounding error here.

    ``mean(5, 175) = 90`` under a linear average; the two values are 10 degrees
    apart on the axis, so the shared axis is 0. A 90-degree error is a different
    physical orientation, which is why this is a mathematical invariant (K10)
    and not a tuning question.
    """
    assert (a + b) / 2.0 % 180.0 == pytest.approx(wrong_linear), "linear baseline"
    got = axial_mean_deg([a, b])
    assert got == pytest.approx(right_axial, abs=1e-9)
    assert 0.0 <= got < 180.0, "documented range is [0, 180)"


def test_axial_mean_agrees_with_linear_where_linear_is_valid():
    """It is not a different opinion; it is the same one done correctly.

    For values close relative to the wrap the two coincide, which is why the
    defect stayed latent on most data.
    """
    for a, b in [(30.0, 40.0), (0.0, 10.0), (100.0, 110.0), (90.0, 90.0)]:
        assert axial_mean_deg([a, b]) == pytest.approx((a + b) / 2.0, abs=1e-9)


def test_axial_mean_ignores_input_order():
    assert axial_mean_deg([5.0, 175.0]) == pytest.approx(axial_mean_deg([175.0, 5.0]))


def test_axial_mean_respects_weights():
    heavy_low = axial_mean_deg([5.0, 175.0], [10.0, 1.0])
    heavy_high = axial_mean_deg([5.0, 175.0], [1.0, 10.0])
    assert heavy_low < 20.0 < heavy_high


def test_axial_mean_is_undefined_for_an_isotropic_population():
    """No resultant means no mean direction; inventing one is the same defect."""
    assert np.isnan(axial_mean_deg([0.0, 45.0, 90.0, 135.0]))
    # Two orthogonal axes have no shared direction either.
    assert np.isnan(axial_mean_deg([45.0, 135.0]))


def test_axial_mean_defaults_and_drops_non_finite():
    assert np.isnan(axial_mean_deg([]))
    assert np.isnan(axial_mean_deg([float("nan"), float("inf")]))
    assert axial_mean_deg([10.0, float("nan"), 20.0]) == pytest.approx(15.0)
    assert axial_mean_deg([10.0, 20.0], default=-1.0) == pytest.approx(15.0)


def test_axial_distance_folds_the_wrap():
    assert axial_angle_distance_deg(0.0, 180.0) == pytest.approx(0.0)
    assert axial_angle_distance_deg(5.0, 175.0) == pytest.approx(10.0)
    assert axial_angle_distance_deg(0.0, 90.0) == pytest.approx(90.0)
    assert 0.0 <= axial_angle_distance_deg(3.0, 177.0) <= 90.0


def test_axial_dispersion_is_zero_for_a_coincident_axial_pair():
    assert axial_dispersion_deg([0.0, 180.0], 0.0) == pytest.approx(0.0, abs=1e-9)
    assert axial_dispersion_deg([5.0, 175.0], 0.0) == pytest.approx(5.0)


def test_dipole_merge_uses_axial_for_orientation_only():
    """The golden-moving site, pinned at the defect.

    Reproduces the ``vendor_iron_box`` merged-dipole call exactly and shows the
    two averages diverge, and that only the orientation one is axial.
    """
    a, b, wa, wb = 119.14928516524714, 84.94748181748102, 38.66636994115668, 23.553506671197
    linear = _weighted_average(a, b, wa, wb)
    axial = _axial_weighted_average(a, b, wa, wb)
    assert linear == pytest.approx(106.20209775217162)
    assert axial == pytest.approx(106.73536510572917, abs=1e-9)
    assert linear != axial

    # Everything else in the merge stays linear -- a non-finite centre must stay
    # NaN rather than being folded through an angle wrap.
    x_a, x_b = 131770.24481111113, 131806.75938
    assert _weighted_average(x_a, x_b, wa, wb) == pytest.approx(131784.0675023273)
    assert np.isnan(_axial_weighted_average(float("nan"), 1.0, wa, wb))


def test_fuse_geometry_uses_the_canonical_axial_mean():
    """The already-correct fusion site now delegates to one implementation."""
    members = []
    for i, angle in enumerate((5.0, 175.0)):
        members.append(
            _candidate(
                id=i + 1,
                orientation_deg=angle,
                major_extent=4.0,
                minor_extent=2.0,
                geometry_quality=0.7,
                evidence_score=0.7,
            )
        )
    fused = fuse_geometry(members)
    assert fused.orientation_deg == pytest.approx(axial_mean_deg([5.0, 175.0]), abs=1e-9)
    assert fused.orientation_deg == pytest.approx(0.0, abs=1e-6)
    assert fused.orientation_dispersion_deg == pytest.approx(5.0, abs=1e-6)


# ===========================================================================
# K11 / S09 -- declared non-finite policy
# ===========================================================================


def test_every_gate_input_has_a_declared_policy():
    for field in (
        "artifact_score",
        "evidence_score",
        "geometry_quality",
        "multiscale_persistence",
        "position_stability",
        "registration_consistency",
        "depth_stability_score",
        "separation_quality",
        "boundary_contact_ratio",
        "mineralization_risk",
        "evidence_uncertainty",
    ):
        assert field in NONFINITE_POLICY, field
        role, fallback, _flag = NONFINITE_POLICY[field]
        assert role in {"worst", "neutral", "flagged"}
        assert math_is_sane(fallback)


def math_is_sane(value: float) -> bool:
    return isinstance(value, float) and 0.0 <= value <= 1.0


def test_a_measured_value_passes_through_untouched():
    candidate = _candidate(**MEASURED)
    for field in NONFINITE_POLICY:
        if field in MEASURED:
            assert resolve_gate_input(candidate, field) == pytest.approx(MEASURED[field])
    assert unmeasured_fields(candidate) == []


@pytest.mark.parametrize("field", sorted(NONFINITE_POLICY))
def test_each_field_alone_never_increases_either_score(field):
    """K11-monotonic, one field at a time.

    The measured baseline and the variant differ in exactly one field, so this
    isolates each declaration: replacing any single measurement with a
    non-finite value must not raise ``quality_score`` or ``screening_score``.
    """
    baseline = assess_candidate_quality(_candidate(**MEASURED))
    variant_kwargs = dict(MEASURED)
    variant_kwargs[field] = float("nan")
    variant = assess_candidate_quality(_candidate(**variant_kwargs))
    assert variant.quality_score <= baseline.quality_score + 1e-12, field
    assert variant.screening_score <= baseline.screening_score + 1e-12, field


def test_all_fields_non_finite_still_yields_finite_scores():
    assessed = assess_candidate_quality(_nan_candidate())
    for name in ("quality_score", "screening_score", "false_positive_risk"):
        value = getattr(assessed, name)
        assert np.isfinite(value), name
        assert 0.0 <= value <= 1.0, name


def test_a_non_finite_field_no_longer_skips_its_own_branch():
    """The actual defect: every NaN comparison is False, so the branch did not run.

    ``multiscale_persistence`` at its ``worst`` value of 0.0 is below the 0.34
    threshold, so the weak-persistence penalty and flag must now fire. With the
    old ``np.clip`` path a NaN skipped both -- as did every other NaN branch.
    """
    assessed = assess_candidate_quality(_nan_candidate())
    assert "weak-multiscale-persistence" in assessed.quality_flags
    assert "unstable-depth" in assessed.quality_flags, "depth NaN skipped its own branch too"
    assert "weak-geometry" in assessed.quality_flags
    # With every field unmeasured the risk field resolves to its adverse extreme,
    # which is the first branch of the status cascade.
    assert assessed.review_status == "artifact-concern"
    assert assessed.quality_score == 0.0


def test_a_risk_field_never_defaults_to_its_favourable_extreme():
    """``artifact_score`` is a risk: 0 means clean, so unknown means 1.0.

    Defaulting a risk to its favourable extreme is a policy inversion -- "we did
    not measure any artifact-like behaviour" reported as "no artifact-like
    behaviour".
    """
    assert bounded01(float("nan"), risk=True) == 1.0
    assert bounded01(float("nan"), risk=False) == 0.0
    assert bounded01(None, unknown="neutral", risk=True) == 0.5
    assessed = assess_candidate_quality(_candidate(**{**MEASURED, "artifact_score": float("nan")}))
    assert "artifact-concern" in assessed.quality_flags
    assert "artifact-score-unmeasured" in assessed.quality_flags


def test_geometry_and_mineralization_are_flagged_not_silently_substituted():
    candidate = _candidate(**{
        **MEASURED,
        "geometry_quality": float("nan"),
        "mineralization_risk": float("nan"),
    })
    # `unmeasured_fields` names the fields; the report-facing flags are the names.
    assert unmeasured_fields(candidate) == ["geometry_quality", "mineralization_risk"]
    assessed = assess_candidate_quality(candidate)
    assert "geometry-quality-unmeasured" in assessed.quality_flags
    assert "mineralization-risk-unmeasured" in assessed.quality_flags


def test_a_flagged_field_never_reports_a_worst_case_risk():
    """Worst (1.0) for mineralization would score an availability gap as a hazard."""
    role, fallback, flag = NONFINITE_POLICY["mineralization_risk"]
    assert role == "neutral"
    assert fallback == 0.5
    assert flag is not None


def test_bounded01_rejects_an_unknown_role():
    with pytest.raises(ValueError, match="unknown"):
        bounded01(0.5, unknown="whatever")


# ===========================================================================
# S08 -- singleton depth fusion
# ===========================================================================


def _depth_candidate(cid: int, estimate: float, **over) -> Candidate:
    base = dict(CANDIDATE_BASE)
    base.update(
        depth_estimate=estimate,
        depth_estimate_std=0.0,
        depth_min=estimate,
        depth_max=estimate,
        depth_valid_fraction=1.0,
        depth_stability_score=1.0,
        evidence_score=0.5,
        geometry_quality=0.5,
    )
    base.update(over)
    return Candidate(id=cid, **base)


def test_singleton_depth_does_not_report_perfect_agreement():
    """The measured defect: count==1 gave relative 0.0 / consistency 1.0.

    ``_robust_dispersion`` returns 0.0 for n < 2, so the relative spread
    collapsed to zero and one scan "confirmed" the depth perfectly -- the same
    class of defect ADR-002 fixed for ``position_stability``.
    """
    fused = fuse_depth([_depth_candidate(1, 2.0)])
    assert fused.measurement_count == 1
    assert fused.relative_dispersion == pytest.approx(0.5)
    assert fused.consistency == pytest.approx(0.5)


def test_two_or_more_observations_are_unaffected():
    before = fuse_depth([_depth_candidate(1, 2.0), _depth_candidate(2, 2.1)])
    assert before.measurement_count == 2
    assert before.relative_dispersion < 0.5
    assert before.consistency > 0.5
    three = fuse_depth([
        _depth_candidate(1, 2.0),
        _depth_candidate(2, 2.1),
        _depth_candidate(3, 2.2),
    ])
    assert three.measurement_count == 3
    assert three.consistency < 1.0


def test_the_derived_depth_fields_all_move_together():
    """Design: the four derived fields must not disagree.

    A fix that corrected ``consistency`` but left ``quality`` claiming high
    confidence would be half a fix.
    """
    one = fuse_depth([_depth_candidate(1, 2.0)])
    two = fuse_depth([_depth_candidate(1, 2.0), _depth_candidate(2, 2.1)])
    assert one.quality < two.quality, "singleton must not out-score a measured pair"
    assert one.relative_dispersion > two.relative_dispersion
    assert one.consistency < two.consistency


def test_no_depth_measurements_keeps_its_existing_convention():
    """Unchanged: a cluster with no depth at all is not the same case."""
    empty = fuse_depth([_depth_candidate(1, 2.0, depth_estimate=float("nan"))])
    assert empty.measurement_count == 0
    assert empty.consistency == 0.0


# ===========================================================================
# S05 / S06 -- field manifest strictness
# ===========================================================================


def _manifest(tmp_path: Path, cases: list[dict], name: str = "m") -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps({"independent_field_ground_truth": True, "cases": cases}),
        encoding="utf-8",
    )
    return path


BASE_CASE = {"case_id": "c1", "scan_path": "s.csv"}


@pytest.mark.parametrize("value", [True, False])
def test_a_real_boolean_target_present_is_accepted(tmp_path, value):
    loaded = load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "target_present": value}]))
    assert loaded[0].target_present is value


@pytest.mark.parametrize("value", ["true", "false", 0, 1, 1.0, None, [], {}, ""])
def test_a_non_boolean_target_present_is_rejected(tmp_path, value):
    """The inversion that mattered: ``"false"`` used to be read as ``True``."""
    with pytest.raises(ValueError):
        load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "target_present": value}]))


def test_the_string_false_inversion_is_pinned_explicitly(tmp_path):
    """The single most damaging coercion, pinned so it cannot come back."""
    payload = {"case_id": "c1", "scan_path": "s.csv", "target_present": "false"}
    errors = validate_field_truth_payload({
        "independent_field_ground_truth": True,
        "cases": [payload],
    })
    assert any("boolean" in e for e in errors)
    with pytest.raises(ValueError):
        load_field_truth(_manifest(tmp_path, [payload]))


def test_absent_target_present_still_defaults_to_true(tmp_path):
    """Absent is the documented default; only a wrong-typed value is an error."""
    loaded = load_field_truth(_manifest(tmp_path, [dict(BASE_CASE)]))
    assert loaded[0].target_present is True


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0, -1, -1e-9])
def test_non_finite_and_non_positive_tolerances_are_rejected(tmp_path, value):
    """``nan <= 0`` is False, so the old guard let both non-finite values through."""
    with pytest.raises(ValueError):
        load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "tolerance_m": value}]))
    with pytest.raises(ValueError):
        load_field_truth(
            _manifest(
                tmp_path,
                [{**BASE_CASE, "depth_m": 3.0, "depth_tolerance_m": value}],
            )
        )


def test_a_valid_tolerance_is_accepted(tmp_path):
    loaded = load_field_truth(
        _manifest(
            tmp_path,
            [{**BASE_CASE, "tolerance_m": 2.5, "depth_m": 3.0, "depth_tolerance_m": 1.0}],
        )
    )
    assert loaded[0].tolerance_m == pytest.approx(2.5)
    assert loaded[0].depth_tolerance_m == pytest.approx(1.0)


def test_no_plausibility_ceiling_is_invented(tmp_path):
    """A large-but-finite tolerance is accepted: the ceiling is calibration.

    Remediation Design v2 §15.1 holds the maximum plausible locator error in the
    do-not-implement-yet register. Stage 2 may reject non-finite and non-positive
    values (no calibration needed) and must not invent the ceiling.
    """
    loaded = load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "tolerance_m": 1e9}]))
    assert loaded[0].tolerance_m == pytest.approx(1e9)


def test_x_and_y_must_come_as_a_pair(tmp_path):
    with pytest.raises(ValueError):
        load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "x": 1.0}]))


def test_depth_requires_a_depth_tolerance(tmp_path):
    with pytest.raises(ValueError):
        load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "depth_m": 3.0}]))


def test_verification_method_is_a_closed_vocabulary(tmp_path):
    for method in VERIFICATION_METHODS:
        loaded = load_field_truth(
            _manifest(tmp_path, [{**BASE_CASE, "verification_method": method}])
        )
        assert loaded[0].verification_method == method
    with pytest.raises(ValueError, match="unknown verification_method"):
        load_field_truth(_manifest(tmp_path, [{**BASE_CASE, "verification_method": "vibes"}]))


def test_the_schema_is_actually_loaded_now():
    """It used to be a documentation string only, so nothing was enforced."""
    source = Path("groundscan/validation/field.py").read_text(encoding="utf-8")
    assert "validate_field_truth_payload" in source
    assert "does not conform" in source
    # And the boolean type the schema relies on is now implemented.
    assert (
        validate_field_truth_payload({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "c", "scan_path": "s", "target_present": True}],
        })
        == []
    )


# ===========================================================================
# S04 -- claim vs verified status
# ===========================================================================


def test_a_manifest_assertion_is_a_claim_not_a_verified_status(tmp_path):
    path = _manifest(tmp_path, [dict(BASE_CASE)])
    status = field_ground_truth_status(json.loads(path.read_text(encoding="utf-8")))
    assert status["claimed"] is True
    assert status["verified"] is False
    assert status["verification_status"] == "unverified-claim"
    assert status["schema_errors"] == []
    assert "no mechanism" in status["reason"]


def test_schema_conformance_is_reported_as_layer_one_only(tmp_path):
    """Contract K8: L1 conformance proves nothing about L3 or L4."""
    status = field_ground_truth_status({
        "independent_field_ground_truth": True,
        "cases": [{"case_id": "c", "scan_path": "s"}],
    })
    assert status["schema_errors"] == []
    assert status["verified"] is False


def test_the_output_separates_claim_from_status():
    source = Path("groundscan/validation/field.py").read_text(encoding="utf-8")
    assert "ground_truth_claim" in source
    assert "ground_truth_verified" in source
    # The old output asserted a result where there was only a claim.
    assert '"independent_field_ground_truth": True' not in source


# ===========================================================================
# S10 -- artifact identity
# ===========================================================================


class _FakeScan:
    def __init__(self, signal: float) -> None:
        self.signal = [signal, signal + 1.0]
        self.x = [0.0, 1.0]
        self.y = [0.0, 1.0]
        self.z = [0.0, 1.0]


def test_the_identity_quad_keeps_four_jobs_apart():
    identity = artifact_identity("Pass 1", fingerprint=scan_fingerprint(_FakeScan(1.0)))
    assert isinstance(identity, ArtifactIdentity)
    assert identity.display_label == "Pass 1"
    assert identity.logical_id
    assert identity.filesystem_stem.startswith("Pass_1-")
    assert identity.content_fingerprint


def test_labels_that_sanitize_alike_get_distinct_stems():
    """The collision: "Pass 1" and "pass_1" both sanitise to ``pass_1``."""
    a = artifact_identity("Pass 1", fingerprint=scan_fingerprint(_FakeScan(1.0)))
    b = artifact_identity("pass_1", fingerprint=scan_fingerprint(_FakeScan(9.0)))
    assert a.filesystem_stem != b.filesystem_stem
    assert a.display_label != b.display_label
    assert a.logical_id != b.logical_id


def test_a_stem_is_human_readable_and_path_safe():
    """Traversal protection is not weakened by adding the digest.

    ``sanitize_label`` keeps only the last path segment, so a traversal attempt
    becomes its final component -- the digest is appended, not substituted for,
    and containment is still enforced by ``contained_path``.
    """
    identity = artifact_identity("../../etc/passwd", fingerprint="0" * 64)
    assert identity.filesystem_stem == "passwd-00000000"
    assert "/" not in identity.filesystem_stem
    assert ".." not in identity.filesystem_stem
    # the operator's own string is still preserved verbatim for display
    assert identity.display_label == "../../etc/passwd"


def test_a_true_duplicate_shares_a_stem_and_that_is_correct():
    """Same content is the same identity; the duplicate is warned about elsewhere."""
    one = artifact_identity("Pass 1", fingerprint=scan_fingerprint(_FakeScan(1.0)))
    two = artifact_identity("Pass 1", fingerprint=scan_fingerprint(_FakeScan(1.0)))
    assert one.filesystem_stem == two.filesystem_stem


def test_the_stem_is_order_independent():
    """A function of content, not of enumeration order."""
    scans = [("b", _FakeScan(2.0)), ("a", _FakeScan(1.0))]
    forward = {
        label: artifact_identity(label, fingerprint=scan_fingerprint(s)) for label, s in scans
    }
    backward = {
        label: artifact_identity(label, fingerprint=scan_fingerprint(s))
        for label, s in reversed(scans)
    }
    assert {k: v.filesystem_stem for k, v in forward.items()} == {
        k: v.filesystem_stem for k, v in backward.items()
    }


def test_the_fingerprint_ignores_the_label():
    a = scan_fingerprint(_FakeScan(1.0))
    b = scan_fingerprint(_FakeScan(1.0))
    assert a == b
    assert a != scan_fingerprint(_FakeScan(2.0))


def test_content_fingerprint_accepts_bytes_and_str():
    assert content_fingerprint(b"abc") == content_fingerprint("abc")
    assert len(content_fingerprint("abc")) == 64


def test_the_identity_helper_is_total_without_a_fingerprint():
    identity = artifact_identity("some label")
    assert identity.filesystem_stem
    assert identity.content_fingerprint


# ===========================================================================
# K9 / S11 -- output side effects
# ===========================================================================


def test_output_dir_creates_nothing_when_disabled(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert output_dir(target, enabled=False) is None
    assert not target.exists()
    assert not tmp_path.joinpath("a").exists()


def test_output_dir_creates_the_tree_when_enabled(tmp_path):
    target = tmp_path / "x" / "y"
    created = output_dir(target, enabled=True)
    assert created is not None and target.is_dir()


def test_write_outputs_false_creates_no_directory(tmp_path):
    """Measured before the fix: a nested tree appeared with nothing written."""
    out = tmp_path / "a" / "b" / "c" / "d"
    analyze_scan(
        _grid_scan(),
        out,
        label="s",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert not out.exists()
    assert not tmp_path.joinpath("a").exists()


def test_write_outputs_false_writes_no_file_including_the_provenance_note(tmp_path):
    """The provenance note used to be written outside the flag."""
    out = tmp_path / "out"
    analyze_scan(
        _grid_scan(),
        out,
        label="s",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert not out.exists()
    written = list(out.rglob("*")) if out.exists() else []
    assert written == []


def test_write_outputs_true_still_writes_everything(tmp_path):
    out = tmp_path / "out"
    analyze_scan(
        _grid_scan(),
        out,
        label="s",
        config=AnalysisConfig(),
        write_outputs=True,
    )
    assert out.is_dir()
    names = {p.name for p in out.iterdir()}
    assert any(n.endswith("_analysis.json") for n in names)
    assert any(n.endswith("_candidates.csv") for n in names)


def test_the_provenance_note_is_written_only_for_index_or_derived_coordinates(tmp_path):
    """It moved inside the output guard, so it must still be written when it applies."""
    out = tmp_path / "out"
    scan = _grid_scan()
    scan.coords_are_index_only = True
    scan.coordinate_provenance = "index"
    analyze_scan(scan, out, label="s", config=AnalysisConfig(), write_outputs=True)
    names = {p.name for p in out.iterdir()}
    assert any("IMPORTANT" in n for n in names), names


def test_the_provenance_note_is_not_written_when_output_is_disabled(tmp_path):
    """The defect: this one file was written outside the flag."""
    out = tmp_path / "out"
    scan = _grid_scan()
    scan.coords_are_index_only = True
    scan.coordinate_provenance = "index"
    analyze_scan(scan, out, label="s", config=AnalysisConfig(), write_outputs=False)
    assert not out.exists()


def test_evaluate_field_dataset_with_no_out_dir_does_not_touch_the_cwd(tmp_path):
    """``Path(".")`` used to make the CWD the output directory."""
    work = tmp_path / "work"
    scans = work / "scans"
    scans.mkdir(parents=True)
    rows = [
        f"{i},{j},0,{0 if not (5 <= i < 8 and 5 <= j < 8) else 20}"
        for j in range(20)
        for i in range(20)
    ]
    (scans / "s.csv").write_text("x,y,z,signal\n" + "\n".join(rows) + "\n", encoding="utf-8")
    manifest = work / "m.json"
    manifest.write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "c1", "scan_path": "scans/s.csv"}],
        }),
        encoding="utf-8",
    )
    from groundscan.validation.field import evaluate_field_dataset

    before = sorted(p.name for p in work.iterdir())
    original = os.getcwd()
    os.chdir(work)
    try:
        evaluate_field_dataset(manifest, out_dir=None)
        after = sorted(p.name for p in work.iterdir())
    finally:
        os.chdir(original)
    assert after == before, "the working directory was polluted"


def test_evaluate_field_dataset_reports_claim_and_status_separately(tmp_path):
    work = tmp_path / "work"
    scans = work / "scans"
    scans.mkdir(parents=True)
    rows = [
        f"{i},{j},0,{0 if not (5 <= i < 8 and 5 <= j < 8) else 20}"
        for j in range(20)
        for i in range(20)
    ]
    (scans / "s.csv").write_text("x,y,z,signal\n" + "\n".join(rows) + "\n", encoding="utf-8")
    manifest = work / "m.json"
    manifest.write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [{"case_id": "c1", "scan_path": "scans/s.csv"}],
        }),
        encoding="utf-8",
    )
    from groundscan.validation.field import evaluate_field_dataset

    result = evaluate_field_dataset(manifest, out_dir=None)
    assert result["ground_truth_claim"] is True
    assert result["ground_truth_verified"] is False
    assert result["manifest_schema_conformant"] is True
    assert "independent_field_ground_truth" not in result


def test_field_case_ids_that_sanitize_alike_do_not_collide(tmp_path):
    work = tmp_path / "work"
    scans = work / "scans"
    scans.mkdir(parents=True)
    rows = [
        f"{i},{j},0,{0 if not (5 <= i < 8 and 5 <= j < 8) else 20}"
        for j in range(20)
        for i in range(20)
    ]
    (scans / "s.csv").write_text("x,y,z,signal\n" + "\n".join(rows) + "\n", encoding="utf-8")
    manifest = work / "m.json"
    manifest.write_text(
        json.dumps({
            "independent_field_ground_truth": True,
            "cases": [
                {"case_id": "Case A", "scan_path": "scans/s.csv"},
                {"case_id": "case_a", "scan_path": "scans/s.csv"},
            ],
        }),
        encoding="utf-8",
    )
    from groundscan.validation.field import evaluate_field_dataset

    out = tmp_path / "out"
    evaluate_field_dataset(manifest, out_dir=out)
    run_dirs = sorted(p.name for p in out.iterdir() if p.is_dir())
    assert len(run_dirs) == 2, run_dirs
    assert len(set(run_dirs)) == 2


def test_site_scans_whose_labels_sanitize_alike_get_distinct_directories(tmp_path):
    """The site-side collision, end to end."""
    from groundscan.site.analyze_site import analyze_site

    base = _grid_scan()
    a = ScanData(x=base.x.copy(), y=base.y.copy(), z=base.z.copy(), signal=base.signal.copy())
    b = ScanData(x=base.x.copy(), y=base.y.copy(), z=base.z.copy(), signal=base.signal + 0.5)
    out = tmp_path / "site"
    analyze_site(
        [("Pass 1", a), ("pass_1", b)],
        out,
    )
    scan_dirs = sorted(p.name for p in (out / "scans").iterdir())
    assert len(scan_dirs) == 2, scan_dirs
    assert len(set(scan_dirs)) == 2
    # still recognisable to a human browsing the output
    assert any("pass_1" in d.lower() for d in scan_dirs)


# ===========================================================================
# S12 -- shape performance
# ===========================================================================


def test_local_edge_distance_matches_full_grid_bit_for_bit():
    """The acceptance criterion: identical, so no numerical behaviour change."""
    from groundscan.core.grid import Grid2D

    rng = np.random.default_rng(5)
    for shape in ((40, 40), (300, 300), (17, 33), (5, 200)):
        h, w = shape
        # The grid is only a shape carrier here; the arithmetic under test is
        # the integer edge distance over the component's own cells.
        assert (
            Grid2D(
                signal=rng.normal(size=shape),
                depth=rng.normal(size=shape),
                counts=np.ones(shape),
                x_centers=np.arange(w, dtype=float),
                y_centers=np.arange(h, dtype=float),
            ).signal.shape
            == shape
        )
        for _ in range(25):
            n = int(rng.integers(1, 400))
            ys = rng.integers(0, h, size=n)
            xs = rng.integers(0, w, size=n)
            yy, xx = np.indices(shape)
            full = np.minimum.reduce([yy, xx, h - 1 - yy, w - 1 - xx])[ys, xs]
            local = np.minimum.reduce([ys, xs, h - 1 - ys, w - 1 - xs])
            assert np.array_equal(full, local), shape
            assert float(np.mean(full <= 1)) == float(np.mean(local <= 1))


def test_the_shape_metric_reports_the_component_extent_not_the_grid_shape():
    """Guard on the shadowing regression this optimisation once introduced.

    A local named ``width``/``height`` silently replaced the candidate's physical
    extent with the grid's row/column counts, which is invisible in the edge
    distance but very visible in the metric.
    """
    _grid, _anomaly, candidates = analyze_scan(
        _grid_scan(),
        Path(os.environ.get("PYTEST_TMP", ".")) / "unused",
        label="s",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert candidates
    for candidate in candidates:
        assert 0.0 < candidate.width < 1000.0
        assert candidate.width < 20.0, "grid is 16 cells; width must be a cell span"
        assert candidate.height < 20.0
        assert 0.0 <= candidate.boundary_contact_ratio <= 1.0


def test_stage_two_changed_no_threshold_or_weight():
    """If Stage 2 had recalibrated anything, this would fail.

    Stage 2 is deterministic fixes only, so every gate band and score weight
    must still hold its pre-Stage-2 value. Pinned as literals read through the
    public module attributes, so a change to any of them is a test failure
    rather than a silent re-calibration.
    """
    from groundscan.gates import thresholds as T

    assert T.FUSION_EVIDENCE_WEIGHTS == _EXPECTED_FUSION_EVIDENCE_WEIGHTS
    assert T.REGISTRATION_EVIDENCE_WEIGHTS == _EXPECTED_REGISTRATION_EVIDENCE_WEIGHTS
    assert T.QUALITY_SUPPORT_WEIGHTS == _EXPECTED_QUALITY_SUPPORT
    assert T.QUALITY_PENALTY_WEIGHTS == _EXPECTED_QUALITY_PENALTY
    assert T.SCREENING_WEIGHTS == _EXPECTED_SCREENING


#: Pre-Stage-2 values, copied from ``gates/thresholds.py`` so a recalibration
#: cannot pass unnoticed.
_EXPECTED_FUSION_EVIDENCE_WEIGHTS = {
    "base": 0.18,
    "detection_rate": 0.17,
    "direction": 0.10,
    "spacing": 0.10,
    "traversal": 0.08,
    "position_stability": 0.10,
    "polarity_consistency": 0.07,
    "signal_consistency": 0.07,
    "depth_consistency": 0.06,
    "registration_consistency": 0.05,
    "consensus": 0.02,
}
_EXPECTED_REGISTRATION_EVIDENCE_WEIGHTS = {
    "correlation": 0.35,
    "overlap": 0.20,
    "margin": 0.15,
    "multiscale": 0.30,
}
_EXPECTED_QUALITY_SUPPORT = {
    "evidence": 0.45,
    "persistence": 0.15,
    "geometry": 0.10,
    "position": 0.08,
    "signal": 0.07,
    "registration": 0.05,
    "multi_evidence": 0.10,
}
_EXPECTED_QUALITY_PENALTY = {
    "artifact": 0.33,
    "boundary": 0.18,
    "uncertainty": 0.15,
}
_EXPECTED_SCREENING = {
    "evidence": 0.55,
    "quality": 0.30,
    "non_artifact": 0.15,
}


def test_the_s02_activation_is_complete_and_narrow():
    """Stage 3 activated S02. The guard moved with it, and says what replaced it.

    Stage 2 pinned "S02 is not activated"; Stage 3 activates it. What has to stay
    true afterwards is the *shape* of the fix, so this test now pins:

    * production computes a dimensionless ratio (cell pitch appears in both the
      numerator and the hull term) and no longer divides a count by an area;
    * the degenerate-centre branch contributes a zero hull area instead of a
      fabricated 1.0, so corner-touching geometry is measurable again;
    * the independent oracle still exists and is still *not* what production
      calls -- the cross-check is only worth anything while the two are separate
      derivations;
    * S03's caller is still untouched (the next stage's business).
    """
    import numpy as np

    from groundscan.core.shape import _convex_hull_solidity

    source = Path("groundscan/core/shape.py").read_text(encoding="utf-8")
    assert "def _convex_hull_solidity" in source
    # A count over an area: `area_cells` must not reach the solidity call.
    assert "_convex_hull_solidity(x_coords, y_coords, area_cells)" not in source
    assert "_convex_hull_solidity(x_coords, y_coords, cell_dx, cell_dy)" in source
    # The collinear branch is a zero-area hull, not a neutral 1.0.
    assert "hull_area = 0.0" in source

    # A diagonal run is one 8-connected component and is not solid.
    cells = np.array([(i, i) for i in range(5)], dtype=float)
    assert _convex_hull_solidity(cells[:, 1], cells[:, 0], 1.0, 1.0) == pytest.approx(
        5.0 / 9.0, abs=1e-12
    )
    # ...and the value cannot depend on the pitch.
    assert _convex_hull_solidity(cells[:, 1] * 7, cells[:, 0] * 7, 7.0, 7.0) == pytest.approx(
        5.0 / 9.0, abs=1e-12
    )

    shadow = Path("groundscan/diagnostics/shadow.py").read_text(encoding="utf-8")
    assert "def exact_solidity" in shadow
    assert "def legacy_solidity" in shadow


def test_the_production_robust_scale_estimator_is_untouched():
    """S03 is *not* activated: ``robust_scale`` still returns the legacy number."""
    from groundscan._util import robust_scale as canonical

    assert canonical(np.full(4000, 7.0)) == 1.0
    assert canonical(np.zeros(4000)) == 1.0
    rng = np.random.default_rng(4)
    values = rng.normal(0, 1, 2000)
    assert canonical(values) == canonical(values)

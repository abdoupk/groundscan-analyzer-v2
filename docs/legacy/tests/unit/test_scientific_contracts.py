"""Wave 0 / Stage 0 (PR-1): scientific contracts K1-K11 -- types, not behaviour.

Scope of this file:

* ``ScaleEstimate`` / ``robust_scale_with_status`` (contract K7) and the
  delegation parity that keeps ``robust_scale`` bit-identical.
* Coordinate semantics as three independent axes (contract K5) and the
  ingestion-time unit normalisation.

Scope it deliberately does **not** have: no caller of ``robust_scale`` is
switched to the status channel, and no existing behaviour changes. The
delegation-parity and golden suites are the proof.

Evidence discipline (v2 §12.1): every oracle here derives from the generating
distribution or from the mathematical structure of the construction. No test
asserts "the current output is X", which is the discipline whose absence let the
scale defect reach production.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from groundscan._util import (
    LEGACY_SCALE_FALLBACK,
    SCALE_STATUS_DEGRADED,
    SCALE_STATUS_INDETERMINATE,
    SCALE_STATUS_VALID,
    robust_scale,
    robust_scale_with_status,
)
from groundscan.models import (
    METRES_PER_UNIT,
    UNIT_SOURCE_ASSUMED_METRES,
    UNIT_SOURCE_DECLARED,
    UNIT_SOURCE_GRID_FRAME,
    ScanData,
    is_metric_coordinates,
    normalise_coordinate_units,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _scan(
    prov: str = "measured", unit: str | None = None, n: int = 6, step: float = 100.0
) -> ScanData:
    return ScanData(
        x=np.arange(n, dtype=float) * step,
        y=np.arange(n, dtype=float) * step,
        z=np.zeros(n),
        signal=np.arange(n, dtype=float),
        coordinate_provenance=prov,
        coordinate_unit=unit,
    )


def _legacy_robust_scale(values: np.ndarray) -> float:
    """The pre-Wave-0 implementation, verbatim: the delegation oracle.

    Copied rather than imported so the test fails if the delegation ever drifts
    from what it replaced. Any difference is a behaviour change.
    """
    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]
    if valid.size < 2:
        return 1.0
    med = float(np.median(valid))
    mad = float(np.median(np.abs(valid - med)))
    std = float(np.std(valid))
    if mad > 1e-9:
        scale = 1.4826 * mad
    else:
        q25, q75 = np.percentile(valid, [25, 75])
        iqr_scale = float(q75 - q25) / 1.349
        if iqr_scale > 1e-9:  # noqa: SIM108 — verbatim shape of the audited original
            scale = iqr_scale
        else:
            scale = std if std > 1e-9 else 1.0
    band = 5.0 * scale
    floor_std = float(np.std(np.clip(valid, med - band, med + band))) if band > 0.0 else 0.0
    return max(scale, 0.05 * floor_std)


# ---------------------------------------------------------------------------
# K7 -- ScaleEstimate type
# ---------------------------------------------------------------------------


def test_scale_estimate_is_frozen_and_self_describing():
    est = robust_scale_with_status(np.random.default_rng(7).normal(0.0, 1.0, 500))
    with pytest.raises(FrozenInstanceError):
        est.scale = 1.0  # type: ignore[misc]
    payload = est.to_dict()
    assert set(payload) == {
        "scale",
        "status",
        "method",
        "contamination_flag",
        "quantisation_step",
        "n_effective",
        # Stage 3: the reliability measurement that makes `degraded` actionable.
        # A status with no number beside it is honest but not usable.
        "contamination_influence",
    }
    assert payload["n_effective"] == 500
    assert isinstance(payload["contamination_flag"], bool)


def test_scale_estimate_reports_nan_not_a_fabricated_number_when_indeterminate():
    """A constant field has no estimable spread -- say so, do not invent one."""
    for constant in (0.0, 5.0, -1.25, 1e9):
        est = robust_scale_with_status(np.full(4000, constant))
        assert est.status == SCALE_STATUS_INDETERMINATE
        assert est.is_indeterminate
        assert est.scale != est.scale, "indeterminate must be NaN, not a number"
        assert est.method == "none"


def test_legacy_fallback_is_preserved_for_the_indeterminate_case():
    """K7 forbids fabricating a *measurement*; it does not break the old API."""
    assert robust_scale(np.zeros(4000)) == LEGACY_SCALE_FALLBACK
    assert robust_scale(np.full(4000, 5.0)) == LEGACY_SCALE_FALLBACK
    # ...and the empty / single-sample cases keep their documented constant.
    assert robust_scale(np.array([])) == LEGACY_SCALE_FALLBACK
    assert robust_scale(np.array([3.0])) == LEGACY_SCALE_FALLBACK


# ---------------------------------------------------------------------------
# K7 -- delegation parity: robust_scale must be bit-identical
# ---------------------------------------------------------------------------
# Stage 3 split this list. Every case that is *not* dust-level must still be
# bit-identical to the pre-Wave-0 implementation, and that is the property the
# delegation exists for. The one case that moved is separated out below with
# its own oracle, because "bit-identical" and "the fabrication is gone" cannot
# both be asserted of it and pretending otherwise is how a behaviour change gets
# signed off as a refactor.


@pytest.mark.parametrize(
    "name, values",
    [
        ("empty", np.array([])),
        ("single", np.array([3.0])),
        ("pair", np.array([1.0, 2.0])),
        ("constant_zero", np.zeros(4000)),
        ("constant_five", np.full(4000, 5.0)),
        ("gaussian", np.random.default_rng(1).normal(0.0, 1.0, 4000)),
        ("student_t3", np.random.default_rng(2).standard_t(3, 4000)),
        ("uniform", np.random.default_rng(3).uniform(-1.0, 1.0, 4000)),
        ("quantised_16", np.round(np.random.default_rng(4).normal(0, 1, 4000) * 4) / 4.0),
        ("quantised_3", np.round(np.random.default_rng(5).normal(0, 1, 4000))),
        ("one_spike_200", np.concatenate([np.zeros(3999), [200.0]])),
        ("huge_spike", np.concatenate([np.zeros(3998), [1e5, 0.0]])),
        (
            "with_nans",
            np.where(
                np.random.default_rng(8).random(4000) < 0.1,
                np.nan,
                np.random.default_rng(9).normal(0, 1, 4000),
            ),
        ),
    ],
)
def test_delegation_is_bit_identical_to_the_pre_wave0_implementation(name, values):
    """The whole point of delegating: not one call site may observe a change.

    Stage 3 replaced the absolute ``mad > 1e-9`` degeneracy test with a
    scale-free one, and this is the test that proves the replacement does not
    move a number. It covers the spike cases as well as the smooth ones on
    purpose: those are where a scale-free gate could plausibly have changed a
    decision, and it does not.
    """
    assert robust_scale(values) == _legacy_robust_scale(values)
    assert robust_scale_with_status(values).legacy_scale == _legacy_robust_scale(values)


def test_the_dust_case_is_the_one_the_scale_free_gate_intentionally_moved():
    """4000 samples of 1e-15 dust: the pre-Wave-0 code reported a scale of 1.0.

    Its own dispersion is 1.0e-15, which is measurable and is not 1.0. The old
    absolute test could not tell "no spread" from "a spread of 1e-15", so it
    declared the sample unmeasurable and the delegated ``return 1.0`` then
    presented that declaration as a measurement. This is the S03 defect in its
    smallest form, and it is asserted here with the *measured* dispersion as the
    oracle rather than with a number copied from the implementation.
    """
    values = np.random.default_rng(6).normal(0.0, 1e-15, 4000)
    dispersion = float(np.std(values))
    assert _legacy_robust_scale(values) == 1.0
    estimate = robust_scale_with_status(values)
    assert estimate.legacy_scale == pytest.approx(dispersion, rel=0.05)
    # The primary tier now *reaches* this field, where the absolute test had
    # declared it unmeasurable. That is the whole change: a Gaussian dust
    # sample is a sample, and its MAD is the estimate.
    assert estimate.status == SCALE_STATUS_VALID
    assert estimate.method == "mad"
    # ...and the value is now a ratio of a quantity to itself, not a constant:
    # scaling the field scales the answer by exactly the same factor.
    scaled = robust_scale_with_status(values * 1e6)
    assert scaled.legacy_scale == pytest.approx(estimate.legacy_scale * 1e6, rel=1e-9)


def test_the_removed_scale_floor_was_provably_inert():
    """The deleted ``max(scale, 5% * winsorized_std)`` floor could never bind.

    The floor was removed as dead code (see ``groundscan._util.robust_scale``).
    This test pins the *reason* it was dead, so the deletion cannot be silently
    reversed on the belief that it was load-bearing, and so a future
    reintroduction of any similar floor is checked against the bound rather
    than against intuition.

    Every winsorized value lies in ``[med - 5*scale, med + 5*scale]``, a
    half-width of ``5*scale``; by Popoviciu's inequality a variable supported on
    such an interval has standard deviation at most ``5*scale``. So the floor's
    candidate ``0.05 * floor_std`` is at most ``0.25 * scale``, strictly below
    ``scale`` -- the ``max()`` could only ever return its first argument.

    The bound is checked empirically across the degenerate regimes the floor was
    supposed to protect, which is where it would have had to bind to matter.
    """
    rng = np.random.default_rng(2024)
    cases = [
        np.full(500, 3.0),  # fully degenerate: no spread at all
        np.concatenate([np.zeros(499), [1e9]]),  # one atom, one spike
        np.concatenate([np.zeros(250), rng.uniform(0.0, 1.0, 250)]),  # atom-heavy
        np.concatenate([np.zeros(400), rng.normal(0.0, 1.0, 100)]),
        np.concatenate([rng.normal(0.0, 0.3, 900), np.full(100, 1e4)]),  # heavy tail
        np.round(rng.normal(0.0, 1.0, 1000)),  # quantised lattice
        np.concatenate([np.zeros(998), [1e5, -1e5]]),
        rng.standard_t(1.5, 2000),  # heavy-tailed, no atoms
    ]
    for values in cases:
        valid = np.asarray(values, dtype=float)
        valid = valid[np.isfinite(valid)]
        if valid.size < 2:
            continue
        # Reproduce the pre-deletion floor exactly, on top of the current value.
        current = robust_scale_with_status(valid).legacy_scale
        med = float(np.median(valid))
        band = 5.0 * current
        floor_std = float(np.std(np.clip(valid, med - band, med + band))) if band > 0.0 else 0.0
        assert 0.05 * floor_std <= 0.25 * current + 1e-12, (
            "winsorized std exceeded the Popoviciu bound 5*scale; the removed "
            "floor would no longer be provably inert and this test's premise "
            "needs re-deriving"
        )
        assert max(current, 0.05 * floor_std) == current, (
            f"the removed floor would have changed the estimate: "
            f"max({current!r}, {0.05 * floor_std!r}) != {current!r}"
        )


# ---------------------------------------------------------------------------
# K7 -- estimator ladder and status
# ---------------------------------------------------------------------------


def test_mad_is_the_primary_tier_and_reports_valid():
    values = np.random.default_rng(11).normal(0.0, 1.0, 4000)
    est = robust_scale_with_status(values)
    assert est.method == "mad"
    assert est.status == SCALE_STATUS_VALID
    # MAD x 1.4826 is consistent with sigma for a Gaussian.
    assert 0.8 < est.scale < 1.25


def test_constant_plus_single_spike_reaches_the_degraded_tier():
    """No estimator recovers a noise floor from {0,...,0, 200}; the status says so."""
    est = robust_scale_with_status(np.concatenate([np.zeros(3999), [200.0]]))
    assert est.status == SCALE_STATUS_DEGRADED
    assert est.method == "std"
    assert np.isfinite(est.scale)


def test_contamination_flag_fires_on_a_heavy_contaminated_population():
    rng = np.random.default_rng(12)
    clean = rng.normal(0.0, 1.0, 1000)
    contaminated = np.concatenate([rng.normal(0.0, 1.0, 600), rng.normal(0.0, 40.0, 400)])
    assert not robust_scale_with_status(clean).contamination_flag
    assert robust_scale_with_status(contaminated).contamination_flag


# ---------------------------------------------------------------------------
# K7 -- the quantisation estimator is metadata, never a scale
# ---------------------------------------------------------------------------


def test_quantisation_step_is_detected_for_a_quantised_lattice():
    """v2 §12.4 metadata contract: 16-level quantised -> step 0.25."""
    rng = np.random.default_rng(13)
    quantised = np.round(rng.normal(0.0, 1.0, 4000) * 4) / 4.0
    est = robust_scale_with_status(quantised)
    assert est.quantisation_step == pytest.approx(0.25, abs=1e-12)


def test_quantisation_step_is_absent_for_continuous_and_constant_fields():
    rng = np.random.default_rng(14)
    assert robust_scale_with_status(rng.normal(0.0, 1.0, 4000)).quantisation_step is None
    assert robust_scale_with_status(np.zeros(4000)).quantisation_step is None
    assert robust_scale_with_status(np.array([1.0, 2.0])).quantisation_step is None


def test_the_gap_detector_is_not_used_as_a_scale():
    """The refuted v1 estimator fails as a scale; it survives only as metadata."""
    # Measured v2 §6.3: the gap "estimator" returns the spike amplitude itself.
    spike_field = np.concatenate([np.zeros(3999), [200.0]])
    est = robust_scale_with_status(spike_field)
    # Whatever the status, the reported scale is never the bare spike amplitude.
    assert not (np.isfinite(est.scale) and est.scale == pytest.approx(200.0))


# ---------------------------------------------------------------------------
# K5 -- coordinate semantics: three independent axes
# ---------------------------------------------------------------------------


def test_undeclared_unit_on_measured_coordinates_assumes_metres_explicitly():
    """Backward compatibility, with the assumption made visible instead of implicit."""
    semantics = _scan("measured", None).coordinate_semantics
    assert semantics.declared_unit is None
    assert semantics.effective_unit == "m"
    assert semantics.unit_source == UNIT_SOURCE_ASSUMED_METRES
    # "assumed, not verified" must be stated in the reason the report carries.
    assert "ASSUMED" in semantics.geometry_reliability_reason
    # Behaviour is unchanged: measured coordinates are still metric.
    assert semantics.geometry_reliable is True
    assert is_metric_coordinates(_scan("measured", None))


def test_declared_metres_is_distinguishable_from_assumed_metres():
    declared = _scan("measured", "m").coordinate_semantics
    assumed = _scan("measured", None).coordinate_semantics
    assert declared.effective_unit == assumed.effective_unit == "m"
    assert declared.unit_source == UNIT_SOURCE_DECLARED
    assert declared.unit_source != assumed.unit_source
    assert declared.conversion_to_metres is None


def test_measured_non_metre_is_normalised_not_refused():
    """v1 proposed refusing measured centimetres; that would reject good data."""
    scan = _scan("measured", "cm")
    factor = normalise_coordinate_units(scan)
    assert factor == pytest.approx(0.01)
    assert scan.coordinate_semantics.geometry_reliable is True
    assert scan.x[1] == pytest.approx(1.0)  # 100 cm -> 1 m


def test_declared_non_metre_normalisation_is_exact_for_every_conversion():
    for unit, factor in METRES_PER_UNIT.items():
        scan = _scan("measured", unit, step=1000.0)
        applied = normalise_coordinate_units(scan)
        if factor == 1.0:
            # "m" needs no conversion, and None is the "nothing was converted"
            # signal -- not 1.0.
            assert applied is None
        else:
            assert applied == pytest.approx(factor), unit
        assert scan.x[1] == pytest.approx(1000.0 * factor), unit


def test_normalisation_is_a_strict_no_op_for_every_pre_wave0_input():
    """No scan that could exist before Wave 0 may move by one ulp."""
    for prov in ("measured", "derived", "index"):
        for unit in (None, "m"):
            scan = _scan(prov, unit, step=3.7)
            before_x, before_y = scan.x.copy(), scan.y.copy()
            assert normalise_coordinate_units(scan) is None
            assert np.array_equal(scan.x, before_x)
            assert np.array_equal(scan.y, before_y)


def test_index_coordinates_are_a_frame_not_a_length():
    for unit in (None, "m", "grid-cells"):
        semantics = _scan("index", unit).coordinate_semantics
        assert semantics.effective_unit == "grid-cells"
        assert semantics.unit_source == UNIT_SOURCE_GRID_FRAME
        assert semantics.geometry_reliable is False
        assert semantics.conversion_to_metres is None
        assert not is_metric_coordinates(_scan("index", unit))


def test_derived_coordinates_stay_unreliable_in_every_unit():
    """Accuracy is bounded by self-reported field dimensions, unit or not."""
    for unit in (None, "m", "cm"):
        semantics = _scan("derived", unit).coordinate_semantics
        assert semantics.geometry_reliable is False


def test_geometry_reliability_stays_consistent_with_the_existing_predicate():
    """K5 must not contradict `is_metric_coordinates`, which gates real decisions."""
    for prov in ("measured", "derived", "index"):
        for unit in (None, "m", "cm", "grid-cells"):
            scan = _scan(prov, unit)
            assert scan.coordinate_semantics.geometry_reliable == is_metric_coordinates(scan)


def test_explicit_geometry_reliable_overrides_the_derived_default():
    scan = _scan("measured", "m")
    scan.geometry_reliable = False
    assert scan.coordinate_semantics.geometry_reliable is False
    assert is_metric_coordinates(scan), "the historical predicate is unchanged"


def test_invalid_unit_is_rejected_at_construction():
    with pytest.raises(ValueError, match="coordinate_unit"):
        _scan("measured", "parsec")


def test_semantics_dict_exposes_the_resolved_axes():
    payload = _scan("measured", "ft").coordinate_semantics.to_dict()
    assert payload["provenance"] == "measured"
    assert payload["declared_unit"] == "ft"
    assert payload["effective_unit"] == "m"
    assert payload["conversion_to_metres"] == pytest.approx(0.3048)
    assert "ft" in payload["geometry_reliability_reason"]


def test_declared_centimetres_are_converted_before_the_grid_is_built(tmp_path):
    """Ingestion normalisation is real: a 100 cm pitch must analyse as 1 m."""
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import analyze_scan

    n = 16
    rng = np.random.default_rng(3)
    gx, gy = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    signal[7:10, 7:10] += 12.0
    scan = ScanData(
        x=(gx * 100.0).ravel(),
        y=(gy * 100.0).ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        coordinate_unit="cm",
    )
    before = float(np.median(np.diff(np.unique(scan.x))))
    assert before == pytest.approx(100.0)
    analyze_scan(
        scan,
        tmp_path / "cm",
        label="scan",
        config=AnalysisConfig(),
        write_outputs=False,
    )
    assert float(np.median(np.diff(np.unique(scan.x)))) == pytest.approx(1.0)

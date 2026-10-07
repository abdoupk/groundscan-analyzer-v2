"""Follow-up audit regression pins: three further confirmed defects.

Companion to ``test_audit_regressions.py`` (the six fixes in the first audit
PR). Same discipline: every test here reproduces a defect that was verified by
execution and fails on the pre-fix code.

  * ingestion  -- a duplicate CSV header must not surface as a ScanData error
  * fusion     -- a single-observation cluster must not claim perfect consistency
  * rescue     -- the extraction-rescue policy's own knobs must actually be used
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

from groundscan import Candidate
from groundscan.core.grid import Grid2D
from groundscan.io.generic_csv import GenericCSVAdapter
from groundscan.site.fusion import _robust_relative_dispersion, fuse_geometry


# --------------------------------------------------------------------------
# ingestion: duplicate headers
# --------------------------------------------------------------------------
def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "scan.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_duplicate_csv_headers_are_rejected_by_name():
    """A repeated column name must be reported against the CSV, not the model.

    The header dict was built by comprehension, so a repeat silently collapsed:
    ``x,x,y,signal`` kept three keys for four names, and the failure surfaced
    much later as ``ScanData.x must be an array of length 3 (len(signal)),
    got 6`` -- an arity message from models.py that says nothing about the file.
    """
    with tempfile.TemporaryDirectory(prefix="gs-dupe-") as tmp:
        path = _write(Path(tmp), "x,x,y,signal\n0,1,0,10\n1,2,1,11\n")
        try:
            GenericCSVAdapter().read(path)
        except ValueError as exc:
            message = str(exc)
            assert "x" in message, f"the error should name the repeated column: {message!r}"
            assert "duplicate" in message.lower(), (
                f"the error should say the column is duplicated: {message!r}"
            )
        else:
            raise AssertionError("a duplicate column name was accepted")


def test_headers_colliding_after_normalization_are_rejected():
    """Case/whitespace variants of one name are the same collision.

    ``X`` and ``x`` normalize to the same lookup key, so a file that passes a
    literal-duplicate check can still lose a column to a silent overwrite.
    """
    with tempfile.TemporaryDirectory(prefix="gs-dupe-") as tmp:
        path = _write(Path(tmp), "x,X,y,signal\n0,1,0,10\n1,2,1,11\n")
        try:
            GenericCSVAdapter().read(path)
        except ValueError as exc:
            assert "duplicate" in str(exc).lower(), str(exc)
        else:
            raise AssertionError("headers colliding after normalization were accepted")


def test_distinct_headers_still_load():
    """The guard must not reject a legitimate multi-measurement export.

    Several adapters legitimately carry repeated channel names distinguished by
    a suffix, so this pins that ordinary distinct headers are untouched.
    """
    with tempfile.TemporaryDirectory(prefix="gs-ok-") as tmp:
        path = _write(Path(tmp), "x,y,signal,depth\n0,0,10,1.5\n1,1,11,1.6\n")
        scan = GenericCSVAdapter().read(path)
        assert len(scan.signal) == 2


# --------------------------------------------------------------------------
# fusion: single-observation consistency
# --------------------------------------------------------------------------
def _member(**overrides) -> Candidate:
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
        scan_count=1,
        scale_class="local",
    )
    base.update(overrides)
    return Candidate(**base)


def test_single_observation_relative_dispersion_is_neutral_not_perfect():
    """One value means "not estimable", which is not "identical".

    ``_robust_relative_dispersion`` returned 0.0 for fewer than two values, and
    its consumer converts that to ``size_consistency = 1.0`` -- a fused
    candidate built from a single observation reported perfect size
    consistency.
    """
    value = _robust_relative_dispersion([4.0])
    assert math.isclose(value, 0.5, rel_tol=1e-9), (
        f"single-observation relative dispersion reported {value}, expected the "
        f"neutral 0.5 (0.0 reads as 'perfectly consistent')"
    )


def test_single_member_fusion_reports_neutral_size_consistency():
    """The derived consistency must be neutral, not perfect, for one member."""
    fused = fuse_geometry([_member()])
    assert math.isclose(fused.geometry_size_consistency, 0.5, rel_tol=1e-9), (
        f"a single-member fusion reported size consistency "
        f"{fused.geometry_size_consistency}, expected the neutral 0.5"
    )
    assert fused.measurement_count == 1


def test_multi_member_fusion_still_measures_real_dispersion():
    """The neutral must not leak into the genuinely-measured case."""
    identical = fuse_geometry([_member(), _member(id=2)])
    assert math.isclose(identical.geometry_size_consistency, 1.0, rel_tol=1e-6), (
        f"two identical members should report full size consistency, got "
        f"{identical.geometry_size_consistency}"
    )

    spread = fuse_geometry([_member(), _member(id=2, major_extent=8.0, minor_extent=2.0)])
    assert spread.geometry_size_consistency < 1.0, (
        f"two disagreeing members reported perfect size consistency "
        f"({spread.geometry_size_consistency})"
    )


# --------------------------------------------------------------------------
# rescue: policy knobs must be reachable
# --------------------------------------------------------------------------
def test_rescue_uses_policy_threshold_when_caller_defers():
    """``policy.threshold`` must be reachable, or the field is a dead knob.

    The signature defaulted ``threshold`` to 3.0 while the body read
    ``policy.threshold if threshold is None else threshold``. The ``None``
    branch could never be taken, so the policy field was unreachable and the
    three knobs silently did nothing.
    """
    from groundscan.core.rescue import (
        ExtractionRescuePolicy,
        propose_conservative_geology_rescues,
    )

    calls: list[dict] = []
    import groundscan.core.rescue as rescue_module

    real = rescue_module.detect_anomalies

    def spy(grid, **kwargs):
        calls.append(kwargs)
        # A benign empty result keeps the rest of the function inert.
        return real(grid, **kwargs)

    rescue_module.detect_anomalies = spy
    try:
        policy = ExtractionRescuePolicy(
            mode="conservative-geology", threshold=7.5, min_size=4, scales=(5, 9)
        )
        empty = _empty_grid()
        propose_conservative_geology_rescues(
            empty,
            [],
            threshold=None,
            min_size=None,
            scales=None,
            coords_are_index_only=False,
            policy=policy,
        )
    finally:
        rescue_module.detect_anomalies = real

    assert calls, "detect_anomalies was never reached"
    assert calls[0]["threshold"] == 7.5, (
        f"policy.threshold=7.5 was ignored; detect_anomalies got threshold={calls[0]['threshold']}"
    )
    assert calls[0]["min_size"] == 4, (
        f"policy.min_size=4 was ignored; got min_size={calls[0]['min_size']}"
    )
    assert tuple(calls[0]["scales"]) == (5, 9), (
        f"policy.scales=(5, 9) was ignored; got scales={calls[0]['scales']}"
    )


def test_rescue_defaults_match_the_policy_defaults():
    """Deferring to the policy must not silently change today's behaviour."""
    import inspect

    from groundscan.core.rescue import propose_conservative_geology_rescues

    signature = inspect.signature(propose_conservative_geology_rescues)
    for name in ("threshold", "min_size", "scales"):
        assert signature.parameters[name].default is None, (
            f"{name} still defaults to {signature.parameters[name].default!r}, so "
            f"the policy value can never be reached"
        )


def _empty_grid() -> Grid2D:
    axis = np.arange(12, dtype=float)
    return Grid2D(
        x_centers=axis,
        y_centers=axis.copy(),
        signal=np.zeros((12, 12)),
        depth=np.ones((12, 12)),
        counts=np.ones((12, 12), dtype=int),
    )

"""Shadow comparison for S03: the candidate scale against production, on real inputs.

The reference table in :mod:`groundscan.validation.scale_reference` says what a
scale estimator *should* do on constructed populations. This module answers the
second, separate question: what does changing it do to a real analysis?

## Why this is not a diff

"Production changed" is not a finding. A scale difference can mean the estimator
got better, that the data was already in a regime nobody modelled, or that a
threshold happened to be crossed. Those are three different things and only one
of them is a reason to accept a change.

So every record here carries the **regime** as well as the numbers. The regime
is computed independently, from the reference module's own definitions, and it
is the thing that makes a difference interpretable: a difference in the ``mad``
regime is a bug, a difference in the ``degenerate`` regime is a disclosed
consequence of a disclosed trade-off, and a difference with no regime change is
nothing at all.

## What is deliberately *not* here

* No vendor label is used as an oracle. The vendor truth table says what the
  field notes claim; the synthetic constructions say what was put in. Where the
  two disagree the record says so rather than picking a winner.
* No threshold is touched. Every "downstream" number is what the pipeline
  already computes at its existing settings, so a change in a candidate count is
  a change in *the scale*, not in a band.
* ``golden = regression reference``. Nothing in this module writes one.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .._util import robust_scale_with_status as _production_status_estimate
from . import scale_reference as ref

#: Regime names. ``mad`` and ``iqr`` are the tiers the shipped ladder already
#: has; ``degenerate`` is the tier with no defensible finite answer; ``low_sample``
#: is the tier where a number can exist but n cannot support it; ``unavailable``
#: is "fewer than two finite values", where no dispersion is defined at all.
REGIME_MAD = "mad"
REGIME_IQR = "iqr"
REGIME_DEGENERATE = "degenerate"
REGIME_LOW_SAMPLE = "low_sample"
REGIME_UNAVAILABLE = "unavailable"

#: Below this many finite values no dispersion estimate is interpretable. Two
#: points give a range, not a spread: there is exactly one number the sample
#: contains, and every "scale" derived from it is a function of that one number
#: rather than a property of a population. Three is the smallest count at which
#: a *robust* estimator is even defined -- MAD of two values is a range, and the
#: third point is what makes it a dispersion.
MIN_SCALE_SAMPLES = 3


def finite_extent(values: np.ndarray[Any, Any]) -> float:
    """Largest absolute deviation from the median, over the finite values.

    This is the denominator of the scale-free degeneracy test. Using the extent
    rather than the spread is deliberate: it is positively homogeneous *and*
    translation invariant, so a test built on it inherits both properties, and
    those two are exactly what the legacy absolute tolerance (``mad > 1e-9``)
    destroys.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    return float(np.max(np.abs(v - float(np.median(v)))))


def finite_mad(values: np.ndarray[Any, Any]) -> float:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    return float(np.median(np.abs(v - float(np.median(v)))))


def finite_iqr(values: np.ndarray[Any, Any]) -> float:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    q25, q75 = np.percentile(v, [25.0, 75.0])
    return float(q75 - q25)


def finite_std(values: np.ndarray[Any, Any]) -> float:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    return float(np.std(v))


#: The scale-free degeneracy tolerance. Its value is a *round-off* allowance and
#: not a calibration: below this fraction of the sample's own extent a MAD is
#: indistinguishable from the accumulation of double-precision error through a
#: median filter. Measured over the whole corpus the smallest non-zero
#: ``mad / extent`` is 0.01, so this sits seven orders of magnitude clear of any
#: real decision and changes none of them.
DEGENERACY_TOLERANCE = 1e-9


def residual_regime(values: np.ndarray[Any, Any]) -> tuple[str, dict[str, float]]:
    """Classify a residual into an estimator regime, from the definitions only.

    Independent of production on purpose: this is the instrument, and an
    instrument that reads the thing it measures cannot disagree with it.
    """
    v = np.asarray(values, dtype=float)
    finite = v[np.isfinite(v)]
    n = int(finite.size)
    extent = finite_extent(finite)
    mad = finite_mad(finite)
    iqr = finite_iqr(finite)
    std = finite_std(finite)
    scale_free = DEGENERACY_TOLERANCE * extent
    stats = {
        "n": float(n),
        "extent": extent,
        "mad": mad,
        "iqr": iqr,
        "std": std,
        "degeneracy_tolerance": scale_free,
    }
    if n < 2:
        return REGIME_UNAVAILABLE, stats
    if n < MIN_SCALE_SAMPLES:
        return REGIME_LOW_SAMPLE, stats
    if mad > scale_free:
        return REGIME_MAD, stats
    if iqr > scale_free:
        return REGIME_IQR, stats
    if std > scale_free:
        return REGIME_DEGENERATE, stats
    return REGIME_UNAVAILABLE, stats


# ---------------------------------------------------------------------------
# Per-residual comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidualComparison:
    """One residual's legacy scale, candidate scale, regime and references."""

    source: str
    channel: str
    regime: str
    n_finite: int
    extent: float
    legacy_scale: float
    legacy_status: str
    legacy_method: str
    candidate_scale: float
    candidate_status: str
    candidate_method: str
    references: dict[str, float]
    quantisation_step: float | None
    contamination_flag: bool
    contamination_influence: float
    mad: float
    iqr: float
    std: float
    degeneracy_tolerance: float

    @property
    def scale_changed(self) -> bool:
        if not (math.isfinite(self.legacy_scale) and math.isfinite(self.candidate_scale)):
            return self.legacy_scale != self.candidate_scale
        return abs(self.candidate_scale - self.legacy_scale) > 1e-12 * max(
            abs(self.legacy_scale), 1e-300
        )

    @property
    def ratio_candidate_over_legacy(self) -> float:
        if not (math.isfinite(self.legacy_scale) and math.isfinite(self.candidate_scale)):
            return float("nan")
        if self.legacy_scale == 0.0:
            return float("nan")
        return self.candidate_scale / self.legacy_scale

    def to_dict(self) -> dict[str, Any]:
        ratio = self.ratio_candidate_over_legacy
        return {
            "source": self.source,
            "channel": self.channel,
            "regime": self.regime,
            "n_finite": self.n_finite,
            "extent": self.extent,
            "mad": self.mad,
            "iqr": self.iqr,
            "std": self.std,
            "degeneracy_tolerance": self.degeneracy_tolerance,
            "legacy_scale": self.legacy_scale,
            "legacy_status": self.legacy_status,
            "legacy_method": self.legacy_method,
            "candidate_scale": self.candidate_scale,
            "candidate_status": self.candidate_status,
            "candidate_method": self.candidate_method,
            "scale_changed": self.scale_changed,
            "ratio_candidate_over_legacy": None if ratio != ratio else ratio,
            "contamination_flag": self.contamination_flag,
            "contamination_influence": self.contamination_influence,
            "quantisation_step": self.quantisation_step,
            "references": {k: (None if v != v else v) for k, v in self.references.items()},
        }


def compare_residual(
    residual: np.ndarray[Any, Any],
    *,
    source: str = "<inline>",
    channel: str = "residual",
) -> ResidualComparison | None:
    """Pre-activation beside activated beside every reference, for one residual.

    ``contamination_influence`` is the number that says *how much of the reported
    scale is contamination*. It is the ratio of the reported scale to the
    strongest high-breakdown estimate the same sample supports, and it is what
    makes a ``degraded`` status actionable rather than merely honest: at 1.0 the
    reported scale is entirely the clean population's, and at 10 it is ten times
    the clean spread and a reader has been told so.
    """
    arr = np.asarray(residual, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return None
    regime, _stats = residual_regime(finite)
    shipped = shipped_status_estimate(finite)
    candidate = candidate_estimate(finite)
    references = {
        name: float(ref.REFERENCE_ESTIMATORS[name](finite)) for name in ref.SCALE_ESTIMATORS
    }
    extent = finite_extent(finite)
    gate = DEGENERACY_TOLERANCE * extent
    robust_reference = 0.0
    for name in ("mad", "iqr", "absdev_q75"):
        value = references.get(name, float("nan"))
        if value == value and value > gate:
            robust_reference = value
            break
    influence = (
        float(candidate.scale / robust_reference)
        if math.isfinite(candidate.scale) and robust_reference > 0.0
        else float("nan")
    )
    return ResidualComparison(
        source=source,
        channel=channel,
        regime=regime,
        n_finite=int(finite.size),
        extent=extent,
        legacy_scale=float(shipped.legacy_scale),
        legacy_status=shipped.status,
        legacy_method=shipped.method,
        candidate_scale=float(candidate.scale),
        candidate_status=candidate.status,
        candidate_method=candidate.method,
        references=references,
        quantisation_step=candidate.quantisation_step,
        contamination_flag=bool(candidate.contamination_flag),
        contamination_influence=influence,
        mad=finite_mad(finite),
        iqr=finite_iqr(finite),
        std=finite_std(finite),
        degeneracy_tolerance=gate,
    )


# ---------------------------------------------------------------------------
# The candidate estimator, described once and reused everywhere
# ---------------------------------------------------------------------------
# Imported lazily from ``_util`` so the shadow and the production path are the
# *same* function -- this is a comparison of a candidate against the shipped
# number, not a second implementation. The independent reference for "is the
# candidate right?" lives in :mod:`scale_reference` and never sees this.


def candidate_estimate(values: Any) -> Any:
    """The activated estimator, which is production itself.

    After Stage 3 there is no separate "candidate": the defended implementation
    *is* the production path, so the oracle-versus-production cross-check that
    S02 established has an S03 analogue -- the shadow compares the shipped
    behaviour against a verbatim copy of the pre-activation behaviour, and the
    production function is what the corpus runs.

    The production function is bound at import rather than looked up per call,
    because :func:`_patched_scale` rebinds that name: a late lookup here would
    recurse into whatever the swap installed.
    """
    return _production_status_estimate(values)


#: Alias with the name the call sites use, so the swap reads as a swap of
#: estimators rather than of numbers.
candidate_status_estimate = candidate_estimate


def shipped_status_estimate(values: Any) -> Any:
    """The **pre-activation** estimator, verbatim.

    This is the S02 baseline, copied rather than imported so the comparison
    cannot drift with the code under test. Three things it does that the
    activated one does not: it tests degeneracy against an *absolute* ``1e-9``
    (so a dispersion of 4e-10 is treated as no dispersion), it fabricates
    ``1.0`` for a population with no estimable spread, and it has no
    ``low_sample`` state. Everything else -- the MAD / IQR / std ladder, the
    winsorised floor and its fraction -- is reproduced exactly, because those
    rungs are not what changed.
    """
    from .._util import (
        CONTAMINATION_FRACTION,
        CONTAMINATION_SIGMAS,
        LEGACY_SCALE_FALLBACK,
        SCALE_STATUS_DEGRADED,
        SCALE_STATUS_INDETERMINATE,
        SCALE_STATUS_VALID,
        ScaleEstimate,
        _quantisation_step,
    )

    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]
    if valid.size < 2:
        return ScaleEstimate(
            scale=float("nan"),
            status=SCALE_STATUS_INDETERMINATE,
            method="none",
            contamination_flag=False,
            quantisation_step=None,
            n_effective=int(valid.size),
            legacy_scale=LEGACY_SCALE_FALLBACK,
        )
    med = float(np.median(valid))
    mad = float(np.median(np.abs(valid - med)))
    std = float(np.std(valid))
    if mad > 1e-9:
        scale, method, status = 1.4826 * mad, "mad", SCALE_STATUS_VALID
    else:
        q25, q75 = np.percentile(valid, [25, 75])
        iqr_scale = float(q75 - q25) / 1.349
        if iqr_scale > 1e-9:  # noqa: SIM108 — verbatim shape of the audited original
            scale, method, status = iqr_scale, "iqr", SCALE_STATUS_VALID
        elif std > 1e-9:
            scale, method, status = std, "std", SCALE_STATUS_DEGRADED
        else:
            scale, method, status = LEGACY_SCALE_FALLBACK, "none", SCALE_STATUS_INDETERMINATE
    band = 5.0 * scale
    floor_std = float(np.std(np.clip(valid, med - band, med + band))) if band > 0.0 else 0.0
    floored = max(scale, 0.05 * floor_std)
    outliers = (
        np.abs(valid - med) > CONTAMINATION_SIGMAS * scale
        if np.isfinite(scale) and scale > 0.0
        else np.zeros(valid.shape, dtype=bool)
    )
    return ScaleEstimate(
        scale=float("nan") if status == SCALE_STATUS_INDETERMINATE else float(floored),
        status=status,
        method=method,
        contamination_flag=bool(float(np.mean(outliers)) > CONTAMINATION_FRACTION),
        quantisation_step=_quantisation_step(valid),
        n_effective=int(valid.size),
        legacy_scale=float(floored),
    )


# ---------------------------------------------------------------------------
# Downstream impact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScaleImpact:
    """What a different scale did to one run's findings.

    Recorded per *finding* keyed by nothing more stable than its index, because
    the finding set itself may change size; the counts are the primary datum and
    the per-finding rows are the explanation.
    """

    candidate_count_legacy: int
    candidate_count_candidate: int
    peak_abs_z_legacy: float
    peak_abs_z_candidate: float
    hypothesis_changes: tuple[tuple[int, str, str], ...] = ()
    label_changes: tuple[tuple[str, int, str, str], ...] = ()
    field_deltas: tuple[tuple[str, float], ...] = ()

    @property
    def count_delta(self) -> int:
        return self.candidate_count_candidate - self.candidate_count_legacy

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count_legacy": self.candidate_count_legacy,
            "candidate_count_candidate": self.candidate_count_candidate,
            "count_delta": self.count_delta,
            "peak_abs_z_legacy": self.peak_abs_z_legacy,
            "peak_abs_z_candidate": self.peak_abs_z_candidate,
            "hypothesis_changes": [
                {"index": i, "legacy": a, "candidate": b} for i, a, b in self.hypothesis_changes
            ],
            "label_changes": [
                {"field": f, "index": i, "legacy": a, "candidate": b}
                for f, i, a, b in self.label_changes
            ],
            "field_deltas": [{"field": f, "delta": d} for f, d in self.field_deltas],
        }


#: The numeric candidate fields a scale change can move. ``evidence_score`` /
#: ``quality_score`` / ``screening_score`` are the three the task names
#: explicitly, so they are listed rather than folded into an "other".
WATCHED_CANDIDATE_FIELDS: tuple[str, ...] = (
    "confidence",
    "evidence_score",
    "selected_hypothesis_margin",
    "quality_score",
    "screening_score",
    "false_positive_risk",
    "max_abs_z",
    "anomaly_area_cells",
    "solidity",
    "geometry_quality",
)

#: The categorical ones, tracked separately because a label flip is a
#: categorically bigger event than a float drifting: it is what a reader of the
#: report actually notices.
WATCHED_CANDIDATE_LABELS: tuple[str, ...] = (
    "pattern_hypothesis",
    "second_hypothesis",
    "review_status",
    "shape_class",
    "response_family",
    "evidence_band",
)


@contextmanager
def _patched_scale(status_fn: Callable[[Any], Any]) -> Iterator[None]:
    """Swap the scale estimation for the duration of a run, on *every* binding.

    Two bindings reach the estimator and patching only one would silently
    measure a half-changed pipeline:

    * ``core.background.robust_zscore`` holds a module-level reference to
      ``_util.robust_scale_with_status`` (Stage 3 made it read the status so the
      indeterminate state cannot reach a threshold);
    * ``core.anomaly`` calls the ``core.background.robust_scale`` wrapper, which
      late-imports ``_util.robust_scale`` inside its body.

    Both are rebound, and the function under test is installed through both, so
    a caller added later cannot be missed by construction. A test asserts both
    bindings really move, because an incomplete patch is worse than none: it
    looks like a measurement.
    """
    import groundscan._util as util

    from ..core import background as background_mod

    originals = (
        util.robust_scale,
        util.robust_scale_with_status,
        background_mod.__dict__["robust_scale_with_status"],
    )

    def _number(values: Any) -> float:
        return float(status_fn(values).legacy_scale)

    util.robust_scale = _number
    # The three rebinds below are deliberately through ``__dict__`` and a
    # module-level alias rather than attribute assignment. Each name is a
    # *re-export* of ``_util``'s, not an explicit export of the module that
    # holds it, and a typed assignment there is a lie the checker is right to
    # reject: the swap is a test fixture, and a fixture says so.
    util.__dict__["robust_scale_with_status"] = status_fn
    background_mod.__dict__["robust_scale_with_status"] = status_fn
    try:
        yield
    finally:
        util.robust_scale = originals[0]
        util.__dict__["robust_scale_with_status"] = originals[1]
        background_mod.__dict__["robust_scale_with_status"] = originals[2]


def _peak_abs_z(candidates: Iterable[Any]) -> float:
    values = [float(getattr(c, "max_abs_z", float("nan"))) for c in candidates]
    finite = [v for v in values if math.isfinite(v)]
    return max(finite, default=0.0)


def _max_field_deltas(legacy: list[Any], candidate: list[Any], name: str) -> float:
    worst = 0.0
    for left, right in zip(legacy, candidate, strict=False):
        a, b = float(getattr(left, name, float("nan"))), float(getattr(right, name, float("nan")))
        if math.isfinite(a) and math.isfinite(b):
            worst = max(worst, abs(b - a))
    return worst


def run_with_scale(
    status_fn: Callable[[Any], Any],
    scan: Any,
    out_dir: str | Path,
    label: str,
    config: Any,
) -> list[Any]:
    """One full ``analyze_scan`` with a substituted scale estimator."""
    from ..services.single_scan import analyze_scan

    with _patched_scale(status_fn):
        _grid, _anomaly, candidates = analyze_scan(
            scan, out_dir, label=label, config=config, write_outputs=False
        )
    return candidates


def compare_downstream(
    scan: Any,
    source: str,
    config: Any = None,
    tmp: str | Path | None = None,
) -> ScaleImpact:
    """Run the pipeline twice, once with the shipped scale and once with the candidate.

    Identical inputs, identical configuration, identical seeds; the only
    difference is which function estimates the spread. Anything that moves moved
    because of the scale.
    """
    from ..services.config import AnalysisConfig

    cfg = config if config is not None else AnalysisConfig()
    with tempfile.TemporaryDirectory(dir=tmp) as work:
        legacy = run_with_scale(shipped_status_estimate, scan, Path(work) / "legacy", source, cfg)
        candidate = run_with_scale(
            candidate_status_estimate, scan, Path(work) / "candidate", source, cfg
        )
    hypotheses: list[tuple[int, str, str]] = []
    labels: list[tuple[str, int, str, str]] = []
    for index, (left, right) in enumerate(zip(legacy, candidate, strict=False)):
        for name in WATCHED_CANDIDATE_LABELS:
            a = str(getattr(left, name, "") or "")
            b = str(getattr(right, name, "") or "")
            if a == b:
                continue
            labels.append((name, index, a, b))
            if name == "pattern_hypothesis":
                hypotheses.append((index, a, b))
    deltas = tuple(
        (name, _max_field_deltas(legacy, candidate, name)) for name in WATCHED_CANDIDATE_FIELDS
    )
    return ScaleImpact(
        candidate_count_legacy=len(legacy),
        candidate_count_candidate=len(candidate),
        peak_abs_z_legacy=_peak_abs_z(legacy),
        peak_abs_z_candidate=_peak_abs_z(candidate),
        hypothesis_changes=tuple(hypotheses),
        label_changes=tuple(labels),
        field_deltas=tuple((name, delta) for name, delta in deltas if delta > 0.0),
    )


# ---------------------------------------------------------------------------
# Per-scan and corpus reports
# ---------------------------------------------------------------------------


@dataclass
class ScaleShadowReport:
    """One scan's residuals and downstream impact."""

    source: str
    comparisons: list[ResidualComparison] = field(default_factory=list)
    impact: ScaleImpact | None = None

    def summary(self) -> dict[str, Any]:
        regimes: dict[str, int] = {}
        for record in self.comparisons:
            regimes[record.regime] = regimes.get(record.regime, 0) + 1
        return {
            "source": self.source,
            "residual_count": len(self.comparisons),
            "regimes": dict(sorted(regimes.items())),
            "scale_change_count": sum(1 for r in self.comparisons if r.scale_changed),
            "contaminated_count": sum(1 for r in self.comparisons if r.contamination_flag),
            "max_contamination_influence": max(
                (
                    r.contamination_influence
                    for r in self.comparisons
                    if math.isfinite(r.contamination_influence)
                ),
                default=0.0,
            ),
            "impact": self.impact.to_dict() if self.impact is not None else None,
        }


def _channel_residuals(
    grid: Any, scales: tuple[int, ...] = (3, 5, 9, 15)
) -> list[tuple[str, np.ndarray[Any, Any]]]:
    """Every residual that reaches the scale estimator, named by its channel.

    The multiscale backgrounds and the broad channel's two fields are taken from
    the *same functions the pipeline calls* -- ``remove_background``,
    ``_detrended_residual`` and ``_largest_odd_scale`` -- rather than from a
    parallel reimplementation, so a channel that disappears or changes shape
    shows up here as a changed or missing row instead of silently diverging.
    """
    from scipy import ndimage

    from ..core.anomaly import _detrended_residual, _largest_odd_scale
    from ..core.background import remove_background

    out: list[tuple[str, np.ndarray[Any, Any]]] = []
    shape = grid.signal.shape
    viable = False
    for size in scales:
        if min(shape) < size:
            continue
        viable = True
        out.append((f"multiscale_median_{size}", remove_background(grid, "median", size)))
    if not viable:
        out.append(("multiscale_none", remove_background(grid, "none")))
    broad_scale = _largest_odd_scale(scales, shape)
    if broad_scale is not None:
        detrended, valid = _detrended_residual(grid)
        if np.any(valid):
            fill = float(np.nanmedian(detrended[valid]))
            sigma = float(np.clip(min(shape) * 0.055, 1.5, 4.0))
            smoothed = ndimage.gaussian_filter(
                np.nan_to_num(detrended, nan=fill), sigma=sigma, mode="nearest"
            )
            out.append(("broad_smoothed_detrended", smoothed))
            out.append(("broad_detrended_support", detrended))
    return out


def compare_scan(
    scan: Any,
    source: str,
    config: Any = None,
    *,
    downstream: bool = True,
) -> ScaleShadowReport:
    """Residual-by-residual comparison for one scan, plus the downstream delta."""
    from ..core.grid import reconstruct_grid

    report = ScaleShadowReport(source=source)
    try:
        grid = reconstruct_grid(scan)
    except Exception as error:  # a scan the grid cannot reconstruct has no scale
        report.impact = ScaleImpact(0, 0, float("nan"), float("nan"))
        report.comparisons.append(
            ResidualComparison(
                source=source,
                channel="grid",
                regime=REGIME_UNAVAILABLE,
                n_finite=0,
                extent=0.0,
                legacy_scale=float("nan"),
                legacy_status="unavailable",
                legacy_method="none",
                candidate_scale=float("nan"),
                candidate_status="unavailable",
                candidate_method="none",
                references={},
                quantisation_step=None,
                contamination_flag=False,
                contamination_influence=float("nan"),
                mad=0.0,
                iqr=0.0,
                std=0.0,
                degeneracy_tolerance=0.0,
            )
        )
        del error
        return report
    for channel, residual in _channel_residuals(grid):
        record = compare_residual(residual, source=source, channel=channel)
        if record is not None:
            report.comparisons.append(record)
    if downstream:
        report.impact = compare_downstream(scan, source=source, config=config)
    return report


#: Every regime name, so a census reports its zeros. A regime that never occurs
#: is a *count of zero*, and a dictionary that simply lacks the key cannot
#: distinguish "never happened" from "not looked for" -- which is the difference
#: between a census and a sample of the interesting parts.
ALL_REGIMES: tuple[str, ...] = (
    REGIME_MAD,
    REGIME_IQR,
    REGIME_DEGENERATE,
    REGIME_LOW_SAMPLE,
    REGIME_UNAVAILABLE,
)


def residual_census(reports: Iterable[ScaleShadowReport]) -> ref.RegimeCensus:
    """The Phase D input: how many residuals sit in each regime, per source."""
    census = ref.RegimeCensus(counts={name: 0 for name in ALL_REGIMES})
    for report in reports:
        per_source: dict[str, int] = {name: 0 for name in ALL_REGIMES}
        for record in report.comparisons:
            census.counts[record.regime] = census.counts.get(record.regime, 0) + 1
            per_source[record.regime] = per_source.get(record.regime, 0) + 1
        census.sources[report.source] = per_source
    return census


# ---------------------------------------------------------------------------
# Corpus generators -- the same corpora the solidity shadow uses
# ---------------------------------------------------------------------------


def synthetic_reports(*, downstream: bool = False) -> Iterator[ScaleShadowReport]:
    from .synthetic_core.core import generate_scan, scenario_catalog

    for scenario in scenario_catalog():
        scan, _truth = generate_scan(scenario)
        yield compare_scan(scan, source=f"synthetic:{scenario.name}", downstream=downstream)


def vendor_reports(*, downstream: bool = False) -> Iterator[ScaleShadowReport]:
    from ..services.single_scan import load_scan
    from .fixtures import VENDOR_ROOT

    for group in ("train", "validation"):
        for path in sorted((VENDOR_ROOT / group).glob("*.csv")):
            yield compare_scan(
                load_scan(path), source=f"vendor:{group}/{path.name}", downstream=downstream
            )


def golden_reports(tmp: str | Path, *, downstream: bool = True) -> Iterator[ScaleShadowReport]:
    """The goldens' own inputs, so the census covers what the gate covers."""
    from ..services.config import AnalysisConfig
    from ..services.single_scan import load_scan
    from .fixtures import VENDOR_ROOT as ORIG_VENDOR_ROOT
    from .golden import GOLDEN_SYNTHETIC_SINGLE, GOLDEN_VENDOR_CASES
    from .synthetic_core.core import SyntheticScenario, SyntheticTarget, generate_scan

    config = AnalysisConfig()
    for kind, seed in GOLDEN_SYNTHETIC_SINGLE:
        target = SyntheticTarget(kind=kind, x=10.0, y=10.0, depth=2.0, amplitude=12.0)
        scenario = SyntheticScenario(
            name=f"golden_{kind}",
            width_m=20.0,
            height_m=20.0,
            nx=40,
            ny=40,
            targets=(target,),
            noise_sigma=0.5,
            seed=seed,
        )
        scan, _ = generate_scan(scenario)
        yield compare_scan(
            scan, source=f"golden:synth_{kind}", config=config, downstream=downstream
        )
    for case_id, (subdir, fname) in GOLDEN_VENDOR_CASES.items():
        yield compare_scan(
            load_scan(ORIG_VENDOR_ROOT / subdir / fname),
            source=f"golden:{case_id}",
            config=config,
            downstream=downstream,
        )


def aggregate(reports: Iterable[ScaleShadowReport]) -> dict[str, Any]:
    """The activation-gate census: regimes, changes, and downstream deltas."""
    reports = list(reports)
    residuals = [r for report in reports for r in report.comparisons]
    census = residual_census(reports)
    impacts = [r.impact for r in reports if r.impact is not None]
    return {
        "input_count": len(reports),
        "residual_count": len(residuals),
        "regime_census": census.to_dict(),
        "scale_change_count": sum(1 for r in residuals if r.scale_changed),
        "changes_by_regime": {
            regime: sum(1 for r in residuals if r.regime == regime and r.scale_changed)
            for regime in sorted({r.regime for r in residuals})
        },
        "status_changes": [r.to_dict() for r in residuals if r.legacy_status != r.candidate_status],
        "contaminated_residuals": sum(1 for r in residuals if r.contamination_flag),
        "max_contamination_influence": max(
            (
                r.contamination_influence
                for r in residuals
                if math.isfinite(r.contamination_influence)
            ),
            default=0.0,
        ),
        "degenerate_residuals": [r.to_dict() for r in residuals if r.regime == REGIME_DEGENERATE],
        "downstream": {
            "runs_compared": len(impacts),
            "candidate_count_changes": sum(1 for i in impacts if i.count_delta != 0),
            "total_count_delta": sum(i.count_delta for i in impacts),
            "hypothesis_changes": [
                {"source": report.source, **change}
                for report in reports
                if report.impact is not None
                for change in (
                    {"index": i, "legacy": a, "candidate": b}
                    for i, a, b in report.impact.hypothesis_changes
                )
            ],
            "label_changes": [
                {"source": report.source, "field": f, "index": i, "legacy": a, "candidate": b}
                for report in reports
                if report.impact is not None
                for f, i, a, b in report.impact.label_changes
            ],
            "max_field_delta": {
                name: max(
                    (
                        dict(report.impact.field_deltas).get(name, 0.0)
                        for report in reports
                        if report.impact is not None
                    ),
                    default=0.0,
                )
                for name in WATCHED_CANDIDATE_FIELDS
            },
            "runs_with_any_numeric_delta": sum(
                1 for report in reports if report.impact is not None and report.impact.field_deltas
            ),
        },
        "by_source": {report.source: report.summary() for report in reports},
    }


def full_census(tmp: str | Path | None = None) -> dict[str, Any]:
    """Run the whole corpus: synthetic catalog, all nine vendor scans, goldens."""
    with tempfile.TemporaryDirectory(dir=tmp) as work:
        reports = [
            *synthetic_reports(),
            *vendor_reports(),
            *golden_reports(Path(work)),
        ]
    return aggregate(reports)


__all__ = [
    "ALL_REGIMES",
    "DEGENERACY_TOLERANCE",
    "MIN_SCALE_SAMPLES",
    "REGIME_DEGENERATE",
    "REGIME_IQR",
    "REGIME_LOW_SAMPLE",
    "REGIME_MAD",
    "REGIME_UNAVAILABLE",
    "WATCHED_CANDIDATE_FIELDS",
    "WATCHED_CANDIDATE_LABELS",
    "ResidualComparison",
    "ScaleImpact",
    "ScaleShadowReport",
    "aggregate",
    "candidate_estimate",
    "candidate_status_estimate",
    "compare_downstream",
    "compare_residual",
    "compare_scan",
    "finite_extent",
    "finite_iqr",
    "finite_mad",
    "finite_std",
    "full_census",
    "golden_reports",
    "residual_census",
    "shipped_status_estimate",
    "residual_regime",
    "synthetic_reports",
    "vendor_reports",
]

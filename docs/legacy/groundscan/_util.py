"""Shared numeric helpers (single source of truth).

v0.5.1: canonical implementations for helpers previously copy-pasted across
``core``, ``site``, ``gates`` and ``diagnostics``. Every module imports these
functions directly; there are no per-module aliases or wrappers.

Remediation Design v2 (Wave 0) adds the scale-status architecture here:
``ScaleEstimate`` / ``robust_scale_with_status`` (contract K7). ``robust_scale``
delegates and is bit-identical, so no caller changes yet.

Stage 2 adds the K10 axial-statistics helpers, the K9 ``output_dir`` choke
point, and the S10 artifact-identity quad.

Stage 3 activates S03 (contract K7). The change is deliberately small, and it is
small because the measurements said it should be -- see
``docs/SCIENTIFIC_CONTRACTS.md`` and
``groundscan/validation/scale_reference.py`` for the evidence. Three things
changed and one thing was *not* changed:

1. The degeneracy tests are **scale-free** (``mad > 1e-9 * extent`` instead of
   ``mad > 1e-9``). An absolute tolerance on a quantity that carries physical
   units is not a criterion; it made the estimator neither positively
   homogeneous nor translation invariant, so the same physical field analysed at
   a different amplitude or a different survey origin got a different scale.
2. The terminal state is **honest**: no measurable spread reports
   ``scale = NaN`` with ``status = "indeterminate"`` instead of the fabricated
   constant, and ``n = 2`` reports ``"low_sample"`` rather than pretending a
   range is a dispersion.
3. The degenerate tier gained a **reliability measurement**,
   :attr:`ScaleEstimate.contamination_influence`: how much of the reported scale
   is contamination rather than spread. A ``degraded`` status with that number
   beside it is actionable; without it, it is only honest.
4. **The degenerate tier's estimator is unchanged.** Every alternative was
   measured and none is defensible (documented in the contract's
   "what this document deliberately does not decide"): the 50 %-breakdown
   family reads exactly zero on an atom-heavy residual, which is a measurement
   error in the *suppressing* direction and strictly worse than the breakdown-0
   number it would replace; the higher-alpha quantile family is non-zero but
   moves two of the nine vendor scans, including reinterpreting a
   ``tunnel-like`` response as ``cavity-like`` -- a physical claim changed by a
   fallback, with no independent field evidence to adjudicate it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

#: Resultant length below which a set of axial angles has no mean direction.
#: An exactly-zero resultant only happens for a perfectly isotropic population,
#: which float error never delivers; without this floor the function would
#: report an arbitrary direction for a population that has none.
_AXIAL_RESULTANT_FLOOR = 1e-12

# ---------------------------------------------------------------------------
# Scale estimation semantics (Remediation Design v2 §6.4, contract K7)
# ---------------------------------------------------------------------------
# A scale estimate carries a *status*, because the confirmed S03 defect is not
# "the estimator is the wrong function" -- it is that an unmeasurable quantity
# was reported as a measurement. A constant field genuinely has no estimable
# spread; the historical ``return 1.0`` presented a fabricated constant as a
# measurement. ``robust_scale`` keeps that legacy constant (so existing callers
# and the frozen golden set are untouched) while ``robust_scale_with_status``
# reports ``scale = NaN`` with ``status = "indeterminate"``.
SCALE_STATUS_VALID = "valid"
SCALE_STATUS_DEGRADED = "degraded"
SCALE_STATUS_INDETERMINATE = "indeterminate"
#: Stage 3: the Wave 0 vocabulary could not express "a number exists, and n
#: cannot support it". Two points give a *range*, not a dispersion -- there is
#: exactly one number the sample contains, and any scale derived from it is a
#: function of that number rather than a property of a population. This is the
#: only status added, because the other distinctions the brief lists are already
#: carried: ``contamination_flag`` is "contaminated", ``quantisation_step`` and
#: ``n_effective`` are "non-finite input", and ``indeterminate`` is
#: "unavailable". Adding parallel spellings of things the record already
#: reports would be two sources of truth for one fact.
SCALE_STATUS_LOW_SAMPLE = "low_sample"

#: The constant the historical ``robust_scale`` returned for an unmeasurable
#: residual. Preserved verbatim so the delegation below is bit-identical; it is
#: a fallback, never a measurement (see ``ScaleEstimate.legacy_scale``).
LEGACY_SCALE_FALLBACK = 1.0

#: Above this many distinct finite values a field is not treated as a small
#: quantisation lattice. Kept a named constant so the boundary is greppable and
#: calibratable rather than buried in the detector.
QUANTISATION_MAX_LEVELS = 64

#: A field counts as contaminated when more than this fraction of its finite
#: values sit beyond ``CONTAMINATION_SIGMAS`` robust sigmas of the median.
CONTAMINATION_SIGMAS = 4.0
CONTAMINATION_FRACTION = 0.05

#: Below this many finite values no dispersion estimate is interpretable. Two
#: points give a range, not a spread. Three is the smallest count at which a
#: *robust* dispersion is even defined: the MAD of two values is their range.
SCALE_MIN_SAMPLES = 3

#: The degeneracy tolerance, as a fraction of the sample's own extent.
#:
#: This replaces the historical absolute test ``mad > 1e-9``. The replacement is
#: not cosmetic and it is not a tuned number:
#:
#: * an absolute tolerance on a length-bearing quantity is a *unit* assumption
#:   hidden in a comparison. The same residual expressed in centimetres rather
#:   than metres, or at a survey origin 1e6 m away, crossed the absolute test at
#:   a different physical state than before -- so the estimator was neither
#:   positively homogeneous nor translation invariant, and the z-score it
#:   produced depended on the unit the file happened to be written in;
#: * against the sample's own extent the same number is a *round-off* allowance,
#:   which is what it was always for: accumulated double-precision error through
#:   a median filter. Measured over the whole corpus (149 residuals), the
#:   smallest non-zero ``mad / extent`` is 0.01, so 1e-9 sits seven orders of
#:   magnitude clear of every real decision and changes none of them -- measured
#:   end to end over 27 scans, the scale-free gate alone changes **zero**
#:   outputs.
SCALE_DEGENERACY_TOLERANCE = 1e-9

#: A dispersion below this, **in the residual's own units**, is not a
#: measurement of anything: it is below the resolution of the double-precision
#: arithmetic that differenced the signal in the first place. Measured on
#: constructed fields, a perfectly smooth noise-free field leaves a residual of
#: this order, so the number is the arithmetic's floor and not a scientific
#: threshold.
#:
#: It is declared here and *applied by the caller*
#: (:func:`groundscan.core.background.robust_zscore`), not by the estimator.
#: That relocation is the point, and it is not a threshold change -- the number
#: is the same 1e-9 the estimator used to test against, and it is applied with
#: the same effect. What changed is that the estimator no longer *claims* a
#: scale of 1.0 for a field whose spread is 4e-13, and instead the caller states
#: a policy about the acquisition's resolution.
#:
#: The alternative -- keeping the absolute test inside the estimator -- was
#: measured and rejected: it is what makes the estimator non-homogeneous, and it
#: is indistinguishable between the two cases it has to separate. On a
#: constructed field whose background is analytic (no noise at all) and on the
#: same field with a genuine 8-sigma target added, the absolute guard reports
#: zero findings in *both*; removing it reports the target in both. It cannot
#: tell a real target from pure dust, so it is not a false-finding guard -- it
#: is a switch on absolute amplitude, and whether the product claims to analyse
#: signals that small is an operating-envelope decision for
#: ``docs/thresholds.md``, not a property of a dispersion estimator.
SCALE_DISPERSION_FLOOR = 1e-9


@dataclass(frozen=True)
class ScaleEstimate:
    """A spread estimate that admits when it could not be measured.

    ``scale`` is ``NaN`` whenever ``status`` is ``"indeterminate"``: contract K7
    requires an indeterminate scale to be reported as such rather than replaced
    by a fabricated number. ``legacy_scale`` is the historical
    :func:`robust_scale` value, kept so the old single-number API can delegate
    without changing a single caller.

    ``contamination_influence`` (Stage 3) is ``scale`` divided by the strongest
    *high-breakdown* estimate available on the same sample, or NaN when the
    robust tiers collapse. At 1.0 the reported scale is entirely the clean
    population's spread; at 10 a reader has been told that nine tenths of it is
    contamination. It is what makes a ``degraded`` status usable rather than
    merely truthful, and it is the measured form of "do not trust this channel".
    """

    scale: float
    status: str
    method: str
    contamination_flag: bool
    quantisation_step: float | None
    n_effective: int
    legacy_scale: float
    contamination_influence: float = float("nan")

    @property
    def is_indeterminate(self) -> bool:
        return self.status == SCALE_STATUS_INDETERMINATE

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable form (diagnostics only; never a payload field)."""
        influence = self.contamination_influence
        return {
            "scale": None if self.scale != self.scale else float(self.scale),
            "status": self.status,
            "method": self.method,
            "contamination_flag": bool(self.contamination_flag),
            "quantisation_step": (
                None if self.quantisation_step is None else float(self.quantisation_step)
            ),
            "n_effective": int(self.n_effective),
            "contamination_influence": None if influence != influence else float(influence),
        }


def _quantisation_step(valid: np.ndarray[Any, Any]) -> float | None:
    """Detect an instrument quantisation step, or ``None``.

    The v1 design proposed this "quantisation gap" as a *scale* estimator.
    Measurement refuted that: it returns 0.00026 for a Gaussian sigma=1 field
    and returns the spike amplitude itself for ``{0, ..., 0, 200}`` (v2 §6.3).
    Its correct role is narrower and it is used only here, as *metadata* for the
    status channel: "is this instrument quantised, and at what quantum?".

    A field qualifies when it takes at most :data:`QUANTISATION_MAX_LEVELS`
    distinct values and every one of them is an integer multiple of the
    smallest positive gap between adjacent distinct values.
    """
    if valid.size < 3:
        return None
    unique = np.unique(valid)
    if unique.size < 3 or unique.size > QUANTISATION_MAX_LEVELS:
        return None
    diffs = np.diff(unique)
    positive = diffs[diffs > 1e-12]
    if positive.size == 0:
        return None
    step = float(np.min(positive))
    multiples = unique / step
    # Tolerance scaled to the field's own magnitude: the lattice test is about
    # representable structure, not about exact binary equality.
    tol = 1e-6 * max(1.0, float(np.max(np.abs(unique))))
    if not np.all(np.abs(multiples - np.round(multiples)) * step <= tol):
        return None
    return step


def _contamination_flag(valid: np.ndarray[Any, Any], scale: float, median: float) -> bool:
    """True when a large fraction of the field sits far outside the robust band."""
    if not np.isfinite(scale) or scale <= 0.0:
        return False
    outliers = np.abs(valid - median) > CONTAMINATION_SIGMAS * scale
    return bool(float(np.mean(outliers)) > CONTAMINATION_FRACTION)


def robust_scale_with_status(values: np.ndarray[Any, Any]) -> ScaleEstimate:
    """Spread estimate plus an explicit status (contract K7, activated in Stage 3).

    Escalation ladder (v2 §6.4), with **no fabricated fallback at the end**:

    ===  ====================  ==================  ==========================
    Step Method                Status             Rationale
    ===  ====================  ==================  ==========================
    1    MAD x 1.4826          ``valid``          50% breakdown, normal case
    2    IQR / 1.349           ``valid``          25% breakdown
    3    std                   ``degraded``       not high-breakdown; reached
                                                only when 1 and 2 collapse
    4    indeterminate         ``indeterminate``  no measurable spread
    ===  ====================  ==================  ==========================

    Rungs 1 and 2 additionally report ``low_sample`` when fewer than
    :data:`SCALE_MIN_SAMPLES` finite values survive, because a value derived
    from two or three samples is a function of those samples rather than a
    property of a population. The *value* is unchanged in that case; only the
    status differs, so no consumer of the number can tell the difference and
    every consumer of the status must.

    Steps 1 and 2 test against ``SCALE_DEGENERACY_TOLERANCE * extent`` rather
    than against an absolute constant, which is what makes the estimator
    positively homogeneous and translation invariant. Measured: the two changes
    move zero outputs across 27 scans, because no residual in the corpus has a
    MAD below 1e-9 of its own extent.

    Step 3 is the *documented* compromise of the degenerate regime, not an
    endorsement of the standard deviation. It has breakdown 0, and every
    alternative was measured and rejected:

    * the whole 50 %-breakdown family (MAD, Sn, Qn) returns **exactly zero** on
      an atom-heavy residual, because more than half the population sits on the
      median. That is not honesty, it is a measurement error in the suppressing
      direction: a residual with a demonstrable spread of 0.82 reported as 0
      destroys every detection in it;
    * an alpha-quantile is non-zero there but carries breakdown ``1 - alpha``,
      and measured end to end it moves two of the nine vendor scans -- including
      reinterpreting a ``tunnel-like`` response as ``cavity-like``, which is a
      physical claim changed by a fallback with no independent field evidence to
      adjudicate it;
    * so the regime keeps the consistent-but-unbounded estimate and *discloses*
      it: ``status = "degraded"`` plus
      :attr:`ScaleEstimate.contamination_influence`.

    The one thing that is no longer tolerated is silence about which regime this
    is. Step 4 reports ``scale = NaN`` and ``status = "indeterminate"``; the
    single-number :func:`robust_scale` keeps the historical constant so that no
    existing call site can observe the difference.
    """
    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]
    n_effective = int(valid.size)
    quantisation = _quantisation_step(valid)
    if n_effective < 2:
        return ScaleEstimate(
            scale=float("nan"),
            status=SCALE_STATUS_INDETERMINATE,
            method="none",
            contamination_flag=False,
            quantisation_step=quantisation,
            n_effective=n_effective,
            legacy_scale=LEGACY_SCALE_FALLBACK,
        )
    med = float(np.median(valid))
    mad = float(np.median(np.abs(valid - med)))
    std = float(np.std(valid))
    extent = float(np.max(np.abs(valid - med)))
    gate = SCALE_DEGENERACY_TOLERANCE * extent
    low_sample = n_effective < SCALE_MIN_SAMPLES

    # The strongest high-breakdown estimate the sample supports, for the
    # influence disclosure. Recorded whether or not the ladder reaches for it.
    robust_reference = 1.4826 * mad if mad > gate else float("nan")

    if mad > gate:
        scale, method, status = 1.4826 * mad, "mad", SCALE_STATUS_VALID
    else:
        q25, q75 = np.percentile(valid, [25, 75])
        iqr_scale = float(q75 - q25) / 1.349
        if iqr_scale > gate:  # noqa: SIM108 — explicit branches mirror the audited original
            scale, method, status = iqr_scale, "iqr", SCALE_STATUS_VALID
            if robust_reference != robust_reference:
                robust_reference = iqr_scale
        elif std > gate:
            scale, method, status = std, "std", SCALE_STATUS_DEGRADED
        else:
            # No measurable spread. ``base`` keeps the legacy constant so the
            # floor below reproduces today's return value exactly; ``scale`` is
            # reported as NaN because no spread was measured.
            scale, method, status = LEGACY_SCALE_FALLBACK, "none", SCALE_STATUS_INDETERMINATE
    if low_sample and status == SCALE_STATUS_VALID:
        status = SCALE_STATUS_LOW_SAMPLE
    influence = (
        float(scale / robust_reference)
        if np.isfinite(robust_reference) and robust_reference > 0.0
        else float("nan")
    )
    return ScaleEstimate(
        scale=float("nan") if status == SCALE_STATUS_INDETERMINATE else float(scale),
        status=status,
        method=method,
        contamination_flag=_contamination_flag(valid, scale, med),
        quantisation_step=quantisation,
        n_effective=n_effective,
        legacy_scale=float(scale),
        contamination_influence=influence,
    )


def robust_scale(values: np.ndarray[Any, Any]) -> float:
    """MAD -> IQR -> std spread estimate (no floor; audit F-01, resolved).

    This used to carry a ``max(scale, 5% * std)`` floor "so the estimate cannot
    collapse on a near-degenerate residual". The floor was removed because it
    provably could not do that job, which the mutation ratchet surfaced as an
    unkillable mutant (``robust-scale-floor-removed``) and then as dead code.

    The floor's own input was a *winsorized* standard deviation -- the spread
    of the values inside a band of five robust sigmas around the median. Every
    winsorized value therefore lies in ``[med - 5*scale, med + 5*scale]``, and
    by Popoviciu's inequality a variable supported on an interval of half-width
    ``h`` has standard deviation at most ``h``. So ``floor_std <= 5 * scale``
    for *every* input, hence ``0.05 * floor_std <= 0.25 * scale < scale``, hence
    ``max(scale, 0.05 * floor_std) == scale`` identically. It was a no-op that
    read as a safety net.

    The degenerate case it was meant to protect is already covered by rung 3
    (the standard deviation), which is the branch a collapsing MAD *and* IQR
    actually reaches. The historical bug it was introduced to fix is real and
    is fixed by the ladder itself rather than by a floor: with the *raw* std as
    the floor's input, a mostly quiet residual with a 1e5 spike pushed the
    3-sigma threshold above every genuine anomaly (scale 0.10 -> 79, three real
    3.0-valued anomalies dropped). Rungs 1 and 2 are high-breakdown, so they
    never take that value in the first place.

    Delegation (Remediation Design v2 §6.5, activated in Stage 3): this
    delegates to :func:`robust_scale_with_status` and returns that estimate's
    :attr:`ScaleEstimate.legacy_scale`, which preserves the historical
    ``return 1.0`` constant bit-for-bit **for every input the corpus
    contains**. The stage-3 change to the *status* -- ``indeterminate`` with
    ``scale = NaN`` instead of a fabricated finite number, and ``low_sample``
    for ``n < 3`` -- is observable here and was deliberately made so.
    """
    return robust_scale_with_status(values).legacy_scale


def finite_values(values: Any) -> np.ndarray[Any, Any]:
    """Return finite float entries of *values* as a 1-D array."""
    try:
        arr = np.asarray(list(values) if isinstance(values, (list, tuple)) else values, dtype=float)
    except (TypeError, ValueError):
        return np.empty(0, dtype=float)
    flat = arr.ravel()
    # asarray keeps the return a typed ndarray across numpy stub versions
    # (boolean-mask getitem alone resolves to Any on newer stubs).
    return np.asarray(flat[np.isfinite(flat)], dtype=float)


def is_finite_number(value: Any) -> bool:
    """True when *value* coerces to a finite number."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return False
    return out == out and abs(out) != float("inf")


def safe_mean(values: Any, default: float = 0.0) -> float:
    """Mean of finite entries, or *default* when none are finite."""
    finite = finite_values(values)
    return float(np.mean(finite)) if finite.size else default


def axis_spacing(values: np.ndarray[Any, Any]) -> float:
    """Median positive inter-sample spacing, 1.0 when degenerate."""
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    diffs = np.abs(np.diff(finite))
    diffs = diffs[diffs > 1e-9]
    return float(np.median(diffs)) if diffs.size else 1.0


def digital_compactness(area_cells: float, perimeter_cells: float) -> float:
    """Isoperimetric quotient ``4πA/P²`` for digital masks, clipped to [0, 1].

    Intended metric (see ``docs/adr/``): the classical compactness with the
    erosion-boundary cell count as the digital perimeter approximation,
    applied identically at every call site. Masks of one or two cells carry
    no measurable shape (a cell has no boundary; two cells have a single
    adjacency) and score ``0.0`` (not-compact) instead of the saturated
    ``1.0`` the quotient clips to — the conservative direction for
    compactness-gated hypotheses (metallic-like requires ``>= 0.45/0.55``),
    and the only regime these survivors reach (2-cell fragments survive
    solely via the strong-multiscan preservation path).

    Scope note (measured): a broader no-interior rule was trialed and
    reverted — it zeroed thin dipole lobes, propagating through the
    lobe-average merge into metallic support (Iron Box 0.45-gate) and the
    frozen overlapping-recall floor. Those thresholds were calibrated on
    this estimator; redefining small-shape compactness requires a proper
    boundary-length estimator plus threshold recalibration on field data
    (recorded as future work). The small-shape saturation bias (5x5 → 1.0
    vs π/4 ≈ 0.785 for a true square) therefore remains a known limitation.
    """
    import math as _math

    try:
        area = float(area_cells)
        perimeter = float(perimeter_cells)
    except (TypeError, ValueError):
        return 0.0
    if area != area or perimeter != perimeter:
        return 0.0
    if not area > 0.0 or not perimeter > 0.0:
        return 0.0
    if area <= 2.0:
        # Degenerate: no shape information exists at this resolution.
        return 0.0
    return float(np.clip(4.0 * _math.pi * area / max(perimeter * perimeter, 1e-9), 0.0, 1.0))


def bounded01(value: Any, *, unknown: str = "worst", risk: bool = False) -> float:
    """Clamp *value* to ``[0, 1]``, mapping non-finite input per *unknown*.

    ``numpy.clip(nan, 0, 1)`` returns ``nan`` and Python's ``min(1.0, nan)``
    returns ``1.0``, so a bounded-evidence helper written either way silently
    turned "no measurement" into "perfect". Every ``nan < threshold`` test is
    False as well, so a gate reading a non-finite field skipped its own branch
    entirely and reported the strongest possible outcome.

    *unknown*="worst" treats a missing measurement as the least favourable
    value (0.0), which is the safe direction for a gate. *unknown*="neutral"
    returns 0.5 for genuinely indeterminate quantities where neither extreme is
    justified. It is a caller decision, not a default.

    *risk* marks the field as a **risk** score, where 0 is the good outcome and
    1 is the adverse one (``artifact_score``, ``mineralization_risk``). For
    those, "worst" must resolve to 1.0, not 0.0: defaulting a risk to its
    favourable extreme is a policy inversion -- "we did not measure any
    artifact-like behaviour" reported as "no artifact-like behaviour".
    *unknown*="neutral" stays 0.5 either way, since the midpoint is the midpoint.

    Note ``unknown="worst"`` must never be used where a field's *absence* is
    meaningful rather than adverse (e.g. a boundary-contact ratio that is
    genuinely unmeasurable) -- those sites should pass ``unknown="neutral"``.
    """
    import numpy as _np

    if unknown == "neutral":
        fallback = 0.5
    elif unknown == "worst":
        fallback = 1.0 if risk else 0.0
    else:
        raise ValueError(f"unknown must be 'worst' or 'neutral', got {unknown!r}")
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    if not is_finite_number(out):
        return fallback
    return float(_np.clip(out, 0.0, 1.0))


def sanitize_label(label: str, *, max_length: int = 80) -> str:
    """Sanitize an untrusted label/case_id for use as a filename stem.

    Keeps ``[A-Za-z0-9._-]``; every other run of characters becomes a single
    ``_``. Strips leading dots/dashes (hidden files, ``..``), truncates to
    *max_length*, and never returns an empty string (falls back to
    ``"scan"``). Rejects absolute paths and parent traversal by construction
    (no ``/`` or ``\\\\`` survives).
    """
    import re as _re

    text = str(label).strip().replace("\\", "/").split("/")[-1]
    text = _re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")[:max_length].strip("._-")
    return text or "scan"


def contained_path(out_dir: Any, *parts: str) -> Any:
    """Join *parts* under *out_dir* and guarantee containment.

    Raises :class:`ValueError` on absolute parts, ``..`` escape, or ``.``
    segments that would leave *out_dir*. Uses :func:`sanitize_label` for the
    final filename stem when callers pass labels — call this helper rather
    than ``out_dir / f"{label}_..."`` directly.
    """
    from pathlib import Path as _Path

    base = _Path(out_dir).expanduser().resolve()
    candidate = base
    for part in parts:
        part_str = str(part)
        if _Path(part_str).is_absolute():
            raise ValueError(f"Refusing absolute output path part: {part_str!r}")
        candidate = candidate / part_str
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(f"Refusing output path escaping {base}: {parts!r}") from None
    if str(resolved) != str(base) and resolved.name in ("", ".", ".."):
        raise ValueError(f"Refusing degenerate output path: {parts!r}")
    return resolved


# ---------------------------------------------------------------------------
# K10 -- axial (doubling-angle) statistics for [0, 180) quantities
# ---------------------------------------------------------------------------
# An orientation in [0, 180) denotes an *axis*, not a direction: 0 deg and
# 180 deg are the same line. A linear mean of such values is therefore wrong at
# the wrap, and wrong in the worst possible way -- the two values that are
# closest together on the circle average to a direction pointing the wrong way.
# Mean(5, 175) is 90; the correct axial answer is 0. That is not a rounding
# difference, it is a different physical orientation, so it is a mathematical
# invariant (contract K10) and not a calibration question.


def axial_mean_deg(
    values: Sequence[float] | np.ndarray[Any, Any],
    weights: Sequence[float] | np.ndarray[Any, Any] | None = None,
    *,
    default: float = float("nan"),
) -> float:
    """Weighted mean of [0, 180) axial quantities, in [0, 180).

    Doubling-angle statistics: 2*theta is a true direction on the full circle, so
    a circular mean of the doubled angles is well defined, and halving maps it
    back into [0, 180). Non-finite values and non-positive weights are dropped;
    *default* is returned when nothing usable remains.

    Returns ``default`` when the resultant is vanishingly small (an isotropic
    population, whose mean direction genuinely carries no information) rather
    than reporting an arbitrary direction.
    """
    values_arr = np.asarray(values, dtype=float)
    if weights is None:
        weights_arr = np.ones(values_arr.shape, dtype=float)
    else:
        weights_arr = np.asarray(weights, dtype=float)
        if weights_arr.shape != values_arr.shape:
            raise ValueError("axial_mean_deg: weights must match values length")
    mask = np.isfinite(values_arr) & np.isfinite(weights_arr) & (weights_arr > 0)
    v = values_arr[mask]
    w = weights_arr[mask]
    if v.size == 0:
        return float(default)
    theta = np.radians(2.0 * v)
    sx = float(np.sum(np.cos(theta) * w))
    sy = float(np.sum(np.sin(theta) * w))
    total = float(np.sum(w))
    resultant = float(math.hypot(sx, sy) / max(total, 1e-12))
    if resultant <= _AXIAL_RESULTANT_FLOOR:
        return float(default)
    # Fold the doubled angle into [0, 360) *before* halving. A mean of, say,
    # 5 and 175 doubles to -6e-15 degrees, whose direct halving and ``% 180``
    # yields 179.99999999999997 -- a value outside the documented [0, 180)
    # range that then displays as 180. Normalising the full turn first maps it
    # to exactly 0.
    doubled = float(math.degrees(math.atan2(sy, sx))) % 360.0
    return float((doubled / 2.0) % 180.0)


def axial_dispersion_deg(angles_deg: Sequence[float], mean_deg: float) -> float:
    """RMS angular distance from *mean_deg*, each angle folded into [0, 180).

    The fold is what makes this an axial distance: ``d(a, b)`` is 0 for a == b,
    0 for a == b + 180, and never exceeds 90.
    """
    values = np.asarray(angles_deg, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or not is_finite_number(mean_deg):
        return float("nan")
    centre = float(mean_deg)
    delta = np.abs(((values - centre + 90.0) % 180.0) - 90.0)
    return float(np.sqrt(np.mean(np.square(delta))))


def axial_angle_distance_deg(a: float, b: float) -> float:
    """Signed-fold angular distance between two [0, 180) axial values, in [0, 90]."""
    return abs(float(((a - b + 90.0) % 180.0) - 90.0))


# ---------------------------------------------------------------------------
# K9 -- one output-directory choke point
# ---------------------------------------------------------------------------
# "No output" must mean no directory, no file, and no CWD mutation (contract
# K9). Measured before this existed: ``analyze_scan(scan, out_dir,
# write_outputs=False)`` still created the whole output tree, because the
# ``mkdir`` sat outside the flag. Two prior audit passes missed it by checking
# for *files* and because an already-existing ``out_dir`` masked the ``mkdir``.


def output_dir(path: Any, *, enabled: bool = True) -> Any:
    """Return the created output directory, or ``None`` when output is disabled.

    The single place a directory is created for analysis output. With
    ``enabled=False`` nothing is created, so ``write_outputs=False`` means
    "produce no filesystem side effects at all" rather than "create a tree and
    leave it empty".
    """
    if not enabled:
        return None
    from pathlib import Path as _Path

    target = _Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# S10 -- artifact identity: label, logical id, filesystem stem, fingerprint
# ---------------------------------------------------------------------------
# Four separate jobs that used to be one string:
#
#   display_label        what the operator typed; shown verbatim
#   logical_id           stable, collision-free, order-independent identity
#   filesystem_stem      safe to put on disk, and distinct per identity
#   content_fingerprint  what the bytes actually were
#
# The defect: ``filesystem_stem`` was just ``sanitize_label(label)``, so two
# distinct labels that sanitize alike ("Pass 1" and "pass_1", "a/b" and "a_b")
# silently overwrote each other's artifacts. The stem is now content-addressed,
# which makes it injective per scan *and* order-independent: the same scan set
# enumerated in any order produces the same paths.
#
# Genuine byte-identical duplicates share a stem. That is correct, not a leak:
# they are the same content, and ``analyze_site`` already detects and excludes
# exact duplicates from fusion with a user-facing warning.

#: Max sanitized-label characters retained in a filesystem stem.
IDENTITY_LABEL_MAX = 48
#: Hex characters of the content digest kept in the stem.
IDENTITY_STEM_DIGEST_CHARS = 8


def content_fingerprint(content: Any) -> str:
    """Stable hex digest of *content* (bytes, str, or an object with bytes)."""
    import hashlib as _hashlib

    if isinstance(content, (bytes, bytearray, memoryview)):
        payload = bytes(content)
    elif isinstance(content, str):
        payload = content.encode("utf-8")
    else:
        payload = repr(content).encode("utf-8")
    return _hashlib.sha256(payload).hexdigest()


def scan_fingerprint(scan: Any) -> str:
    """Order-independent fingerprint of a scan's measured content.

    Hashes the array shapes, dtypes and bytes of the measured channels -- not
    the label. Two differently-labelled scans with the same data therefore share
    a fingerprint (a true duplicate), while two scans whose labels sanitise
    alike do not, which is the collision being fixed.
    """
    import hashlib as _hashlib

    digest = _hashlib.sha256()
    for name in ("signal", "x", "y", "z"):
        arr = np.asarray(getattr(scan, name, None), dtype=float)
        digest.update(name.encode("utf-8"))
        digest.update(str(arr.shape).encode("utf-8"))
        digest.update(np.ascontiguousarray(arr).tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class ArtifactIdentity:
    """The four identity jobs, kept apart (Remediation Design v2 §9.1)."""

    display_label: str
    logical_id: str
    filesystem_stem: str
    content_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "display_label": self.display_label,
            "logical_id": self.logical_id,
            "filesystem_stem": self.filesystem_stem,
            "content_fingerprint": self.content_fingerprint,
        }


def artifact_identity(label: Any, *, fingerprint: str | None = None) -> ArtifactIdentity:
    """Build the identity quad for one artifact.

    *label* is the caller's string, kept verbatim as the display label.
    *fingerprint* is the content digest; when omitted it is derived from the
    label so the function is still total.

    The filesystem stem keeps a human-readable sanitized prefix (so an operator
    browsing the output directory still recognises the scan) and appends a
    content digest, which is what makes distinct identities distinct on disk.
    """
    display = str(label)
    digest = fingerprint if fingerprint is not None else content_fingerprint(display)
    safe = sanitize_label(display, max_length=IDENTITY_LABEL_MAX)
    stem = f"{safe}-{digest[:IDENTITY_STEM_DIGEST_CHARS]}"
    return ArtifactIdentity(
        display_label=display,
        logical_id=digest[:16],
        filesystem_stem=stem,
        content_fingerprint=digest,
    )


__all__ = [
    "ArtifactIdentity",
    "IDENTITY_LABEL_MAX",
    "IDENTITY_STEM_DIGEST_CHARS",
    "ScaleEstimate",
    "SCALE_STATUS_VALID",
    "SCALE_STATUS_DEGRADED",
    "SCALE_STATUS_INDETERMINATE",
    "artifact_identity",
    "axial_angle_distance_deg",
    "axial_dispersion_deg",
    "axial_mean_deg",
    "content_fingerprint",
    "finite_values",
    "is_finite_number",
    "output_dir",
    "robust_scale",
    "robust_scale_with_status",
    "safe_mean",
    "axis_spacing",
    "scan_fingerprint",
    "digital_compactness",
    "bounded01",
    "sanitize_label",
    "contained_path",
]

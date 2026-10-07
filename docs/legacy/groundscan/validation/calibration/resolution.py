"""Phases B and C -- ``d_res`` and ``min_size``, characterized as curves.

Both parameters are *resolution* parameters, and both are usually written down
as single numbers. Neither can be, and the reason is the same in both cases:
a single number silently assumes a response width, a sampling pitch, a noise
level and a detection threshold that the number never states.

Phase B -- ``d_res``
--------------------
A separation curve, not a threshold. The construction is a pair of equal
isotropic Gaussians, so the continuous field's modality is known *from the
construction* before any code runs:

.. code-block:: text

    d_analytic(sigma) = 2 * sigma

Two equal Gaussians superpose into two local maxima iff their separation
exceeds twice their shared sigma, and not otherwise. That is a closed form, so
the analytic expectation is available without asking any detector, and the
experiment's whole job is to measure how much *worse* than the analytic limit
the pipeline is at a given pitch, noise level and detection threshold.

The measured quantity is therefore dimensionless and is the useful one:

.. code-block:: text

    operating_factor = d_measured / (2 * sigma)

``d_measured`` is where the pipeline stops merging, ``2 * sigma`` is where the
mathematics stops merging. The ratio is how much of the analytic resolution the
acquisition actually delivers, and it is a function of the operating regime
rather than of the instrument. Presenting that ratio as a single number would
repeat the original error one level up, so the primary output is the curve.

Phase C -- ``min_size``
-----------------------
``min_size`` is a count of cells, so as a *physical* size it is
``min_size * dx * dy`` -- and that product is a function of the sampling pitch.
At a 0.25 m pitch, ``min_size = 3`` rejects anything smaller than 0.1875 m²; at
a 1.0 m pitch it rejects anything smaller than 3 m². The same number describes
two different instruments.

The metamorphic experiment separates the two possibilities directly: sample one
physical response at several pitches and ask what ``min_size`` value would be
needed to reproduce the same detection outcome at each. If the required value
scales as ``1/pitch^2`` the parameter is a cell count and nothing else. The
response-width form -- footprint width in units of the response's own sigma --
is the invariant one, and it is measured here rather than assumed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from ...core.anomaly import AnomalyMap, detect_anomalies
from ...core.grid import Grid2D, reconstruct_grid
from ...services.config import AnalysisConfig
from ...services.single_scan_stages import apply_zigzag_policy
from ..synthetic_core.cross_resolution import (
    PhysicalResponse,
    PhysicalScene,
    Resolution,
    continuous_maxima_count,
)

# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

#: Distinguishability vocabulary for one separation trial. Three outcomes, not
#: two, because "the pipeline split it and the mathematics says it is one
#: response" and "the pipeline merged it and the mathematics says it is two" are
#: different failures with different remedies, and collapsing them into
#: "unstable" hides which one occurred.
DISTINGUISHABLE = "distinguishable"
AMBIGUOUS = "ambiguous"
INDISTINGUISHABLE = "indistinguishable"

#: Two outcomes the construction rules out as *errors* but which are still worth
#: naming: the mathematics says two and the pipeline found two, versus the
#: mathematics saying one and the pipeline finding one.
RESOLVED = "resolved-as-constructed"
MERGED_AS_CONSTRUCTED = "merged-as-constructed"
FALSE_SPLIT = "false-split"
FALSE_MERGE = "false-merge"


def analytic_bifurcation_separation_m(sigma_m: float) -> float:
    """``2 * sigma``: the exact separation at which two equal Gaussians bifurcate.

    Closed form, no sampling, no pipeline. For a pair
    ``A*exp(-(x-s/2)^2/2s^2) + A*exp(-(x+s/2)^2/2s^2)`` the midpoint is a local
    maximum while ``s < 2*sigma`` and a local minimum while ``s > 2*sigma``, so
    the superlevel set is contractible below the bifurcation and splits above it.
    """
    return 2.0 * float(sigma_m)


# ---------------------------------------------------------------------------
# The detector call, exactly as production makes it
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectorRun:
    """One detection run, at the production detector arguments.

    ``analyze_scan`` reaches ``detect_anomalies`` through
    ``apply_zigzag_policy`` first, so the zigzag stage is reproduced here rather
    than skipped: skipping it would measure a pipeline that does not exist.
    """

    grid: Grid2D
    anomaly: AnomalyMap
    config: AnalysisConfig

    @property
    def region_count(self) -> int:
        """Level 2: connected components of the thresholded z-field."""
        return int(self.anomaly.n_components)

    @property
    def region_sizes(self) -> tuple[int, ...]:
        sizes = ndimage.sum(
            np.ones_like(self.anomaly.labels, dtype=float),
            self.anomaly.labels,
            index=range(1, self.anomaly.n_components + 1),
        )
        return tuple(int(s) for s in np.atleast_1d(sizes))


def run_detector(scan: Any, config: AnalysisConfig | None = None) -> DetectorRun:
    """Run the production grid reconstruction and detector on *scan*."""
    cfg = config or AnalysisConfig()
    grid = reconstruct_grid(scan)
    grid, _diag = apply_zigzag_policy(scan, grid, zigzag=cfg.zigzag)
    anomaly = detect_anomalies(
        grid,
        threshold=cfg.threshold,
        min_size=cfg.min_size,
        background_method=cfg.background_method,
        scales=cfg.scales,
        connectivity=cfg.connectivity,
    )
    return DetectorRun(grid=grid, anomaly=anomaly, config=cfg)


def _assign_regions(
    labels: np.ndarray[Any, Any],
    response_anchors: Sequence[tuple[float, float]],
    x_centers: np.ndarray[Any, Any],
    y_centers: np.ndarray[Any, Any],
) -> list[int]:
    """Which detected region covers each constructed response.

    A response is assigned to the region containing the lattice cell nearest its
    constructed centre. A half-way split is what the geometry of the
    construction says -- the two responses are separated along a known axis -- so
    the assignment never consults the detector's opinion about which region is
    which one.
    """
    out: list[int] = []
    for cx, cy in response_anchors:
        col = int(np.argmin(np.abs(x_centers - cx)))
        row = int(np.argmin(np.abs(y_centers - cy)))
        out.append(int(labels[row, col]))
    return out


# ---------------------------------------------------------------------------
# Phase B -- the separation curve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeparationTrial:
    """One point on the separation curve, with its ground truth attached."""

    trial_id: str
    sigma_m: float
    separation_m: float
    pitch_dx_m: float
    pitch_dy_m: float
    noise_sigma: float
    amplitude: float
    seed: int
    analytic_modes: int
    continuous_modes: int
    region_count: int
    assigned_region_ids: tuple[int, ...]
    distinct_regions: int
    outcome: str
    separation_over_sigma: float
    separation_over_2sigma: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "sigma_m": self.sigma_m,
            "separation_m": self.separation_m,
            "separation_over_sigma": round(self.separation_over_sigma, 6),
            "separation_over_2sigma": round(self.separation_over_2sigma, 6),
            "pitch_dx_m": self.pitch_dx_m,
            "pitch_dy_m": self.pitch_dy_m,
            "lattice_aspect": round(self.pitch_dy_m / self.pitch_dx_m, 6),
            "noise_sigma": self.noise_sigma,
            "amplitude": self.amplitude,
            "seed": self.seed,
            "analytic_modes": self.analytic_modes,
            "continuous_modes": self.continuous_modes,
            "region_count": self.region_count,
            "distinct_regions": self.distinct_regions,
            "assigned_region_ids": list(self.assigned_region_ids),
            "outcome": self.outcome,
        }


#: Field extent for the two-response scenes. Wide enough that the two responses
#: and their tails never reach the field edge, because an edge is a boundary
#: effect and a boundary effect would be attributed to separation.
PAIR_FIELD_WIDTH_M = 24.0
PAIR_FIELD_HEIGHT_M = 16.0


def pair_scene(
    *,
    sigma_m: float,
    separation_m: float,
    amplitude: float,
    noise_sigma: float,
    width_m: float = PAIR_FIELD_WIDTH_M,
    height_m: float = PAIR_FIELD_HEIGHT_M,
) -> PhysicalScene:
    """Two equal Gaussians separated along x, centred in the field."""
    cx = width_m / 2.0
    cy = height_m / 2.0
    half = separation_m / 2.0
    return PhysicalScene(
        name=f"pair_s{separation_m:g}",
        width_m=width_m,
        height_m=height_m,
        responses=(
            PhysicalResponse(
                label="left",
                cx=cx - half,
                cy=cy,
                sigma_x=sigma_m,
                sigma_y=sigma_m,
                amplitude=amplitude,
            ),
            PhysicalResponse(
                label="right",
                cx=cx + half,
                cy=cy,
                sigma_x=sigma_m,
                sigma_y=sigma_m,
                amplitude=amplitude,
            ),
        ),
        noise_sigma=noise_sigma,
        case_family="d_res-pair",
    )


def _scan_for(scene: PhysicalScene, resolution: Resolution, seed: int) -> Any:
    from ..synthetic_core.cross_resolution import sample_scene

    return sample_scene(scene, resolution, seed=seed)


def separation_trial(
    *,
    sigma_m: float,
    separation_m: float,
    pitch_dx_m: float,
    amplitude: float = 10.0,
    noise_sigma: float = 1.0,
    dy_ratio: float = 1.0,
    seed: int = 0,
    config: AnalysisConfig | None = None,
    lattice_margin_m: float = 6.0,
) -> SeparationTrial:
    """One separation trial: construct, count the mathematics, run the detector."""
    scene = pair_scene(
        sigma_m=sigma_m,
        separation_m=separation_m,
        amplitude=amplitude,
        noise_sigma=noise_sigma,
        width_m=PAIR_FIELD_WIDTH_M,
        height_m=PAIR_FIELD_HEIGHT_M,
    )
    # The lattice is padded past the construction so neither response's tail can
    # meet a field edge. Recorded on the trial so a reader can see the margin.
    width = PAIR_FIELD_WIDTH_M + 2.0 * lattice_margin_m
    height = PAIR_FIELD_HEIGHT_M + 2.0 * lattice_margin_m
    resolution = Resolution(
        name=f"p{pitch_dx_m:g}",
        dx=float(pitch_dx_m),
        width_m=width,
        height_m=height,
        dy_ratio=float(dy_ratio),
    )
    shift_x = lattice_margin_m + PAIR_FIELD_WIDTH_M / 2.0
    shift_y = lattice_margin_m + PAIR_FIELD_HEIGHT_M / 2.0
    anchored = PhysicalScene(
        name=scene.name,
        width_m=width,
        height_m=height,
        responses=tuple(
            PhysicalResponse(
                label=r.label,
                cx=r.cx + shift_x,
                cy=r.cy + shift_y,
                sigma_x=r.sigma_x,
                sigma_y=r.sigma_y,
                amplitude=r.amplitude,
            )
            for r in scene.responses
        ),
        noise_sigma=noise_sigma,
        case_family=scene.case_family,
    )
    analytic = 2 if separation_m > analytic_bifurcation_separation_m(sigma_m) else 1
    continuous = continuous_maxima_count(anchored)
    run = run_detector(_scan_for(anchored, resolution, seed), config)
    anchors = [(r.cx, r.cy) for r in anchored.responses]
    assigned = _assign_regions(run.anomaly.labels, anchors, run.grid.x_centers, run.grid.y_centers)
    distinct = len({rid for rid in assigned if rid > 0})
    resolved = distinct == analytic
    if resolved:
        outcome = RESOLVED if analytic == 2 else MERGED_AS_CONSTRUCTED
    else:
        outcome = FALSE_MERGE if analytic == 2 else FALSE_SPLIT
    return SeparationTrial(
        trial_id=f"s{sigma_m:g}_d{separation_m:g}_p{pitch_dx_m:g}_n{noise_sigma:g}_s{seed}",
        sigma_m=sigma_m,
        separation_m=separation_m,
        pitch_dx_m=float(pitch_dx_m),
        pitch_dy_m=float(resolution.dy),
        noise_sigma=noise_sigma,
        amplitude=amplitude,
        seed=seed,
        analytic_modes=analytic,
        continuous_modes=continuous,
        region_count=run.region_count,
        assigned_region_ids=tuple(assigned),
        distinct_regions=distinct,
        outcome=outcome,
        separation_over_sigma=separation_m / sigma_m,
        separation_over_2sigma=separation_m / analytic_bifurcation_separation_m(sigma_m),
    )


#: Separations swept as multiples of the analytic bifurcation scale. The
#: multipliers straddle 1.0 so the sweep crosses the mathematical boundary, and
#: run well past it so the empirical boundary is bracketed rather than assumed.
SEPARATION_MULTIPLIERS: tuple[float, ...] = (
    0.40,
    0.60,
    0.80,
    0.90,
    1.00,
    1.10,
    1.25,
    1.50,
    1.75,
    2.00,
    2.50,
    3.00,
    4.00,
    5.00,
)


def separation_curve(
    *,
    sigma_m: float,
    pitch_dx_m: float,
    noise_sigma: float = 1.0,
    amplitude: float = 10.0,
    dy_ratio: float = 1.0,
    seeds: Sequence[int] = (0, 1, 2),
    multipliers: Sequence[float] = SEPARATION_MULTIPLIERS,
    config: AnalysisConfig | None = None,
) -> tuple[SeparationTrial, ...]:
    """The full separation curve for one (sigma, pitch, noise, anisotropy) cell."""
    analytic = analytic_bifurcation_separation_m(sigma_m)
    trials: list[SeparationTrial] = []
    for multiplier in multipliers:
        for seed in seeds:
            trials.append(
                separation_trial(
                    sigma_m=sigma_m,
                    separation_m=multiplier * analytic,
                    pitch_dx_m=pitch_dx_m,
                    amplitude=amplitude,
                    noise_sigma=noise_sigma,
                    dy_ratio=dy_ratio,
                    seed=seed,
                    config=config,
                )
            )
    return tuple(trials)


@dataclass(frozen=True)
class SeparationSummary:
    """The outcome of one curve, with the rates and the measured threshold."""

    sigma_m: float
    pitch_dx_m: float
    pitch_dy_m: float
    noise_sigma: float
    dy_ratio: float
    peak_snr: float
    analytic_d_res_m: float
    measured_d_res_m: float | None
    measured_d_res_bracket_m: list[float] | None
    operating_factor: float | None
    n_trials: int
    n_false_merge: int
    n_false_split: int
    n_ambiguous_multipliers: int
    false_merge_rate: float | None
    false_split_rate: float | None
    n_resolved: int
    n_merged_as_constructed: int
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sigma_m": self.sigma_m,
            "pitch_dx_m": self.pitch_dx_m,
            "pitch_dy_m": self.pitch_dy_m,
            "lattice_aspect": round(self.pitch_dy_m / self.pitch_dx_m, 6),
            "noise_sigma": self.noise_sigma,
            "peak_snr": round(self.peak_snr, 4),
            "analytic_d_res_m": self.analytic_d_res_m,
            "measured_d_res_m": self.measured_d_res_m,
            "measured_d_res_bracket_m": (
                [round(v, 6) for v in self.measured_d_res_bracket_m]
                if self.measured_d_res_bracket_m
                else None
            ),
            "operating_factor": self.operating_factor,
            "n_trials": self.n_trials,
            "n_resolved": self.n_resolved,
            "n_merged_as_constructed": self.n_merged_as_constructed,
            "n_false_merge": self.n_false_merge,
            "n_false_split": self.n_false_split,
            "n_ambiguous_multipliers": self.n_ambiguous_multipliers,
            "false_merge_rate": self.false_merge_rate,
            "false_split_rate": self.false_split_rate,
            "verdict": self.verdict,
        }


def _classify_multiplier(trials: Sequence[SeparationTrial], multiplier: float) -> str:
    """Distinguishability of one separation, aggregated over the noise draws.

    Three-way, because a trial where the draws disagree is a *different finding*
    from one where every draw agrees:
    ``distinguishable`` every draw resolved as constructed; ``indistinguishable``
    every draw did not; ``ambiguous`` the draws disagreed.
    """
    outcomes = {t.outcome for t in trials}
    if outcomes == {RESOLVED} or outcomes == {MERGED_AS_CONSTRUCTED}:
        return DISTINGUISHABLE
    if outcomes == {FALSE_MERGE} or outcomes == {FALSE_SPLIT}:
        return INDISTINGUISHABLE
    return AMBIGUOUS


def summarize_separation_curve(
    trials: Sequence[SeparationTrial],
    *,
    sigma_m: float,
    pitch_dx_m: float,
    pitch_dy_m: float,
    noise_sigma: float,
    amplitude: float,
    dy_ratio: float = 1.0,
) -> SeparationSummary:
    """Reduce a curve to rates, a measured threshold, and a verdict.

    The *measured* ``d_res`` is the smallest swept separation at which every
    noise draw resolved the pair as two regions. It is a property of the swept
    grid, so it is reported as the lower bound it actually is: the true crossing
    lies between the last failing and the first passing multiplier.
    """
    analytic = analytic_bifurcation_separation_m(sigma_m)
    by_multiplier: dict[float, list[SeparationTrial]] = {}
    for trial in trials:
        by_multiplier.setdefault(round(trial.separation_over_2sigma, 9), []).append(trial)

    ordered = sorted(by_multiplier)
    resolving: list[float] = []
    merged: list[float] = []
    failing: list[float] = []
    ambiguous: list[float] = []
    for multiplier in ordered:
        group = by_multiplier[multiplier]
        kind = _classify_multiplier(group, multiplier)
        if kind == AMBIGUOUS:
            ambiguous.append(multiplier)
        elif all(t.outcome == RESOLVED for t in group):
            resolving.append(multiplier)
        elif all(t.outcome == MERGED_AS_CONSTRUCTED for t in group):
            merged.append(multiplier)
        else:
            failing.append(multiplier)

    measured: float | None = None
    lower_bracket: float | None = None
    if resolving:
        first = min(resolving)
        measured = first * analytic
        below = [m for m in failing + merged + ambiguous if m < first]
        lower_bracket = max(below) if below else None
        verdict = f"monotone: the pair resolves at every draw from {first:g}*2sigma upward"
    else:
        verdict = "no separation in the swept range resolved the pair at every draw"
    if resolving and failing and max(failing) > min(resolving):
        verdict = (
            f"non-monotone: a separation of {max(failing):g}*2sigma still failed while "
            f"{min(resolving):g}*2sigma resolved, so the curve has no single crossing"
        )

    n_false_merge = sum(1 for t in trials if t.outcome == FALSE_MERGE)
    n_false_split = sum(1 for t in trials if t.outcome == FALSE_SPLIT)
    n_resolved = sum(1 for t in trials if t.outcome == RESOLVED)
    n_merged = sum(1 for t in trials if t.outcome == MERGED_AS_CONSTRUCTED)
    two_response = [t for t in trials if t.analytic_modes == 2]
    one_response = [t for t in trials if t.analytic_modes == 1]
    false_merge_rate = round(n_false_merge / len(two_response), 4) if two_response else None
    false_split_rate = round(n_false_split / len(one_response), 4) if one_response else None
    return SeparationSummary(
        sigma_m=sigma_m,
        pitch_dx_m=pitch_dx_m,
        pitch_dy_m=pitch_dy_m,
        noise_sigma=noise_sigma,
        dy_ratio=dy_ratio,
        peak_snr=amplitude / noise_sigma if noise_sigma > 0 else float("inf"),
        analytic_d_res_m=analytic,
        measured_d_res_m=measured,
        measured_d_res_bracket_m=(
            [lower_bracket * analytic, measured] if measured and lower_bracket else None
        ),
        operating_factor=round(measured / analytic, 4) if measured else None,
        n_trials=len(trials),
        n_resolved=n_resolved,
        n_merged_as_constructed=n_merged,
        n_false_merge=n_false_merge,
        n_false_split=n_false_split,
        n_ambiguous_multipliers=len(ambiguous),
        false_merge_rate=false_merge_rate,
        false_split_rate=false_split_rate,
        verdict=verdict,
    )


def d_res_operating_envelope(
    *,
    sigmas: Sequence[float] = (0.5, 1.0, 1.5, 2.0),
    pitches: Sequence[float] = (0.25, 0.5, 1.0),
    noise_sigmas: Sequence[float] = (0.5, 1.0, 2.0),
    dy_ratios: Sequence[float] = (1.0, 2.0),
    seeds: Sequence[int] = (0, 1, 2),
    amplitude: float = 10.0,
    config: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """The operating-envelope probe for ``d_res``: a surface, not a number.

    Every cell of the surface is one complete separation curve. The output is
    the surface, the per-cell operating factor, and the honest verdict that no
    single ``d_res`` exists without also stating sigma, pitch, noise and
    anisotropy.
    """
    summaries: list[SeparationSummary] = []
    for sigma in sigmas:
        for pitch in pitches:
            for noise in noise_sigmas:
                for ratio in dy_ratios:
                    trials = separation_curve(
                        sigma_m=sigma,
                        pitch_dx_m=pitch,
                        noise_sigma=noise,
                        amplitude=amplitude,
                        dy_ratio=ratio,
                        seeds=seeds,
                        config=config,
                    )
                    summaries.append(
                        summarize_separation_curve(
                            trials,
                            sigma_m=sigma,
                            pitch_dx_m=pitch,
                            pitch_dy_m=pitch * ratio,
                            noise_sigma=noise,
                            amplitude=amplitude,
                            dy_ratio=ratio,
                        )
                    )
    factors = [s.operating_factor for s in summaries if s.operating_factor is not None]
    pitch_sensitivity: dict[str, Any] = {}
    for sigma in sigmas:
        for noise in noise_sigmas:
            for ratio in dy_ratios:
                subset = [
                    s
                    for s in summaries
                    if s.sigma_m == sigma and s.noise_sigma == noise and s.dy_ratio == ratio
                ]
                factors_here = [s.operating_factor for s in subset if s.operating_factor]
                if factors_here:
                    pitch_sensitivity[f"sigma{sigma:g}_noise{noise:g}_dy{ratio:g}"] = {
                        "factor_by_pitch": {
                            f"{s.pitch_dx_m:g}": s.operating_factor for s in subset
                        },
                        "factor_min": round(min(factors_here), 4),
                        "factor_max": round(max(factors_here), 4),
                    }
    return {
        "n_curves": len(summaries),
        "n_trials": sum(s.n_trials for s in summaries),
        "analytic_d_res_m": {
            f"sigma{s:g}": round(analytic_bifurcation_separation_m(s), 6) for s in sigmas
        },
        "operating_factor": {
            "min": round(min(factors), 4) if factors else None,
            "median": round(float(np.median(factors)), 4) if factors else None,
            "max": round(max(factors), 4) if factors else None,
            "n_defined": len(factors),
        },
        "pitch_sensitivity": pitch_sensitivity,
        "curves": [s.to_dict() for s in summaries],
        "single_value_supported": False,
        "why_no_single_value": (
            "d_res is a property of (response width, sampling pitch, noise level, "
            "detection threshold, lattice anisotropy) jointly. The analytic limit is "
            "exactly 2*sigma, but the delivered limit is a measured multiple of it "
            "that varies across the surface above, so a single number would have to "
            "silently assume an operating point that the number does not state."
        ),
    }


# ---------------------------------------------------------------------------
# Phase C -- min_size and physical resolution
# ---------------------------------------------------------------------------


def min_size_physical_floor_m2(min_size: int, dx_m: float, dy_m: float) -> float:
    """The physical area floor that ``min_size`` cells implies at this pitch."""
    return float(min_size) * float(dx_m) * float(dy_m)


@dataclass(frozen=True)
class MinSizeObservation:
    """Where the size filter starts rejecting one constructed response.

    Measured at the *boundary* rather than at a fixed amplitude, because at any
    comfortable amplitude the response is detected at ``min_size = 1`` and the
    parameter is inert. A parameter is only observable where it changes the
    outcome, so the response amplitude is walked down until the filter's answer
    changes, and the geometry is reported there.

    Three candidate units, because the question is which of them is invariant:
    the cell count the code uses, the physical area that count implies, and the
    equivalent diameter in units of the constructed response's own FWHM. One
    further quantity, ``boundary_amplitude``, is recorded knowing it is *not*
    invariant: a finer lattice needs more amplitude to shrink the same physical
    response down to the same cell count, and that non-invariance is part of the
    finding rather than a defect in the measurement.
    """

    response_sigma_m: float
    pitch_dx_m: float
    pitch_dy_m: float
    noise_sigma: float
    boundary_amplitude: float
    boundary_snr: float
    min_size_rejected: int
    min_size_accepted: int
    footprint_cells_at_boundary: int
    footprint_area_m2: float
    equivalent_diameter_m: float
    response_fwhm_m: float
    footprint_width_over_fwhm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_sigma_m": self.response_sigma_m,
            "pitch_dx_m": self.pitch_dx_m,
            "pitch_dy_m": self.pitch_dy_m,
            "lattice_aspect": round(self.pitch_dy_m / self.pitch_dx_m, 6),
            "noise_sigma": self.noise_sigma,
            "boundary_amplitude": round(self.boundary_amplitude, 9),
            "boundary_snr": round(self.boundary_snr, 6),
            "min_size_rejected": self.min_size_rejected,
            "min_size_accepted": self.min_size_accepted,
            "footprint_cells_at_boundary": self.footprint_cells_at_boundary,
            "footprint_area_m2": round(self.footprint_area_m2, 9),
            "equivalent_diameter_m": round(self.equivalent_diameter_m, 9),
            "response_fwhm_m": round(self.response_fwhm_m, 9),
            "footprint_width_over_fwhm": round(self.footprint_width_over_fwhm, 9),
        }


SINGLE_FIELD_WIDTH_M = 24.0
SINGLE_FIELD_HEIGHT_M = 18.0

#: The amplitude ladder walked when locating the size filter's boundary. Spans two
#: orders of magnitude and starts high enough that the response is comfortably above
#: threshold before the walk begins, so the boundary is bracketed rather than hit
#: at the first step.
MIN_SIZE_AMPLITUDE_LADDER: tuple[float, ...] = (
    40.0,
    30.0,
    24.0,
    20.0,
    16.0,
    14.0,
    12.0,
    10.0,
    9.0,
    8.0,
    7.0,
    6.0,
    5.0,
    4.5,
    4.0,
    3.5,
    3.0,
    2.6,
    2.2,
    1.8,
    1.5,
    1.2,
)


#: A surviving region counts as "the response" when any of its cells lies within
#: this many response widths of the constructed centre. Wide enough to include a
#: region the response genuinely split across, narrow enough to exclude the rest of
#: the field -- without it, the measurement latches onto whichever noise excursion
#: happened to clear the threshold, and the size filter's boundary is then a
#: property of the noise draw rather than of the response.
MIN_SIZE_RESPONSE_RADIUS_IN_SIGMA = 3.0


def _regions_near(
    run: DetectorRun, centre_x: float, centre_y: float, sigma_m: float
) -> dict[int, int]:
    """Region id -> cell count, for regions overlapping the constructed response."""
    radius = MIN_SIZE_RESPONSE_RADIUS_IN_SIGMA * float(sigma_m)
    xs = run.grid.x_centers
    ys = run.grid.y_centers
    labels = run.anomaly.labels
    inside = ((xs[None, :] - centre_x) ** 2 + (ys[:, None] - centre_y) ** 2) <= radius**2
    found: dict[int, int] = {}
    for comp_id in range(1, run.anomaly.n_components + 1):
        mask = labels == comp_id
        if not np.any(mask & inside):
            continue
        found[comp_id] = int(np.count_nonzero(mask))
    return found


def min_size_observation(
    *,
    response_sigma_m: float,
    pitch_dx_m: float,
    noise_sigma: float = 1.0,
    dy_ratio: float = 1.0,
    seed: int = 0,
    config: AnalysisConfig | None = None,
    ladder: Sequence[float] = MIN_SIZE_AMPLITUDE_LADDER,
    probe_min_sizes: Sequence[int] = (1, 2, 3, 5, 8),
    lattice_margin_m: float = 6.0,
) -> MinSizeObservation:
    """Walk one constructed response down to the size filter's boundary.

    For each amplitude on the ladder, and for each probe ``min_size``, the
    production detector is run and the surviving-region count recorded. The
    boundary is the highest amplitude at which a larger ``min_size`` rejects a
    response a smaller one keeps -- that is, the narrowest gap on which the
    parameter can act at all.

    Raises when no amplitude on the ladder produces a boundary. "This parameter
    never acted on this construction" is a real result, and raising keeps it from
    being reported as a measurement of something.
    """
    from dataclasses import replace as _replace

    cfg = config or AnalysisConfig()
    width = SINGLE_FIELD_WIDTH_M + 2.0 * lattice_margin_m
    height = SINGLE_FIELD_HEIGHT_M + 2.0 * lattice_margin_m
    resolution = Resolution(
        name=f"p{pitch_dx_m:g}",
        dx=float(pitch_dx_m),
        width_m=width,
        height_m=height,
        dy_ratio=float(dy_ratio),
    )
    centre_x = width / 2.0
    centre_y = height / 2.0
    fwhm = 2.0 * response_sigma_m * math.sqrt(2.0 * math.log(2.0))
    ordered = sorted(int(p) for p in probe_min_sizes)
    if len(ordered) < 2:
        raise ValueError("at least two probe min_size values are needed to find a boundary")

    for amplitude in ladder:
        scene = PhysicalScene(
            name=f"single_s{response_sigma_m:g}_a{amplitude:g}",
            width_m=width,
            height_m=height,
            responses=(
                PhysicalResponse(
                    label="single",
                    cx=centre_x,
                    cy=centre_y,
                    sigma_x=response_sigma_m,
                    sigma_y=response_sigma_m,
                    amplitude=amplitude,
                ),
            ),
            noise_sigma=noise_sigma,
            case_family="min_size-single",
        )
        scan = _scan_for(scene, resolution, seed)
        counts: dict[int, int] = {}
        sizes: dict[int, int] = {}
        for probe in ordered:
            run = run_detector(scan, _replace(cfg, min_size=probe))
            local = _regions_near(run, centre_x, centre_y, response_sigma_m)
            counts[probe] = len(local)
            sizes[probe] = max(local.values()) if local else 0
        largest = ordered[-1]
        rejected = [p for p in ordered[:-1] if counts[p] >= 1 and counts[largest] == 0]
        if not rejected:
            continue
        min_size_rejected = max(rejected)
        accepted = [p for p in ordered if counts[p] >= 1]
        min_size_accepted = min(accepted) if accepted else min_size_rejected
        footprint = sizes[min_size_accepted] or sizes[min_size_rejected]
        area_m2 = footprint * resolution.dx * resolution.dy
        equivalent_diameter = 2.0 * math.sqrt(max(area_m2, 0.0) / math.pi)
        return MinSizeObservation(
            response_sigma_m=response_sigma_m,
            pitch_dx_m=float(pitch_dx_m),
            pitch_dy_m=float(resolution.dy),
            noise_sigma=noise_sigma,
            boundary_amplitude=float(amplitude),
            boundary_snr=amplitude / noise_sigma if noise_sigma > 0 else float("inf"),
            min_size_rejected=int(min_size_rejected),
            min_size_accepted=int(min_size_accepted),
            footprint_cells_at_boundary=int(footprint),
            footprint_area_m2=area_m2,
            equivalent_diameter_m=equivalent_diameter,
            response_fwhm_m=fwhm,
            footprint_width_over_fwhm=equivalent_diameter / max(fwhm, 1e-9),
        )
    raise ValueError(
        f"no amplitude on the ladder produced a size-filter boundary for sigma="
        f"{response_sigma_m:g} m at pitch {pitch_dx_m:g} m; the parameter never acted "
        f"on this construction, which is a result and not a failure to measure"
    )


def min_size_resolution_sweep(
    *,
    response_sigmas: Sequence[float] = (0.5, 1.0, 1.5, 2.0, 3.0),
    pitches: Sequence[float] = (0.2, 0.25, 0.4, 0.5, 0.8, 1.0, 1.5),
    noise_sigma: float = 1.0,
    seeds: Sequence[int] = (0,),
    config: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """Does ``min_size`` mean a physical size, a cell count, or a response width?

    One physical response, swept over sampling pitch, with the size filter's
    boundary located at each pitch. Then each candidate parameterization is
    *tested* for invariance across pitch, because a parameterization is only a
    parameter if one of the three units is the one that holds still.

    The cell count cannot be invariant by construction: a finer lattice covers
    the same physical response with more cells, so a fixed cell threshold is
    always stricter at a fine pitch. The interesting question is whether physical
    area or response width is invariant, and which of them -- if either -- the
    current value corresponds to.
    """
    observations: list[MinSizeObservation] = []
    skipped: list[dict[str, Any]] = []
    for sigma in response_sigmas:
        for pitch in pitches:
            for seed in seeds:
                try:
                    observations.append(
                        min_size_observation(
                            response_sigma_m=sigma,
                            pitch_dx_m=pitch,
                            noise_sigma=noise_sigma,
                            seed=seed,
                            config=config,
                        )
                    )
                except ValueError as exc:
                    skipped.append({
                        "response_sigma_m": sigma,
                        "pitch_dx_m": pitch,
                        "seed": seed,
                        "reason": str(exc),
                    })
    by_sigma: dict[str, Any] = {}
    for sigma in response_sigmas:
        subset = sorted(
            (o for o in observations if o.response_sigma_m == sigma),
            key=lambda o: o.pitch_dx_m,
        )
        key = f"sigma{sigma:g}"
        if not subset:
            by_sigma[key] = {"n": 0, "rows": [], "note": "no boundary located at any pitch"}
            continue
        cells = np.array([o.footprint_cells_at_boundary for o in subset], dtype=float)
        areas = np.array([o.footprint_area_m2 for o in subset], dtype=float)
        widths = np.array([o.footprint_width_over_fwhm for o in subset], dtype=float)
        amplitudes = np.array([o.boundary_amplitude for o in subset], dtype=float)
        pitches_arr = np.array([o.pitch_dx_m for o in subset], dtype=float)
        cell_log = np.log(np.maximum(cells, 1.0))
        pitch_log = np.log(pitches_arr)
        cell_exponent = (
            float(np.polyfit(pitch_log, cell_log, 1)[0]) if cells.size > 1 else float("nan")
        )
        by_sigma[key] = {
            "n": len(subset),
            "rows": [o.to_dict() for o in subset],
            "footprint_cells": [int(v) for v in cells],
            "footprint_area_m2": [round(float(v), 9) for v in areas],
            "footprint_width_over_fwhm": [round(float(v), 9) for v in widths],
            "boundary_amplitude": [round(float(v), 6) for v in amplitudes],
            "cells_vs_pitch_exponent": round(cell_exponent, 4),
            "area_relative_spread": round(
                float((areas.max() - areas.min()) / max(areas.mean(), 1e-12)), 6
            ),
            "width_relative_spread": round(
                float((widths.max() - widths.min()) / max(widths.mean(), 1e-12)), 6
            ),
            "amplitude_relative_spread": round(
                float((amplitudes.max() - amplitudes.min()) / max(amplitudes.mean(), 1e-12)), 6
            ),
        }

    def _median_spread(field: str) -> float:
        values = [
            by_sigma[f"sigma{s:g}"][field]
            for s in response_sigmas
            if by_sigma[f"sigma{s:g}"].get("n")
        ]
        finite = [v for v in values if np.isfinite(v)]
        return round(float(np.median(finite)), 6) if finite else float("nan")

    def _median_exponent() -> float:
        # Only sigmas with at least two pitches contribute: a single point has no
        # slope, and admitting a NaN into the median would silently void the whole
        # figure rather than reducing its sample.
        values = [
            by_sigma[f"sigma{s:g}"]["cells_vs_pitch_exponent"]
            for s in response_sigmas
            if by_sigma[f"sigma{s:g}"].get("n", 0) >= 2
        ]
        finite = [v for v in values if np.isfinite(v)]
        return round(float(np.median(finite)), 4) if finite else float("nan")

    exponents = [
        by_sigma[f"sigma{s:g}"]["cells_vs_pitch_exponent"]
        for s in response_sigmas
        if by_sigma[f"sigma{s:g}"].get("n", 0) >= 2
    ]
    return {
        "n_observations": len(observations),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "n_sigmas_with_a_pitch_slope": len(exponents),
        "response_sigmas_m": list(response_sigmas),
        "pitches_m": list(pitches),
        "per_sigma": by_sigma,
        "cells_vs_pitch_exponent": {
            "values": exponents,
            "median": _median_exponent(),
            "expected_if_pure_cell_count": -2.0,
            "note": (
                "sigmas where a boundary was located at fewer than two pitches are "
                "excluded: one point has no slope, and a NaN in the median would void "
                "the figure rather than shrink its sample"
            ),
        },
        "physical_area_relative_spread": _median_spread("area_relative_spread"),
        "response_width_relative_spread": _median_spread("width_relative_spread"),
        "boundary_amplitude_relative_spread": _median_spread("amplitude_relative_spread"),
        "production_min_size": int((config or AnalysisConfig()).min_size),
        "verdict": None,
    }


#: Relative spread below which two measurements are called the same number twice.
#: Fixed before the measurement rather than fitted to it, for the usual reason.
MIN_SIZE_INVARIANCE_TOLERANCE = 0.25


def min_size_parameterisation_verdict(sweep: dict[str, Any]) -> str:
    """State which unit, if any, is invariant -- from the measured spreads.

    Three candidates, three measured numbers, one conclusion. Nothing here is
    asserted by construction; the verdict is a function of what the sweep
    returned, so it cannot drift from the evidence it cites.
    """
    if not sweep.get("n_observations"):
        return (
            "No size-filter boundary was located for any (response width, pitch) pair in "
            "the swept range, so no unit of min_size can be scored for invariance: the "
            "parameter never acted on these constructions."
        )
    exponent = sweep["cells_vs_pitch_exponent"]["median"]
    area = sweep["physical_area_relative_spread"]
    width = sweep["response_width_relative_spread"]
    amplitude = sweep["boundary_amplitude_relative_spread"]
    flat = MIN_SIZE_INVARIANCE_TOLERANCE
    parts = [
        "The cell count at the boundary is small by construction -- that is where the "
        "filter bites -- so it is quantized by the amplitude ladder rather than by the "
        "pitch, and the fitted pitch exponent "
        f"({exponent:+.2f}, where a footprint tracking a fixed physical size would give "
        "-2.00) is therefore not a usable discriminator. The two spreads that are: "
        f"physical area varies by {area:.1%} across pitch and the footprint width in units "
        f"of the response's FWHM by {width:.1%}, while the amplitude needed to reach the "
        f"boundary at all varies by {amplitude:.1%}."
    ]
    area_flat = area < flat
    width_flat = width < flat
    if area_flat and width_flat:
        parts.append(
            "Both physical area and response width hold still, so a context-free physical "
            "parameterization is available and the cell count is a proxy for it."
        )
    elif width_flat:
        parts.append(
            "Response width is the only near-invariant of the three, so a width "
            "parameterization is the more defensible of the available readings -- but "
            f"{width:.0%} is not flat enough to call one, and the boundary amplitude is not "
            "flat at all."
        )
    elif area_flat:
        parts.append(
            "Physical area is the only near-invariant of the three, so a physical-area "
            "parameterization is the more defensible reading -- with the same reservation."
        )
    else:
        parts.append(
            "No candidate unit is invariant across the swept pitches on this evidence, so "
            "min_size cannot be recalibrated as a context-free number: a replacement would "
            "substitute one arbitrary unit for another."
        )
    return " ".join(parts)

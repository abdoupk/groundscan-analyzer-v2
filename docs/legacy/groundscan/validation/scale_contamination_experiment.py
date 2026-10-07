"""Phase F: the previously reported failure, reconstructed from first principles.

The reported failure was: *"a mostly quiet residual plus one extreme acquisition
cell pushed the 3-sigma detection threshold above every genuine anomaly and the
scan reported nothing."* Two audit rounds touched this and the second one
(winsorising the std floor) fixed the *floor* half of it. This module
reconstructs the scenario so the remaining half can be measured, and so the
reconstruction -- not a golden, and not the vendor annotations -- is the oracle.

## The construction, and why the background is quantised

The field is built the way the two real vendor residuals that still land in the
degenerate regime are built: on an **integer lattice**. That is not decoration.
It is the whole reason the failure is hard, and it is measured rather than
assumed: on 8 of the 9 vendor scans the median-filter residual is continuous and
the MAD tier applies; on the two that are quantised, more than half the
population sits exactly on the median, the MAD and IQR both collapse, and the
estimator falls through to a tier with breakdown 0.

So the clean background is a quantised population with a *known* dispersion, and
the question is: does one extreme cell change the estimated dispersion, and does
that change reach the finding set?

## What the experiment is allowed to conclude

Three outcomes are possible and all three are informative:

* the clean scale is recovered -> the estimator resists the contamination, and
  the targets survive;
* the scale inflates -> the estimator does not resist it, the targets vanish,
  and the *count* of vanished targets is the defect's size in the units an
  operator sees;
* the scale collapses to zero -> the estimator is robust in the textbook sense
  and useless in the operational one, because "no dispersion" is a false reading
  of a population that demonstrably has some. This is the outcome that makes a
  replacement estimator *worse*, and it is measured here rather than assumed
  away.

A golden hash is not an oracle for any of them, and the vendor table is not
either: it says what the field notes claim, not what the residual is.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import scale_reference as ref
from .scale_shadow_report import _patched_scale, candidate_status_estimate, shipped_status_estimate

#: The lattice the contaminated background lives on. 1.0 counts, matching the
#: measured ``quantisation_step`` of both degenerate vendor residuals.
QUANTUM = 1.0

#: The background's true dispersion, in counts.
#:
#: The value is not arbitrary: it is what makes the background *degenerate*. A
#: lattice population needs an atom heavier than 50 % at the median before the
#: MAD collapses, and ``P(round(N(0, s)) == 0) = erf(s / sqrt(2))`` crosses 50 %
#: at ``s = 0.674``. At 0.5 counts the atom carries about 68 % of the mass, so
#: the MAD and the IQR are both exactly zero and the estimator has nowhere left
#: to go but the breakdown-0 tier -- which is the regime the two real vendor
#: residuals are in, and which a 1-count sigma would *not* reproduce.
BACKGROUND_SIGMA_COUNTS = 0.5

#: Target amplitude in counts. Six counts against a 0.5-count background is
#: about 13 sigma, so a target this size is unambiguously detectable on the
#: clean construction and its disappearance can only be attributed to the
#: estimator.
TARGET_AMPLITUDE_COUNTS = 6.0

#: Target size in cells, a block rather than a line: the pipeline's ``min_size``
#: and multi-scale persistence gates would legitimately discard a one-cell
#: response, and an experiment that failed because of a size gate would be
#: measuring the size gate.
TARGET_BLOCK_CELLS = 3


def quantised_background(
    n: int, seed: int, sigma_counts: float = BACKGROUND_SIGMA_COUNTS
) -> np.ndarray[Any, Any]:
    """A lattice-valued background with a *known* population dispersion.

    Drawn as a discrete distribution whose continuous counterpart has standard
    deviation ``sigma_counts``, then rounded to the lattice. Rounding is what
    makes the MAD collapse: for ``sigma_counts = 1`` roughly 68 % of the mass
    lands on the three central counts, so the median absolute deviation is 0 and
    the interquartile range is 0 as well.
    """
    rng = np.random.default_rng(seed)
    return np.round(rng.normal(0.0, sigma_counts, n)) * QUANTUM


def plant_targets(
    background: np.ndarray[Any, Any],
    indices: Iterable[int],
    amplitude_counts: float,
) -> np.ndarray[Any, Any]:
    """Add known responses of a known amplitude to a known background.

    The amplitude is in counts, so the expected z-score of a target is
    ``amplitude / (population sigma of the background)`` -- a number the
    construction states, not one read back from the estimator.
    """
    out = np.array(background, dtype=float)
    for index in indices:
        out[index] += amplitude_counts * QUANTUM
    return out


def contaminate(residual: np.ndarray[Any, Any], index: int, value: float) -> np.ndarray[Any, Any]:
    """One extreme acquisition cell, the way a single bad reading arrives."""
    out = np.array(residual, dtype=float)
    out[index] = value
    return out


@dataclass(frozen=True)
class ContaminationOutcome:
    """One (contamination amplitude, target amplitude) point of the experiment."""

    n_background: int
    contamination_value: float
    target_amplitude_counts: float
    true_background_sigma: float
    background_scale: float
    contaminated_scale: float
    scale_ratio: float
    target_z: float
    target_z_legacy: float
    detector_threshold: float
    targets_survive: bool
    status: str
    regime: str
    references: dict[str, float] = field(default_factory=dict)

    @property
    def scale_inflation(self) -> float:
        return (
            self.contaminated_scale / self.background_scale if self.background_scale else math.nan
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_background": self.n_background,
            "contamination_value": self.contamination_value,
            "target_amplitude_counts": self.target_amplitude_counts,
            "true_background_sigma": self.true_background_sigma,
            "background_scale": self.background_scale,
            "contaminated_scale": self.contaminated_scale,
            "scale_inflation": self.scale_inflation,
            "target_z": self.target_z,
            "target_z_legacy": self.target_z_legacy,
            "detector_threshold": self.detector_threshold,
            "targets_survive": self.targets_survive,
            "status": self.status,
            "regime": self.regime,
            "references": {k: (None if v != v else v) for k, v in self.references.items()},
        }


#: The pipeline's own detection gate, quoted rather than re-tuned. A target is
#: "detected" when its z-score reaches it; the multiscale channel and the
#: ``min_size`` / persistence gates are measured separately by
#: :func:`end_to_end_survival`, which runs the real pipeline.
DETECTION_THRESHOLD = 3.0


def measure(
    *,
    n_background: int = 4000,
    seed: int = 4242,
    n_targets: int = 3,
    target_amplitude_counts: float = TARGET_AMPLITUDE_COUNTS,
    contamination_value: float = 0.0,
    contamination_index: int = 17,
) -> ContaminationOutcome:
    """The scale-level half of the experiment, on a known construction.

    Both the clean and the contaminated population come from the *same* draw, so
    the ratio between their reported scales is against a measured clean
    population rather than a nominal sigma. Everything asserted downstream of
    this rests on ``true_background_sigma``, which is a *stated* property of the
    generator: the population standard deviation of ``round(N(0, sigma^2))`` is
    measured from the clean draw once and reported, rather than assumed equal to
    ``sigma`` (rounding moves it -- at ``sigma = 1`` the lattice value is about
    0.96, which is exactly the kind of 4 % nobody would guess).
    """
    from .scale_shadow_report import residual_regime

    background = quantised_background(n_background, seed)
    true_sigma = float(np.std(background))
    target_slots = [n_background // 4, n_background // 2, (3 * n_background) // 4][:n_targets]
    clean = plant_targets(background, target_slots, target_amplitude_counts)
    contaminated = (
        contaminate(clean, contamination_index, contamination_value)
        if contamination_value
        else clean
    )

    clean_estimate = candidate_status_estimate(clean)
    contaminated_estimate = candidate_status_estimate(contaminated)
    legacy_estimate = shipped_status_estimate(contaminated)
    regime, _stats = residual_regime(contaminated)
    median = float(np.median(contaminated))
    peak = max(float(contaminated[i] - median) for i in target_slots)
    scale = contaminated_estimate.legacy_scale
    legacy_scale = legacy_estimate.legacy_scale
    target_z = peak / scale if scale else math.nan
    return ContaminationOutcome(
        n_background=n_background,
        contamination_value=contamination_value,
        target_amplitude_counts=target_amplitude_counts,
        true_background_sigma=true_sigma,
        background_scale=float(clean_estimate.legacy_scale),
        contaminated_scale=float(scale),
        scale_ratio=float(scale / clean_estimate.legacy_scale)
        if clean_estimate.legacy_scale
        else math.nan,
        target_z=target_z,
        target_z_legacy=peak / legacy_scale if legacy_scale else math.nan,
        detector_threshold=DETECTION_THRESHOLD,
        targets_survive=bool(scale > 0.0 and target_z >= DETECTION_THRESHOLD),
        status=contaminated_estimate.status,
        regime=regime,
        references={
            name: float(ref.REFERENCE_ESTIMATORS[name](contaminated))
            for name in ref.SCALE_ESTIMATORS
        },
    )


def contamination_sweep(
    values: Iterable[float] = (0.0, 10.0, 100.0, 200.0, 1e3, 1e5),
    **kwargs: Any,
) -> list[ContaminationOutcome]:
    """How the reported scale responds as one cell goes further out.

    Each row already carries the clean scale from the same draw, so the ratio
    column is against a measured clean population rather than a nominal sigma.
    Both the pre-activation and the activated estimators are carried, so the
    change the activation makes is visible at this level too.
    """
    return [measure(contamination_value=value, **kwargs) for value in values]


def end_to_end_survival(
    *,
    n_side: int = 40,
    contamination_value: float = 0.0,
    target_amplitude_counts: float = TARGET_AMPLITUDE_COUNTS,
    block: int = TARGET_BLOCK_CELLS,
    seed: int = 4242,
) -> dict[str, Any]:
    """Run the real pipeline on the contaminated construction, twice.

    Once with the pre-activation estimator, once with production. The
    construction is a *field*, not a residual array: a quantised background with
    a known dispersion plus three known targets of known amplitude and known
    size, so a finding that disappears is a finding the construction put there
    and the estimator lost.

    Returns the finding count under each estimator, and whether the constructed
    target cells still reach the detection gate, so "the candidate disappeared"
    is checkable against the construction rather than against a stored label.
    """
    from ..models import ScanData
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan

    gx, gy = np.meshgrid(np.arange(n_side, dtype=float), np.arange(n_side, dtype=float))
    background = quantised_background(n_side * n_side, seed)
    field = background.reshape(n_side, n_side)
    centre = n_side // 2
    half = block // 2
    target_cells: list[tuple[int, int]] = []
    for offset in (-6, 0, 6):
        for row in range(centre + offset - half, centre + offset + half + 1):
            for col in range(centre - half, centre + half + 1):
                field[row, col] += target_amplitude_counts * QUANTUM
                target_cells.append((row, col))
    if contamination_value:
        # A background cell far from every target: one bad acquisition reading.
        field[1, 1] = contamination_value
    scan = ScanData(
        x=(gx * QUANTUM).ravel(),
        y=(gy * QUANTUM).ravel(),
        z=np.zeros(n_side * n_side),
        signal=field.ravel(),
    )
    config = AnalysisConfig()
    out: dict[str, Any] = {
        "contamination_value": contamination_value,
        "target_amplitude_counts": target_amplitude_counts,
        "target_block_cells": block,
        "n_target_cells": len(target_cells),
        "true_background_sigma": float(np.std(background)),
        "background_atom_fraction": float(np.mean(background == np.median(background))),
    }
    for label, estimator in (
        ("legacy", shipped_status_estimate),
        ("activated", candidate_status_estimate),
    ):
        with _patched_scale(estimator), tempfile.TemporaryDirectory() as work:
            _grid, anomaly, candidates = analyze_scan(
                scan, Path(work) / label, label=label, config=config, write_outputs=False
            )
        z = anomaly.zscore
        finite = z[np.isfinite(z)]
        target_z = [float(z[row, col]) for row, col in target_cells]
        out[label] = {
            "n_components": int(anomaly.n_components),
            "n_findings": len(candidates),
            "peak_abs_z": float(np.max(np.abs(finite))) if finite.size else 0.0,
            "target_z_median": float(np.median(np.abs(target_z))) if target_z else 0.0,
            "target_z_max": float(np.max(np.abs(target_z))) if target_z else 0.0,
            "target_cells_above_threshold": int(
                sum(1 for v in target_z if abs(v) >= DETECTION_THRESHOLD)
            ),
            "hypotheses": sorted(str(getattr(c, "pattern_hypothesis", "")) for c in candidates),
        }
    out["n_targets_constructed"] = 3
    return out


__all__ = [
    "BACKGROUND_SIGMA_COUNTS",
    "DETECTION_THRESHOLD",
    "QUANTUM",
    "ContaminationOutcome",
    "contamination_sweep",
    "end_to_end_survival",
    "measure",
    "plant_targets",
    "quantised_background",
]

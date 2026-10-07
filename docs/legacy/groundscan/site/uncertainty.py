"""Multi-scan evidence aggregation and auditable uncertainty metrics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import hypot
from typing import Any

import numpy as np

from ..models import Candidate


@dataclass(frozen=True)
class UncertaintyProfile:
    """Bounded uncertainty profile. Higher uncertainty means less stable evidence."""

    evidence_score: float
    evidence_uncertainty: float
    depth_uncertainty: float
    geometry_uncertainty: float
    signal_uncertainty: float
    position_uncertainty: float
    registration_uncertainty: float
    leave_one_out_stability: float
    effective_scan_count: int
    flags: tuple[str, ...]
    components: dict[str, float]


def finite_values(values: Iterable[float]) -> np.ndarray[Any, Any]:
    """Backward-compat alias — canonical impl is groundscan._util.finite_values."""
    from .._util import finite_values

    return finite_values(values)


def _robust_relative_dispersion(values: Iterable[float], floor: float = 1e-9) -> float:
    a = finite_values(values)
    if len(a) < 2:
        return 1.0
    center = float(np.median(a))
    mad = float(np.median(np.abs(a - center)))
    scale = 1.4826 * mad
    if scale <= floor:
        scale = float(np.std(a))
    denom = max(abs(center), floor)
    return float(np.clip(scale / denom, 0.0, 1.0))


def _bounded_uncertainty_from_values(values: Iterable[float]) -> float:
    a = finite_values(values)
    if len(a) < 2:
        return 1.0
    return _robust_relative_dispersion(a)


def compute_uncertainty_profile(
    members: list[Candidate],
    positions: list[tuple[float, float]],
    registration_values: list[float],
    *,
    detection_rate: float,
    direction_persistence: float,
    spacing_persistence: float,
    traversal_persistence: float,
    polarity_consistency: float,
    position_stability: float,
    multiscan_signal_consistency: float,
    multiresolution_consensus: float,
    depth_cross_scan_consistency: float,
    geometry_consistency: float,
) -> UncertaintyProfile:
    """Aggregate scan-level evidence without fabricating probabilities."""
    n = len(members)

    depth_values = []
    geometry_values = []
    signal_values = []
    evidence_values = []
    for c in members:
        d = c.depth_estimate if np.isfinite(c.depth_estimate) else c.depth_mean
        if np.isfinite(d):
            depth_values.append(float(d))
        geometry_values.append(float(c.major_extent))
        signal_values.append(float(c.anomaly_score))
        evidence_values.append(float(c.evidence_score))

    depth_unc = _bounded_uncertainty_from_values(depth_values)
    geom_unc = _bounded_uncertainty_from_values(geometry_values)
    signal_unc = _bounded_uncertainty_from_values(signal_values)

    if len(positions) >= 2:
        ux = finite_values([p[0] for p in positions])
        uy = finite_values([p[1] for p in positions])
        position_unc = float(np.clip(hypot(float(np.std(ux)), float(np.std(uy))) / 0.10, 0.0, 1.0))
    else:
        position_unc = 1.0

    # v0.4.2 (audit F-10): absent registration is unknown (0.5
    # uncertainty), never perfect (0.0). No evidence must read as indifference.
    registration_unc = (
        1.0 - float(np.clip(np.mean(registration_values), 0.0, 1.0)) if registration_values else 0.5
    )

    component_stability = {
        "detection": float(np.clip(detection_rate, 0.0, 1.0)),
        "direction": float(np.clip(direction_persistence, 0.0, 1.0)),
        "spacing": float(np.clip(spacing_persistence, 0.0, 1.0)),
        "traversal": float(np.clip(traversal_persistence, 0.0, 1.0)),
        "polarity": float(np.clip(polarity_consistency, 0.0, 1.0)),
        "position": float(np.clip(position_stability, 0.0, 1.0)),
        "signal": float(np.clip(multiscan_signal_consistency, 0.0, 1.0)),
        "multiresolution": float(np.clip(multiresolution_consensus, 0.0, 1.0)),
        "depth": float(np.clip(depth_cross_scan_consistency, 0.0, 1.0)),
        "geometry": float(np.clip(geometry_consistency, 0.0, 1.0)),
        "registration": 1.0 - registration_unc,
        "scan_evidence": float(
            np.clip(np.mean(evidence_values) if evidence_values else 0.0, 0.0, 1.0)
        ),
    }

    # A multi-scan evidence score rewards independent coverage and stable
    # measurements; it is deliberately not labelled as a probability.
    weights = {
        "scan_evidence": 0.22,
        "detection": 0.14,
        "direction": 0.08,
        "spacing": 0.08,
        "traversal": 0.08,
        "polarity": 0.06,
        "position": 0.10,
        "signal": 0.07,
        "multiresolution": 0.06,
        "depth": 0.05,
        "geometry": 0.04,
        "registration": 0.02,
    }
    score = float(sum(weights[k] * component_stability[k] for k in weights))
    if n <= 1:
        score = min(score, 0.45)

    instability = (
        0.20 * depth_unc
        + 0.16 * geom_unc
        + 0.16 * signal_unc
        + 0.18 * position_unc
        + 0.10 * registration_unc
        + 0.20 * (1.0 - detection_rate)
    )
    evidence_unc = float(np.clip(instability, 0.0, 1.0))

    # Leave-one-out stability: how much the aggregate scan-level evidence
    # changes when one observation is removed. With <3 scans there is no
    # meaningful jackknife (one remainder is not a distribution), so
    # uncertainty stays explicit instead of pretending a robust estimate.
    # v0.4.2 (audit F-19): a 2-scan site used to report perfect 1.0
    # stability -- exactly where the sample is smallest. Both n=1 and n=2
    # now report the neutral 0.5; a genuine jackknife needs n>=3.
    if n < 3:
        loo = 0.5
    else:
        values = np.asarray(evidence_values, dtype=float)
        full = float(np.mean(values)) if len(values) else 0.0
        deltas = []
        for i in range(len(values)):
            remain = np.delete(values, i)
            if remain.size:
                deltas.append(abs(float(np.mean(remain)) - full))
        loo = float(np.clip(1.0 - (np.mean(deltas) / max(0.25, abs(full))), 0.0, 1.0))

    flags: list[str] = []
    if n <= 1:
        flags.append("single-scan")
    if n < 3:
        # v0.4.2 (audit F-19): no jackknife exists below 3 scans, so the
        # neutral 0.5 above must read as "unavailable", never as a measured
        # stability value.
        flags.append("leave-one-out-unavailable")
    if detection_rate < 0.5:
        flags.append("low-scan-coverage")
    if position_unc > 0.45:
        flags.append("position-unstable")
    if depth_unc > 0.45 or depth_cross_scan_consistency < 0.55:
        flags.append("depth-uncertain")
    if geom_unc > 0.45 or geometry_consistency < 0.55:
        flags.append("geometry-variable")
    if signal_unc > 0.45 or multiscan_signal_consistency < 0.55:
        flags.append("signal-variable")
    if registration_unc > 0.45:
        flags.append("registration-uncertain")
    if loo < 0.65 and n >= 3:
        flags.append("leave-one-out-sensitive")
    if polarity_consistency < 0.65:
        flags.append("polarity-variable")

    return UncertaintyProfile(
        evidence_score=round(float(np.clip(score, 0.0, 1.0)), 3),
        evidence_uncertainty=round(evidence_unc, 3),
        depth_uncertainty=round(depth_unc, 3),
        geometry_uncertainty=round(geom_unc, 3),
        signal_uncertainty=round(signal_unc, 3),
        position_uncertainty=round(position_unc, 3),
        registration_uncertainty=round(registration_unc, 3),
        leave_one_out_stability=round(loo, 3),
        effective_scan_count=n,
        flags=tuple(flags),
        components={k: round(float(v), 3) for k, v in component_stability.items()},
    )

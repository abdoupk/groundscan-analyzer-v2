"""Experimental soil-aware models built on the five exported soil factors.

This module is deliberately conservative:

* The current detector remains the baseline unless ``soil_mode='experimental'``
  is requested.
* The experimental background model is an A/B diagnostic only; it does not
  replace candidate extraction or classification.
* The depth model can only compute a physically meaningful depth from
  two-way-travel-time (TWT) data. The OKM ``Depth Z [m]`` field is treated as a
  device-reported estimate and is never silently re-derived from soil metadata.

The EM velocity relation used here is the standard low-loss approximation
v = c / sqrt(epsilon_r * mu_r). See US EPA environmental geophysics guidance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from ..core.background import multiscale_zscore, robust_zscore
from ..core.grid import Grid2D
from ..models import ScanData, ScanMetadata
from .context import soil_confounder_context

C_M_PER_NS = 0.299792458


@dataclass(frozen=True)
class SoilPhysicsDiagnostics:
    dielectric_constant: float | None
    relative_permeability: float | None
    mineralization_pct: float | None
    humidity_pct: float | None
    homogeneity_pct: float | None
    refractive_index: float | None
    wave_velocity_m_per_ns: float | None
    relative_velocity_to_air: float | None
    depth_model_status: str


def _finite_positive(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x) or x <= 0:
        return None
    return x


def soil_physics_diagnostics(metadata: ScanMetadata) -> SoilPhysicsDiagnostics:
    """Return transparent EM propagation diagnostics from the soil metadata."""
    eps_r = _finite_positive(getattr(metadata, "dielectric_constant", None))
    mu_r = _finite_positive(getattr(metadata, "relative_permeability", None))
    refractive_index = None
    velocity = None
    relative_velocity = None
    status = "unavailable: positive dielectric constant and relative permeability are required"
    if eps_r is not None and mu_r is not None:
        refractive_index = float(np.sqrt(eps_r * mu_r))
        velocity = float(C_M_PER_NS / refractive_index)
        relative_velocity = float(1.0 / refractive_index)
        status = "TWT required for independent corrected depth; soil factors provide velocity context only"
    return SoilPhysicsDiagnostics(
        dielectric_constant=eps_r,
        relative_permeability=mu_r,
        mineralization_pct=getattr(metadata, "mineralization_pct", None),
        humidity_pct=getattr(metadata, "humidity_pct", None),
        homogeneity_pct=getattr(metadata, "homogeneity_pct", None),
        refractive_index=refractive_index,
        wave_velocity_m_per_ns=velocity,
        relative_velocity_to_air=relative_velocity,
        depth_model_status=status,
    )


def depth_from_twt_ns(
    twt_ns: np.ndarray[Any, Any] | Sequence[float] | float, metadata: ScanMetadata
) -> np.ndarray[Any, Any]:
    """Compute depth [m] from TWT [ns] using soil epsilon/mu.

    This is a physics-based conversion, not a correction of the device's
    reported depth. It requires positive dielectric constant and relative
    permeability. The calculation is the low-loss approximation.
    """
    eps_r = _finite_positive(getattr(metadata, "dielectric_constant", None))
    mu_r = _finite_positive(getattr(metadata, "relative_permeability", None))
    if eps_r is None or mu_r is None:
        raise ValueError("positive dielectric_constant and relative_permeability are required")
    twt = np.asarray(twt_ns, dtype=float)
    depth = 0.5 * C_M_PER_NS * twt / np.sqrt(eps_r * mu_r)
    return np.where(np.isfinite(twt), depth, np.nan)


def _softmax(values: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    shifted = values - np.nanmax(values)
    exp = np.exp(shifted)
    total = float(np.nansum(exp))
    return exp / total if total > 0 else np.full(values.shape, 1.0 / max(values.size, 1))


def soil_scale_weights(
    scales: Sequence[int], homogeneity_pct: float | None
) -> np.ndarray[Any, Any]:
    """Return experimental scale weights driven only by exported homogeneity.

    Low homogeneity favors smaller local background windows; high homogeneity
    favors broader windows. This mapping is explicitly heuristic and is not
    used by default in the detector.
    """
    normalized_scales = np.asarray([max(1, int(s) | 1) for s in scales], dtype=float)
    if normalized_scales.size == 0:
        return np.array([], dtype=float)
    h = np.nan
    try:
        h = float(homogeneity_pct) / 100.0 if homogeneity_pct is not None else np.nan
    except (TypeError, ValueError):
        h = np.nan
    if not np.isfinite(h):
        return np.full(normalized_scales.shape, 1.0 / normalized_scales.size)
    h = float(np.clip(h, 0.0, 1.0))
    if normalized_scales.size == 1:
        return np.ones(1, dtype=float)
    ranks = (normalized_scales - normalized_scales.min()) / max(
        normalized_scales.max() - normalized_scales.min(), 1e-12
    )
    temperature = (2.0 * h - 1.0) * 1.5
    return _softmax(temperature * ranks)


def soil_aware_background_zscore(
    grid: Grid2D,
    scales: Sequence[int] = (3, 5, 9, 15),
    homogeneity_pct: float | None = None,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Compute an experimental homogeneity-weighted background z-score.

    Returns ``(weighted_z, weights, residual)``. The caller must treat this as
    an alternative diagnostic channel, not a validated replacement detector.
    """
    from ..core.background import remove_background

    viable_sizes: list[int] = []
    residuals: list[np.ndarray[Any, Any]] = []
    z_channels: list[np.ndarray[Any, Any]] = []
    for raw_size in scales:
        size = max(1, int(raw_size))
        if size % 2 == 0:
            size += 1
        if min(grid.signal.shape) < size:
            continue
        residual = remove_background(grid, method="median", size=size)
        residuals.append(np.asarray(residual, dtype=float))
        z_channels.append(robust_zscore(residual))
        viable_sizes.append(size)

    if not residuals:
        residual = remove_background(grid, method="none")
        return robust_zscore(residual), np.array([], dtype=float), residual

    weights = soil_scale_weights(viable_sizes, homogeneity_pct)
    stack_residual = np.stack(residuals, axis=0)
    with np.errstate(invalid="ignore"):
        weighted_residual = np.nansum(stack_residual * weights[:, None, None], axis=0)
    valid_count = np.sum(np.isfinite(stack_residual), axis=0)
    weighted_residual[valid_count == 0] = np.nan
    weighted_z = robust_zscore(weighted_residual)
    return weighted_z, weights, weighted_residual


def soil_background_factor_sweep(
    grid: Grid2D,
    metadata: ScanMetadata,
    scales: Sequence[int] = (3, 5, 9, 15),
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Evaluate each exported soil factor for background-model eligibility.

    This is intentionally conservative. Only ``homogeneity_pct`` is permitted
    to generate an experimental alternative background because it directly
    describes spatial background uniformity. The other four factors are
    recorded as context-only here; using them to reshape the background would
    require a calibrated spatial/physical relationship not present in the
    current data model.
    """
    factors = (
        (
            "dielectric_constant",
            getattr(metadata, "dielectric_constant", None),
            False,
            "propagation/depth context; no calibrated spatial background mapping",
        ),
        (
            "relative_permeability",
            getattr(metadata, "relative_permeability", None),
            False,
            "propagation/depth context; no calibrated spatial background mapping",
        ),
        (
            "mineralization_pct",
            getattr(metadata, "mineralization_pct", None),
            False,
            "confounder/risk context; no calibrated anomaly-background correction",
        ),
        (
            "humidity_pct",
            getattr(metadata, "humidity_pct", None),
            False,
            "confounder context; no calibrated anomaly-background correction",
        ),
        (
            "homogeneity_pct",
            getattr(metadata, "homogeneity_pct", None),
            True,
            "experimental scale weighting for background estimation",
        ),
    )
    out: dict[str, Any] = {
        "threshold": float(threshold),
        "experimental_factor": "homogeneity_pct",
        "factors": {},
    }
    for name, value, eligible, reason in factors:
        record: dict[str, Any] = {
            "value": value,
            "available": value is not None,
            "background_experiment_eligible": bool(eligible and value is not None),
            "status": "experimental"
            if eligible and value is not None
            else ("context-only" if value is not None else "unavailable"),
            "reason": reason,
        }
        if eligible and value is not None:
            try:
                z, weights, _ = soil_aware_background_zscore(
                    grid, scales=scales, homogeneity_pct=float(value)
                )
                record["scale_weights"] = [float(w) for w in weights]
                baseline_z, _, _ = multiscale_zscore(grid, scales=tuple(int(s) for s in scales))
                record["ab"] = soil_ab_summary(baseline_z, z, threshold)
            except Exception as exc:
                record["status"] = "error"
                record["reason"] = f"experimental background failed: {exc}"
        out["factors"][name] = record
    return out


def soil_context(metadata: ScanMetadata) -> dict[str, Any]:
    """Return an explicit five-factor soil context with non-overlapping roles.

    This function is intentionally descriptive. It does not invent a combined
    correction coefficient. Each exported factor is assigned to the narrowest
    role that can be justified without field calibration:
      - dielectric/permeability: EM propagation and TWT depth context
      - mineralization/humidity: confounder context
      - homogeneity: background-model context
    """
    eps_r = _finite_positive(getattr(metadata, "dielectric_constant", None))
    mu_r = _finite_positive(getattr(metadata, "relative_permeability", None))
    mineralization = getattr(metadata, "mineralization_pct", None)
    humidity = getattr(metadata, "humidity_pct", None)
    homogeneity = getattr(metadata, "homogeneity_pct", None)

    def _pct(value: Any) -> float | None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        return float(np.clip(v, 0.0, 100.0)) if np.isfinite(v) else None

    return {
        "soil_type": getattr(metadata, "soil_type", None),
        "factors": {
            "dielectric_constant": eps_r,
            "relative_permeability": mu_r,
            "mineralization_pct": _pct(mineralization),
            "humidity_pct": _pct(humidity),
            "homogeneity_pct": _pct(homogeneity),
        },
        "roles": {
            "propagation": ["dielectric_constant", "relative_permeability"],
            "confounder_context": ["mineralization_pct", "humidity_pct"],
            "background_context": ["homogeneity_pct"],
        },
        "corrections_applied": {
            "signal": False,
            "anomaly": False,
            "device_depth": False,
        },
        "calibration_required_for_detector_change": True,
    }


def integrated_soil_model(
    metadata: ScanMetadata,
    *,
    soil_model: dict[str, Any] | None = None,
    depth_channel: dict[str, Any] | None = None,
    background_sweep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one explicit five-factor soil model profile from existing diagnostics.

    This is an integration/provenance layer, not a new detector.  It combines
    propagation, confounder, background and depth channels without inventing a
    combined correction coefficient.  The baseline detector remains authoritative.
    """
    context = soil_context(metadata)
    physics = soil_physics_diagnostics(metadata)
    confounder = soil_confounder_context(metadata)
    model = soil_model if isinstance(soil_model, dict) else {}
    depth_info = (
        depth_channel if isinstance(depth_channel, dict) else model.get("depth_diagnostic", {})
    )
    sweep = (
        background_sweep
        if isinstance(background_sweep, dict)
        else model.get("background_factor_sweep", {})
    )

    factors = context.get("factors", {})
    available = [name for name, value in factors.items() if value is not None]
    finite_count = len(available)
    completeness = float(finite_count / 5.0)

    eps_ok = physics.dielectric_constant is not None
    mu_ok = physics.relative_permeability is not None
    propagation_status = "available" if eps_ok and mu_ok else "unavailable"
    twt_status = "available" if bool(depth_info.get("available")) else "unavailable"

    homogeneity = factors.get("homogeneity_pct")
    humidity = factors.get("humidity_pct")
    mineralization = factors.get("mineralization_pct")
    background_status = "experimental" if homogeneity is not None else "context-only"

    factor_roles = {
        "dielectric_constant": "propagation/depth",
        "relative_permeability": "propagation/depth",
        "mineralization_pct": "confounder/risk",
        "humidity_pct": "confounder/context",
        "homogeneity_pct": "background context",
    }

    return {
        "model_version": "soil-integrated",
        "soil_type": context.get("soil_type"),
        "factor_count": finite_count,
        "completeness": completeness,
        "factor_roles": factor_roles,
        "factors": factors,
        "propagation": {
            "status": propagation_status,
            "dielectric_constant": physics.dielectric_constant,
            "relative_permeability": physics.relative_permeability,
            "refractive_index": physics.refractive_index,
            "wave_velocity_m_per_ns": physics.wave_velocity_m_per_ns,
            "requires_twt_for_depth": True,
        },
        "background": {
            "status": background_status,
            "homogeneity_pct": homogeneity,
            "experimental_detector_replacement": False,
            "sweep_factors": list((sweep.get("factors") or {}).keys())
            if isinstance(sweep, dict)
            else [],
        },
        "confounders": {
            "mineralization_pct": mineralization,
            "humidity_pct": humidity,
            "mineralization_risk": confounder.get("mineralization_risk", 0.0),
            "flags": list(confounder.get("flags") or []),
        },
        "depth": {
            "status": twt_status,
            "source": depth_info.get("source") if isinstance(depth_info, dict) else None,
            "replaces_device_depth": False,
            "calibrated": False,
        },
        "detector": {
            "baseline_preserved": True,
            "signal_correction_applied": False,
            "anomaly_correction_applied": False,
            "candidate_extraction_replaced": False,
            "calibration_required_for_detector_change": True,
        },
    }


def soil_twt_depth_grid(scan: ScanData, metadata: ScanMetadata) -> Grid2D | None:
    """Return a Grid2D whose depth channel is derived from explicit TWT.

    The returned grid reuses the scan's x/y/grid topology and replaces only the
    depth channel with the soil-aware TWT-derived depth. Signal is untouched.
    Returns ``None`` when TWT or the required soil propagation factors are not
    available.
    """
    twt = getattr(scan, "twt_ns", None)
    if twt is None:
        return None
    try:
        depth_values = depth_from_twt_ns(twt, metadata)
    except (TypeError, ValueError):
        return None
    aux_scan = replace(scan, z=np.asarray(depth_values, dtype=float), twt_ns=None)
    from ..core.grid import reconstruct_grid

    return reconstruct_grid(aux_scan)


def compare_depth_channels(device_grid: Grid2D, twt_depth_grid: Grid2D) -> dict[str, Any]:
    """Compare device-reported depth with TWT+soil-derived depth without replacing it."""
    device = np.asarray(device_grid.depth, dtype=float)
    twt = np.asarray(twt_depth_grid.depth, dtype=float)
    if device.shape != twt.shape:
        return {
            "available": False,
            "reason": "Device and TWT-derived depth grids have different shapes.",
        }
    valid = np.isfinite(device) & np.isfinite(twt)
    count = int(np.count_nonzero(valid))
    if count == 0:
        return {
            "available": False,
            "reason": "No cells contain both device depth and TWT-derived depth.",
        }
    d = device[valid]
    t = twt[valid]
    delta = t - d
    corr = (
        float(np.corrcoef(d, t)[0, 1])
        if count >= 2 and np.std(d) > 0 and np.std(t) > 0
        else float("nan")
    )
    return {
        "available": True,
        "count": count,
        "correlation": corr,
        "bias_m": float(np.mean(delta)),
        "mae_m": float(np.mean(np.abs(delta))),
        "rmse_m": float(np.sqrt(np.mean(np.square(delta)))),
        "median_abs_delta_m": float(np.median(np.abs(delta))),
        "device_depth_median_m": float(np.median(d)),
        "twt_depth_median_m": float(np.median(t)),
        "replaces_device_depth": False,
    }


def soil_depth_diagnostic(scan: ScanData, metadata: ScanMetadata) -> dict[str, Any]:
    """Summarize a TWT-derived depth channel without replacing device depth."""
    twt = getattr(scan, "twt_ns", None)
    if twt is None:
        return {"available": False, "reason": "No explicit TWT field was exported."}
    try:
        arr = np.asarray(twt, dtype=float)
        finite = np.isfinite(arr)
    except (TypeError, ValueError):
        return {"available": False, "reason": "TWT field could not be converted to numeric values."}
    if not np.any(finite):
        return {"available": False, "reason": "TWT field contains no finite values."}
    try:
        depth = depth_from_twt_ns(arr, metadata)
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    vals = depth[np.isfinite(depth)]
    return {
        "available": True,
        "source": "explicit_twt_ns",
        "count": int(vals.size),
        "depth_min_m": float(np.min(vals)),
        "depth_max_m": float(np.max(vals)),
        "depth_median_m": float(np.median(vals)),
        "depth_mean_m": float(np.mean(vals)),
        "formula": "0.5 * c * TWT / sqrt(epsilon_r * mu_r)",
        "replaces_device_depth": False,
    }


def soil_ab_summary(
    baseline_z: np.ndarray[Any, Any],
    soil_z: np.ndarray[Any, Any],
    threshold: float,
) -> dict[str, float]:
    """Compare baseline and experimental soil-aware maps without changing detection."""
    a = np.asarray(baseline_z, dtype=float)
    b = np.asarray(soil_z, dtype=float)
    valid = np.isfinite(a) & np.isfinite(b)
    if not np.any(valid):
        return {
            "correlation": float("nan"),
            "flag_overlap": float("nan"),
            "baseline_flag_fraction": 0.0,
            "soil_flag_fraction": 0.0,
        }
    av = a[valid]
    bv = b[valid]
    correlation = (
        float(np.corrcoef(av, bv)[0, 1])
        if av.size >= 2 and np.std(av) > 0 and np.std(bv) > 0
        else float("nan")
    )
    a_mask = np.abs(av) >= float(threshold)
    b_mask = np.abs(bv) >= float(threshold)
    union = np.count_nonzero(a_mask | b_mask)
    inter = np.count_nonzero(a_mask & b_mask)
    return {
        "correlation": correlation,
        "flag_overlap": float(inter / union) if union else 1.0,
        "baseline_flag_fraction": float(np.mean(a_mask)),
        "soil_flag_fraction": float(np.mean(b_mask)),
    }


def attach_soil_model_diagnostics(
    metadata: ScanMetadata,
    *,
    baseline_z: np.ndarray[Any, Any] | None = None,
    soil_z: np.ndarray[Any, Any] | None = None,
    soil_weights: np.ndarray[Any, Any] | None = None,
    threshold: float = 3.0,
    soil_mode: str = "diagnostic",
) -> dict[str, Any]:
    """Attach the soil-aware model results to metadata provenance."""
    physics = soil_physics_diagnostics(metadata)
    result: dict[str, Any] = {
        "mode": str(soil_mode),
        "physics": {
            "refractive_index": physics.refractive_index,
            "wave_velocity_m_per_ns": physics.wave_velocity_m_per_ns,
            "relative_velocity_to_air": physics.relative_velocity_to_air,
            "depth_model_status": physics.depth_model_status,
        },
        "background": {
            "applied_to_detector": False,
            "calibrated": False,
            "weights": [float(v) for v in (soil_weights if soil_weights is not None else [])],
        },
        "ab": None,
    }
    if baseline_z is not None and soil_z is not None:
        result["ab"] = soil_ab_summary(baseline_z, soil_z, threshold)
    metadata.extra = dict(metadata.extra or {})
    metadata.extra["soil_model"] = result
    return result

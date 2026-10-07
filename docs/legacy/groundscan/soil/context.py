"""Soil-context metadata normalization and diagnostics.

This module deliberately does not modify signal/anomaly values. It provides a
normalized representation of the five OKM soil factors and transparent
completeness/range diagnostics so later soil-aware models can be calibrated
without changing the current detector baseline.
"""

from __future__ import annotations

from typing import Any

from ..models import ScanMetadata

SOIL_FACTORS = (
    "dielectric_constant",
    "relative_permeability",
    "mineralization_pct",
    "humidity_pct",
    "homogeneity_pct",
)

PERCENT_FACTORS = ("mineralization_pct", "humidity_pct", "homogeneity_pct")


MINERALIZATION_FLAG_THRESHOLD = 30.0
MINERALIZATION_HIGH_THRESHOLD = 60.0


def mineralization_risk_from_pct(value: float | None) -> float:
    """Convert reported mineralization percent to the legacy bounded risk.

    The transform is intentionally preserved from the pre-Soil-Context model: it
    is a screening indicator, not a calibrated physical false-positive model.
    Keeping it here makes mineralization part of the unified soil context while
    preserving backward-compatible behavior.
    """
    if value is None:
        return 0.0
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return 0.0
    if pct != pct:
        return 0.0
    return max(0.0, min(1.0, pct / 100.0))


def soil_confounder_context(metadata: ScanMetadata) -> dict[str, Any]:
    """Return the non-material soil/confounder context without detector correction."""
    context = build_soil_context(metadata)
    factors = context["factors"]
    mineralization = factors.get("mineralization_pct")
    humidity = factors.get("humidity_pct")
    homogeneity = factors.get("homogeneity_pct")
    flags: list[str] = []
    risk = mineralization_risk_from_pct(mineralization)
    if mineralization is not None and risk >= MINERALIZATION_HIGH_THRESHOLD / 100.0:
        flags.append("high-mineralization-risk")
    elif mineralization is not None and risk >= MINERALIZATION_FLAG_THRESHOLD / 100.0:
        flags.append("elevated-mineralization-risk")
    return {
        "mineralization_risk": risk,
        "humidity_pct": humidity,
        "homogeneity_pct": homogeneity,
        "flags": flags,
        "used_for_detector_correction": False,
        "calibration_required_for_detector_change": True,
    }


def build_soil_context(metadata: ScanMetadata) -> dict[str, Any]:
    values = {name: getattr(metadata, name, None) for name in SOIL_FACTORS}
    present = [name for name, value in values.items() if value is not None]
    finite = []
    invalid = []
    for name, value in values.items():
        if value is None:
            continue
        try:
            finite_value = float(value)
        except (TypeError, ValueError):
            invalid.append(name)
            continue
        if finite_value != finite_value:
            invalid.append(name)
            continue
        finite.append(name)
        if name in PERCENT_FACTORS and not 0.0 <= finite_value <= 100.0:
            invalid.append(name)
    return {
        "soil_type": metadata.soil_type,
        "factors": {name: values[name] for name in SOIL_FACTORS},
        "present_factors": present,
        "finite_factors": finite,
        "invalid_factors": list(dict.fromkeys(invalid)),
        "completeness": len(finite) / len(SOIL_FACTORS),
        "source": "scan_metadata",
        "used_for_signal_correction": False,
        "used_for_anomaly_correction": False,
        "used_for_depth_correction": False,
        "soil_context_model": "five-factor-context",
        "mineralization_role": "confounder-risk-baseline",
    }


def attach_soil_context(metadata: ScanMetadata) -> dict[str, Any]:
    context = build_soil_context(metadata)
    extra = dict(metadata.extra or {})
    extra["soil_context"] = context
    metadata.extra = extra
    return context


def soil_context_summary(metadata: ScanMetadata) -> str:
    context = build_soil_context(metadata)
    if not context["finite_factors"]:
        return "No exported soil factors were available."
    if context["invalid_factors"]:
        return f"{len(context['finite_factors'])}/5 soil factors available; invalid values: {', '.join(context['invalid_factors'])}."
    return f"{len(context['finite_factors'])}/5 soil factors available; no signal/depth correction is applied."

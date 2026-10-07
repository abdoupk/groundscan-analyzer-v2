"""Diagnostic background-factor attribution audit for v0.2.91.

This module does not change production analysis. It uses the independent
synthetic geology target plans and varies one background component at a time
before the current production broad-response representation. The goal is to
identify which background property causes broad/geological extraction loss,
not to tune production thresholds to a generator.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.core.anomaly import _broad_component_selection, _regional_trend_zscore
from groundscan.core.grid import Grid2D
from groundscan.validation.synthetic_core.core import SyntheticTarget
from groundscan_research.forward_background_interaction import (
    BROAD_THRESHOLD,
    MATCH_RADIUS_M,
    MIN_AREA_FRACTION,
    MIN_SPAN_FRACTION,
    _target_mask,
)
from groundscan_research.synthetic_generator_independence import (
    _master_plan,
    _response_b,
    _response_c,
)

GENERATORS = ("B", "C")


def _coords(plan: dict) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, float(plan["width"]), int(plan["nx"]))
    y = np.linspace(0.0, float(plan["height"]), int(plan["ny"]))
    return np.meshgrid(y, x, indexing="ij")


def _components(
    generator: str, xx: np.ndarray, yy: np.ndarray, *, scale: float = 1.0
) -> dict[str, np.ndarray]:
    """Return native non-constant background components for one generator."""
    if generator == "B":
        x0 = float(np.mean(xx))
        y0 = float(np.mean(yy))
        plane = 0.11 * (xx - x0) - 0.07 * (yy - y0)
        periodic = 2.2 * np.sin((xx - x0) / (7.0 * scale)) + 1.4 * np.cos((yy - y0) / (5.0 * scale))
        return {"trend_plane": plane, "periodic": periodic}
    x0 = float(np.mean(xx))
    y0 = float(np.mean(yy))
    radius = np.sqrt((xx - x0) ** 2 + (yy - y0) ** 2)
    radial = 0.16 * radius
    periodic = 1.7 * np.sin(((xx - x0) + 1.8 * (yy - y0)) / (9.5 * scale)) + 0.9 * np.sin(
        (yy - y0) / (3.7 * scale)
    )
    return {"radial_curvature": radial, "periodic": periodic}


def _baseline_constant(generator: str) -> float:
    return 142.0 if generator == "B" else 118.0


def _grid(field: np.ndarray, plan: dict) -> Grid2D:
    ny, nx = field.shape
    return Grid2D(
        x_centers=np.linspace(0.0, float(plan["width"]), nx),
        y_centers=np.linspace(0.0, float(plan["height"]), ny),
        signal=np.asarray(field, dtype=float),
        depth=np.full_like(field, 5.0, dtype=float),
        counts=np.ones_like(field, dtype=int),
    )


def _metrics(field: np.ndarray, plan: dict, target: SyntheticTarget) -> dict:
    z = _regional_trend_zscore(_grid(field, plan))
    labels, _, n = _broad_component_selection(
        _grid(field, plan), z, BROAD_THRESHOLD, MIN_AREA_FRACTION, MIN_SPAN_FRACTION
    )
    mask = _target_mask(plan, target, field.shape)
    valid = np.isfinite(z)
    vals = np.abs(z[mask & valid])
    x = np.linspace(0.0, float(plan["width"]), field.shape[1])
    y = np.linspace(0.0, float(plan["height"]), field.shape[0])
    distances: list[float] = []
    false_components = 0
    for cid in range(1, int(n) + 1):
        ys, xs = np.where(labels == cid)
        if not len(xs):
            continue
        distances.append(float(np.hypot(np.mean(x[xs]) - target.x, np.mean(y[ys]) - target.y)))
        overlap = float(np.count_nonzero((labels == cid) & mask)) / max(
            int(np.count_nonzero(labels == cid)), 1
        )
        if overlap < 0.25:
            false_components += 1
    nearest = min(distances) if distances else None
    return {
        "component_hit": bool(nearest is not None and nearest <= MATCH_RADIUS_M),
        "nearest_component_distance_m": nearest,
        "components": int(n),
        "false_components": int(false_components),
        "target_peak_abs_z": float(np.max(vals)) if vals.size else 0.0,
        "target_mean_abs_z": float(np.mean(vals)) if vals.size else 0.0,
        "target_fraction_abs_z_ge_2": float(np.mean(vals >= 2.0)) if vals.size else 0.0,
    }


def _target_response(
    plan: dict, generator: str, xx: np.ndarray, yy: np.ndarray, target: SyntheticTarget
) -> np.ndarray:
    return _response_b(xx, yy, target) if generator == "B" else _response_c(xx, yy, target)


def _native_scene_variants(
    plan: dict, generator: str, target: SyntheticTarget
) -> dict[str, np.ndarray]:
    yy, xx = _coords(plan)
    base = _baseline_constant(generator)
    target_response = _target_response(plan, generator, xx, yy, target)
    comps = _components(generator, xx, yy)
    zero = np.full_like(xx, base, dtype=float)
    variants: dict[str, np.ndarray] = {"target_only": zero + target_response}
    for name, comp in comps.items():
        variants[f"{name}_only"] = zero + comp
        variants[f"target_plus_{name}"] = zero + target_response + comp
    variants["full_native_background"] = (
        zero + target_response + sum(comps.values(), np.zeros_like(xx))
    )
    return variants


def _strength_scene(
    plan: dict, generator: str, target: SyntheticTarget, component: str, strength: float
) -> np.ndarray:
    yy, xx = _coords(plan)
    base = _baseline_constant(generator)
    response = _target_response(plan, generator, xx, yy, target)
    comp = _components(generator, xx, yy)[component]
    return base + response + float(strength) * comp


def _scale_scene(
    plan: dict, generator: str, target: SyntheticTarget, component: str, scale: float
) -> np.ndarray:
    yy, xx = _coords(plan)
    base = _baseline_constant(generator)
    response = _target_response(plan, generator, xx, yy, target)
    comp = _components(generator, xx, yy, scale=float(scale))[component]
    return base + response + comp


def _native_rows(seeds: tuple[int, ...], count: int) -> list[dict]:
    rows: list[dict] = []
    for seed in map(int, seeds):
        for i, plan in enumerate(_master_plan(seed, count)):
            geos = [t for t in plan["targets"] if t.kind in {"geology", "geological"}]
            if not geos:
                continue
            target = geos[0]
            for generator in GENERATORS:
                variants = _native_scene_variants(plan, generator, target)
                for variant, field in variants.items():
                    rows.append({
                        "seed": seed,
                        "site": plan["scenario"],
                        "generator": generator,
                        "family": "native_components",
                        "variant": variant,
                        **_metrics(field, plan, target),
                    })
    return rows


def _strength_rows(seeds: tuple[int, ...], count: int) -> list[dict]:
    rows: list[dict] = []
    levels = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
    for seed in map(int, seeds):
        for i, plan in enumerate(_master_plan(seed, count)):
            geos = [t for t in plan["targets"] if t.kind in {"geology", "geological"}]
            if not geos:
                continue
            target = geos[0]
            for generator in GENERATORS:
                for component in _components(generator, *_coords(plan)).keys():
                    for strength in levels:
                        field = _strength_scene(plan, generator, target, component, strength)
                        rows.append({
                            "seed": seed,
                            "site": plan["scenario"],
                            "generator": generator,
                            "family": "strength_sweep",
                            "component": component,
                            "level": float(strength),
                            **_metrics(field, plan, target),
                        })
    return rows


def _scale_rows(seeds: tuple[int, ...], count: int) -> list[dict]:
    rows: list[dict] = []
    levels = (0.5, 0.75, 1.0, 1.5, 2.0)
    for seed in map(int, seeds):
        for i, plan in enumerate(_master_plan(seed, count)):
            geos = [t for t in plan["targets"] if t.kind in {"geology", "geological"}]
            if not geos:
                continue
            target = geos[0]
            for generator in GENERATORS:
                for component in _components(generator, *_coords(plan)).keys():
                    # Plane/radial curvature has no wavelength parameter, so scale sweep is only meaningful for periodic components.
                    if component != "periodic":
                        continue
                    for scale in levels:
                        field = _scale_scene(plan, generator, target, component, scale)
                        rows.append({
                            "seed": seed,
                            "site": plan["scenario"],
                            "generator": generator,
                            "family": "spatial_scale_sweep",
                            "component": component,
                            "level": float(scale),
                            **_metrics(field, plan, target),
                        })
    return rows


def _summarize(rows: list[dict], *, keys: tuple[str, ...]) -> dict:
    out: dict = {}
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        group = tuple(row.get(k) for k in keys)
        groups.setdefault(group, []).append(row)
    for group, group_rows in groups.items():
        key = "|".join(str(v) for v in group)
        out[key] = {
            "records": len(group_rows),
            "hit_rate": float(np.mean([r["component_hit"] for r in group_rows])),
            "mean_peak_abs_z": float(np.mean([r["target_peak_abs_z"] for r in group_rows])),
            "mean_target_abs_z": float(np.mean([r["target_mean_abs_z"] for r in group_rows])),
            "mean_fraction_abs_z_ge_2": float(
                np.mean([r["target_fraction_abs_z_ge_2"] for r in group_rows])
            ),
            "mean_components": float(np.mean([r["components"] for r in group_rows])),
            "mean_false_components": float(np.mean([r["false_components"] for r in group_rows])),
        }
    return out


def _write_report(out: Path, payload: dict) -> None:
    lines = [
        "# GroundScan Analyzer v0.2.91 — Background Factor Attribution",
        "",
        "> Diagnostic-only. No production detector, classifier, threshold, registration, fusion, or scoring behavior changed.",
        "",
        f"Seeds: **{len(payload['seeds'])}**; sites/seed: **{payload['count']}**; geology records/generator: **{payload['geology_records_per_generator']}**.",
        "",
        "## Native background components",
        "",
        "| Generator | Variant | Hit | Peak | Target abs-z | ≥2 fraction | Components | False comps |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    native = payload["native_summary"]
    for generator in GENERATORS:
        for variant in [
            v
            for v in sorted({
                k.split("|", 2)[2]
                for k in native
                if k.startswith(generator + "|native_components|")
            })
        ]:
            s = native[f"{generator}|native_components|{variant}"]
            lines.append(
                f"| {generator} | {variant} | {s['hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | {s['mean_target_abs_z']:.3f} | "
                f"{s['mean_fraction_abs_z_ge_2']:.3f} | {s['mean_components']:.2f} | {s['mean_false_components']:.2f} |"
            )
    lines += [
        "",
        "## Component-strength sweeps",
        "",
        "| Generator | Component | Strength | Hit | Peak | False comps |",
        "|---|---|---:|---:|---:|---:|",
    ]
    strength = payload["strength_summary"]
    parsed = []
    for key, s in strength.items():
        g, _, component, level = key.split("|", 3)
        parsed.append((g, component, float(level), s))
    for g, component, level, s in sorted(parsed):
        lines.append(
            f"| {g} | {component} | {level:g} | {s['hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | {s['mean_false_components']:.2f} |"
        )
    lines += [
        "",
        "## Periodic spatial-scale sweeps",
        "",
        "| Generator | Scale multiplier | Hit | Peak | False comps |",
        "|---|---:|---:|---:|---:|",
    ]
    scale = payload["scale_summary"]
    parsed = []
    for key, s in scale.items():
        g, _, component, level = key.split("|", 3)
        parsed.append((g, component, float(level), s))
    for g, component, level, s in sorted(parsed):
        lines.append(
            f"| {g} | {level:g} | {s['hit_rate']:.3f} | {s['mean_peak_abs_z']:.3f} | {s['mean_false_components']:.2f} |"
        )
    lines += ["", "## Attribution", ""]
    for generator in GENERATORS:
        base = native[f"{generator}|native_components|target_only"]
        full = native[f"{generator}|native_components|full_native_background"]
        lines.append(
            f"- **{generator}:** target-only hit **{base['hit_rate']:.3f}** → full native background **{full['hit_rate']:.3f}** "
            f"(Δ {full['hit_rate'] - base['hit_rate']:+.3f})."
        )
        comp_names = [
            k.split("|", 2)[2]
            for k in native
            if k.startswith(generator + "|native_components|target_plus_")
        ]
        for component in sorted(comp_names):
            s = native[f"{generator}|native_components|{component}"]
            delta = s["hit_rate"] - base["hit_rate"]
            lines.append(
                f"  - Adding **{component.removeprefix('target_plus_')}** alone: hit Δ **{delta:+.3f}**; peak Δ **{s['mean_peak_abs_z'] - base['mean_peak_abs_z']:+.3f}**."
            )
    lines += [
        "",
        "## Decision",
        "",
        "Diagnostic only. No production change is justified by this audit alone. A production change should require a component-independent representation that improves B and C while preserving the frozen and hard regression gates.",
        "",
        "## Validation boundary",
        "",
        "Synthetic software-validation measurements only. They do not establish real-device field detection performance or prove a geological structure, cavity, tunnel, metal, gold, or mineral in field data.",
    ]
    (out / "background_factor_attribution.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_background_factor_attribution(
    out_dir: str | Path,
    *,
    seeds: tuple[int, ...] = tuple(range(8911, 8919)),
    count: int = 24,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    native_rows = _native_rows(seeds, count)
    strength_rows = _strength_rows(seeds, count)
    scale_rows = _scale_rows(seeds, count)
    b_rows = [r for r in native_rows if r["generator"] == "B"]
    b_variants = len({r["variant"] for r in b_rows})
    geology_records = len(b_rows) // max(b_variants, 1)
    payload = {
        "version": "0.2.91",
        "benchmark": "background_factor_attribution",
        "seeds": list(map(int, seeds)),
        "count": int(count),
        "geology_records_per_generator": int(geology_records),
        "same_truth_plans_across_generators": True,
        "production_behavior_changed": False,
        "production_detector_changed": False,
        "production_thresholds_changed": False,
        "production_classifier_changed": False,
        "production_registration_changed": False,
        "production_fusion_changed": False,
        "native_summary": _summarize(native_rows, keys=("generator", "family", "variant")),
        "strength_summary": _summarize(
            strength_rows, keys=("generator", "family", "component", "level")
        ),
        "scale_summary": _summarize(scale_rows, keys=("generator", "family", "component", "level")),
        "records": {"native": native_rows, "strength": strength_rows, "scale": scale_rows},
        "decision": "diagnostic_only_no_production_change",
        "validation_boundary": "Synthetic diagnostic only; no field ground truth, device-calibrated forward model, or material identification.",
    }
    (out / "background_factor_attribution.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8"
    )
    _write_report(out, payload)
    return payload

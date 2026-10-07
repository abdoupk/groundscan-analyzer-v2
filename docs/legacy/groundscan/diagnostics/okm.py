"""OKM signal/data characterization diagnostics.

v0.2.95 adds a scale-free fingerprint layer for comparing exported signal structure
across OKM example files without inferring physical targets or device equivalence.

The characterization layer is deliberately non-destructive: it reads the OKM
export into the standard :class:`~groundscan.models.ScanData` model, measures
format/geometry/signal properties, and optionally records the existing baseline
analyzer signature. It does not alter detector thresholds or production
classification behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

from ..core.grid import Grid2D, reconstruct_grid
from ..io import detect_adapter
from ..models import ScanData, is_metric_coordinates

_DEVICE_PATTERNS = (
    re.compile(r"\bRover\s+C\s*II\b", re.I),
    re.compile(r"\bRover\s+C\s*4\b", re.I),
    re.compile(r"\bRover\s+UC\b", re.I),
    re.compile(r"\beXp\s+4500(?:\s+Professional)?\b", re.I),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sections(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sections: dict[str, dict[str, str]] = {"General": {}}
    current = "General"
    section_re = re.compile(r"^\+\+\+\s*(.+?)\s*\+\+\+$")
    for raw in text.splitlines():
        line = raw.strip().strip('"')
        if not line:
            continue
        m = section_re.match(line)
        if m:
            current = m.group(1)
            sections.setdefault(current, {})
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            sections[current][k.strip()] = v.strip()
    return sections


def _notes_hardware(notes: str | None) -> list[str]:
    text = notes or ""
    hits: list[str] = []
    for pattern in _DEVICE_PATTERNS:
        for m in pattern.finditer(text):
            value = " ".join(m.group(0).split())
            if value not in hits:
                hits.append(value)
    return hits


def _finite_stats(values: np.ndarray[Any, Any]) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "median": None,
            "mad": None,
        }
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med)))
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "median": med,
        "mad": mad,
    }


def _spacing(axis: np.ndarray[Any, Any]) -> float | None:
    axis = np.asarray(axis, dtype=float)
    axis = np.unique(axis[np.isfinite(axis)])
    if axis.size < 2:
        return None
    d = np.diff(axis)
    d = d[d > 1e-12]
    return float(np.median(d)) if d.size else None


def _roughness(grid: np.ndarray[Any, Any]) -> dict[str, float | None]:
    xdiff = np.abs(np.diff(grid, axis=1)) if grid.shape[1] > 1 else np.array([])
    ydiff = np.abs(np.diff(grid, axis=0)) if grid.shape[0] > 1 else np.array([])
    return {
        "median_abs_step_x": float(np.median(xdiff)) if xdiff.size else None,
        "median_abs_step_y": float(np.median(ydiff)) if ydiff.size else None,
        "p95_abs_step_x": float(np.percentile(xdiff, 95)) if xdiff.size else None,
        "p95_abs_step_y": float(np.percentile(ydiff, 95)) if ydiff.size else None,
    }


def _smoothness(grid: np.ndarray[Any, Any]) -> dict[str, float | None]:
    finite = np.asarray(grid, dtype=float)
    if not np.isfinite(finite).any():
        return {"sigma_1_smooth_variance_ratio": None, "sigma_2_smooth_variance_ratio": None}
    fill = finite.copy()
    med = float(np.nanmedian(fill))
    fill[~np.isfinite(fill)] = med
    base_var = float(np.var(fill))
    if base_var <= 1e-18:
        return {"sigma_1_smooth_variance_ratio": 1.0, "sigma_2_smooth_variance_ratio": 1.0}
    s1 = gaussian_filter(fill, sigma=1.0, mode="nearest")
    s2 = gaussian_filter(fill, sigma=2.0, mode="nearest")
    return {
        "sigma_1_smooth_variance_ratio": float(np.var(s1) / base_var),
        "sigma_2_smooth_variance_ratio": float(np.var(s2) / base_var),
    }


@dataclass(frozen=True)
class LoadedExport:
    """One OKM file read exactly once: scan, grid, and parsed sections."""

    path: Path
    scan: ScanData
    grid: Grid2D
    sections: dict[str, dict[str, str]]


def load_okm_export(path: str | Path) -> LoadedExport:
    """Read an OKM export file into scan + grid + sections (single load)."""
    from ..services.single_scan import load_scan

    resolved = Path(path).expanduser().resolve()
    adapter = detect_adapter(resolved)
    scan = load_scan(resolved, adapter=adapter)
    return LoadedExport(
        path=resolved,
        scan=scan,
        grid=reconstruct_grid(scan),
        sections=_sections(resolved),
    )


def characterize_file(
    path: str | Path,
    *,
    run_baseline: bool = True,
    _preloaded: LoadedExport | None = None,
) -> dict[str, Any]:
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan, load_scan

    path = Path(path).expanduser().resolve()
    if _preloaded is not None and _preloaded.path == path:
        sections = _preloaded.sections
        scan = _preloaded.scan
        grid = _preloaded.grid
    else:
        sections = _sections(path)
        adapter = detect_adapter(path)
        scan = load_scan(path, adapter=adapter)
        grid = reconstruct_grid(scan)
    chars = sections.get("Characteristics", {})
    soil = sections.get("Soil Type", {})
    adapter = detect_adapter(path)
    signal = np.asarray(scan.signal, dtype=float)
    depth = np.asarray(scan.z, dtype=float)
    signal_stats = _finite_stats(signal)
    depth_stats = _finite_stats(depth)
    finite_signal = signal[np.isfinite(signal)]
    median_signal = float(np.median(finite_signal)) if finite_signal.size else 0.0
    above = int(np.sum(finite_signal > median_signal)) if finite_signal.size else 0
    below = int(np.sum(finite_signal < median_signal)) if finite_signal.size else 0
    equal = int(np.sum(finite_signal == median_signal)) if finite_signal.size else 0
    notes = chars.get("Notes", "")
    source_device = _notes_hardware(notes)

    candidate_summary: dict[str, Any] | None = None
    if run_baseline:
        _, anomaly, candidates = analyze_scan(
            scan,
            path.parent / ".okm_characterization_tmp",
            label=path.stem,
            config=AnalysisConfig(),
            write_outputs=False,
        )
        patterns: dict[str, int] = {}
        for c in candidates:
            patterns[c.pattern_hypothesis] = patterns.get(c.pattern_hypothesis, 0) + 1
        candidate_summary = {
            "candidate_count": int(len(candidates)),
            "patterns": dict(sorted(patterns.items())),
            "max_abs_anomaly_z": float(np.nanmax(np.abs(anomaly.zscore)))
            if np.isfinite(anomaly.zscore).any()
            else None,
        }

    return {
        "file": path.name,
        "sha256": _sha256(path),
        "adapter": adapter.name,
        "project_title": chars.get("Project Title"),
        "source_device_mentions": source_device,
        "explicit_normalized_device": scan.metadata.device,
        "date": scan.metadata.date,
        "time": scan.metadata.time,
        "operating_mode": scan.metadata.extra.get("operating_mode"),
        "scan_mode": scan.metadata.extra.get("scan_mode"),
        "impulse_mode": scan.metadata.extra.get("impulse_mode"),
        "soil": {
            "title": soil.get("Title"),
            "dielectric_constant": scan.metadata.dielectric_constant,
            "relative_permeability": scan.metadata.relative_permeability,
            "mineralization_pct": scan.metadata.mineralization_pct,
            "humidity_pct": scan.metadata.humidity_pct,
            "homogeneity_pct": scan.metadata.homogeneity_pct,
        },
        "geometry": {
            "grid_rows": int(grid.signal.shape[0]),
            "grid_cols": int(grid.signal.shape[1]),
            "points": int(len(scan)),
            "field_length_m": scan.metadata.field_length_m,
            "field_width_m": scan.metadata.field_width_m,
            "coordinates_are_metric": is_metric_coordinates(scan),
            "x_spacing_m_median": _spacing(scan.x),
            "y_spacing_m_median": _spacing(scan.y),
        },
        "signal": {
            **signal_stats,
            "unique_count": int(np.unique(finite_signal).size) if finite_signal.size else 0,
            "unique_fraction": float(np.unique(finite_signal).size / finite_signal.size)
            if finite_signal.size
            else None,
            "median_above_count": above,
            "median_below_count": below,
            "median_equal_count": equal,
            "roughness": _roughness(grid.signal),
            "smoothness": _smoothness(grid.signal),
        },
        "depth": {
            **depth_stats,
            "pearson_signal_depth": float(
                np.corrcoef(
                    signal[np.isfinite(signal) & np.isfinite(depth)],
                    depth[np.isfinite(signal) & np.isfinite(depth)],
                )[0, 1]
            )
            if np.sum(np.isfinite(signal) & np.isfinite(depth)) >= 3
            else None,
        },
        "claims_note": notes.strip() or None,
        "baseline_analysis": candidate_summary,
    }


def characterize_okm(
    inputs: Iterable[str | Path], out_dir: str | Path, *, run_baseline: bool = True
) -> dict[str, Any]:
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            paths.extend(sorted(p.glob("*.csv")))
            paths.extend(sorted(p.glob("*.txt")))
        elif p.is_file():
            paths.append(p)
    unique = sorted({p for p in paths})
    records = [characterize_file(p, run_baseline=run_baseline) for p in unique]
    device_mentions = sorted({d for r in records for d in r["source_device_mentions"]})
    explicit_devices = sorted({
        r["explicit_normalized_device"] for r in records if r["explicit_normalized_device"]
    })
    report = {
        "version": "0.2.95",
        "purpose": "OKM signal/data characterization; diagnostic only",
        "files": len(records),
        "device_mentions_observed": device_mentions,
        "explicit_normalized_devices": explicit_devices,
        "records": records,
        "limitations": [
            "Source descriptions and notes are claims from the exported files, not independent field ground truth.",
            "OKM examples may originate from different OKM devices; device mentions are reported, not inferred when absent.",
            "Signal/depth statistics describe the export and do not establish material identity, target identity, depth accuracy, or field detection accuracy.",
        ],
    }
    (out_dir / "okm_signal_characterization.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# GroundScan Analyzer v0.2.95 — OKM Signal Characterization",
        "",
        "Diagnostic release: no detector/classifier/fusion threshold changes.",
        "",
        f"Files characterized: **{len(records)}**",
        f"Hardware mentions observed in source notes: **{', '.join(device_mentions) if device_mentions else 'none'}**",
        f"Explicit normalized device fields: **{', '.join(explicit_devices) if explicit_devices else 'none'}**",
        "",
        "## Per-file characterization",
        "",
        "| File | Project | Hardware mentioned | Grid | Field (m) | Metric XY | Signal range | Depth range | Candidates |",
        "|---|---|---|---:|---:|:---:|---:|---:|---:|",
    ]
    for r in records:
        g = r["geometry"]
        s = r["signal"]
        d = r["depth"]
        b = r["baseline_analysis"] or {}
        grid_label = f"{g['grid_rows']}×{g['grid_cols']}"
        field_label = (
            f"{g['field_length_m']}×{g['field_width_m']}"
            if g["field_length_m"] is not None and g["field_width_m"] is not None
            else "—"
        )
        signal_range = f"{s['min']:.6g}…{s['max']:.6g}" if s["min"] is not None else "—"
        depth_range = f"{d['min']:.4g}…{d['max']:.4g}" if d["min"] is not None else "—"
        hw = ", ".join(r["source_device_mentions"]) or "—"
        lines.append(
            f"| {r['file']} | {r['project_title'] or '—'} | {hw} | {grid_label} | {field_label} | {'yes' if g['coordinates_are_metric'] else 'no'} | {signal_range} | {depth_range} | {b.get('candidate_count', '—')} |"
        )

    lines += [
        "",
        "## Interpretation guardrails",
        "",
        "1. Device mentions come from the file's own notes. An absent device name is not treated as proof of a particular OKM model.",
        "2. The characterization preserves the distinction between OKM format compatibility and device-specific field validation.",
        "3. Synthetic A/B/C generators remain robustness tests; they are not used here to define OKM signal behavior.",
        "4. The baseline candidate summary is a regression signature, not an accuracy estimate.",
    ]
    (out_dir / "okm_signal_characterization.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return report


def _quantiles(values: np.ndarray[Any, Any]) -> dict[str, float | None]:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {f"p{q}": None for q in (1, 5, 25, 50, 75, 95, 99)}
    qs = np.percentile(finite, [1, 5, 25, 50, 75, 95, 99])
    return {f"p{q}": float(v) for q, v in zip((1, 5, 25, 50, 75, 95, 99), qs, strict=True)}


def _scale_free_signal(values: np.ndarray[Any, Any]) -> dict[str, float | None]:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size < 3:
        return {
            "median": None,
            "mad": None,
            "robust_z_p95": None,
            "robust_z_p99": None,
            "robust_z_std": None,
            "skew_proxy": None,
        }
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med)))
    scale = max(1.4826 * mad, float(np.std(finite)), 1e-12)
    z = (finite - med) / scale
    centered = finite - med
    m2 = float(np.mean(centered**2))
    m3 = float(np.mean(centered**3))
    skew_proxy = m3 / (m2**1.5) if m2 > 1e-18 else 0.0
    return {
        "median": med,
        "mad": mad,
        "robust_z_p95": float(np.percentile(np.abs(z), 95)),
        "robust_z_p99": float(np.percentile(np.abs(z), 99)),
        "robust_z_std": float(np.std(z)),
        "skew_proxy": float(skew_proxy),
    }


def _spatial_fingerprint(grid: np.ndarray[Any, Any]) -> dict[str, float | None]:
    a = np.asarray(grid, dtype=float)
    if not np.isfinite(a).any():
        return {
            "neighbor_corr_x": None,
            "neighbor_corr_y": None,
            "gradient_anisotropy": None,
            "laplacian_energy_ratio": None,
        }
    fill = a.copy()
    med = float(np.nanmedian(fill))
    fill[~np.isfinite(fill)] = med

    def corr(u: np.ndarray[Any, Any], v: np.ndarray[Any, Any]) -> float | None:
        if u.size < 3 or np.std(u) < 1e-12 or np.std(v) < 1e-12:
            return None
        return float(np.corrcoef(u, v)[0, 1])

    cx = corr(fill[:, :-1].ravel(), fill[:, 1:].ravel()) if fill.shape[1] > 1 else None
    cy = corr(fill[:-1, :].ravel(), fill[1:, :].ravel()) if fill.shape[0] > 1 else None
    dx = np.diff(fill, axis=1) if fill.shape[1] > 1 else np.zeros((fill.shape[0], 0))
    dy = np.diff(fill, axis=0) if fill.shape[0] > 1 else np.zeros((0, fill.shape[1]))
    gx = float(np.median(np.abs(dx))) if dx.size else 0.0
    gy = float(np.median(np.abs(dy))) if dy.size else 0.0
    gradient_anisotropy = (max(gx, gy) / max(min(gx, gy), 1e-12)) if gx > 0 and gy > 0 else None
    if fill.shape[0] > 2 and fill.shape[1] > 2:
        lap = (
            fill[:-2, 1:-1]
            + fill[2:, 1:-1]
            + fill[1:-1, :-2]
            + fill[1:-1, 2:]
            - 4.0 * fill[1:-1, 1:-1]
        )
        denom = float(np.var(fill))
        lap_ratio = float(np.mean(lap**2) / max(denom, 1e-12))
    else:
        lap_ratio = None
    return {
        "neighbor_corr_x": cx,
        "neighbor_corr_y": cy,
        "gradient_anisotropy": gradient_anisotropy,
        "laplacian_energy_ratio": lap_ratio,
    }


def _header_signature(path: Path) -> dict[str, object]:
    sections = _sections(path)
    header = None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        clean = line.strip().strip('"')
        if clean.startswith("Impulse X,Scan Line Y,Impulse X [m]"):
            header = [c.strip() for c in clean.split(",")]
            break
    normalized = [re.sub(r"\s+", " ", c).lower() for c in (header or [])]
    digest = (
        hashlib.sha256("|".join(normalized).encode("utf-8")).hexdigest()[:16]
        if normalized
        else None
    )
    return {"sections": sorted(sections), "columns": normalized, "column_signature": digest}


def _fingerprint_record(path: str | Path, *, run_baseline: bool = True) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    preloaded = load_okm_export(path)
    scan = preloaded.scan
    grid = preloaded.grid
    signal = np.asarray(scan.signal, dtype=float)
    sf = _scale_free_signal(signal)
    q = _quantiles(signal)
    spatial = _spatial_fingerprint(grid.signal)
    b = characterize_file(path, run_baseline=run_baseline, _preloaded=preloaded)
    geometry = b["geometry"]
    z = np.asarray(scan.z, dtype=float)
    valid = np.isfinite(signal) & np.isfinite(z)
    depth_signal_corr = None
    if int(np.sum(valid)) >= 3 and np.std(signal[valid]) > 1e-12 and np.std(z[valid]) > 1e-12:
        depth_signal_corr = float(np.corrcoef(signal[valid], z[valid])[0, 1])
    return {
        "file": path.name,
        "sha256": _sha256(path),
        "device": b["explicit_normalized_device"],
        "source_device_mentions": b["source_device_mentions"],
        "adapter": b["adapter"],
        "format": _header_signature(path),
        "geometry": geometry,
        "scale_free_signal": sf,
        "raw_quantiles": q,
        "spatial": spatial,
        "depth_signal_correlation": depth_signal_corr,
        "baseline_analysis": b["baseline_analysis"],
    }


def _numeric_vector(record: dict[str, Any]) -> np.ndarray[Any, Any]:
    sf = record["scale_free_signal"]
    sp = record["spatial"]
    return np.array(
        [
            sf.get("robust_z_p95") or 0.0,
            sf.get("robust_z_p99") or 0.0,
            sf.get("robust_z_std") or 0.0,
            sf.get("skew_proxy") or 0.0,
            sp.get("neighbor_corr_x") if sp.get("neighbor_corr_x") is not None else 0.0,
            sp.get("neighbor_corr_y") if sp.get("neighbor_corr_y") is not None else 0.0,
            sp.get("gradient_anisotropy") if sp.get("gradient_anisotropy") is not None else 1.0,
            sp.get("laplacian_energy_ratio")
            if sp.get("laplacian_energy_ratio") is not None
            else 0.0,
            record.get("depth_signal_correlation")
            if record.get("depth_signal_correlation") is not None
            else 0.0,
        ],
        dtype=float,
    )


def fingerprint_okm(
    inputs: Iterable[str | Path], out_dir: str | Path, *, run_baseline: bool = True
) -> dict[str, Any]:
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            paths.extend(sorted(p.glob("*.csv")))
            paths.extend(sorted(p.glob("*.txt")))
        elif p.is_file():
            paths.append(p)
    unique = sorted(set(paths))
    records = [_fingerprint_record(p, run_baseline=run_baseline) for p in unique]
    vectors = [_numeric_vector(r) for r in records]
    pairwise: list[dict[str, object]] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            denom = np.linalg.norm(vectors[i]) * np.linalg.norm(vectors[j])
            cosine = float(np.dot(vectors[i], vectors[j]) / denom) if denom > 1e-12 else 1.0
            pairwise.append({
                "a": records[i]["file"],
                "b": records[j]["file"],
                "cosine_similarity": cosine,
            })
    device_groups: dict[str, list[str]] = {}
    for r in records:
        key = r["device"] or "unspecified"
        device_groups.setdefault(str(key), []).append(str(r["file"]))
    report = {
        "version": "0.2.95",
        "purpose": "OKM signal fingerprint diagnostics; format compatibility and scale-free signal characterization only",
        "files": len(records),
        "device_groups": {k: sorted(v) for k, v in sorted(device_groups.items())},
        "records": records,
        "pairwise_fingerprint_similarity": sorted(pairwise, key=lambda x: (x["a"], x["b"])),
        "limitations": [
            "The fingerprint is descriptive and does not infer physical target identity or material.",
            "Files with different hardware mentions are not treated as one device-validation corpus.",
            "Scale-free features reduce raw amplitude dependence but do not make measurements physically equivalent across devices.",
            "The corpus remains reference/example data, not independent field ground truth.",
        ],
    }
    json_path = out_dir / "okm_signal_fingerprint.json"
    md_path = out_dir / "okm_signal_fingerprint.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# GroundScan Analyzer v0.2.95 — OKM Signal Fingerprint",
        "",
        "Diagnostic release: no detector/classifier/fusion threshold changes.",
        "",
        f"Files fingerprinted: **{len(records)}**",
        f"Device groups: **{', '.join(sorted(device_groups)) if device_groups else 'none'}**",
        "",
        "## Per-file scale-free fingerprint",
        "",
        "| File | Device mention | Normalized device | Grid | Metric XY | rX | rY | |z| p95 | |z| p99 | Skew proxy | Depth/signal r | Candidates |",
        "|---|---|---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in records:
        g = r["geometry"]
        sf = r["scale_free_signal"]
        sp = r["spatial"]
        b = r["baseline_analysis"] or {}
        lines.append(
            f"| {r['file']} | {', '.join(r['source_device_mentions']) or '—'} | {r['device'] or '—'} | {g['grid_rows']}×{g['grid_cols']} | {'yes' if g['coordinates_are_metric'] else 'no'} | "
            f"{sp['neighbor_corr_x']:.3f} | {sp['neighbor_corr_y']:.3f} | {sf['robust_z_p95']:.3f} | {sf['robust_z_p99']:.3f} | "
            f"{sf['skew_proxy']:.3f} | {r['depth_signal_correlation']:.3f} | {b.get('candidate_count', '—')} |"
        )
    lines += [
        "",
        "## Format conclusion",
        "",
        "The fingerprint keeps export-format compatibility separate from hardware identity; source-note hardware mentions are shown separately from normalized metadata. Missing device names are not interpreted as a device guess.",
        "",
        "## Interpretation guardrails",
        "",
        "1. These fingerprints describe signal structure; they are not material probabilities or physical inversions.",
        "2. Device-specific validation still requires independent same-device field data.",
        "3. Synthetic A/B/C remain robustness tests and are not used to define the OKM fingerprint.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


__all__ = [
    "LoadedExport",
    "characterize_file",
    "characterize_okm",
    "fingerprint_okm",
    "load_okm_export",
]

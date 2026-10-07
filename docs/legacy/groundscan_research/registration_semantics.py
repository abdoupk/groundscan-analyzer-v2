"""v0.2.74 controlled benchmark for the semantics of orientation metadata.

Diagnostic-only: production registration is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from groundscan.site.registration import align_grids


def _synthetic_map(resolution: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:resolution, :resolution]
    base = rng.normal(0.0, 0.08, size=(resolution, resolution))
    for cy, cx, amp, sigma in (
        (8, 10, 5.0, 1.8),
        (22, 19, -4.0, 2.8),
        (15, 27, 2.4, 2.2),
        (25, 6, 1.7, 1.5),
    ):
        base += amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma * sigma))
    return base


def _row(alignment) -> dict:
    return {
        "transform": alignment.transform_name,
        "correlation": float(alignment.correlation),
        "multiscale_correlation": float(alignment.multiscale_correlation),
        "overlap_fraction": float(alignment.overlap_fraction),
        "registration_evidence": float(alignment.registration_evidence),
        "status": alignment.status,
        "candidate_count": int(alignment.candidate_count),
    }


def run_registration_semantics_benchmark(
    out_dir: str | Path,
    *,
    resolution: int = 32,
    seed: int = 7274,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _synthetic_map(resolution, seed)
    rotated = np.rot90(base, 1)

    same = align_grids(
        base, base, resolution=resolution, max_shift=2, orientation_a_deg=0.0, orientation_b_deg=0.0
    )
    metadata_only_90 = align_grids(
        base,
        base,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=0.0,
        orientation_b_deg=90.0,
    )
    physical_rotated_90 = align_grids(
        base,
        rotated,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=0.0,
        orientation_b_deg=90.0,
    )
    physical_rotated_unknown = align_grids(
        base,
        rotated,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=None,
        orientation_b_deg=None,
    )
    metadata_only_180 = align_grids(
        base,
        base,
        resolution=resolution,
        max_shift=2,
        orientation_a_deg=0.0,
        orientation_b_deg=180.0,
    )

    frame_contract_pass = bool(
        same.registration_evidence >= 0.80
        and physical_rotated_90.registration_evidence >= 0.80
        and physical_rotated_90.transform_name in {"rot90", "rot270"}
        and physical_rotated_unknown.registration_evidence >= 0.80
        and physical_rotated_unknown.transform_name in {"rot90", "rot270"}
        and metadata_only_90.registration_evidence < 0.50
    )
    heading_only_compatible = bool(metadata_only_90.registration_evidence >= 0.80)

    payload = {
        "version": "0.2.74",
        "benchmark": "registration_semantics",
        "seed": int(seed),
        "resolution": int(resolution),
        "cases": {
            "same_frame_same_metadata": _row(same),
            "metadata_only_90": _row(metadata_only_90),
            "physical_rotation_90_with_metadata": _row(physical_rotated_90),
            "physical_rotation_90_without_metadata": _row(physical_rotated_unknown),
            "metadata_only_180": _row(metadata_only_180),
        },
        "summary": {
            "frame_contract_pass": frame_contract_pass,
            "heading_only_compatible": heading_only_compatible,
            "metadata_only_evidence": float(metadata_only_90.registration_evidence),
            "physical_rotation_evidence": float(physical_rotated_90.registration_evidence),
            "physical_rotation_unknown_evidence": float(
                physical_rotated_unknown.registration_evidence
            ),
            "same_frame_evidence": float(same.registration_evidence),
            "metadata_only_180_evidence": float(metadata_only_180.registration_evidence),
        },
        "current_implementation_semantics": "frame_orientation_constraint",
        "heading_only_status": "incompatible_without_ignoring_orientation_metadata_in_registration",
        "decision": "benchmark_only_no_production_registration_change",
        "interpretation": [
            "Known orientation metadata currently constrains the rigid-transform family.",
            "A metadata-only 90-degree change is therefore not equivalent to a physical map rotation.",
            "The current implementation is compatible with scan-frame orientation metadata, not heading-only metadata.",
            "This benchmark cannot establish the meaning used by a specific vendor export.",
        ],
        "field_data_status": "No independently verified field ground truth is available; controlled synthetic semantics benchmark only.",
    }
    (out_dir / "registration_semantics.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    labels = [
        ("same_frame_same_metadata", "Same map + same metadata"),
        ("metadata_only_90", "Same map + metadata 90°"),
        ("physical_rotation_90_with_metadata", "Map rotated 90° + metadata 90°"),
        ("physical_rotation_90_without_metadata", "Map rotated 90° + no metadata"),
        ("metadata_only_180", "Same map + metadata 180°"),
    ]
    lines = [
        "# GroundScan Analyzer v0.2.74 — Registration Semantics Benchmark",
        "",
        "> Controlled synthetic benchmark. Production registration is unchanged.",
        "",
        "## Purpose",
        "",
        "Determine whether the current `orientation_deg` handling matches a scan-frame orientation contract or a heading-only contract.",
        "",
        "| Case | Transform | Evidence | Status |",
        "|---|---|---:|---|",
    ]
    for key, label in labels:
        row = payload["cases"][key]
        lines.append(
            f"| {label} | `{row['transform']}` | {row['registration_evidence']:.3f} | {row['status']} |"
        )
    lines += [
        "",
        "## Result",
        "",
        f"Frame-orientation contract: **{'PASS' if frame_contract_pass else 'FAIL'}**.",
        f"Heading-only compatibility of current implementation: **{'YES' if heading_only_compatible else 'NO'}**.",
        "",
        "The current aligner uses known orientation metadata to restrict allowable rigid transforms. Under that implementation contract, a 90-degree physical rotation should be reflected in the signal map as well as metadata. A metadata-only 90-degree change is expected to score poorly.",
        "",
        "## Important limitation",
        "",
        "This benchmark characterizes GroundScan behavior; it does not prove what an external/vendor metadata field means. That requires authoritative vendor semantics or paired known-coordinate data.",
        "",
        "## Validation boundary",
        "",
        "Synthetic semantics test only; no field accuracy, material identification, or cavity/tunnel proof is established.",
        "",
    ]
    (out_dir / "registration_semantics.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

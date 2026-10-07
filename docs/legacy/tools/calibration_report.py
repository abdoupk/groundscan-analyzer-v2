#!/usr/bin/env python
"""Emit the Stage 4 calibration and characterization report as JSON.

A thin CLI over :mod:`groundscan.validation.calibration`. It adds no analysis of
its own: every number it prints was produced by a characterization function in
that package, and the ``--section`` choice only decides which of them to run.

    python tools/calibration_report.py --list
    python tools/calibration_report.py --section datasets
    python tools/calibration_report.py --section register --out calibration_register.json
    python tools/calibration_report.py --section all --full

``--full`` widens the d_res surface and the false-positive sweep beyond the sizes
the test suite runs, at a correspondingly higher runtime. Without it the tool
uses the reduced configuration the characterization tests use, so a report can be
produced in the time a reviewer has.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundscan.validation.calibration import (  # noqa: E402  # noqa: E402
    datasets,
    decision,
    envelope,
    geometry,
    interactions,
    register,
    resolution,
)

SECTIONS = (
    "datasets",
    "field_evidence",
    "solidity",
    "compactness",
    "d_res",
    "min_size",
    "margin",
    "sigma3",
    "sensitivity",
    "interactions",
    "envelope",
    "register",
)


def _population(limit_vendor: int | None) -> tuple[Any, ...]:
    return decision.candidate_population(limit_vendor=limit_vendor)


def build(section: str, *, full: bool = False) -> dict[str, Any]:
    """Run one section and return its JSON-ready result."""
    vendor_limit = None if full else 4
    started = time.time()
    if section == "datasets":
        payload: dict[str, Any] = datasets.dataset_report()
    elif section == "field_evidence":
        payload = datasets.field_evidence_availability()
    elif section == "solidity":
        payload = {
            "census": geometry.solidity_census_summary(),
            "rows": [r.to_dict() for r in geometry.solidity_census()],
            "pitch_invariance": geometry.pitch_invariance(),
            "geometry_quality_weight_sweep": geometry.geometry_quality_weight_sweep(),
            "geometry_terms_reconstruction": (geometry.verify_geometry_quality_reconstruction()),
            "retired_formula_shift": decision.solidity_distribution_shift(),
        }
    elif section == "compactness":
        payload = {
            "matrix_summary": geometry.compactness_matrix_summary(),
            "rows": [r.to_dict() for r in geometry.compactness_matrix()],
            "scale_bias": geometry.compactness_scale_bias(),
            "thin_diagnostic": geometry.compactness_thin_diagnostic(),
            "border_bias": datasets.border_bias_probe(6),
        }
    elif section == "d_res":
        if full:
            payload = resolution.d_res_operating_envelope(
                sigmas=(0.5, 1.0, 1.5, 2.0),
                pitches=(0.25, 0.5, 1.0),
                noise_sigmas=(0.5, 1.0, 2.0),
                dy_ratios=(1.0, 2.0),
                seeds=(0, 1, 2),
            )
        else:
            payload = resolution.d_res_operating_envelope(
                sigmas=(1.0,),
                pitches=(0.5,),
                noise_sigmas=(1.0,),
                dy_ratios=(1.0,),
                seeds=(0, 1, 2),
            )
        payload["decomposition_interaction"] = interactions.d_res_x_decomposition()
    elif section == "min_size":
        sweep = resolution.min_size_resolution_sweep(
            response_sigmas=(0.5, 1.0, 2.0) if full else (1.0, 2.0),
            pitches=(0.25, 0.5, 1.0) if full else (0.5, 1.0),
        )
        sweep["verdict"] = resolution.min_size_parameterisation_verdict(sweep)
        payload = sweep
    elif section == "margin":
        population = _population(vendor_limit)
        payload = {
            "population": decision.population_summary(population),
            "structure": decision.margin_structure(population),
            "sensitivity": decision.margin_sensitivity_sweep(population),
            "evidence_ladder": decision.evidence_margin_ladder(),
            "controlled_cases": decision.controlled_margin_cases(),
            "instability": decision.margin_instability_zone(),
        }
    elif section == "sigma3":
        payload = {
            "characterization": decision.three_sigma_characterization(
                seeds=tuple(range(8)) if full else (0, 1, 2, 3),
            ),
            "false_positive_components": {
                str(tau): decision.threshold_false_positive_count(
                    threshold=tau, seeds=tuple(range(12)) if full else (0, 1, 2, 3, 4)
                )
                for tau in ((2.5, 3.0, 4.0) if full else (3.0,))
            },
            "contamination": decision.contamination_sensitivity(
                seeds=tuple(range(4)) if full else (0, 1)
            ),
        }
    elif section == "sensitivity":
        population = _population(vendor_limit)
        payload = decision.evidence_quality_sensitivity_matrix(population)
    elif section == "interactions":
        payload = interactions.interaction_report(
            _population(vendor_limit), limit_vendor=vendor_limit
        )
    elif section == "envelope":
        payload = envelope.operating_envelope()
    elif section == "register":
        payload = register.register_report()
    else:
        raise SystemExit(f"unknown section {section!r}; choose from {SECTIONS}")
    return {
        "section": section,
        "full": full,
        "elapsed_s": round(time.time() - started, 3),
        "result": payload,
    }


def build_all(*, full: bool = False) -> dict[str, Any]:
    return {section: build(section, full=full) for section in SECTIONS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=(*SECTIONS, "all"), default="all")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument(
        "--full",
        action="store_true",
        help="widen the sweeps beyond the characterization-test configuration",
    )
    parser.add_argument("--list", action="store_true", help="list sections and exit")
    args = parser.parse_args(argv)

    if args.list:
        for section in SECTIONS:
            print(section)
        return 0

    payload = (
        build_all(full=args.full) if args.section == "all" else build(args.section, full=args.full)
    )
    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} bytes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

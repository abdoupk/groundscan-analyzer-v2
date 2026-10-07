"""Runnable performance benchmark (see docs/adr/010-performance-benchmark.md).

Covers the areas the remediation plan names: single scan, large grid,
many components, multiscan, registration, soil diagnostics,
serialization. Prints a timing + peak-memory table; `--json` emits the
same payload for trend tracking. Not a gate (no fail-under): absolute
times are CLI-acceptable and the exhaustive registration search is
load-bearing for the ambiguity contract, so there is deliberately no
optimization target here. Re-run after any performance-motivated change
together with the equivalence suite.

Usage:
    python tools/benchmark.py [--json] [--out bench.json]
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np

from groundscan import ScanData, ScanMetadata
from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.site.registration import align_grids


def _scan(n: int = 40, blocks: tuple = ((10, 10, 12.0), (25, 25, 11.0)), seed: int = 0) -> ScanData:
    rng = np.random.default_rng(seed)
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    for r0, c0, amp in blocks:
        signal[r0 : r0 + 3, c0 : c0 + 3] += amp
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


def _many_component_scan(n: int = 60, count: int = 12, seed: int = 5) -> ScanData:
    rng = np.random.default_rng(seed)
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    signal = rng.normal(0, 1, size=(n, n))
    spots = rng.choice(n - 4, size=(count, 2), replace=False)
    for r0, c0 in spots:
        signal[r0 : r0 + 3, c0 : c0 + 3] += 12.0
    return ScanData(
        x=x.ravel(),
        y=y.ravel(),
        z=np.zeros(n * n),
        signal=signal.ravel(),
        metadata=ScanMetadata(),
    )


def _time(fn, *args, **kwargs) -> tuple[float, object]:
    start = time.perf_counter()
    out = fn(*args, **kwargs)
    return time.perf_counter() - start, out


def main() -> int:
    parser = argparse.ArgumentParser(description="GroundScan performance benchmark (not a gate).")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    parser.add_argument("--out", default=None, help="write the JSON payload to this path")
    args = parser.parse_args()

    rows: list[dict] = []
    # Timings run WITHOUT tracemalloc: tracing inflates per-allocation
    # overhead ~3x on the registration search loop. Memory is measured in
    # a separate traced pass below so the timings stay representative.
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        cfg = AnalysisConfig()

        dt, (grid, anomaly, cands) = _time(
            analyze_scan, _scan(), work / "single", label="single", config=cfg, write_outputs=True
        )
        rows.append({
            "case": "single-40x40-with-outputs",
            "seconds": round(dt, 3),
            "candidates": len(cands),
        })

        dt, (_, _, cands) = _time(
            analyze_scan,
            _scan(n=120, blocks=((30, 30, 12.0), (80, 80, 11.0), (60, 20, 10.0))),
            work / "large",
            label="large",
            config=cfg,
            write_outputs=False,
        )
        rows.append({
            "case": "single-120x120-no-outputs",
            "seconds": round(dt, 3),
            "candidates": len(cands),
        })

        dt, (_, anomaly_many, cands_many) = _time(
            analyze_scan,
            _many_component_scan(),
            work / "many",
            label="many",
            config=cfg,
            write_outputs=False,
        )
        rows.append({
            "case": "many-components-60x60",
            "seconds": round(dt, 3),
            "candidates": len(cands_many),
            "components": int(anomaly_many.n_components),
        })

        from groundscan import analyze_site

        scans = [("a", _scan(seed=1)), ("b", _scan(seed=2))]
        dt, res = _time(analyze_site, scans, work / "site", config=cfg)
        rows.append({
            "case": "site-2x40x40",
            "seconds": round(dt, 3),
            "fused": len(res.fused_candidates),
        })

        rng = np.random.default_rng(0)
        z = rng.normal(0, 1, size=(40, 40))
        z[15:20, 15:20] += 8.0
        dt, _ = _time(align_grids, z, z.copy(), resolution=40)
        rows.append({"case": "registration-40x40", "seconds": round(dt, 3)})

    with tempfile.TemporaryDirectory() as td:
        tracemalloc.start()
        analyze_scan(
            _scan(),
            Path(td) / "mem",
            label="mem",
            config=AnalysisConfig(),
            write_outputs=True,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    payload_out = {"peak_mem_mb": round(peak / 1e6, 1), "cases": rows}
    if args.out:
        Path(args.out).write_text(json.dumps(payload_out, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload_out, indent=2))
    else:
        print(f"{'case':32s} {'seconds':>8s}")
        for row in rows:
            extra = f" ({row['candidates']} cand)" if "candidates" in row else ""
            print(f"{row['case']:32s} {row['seconds']:8.3f}{extra}")
        print(f"peak traced memory: {payload_out['peak_mem_mb']} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

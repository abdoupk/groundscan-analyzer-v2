"""Field-operational quality gate handler (lazy heavy imports)."""

from __future__ import annotations

import sys
from pathlib import Path

# v0.5.1: accept the same scan extensions as analyze-site
# (*.csv, *.tsv, *.txt, *.dat); directories are searched recursively.
QUALITY_PATTERNS = ("*.csv", "*.tsv", "*.txt", "*.dat")


def cmd_quality(args) -> int:
    # Light input collection first so "no input files" exits 3 without
    # requiring heavy analysis imports.
    files: list[Path] = []
    for item in args.inputs:
        path = Path(item)
        if path.is_dir():
            for pattern in QUALITY_PATTERNS:
                files.extend(sorted(path.rglob(pattern)))
        else:
            files.append(path)
    if not files:
        print("quality-check: no input files found", file=sys.stderr)
        return 3

    import json as _json

    from ..core.grid import reconstruct_grid
    from ..diagnostics.quality_probe import detect_scan_quality_diagnostics
    from ..gates.field_quality import assess_field_quality
    from ..gates.geometry import summarize_geometry
    from ..services.single_scan import load_scan

    results = {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for path in files:
        scan = load_scan(path)
        grid = reconstruct_grid(scan)
        geometry = summarize_geometry(scan)
        diag = detect_scan_quality_diagnostics(grid)
        results[str(path)] = assess_field_quality(scan, grid, geometry, diag).to_dict()
    # v0.5.1: unversioned filename (the version lived in the dirname before).
    report_path = out / "field_quality.json"
    report_path.write_text(_json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    quiet = bool(getattr(args, "quiet", False))
    as_json = bool(getattr(args, "json", False))
    if not quiet:
        print(f"Field quality check complete: files={len(results)}")
        print(f"Report written to {report_path}")
    if as_json:
        print(
            _json.dumps(
                {"command": "quality-check", "out": str(report_path), "files": len(results)},
                sort_keys=True,
            )
        )
    return 0

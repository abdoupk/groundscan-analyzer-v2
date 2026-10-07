"""Single-scan and site handlers (lazy heavy imports)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_DEFAULT_SCAN_PATTERNS = ("*.csv", "*.tsv", "*.txt")

_RESULTS_ROOT = Path("results")


def default_single_out(file: str | Path) -> Path:
    """Default output folder for one scan: results/<file-stem>/."""
    return _RESULTS_ROOT / Path(file).stem


def default_site_out(inputs: list[str]) -> Path:
    """Default output folder for a site run.

    Single directory input -> its name; files sharing one parent -> the
    parent name; otherwise a generic ``site`` folder. All under results/.
    """
    paths = [Path(raw).expanduser() for raw in inputs]
    if len(paths) == 1 and paths[0].is_dir():
        return _RESULTS_ROOT / (paths[0].name or "site")
    anchors = set()
    for path in paths:
        resolved = path.resolve()
        anchors.add(resolved if path.is_dir() else resolved.parent)
    if len(anchors) == 1:
        return _RESULTS_ROOT / (next(iter(anchors)).name or "site")
    return _RESULTS_ROOT / "site"


def resolve_out(explicit: str | Path | None, default: Path) -> Path:
    """Honor an explicit --out; otherwise use the default, timestamped when
    the folder already holds a previous run so runs never overwrite."""
    if explicit is not None:
        return Path(explicit)
    if default.exists() and any(default.iterdir()):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return default.parent / f"{default.name}_{stamp}"
    return default


def _path_is_within(path: Path, directory: Path) -> bool:
    """Return True when path is the same as or nested under directory."""
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _expand_site_inputs(
    inputs: list[str], *, recursive: bool, patterns: list[str] | None, out_dir: str | Path
) -> tuple[list[Path], list[Path]]:
    """Expand mixed files/directories into deterministic, adapter-readable inputs.

    Directories contribute files matching the requested patterns. Every candidate
    is preflighted through the adapter registry so unrelated CSV/TXT files in a
    site folder are skipped instead of failing the entire site analysis.
    """
    from ..io import detect_adapter

    patterns = tuple(patterns or _DEFAULT_SCAN_PATTERNS)
    output_path = Path(out_dir).expanduser().resolve()
    found: list[Path] = []
    skipped: list[Path] = []
    suffixes = {Path(pattern).suffix.lower() for pattern in patterns if Path(pattern).suffix}

    def add_file(path: Path) -> None:
        path = path.resolve()
        if not path.is_file():
            return
        if _path_is_within(path, output_path):
            skipped.append(path)
            return
        if suffixes and path.suffix.lower() not in suffixes:
            skipped.append(path)
            return
        try:
            detect_adapter(path)
        except ValueError:
            skipped.append(path)
            return
        found.append(path)

    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_file():
            add_file(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(f"Input path does not exist: {raw}")
        iterator = path.rglob("*") if recursive else path.glob("*")
        for candidate in iterator:
            if not candidate.is_file():
                continue
            # Pattern filtering is intentionally done before adapter parsing.
            if any(candidate.match(pattern) for pattern in patterns):
                add_file(candidate)
            else:
                skipped.append(candidate.resolve())

    unique = sorted(set(found), key=lambda p: str(p).lower())
    return unique, sorted(set(skipped), key=lambda p: str(p).lower())


def _unique_site_labels(paths: list[Path]) -> list[str]:
    """Generate stable human-readable labels, disambiguating duplicate stems."""
    labels: list[str] = []
    counts: dict[str, int] = {}
    for path in paths:
        base = path.stem
        counts[base.lower()] = counts.get(base.lower(), 0) + 1
        labels.append(base)
    if all(v == 1 for v in counts.values()):
        return labels
    out: list[str] = []
    used: dict[str, int] = {}
    for path, base in zip(paths, labels, strict=False):
        key = base.lower()
        if counts[key] == 1:
            out.append(base)
            continue
        used[key] = used.get(key, 0) + 1
        parent = path.parent.name or "folder"
        out.append(f"{parent}/{base}")
    return out


def _enrich_design_metadata(
    scan,
    label: str,
    line_spacing: float | None,
    point_spacing: float | None,
    *,
    quiet: bool = False,
):
    """Infer only low-risk survey-design metadata from a scan label/filename.

    v0.5.1: inference is logged (not silent) so filename-guessed
    orientation/pattern/spacing never masquerades as measured metadata.
    Pass ``quiet=True`` to suppress the log line.
    """
    inferred: list[str] = []
    low = label.lower().replace("-", "_").replace(" ", "_")
    if scan.metadata.orientation_deg is None:
        if re.search(r"(?:^|_)h(?:_|$)|horizontal|horiz", low):
            scan.metadata.orientation_deg = 0.0
            inferred.append("orientation_deg=0.0 (from filename)")
        elif re.search(r"(?:^|_)v(?:_|$)|vertical|vert", low):
            scan.metadata.orientation_deg = 90.0
            inferred.append("orientation_deg=90.0 (from filename)")
    if not scan.metadata.scan_pattern:
        if "zigzag" in low or "zig_zag" in low or re.search(r"(?:^|_)zig(?:_|$)", low):
            scan.metadata.scan_pattern = "zigzag"
            inferred.append("scan_pattern=zigzag (from filename)")
        elif "parallel" in low or re.search(r"(?:^|_)par(?:_|$)", low):
            scan.metadata.scan_pattern = "parallel"
            inferred.append("scan_pattern=parallel (from filename)")
    if line_spacing is not None:
        scan.metadata.line_spacing_m = line_spacing
    if point_spacing is not None:
        scan.metadata.point_spacing_m = point_spacing
    if scan.metadata.line_spacing_m is None:
        matches = re.findall(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*m(?:_|$)", low)
        if matches:
            try:
                scan.metadata.line_spacing_m = float(matches[-1].replace(",", "."))
                inferred.append(f"line_spacing_m={scan.metadata.line_spacing_m} (from filename)")
            except ValueError:
                pass
    if inferred and not quiet:
        print(
            f"Inferred design metadata for {label!r}: "
            + "; ".join(inferred)
            + " (filename guess, not measured)"
        )
    return scan


def _adapter_for(path: str, line_spacing: float | None, point_spacing: float | None):
    from ..io.rover import RoverAdapter

    if line_spacing is None and point_spacing is None:
        return None
    rover = RoverAdapter()
    if rover.can_read(path):
        return RoverAdapter(line_spacing_m=line_spacing, point_spacing_m=point_spacing)
    return None


def _emit_json(payload: dict, enabled: bool) -> None:
    if enabled:
        import json as _json

        print(_json.dumps(payload, sort_keys=True))


def cmd_analyze(args, parser=None) -> int:
    import time as _time

    from ..gates.geometry import summarize_geometry
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan, load_scan

    _t0 = _time.perf_counter()
    quiet = bool(getattr(args, "quiet", False))
    as_json = bool(getattr(args, "json", False))

    def adapter_for(path):
        return _adapter_for(path, args.line_spacing, args.point_spacing)

    scan = load_scan(args.file, adapter=adapter_for(args.file))
    _enrich_design_metadata(
        scan, Path(args.file).stem, args.line_spacing, args.point_spacing, quiet=quiet
    )
    geometry_desc = summarize_geometry(scan).describe()
    if not quiet:
        print(f"Scan geometry: {geometry_desc}")
    out = resolve_out(args.out, default_single_out(args.file))
    _, _, candidates = analyze_scan(
        scan,
        out,
        label="scan",
        config=AnalysisConfig(
            threshold=args.threshold,
            min_size=args.min_size,
            zigzag=args.zigzag,
            soil_mode=args.soil_mode,
            extraction_rescue=args.extraction_rescue,
            field_quality_mode=args.field_quality_mode,
        ),
    )
    if not quiet:
        print(f"{len(candidates)} candidate(s) found. Outputs written to {Path(out)}")
    _emit_json(
        {
            "command": "analyze",
            "out": str(out),
            "candidates": len(candidates),
            "duration_s": round(_time.perf_counter() - _t0, 3),
        },
        as_json,
    )
    return 0


def cmd_site(args, parser=None) -> int:
    # Light input expansion/validation first so usage errors exit 2 via
    # parser.error without requiring heavy analysis imports.
    out = resolve_out(args.out, default_site_out(args.inputs))
    try:
        site_paths, skipped_paths = _expand_site_inputs(
            args.inputs, recursive=args.recursive, patterns=args.pattern, out_dir=out
        )
    except FileNotFoundError as exc:
        if parser is not None:
            parser.error(str(exc))
        raise
    if len(site_paths) < 2:
        msg = (
            f"analyze-site found {len(site_paths)} usable scan file(s); at least two are required. "
            "Pass scan files/directories or adjust --pattern/--recursive."
        )
        if parser is not None:
            parser.error(msg)
        raise ValueError(msg)

    import time as _time

    from ..services.single_scan import load_scan
    from ..site.analyze_site import analyze_site

    _t0 = _time.perf_counter()

    def adapter_for(path):
        return _adapter_for(path, args.line_spacing, args.point_spacing)

    quiet = bool(getattr(args, "quiet", False))
    as_json = bool(getattr(args, "json", False))
    labels = _unique_site_labels(site_paths)
    if not quiet:
        print(f"Discovered {len(site_paths)} scan file(s).")
        for path, label in zip(site_paths, labels, strict=False):
            print(f"  INPUT: {label} <- {path}")
        if skipped_paths:
            print(f"Skipped {len(skipped_paths)} unsupported/non-input file(s).")
    scans = []
    for file_path, label in zip(site_paths, labels, strict=False):
        scan = load_scan(file_path, adapter=adapter_for(str(file_path)))
        _enrich_design_metadata(scan, label, args.line_spacing, args.point_spacing, quiet=quiet)
        scans.append((label, scan))
    result = analyze_site(
        scans,
        out,
        threshold=args.threshold,
        min_size=args.min_size,
        zigzag=args.zigzag,
        resolution=args.fusion_resolution,
        soil_mode=args.soil_mode,
        extraction_rescue=args.extraction_rescue,
        fusion_pruning=args.fusion_pruning,
        field_quality_mode=args.field_quality_mode,
    )
    if not quiet:
        print(
            f"Site analysis: {result.scan_count} scans, {len(result.fused_candidates)} fused candidate(s). Outputs written to {Path(out)}"
        )
    if result.registration and not quiet:
        print(
            f"Registration status: {result.registration.status} (consistency={result.registration.registration_consistency:.0%})"
        )
        for warning in result.warnings:
            print(f"WARNING: {warning}")
    if not quiet:
        for c in result.fused_candidates:
            print(
                f"Candidate #{c.id}: {c.pattern_hypothesis}, evidence={c.evidence_score:.2f}, "
                f"detected={c.scan_count}/{result.scan_count}, "
                f"direction={c.directional_persistence:.0%}, spacing={c.spacing_persistence:.0%}, "
                f"traversal={c.traversal_persistence:.0%}, quality={c.quality_score:.2f}, "
                f"fp-risk={c.false_positive_risk:.2f}, status={c.review_status}"
            )
    _emit_json(
        {
            "command": "analyze-site",
            "out": str(out),
            "scans": result.scan_count,
            "fused_candidates": len(result.fused_candidates),
            "warnings": list(result.warnings),
            "duration_s": round(_time.perf_counter() - _t0, 3),
        },
        as_json,
    )
    return 0

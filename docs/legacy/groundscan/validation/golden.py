"""Golden-output hashes: prove structural refactors don't change analytics.

Design (plan section N):
- Covers the production contracts only: single-scan ``analysis.json`` +
  ``candidates.csv`` and site ``site_fused_candidates.json`` + ``.csv``.
- PNG/HTML/timestamps excluded (rendering, not analytics).
- Inputs are pinned: seeded synthetic generator cases + frozen vendor CSVs
  (by basename; absolute ``source_file`` is normalized away).
- Hashes are computed over normalized, key-sorted JSON and
  newline-normalized CSV so the gate is order/layout stable but
  value-sensitive: any analytical change alters a hash.

Regenerating baselines (requires review before commit)::
    GOLDEN_UPDATE=1 python -m pytest tests/validation/test_golden_outputs.py -q
Targeted regeneration of one case (review the diff before commit)::
    GOLDEN_UPDATE=synth_tunnel python -m pytest tests/validation/test_golden_outputs.py -q

Portability note (2026-09-25): hashes must reproduce across OS/CPU/BLAS
builds, whose last-ulp float differences otherwise break every frozen
gate on a new machine. All floats are therefore rounded to 9 decimals
during normalization -- 3+ orders of margin each way (fp noise here is
~1e-12 worst case; real analytical changes surface at >=1e-6). A change
that legitimately moves rounded values still requires reviewed
regeneration, never silent updates.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _basename(value: object) -> object:
    if isinstance(value, str) and ("\\" in value or "/" in value):
        return value.replace("\\", "/").rsplit("/", 1)[-1]
    return value


#: Decimals kept by frozen-gate normalization. See the portability note above.
FLOAT_NDIGITS = 9


def _round_floats(obj: object, ndigits: int = FLOAT_NDIGITS) -> object:
    """Recursively round every float in JSON-like data (bools untouched).

    round() on binary floats is exactly specified, so this erases
    last-ulp cross-platform noise while preserving any real analytical
    change (>=1e-6). NaN/Infinity round-trip unchanged.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {key: _round_floats(value, ndigits) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(value, ndigits) for value in obj]
    return obj


def _round_csv_cell(cell: str, ndigits: int = FLOAT_NDIGITS) -> str:
    """Round one CSV cell when it carries a float; pass everything else through.

    Integer-looking cells (no ``.``/exponent) are never touched so ``5`` can
    never become ``5.0``. JSON-encoded dict cells (evidence/hypothesis maps)
    are parsed, rounded recursively, and re-dumped with the writer's exact
    settings (``sort_keys=True``, default separators).
    """
    text = cell.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except ValueError:
            return cell
        return json.dumps(_round_floats(parsed, ndigits), sort_keys=True)
    if any(mark in text for mark in (".", "e", "E")) or text.lower() in {
        "nan",
        "inf",
        "+inf",
        "-inf",
    }:
        try:
            return repr(round(float(text), ndigits))
        except ValueError:
            return cell
    return cell


def normalize_analysis_payload(obj: dict) -> dict:
    """Return a normalized copy of an analysis.json payload."""
    obj = json.loads(json.dumps(obj, allow_nan=True))
    meta = obj.get("metadata")
    if isinstance(meta, dict):
        if "source_file" in meta:
            meta["source_file"] = _basename(meta.get("source_file"))
        extra = meta.get("extra")
        if isinstance(extra, dict):
            extra.pop("analysis_tmp_dir", None)
    return _round_floats(obj)


def normalize_site_payload(obj: dict) -> dict:
    """Return a normalized copy of a site_fused_candidates.json payload."""
    return _round_floats(json.loads(json.dumps(obj, allow_nan=True)))


def normalize_csv(text: str) -> str:
    import csv as _csv
    import io as _io

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    reader = _csv.reader(_io.StringIO(text))
    rows = [[_round_csv_cell(cell) for cell in row] for row in reader]
    buffer = _io.StringIO()
    _csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def hash_json(obj: dict) -> str:
    canonical = json.dumps(obj, sort_keys=True, allow_nan=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Golden case definitions
# ---------------------------------------------------------------------------

# (kind, identifier, label)
GOLDEN_SYNTHETIC_SINGLE = (
    ("positive_compact", 101),
    ("negative_cavity", 102),
    ("tunnel", 103),
    ("geology", 104),
)
GOLDEN_SITE_SEED = 20260702

from .fixtures import (  # noqa: E402 — deferred after golden constants by design
    VENDOR_ROOT as ORIG_VENDOR_ROOT,
)


def _run_single_scan(scan, out_dir: Path, label: str) -> dict[str, str]:
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan

    out_dir.mkdir(parents=True, exist_ok=True)
    _, _, _ = analyze_scan(
        scan,
        out_dir,
        label=label,
        config=AnalysisConfig(),
    )
    analysis = json.loads((out_dir / f"{label}_analysis.json").read_text(encoding="utf-8"))
    csv_text = (out_dir / f"{label}_candidates.csv").read_text(encoding="utf-8")
    return {
        f"{label}.analysis.json": hash_json(normalize_analysis_payload(analysis)),
        f"{label}.candidates.csv": hash_text(normalize_csv(csv_text)),
    }


#: Golden case ids (one case = one scan label / site run = 2 artifacts).
#: Per-case tests pin values; the registry test pins the artifact set, so
#: adding or removing an artifact fails one targeted test, not the whole gate.
GOLDEN_CASE_IDS: tuple[str, ...] = (
    "synth_positive_compact",
    "synth_negative_cavity",
    "synth_tunnel",
    "synth_geology",
    "vendor_pipeline",
    "vendor_iron_box",
    "site_two_pass",
)

#: Case id -> vendor fixture for the two frozen vendor singles.
GOLDEN_VENDOR_CASES: dict[str, tuple[str, str]] = {
    "vendor_pipeline": ("train", "Pipeline.csv"),
    "vendor_iron_box": ("validation", "Iron Box.csv"),
}

#: Static artifact inventory (14 entries); the registry test compares the
#: baseline file against this without running any analysis.
GOLDEN_ARTIFACT_NAMES: tuple[str, ...] = tuple(
    [f"{kind}.analysis.json" for kind, _ in GOLDEN_SYNTHETIC_SINGLE]
    + [f"{kind}.candidates.csv" for kind, _ in GOLDEN_SYNTHETIC_SINGLE]
    + [
        "pipeline.analysis.json",
        "pipeline.candidates.csv",
        "iron_box.analysis.json",
        "iron_box.candidates.csv",
    ]
    + ["site_two_pass.site_fused_candidates.json", "site_two_pass.site_fused_candidates.csv"]
)


def compute_golden_case(workdir: Path, case_id: str) -> dict[str, str]:
    """Run a single golden case under workdir; return its {artifact_name: sha256}.

    Each case yields exactly 2 artifacts. Raises ValueError for unknown ids.
    """
    from ..services.single_scan import load_scan
    from ..site.analyze_site import analyze_site
    from .synthetic_core.core import SyntheticScenario, SyntheticTarget, generate_scan

    if case_id.startswith("synth_"):
        kind = case_id[len("synth_") :]
        seeds = dict(GOLDEN_SYNTHETIC_SINGLE)
        if kind not in seeds:
            raise ValueError(f"unknown golden case {case_id!r}; expected one of {GOLDEN_CASE_IDS}")
        target = SyntheticTarget(kind=kind, x=10.0, y=10.0, depth=2.0, amplitude=12.0)
        scenario = SyntheticScenario(
            name=f"golden_{kind}",
            width_m=20.0,
            height_m=20.0,
            nx=40,
            ny=40,
            targets=[target],
            noise_sigma=0.5,
            seed=seeds[kind],
        )
        scan, _truth = generate_scan(scenario)
        return _run_single_scan(scan, workdir, kind)

    if case_id in GOLDEN_VENDOR_CASES:
        subdir, fname = GOLDEN_VENDOR_CASES[case_id]
        path = ORIG_VENDOR_ROOT / subdir / fname
        if not path.exists():
            alt = sorted((ORIG_VENDOR_ROOT / subdir).glob("*.csv"))
            raise FileNotFoundError(
                f"golden vendor fixture missing: {path} (available: {[p.name for p in alt]})"
            )
        scan = load_scan(path)
        label = path.stem.lower().replace(" ", "_")
        return _run_single_scan(scan, workdir, label)

    if case_id == "site_two_pass":
        # Two-scan site from the same synthetic truth with different noise draws.
        site_targets = [
            SyntheticTarget(kind="positive_compact", x=10.0, y=10.0, depth=2.0, amplitude=12.0)
        ]
        scans = []
        for i, seed in enumerate((GOLDEN_SITE_SEED, GOLDEN_SITE_SEED + 1)):
            scenario = SyntheticScenario(
                name=f"golden_site_{i}",
                width_m=20.0,
                height_m=20.0,
                nx=40,
                ny=40,
                targets=site_targets,
                noise_sigma=0.5,
                seed=seed,
            )
            scan, _ = generate_scan(scenario)
            scans.append((f"pass_{i}", scan))
        workdir.mkdir(parents=True, exist_ok=True)
        analyze_site(scans, workdir)
        site_json = json.loads((workdir / "site_fused_candidates.json").read_text(encoding="utf-8"))
        site_csv = (workdir / "site_fused_candidates.csv").read_text(encoding="utf-8")
        return {
            "site_two_pass.site_fused_candidates.json": hash_json(
                normalize_site_payload(site_json)
            ),
            "site_two_pass.site_fused_candidates.csv": hash_text(normalize_csv(site_csv)),
        }

    raise ValueError(f"unknown golden case {case_id!r}; expected one of {GOLDEN_CASE_IDS}")


def compute_goldens(workdir: Path) -> dict[str, str]:
    """Run all golden cases under workdir; return {artifact_name: sha256}."""
    goldens: dict[str, str] = {}
    for case_id in GOLDEN_CASE_IDS:
        goldens.update(compute_golden_case(workdir / case_id, case_id))
    return dict(sorted(goldens.items()))


def merge_golden_update(
    baseline: dict[str, str], new: dict[str, str], case_id: str | None
) -> dict[str, str]:
    """Pure merge for GOLDEN_UPDATE (unit-testable; touches no files).

    ``None`` regenerates the full baseline; a case id overwrites only that
    case's artifact entries so review stays scoped to the changed case.
    """
    if case_id is None:
        return dict(sorted(new.items()))
    if case_id not in GOLDEN_CASE_IDS:
        raise ValueError(f"unknown golden case {case_id!r}; expected one of {GOLDEN_CASE_IDS}")
    merged = dict(baseline)
    merged.update(new)
    return dict(sorted(merged.items()))


# ---------------------------------------------------------------------------
# Cross-tree equivalence set (plan section N)
# ---------------------------------------------------------------------------
# Same fixed procedure must produce identical hashes on the original layout
# (groundscan.pipeline / groundscan.compare.multiscan / groundscan.synthetic)
# and on this refactored layout. The ORIGINAL side is recorded once in
# tests/validation/equiv_original.hashes; this function recomputes the
# REFACTORED side. Scenario names intentionally match the original-side
# procedure byte-for-byte (source_file embeds the scenario name).

EQUIV_SYNTHETIC = (
    ("positive_compact", 101),
    ("negative_cavity", 102),
    ("tunnel", 103),
    ("geology", 104),
)


def compute_equivalence_goldens(workdir: Path) -> dict[str, str]:
    """Recompute the refactored side of the cross-tree equivalence set."""
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan, load_scan
    from ..site.analyze_site import analyze_site
    from .synthetic_core.core import SyntheticScenario, SyntheticTarget, generate_scan

    config = AnalysisConfig()

    goldens: dict[str, str] = {}
    for kind, seed in EQUIV_SYNTHETIC:
        target = SyntheticTarget(kind=kind, x=10.0, y=10.0, depth=2.0, amplitude=12.0)
        scenario = SyntheticScenario(
            name=f"equiv_{kind}",
            width_m=20.0,
            height_m=20.0,
            nx=40,
            ny=40,
            targets=[target],
            noise_sigma=0.5,
            seed=seed,
        )
        scan, _ = generate_scan(scenario)
        d = workdir / f"synth_{kind}"
        d.mkdir(parents=True, exist_ok=True)
        analyze_scan(scan, d, label=kind, config=config)
        analysis = json.loads((d / f"{kind}_analysis.json").read_text(encoding="utf-8"))
        csv_text = (d / f"{kind}_candidates.csv").read_text(encoding="utf-8")
        goldens[f"{kind}.analysis.json"] = hash_json(normalize_analysis_payload(analysis))
        goldens[f"{kind}.candidates.csv"] = hash_text(normalize_csv(csv_text))

    vendor = ORIG_VENDOR_ROOT / "train" / "Pipeline.csv"
    scan = load_scan(vendor)
    d = workdir / "vendor_pipeline"
    d.mkdir(parents=True, exist_ok=True)
    analyze_scan(scan, d, label="pipeline", config=config)
    analysis = json.loads((d / "pipeline_analysis.json").read_text(encoding="utf-8"))
    csv_text = (d / "pipeline_candidates.csv").read_text(encoding="utf-8")
    goldens["pipeline.analysis.json"] = hash_json(normalize_analysis_payload(analysis))
    goldens["pipeline.candidates.csv"] = hash_text(normalize_csv(csv_text))

    targets = [SyntheticTarget(kind="positive_compact", x=10.0, y=10.0, depth=2.0, amplitude=12.0)]
    scans = []
    for i, seed in enumerate((20260702, 20260703)):
        sc = SyntheticScenario(
            name=f"equiv_site_{i}",
            width_m=20.0,
            height_m=20.0,
            nx=40,
            ny=40,
            targets=targets,
            noise_sigma=0.5,
            seed=seed,
        )
        s, _ = generate_scan(sc)
        scans.append((f"pass_{i}", s))
    site_out = workdir / "site_two_pass"
    site_out.mkdir(parents=True, exist_ok=True)
    analyze_site(scans, site_out)
    site_json = json.loads((site_out / "site_fused_candidates.json").read_text(encoding="utf-8"))
    site_csv = (site_out / "site_fused_candidates.csv").read_text(encoding="utf-8")
    goldens["site.site_fused_candidates.json"] = hash_json(normalize_site_payload(site_json))
    goldens["site.site_fused_candidates.csv"] = hash_text(normalize_csv(site_csv))
    return dict(sorted(goldens.items()))

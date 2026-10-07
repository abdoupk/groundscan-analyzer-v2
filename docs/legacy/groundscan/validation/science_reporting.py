"""Science report serialization (strict JSON + Markdown summary).

Rendering responsibility only: sanitization, artifact writing, and the
human-readable summary. Pass/fail logic, oracles, and verdict derivation
live in :mod:`groundscan.validation.scientific`. Split from that module
under its documented split rule (>400 lines): serialization imports
nothing engine-specific.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def sanitize_json(value: Any) -> Any:
    """Recursively replace non-finite floats with None (strict RFC JSON).

    The science report must never contain NaN/Infinity literals: unlike
    frozen machine contracts (grandfathered ``allow_nan``), this is a new
    artifact and stays strict from birth.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): sanitize_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json(v) for v in value]
    return value


def write_science_report(report: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    """Write strict-JSON report + Markdown summary; return artifact paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = sanitize_json(report)
    json_path = out_dir / "science_report.json"
    json_path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path = out_dir / "science_report.md"
    md_path.write_text(render_markdown(clean), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def render_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable summary with gating made explicit."""
    sections = report["sections"]
    gating_note = (
        "Gating sections decide the verdict; informational items are recorded, never scored."
    )
    lines = [
        "# Science validation report",
        "",
        "> Evidence classes are complementary, never interchangeable. "
        "Synthetic truth is synthetic truth. Reference compatibility is "
        "reference compatibility. Regression stability is regression "
        "stability. Field accuracy is field accuracy.",
        "",
        f"Verdict: **{report['verdict']}** "
        f"(schema v{report['science_schema_version']}; "
        f"basis: {', '.join(report.get('verdict_basis', []))}).",
        "",
        f">{gating_note}",
        "",
        "## Scientific / technical validation (gating)",
        "",
    ]
    for key in ("mathematical", "synthetic", "adversarial", "metamorphic"):
        section = sections[key]
        lines.append(f"### {key}: {section.get('status', '?')}")
        if key == "synthetic":
            for family, metrics in section.get("families", {}).items():
                gated = "gating" if metrics.get("gating", True) else "informational"
                lines.append(
                    f"- {family} [{gated}]: synthetic recall "
                    f"{metrics.get('synthetic_recall')}, synthetic precision "
                    f"{metrics.get('synthetic_precision')}"
                )
            large = section.get("large_suite")
            if isinstance(large, dict):
                lines.append(
                    f"- large breadth [{('gating' if large.get('gating') else 'informational')}]: "
                    f"{large.get('cases')} cases, integrity failures: "
                    f"{large.get('integrity_failures', []) or 'none'}"
                )
        if key == "adversarial":
            lines.append(f"- verdict bins: {section.get('verdict_bins')}")
            for limitation in section.get("limitations", []):
                lines.append(
                    f"- known limitation (within allowance, tracked): "
                    f"{limitation.get('case_id')}: {limitation.get('detail')}"
                )
        if key == "metamorphic":
            informational = sum(
                1 for p in section.get("pair_records", []) if not p.get("gating", True)
            )
            lines.append(
                f"- pairs: {section.get('pairs')} ({informational} informational review-only)"
            )
        for failure in section.get("failed_cases", []) or section.get("failed_pairs", []):
            lines.append(f"- FAIL: {failure}")
        lines.append("")
    lines += [
        "## Reference evidence (informational pointers, not recomputed)",
        "",
        f"- reference_compatibility: {sections['reference_compatibility']['status']}",
        f"- regression_protection: {sections['regression_protection']['status']}",
        "",
        "## Empirical evidence",
        "",
        "- field_validation: **UNKNOWN** -- no independent field-ground-truth "
        "dataset has been evaluated. This is a scope statement, not a failure.",
        "",
        "## Operating point",
        "",
        f"- policy {report['operating_point']['policy_version']} at "
        f"{report['operating_point']['primary_threshold']} "
        f"({report['operating_point']['status']}; "
        f"{report['operating_point']['scientific_claim']}).",
        "",
    ]
    return "\n".join(lines)

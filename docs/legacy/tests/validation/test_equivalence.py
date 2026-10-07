"""Cross-tree equivalence: refactored outputs match the recorded ORIGINAL hashes.

The ORIGINAL side was produced once by the fixed procedure in
groundscan/validation/golden.compute_equivalence_goldens (scenario names
``equiv_*``, Pipeline.csv, two-pass site) and committed as
equiv_original.hashes. This test recomputes the REFACTORED side and fails
naming any artifact whose hash differs -- i.e. any analytical behavior change
introduced by the refactor. 12/12 matched at commit time.

Portability regime (2026-09-25): both sides are hashed after rounding all
floats to 9 decimals (see golden.FLOAT_NDIGITS), and rendered explanation
copy is excluded (see _strip_rendered_explanations -- P1 deliberately
changed explanation wording, so prose can never match across trees).
Analytics (numbers, labels, counts, geometry) are fully compared. The
fixture was re-recorded same-regime from the original tree; any future
re-record must rerun the original procedure, never hand-edit hashes.
"""

import json
from pathlib import Path

import pytest

from groundscan.validation.golden import compute_equivalence_goldens

FIXTURE = Path(__file__).resolve().parent / "equiv_original.hashes"

# Intentional scientific corrections that diverge from the ORIGINAL tree.
# The fixture above stays the untouched historical record; each entry here
# names the artifact, the cause, and the review trail. Any mismatch NOT in
# this map still fails the gate.
_RENAME_DIVERGENCE = (
    "Method/provenance tag rename (evidence-model, multi-hypothesis, "
    "local-geology-context, secondary-median-geology-rescue, "
    "morphology_metrics, soil_context, five-factor-context, "
    "soil-integrated, rescue-screening, analyze_failure_modes) plus the "
    "soil_model v2->soil_context key: string values only, proven "
    "renames-only by code-diff normalization and old/new field diffs. "
    "See docs/remediation/GOLDEN_CHANGELOG.md."
)

INTENDED_DIVERGENCES = {
    "site.site_fused_candidates.csv": (
        "REG01 registration correlation units (ambiguity_margin / "
        "second_best_correlation are raw Pearson correlations, not composite "
        "scores); registration_consistency 0.756 -> 0.757. See "
        "docs/remediation/GOLDEN_CHANGELOG.md + docs/adr/."
    ),
    "site.site_fused_candidates.json": ("Same REG01 cause as the site CSV twin."),
    "geology.analysis.json": _RENAME_DIVERGENCE,
    "geology.candidates.csv": _RENAME_DIVERGENCE,
    "negative_cavity.analysis.json": _RENAME_DIVERGENCE,
    "negative_cavity.candidates.csv": _RENAME_DIVERGENCE,
    "pipeline.analysis.json": _RENAME_DIVERGENCE,
    "pipeline.candidates.csv": _RENAME_DIVERGENCE,
    "positive_compact.analysis.json": _RENAME_DIVERGENCE,
    "positive_compact.candidates.csv": _RENAME_DIVERGENCE,
    "tunnel.analysis.json": _RENAME_DIVERGENCE,
    "tunnel.candidates.csv": _RENAME_DIVERGENCE,
}


@pytest.mark.slow
def test_refactored_matches_original_tree(tmp_path):
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["goldens"]
    actual = compute_equivalence_goldens(tmp_path / "work")
    assert set(actual) == set(expected)
    mismatched = sorted(k for k in expected if expected[k] != actual[k])
    unexpected = [k for k in mismatched if k not in INTENDED_DIVERGENCES]
    assert not unexpected, "refactor changed analytical behavior in: " + ", ".join(
        f"{k} (original {expected[k][:12]}…, refactored {actual[k][:12]}…)" for k in unexpected
    )
    for key in INTENDED_DIVERGENCES:
        assert key in expected, f"allowlist entry {key!r} no longer names a tracked artifact"


@pytest.mark.slow
def test_intended_divergences_still_diverge(tmp_path):
    """Fail closed: if a correction stops changing behavior, re-examine it.

    An allowlist entry that no longer diverges means the correction was
    silently reverted (or the original fixture moved) — either way the
    review trail in INTENDED_DIVERGENCES needs updating, not silent passing.
    """
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["goldens"]
    actual = compute_equivalence_goldens(tmp_path / "work")
    for key in INTENDED_DIVERGENCES:
        assert expected[key] != actual[key], (
            f"{key!r} no longer diverges from the original tree; "
            "remove it from INTENDED_DIVERGENCES with review"
        )

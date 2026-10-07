"""Golden-output gate: structural refactors must not change analytics.

Covers production contracts only (analysis.json/candidates.csv single-scan,
site_fused_candidates.json/.csv site). PNG/HTML excluded (rendering).

One test per case (7 cases x 2 artifacts): an analytical change fails only
its case's test. Artifact add/remove fails the registry test instead.

Update procedures (each requires review before commit — never silent):
    python -m pytest tests/validation/test_golden_outputs.py -q --update-goldens
    python -m pytest tests/validation/test_golden_outputs.py -q --update-goldens=<case_id>
Ambient GOLDEN_UPDATE=1 still works locally via the tests/conftest.py
bridge, but the explicit flag is preferred; update mode refuses to run
in CI either way.
"""

import json
import os
from pathlib import Path

import pytest

from groundscan.validation.golden import (
    GOLDEN_ARTIFACT_NAMES,
    GOLDEN_CASE_IDS,
    compute_golden_case,
    compute_goldens,
    merge_golden_update,
)

HASHES_FILE = Path(__file__).resolve().parent / "golden.hashes"


def _read_baseline() -> dict[str, str]:
    if not HASHES_FILE.exists():
        pytest.fail(
            f"baseline {HASHES_FILE.name} missing; regenerate with "
            "GOLDEN_UPDATE=1 (requires review before commit)"
        )
    return json.loads(HASHES_FILE.read_text(encoding="utf-8"))


def _maybe_update(case_id: str | None, fresh: dict[str, str]) -> None:
    """Handle GOLDEN_UPDATE; return None, or pytest.skip after writing.

    Full regen ("1") is owned by the union test (the only one that computes
    everything); per-case tests skip and defer to it. A case id is merged
    (scoped) by its own case test; run the whole file when updating.
    """
    requested = os.environ.get("GOLDEN_UPDATE")
    if requested is None:
        return
    if requested != "1" and requested not in GOLDEN_CASE_IDS:
        pytest.fail(f"GOLDEN_UPDATE={requested!r} unknown; use 1 or one of {GOLDEN_CASE_IDS}")
    if requested == "1" and case_id is not None:
        pytest.skip("deferred to the full-regen union test")
    if requested == case_id or (requested == "1" and case_id is None):
        baseline = _read_baseline() if HASHES_FILE.exists() else {}
        merged = merge_golden_update(baseline, fresh, None if requested == "1" else requested)
        HASHES_FILE.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        pytest.skip(f"goldens regenerated at {HASHES_FILE} — review the diff before commit")


def test_golden_registry_complete():
    """The baseline artifact set matches the static inventory (no compute)."""
    expected = _read_baseline()
    assert set(expected) == set(GOLDEN_ARTIFACT_NAMES), (
        f"artifact set changed: only-in-baseline={sorted(set(expected) - set(GOLDEN_ARTIFACT_NAMES))}, "
        f"only-in-code={sorted(set(GOLDEN_ARTIFACT_NAMES) - set(expected))} "
        "(add/remove the case in golden.py, then GOLDEN_UPDATE=1 + review)"
    )


@pytest.mark.slow
@pytest.mark.parametrize("case_id", GOLDEN_CASE_IDS)
def test_golden_case_matches_baseline(tmp_path, case_id):
    expected = _read_baseline()
    actual = compute_golden_case(tmp_path / case_id, case_id)
    assert set(actual) <= set(expected), (
        f"{case_id}: unknown artifacts {sorted(set(actual) - set(expected))}"
    )
    _maybe_update(case_id, actual)
    mismatched = sorted(k for k in actual if expected.get(k) != actual[k])
    assert not mismatched, f"analytical behavior changed in {case_id}: " + ", ".join(
        f"{k} (expected {expected[k][:12]}…, got {actual[k][:12]}…)" for k in mismatched
    )


def test_golden_full_union_matches_baseline(tmp_path):
    """compute_goldens stays the union of the per-case runners."""
    expected = _read_baseline()
    actual = compute_goldens(tmp_path / "work")
    _maybe_update(None, actual)
    assert set(actual) == set(expected)
    mismatched = sorted(k for k in expected if expected[k] != actual[k])
    assert not mismatched


def test_merge_golden_update_scoped_and_full():
    baseline = {"a.json": "old-a", "b.json": "old-b"}
    full = merge_golden_update(baseline, {"a.json": "new-a", "c.json": "new-c"}, None)
    assert full == {"a.json": "new-a", "c.json": "new-c"}
    scoped = merge_golden_update(baseline, {"a.json": "new-a"}, "synth_tunnel")
    assert scoped == {"a.json": "new-a", "b.json": "old-b"}
    with pytest.raises(ValueError):
        merge_golden_update(baseline, {"a.json": "x"}, "no-such-case")

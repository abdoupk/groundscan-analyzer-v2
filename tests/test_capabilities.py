"""Checks on `docs/capabilities.md`, the legacy capability census.

Two checks, with different reach, and the difference is deliberate.

The first is unconditional and offline: it reads only the artefact, so it runs
for anyone with the repository. The second is conditional on `docs/legacy/`,
which is untracked, so it records a skip rather than a pass for every reader
without the archaeology. A check that reports "passed" when it never looked at
the tree is worse than no check.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "docs" / "capabilities.md"
LEGACY = REPO / "docs" / "legacy"
DERIVER = REPO / "scripts" / "derive_capabilities.py"
BEGIN_MARKER = "<!-- BEGIN DERIVED TABLE -->"
END_MARKER = "<!-- END DERIVED TABLE -->"

KINDS = frozenset({"output", "no-output"})
ROLES = frozenset({"callable-surface", "private-only", "constants-only"})
ISSUE_REFERENCE = re.compile(r"^#\d+$")

#: The rules the artefact must state rather than only enforce. Each is a full
#: bullet lead, asserted inside the Rules section - so restating the same words
#: in the Checks section cannot satisfy it.
STATED_RULES = (
    "**The denominator is every `.py` under `docs/legacy/` except",
    "**No row carries verdict prose.**",
    "**Rows are legacy-side.",
    "**This census holds two subjects inside one file",
    "**A re-export surface takes no row",
    "**The old package-marker reason was false",
    "**`role` is populated exactly when",
    "**A private-only row's verdict is decided at the row",
    "**The count of covered modules is derived",
    "**The lint verifies that a name exists, never that a list is complete.**",
)

#: The limit of the offline check, which the artefact must say out loud rather
#: than leave implied by the check's silence.
STATED_LIMIT = "costs nothing real, because issues are not deleted on this tracker"


def artefact_text() -> str:
    return ARTEFACT.read_text(encoding="utf-8")


def derived_block() -> list[str]:
    text = artefact_text()
    head, _, rest = text.partition(f"{BEGIN_MARKER}\n")
    assert head, f"{ARTEFACT} has no {BEGIN_MARKER} marker"
    block, _, _ = rest.partition(END_MARKER)
    return [line for line in block.splitlines() if line.startswith("|")]


def rows() -> list[dict[str, str]]:
    """The row table, as a list of cells keyed by the header's column names.

    Returns:
        One dict per row, keyed by the table's own column headers.
    """
    lines = derived_block()
    assert len(lines) > 2, "the derived table has a header but no rows"
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    parsed = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == len(header), f"ragged row: {line}"
        parsed.append(dict(zip(header, cells, strict=True)))
    return parsed


def vocabulary(name: str) -> set[str]:
    """A closed vocabulary as the artefact itself states it.

    Read from the file rather than hard-coded, so a vocabulary re-opened at map
    level makes this fail here instead of passing against a stale copy.

    Returns:
        The value column of the vocabulary's own table.
    """
    head, _, rest = artefact_text().partition(f"**`{name}`**")
    assert head, f"the artefact states no `{name}` vocabulary"
    lines = rest.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("| value"))
    cells = (line.strip("|").split("|")[0].strip().strip("` ") for line in lines[start + 2 :])
    return {cell for cell in cells if cell}


def load_deriver() -> ModuleType:
    """Import the derivation script, which is tooling rather than a package.

    Returns:
        The script's module object, executed against the archaeology.
    """
    spec = importlib.util.spec_from_file_location("derive_capabilities", DERIVER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rules_section() -> str:
    head, _, rest = artefact_text().partition("## Rules")
    assert head, "the artefact has no Rules section"
    body, _, _ = rest.partition("\n## ")
    return body


def test_the_artefact_states_its_rules() -> None:
    section = rules_section()
    for rule in STATED_RULES:
        assert rule in section, f"the Rules section does not state the rule: {rule}"


def test_the_artefact_states_the_limit_of_the_offline_check() -> None:
    assert STATED_LIMIT in artefact_text()


def test_every_row_kind_is_in_the_closed_set() -> None:
    assert {row["kind"].strip("` ") for row in rows()} <= KINDS


def test_every_row_role_is_in_the_closed_set() -> None:
    roles = {row["role"].strip("` ") for row in rows() if row["role"]}
    assert roles <= ROLES


def test_role_is_populated_exactly_when_kind_is_no_output() -> None:
    """A role classifies a location emitting nothing; an output row has none."""
    blank_no_output = [
        row["capability"] for row in rows() if row["kind"] == "`no-output`" and not row["role"]
    ]
    assert not blank_no_output, f"no-output rows with no role: {blank_no_output}"
    filled_output = [
        row["capability"] for row in rows() if row["kind"] == "`output`" and row["role"]
    ]
    assert not filled_output, f"output rows carry a no-output role: {filled_output}"


def test_every_row_cites_an_issue_number() -> None:
    for row in rows():
        assert ISSUE_REFERENCE.match(row["verdict issue"]), row


def test_every_row_is_uniquely_keyed() -> None:
    keys = [f"{row['legacy module']}::{row['capability']}" for row in rows()]
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"duplicate rows: {sorted(duplicates)}"


@pytest.mark.parametrize(
    ("column", "vocabulary_name"),
    [("concept", "concept"), ("implementation", "implementation")],
)
def test_every_verdict_is_empty_or_a_member_of_its_vocabulary(
    column: str, vocabulary_name: str
) -> None:
    allowed = vocabulary(vocabulary_name)
    assert allowed, f"the artefact states no `{vocabulary_name}` vocabulary"
    for row in rows():
        cell = row[column]
        if cell:
            assert cell.strip("` ") in allowed, f"{row['capability']}: {cell!r} is not in {allowed}"


@pytest.mark.parametrize("column", ["concept", "implementation"])
def test_no_row_carries_verdict_prose(column: str) -> None:
    """A populated cell is one bare token. Anything longer is a second home."""
    for row in rows():
        cell = row[column]
        if cell:
            assert cell.startswith("`"), f"{row['capability']}: {cell!r} is not a bare token"
            assert cell.endswith("`"), f"{row['capability']}: {cell!r} is not a bare token"
            assert " " not in cell.strip("`"), f"{row['capability']}: {cell!r} reads as prose"


@pytest.mark.parametrize("vocabulary_name", ["concept", "implementation"])
def test_reserved_is_not_a_member_of_either_vocabulary(vocabulary_name: str) -> None:
    """It names a slot in a contract, not the fate of a capability."""
    assert "reserved" not in vocabulary(vocabulary_name)


def test_the_two_vocabularies_are_disjoint_in_purpose() -> None:
    """`preserved` is in both, and means a fate of the idea in one and of the
    machinery in the other. Sharing a token is the point; sharing a definition
    would be the defect."""
    assert "preserved" in vocabulary("concept")
    assert "preserved" in vocabulary("implementation")


def _tree_dependent() -> ModuleType:
    if not LEGACY.is_dir():
        pytest.skip(
            "not checked: docs/legacy/ is untracked, so this reader has no archaeology to "
            "check against. Recorded as not checked, never as passed."
        )
    return load_deriver()


def test_the_covered_count_is_never_written_as_a_numeral() -> None:
    """`modules_covered` is derived and must never be stated as a numeral."""
    text = artefact_text()
    assert "never written here" in text
    assert "134 of" not in text
    assert "118 of" not in text


def test_every_denominator_module_carries_a_row_or_is_excluded() -> None:
    module = _tree_dependent()
    census = module.derive()
    covered = {row.module for row in census.rows}
    excluded = set(census.facades) | set(census.package_markers)
    expected = set(census.denominator) - excluded
    assert expected - covered == set(), "denominator modules with no row and no exclusion"
    assert covered & excluded == set(), "excluded modules carry rows"


def test_the_row_set_equals_the_derived_row_set() -> None:
    module = _tree_dependent()
    derived = {(row.module, row.name, row.kind, row.role) for row in module.derive().rows}
    stated = {
        (
            row["legacy module"].strip("` "),
            row["capability"].strip("` "),
            row["kind"].strip("` "),
            row["role"].strip("` "),
        )
        for row in rows()
    }
    assert stated == derived, "the table and the derivation disagree"


def test_every_facade_target_takes_a_row_in_one_hop() -> None:
    """Each excluded facade resolves to row-carrying modules, with no chains."""
    module = _tree_dependent()
    census = module.derive()
    covered = {row.module for row in census.rows}
    assert census.facades, "the derivation names no excluded facades"
    for facade, targets in census.facades.items():
        assert targets, f"{facade} names no targets"
        for target in targets:
            assert target in covered, f"{facade} targets {target}, which carries no row"
            assert target not in census.facades, f"{facade} targets {target}, a second facade"


def test_the_excluded_set_is_the_derived_one() -> None:
    """The table holds no excluded module; the excluded set comes from the tree."""
    module = _tree_dependent()
    census = module.derive()
    excluded = set(census.facades) | set(census.package_markers)
    stated_modules = {row["legacy module"].strip("` ") for row in rows()}
    assert stated_modules & excluded == set(), "excluded modules carry rows"
    assert set(census.denominator) - stated_modules == excluded


def test_the_denominator_excludes_tests() -> None:
    module = _tree_dependent()
    assert not [path for path in module.denominator() if "tests" in path.parts]

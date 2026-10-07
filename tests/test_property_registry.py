"""Checks on the contract vocabulary module and its artefact.

The module is the shipped, typed, versioned home of every closed vocabulary
the contract has. The artefact states the same sets in tables a reader can
see. The checks below verify the two agree per vocabulary, that the glossary
agrees where it restates one, that every glossary headword carries its
avoidance line, and that the placement test with its non-output marker is
stated rather than implied.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

import groundscan_analyzer.property_registry as registry

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "docs" / "contract.md"
GLOSSARY = REPO / "CONTEXT.md"

HEAD_PATTERN = re.compile(r"^\*\*([^*]+?)\*\*:")
AVOID_PATTERN = re.compile(r"^_Avoid_:")
SECTION_PATTERN = re.compile(r"^#+ ")

STATED_RULES = (
    "**The module is the single home of the five closed vocabularies",
    "**A closed set is closed against its own members",
    "**An `_Avoid_` line is declaration, not use",
    "**The placement test is the only way an output enters a class",
    "**Failing the placement test is an answer, not a gap",
    "**A census edit is a semantic contract change",
)

PLACEMENT_CLAUSES = (
    "decided from the computation",
    "carried on the record",
    "withheld rather than a caveat",
)


def artefact_text() -> str:
    return ARTEFACT.read_text(encoding="utf-8")


def glossary_text() -> str:
    return GLOSSARY.read_text(encoding="utf-8")


def rules_section() -> str:
    head, _, rest = artefact_text().partition("## Rules")
    assert head, "the artefact has no Rules section"
    body, _, _ = rest.partition("\n## ")
    return body


def vocabulary_table(name: str) -> set[str]:
    """Read one vocabulary table from the artefact by its heading.

    Args:
        name: The heading slug of the vocabulary table to read.

    Returns:
        The first-column values of that table as a set.
    """
    text = artefact_text()
    head, _, rest = text.partition(f"### `{name}`")
    assert head, f"the artefact states no `{name}` vocabulary"
    lines = rest.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("| value"))
    cells = (line.strip("|").split("|")[0].strip().strip("` ") for line in lines[start + 2 :])
    values = set()
    for cell in cells:
        if not cell:
            break
        values.add(cell)
    assert values, f"the artefact states an empty `{name}` vocabulary"
    return values


def true_headwords() -> list[tuple[int, str, list[str]]]:
    """Glossary entries as (line number, headword, block lines to Avoid).

    Returns:
        One tuple per glossary entry with its line number and following block.
    """
    lines = glossary_text().splitlines()
    found: list[tuple[int, str, int]] = []
    last_sig = "start"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if SECTION_PATTERN.match(line):
            last_sig = "header"
            continue
        if AVOID_PATTERN.match(line):
            last_sig = "avoid"
            continue
        match = HEAD_PATTERN.match(line)
        if match:
            if last_sig in {"start", "avoid", "header"}:
                found.append((index + 1, match.group(1), index))
            last_sig = "head"
            continue
        last_sig = "text"
    entries = []
    for pos, (lineno, head, line_index) in enumerate(found):
        end = found[pos + 1][2] if pos + 1 < len(found) else len(lines)
        block = lines[line_index + 1 : end]
        entries.append((lineno, head, block))
    return entries


def validate_member(vocabulary: frozenset[str], name: str) -> None:
    """Raise for a name outside its closed vocabulary.

    Args:
        vocabulary: The closed set the name must belong to.
        name: The candidate member name to check.

    Raises:
        ValueError: If the name is not a member of the vocabulary.
    """
    if name not in vocabulary:
        msg = f"{name!r} is not a member of the closed vocabulary"
        raise ValueError(msg)


def validate_census_line(line: dict[str, str]) -> None:
    """Raise for a census line with no class and no named non-output clause.

    Args:
        line: A census line carrying a class or the non-output marker.

    Raises:
        ValueError: If the line carries neither a known class nor the marker.
    """
    output_class = line.get("class", "")
    marker = line.get("non-output", "")
    if output_class in registry.OUTPUT_CLASSES:
        return
    if (
        marker == registry.NON_OUTPUT_MARKER
        and line.get("clause") in registry.PLACEMENT_FAILURE_CLAUSES
    ):
        return
    msg = f"unplaced output: {line!r}"
    raise ValueError(msg)


def test_the_artefact_states_its_rules() -> None:
    section = rules_section()
    for rule in STATED_RULES:
        assert rule in section, f"the Rules section does not state the rule: {rule}"


def test_versions_travel_once_at_the_document_root() -> None:
    text = artefact_text()
    contract_hits = text.count(f"Contract version: {registry.CONTRACT_VERSION}")
    registry_hits = text.count(f"Registry version: {registry.REGISTRY_VERSION}")
    assert contract_hits == 1, "contract version must appear exactly once"
    assert registry_hits == 1, "registry version must appear exactly once"
    contract_at = text.index(f"Contract version: {registry.CONTRACT_VERSION}")
    registry_at = text.index(f"Registry version: {registry.REGISTRY_VERSION}")
    assert abs(contract_at - registry_at) < 200, "versions must travel beside each other"


def test_output_classes_match_the_module() -> None:
    assert vocabulary_table("output-classes") == set(registry.OUTPUT_CLASSES)


def test_scope_groups_match_the_module() -> None:
    assert vocabulary_table("scope-groups") == set(registry.SCOPE_GROUPS)


def test_transforms_match_the_module() -> None:
    assert vocabulary_table("transforms") == set(registry.TRANSFORMS)


def test_refusal_register_matches_the_module() -> None:
    assert vocabulary_table("refusal-register") == set(registry.REFUSED_TRANSFORMS)


def test_conventions_match_the_module() -> None:
    assert vocabulary_table("conventions") == set(registry.CONVENTIONS)


# The glossary restates only the nine-class partition as a closed list, so only
# it admits an equality check. Conventions and scopes are named across entries
# (quantile-v1 appears nowhere in CONTEXT.md), and transforms use new tokens;
# their agreement surface is artefact-versus-module above, with member-as-term
# checks arriving with the census lines in a later slice.
def test_glossary_and_module_agree_on_output_classes() -> None:
    text = glossary_text()
    head, _, rest = text.partition("The partition has nine classes and all of them ship.")
    assert head, "the glossary states no nine-class partition"
    segment = rest.split("\u2014")[0]
    listed = set(re.findall(r"`([a-z][a-z0-9-]*)`", segment))
    assert listed == set(registry.OUTPUT_CLASSES)


def test_every_glossary_headword_carries_an_avoidance_line() -> None:
    missing = [
        f"{lineno}: {head}"
        for lineno, head, block in true_headwords()
        if not any(AVOID_PATTERN.match(line) for line in block)
    ]
    assert not missing, f"headwords with no avoidance line: {missing}"


def test_avoidance_line_is_declaration_not_use() -> None:
    for _, head, block in true_headwords():
        avoid_lines = [line for line in block if AVOID_PATTERN.match(line)]
        assert len(avoid_lines) <= 1, f"{head} carries more than one avoidance line"
        for line in avoid_lines:
            assert line.startswith("_Avoid_:"), f"{head}: avoidance line must declare, not prose"


def test_avoidance_carrying_banned_material_by_design_is_not_a_violation() -> None:
    entries = {head: block for _, head, block in true_headwords()}
    block = entries["Field position"]
    avoid_lines = [line for line in block if AVOID_PATTERN.match(line)]
    assert avoid_lines, "Field position carries no avoidance line"
    assert any("metric coordinate" in line for line in avoid_lines)
    missing = [line for line in block if AVOID_PATTERN.match(line)]
    assert missing, "an avoidance line carrying banned material must still count"


def test_headword_losing_its_avoidance_line_is_a_failure() -> None:
    entries = {head: block for _, head, block in true_headwords()}
    stripped = [line for line in entries["Field position"] if not AVOID_PATTERN.match(line)]
    assert stripped, "the entry has no non-avoidance lines to keep"
    assert not any(AVOID_PATTERN.match(line) for line in stripped)


def test_placement_test_is_stated_in_the_artefact() -> None:
    text = artefact_text()
    for clause in PLACEMENT_CLAUSES:
        assert clause in text, f"the artefact does not state the placement clause: {clause}"


def test_non_output_names_the_failed_clause() -> None:
    assert registry.NON_OUTPUT_MARKER == "non-output"
    assert set(registry.PLACEMENT_FAILURE_CLAUSES) == {
        "decided-from-computation",
        "carried-on-record",
        "withheld-state-not-caveat",
    }


def test_corruption_of_a_declared_set_fails() -> None:
    cases = [
        (frozenset(registry.OUTPUT_CLASSES), "identity"),
        (frozenset(registry.SCOPE_GROUPS), "residual-field"),
        (frozenset(registry.TRANSFORMS), "identity"),
        (frozenset(registry.REFUSED_TRANSFORMS), "rot90"),
        (frozenset(registry.CONVENTIONS), "background-model-v1"),
    ]
    for vocabulary, member in cases:
        corrupted = frozenset(set(vocabulary) - {member})
        assert corrupted != vocabulary
        with pytest.raises(ValueError, match="not a member"):
            validate_member(corrupted, member)


def test_unknown_member_name_fails() -> None:
    with pytest.raises(ValueError, match="not a member"):
        validate_member(frozenset(registry.OUTPUT_CLASSES), "no-such-class")


def test_unplaced_output_fails() -> None:
    with pytest.raises(ValueError, match="unplaced output"):
        validate_census_line({"class": "", "non-output": "", "clause": ""})


def test_filling_every_set_correctly_turns_green() -> None:
    validate_member(frozenset(registry.OUTPUT_CLASSES), "identity")
    validate_member(frozenset(registry.SCOPE_GROUPS), "residual-field")
    validate_member(frozenset(registry.TRANSFORMS), "identity")
    validate_member(frozenset(registry.REFUSED_TRANSFORMS), "rot90")
    validate_member(frozenset(registry.CONVENTIONS), "background-model-v1")
    validate_census_line({"class": "recorded-fact", "non-output": "", "clause": ""})
    validate_census_line({
        "class": "",
        "non-output": "non-output",
        "clause": "decided-from-computation",
    })

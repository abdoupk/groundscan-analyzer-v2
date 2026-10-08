"""Registry entries and the output census.

Seam: static lint over committed artefacts. The shipped registry is the
property suite's single source of truth: every output carries exactly one
class or a named non-output clause, every convention bump names its
warrant kind and its evidence coverage apart from its grade, and the
census keys on the registry rather than on the record.
"""

from __future__ import annotations

from pathlib import Path
import re

import groundscan_analyzer.property_registry as registry

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "docs" / "contract.md"
GLOSSARY = REPO / "CONTEXT.md"

HEAD_PATTERN = re.compile(r"^\*\*([^*]+?)\*\*:")


def glossary_headwords() -> set[str]:
    """Collect glossary headwords for member resolution.

    Returns:
        The headword strings as written between leading markers.
    """
    words: set[str] = set()
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        match = HEAD_PATTERN.match(line)
        if match:
            words.add(match.group(1).strip())
    return words


def test_every_census_output_carries_one_class() -> None:
    """Each census line names a closed class with members as glossary terms."""
    assert len(registry.OUTPUT_CENSUS) == 32
    for line in registry.OUTPUT_CENSUS:
        assert line.output_class in registry.OUTPUT_CLASSES


def test_placement_test_is_only_way_in() -> None:
    """Non-outputs name the failed clause; census lines never carry both."""
    assert len(registry.NON_OUTPUTS) == 7
    for line in registry.NON_OUTPUTS:
        assert line.clause in registry.PLACEMENT_FAILURE_CLAUSES
    outputs = {line.output for line in registry.OUTPUT_CENSUS}
    non_outputs = {line.output for line in registry.NON_OUTPUTS}
    assert not outputs.intersection(non_outputs)


def test_each_convention_moves_a_class_with_named_warrant() -> None:
    """Every convention appears as a feeder with a structural warrant kind."""
    feeders = {feeder for feeders in registry.SCOPE_FEEDERS.values() for feeder in feeders}
    for convention in registry.CONVENTIONS:
        if convention == "default-numeric-reading-v1":
            continue
        assert convention in feeders
    for entry in registry.PROPERTY_ENTRIES:
        assert entry.warrant in registry.WARRANT_KINDS
        assert entry.evidence_coverage in registry.EVIDENCE_COVERAGE
        assert entry.grade in registry.GRADES


def test_non_general_warrants_say_so() -> None:
    """Entries using a non-general kind mark themselves as such."""
    non_general = [entry for entry in registry.PROPERTY_ENTRIES if entry.warrant_non_general]
    assert non_general != []
    kinds = {entry.warrant for entry in non_general}
    assert "non-constancy-in-metric-scale" in kinds
    assert "direct-dependence-on-declared-data" in kinds
    assert "reference-relativity" in kinds
    assert "route-independence" in kinds


def test_exclusion_covers_result_states() -> None:
    """Moving existence moves the limitation member beside it."""
    field_area = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "field-position" and entry.output_class == "analysis-quantity"
    )
    assert "Field area" in field_area.excluded
    limitation = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "field-position" and entry.output_class == "limitation"
    )
    assert "requires-homogeneous-axes" in limitation.excluded


def test_entries_state_survivors_with_members() -> None:
    """Strict-subset footprints enumerate members rather than naming the class."""
    positional = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "field-position" and entry.output_class == "positional-expression"
    )
    assert positional.governed == ("Scan-local position",)
    assert "Field position" in positional.excluded
    assert len(positional.feeder_exclusions) == 3


def test_convention_parts_named_without_per_part_versions() -> None:
    """Each convention names its parts; bumps declare which they carry."""
    assert registry.CONVENTION_PARTS["field-position-v1"] == (
        "divisor",
        "series-origin",
        "per-axis-independence",
    )
    for convention in registry.CONVENTIONS:
        parts = registry.CONVENTION_PARTS[convention]
        assert parts != ()
        for part in parts:
            assert "v1" not in part
            assert "v2" not in part
    for entry in registry.PROPERTY_ENTRIES:
        if not entry.scope:
            continue
        for part in entry.bump_carries:
            assert part


def test_cancelled_part_is_constrained_move() -> None:
    """The calibration constant cancels in the disagreement magnitude."""
    scale_entry = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "scale-agreement" and entry.output_class == "analysis-quantity"
    )
    assert (
        "estimator-pair" in scale_entry.bump_carries or "tolerance-form" in scale_entry.bump_carries
    )
    assert "calibration-constant" not in scale_entry.bump_carries


def test_scopes_declare_feeders_and_locality() -> None:
    """Every scope names its feeders; split footprints declare locality."""
    assert set(registry.SCOPE_FEEDERS) == set(registry.SCOPE_GROUPS)
    assert set(registry.SCOPES_WITH_LOCALITY) == {
        "residual-field",
        "field-position",
        "frame-relation",
    }
    field_feeders = registry.SCOPE_FEEDERS["field-position"]
    assert set(field_feeders) == {
        "field-position-v1",
        "relative-turn-v1",
        "canonical-reference-v1",
    }


def test_shared_entry_carries_both_answers() -> None:
    """Two feeders moving one class differently share one entry per feeder."""
    frame_positional = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "frame-relation" and entry.output_class == "positional-expression"
    )
    by_feeder = {item.feeder: item for item in frame_positional.feeder_exclusions}
    assert set(by_feeder) == {"relative-turn-v1", "canonical-reference-v1"}
    assert by_feeder["relative-turn-v1"].excluded == by_feeder["canonical-reference-v1"].excluded


def test_frame_conventions_share_ground_with_precondition() -> None:
    """Turn and reference agree on common members; reference conditions its class."""
    frame_fact = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "frame-relation" and entry.output_class == "recorded-fact"
    )
    assert "Frame relation" in frame_fact.excluded
    identity = next(
        entry
        for entry in registry.PROPERTY_ENTRIES
        if entry.scope == "frame-relation" and entry.output_class == "identity"
    )
    assert "Shared frame" in identity.excluded
    assert identity.zero_bound_condition == "path-composes-to-identity"
    assert "precondition" in identity.preconditions or "root" in identity.preconditions


def test_void_entry_names_all_classes_as_governed() -> None:
    """The admissible void convention governs every class with empty exclusions."""
    void_entries = [entry for entry in registry.PROPERTY_ENTRIES if not entry.scope]
    assert len(void_entries) == 9
    assert {entry.output_class for entry in void_entries} == set(registry.OUTPUT_CLASSES)
    for entry in void_entries:
        assert entry.excluded == ()
        assert entry.governed == (entry.output_class,)
    assert registry.REFUSED_TRANSFORMS != ()
    void_convention = "default-numeric-reading-v1"
    assert void_convention in registry.CONVENTIONS
    assert void_convention not in {
        feeder for feeders in registry.SCOPE_FEEDERS.values() for feeder in feeders
    }


def test_census_members_resolve_to_glossary_terms() -> None:
    """Strict-subset census members exist as glossary headwords."""
    words = glossary_headwords()
    for line in registry.OUTPUT_CENSUS:
        if line.output_class == "limitation":
            continue
        for member in line.members:
            assert member in words


def test_census_check_verifies_existence_never_completeness() -> None:
    """The artefact states one line per output; the module is the home."""
    text = ARTEFACT.read_text(encoding="utf-8")
    for line in registry.OUTPUT_CENSUS:
        assert f"`{line.output}`" in text
        assert f"`{line.output_class}`" in text


def test_every_mover_is_a_declared_feeder() -> None:
    """Governed means unmoved by this transform, never unmoved outright."""
    for entry in registry.PROPERTY_ENTRIES:
        if not entry.scope:
            continue
        for feeder in entry.feeders:
            assert feeder in registry.SCOPE_FEEDERS[entry.scope]


def test_evidence_coverage_apart_from_grade() -> None:
    """Coverage is recorded separately with no third grade."""
    assert set(registry.GRADES) == {"exact", "bounded"}
    assert set(registry.EVIDENCE_COVERAGE) == {"real-data", "synthetic-only", "unexercised"}
    assert set(registry.GRADES).isdisjoint(set(registry.EVIDENCE_COVERAGE))
    for entry in registry.PROPERTY_ENTRIES:
        assert entry.grade in registry.GRADES
        assert entry.evidence_coverage in registry.EVIDENCE_COVERAGE

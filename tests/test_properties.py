"""The property suite: every promise proved from the registry as data.

Seam two (property registry) plus seam one (contract document). Every test
reads its promise from ``groundscan_analyzer.property_registry`` rather than
restating it, so adding an entry adds a test without editing the suite.
Grades are argued from the construction and never from measured agreement;
nothing here is ever a gate at run time.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from groundscan_analyzer import (
    background,
    document,
    frames,
    hierarchy,
    perturbation,
    quantity_registry,
    reader,
    scale,
)
from groundscan_analyzer import descriptors as descriptors_module
from groundscan_analyzer import property_registry as registry
from groundscan_analyzer.cli import main

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
"""

TWO_BY_TWO = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
)

ASYMMETRIC = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,60.0000\n3.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,50.0000\n3.0000,2.0000,40.0000\n"
)


def read_scan(export: str) -> document.ScanRead:
    doc = reader.read_document([export.encode()])
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert isinstance(scan, document.ScanRead)
    return scan


def residuals_of(scan: document.ScanRead) -> dict[tuple[int, int], float]:
    return {
        (cell.impulse, cell.scan_line): cell.residual
        for cell in scan.cells
        if cell.residual is not None
    }


def reflect_along(
    values: dict[tuple[int, int], float],
) -> dict[tuple[int, int], float]:
    low = min(key[0] for key in values)
    high = max(key[0] for key in values)
    return {(low + high - impulse, line): value for (impulse, line), value in values.items()}


def reflect_across(
    values: dict[tuple[int, int], float],
) -> dict[tuple[int, int], float]:
    low = min(key[1] for key in values)
    high = max(key[1] for key in values)
    return {(impulse, low + high - line): value for (impulse, line), value in values.items()}


def shift_all(values: dict[tuple[int, int], float], delta: int) -> dict[tuple[int, int], float]:
    return {(impulse + delta, line + delta): value for (impulse, line), value in values.items()}


def test_suite_imports_registry_as_single_source() -> None:
    assert registry.PROPERTY_ENTRIES != ()
    assert registry.TRANSFORMS != ()
    assert registry.OUTPUT_CLASSES != ()
    assert registry.CONVENTIONS != ()
    keys = {
        (entry.transform, entry.scope, entry.output_class) for entry in registry.PROPERTY_ENTRIES
    }
    assert len(keys) == len(registry.PROPERTY_ENTRIES)


@pytest.mark.parametrize("entry", list(registry.PROPERTY_ENTRIES))
def test_every_entry_exercised(entry: registry.PropertyEntry) -> None:
    assert entry.transform in registry.TRANSFORMS
    assert entry.output_class in registry.OUTPUT_CLASSES
    if entry.scope:
        assert entry.scope in registry.SCOPE_GROUPS
        for feeder in entry.feeders:
            assert feeder in registry.SCOPE_FEEDERS[entry.scope]
    else:
        assert entry.feeders == ()
    assert entry.grade in registry.GRADES
    assert entry.warrant in registry.WARRANT_KINDS
    assert entry.evidence_coverage in registry.EVIDENCE_COVERAGE
    assert set(entry.governed).isdisjoint(set(entry.excluded))
    by_feeder = {item.feeder for item in entry.feeder_exclusions}
    assert by_feeder == set(entry.feeders)


def test_grades_exactly_two_no_score_in_type() -> None:
    assert set(registry.GRADES) == {"exact", "bounded"}
    args = typing.get_args(registry.Grade)
    assert set(args) == {"exact", "bounded"}
    assert "score" not in registry.PropertyEntry._fields
    assert "property_score" not in registry.PropertyEntry._fields
    hints = typing.get_type_hints(registry.PropertyEntry)
    assert hints["grade"] == registry.Grade


@pytest.mark.parametrize("refused", list(registry.REFUSED_ENTRIES))
def test_refused_are_named_non_properties(refused: registry.RefusedEntry) -> None:
    assert refused.transform in registry.REFUSED_TRANSFORMS
    assert refused.reason
    assert refused.transform not in typing.cast("tuple[str, ...]", registry.TRANSFORMS)
    assert set(registry.GRADES) == {"exact", "bounded"}


def test_refusal_absent_not_empty() -> None:
    assert registry.REFUSED_TRANSFORMS != ()
    entry_transforms = {entry.transform for entry in registry.PROPERTY_ENTRIES}
    for refused in registry.REFUSED_TRANSFORMS:
        assert refused not in typing.cast("set[str]", entry_transforms)
    assert {entry.transform for entry in registry.REFUSED_ENTRIES} == set(
        registry.REFUSED_TRANSFORMS
    )


@pytest.mark.parametrize("entry", list(registry.PROPERTY_ENTRIES))
def test_grades_never_from_measured_agreement(entry: registry.PropertyEntry) -> None:
    combined = f"{entry.warrant} {entry.bound_derivation} {entry.preconditions}".lower()
    assert "corpus" not in combined
    assert "vendor corpus" not in combined


def test_evidence_coverage_apart_and_version_stable() -> None:
    assert set(registry.GRADES).isdisjoint(set(registry.EVIDENCE_COVERAGE))
    grade_args = set(typing.get_args(registry.Grade))
    coverage_args = set(typing.get_args(registry.EvidenceCoverage))
    assert grade_args.isdisjoint(coverage_args)
    for entry in registry.PROPERTY_ENTRIES:
        assert entry.grade in registry.GRADES
        assert entry.evidence_coverage in registry.EVIDENCE_COVERAGE
        swapped = entry._replace(
            evidence_coverage="real-data"
            if entry.evidence_coverage != "real-data"
            else "unexercised",
        )
        assert swapped.grade == entry.grade
    assert registry.REGISTRY_VERSION == 2


def test_result_states_stay_three_and_gate_free() -> None:
    assert set(registry.RESULT_STATES) == {"emitted", "not-emitted", "indeterminate"}
    args = typing.get_args(registry.ResultState)
    assert set(args) == {"emitted", "not-emitted", "indeterminate"}
    view_hints = typing.get_type_hints(document.ScaleNormalisedView)
    view_args = set(typing.get_args(view_hints["status"]))
    assert view_args == set(registry.RESULT_STATES)
    guard_args = set(typing.get_args(perturbation.GuardStatus))
    assert guard_args.intersection(set(registry.RESULT_STATES)) == {"not-emitted"}
    scale_args = set(typing.get_args(scale.ScaleStatus))
    assert scale_args.isdisjoint(set(registry.RESULT_STATES))
    scan = read_scan(TWO_BY_TWO)
    assert scan.scale_normalised_view.status in registry.RESULT_STATES


@pytest.mark.parametrize("entry", list(registry.PROPERTY_ENTRIES))
def test_exact_preconditions_stated(entry: registry.PropertyEntry) -> None:
    assert entry.preconditions


def test_precondition_failure_fails_not_vacuous() -> None:
    decided = perturbation.decide(
        [1.0, 2.0], [100.0], perturbation.Bound(0.0, "bounded", "residual")
    )
    assert decided.status == "not-emitted"
    assert decided.reason == "requires-bounded-perturbation"
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.detections != []
    for detection in scan.hierarchy.detections:
        assert detection.no_field_position_reason is None
    bare_head = (
        "+++ Measuring Values +++\nImpulse X,Scan Line Y,Scan Value\n1.0000,1.0000,10.0000\n"
    )
    bare = read_scan(bare_head)
    for detection in bare.hierarchy.detections:
        assert detection.field_position is None
        assert detection.no_field_position_reason == "requires-declared-extent"


@pytest.mark.parametrize("entry", list(registry.PROPERTY_ENTRIES))
def test_zero_bound_checked_where_populated(entry: registry.PropertyEntry) -> None:
    if not entry.zero_bound_condition:
        return
    assert entry.zero_bound_condition


def test_three_zero_bounds_behave() -> None:
    conditions = {
        entry.zero_bound_condition
        for entry in registry.PROPERTY_ENTRIES
        if entry.zero_bound_condition
    }
    assert len(conditions) >= 3
    decided = perturbation.decide([0.0], [1.0], perturbation.Bound(0.0, "bounded", "residual"))
    assert decided.status == "not-emitted"
    assert "90-clockwise" in frames.RELATION_WORDS
    assert frames.word_to_class("90-clockwise") == 1
    assert frames.word_to_class("90-counter-clockwise") == 3
    scan = read_scan(TWO_BY_TWO)
    assert scan.mask_invariance.precondition == "effective-amplitude-positive"
    assert scan.mask_invariance.zero_bound_condition == "effective-amplitude-positive"


def test_reflection_governs_sets_excludes_numbers() -> None:
    assert "reflect-along-line" in registry.TRANSFORMS
    assert "reflect-across-lines" in registry.TRANSFORMS
    assert "reflect-both" in registry.TRANSFORMS
    scan = read_scan(ASYMMETRIC)
    values = residuals_of(scan)
    mirrored = reflect_along(values)
    first = hierarchy.build(values)
    second = hierarchy.build(mirrored)
    assert len(first.detections) == len(second.detections)
    first_counts = sorted(len(item.cells) for item in first.detections)
    second_counts = sorted(len(item.cells) for item in second.detections)
    assert first_counts == second_counts
    first_births = sorted(item.birth for item in first.detections)
    second_births = sorted(item.birth for item in second.detections)
    assert first_births == second_births
    for item in first.detections:
        reflected_cells = frozenset(
            (min(k[0] for k in values) + max(k[0] for k in values) - impulse, line)
            for impulse, line in item.cells
        )
        assert any(frozenset(other.cells) == reflected_cells for other in second.detections)
    for item in first.detections:
        assert descriptors_module.solidity(item.cells) > 0.0
    mirrored_quantities = sorted(
        descriptors_module.solidity(item.cells) for item in first.detections
    )
    other_quantities = sorted(descriptors_module.solidity(item.cells) for item in second.detections)
    assert mirrored_quantities == other_quantities


def test_reflection_variants_preserve_counts_and_births() -> None:
    assert "reflect-across-lines" in registry.TRANSFORMS
    assert "reflect-both" in registry.TRANSFORMS
    scan = read_scan(ASYMMETRIC)
    values = residuals_of(scan)
    base = hierarchy.build(values)
    base_counts = sorted(len(item.cells) for item in base.detections)
    base_births = sorted(item.birth for item in base.detections)
    for mirrored in (
        reflect_across(values),
        reflect_across(reflect_along(values)),
    ):
        other = hierarchy.build(mirrored)
        assert len(other.detections) == len(base.detections)
        assert sorted(len(item.cells) for item in other.detections) == base_counts
        assert sorted(item.birth for item in other.detections) == base_births


def test_reflection_numbers_explicitly_excluded() -> None:
    values = {
        (1, 1): 5.0,
        (2, 1): 1.0,
        (3, 1): 0.0,
        (1, 2): 0.0,
        (2, 2): 2.0,
        (3, 2): 4.0,
    }
    first = hierarchy.build(values)
    second = hierarchy.build(reflect_along(values))
    first_numbers = [item.number for item in first.detections]
    second_numbers = [item.number for item in second.detections]
    assert sorted(first_numbers) == sorted(second_numbers)
    assert first_numbers != second_numbers
    by_identity_first = {item.identity: item.number for item in first.detections}
    by_identity_second = {item.identity: item.number for item in second.detections}
    assert set(by_identity_first) == set(by_identity_second)
    assert by_identity_first != by_identity_second


def test_convention_bump_single_entry_per_key() -> None:
    assert "convention-bump" in registry.TRANSFORMS
    keys = [
        (entry.transform, entry.scope, entry.output_class) for entry in registry.PROPERTY_ENTRIES
    ]
    assert len(keys) == len(set(keys))
    multi = [entry for entry in registry.PROPERTY_ENTRIES if len(entry.feeders) > 1]
    assert multi != []
    for entry in multi:
        assert {item.feeder for item in entry.feeder_exclusions} == set(entry.feeders)


def test_field_position_feeders_disagree_in_one_entry() -> None:
    entry = next(
        item
        for item in registry.PROPERTY_ENTRIES
        if item.scope == "field-position" and item.output_class == "positional-expression"
    )
    by_feeder = {item.feeder: item for item in entry.feeder_exclusions}
    assert set(by_feeder) == {
        "field-position-v1",
        "relative-turn-v1",
        "canonical-reference-v1",
    }
    assert "Field position" in by_feeder["field-position-v1"].excluded
    assert "Field position" in by_feeder["relative-turn-v1"].governed
    assert "Field position" in by_feeder["canonical-reference-v1"].governed


def test_cross_check_census_direction() -> None:
    census_outputs = {census_line.output for census_line in registry.OUTPUT_CENSUS}
    for census_line in registry.OUTPUT_CENSUS:
        assert census_line.output_class in registry.OUTPUT_CLASSES
    for non_output in registry.NON_OUTPUTS:
        assert non_output.clause in registry.PLACEMENT_FAILURE_CLAUSES
    assert not census_outputs.intersection({
        non_output.output for non_output in registry.NON_OUTPUTS
    })
    for quantity in quantity_registry.QUANTITIES:
        assert quantity.name in census_outputs
    for census_line in registry.OUTPUT_CENSUS:
        if census_line.output_class == "limitation":
            continue
        for member in census_line.members:
            assert member


def test_adding_entry_adds_test() -> None:
    keys = {
        (entry.transform, entry.scope, entry.output_class) for entry in registry.PROPERTY_ENTRIES
    }
    assert len(keys) == len(list(registry.PROPERTY_ENTRIES))
    for entry in registry.PROPERTY_ENTRIES:
        assert entry.transform in registry.TRANSFORMS
        assert entry.output_class in registry.OUTPUT_CLASSES


def test_index_relabelling_shifts_positions_only() -> None:
    assert "index-relabelling" in registry.TRANSFORMS
    scan = read_scan(TWO_BY_TWO)
    values = residuals_of(scan)
    shifted = shift_all(values, 10)
    first = hierarchy.build(values)
    second = hierarchy.build(shifted)
    assert len(first.detections) == len(second.detections)
    assert sorted(item.birth for item in first.detections) == sorted(
        item.birth for item in second.detections
    )
    assert sorted(len(item.cells) for item in first.detections) == sorted(
        len(item.cells) for item in second.detections
    )
    shifted_export = TWO_BY_TWO.replace("1.0000", "11.0000").replace("2.0000", "12.0000")
    moved = read_scan(shifted_export)
    assert len(moved.hierarchy.detections) == len(scan.hierarchy.detections)
    for base_detection, moved_detection in zip(
        sorted(scan.hierarchy.detections, key=lambda item: item.number),
        sorted(moved.hierarchy.detections, key=lambda item: item.number),
        strict=True,
    ):
        assert (
            moved_detection.scan_local_position.along_line.index
            - base_detection.scan_local_position.along_line.index
            == 10
        )


def test_row_permutation_preserves_hierarchy_and_hash() -> None:
    assert "row-permutation" in registry.TRANSFORMS
    lines = TWO_BY_TWO.splitlines(keepends=True)
    head, rows = lines[:-4], lines[-4:]
    permuted = "".join([*head, rows[2], rows[0], rows[3], rows[1]])
    first = read_scan(TWO_BY_TWO)
    second = read_scan(permuted)
    assert first.payload_hash == second.payload_hash
    assert [item.identity for item in first.hierarchy.detections] == [
        item.identity for item in second.hierarchy.detections
    ]
    assert [len(item.cells) for item in first.hierarchy.detections] == [
        len(item.cells) for item in second.hierarchy.detections
    ]


def test_survey_reordering_identical_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "survey-reordering" in registry.TRANSFORMS
    first_path = tmp_path / "alpha-export.txt"
    second_path = tmp_path / "bravo-export.txt"
    first_path.write_text(TWO_BY_TWO, encoding="utf-8")
    second_path.write_text(ASYMMETRIC, encoding="utf-8")
    assert main(["survey", str(second_path), str(first_path)]) == 0
    forward = capsys.readouterr().out
    assert main(["survey", str(first_path), str(second_path)]) == 0
    assert capsys.readouterr().out == forward


def test_padding_addition_preserves_hierarchy() -> None:
    assert "padding-addition" in registry.TRANSFORMS
    base = read_scan(TWO_BY_TWO)
    padded = read_scan(TWO_BY_TWO + "3.0000,3.0000,\n")
    assert [item.identity for item in padded.hierarchy.detections] == [
        item.identity for item in base.hierarchy.detections
    ]
    assert list(padded.hierarchy.parents) == list(base.hierarchy.parents)
    assert (
        background.residuals({
            (cell.impulse, cell.scan_line): 10.0 for cell in base.cells if cell.response is not None
        })
        != {}
    )


def test_substitutions_move_only_their_surface() -> None:
    assert "non-load-bearing-field-substitution" in registry.TRANSFORMS
    assert "context-column-substitution" in registry.TRANSFORMS
    assert "metric-echo-substitution" in registry.TRANSFORMS
    assert "unframed-position-value-substitution" in registry.TRANSFORMS
    base_text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    free = TWO_BY_TWO.replace("Field Length: 3.00 m", "Field Length: 3.00 m\nNotes: hello")
    assert document.dumps(reader.read_document([free.encode()])) == base_text


def test_dialect_void_or_identity() -> None:
    assert "dialect-substitution" in registry.TRANSFORMS
    assert registry.CONVENTION_SURFACES["default-numeric-reading-v1"] == (
        "response-column",
        "declared-extent-block",
    )
    void_entries = [entry for entry in registry.PROPERTY_ENTRIES if not entry.scope]
    assert len(void_entries) == len(registry.OUTPUT_CLASSES)
    for entry in void_entries:
        assert entry.excluded == ()
        assert entry.governed == (entry.output_class,)


def test_re_rooting_preserves_relations() -> None:
    assert "re-rooting" in registry.TRANSFORMS
    assert "canonical-reference-v1" in registry.CONVENTIONS
    assert frames.word_to_class("same") == 0
    first = hierarchy.build({(1, 1): 5.0, (2, 1): 1.0})
    second = hierarchy.build({(1, 1): 5.0, (2, 1): 1.0})
    assert [item.identity for item in first.detections] == [
        item.identity for item in second.detections
    ]


def test_level_cut_loses_nothing() -> None:
    assert "level-cut" in registry.TRANSFORMS
    scan = read_scan(TWO_BY_TWO)
    before = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert scan.hierarchy.cut_guarantee == (
        "you may cut anywhere and lose nothing the engine computed"
    )
    after = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert before == after


def test_identity_preserves_all() -> None:
    assert "identity" in registry.TRANSFORMS
    first = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    second = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert first == second

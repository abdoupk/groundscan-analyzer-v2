"""The synthetic scenario arm: manufactured surveys for the perpendicular case.

Seam: the contract document. Behavioural tests run the synthetic arm
over manufactured bytes with fixture-asserted declarations and assert on
the document it emits. Generator checks read the arm source directly,
where the record cannot isolate exactness from platform luck.
"""

from __future__ import annotations

import ast
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import typing

import pytest

from groundscan_analyzer import document, frames, reader, synthetic
from groundscan_analyzer.cli import main
from groundscan_analyzer.synthetic import build_required_cases

DATA = Path(__file__).resolve().parent / "data" / "synthetic"
MANIFEST = DATA / "manifest.json"

GENERATOR_FNS = (
    synthetic.format_extent,
    synthetic.format_response,
    synthetic.pitch_fraction,
    synthetic.make_export,
    synthetic.center_of_scan,
    synthetic.oracle_express,
    synthetic._header_for,
    synthetic._cell_text,
    synthetic._row_line,
    synthetic._square_at,
    synthetic._wrap,
    synthetic._perp_equal,
    synthetic._perp_unequal,
    synthetic._missing,
    synthetic._contradictory,
    synthetic._contradictory_mirror,
    synthetic._closing,
    synthetic._signed_cw,
    synthetic._signed_ccw,
    synthetic._reversal,
    synthetic._single_empty,
    synthetic._presence_absent,
    synthetic._presence_empty,
    synthetic._presence_value,
)


def case_doc(name: str) -> tuple[synthetic.SyntheticCase, document.Document]:
    """Read one required case through the synthetic entry point.

    Args:
        name: The required case name.

    Returns:
        The case with its survey document.
    """
    case = build_required_cases()[name]
    return case, synthetic.read_synthetic_document(case)


def read_scan(doc: document.Document, position: int) -> document.ScanRead:
    """Read one survey scan record by intake position.

    Args:
        doc: The survey document.
        position: The intake position.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    scan = doc.scans[position]
    assert scan.status == "read"
    assert isinstance(scan, document.ScanRead)
    return scan


def test_generator_uses_no_float_arithmetic() -> None:
    """Generator functions hold no float names and no float constants.

    Failing input: a generator computing a pitch with float(span) over (n - 1).
    """
    for fn in GENERATOR_FNS:
        tree = ast.parse(inspect.getsource(fn))
        names_float = any(
            isinstance(node, ast.Name) and node.id == "float" for node in ast.walk(tree)
        )
        assert not names_float
        holds_float = any(
            isinstance(node, ast.Constant) and isinstance(node.value, float)
            for node in ast.walk(tree)
        )
        assert not holds_float


def test_pitches_are_exact_rationals_not_floats() -> None:
    """Pitch arithmetic is Fraction equality, never float closeness.

    Failing input: asserting `pitch == 1.6666666666666667` instead of `Fraction(5, 3)`.
    """
    assert synthetic.pitch_fraction(300, 4) == Fraction(1, 1)
    assert synthetic.pitch_fraction(500, 4) == Fraction(5, 3)
    assert synthetic.pitch_fraction(700, 4) == Fraction(7, 3)
    assert synthetic.pitch_fraction(200, 3) == Fraction(1, 1)


def test_frozen_bytes_do_not_drift() -> None:
    """Regenerating every frozen case yields the committed bytes exactly.

    Failing input: a generator edit or a hand-edited frozen file.
    """
    for name, case in build_required_cases().items():
        for position, payload in enumerate(synthetic.exports_of(case)):
            frozen = (DATA / f"{name}-{position}.txt").read_bytes()
            assert payload == frozen, f"{name}-{position} drifted"


def test_manifest_covers_required_cases() -> None:
    """The manifest names every required file with its hash and generator.

    Failing input: a frozen file with no manifest line, or a stale hash.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["generator"] == synthetic.GENERATOR_VERSION
    assert set(manifest["cases"]) == set(synthetic.REQUIRED_CASE_NAMES)
    for name, case in build_required_cases().items():
        for position, payload in enumerate(synthetic.exports_of(case)):
            key = f"{name}-{position}.txt"
            digest = hashlib.sha256(payload).hexdigest()
            assert manifest["files"][key] == digest, key
            assert (DATA / key).read_bytes() == payload


def test_every_assertion_carries_fixture_source_at_entry() -> None:
    """Every required case sources every declaration from the fixture entry.

    Failing input: a case with an `operator-asserted` source reading as a finding.
    """
    for name, case in build_required_cases().items():
        assert case.sources != ()
        assert set(case.sources) == {synthetic.FIXTURE_SOURCE}, name
        doc = synthetic.read_synthetic_document(case)
        assert len(doc.scans) == len(case.specs)


def test_synthetic_scales_carry_fixture_source() -> None:
    """Synthetic extents read as fixture-asserted, never operator-asserted.

    Failing input: a synthetic document recording `operator-asserted` spans.
    """
    _, doc = case_doc("perp-equal")
    for position in (0, 1):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.field_position is not None
            for axis in (
                detection.field_position.along_line,
                detection.field_position.across_lines,
            ):
                assert axis.scale.span_provenance == synthetic.FIXTURE_SOURCE
    control = reader.read_document(list(synthetic.exports_of(build_required_cases()["perp-equal"])))
    for detection in read_scan(control, 0).hierarchy.detections:
        assert detection.field_position is not None
        assert (
            detection.field_position.along_line.scale.span_provenance == synthetic.OPERATOR_SOURCE
        )


def test_declared_relations_carry_entry_source() -> None:
    """Relations echo with the loader source, fixture on the synthetic path.

    Failing input: a synthetic relation echoing `operator-asserted`.
    """
    _, doc = case_doc("contradictory")
    assert doc.declared_relations != []
    for declared in doc.declared_relations:
        assert declared.source == synthetic.FIXTURE_SOURCE
    control = reader.read_document(
        list(synthetic.exports_of(build_required_cases()["contradictory"])),
        [frames.Relation(0, 1, "same")],
    )
    for declared in control.declared_relations:
        assert declared.source == synthetic.OPERATOR_SOURCE


def code_strings(path: Path) -> list[str]:
    """Non-docstring string constants in one module.

    Docstrings are prose, not values the engine can assign: the check
    mirrors the vocabulary lint's docstring exclusion rather than
    grepping file text.

    Args:
        path: The module file to read.

    Returns:
        The code string constants in walk order.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_sources_live_in_contract_vocabulary_only() -> None:
    """The closed source vocabulary is declared once; files cannot claim one.

    Failing input: `reader.py` deciding a source from file content.
    """
    assert set(typing.get_args(document.AssertionSource)) == {
        synthetic.OPERATOR_SOURCE,
        synthetic.FIXTURE_SOURCE,
    }
    repo = Path(__file__).resolve().parents[1] / "src" / "groundscan_analyzer"
    for filename in ("frames.py", "positions.py", "cli.py"):
        text = (repo / filename).read_text(encoding="utf-8")
        assert "fixture-asserted" not in text, filename
    assert not [text for text in code_strings(repo / "reader.py") if "fixture-asserted" in text]
    harness = (repo / "synthetic.py").read_text(encoding="utf-8")
    assert "document_module.FIXTURE_SOURCE" in harness
    labelled = synthetic.make_export(build_required_cases()["single-empty"].specs[0])
    labelled = labelled.replace(b"Field Width:", b"Notes: fixture-asserted\nField Width:")
    doc = reader.read_document([labelled])
    for detection in read_scan(doc, 0).hierarchy.detections:
        assert detection.field_position is not None
        assert (
            detection.field_position.along_line.scale.span_provenance == synthetic.OPERATOR_SOURCE
        )


def test_operator_entry_points_accept_no_fixture_label() -> None:
    """The operator surface takes no source argument and asserts operator.

    Failing input: a `--source fixture-asserted` flag on the command line.
    """
    assert "fixture" not in inspect.signature(main).parameters
    assert "source" not in inspect.signature(main).parameters
    assert "assertion_sources" not in inspect.signature(main).parameters


def test_real_loader_asserts_operator_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Command-line reads record operator spans with no limitations.

    Failing input: a CLI document recording fixture spans.
    """
    export = tmp_path / "operator-export.txt"
    export.write_bytes(synthetic.exports_of(build_required_cases()["single-empty"])[0])
    assert main(["scan", str(export)]) == 0
    doc = document.loads(capsys.readouterr().out)
    for detection in read_scan(doc, 0).hierarchy.detections:
        assert detection.field_position is not None
        assert (
            detection.field_position.along_line.scale.span_provenance == synthetic.OPERATOR_SOURCE
        )
        assert set(detection.limitations) == set()


def test_engine_carries_limitation_by_rule_not_content() -> None:
    """The limitation literal lives in the contract; the engine only carries it.

    Failing input: `reader.py` containing `fixture-asserted-declaration`.
    """
    assert list(typing.get_args(document.ClaimLimitation)) == [synthetic.FIXTURE_LIMITATION]
    repo = Path(__file__).resolve().parents[1] / "src" / "groundscan_analyzer"
    for filename in ("reader.py", "frames.py", "positions.py", "cli.py", "synthetic.py"):
        text = (repo / filename).read_text(encoding="utf-8")
        assert "fixture-asserted-declaration" not in text, filename


def test_limitations_name_fixture_source_by_exact_set_equality() -> None:
    """Each detection and frame limitation equals the singleton on the record.

    Failing input: a synthetic detection carrying no limitation at all.
    """
    for name, case in build_required_cases().items():
        assert set(synthetic.case_limitations(case)) == {synthetic.FIXTURE_LIMITATION}, name
        _, doc = case_doc(name)
        for position in range(len(doc.scans)):
            for detection in read_scan(doc, position).hierarchy.detections:
                assert set(detection.limitations) == {synthetic.FIXTURE_LIMITATION}, name
        for frame in doc.frames:
            assert set(frame.limitations) == {synthetic.FIXTURE_LIMITATION}, name


def test_operator_documents_carry_empty_limitations() -> None:
    """Operator-path claims state no limitations rather than leaving them out.

    Failing input: an operator detection carrying the fixture limitation.
    """
    doc = reader.read_document(
        list(synthetic.exports_of(build_required_cases()["perp-equal"])),
        [frames.Relation(0, 1, "90-clockwise")],
    )
    assert doc.frames != []
    for position in (0, 1):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert set(detection.limitations) == set()
    for frame in doc.frames:
        assert set(frame.limitations) == set()


def test_mixed_sources_coexist_with_over_caveating() -> None:
    """Sources may coexist; any fixture touch caves the shared claim.

    Failing input: a mixed relation echoing `operator-asserted`.
    """
    exports = list(synthetic.exports_of(build_required_cases()["perp-equal"]))
    doc = reader.read_document(
        exports,
        [frames.Relation(0, 1, "90-clockwise")],
        assertion_sources=[synthetic.OPERATOR_SOURCE, synthetic.FIXTURE_SOURCE],
    )
    first_spans = {
        detection.field_position.along_line.scale.span_provenance
        for detection in read_scan(doc, 0).hierarchy.detections
        if detection.field_position is not None
    }
    second_spans = {
        detection.field_position.along_line.scale.span_provenance
        for detection in read_scan(doc, 1).hierarchy.detections
        if detection.field_position is not None
    }
    assert first_spans == {synthetic.OPERATOR_SOURCE}
    assert second_spans == {synthetic.FIXTURE_SOURCE}
    assert [declared.source for declared in doc.declared_relations] == [synthetic.FIXTURE_SOURCE]
    assert [set(frame.limitations) for frame in doc.frames] == [{synthetic.FIXTURE_LIMITATION}]
    assert {
        limitation
        for detection in read_scan(doc, 0).hierarchy.detections
        for limitation in detection.limitations
    } == set()
    with pytest.raises(ValueError, match="assertion sources name no scan"):
        reader.read_document(exports, assertion_sources=[synthetic.FIXTURE_SOURCE])
    with pytest.raises(ValueError, match="unknown assertion source"):
        reader.read_document(exports, assertion_sources=["someone-said-it", "someone-said-it"])


def test_perpendicular_equal_pitches() -> None:
    """Equal pitches compose under one clockwise turn with homogeneous scales.

    Failing input: transposed extents swapped the wrong way, giving 3/2 pitches.
    """
    case, doc = case_doc("perp-equal")
    assert [r.word for r in case.relations] == ["90-clockwise"]
    first, second = case.specs
    assert synthetic.pitch_fraction(first.length_hundredths, first.impulse_total) == Fraction(1, 1)
    assert synthetic.pitch_fraction(second.length_hundredths, second.impulse_total) == Fraction(
        1, 1
    )
    assert len(doc.frames) == 1
    for position in (0, 1):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is not None
            assert detection.shared_frame_position.homogeneous is True


def test_perpendicular_unequal_pitches_are_exact_rationals() -> None:
    """Unequal pitches assert as Fractions, with inhomogeneous shared scales.

    Failing input: comparing `1.6666666666666667 == 5 / 3` as floats.
    """
    case, doc = case_doc("perp-unequal")
    assert [r.word for r in case.relations] == ["90-counter-clockwise"]
    first, second = case.specs
    assert synthetic.pitch_fraction(first.length_hundredths, first.impulse_total) == Fraction(5, 3)
    assert synthetic.pitch_fraction(second.width_hundredths, second.line_total) == Fraction(7, 3)
    assert len(doc.frames) == 1
    for position in (0, 1):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is not None
            assert detection.shared_frame_position.homogeneous is False


def test_missing_withdraws_only_shared_position() -> None:
    """An isolated scan loses its shared position and nothing else.

    Failing input: a missing link refusing the isolated scan or emptying its tree.
    """
    _, doc = case_doc("missing")
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [0, 1]
    lone = read_scan(doc, 2)
    for detection in lone.hierarchy.detections:
        assert detection.shared_frame_position is None
        assert detection.no_shared_position_reason == "missing-orientation-path"
        assert detection.scan_local_position is not None
    for position in (0, 1):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is not None
    assert doc.contradictions == []


def test_contradictory_withdraws_component_only() -> None:
    """A disagreeing triple withdraws while the untouched pair stays framed.

    Failing input: a contradiction emptying the clean pair's shared positions.
    """
    _, doc = case_doc("contradictory")
    assert len(doc.contradictions) == 1
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [3, 4]
    for position in (0, 1, 2):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is None
            assert detection.no_shared_position_reason == "withdrawn-component"
    for position in (3, 4):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is not None


def test_contradictory_mirror_withdraws_component_only() -> None:
    """The odd-class mirror disagrees while the untouched pair stays framed.

    Failing input: a mirror declaring `same` on the closing edge, closing
    where it must contradict.
    """
    _, doc = case_doc("contradictory-mirror")
    assert len(doc.contradictions) == 1
    edge = doc.contradictions[0]
    assert (edge.first, edge.second, edge.relation) == (0, 2, "same")
    assert edge.declared_class == 0
    assert edge.expected_class == 2
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [3, 4]
    for position in (0, 1, 2):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is None
            assert detection.no_shared_position_reason == "withdrawn-component"
    for position in (3, 4):
        for detection in read_scan(doc, position).hierarchy.detections:
            assert detection.shared_frame_position is not None
    _, even = case_doc("contradictory")
    assert {r.relation for r in even.declared_relations} != {
        r.relation for r in doc.declared_relations
    }


def test_closing_cycle_closes() -> None:
    """Same plus opposite twice composes to the identity with no contradiction.

    Failing input: declaring the closing edge as `same` instead of `opposite`.
    """
    _, doc = case_doc("closing")
    assert doc.contradictions == []
    assert len(doc.frames) == 1
    assert doc.frames[0].members == [0, 1, 2]


def test_mirror_signed_cycles_close() -> None:
    """Clockwise and counter-clockwise signed cycles both close as mirrors.

    Failing input: a mirror declaring `opposite` as `same`, breaking closure.
    """
    _, clockwise = case_doc("closing-signed-cw")
    _, mirror = case_doc("closing-signed-ccw")
    assert clockwise.contradictions == []
    assert mirror.contradictions == []
    assert len(clockwise.frames) == 1
    assert len(mirror.frames) == 1
    clockwise_classes = {
        entry.scan: entry.relation_class for entry in clockwise.frames[0].relations
    }
    mirror_classes = {entry.scan: entry.relation_class for entry in mirror.frames[0].relations}
    assert clockwise_classes != mirror_classes
    assert set(clockwise_classes) == set(mirror_classes) == {0, 1, 2}


def test_edge_reversal_with_inverse_relation() -> None:
    """Reversing an edge with the inverse word preserves the frame exactly.

    Failing input: reversing the edge without inverting the word.
    """
    case = build_required_cases()["reversal"]
    forward = synthetic.read_synthetic_document(case)
    reversed_case = synthetic.SyntheticCase(
        name="reversal-check",
        specs=case.specs,
        relations=(frames.Relation(1, 0, "90-counter-clockwise"),),
        sources=case.sources,
        limitations=case.limitations,
    )
    backward = synthetic.read_synthetic_document(reversed_case)
    assert forward.contradictions == backward.contradictions == []
    assert len(forward.frames) == len(backward.frames) == 1
    assert forward.frames[0].members == backward.frames[0].members
    forward_classes = tuple(
        (entry.scan, entry.relation_class) for entry in forward.frames[0].relations
    )
    backward_classes = tuple(
        (entry.scan, entry.relation_class) for entry in backward.frames[0].relations
    )
    assert forward_classes == backward_classes


def test_both_turn_directions_covered() -> None:
    """The frozen set declares clockwise and counter-clockwise turns.

    Failing input: a frozen set declaring only `90-clockwise` turns.
    """
    words = {
        relation.word for case in build_required_cases().values() for relation in case.relations
    }
    assert "90-clockwise" in words
    assert "90-counter-clockwise" in words


def test_single_empty_declaration_synthesises_nothing() -> None:
    """One scan with no declarations yields no frame and no implicit same.

    Failing input: an engine synthesising `same` for a solitary scan.
    """
    case, doc = case_doc("single-empty")
    assert case.relations == ()
    assert doc.frames == []
    assert doc.declared_relations == []
    assert doc.contradictions == []
    scan = read_scan(doc, 0)
    assert scan.hierarchy.detections != []
    for detection in scan.hierarchy.detections:
        assert detection.shared_frame_position is None
        assert detection.no_shared_position_reason == "missing-orientation-path"


def test_all_three_presence_states_covered() -> None:
    """Absent, empty and valued discarded columns each have a frozen case.

    Failing input: a frozen set with no `present-but-empty` scan.
    """
    assert read_scan(case_doc("presence-absent")[1], 0).latitude_presence == "absent"
    assert read_scan(case_doc("presence-absent")[1], 0).longitude_presence == "absent"
    empty = read_scan(case_doc("presence-empty")[1], 0)
    assert empty.latitude_presence == "present-but-empty"
    assert empty.longitude_presence == "present-but-empty"
    valued = read_scan(case_doc("presence-value-a")[1], 0)
    assert valued.latitude_presence == "present-with-value"
    assert valued.longitude_presence == "present-with-value"


def test_differing_values_produce_identical_outputs() -> None:
    """Two valued exports differing only in discarded numbers read identically.

    Failing input: a discarded coordinate value leaking into any record field.
    """
    _, first = case_doc("presence-value-a")
    _, second = case_doc("presence-value-b")
    assert document.dumps(first) == document.dumps(second)


def test_cases_require_detections_away_from_fixed_points() -> None:
    """Every frozen case emits a detection per scan away from coincidence.

    Failing input: a perpendicular case spiking only the lattice centre.
    """
    for case in build_required_cases().values():
        doc = synthetic.read_synthetic_document(case)
        synthetic.require_detections_away_from_fixed_points(doc, case)


def test_vacuity_reports_in_own_vocabulary() -> None:
    """A centred detection reports vacuity instead of passing quietly."""
    centred = synthetic.ScanSpec(3, 3, 300, 300, 10, 2, 2, 310, "absent", "absent", 0, 0)
    case = synthetic.SyntheticCase(
        name="centred-only",
        specs=(centred, centred),
        relations=(frames.Relation(0, 1, "90-clockwise"),),
        sources=(synthetic.FIXTURE_SOURCE, synthetic.FIXTURE_SOURCE),
        limitations=(synthetic.FIXTURE_LIMITATION,),
    )
    doc = synthetic.read_synthetic_document(case)
    with pytest.raises(synthetic.VacuousCaseError, match="vacuous:"):
        synthetic.require_detections_away_from_fixed_points(doc, case)


def doc_with_detection_cells(
    doc: document.Document, position: int, cells: list[tuple[int, int]]
) -> document.Document:
    """Rebuild one survey document with fabricated detection cells.

    The fabrication isolates the cell-collection rule from background
    behaviour: count, location, size and polarity are out of scope, so
    only which cells the check reads matters.

    Args:
        doc: The survey document over the synthetic exports.
        position: The intake position whose detections to replace.
        cells: The fabricated lattice cells for the first detection.

    Returns:
        The document carrying the fabricated first detection.
    """
    scan = read_scan(doc, position)
    first = scan.hierarchy.detections[0]
    rebuilt = document.Detection(**{
        **first.model_dump(),
        "cells": [
            document.DetectionCell(impulse=impulse, scan_line=line) for impulse, line in cells
        ],
        "cell_count": len(cells),
    })
    hierarchy = document.Hierarchy(**{**scan.hierarchy.model_dump(), "detections": [rebuilt]})
    scans = list(doc.scans)
    scans[position] = scan.model_copy(update={"hierarchy": hierarchy})
    return doc.model_copy(update={"scans": scans})


def test_vacuity_counts_every_cell_of_a_detection() -> None:
    """A detection straddling coincidence counts through its off-centre cell.

    Failing input: judging a detection by its representative cell alone.
    """
    centred = synthetic.ScanSpec(3, 3, 300, 300, 10, 1, 1, 310, "absent", "absent", 0, 0)
    case = synthetic.SyntheticCase(
        name="straddle-only",
        specs=(centred,),
        relations=(frames.Relation(0, 0, "90-clockwise"),),
        sources=(synthetic.FIXTURE_SOURCE,),
        limitations=(synthetic.FIXTURE_LIMITATION,),
    )
    doc = synthetic.read_synthetic_document(case)
    straddling = doc_with_detection_cells(doc, 0, [(2, 2), (1, 1)])
    synthetic.require_detections_away_from_fixed_points(straddling, case)
    centred_only = doc_with_detection_cells(doc, 0, [(2, 2)])
    with pytest.raises(synthetic.VacuousCaseError, match="vacuous:"):
        synthetic.require_detections_away_from_fixed_points(centred_only, case)


def test_turn_oracle_reads_contract_table() -> None:
    """The oracle follows the versioned table, including the coincidence set.

    Failing input: an oracle hard-coding `swap=True, signs=(1, -1)` prose.
    """
    assert "TURN_TABLE" in inspect.getsource(synthetic.oracle_express)
    assert "TURN_TABLE" in inspect.getsource(synthetic.coincident_under_both_turns)
    centre = (Fraction(5, 2), Fraction(5, 2))
    reference = (Fraction(5, 2), Fraction(5, 2))
    for relation_class in (0, 1, 2, 3):
        for impulse in (1, 4):
            for scan_line in (1, 4):
                expected = synthetic.oracle_express(
                    relation_class, centre, reference, impulse, scan_line
                )
                found = frames.express(
                    relation_class,
                    (2.5, 2.5),
                    (2.5, 2.5),
                    impulse,
                    scan_line,
                )
                # Halves are exact in binary64, so Fraction reads them exactly.
                assert Fraction(found[0]) == expected[0]
                assert Fraction(found[1]) == expected[1]
    odd_centre = (Fraction(2, 1), Fraction(2, 1))
    assert synthetic.coincident_under_both_turns(odd_centre, 2, 2) is True
    assert synthetic.coincident_under_both_turns(odd_centre, 1, 1) is False


def test_no_detection_contains_cross_scan_cells() -> None:
    """Shared frames relate lattices without merging cells or counting across.

    Retained against #135: no detection holds cells from more than one
    scan with its contributing payload identity kept, and counting stays
    per scan including over an overlap. The synthetic perpendicular
    surveys are the only place this is exercisable, since no real cross-
    pitch pair exists. Failing input: a shared-frame position merging two
    scans' cells.
    """
    for name in ("perp-equal", "perp-unequal", "missing", "contradictory"):
        _, doc = case_doc(name)
        for position in range(len(doc.scans)):
            scan = read_scan(doc, position)
            lattice = {
                (impulse, line)
                for impulse in scan.lattice.impulses
                for line in scan.lattice.scan_lines
            }
            for detection in scan.hierarchy.detections:
                assert detection.scan_payload_hash == scan.payload_hash
                for cell in detection.cells:
                    assert (cell.impulse, cell.scan_line) in lattice
            for tally in scan.hierarchy.detection_counts:
                assert tally.denominator == scan.hierarchy.measured_cells
    text = document.dumps(case_doc("perp-equal")[1])
    assert '"total"' not in text


def test_generated_property_cases_carry_no_fixed_expectation() -> None:
    """Generated surveys assert composition invariants with no fixed numbers.

    Failing input: asserting a generated survey yields exactly N detections.
    """
    spikes = ((4, 1), (1, 4), (4, 4), (1, 1))
    for corner in spikes:
        first = synthetic.ScanSpec(
            4, 4, 300, 300, 10, corner[0], corner[1], 310, "absent", "absent", 0, 0
        )
        second = synthetic.ScanSpec(4, 4, 300, 300, 10, 4, 1, 310, "absent", "absent", 0, 0)
        specs = (first, second)
        case = synthetic.SyntheticCase(
            name="generated-only",
            specs=specs,
            relations=(frames.Relation(0, 1, "same"),),
            sources=(synthetic.FIXTURE_SOURCE, synthetic.FIXTURE_SOURCE),
            limitations=(synthetic.FIXTURE_LIMITATION,),
        )
        doc = synthetic.read_synthetic_document(case)
        assert len(doc.frames) == 1
        assert doc.contradictions == []
        synthetic.require_detections_away_from_fixed_points(doc, case)


def test_coverage_states_declaration_gap_untouched() -> None:
    """The arm states it cannot warrant any operator's real declaration.

    Failing input: a coverage line claiming the arm validates real walks.
    """
    statement = synthetic.COVERAGE_STATEMENT
    assert "cannot prove an operator declared a real walk correctly" in statement
    assert "closes no part of that gap" in statement


def test_pitch_fraction_requires_two_indices() -> None:
    """A lone index defines no pitch at all.

    Failing input: a pitch over a single observed index.
    """
    with pytest.raises(ValueError, match="no pitch"):
        synthetic.pitch_fraction(300, 1)


def test_oracle_rejects_unknown_class() -> None:
    """A class outside the cyclic group fails rather than mapping quietly.

    Failing input: class `7` mapping to some turn.
    """
    centre = (Fraction(1, 1), Fraction(1, 1))
    with pytest.raises(ValueError, match="unknown relation class"):
        synthetic.oracle_express(7, centre, centre, 1, 1)


def test_coincident_requires_contract_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A table missing an odd class cannot state a coincidence set.

    Failing input: a table holding only the even classes.
    """
    monkeypatch.setattr(frames, "TURN_TABLE", {0: frames.TURN_TABLE[0], 2: frames.TURN_TABLE[2]})
    with pytest.raises(ValueError, match="no coincidence set"):
        synthetic.coincident_under_both_turns((Fraction(1, 1), Fraction(1, 1)), 1, 1)


def test_require_reports_unread_scan() -> None:
    """A refused synthetic scan reports vacuity instead of passing quietly.

    Failing input: a refused scan counted as an emitted detection.
    """
    case = build_required_cases()["single-empty"]
    doc = reader.read_document([b"not an export"])
    with pytest.raises(synthetic.VacuousCaseError, match="vacuous:"):
        synthetic.require_detections_away_from_fixed_points(doc, case)


def test_read_synthetic_rejects_operator_source() -> None:
    """The synthetic entry accepts the fixture source only.

    Failing input: a case sourcing a declaration from an operator.
    """
    case = build_required_cases()["single-empty"]
    bad = synthetic.SyntheticCase(
        name=case.name,
        specs=case.specs,
        relations=case.relations,
        sources=(synthetic.OPERATOR_SOURCE,),
        limitations=case.limitations,
    )
    with pytest.raises(ValueError, match="fixture source only"):
        synthetic.read_synthetic_document(bad)


def test_read_synthetic_rejects_wrong_limitations() -> None:
    """Limitations name the fixture source exactly, never loosely.

    Failing input: a case carrying no limitation while resting on a fixture.
    """
    case = build_required_cases()["single-empty"]
    bad = synthetic.SyntheticCase(
        name=case.name,
        specs=case.specs,
        relations=case.relations,
        sources=case.sources,
        limitations=(),
    )
    with pytest.raises(ValueError, match="limitations name"):
        synthetic.read_synthetic_document(bad)


def test_hash_bytes_matches_sha256() -> None:
    """Frozen hashes are SHA-256 over the explicit bytes.

    Failing input: a manifest hashing the decoded text instead of the bytes.
    """
    payload = synthetic.exports_of(build_required_cases()["single-empty"])[0]
    assert synthetic.hash_bytes(payload) == hashlib.sha256(payload).hexdigest()

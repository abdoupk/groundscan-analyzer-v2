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


def test_engine_never_assigns_fixture_source() -> None:
    """No engine module names the fixture source, so no file can claim it.

    Failing input: `reader.py` containing the string `fixture-asserted`.
    """
    repo = Path(__file__).resolve().parents[1] / "src" / "groundscan_analyzer"
    engine = ("reader.py", "frames.py", "positions.py", "document.py", "cli.py")
    for filename in engine:
        text = (repo / filename).read_text(encoding="utf-8")
        assert "fixture-asserted" not in text, filename


def test_operator_entry_points_accept_no_fixture_source() -> None:
    """The operator surface takes no source argument at all.

    Failing input: read_document(contents, fixture_source equals fixture-asserted).
    """
    assert "fixture" not in inspect.signature(reader.read_document).parameters
    assert "fixture" not in inspect.signature(main).parameters


def test_engine_never_sets_fixture_limitation() -> None:
    """No engine module names the fixture limitation either.

    Failing input: `document.py` emitting `fixture-asserted-declaration` itself.
    """
    repo = Path(__file__).resolve().parents[1] / "src" / "groundscan_analyzer"
    for filename in ("reader.py", "frames.py", "positions.py", "document.py", "cli.py"):
        text = (repo / filename).read_text(encoding="utf-8")
        assert synthetic.FIXTURE_LIMITATION not in text, filename


def test_limitations_name_fixture_source_by_exact_set_equality() -> None:
    """Each case limitations equal the singleton, never a filtered projection.

    Failing input: a case carrying an extra limitation, or none at all.
    """
    for name, case in build_required_cases().items():
        assert set(synthetic.case_limitations(case)) == {synthetic.FIXTURE_LIMITATION}, name


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
                assert (float(expected[0]), float(expected[1])) == found
    odd_centre = (Fraction(2, 1), Fraction(2, 1))
    assert synthetic.coincident_under_both_turns(odd_centre, 2, 2) is True
    assert synthetic.coincident_under_both_turns(odd_centre, 1, 1) is False


def test_no_detection_contains_cross_scan_cells() -> None:
    """Every detection stays in its own lattice with its own payload identity.

    Failing input: a shared-frame position merging two scans' cells.
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

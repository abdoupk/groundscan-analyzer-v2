"""Vocabulary: provenance closure, axis names, and the retired word.

The positional provenance vocabulary holds exactly four values, the
field vocabulary adds the one promising no unit that is illegal for any
positional role, and the word for measured names no provenance anywhere.
"""

from __future__ import annotations

from pathlib import Path
import re

from groundscan_analyzer import input_contract, reader

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

POSITIONAL = frozenset({
    "device-index",
    "operator-asserted",
    "derived-by-vendor-software-from-operator-assertion",
    "engine-constructed",
})

REPO = Path(__file__).resolve().parents[1]


def test_positional_provenance_is_closed_over_four_values() -> None:
    """Every axis provenance on the record is one of the four, never more."""
    doc = reader.read_document([TWO_BY_TWO.encode()])
    scan = doc.scans[0]
    assert scan.status == "read"
    for detection in scan.hierarchy.detections:
        provenances: set[str] = {
            detection.scan_local_position.along_line.provenance,
            detection.scan_local_position.across_lines.provenance,
        }
        if detection.field_position is not None:
            provenances |= {
                detection.field_position.along_line.provenance,
                detection.field_position.across_lines.provenance,
            }
            for axis in (
                detection.field_position.along_line,
                detection.field_position.across_lines,
            ):
                provenances.add(axis.scale.span_provenance)
                provenances.add(axis.scale.count_provenance)
        assert provenances <= POSITIONAL


def test_field_vocabulary_fifth_value_never_positions() -> None:
    """The unitless field value is registered yet illegal for positions."""
    fifth = "instrument-produced-and-software-transformed"
    assert fifth not in POSITIONAL
    assert fifth in {entry.provenance for entry in input_contract.COLUMNS}
    doc = reader.read_document([TWO_BY_TWO.encode()])
    scan = doc.scans[0]
    assert scan.status == "read"
    text = doc.model_dump_json()
    assert fifth not in text


def test_measured_names_no_provenance() -> None:
    """The retired word appears as no provenance value anywhere shipped."""
    assert "measured" not in {entry.provenance for entry in input_contract.COLUMNS}
    assert "measured" not in set(input_contract.ROLES)
    quoted = re.compile(r"""["']measured["']""")
    hits = [
        f"{path}:{number}"
        for path in sorted((REPO / "src").rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if quoted.search(line)
    ]
    assert hits == []


def test_axes_carry_no_direction() -> None:
    """Along-line and across-lines exhaust the axis names on the record."""
    doc = reader.read_document([TWO_BY_TWO.encode()])
    scan = doc.scans[0]
    assert scan.status == "read"
    for detection in scan.hierarchy.detections:
        names = {
            detection.scan_local_position.along_line.name,
            detection.scan_local_position.across_lines.name,
        }
        assert names == {"along-line", "across-lines"}

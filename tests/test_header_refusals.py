"""Header refusals: every bad name refuses the scan with its own reason.

Seam: the contract document. Each test reads one export and asserts on
the refusal record. Matching is trim plus case-insensitive and nothing
else, so the unit is part of the name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from groundscan_analyzer import reader

if TYPE_CHECKING:
    from groundscan_analyzer import document

BASE = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Meta Data +++
Date / Time: 21.03.2020, 07:51

+++ Soil Type +++
Title: Gravel

+++ Measuring Values +++
{header}
1.0000,1.0000,10.0000
2.0000,1.0000,20.0000
"""


def read(header: str) -> document.ScanRefused | document.ScanRead:
    """Read one export carrying the given measuring header.

    Args:
        header: The measuring header line to test.

    Returns:
        The scan record, read or refused.
    """
    doc = reader.read_document([(BASE.format(header=header)).encode()])
    assert len(doc.scans) == 1
    return doc.scans[0]


def test_column_in_different_unit_is_unknown() -> None:
    """The unit is part of the name: feet is unknown, never convertible."""
    scan = read("Impulse X,Scan Line Y,Impulse X [ft]")
    assert scan.status == "refused"
    assert scan.reason == "unknown-column-name"


def test_unknown_column_name_refuses() -> None:
    """A name outside the registry refuses the scan."""
    scan = read("Impulse X,Scan Line Y,Scan Value,Foo Bar")
    assert scan.status == "refused"
    assert scan.reason == "unknown-column-name"


def test_misspelled_required_column_reads_as_unknown() -> None:
    """Unknown is checked before missing: a misspelling is unknown, not missing."""
    scan = read("Impuls X,Scan Line Y,Scan Value")
    assert scan.status == "refused"
    assert scan.reason == "unknown-column-name"


def test_duplicate_normalised_name_refuses() -> None:
    """A name repeated after normalisation refuses the scan."""
    scan = read("Impulse X,Scan Line Y,Scan Value, impulse x ")
    assert scan.status == "refused"
    assert scan.reason == "duplicate-normalised-name"


def test_missing_required_column_refuses() -> None:
    """A header without the response role refuses the scan."""
    scan = read("Impulse X,Scan Line Y")
    assert scan.status == "refused"
    assert scan.reason == "missing-required-column"


def test_name_matching_ignores_case_and_whitespace() -> None:
    """Trim plus case-insensitive is the whole of the matching rule."""
    export = BASE.format(header="  impulse x , SCAN LINE Y , scan value ")
    doc = reader.read_document([export.encode()])
    assert doc.scans[0].status == "read"


def test_unknown_section_refuses() -> None:
    """A section outside the four registered names refuses the scan."""
    export = BASE.format(header="Impulse X,Scan Line Y,Scan Value")
    export += "+++ Extra +++\nFoo: bar\n"
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unknown-column-name"


def test_repeated_section_refuses() -> None:
    """Each present section appears exactly once: no first-wins reading."""
    export = BASE.format(header="Impulse X,Scan Line Y,Scan Value")
    export += "+++ Meta Data +++\nScan Mode: Zigzag\n"
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "duplicate-normalised-name"


def test_missing_measuring_block_refuses() -> None:
    """The measuring block is required; its absence refuses the scan."""
    export = """+++ Characteristics +++
Field Length: 3.00 m
"""
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "missing-required-column"


def test_content_before_first_section_refuses() -> None:
    """A line outside any section is an unparseable row at its own line."""
    export = "stray line\n" + BASE.format(header="Impulse X,Scan Line Y,Scan Value")
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-row"
    assert [(issue.line, issue.reason) for issue in scan.rows] == [(1, "unparseable-row")]


def test_empty_measuring_block_refuses() -> None:
    """A measuring block with no header refuses the scan."""
    export = BASE.format(header="Impulse X,Scan Line Y,Scan Value")
    export = export.split("+++ Measuring Values +++")[0] + "+++ Measuring Values +++\n"
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "missing-required-column"

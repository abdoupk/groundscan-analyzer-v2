"""One scan export in, one document out: the happy path.

Seam: the contract document. Every test runs the engine over input bytes
and asserts on the document it emits. No test reaches inside the reader.
"""

from __future__ import annotations

from groundscan_analyzer import reader

MINIMAL_EXPORT = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Meta Data +++
Date / Time: 21.03.2020, 07:51

+++ Soil Type +++
Title: Gravel

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
1.0000,1.0000,10.0000
2.0000,1.0000,20.0000
1.0000,2.0000,30.0000
2.0000,2.0000,40.0000
"""


def test_one_named_export_reads_to_a_document() -> None:
    """A minimal export yields one read scan carrying its lattice and responses."""
    doc = reader.read_document([MINIMAL_EXPORT.encode()])
    assert doc.contract_version == 1
    assert doc.decimal_separator == "."
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert scan.position == 0
    assert scan.lattice.impulses == [1, 2]
    assert scan.lattice.scan_lines == [1, 2]
    assert [(c.impulse, c.scan_line, c.response) for c in scan.cells] == [
        (1, 1, 10.0),
        (2, 1, 20.0),
        (1, 2, 30.0),
        (2, 2, 40.0),
    ]


def test_reordered_columns_read_by_name_not_position() -> None:
    """Column order carries no information: a reordered header reads identically."""
    reordered_export = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Meta Data +++
Date / Time: 21.03.2020, 07:51

+++ Soil Type +++
Title: Gravel

+++ Measuring Values +++
Scan Value,Scan Line Y,Impulse X
10.0000,1.0000,1.0000
20.0000,1.0000,2.0000
30.0000,2.0000,1.0000
40.0000,2.0000,2.0000
"""
    first = reader.read_document([MINIMAL_EXPORT.encode()])
    second = reader.read_document([reordered_export.encode()])
    assert first.scans[0].status == "read"
    assert second.scans[0].status == "read"
    assert second.scans[0].cells == first.scans[0].cells

"""Row rules: each failing row carries exactly one reason, in rule order.

Seam: the contract document. A row failing an earlier rule is never
evaluated against a later one: unparseable before index validity before
duplicates, with duplicates counted only among valid rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from groundscan_analyzer import reader

if TYPE_CHECKING:
    from groundscan_analyzer import document

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
"""


def read_rows(rows: str) -> document.ScanRefused | document.ScanRead:
    """Read one export carrying the given measuring rows.

    Args:
        rows: The measuring data lines.

    Returns:
        The scan record, read or refused.
    """
    doc = reader.read_document([(HEAD + rows).encode()])
    assert len(doc.scans) == 1
    return doc.scans[0]


def test_unparseable_row_carries_its_reason() -> None:
    """A non-numeric token with no separator refuses the scan by row."""
    scan = read_rows("1.0000,1.0000,10.0000\nabc,1.0000,20.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "unparseable-row"
    assert [(issue.line, issue.reason) for issue in scan.rows] == [(8, "unparseable-row")]


def test_empty_index_cell_is_an_index_violation() -> None:
    """An empty index cell leaves the coordinate unreconstructable."""
    scan = read_rows("1.0000,1.0000,10.0000\n,1.0000,20.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "invalid-index-value"
    assert [(issue.line, issue.reason) for issue in scan.rows] == [(8, "invalid-index-value")]


def test_non_integral_and_negative_indices_are_violations() -> None:
    """Indices are ordinals: fractional or negative values are refused."""
    scan = read_rows("1.5000,1.0000,10.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "invalid-index-value"
    scan = read_rows("-1.0000,1.0000,10.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "invalid-index-value"


def test_duplicate_coordinate_counts_only_valid_rows() -> None:
    """A repeated lattice position refuses; invalid rows never duplicate."""
    scan = read_rows("1.0000,1.0000,10.0000\n1.0000,1.0000,20.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "duplicate-coordinate"
    assert [(issue.line, issue.reason) for issue in scan.rows] == [(8, "duplicate-coordinate")]


def test_two_invalid_rows_are_never_duplicates() -> None:
    """Two rows with empty indices fail as index violations, not duplicates."""
    scan = read_rows(",1.0000,10.0000\n,1.0000,20.0000\n")
    assert scan.status == "refused"
    assert scan.reason == "invalid-index-value"
    assert [issue.reason for issue in scan.rows] == ["invalid-index-value"] * 2


def test_earlier_row_rule_wins_and_scan_names_the_first() -> None:
    """Each row carries one reason; the scan carries the first row's."""
    scan = read_rows(
        "1.0000,1.0000,10.0000\nabc,1.0000,20.0000\n,2.0000,30.0000\n1.0000,1.0000,40.0000\n"
    )
    assert scan.status == "refused"
    assert scan.reason == "unparseable-row"
    assert [(issue.line, issue.reason) for issue in scan.rows] == [
        (8, "unparseable-row"),
        (9, "invalid-index-value"),
        (10, "duplicate-coordinate"),
    ]


def test_overlong_row_is_unparseable() -> None:
    """A row with more fields than the header is unparseable."""
    scan = read_rows("1.0000,1.0000,10.0000\n1.0000,1.0000,10.0000,extra\n")
    assert scan.status == "refused"
    assert scan.reason == "unparseable-row"

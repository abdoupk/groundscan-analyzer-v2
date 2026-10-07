"""Positions and padding: carried exactly, never re-based or filled.

Seam: the contract document. An empty response at a valid coordinate is
padding; a short line is a recorded discrepancy and is never filled with
zeros; a non-one index minimum is recorded rather than subtracted away.
"""

from __future__ import annotations

import struct
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

METRIC_HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Scan Value
"""


def bits(value: float) -> int:
    """Expose the binary64 bits for exact comparison.

    Args:
        value: The float to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def read(export: str) -> document.ScanRefused | document.ScanRead:
    """Read one export to its scan record.

    Args:
        export: The full export text.

    Returns:
        The scan record, read or refused.
    """
    doc = reader.read_document([export.encode()])
    assert len(doc.scans) == 1
    return doc.scans[0]


def kinds(scan: document.ScanRead) -> list[str]:
    """List the discrepancy kinds on a read scan.

    Args:
        scan: The read scan record.

    Returns:
        The discrepancy kinds in record order.
    """
    assert scan.status == "read"
    return [item.kind for item in scan.discrepancies]


def test_positions_travel_exactly_as_exported() -> None:
    """Indices are carried verbatim, including a non-one minimum."""
    scan = read(HEAD + "5.0000,6.0000,10.0000\n6.0000,6.0000,20.0000\n")
    assert scan.status == "read"
    assert scan.lattice.impulses == [5, 6]
    assert scan.lattice.scan_lines == [6]
    assert [(cell.impulse, cell.scan_line) for cell in scan.cells] == [(5, 6), (6, 6)]
    assert "index-origin" in kinds(scan)


def test_one_based_minimum_carries_no_discrepancy() -> None:
    """The corpus base reads clean: no discrepancy where nothing deviates."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n")
    assert scan.status == "read"
    assert "index-origin" not in kinds(scan)


def test_empty_response_at_valid_coordinate_is_padding() -> None:
    """Padding is a structural null, never a numeric sentinel."""
    scan = read(HEAD + "1.0000,1.0000,\n2.0000,1.0000,20.0000\n")
    assert scan.status == "read"
    assert scan.cells[0].response is None
    assert scan.cells[1].response is not None
    assert bits(scan.cells[1].response) == bits(20.0)


def test_short_line_is_a_discrepancy_never_a_zero_fill() -> None:
    """A short row keeps its cells with the missing response as padding."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n1.0000,2.0000\n")
    assert scan.status == "read"
    assert "short-line" in kinds(scan)
    short = scan.cells[2]
    assert (short.impulse, short.scan_line, short.response) == (1, 2, None)


def test_absent_rows_stay_absent() -> None:
    """Coordinates never written are not listed anywhere."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,2.0000,40.0000\n")
    assert scan.status == "read"
    assert scan.lattice.impulses == [1, 2]
    assert scan.lattice.scan_lines == [1, 2]
    assert len(scan.cells) == 2


def test_non_zero_metric_origin_is_a_discrepancy() -> None:
    """A metric echo not starting at zero is recorded, not repaired."""
    scan = read(
        METRIC_HEAD
        + "1.0000,1.0000,0.5000,0.0000,10.0000\n"
        + "2.0000,1.0000,2.0000,0.0000,20.0000\n"
        + "1.0000,2.0000,0.5000,0.2500,30.0000\n"
        + "2.0000,2.0000,2.0000,0.2500,40.0000\n"
    )
    assert scan.status == "read"
    assert "metric-origin" in kinds(scan)
    assert scan.metric_check.checked is True
    assert scan.metric_check.mismatches != []


def test_empty_metric_cell_is_skipped_not_zeroed() -> None:
    """An empty echo cell takes no part in the check and becomes no zero."""
    scan = read(
        METRIC_HEAD
        + "1.0000,1.0000,,0.0000,10.0000\n"
        + "2.0000,1.0000,3.0000,0.0000,20.0000\n"
        + "1.0000,2.0000,,3.0000,30.0000\n"
        + "2.0000,2.0000,3.0000,3.0000,40.0000\n"
    )
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert scan.metric_check.mismatches == []


def test_single_impulse_checks_only_the_covered_axis() -> None:
    """One observed impulse defines no series, so only the lines compare."""
    scan = read(
        METRIC_HEAD + "1.0000,1.0000,0.0000,0.0000,10.0000\n1.0000,2.0000,0.0000,9.0000,20.0000\n"
    )
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert [mismatch.axis for mismatch in scan.metric_check.mismatches] == ["scan-line"]


def test_scan_line_only_metric_origin() -> None:
    """The origin discrepancy is recorded per axis, not per file."""
    scan = read(
        METRIC_HEAD
        + "1.0000,1.0000,0.0000,0.5000,10.0000\n"
        + "2.0000,1.0000,3.0000,0.5000,20.0000\n"
        + "1.0000,2.0000,0.0000,3.5000,30.0000\n"
        + "2.0000,2.0000,3.0000,3.5000,40.0000\n"
    )
    assert scan.status == "read"
    origins = [item for item in scan.discrepancies if item.kind == "metric-origin"]
    assert len(origins) == 1
    assert "scan-line" in origins[0].detail

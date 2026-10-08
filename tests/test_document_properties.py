"""Document guarantees: versioned, content-addressed, strict and lossless.

Seam: the contract document. The bytes declare their contract version,
carry nothing incidental, serialise deterministically, forbid non-finite
values everywhere, and round-trip losslessly in both directions.
"""

from __future__ import annotations

import socket
import struct

import pytest

from groundscan_analyzer import document, reader

EXPORT = """+++ Characteristics +++
Project Title: Iron Box
Date: 21.03.2020
Time: 07:51
Field Length: 3.00 m
Field Width: 3.00 m
Notes: the user has performed a control scan

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
1.0000,1.0000,131773.6875
2.0000,1.0000,0.1667
1.0000,2.0000,10.123456789
2.0000,2.0000,-0.0000
"""


def bits(value: float) -> int:
    """Expose the binary64 bits for equality beyond ``==``.

    Args:
        value: The float to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def read() -> document.Document:
    """Read the shared export to its document.

    Returns:
        The survey document carrying one read scan.
    """
    return reader.read_document([EXPORT.encode()])


def test_contract_version_declared_first_at_root() -> None:
    """The document opens with its monotonic integer contract version."""
    doc = read()
    assert doc.contract_version == 1
    assert doc.registry_version == 3
    text = document.dumps(doc)
    assert text.index('"contract_version"') < text.index('"scans"')


def test_document_carries_nothing_incidental() -> None:
    """No path, filename, timestamp, hostname or free text travels."""
    text = document.dumps(read())
    assert "Iron Box" not in text
    assert "21.03.2020" not in text
    assert "07:51" not in text
    assert "control scan" not in text
    assert socket.gethostname() not in text
    assert ".csv" not in text


def test_repeated_reads_emit_identical_bytes() -> None:
    """The same input serialises deterministically every time."""
    assert document.dumps(read()) == document.dumps(read())


def test_non_finite_inputs_are_refused_by_row() -> None:
    """Overflow and spelled non-finites never enter the record."""
    base = EXPORT
    for token in ("1e999", "nan", "inf", "-Infinity"):
        export = base.replace("131773.6875", token)
        doc = reader.read_document([export.encode()])
        scan = doc.scans[0]
        assert scan.status == "refused"
        assert scan.reason == "unparseable-row"


def test_non_finite_is_unrepresentable_in_the_model() -> None:
    """Padding is a null; infinities cannot be constructed anywhere."""
    with pytest.raises(ValueError, match="unrepresentable"):
        document.Cell(impulse=1, scan_line=1, response=float("inf"))
    with pytest.raises(ValueError, match="unrepresentable"):
        document.Extent(field_length=float("nan"))


def test_negative_zero_canonicalises_at_parse() -> None:
    """A negative zero reads as positive zero, so no dialect moves it."""
    doc = read()
    scan = doc.scans[0]
    assert scan.status == "read"
    value = scan.cells[3].response
    assert value is not None
    assert bits(value) == bits(0.0)


def test_nothing_rounds_anywhere() -> None:
    """Printed decimals arrive bit-for-bit and survive the round trip."""
    wanted = [131773.6875, 0.1667, 10.123456789, 0.0]
    doc = read()
    scan = doc.scans[0]
    assert scan.status == "read"
    for cell, expect in zip(scan.cells, wanted, strict=True):
        assert cell.response is not None
        assert bits(cell.response) == bits(expect)
    again = document.loads(document.dumps(doc))
    assert again == doc


def test_round_trip_is_lossless_in_both_directions() -> None:
    """Writing then reading, and reading then writing, lose nothing."""
    text = document.dumps(read())
    assert document.dumps(document.loads(text)) == text


def test_strict_reader_rejects_duplicates_and_constants() -> None:
    """Duplicate keys and non-standard constants are refused, not repaired."""
    with pytest.raises(ValueError, match="duplicate key"):
        document.loads('{"contract_version": 1, "contract_version": 1}')
    for constant in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match="non-standard constant"):
            document.loads(f'{{"value": {constant}}}')


def test_strict_reader_rejects_other_versions_and_extras() -> None:
    """Only the current contract version reads, with no extra fields."""
    text = document.dumps(read())
    with pytest.raises(ValueError, match="contract_version"):
        document.loads(text.replace('"contract_version": 1', '"contract_version": 2'))
    with pytest.raises(ValueError, match="extra"):
        document.loads(text.replace('"convention":', '"zzz": 1, "convention":'))

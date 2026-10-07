"""Positions: scan-local always, field positions where declared.

Seam: the contract document. Every test runs the engine over input bytes
and asserts on the document it emits. No test reaches inside the reader.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from pydantic import ValidationError
import pytest

from groundscan_analyzer import document as record
from groundscan_analyzer import reader

if TYPE_CHECKING:
    from groundscan_analyzer import document

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


def read(export: str) -> document.ScanRead:
    """Read one export to its read scan record.

    Args:
        export: The full export text.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    doc = reader.read_document([export.encode()])
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    return scan


def test_scan_local_position_is_always_carried() -> None:
    """The canonical position rides on every detection, indices exact."""
    scan = read(TWO_BY_TWO)
    positions = {
        detection.identity: detection.scan_local_position for detection in scan.hierarchy.detections
    }
    assert positions["positive@15.0#0"].along_line.index == 1
    assert positions["positive@15.0#0"].across_lines.index == 2
    assert positions["negative@-15.0#0"].along_line.index == 1
    assert positions["negative@-15.0#0"].across_lines.index == 1
    for position in positions.values():
        assert position.frame == "scan-local"
        assert position.origin == "operator-marked-starting-point"
        assert position.origin_limitation == "origin-unverifiable-and-unlocatable"
        assert position.along_line.name == "along-line"
        assert position.across_lines.name == "across-lines"
        assert position.along_line.provenance == "device-index"
        assert position.across_lines.provenance == "device-index"


def test_field_position_derives_from_declared_extent() -> None:
    """Coordinates are index-minus-one times span over count-minus-one."""
    scan = read(TWO_BY_TWO)
    positions = {
        detection.identity: detection.field_position for detection in scan.hierarchy.detections
    }
    positive = positions["positive@15.0#0"]
    assert positive is not None
    assert bits(positive.along_line.coordinate) == bits(0.0)
    assert bits(positive.across_lines.coordinate) == bits(3.0)
    negative = positions["negative@-15.0#0"]
    assert negative is not None
    assert bits(negative.along_line.coordinate) == bits(0.0)
    assert bits(negative.across_lines.coordinate) == bits(0.0)
    for position in (positive, negative):
        assert position.frame == "scan-local"
        assert position.origin == "operator-marked-starting-point"
        assert position.origin_limitation == "origin-unverifiable-and-unlocatable"
        for axis in (position.along_line, position.across_lines):
            assert axis.provenance == "engine-constructed"
            assert axis.scale.span_provenance == "operator-asserted"
            assert axis.scale.count_provenance == "device-index"
    assert bits(positive.along_line.scale.span) == bits(3.0)
    assert positive.along_line.scale.count == 2
    assert bits(positive.along_line.scale.quotient) == bits(3.0)


def test_no_extent_means_no_field_position_with_named_reason() -> None:
    """The absence reads as a stated fact, and the detection still ships."""
    lines = [line for line in TWO_BY_TWO.splitlines(keepends=True) if "Field Length" not in line]
    lines = [line for line in lines if "Field Width" not in line]
    scan = read("".join(lines))
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        assert detection.scan_local_position is not None
        assert detection.field_position is None
        assert detection.no_field_position_reason == "requires-declared-extent"
        assert detection.solidity is not None


def test_single_index_axis_withholds_like_inhomogeneous_axes() -> None:
    """One observed impulse defines no pitch, so no homogeneous pair exists."""
    export = HEAD + "1.0000,1.0000,10.0000\n1.0000,2.0000,30.0000\n"
    scan = read(export)
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        assert detection.field_position is None
        assert detection.no_field_position_reason == "requires-homogeneous-axes"


def test_lattice_is_observed_never_inferred() -> None:
    """A 100 m declaration over two impulses still observes two indices."""
    export = TWO_BY_TWO.replace("Field Length: 3.00 m", "Field Length: 100.00 m")
    export = export.replace("Field Width: 3.00 m", "Field Width: 100.00 m")
    scan = read(export)
    assert scan.lattice.impulses == [1, 2]
    assert scan.lattice.scan_lines == [1, 2]
    for detection in scan.hierarchy.detections:
        assert detection.field_position is not None
        assert bits(detection.field_position.along_line.scale.quotient) == bits(100.0)


def test_spacing_is_derived_not_adopted() -> None:
    """The pitch is span over count-minus-one, never density or band."""
    rows = "".join(f"{i}.0000,{j}.0000,{10 * i + j}.0000\n" for j in (1, 2) for i in range(1, 5))
    scan = read(HEAD + rows)
    assert scan.lattice.impulses == [1, 2, 3, 4]
    pitch = 3.0 / (4 - 1)
    density = 3.0 / 4
    assert bits(pitch) != bits(density)
    for detection in scan.hierarchy.detections:
        assert detection.field_position is not None
        quotient = detection.field_position.along_line.scale.quotient
        assert bits(quotient) == bits(pitch)
        assert bits(quotient) != bits(density)


def test_field_area_cites_position_pitches() -> None:
    """Area equals cells times the position scales' own quotients."""
    scan = read(TWO_BY_TWO)
    for detection in scan.hierarchy.detections:
        assert detection.field_position is not None
        assert detection.field_area is not None
        quotient_x = detection.field_position.along_line.scale.quotient
        quotient_y = detection.field_position.across_lines.scale.quotient
        assert bits(detection.field_area) == bits(detection.cell_count * quotient_x * quotient_y)


def test_area_and_position_share_one_absence_reason() -> None:
    """The area cites the position's reason instead of restating it."""
    lines = [line for line in TWO_BY_TWO.splitlines(keepends=True) if "Field Length" not in line]
    lines = [line for line in lines if "Field Width" not in line]
    scan = read("".join(lines))
    for detection in scan.hierarchy.detections:
        assert detection.no_field_position_reason == "requires-declared-extent"
        assert detection.field_area_withheld == detection.no_field_position_reason


def test_line_order_is_preserved_and_its_absence_stated() -> None:
    """Rows travel as exported with no correction, and the gap is named."""
    export = (
        HEAD
        + "2.0000,1.0000,20.0000\n1.0000,1.0000,10.0000\n"
        + "2.0000,2.0000,40.0000\n1.0000,2.0000,30.0000\n"
    )
    scan = read(export)
    assert scan.line_order == "absent-from-export"
    assert [(cell.impulse, cell.scan_line) for cell in scan.cells] == [
        (2, 1),
        (1, 1),
        (2, 2),
        (1, 2),
    ]
    assert read(TWO_BY_TWO).line_order == "absent-from-export"


def test_bare_figures_are_impossible_in_the_type() -> None:
    """A position without its frame fails validation."""
    with pytest.raises(ValidationError):
        record.ScanLocalPosition.model_validate({
            "origin": "operator-marked-starting-point",
            "origin_limitation": "origin-unverifiable-and-unlocatable",
            "along_line": {"name": "along-line", "index": 1},
            "across_lines": {"name": "across-lines", "index": 2},
        })

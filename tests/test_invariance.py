"""Invariance: free text, echo and context never move the record.

Seam: the contract document. Replacing any non-load-bearing free-text
field leaves every output unchanged; substituting the metric echo moves
only its cross-check; context columns are parsed and then discarded.
"""

from __future__ import annotations

import struct

from groundscan_analyzer import document, reader

FULL = """+++ Characteristics +++
Project Title: Iron Box
Date: 21.03.2020
Time: 07:51
Field Length: 3.00 m
Field Width: 3.00 m
Notes: the user has performed a control scan
Operating Mode: 3D Ground Scan
Scan Mode: Zigzag
Impulse Mode: Automatic

+++ Meta Data +++
Date / Time: 21.03.2020, 07:51
Scan Mode: Zigzag
Impulse Mode: Automatic

+++ Soil Type +++
Title: Gravel
Dielectric Constant: 2.60
Relative Permeability: 1.00
Mineralization: 30 %
Humidity: 20 %
Homogeneity: 50 %

+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Depth Z [m],Scan Value,Latitude,Longitude
1.0000,1.0000,0.0000,0.0000,0.1000,10.0000,,
2.0000,1.0000,3.0000,0.0000,0.2000,20.0000,,
1.0000,2.0000,0.0000,3.0000,0.3000,30.0000,,
2.0000,2.0000,3.0000,3.0000,0.4000,40.0000,,
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


def dumps_of(export: str) -> str:
    """Serialise one export's document for byte comparison.

    Args:
        export: The full export text.

    Returns:
        The canonical document text.
    """
    return document.dumps(reader.read_document([export.encode()]))


def test_free_text_substitution_changes_nothing() -> None:
    """Prose is never parsed: arbitrary text leaves the bytes identical."""
    variant = FULL
    for old, new in [
        ("Iron Box", "It is located in a depth of approx. 4 m"),
        ("21.03.2020", "yesterday, more or less"),
        ("07:51", "whenever o'clock"),
        ("the user has performed a control scan", "lorem ipsum dolor sit amet"),
        ("Zigzag", "Widdershins"),
        ("Gravel", "Some other ground"),
    ]:
        variant = variant.replace(old, new)
    assert dumps_of(variant) == dumps_of(FULL)


def test_soil_numeric_substitution_changes_nothing() -> None:
    """Soil numerics are parsed for the dialect, then discarded."""
    variant = FULL.replace("2.60", "2.61").replace("30 %", "31 %")
    assert dumps_of(variant) == dumps_of(FULL)


def test_metric_substitution_moves_only_its_check() -> None:
    """The echo is cross-check only: lattice and cells stand still."""
    variant = FULL.replace("0.0000,0.0000,0.1000", "0.1000,0.0000,0.1000")
    first = read(FULL)
    second = read(variant)
    assert first.status == "read"
    assert second.status == "read"
    assert second.cells == first.cells
    assert second.lattice == first.lattice
    assert second.metric_check != first.metric_check


def test_conformant_echo_carries_tolerance_without_mismatch() -> None:
    """Four printed places compare at half a unit of the last place."""
    scan = read(FULL)
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert scan.metric_check.tolerance is not None
    assert bits(scan.metric_check.tolerance) == bits(0.00005)
    assert scan.metric_check.mismatches == []


def test_depth_substitution_moves_only_depth_intervals() -> None:
    """Depth is load-bearing for intervals alone: structure stands still."""
    variant = FULL.replace("0.1000,10.0000", "9.9000,10.0000")
    first = read(FULL)
    second = read(variant)
    assert first.status == "read"
    assert second.status == "read"
    assert second.cells == first.cells
    assert second.lattice == first.lattice
    assert [d.identity for d in second.hierarchy.detections] == [
        d.identity for d in first.hierarchy.detections
    ]
    assert [d.cells for d in second.hierarchy.detections] == [
        d.cells for d in first.hierarchy.detections
    ]
    first_intervals = [d.depth for d in first.hierarchy.detections]
    second_intervals = [d.depth for d in second.hierarchy.detections]
    assert second_intervals != first_intervals
    assert [d for d in second_intervals if d is not None] != []


def test_discarded_presence_states_are_recorded() -> None:
    """Absent, present-but-empty and present-with-value are three states."""
    empty = read(FULL)
    assert empty.status == "read"
    assert empty.latitude_presence == "present-but-empty"
    valued = read(FULL.replace("10.0000,,", "10.0000,1.5,2.5"))
    assert valued.status == "read"
    assert valued.latitude_presence == "present-with-value"
    assert valued.cells == empty.cells
    dropped = read(FULL.replace(",Latitude,Longitude", "").replace(",,", ""))
    assert dropped.status == "read"
    assert dropped.latitude_presence == "absent"


def test_absent_extent_means_no_check_not_a_contradiction() -> None:
    """Without Characteristics there is no extent at all, and no mismatch."""
    lines = [line for line in FULL.splitlines(keepends=True) if "Field Length" not in line]
    lines = [line for line in lines if "Field Width" not in line]
    scan = read("".join(lines))
    assert scan.status == "read"
    assert scan.extent.field_length is None
    assert scan.extent.field_width is None
    assert scan.metric_check.checked is False


def test_all_zero_echo_against_declared_extent_mismatches() -> None:
    """Zeros against a non-zero declaration disagree and are recorded."""
    variant = FULL
    for token in ("3.0000,0.0000,", "3.0000,3.0000,"):
        variant = variant.replace(token, "0.0000,0.0000,")
    variant = variant.replace("0.0000,3.0000,", "0.0000,0.0000,")
    scan = read(variant)
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert scan.metric_check.mismatches != []


def test_colon_less_lines_are_free_text() -> None:
    """A line without a colon is prose: it changes no byte."""
    variant = FULL.replace(
        "Notes: the user has performed a control scan",
        "Notes: the user has performed a control scan\ncontinued without a colon",
    )
    assert dumps_of(variant) == dumps_of(FULL)


def test_repeated_extent_key_keeps_its_first_value() -> None:
    """A repeated declaration cannot contradict itself silently."""
    variant = FULL.replace("Field Length: 3.00 m", "Field Length: 3.00 m\nField Length: 9.00 m")
    scan = read(variant)
    assert scan.status == "read"
    assert scan.extent.field_length is not None
    assert bits(scan.extent.field_length) == bits(3.0)
    assert scan.metric_check.mismatches == []


def test_missing_characteristics_section_means_no_extent() -> None:
    """Without the extent-carrying section there is nothing to declare."""
    lines = FULL.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if "Characteristics" in line)
    end = next(index for index, line in enumerate(lines) if "Meta Data" in line)
    scan = read("".join(lines[:start] + lines[end:]))
    assert scan.status == "read"
    assert scan.extent.field_length is None
    assert scan.extent.field_width is None
    assert scan.metric_check.checked is False


def test_single_axis_echo_is_checked_alone() -> None:
    """One absent echo never silences the check of the other axis."""
    export = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Value
1.0000,1.0000,0.0000,10.0000
2.0000,1.0000,3.0000,20.0000
1.0000,2.0000,0.0000,30.0000
2.0000,2.0000,3.0000,40.0000
"""
    scan = read(export)
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert scan.metric_check.mismatches == []


def test_missing_width_leaves_only_the_impulse_axis_checked() -> None:
    """An axis without a declared span contributes no disagreements."""
    export = (
        "\n".join(line for line in FULL.splitlines() if not line.startswith("Field Width")) + "\n"
    )
    scan = read(export)
    assert scan.status == "read"
    assert scan.metric_check.checked is True
    assert scan.metric_check.mismatches == []

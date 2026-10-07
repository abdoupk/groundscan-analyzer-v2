"""The assumed reading: stated on the result, refusing what it cannot parse.

Seam: the contract document. The decimal separator is determined nowhere,
so the engine records its assumption and refuses files that do not parse
under it, naming the assumption rather than the row.
"""

from __future__ import annotations

from groundscan_analyzer import reader

DOT_EXPORT = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
1.0000,1.0000,10.0000
2.0000,1.0000,20.0000
"""

EUROPEAN_EXPORT = """+++ Characteristics +++
Field Length: 3,00 m
Field Width: 3,00 m

+++ Measuring Values +++
Impulse X;Scan Line Y;Scan Value
1,0000;1,0000;10,0000
2,0000;1,0000;20,0000
"""


def test_assumption_is_recorded_on_the_result() -> None:
    """The document states which decimal reading its numbers depend on."""
    doc = reader.read_document([DOT_EXPORT.encode()])
    assert doc.decimal_separator == "."
    assert doc.convention == "default-numeric-reading-v1"


def test_other_separator_refuses_naming_the_assumption() -> None:
    """A comma-decimal file is refused for the pairing, not for any row."""
    doc = reader.read_document([EUROPEAN_EXPORT.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"
    assert scan.rows == []


def test_partial_failure_refuses_the_whole_scan() -> None:
    """One comma token refuses the scan even where other tokens parsed."""
    export = DOT_EXPORT.replace("Field Length: 3.00 m", "Field Length: 3,00 m")
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"


def test_soil_decimal_is_inside_the_checked_surface() -> None:
    """A comma in a soil numeric refuses, since the surface includes soil."""
    export = DOT_EXPORT.replace(
        "+++ Measuring Values +++",
        "+++ Soil Type +++\nDielectric Constant: 2,60\n\n+++ Measuring Values +++",
    )
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"


def test_comma_row_under_dot_delimiter_refuses_upstream() -> None:
    """A comma token in a row bypasses the row rules entirely."""
    semi = DOT_EXPORT.replace(
        "Impulse X,Scan Line Y,Scan Value", "Impulse X;Scan Line Y;Scan Value"
    ).replace("1.0000,1.0000,10.0000", "1,0000;1.0000;10.0000")
    doc = reader.read_document([semi.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"
    assert scan.rows == []


def test_unparseable_extent_refuses() -> None:
    """An extent outside the grammar refuses, naming the assumption."""
    export = DOT_EXPORT.replace("Field Length: 3.00 m", "Field Length: about three")
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"


def test_overflowing_extent_refuses() -> None:
    """An extent overflowing binary64 is no number the record can carry."""
    export = DOT_EXPORT.replace("Field Length: 3.00 m", "Field Length: 1e999 m")
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"


def test_word_unit_is_not_a_number() -> None:
    """Only the observed units read: a spelled unit refuses the scan."""
    export = DOT_EXPORT.replace("Field Length: 3.00 m", "Field Length: 3.00 meters")
    doc = reader.read_document([export.encode()])
    scan = doc.scans[0]
    assert scan.status == "refused"
    assert scan.reason == "unparseable-under-assumed-reading"

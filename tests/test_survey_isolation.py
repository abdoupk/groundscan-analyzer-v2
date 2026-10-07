"""Survey isolation: one bad scan refuses only itself; run failures stop all.

Seam: the contract document. Per-scan violations are isolated records;
run-level violations raise instead of emitting a partial document.
"""

from __future__ import annotations

import pytest

from groundscan_analyzer import document, reader

GOOD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
1.0000,1.0000,10.0000
2.0000,1.0000,20.0000
"""

BAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value,Foo Bar
1.0000,1.0000,10.0000,0.0000
"""


def test_one_bad_scan_refuses_only_itself() -> None:
    """A survey records the refusal with its position and reason."""
    doc = reader.read_document([GOOD.encode(), BAD.encode(), GOOD.encode()])
    assert [scan.status for scan in doc.scans] == ["read", "refused", "read"]
    middle = doc.scans[1]
    assert isinstance(middle, document.ScanRefused)
    assert middle.position == 1
    assert middle.reason == "unknown-column-name"


def test_undecodable_input_stops_the_run() -> None:
    """Bytes that decode as nothing stop the run instead of refusing one scan."""
    with pytest.raises(reader.UndecodableInputError):
        reader.read_document([GOOD.encode(), b"\xff\xfe\x00bad"])


def test_delimiter_collision_stops_the_run() -> None:
    """A delimiter colliding with the assumed separator stops the run."""
    colliding = GOOD.replace("Impulse X,Scan Line Y,Scan Value", "Impulse X.Scan Line Y.Scan Value")
    with pytest.raises(reader.DelimiterCollisionError):
        reader.read_document([colliding.encode()])

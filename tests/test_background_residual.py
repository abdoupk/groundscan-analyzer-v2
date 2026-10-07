"""Background and residual: multiscale median pinned as a convention.

Seam: the contract document. Every test runs the engine over input bytes and
asserts on the document it emits. No test reaches inside the reader.
"""

from __future__ import annotations

import struct

import pytest

from groundscan_analyzer import background, document, property_registry, reader

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
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


def residuals_by_key(scan: document.ScanRead) -> dict[tuple[int, int], float | None]:
    """Index a scan's residuals by lattice coordinate.

    Args:
        scan: The read scan record.

    Returns:
        The residual per coordinate, None where padding.
    """
    return {(cell.impulse, cell.scan_line): cell.residual for cell in scan.cells}


def test_residual_is_response_minus_background() -> None:
    """A 2x2 scan centres every window on all four cells, so all agree."""
    scan = read(
        HEAD
        + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
        + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
    )
    by_key = residuals_by_key(scan)
    assert by_key[1, 1] is not None
    assert bits(by_key[1, 1]) == bits(-15.0)
    assert by_key[2, 1] is not None
    assert bits(by_key[2, 1]) == bits(-5.0)
    assert by_key[1, 2] is not None
    assert bits(by_key[1, 2]) == bits(5.0)
    assert by_key[2, 2] is not None
    assert bits(by_key[2, 2]) == bits(15.0)


def test_single_measured_cell_yields_exactly_zero() -> None:
    """A window of support one reproduces its centre, so zero is exact."""
    scan = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert len(scan.cells) == 1
    assert scan.cells[0].response is not None
    assert bits(scan.cells[0].response) == bits(7.5)
    assert scan.cells[0].residual is not None
    assert bits(scan.cells[0].residual) == bits(0.0)


def test_padding_cells_carry_null_residual() -> None:
    """Padding is a structural null for the residual exactly as for response."""
    scan = read(HEAD + "1.0000,1.0000,\n2.0000,1.0000,20.0000\n")
    assert scan.cells[0].response is None
    assert scan.cells[0].residual is None
    assert scan.cells[1].residual is not None


def test_padding_excluded_from_neighbours() -> None:
    """A gap never manufactures a neighbour's value: no zero fill."""
    scan = read(
        HEAD
        + "1.0000,1.0000,10.0000\n2.0000,1.0000,\n1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
    )
    by_key = residuals_by_key(scan)
    assert by_key[2, 1] is None
    assert by_key[1, 1] is not None
    assert bits(by_key[1, 1]) == bits(-20.0)


def test_every_scale_defined_on_small_scans() -> None:
    """No viability rule: 1x1 and 2x2 scans both read with the same ladder."""
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert tuple(single.background_model.windows) == (3, 5, 9)
    tiny = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n")
    assert tuple(tiny.background_model.windows) == (3, 5, 9)
    dumped = tiny.model_dump()
    assert "viable" not in str(dumped)
    assert "scale_set" not in dumped


def test_even_support_halves_before_adding() -> None:
    """Halving first keeps a large pair finite where their sum would overflow."""
    scan = read(HEAD + "1.0000,1.0000,1e308\n2.0000,1.0000,1e308\n")
    for cell in scan.cells:
        assert cell.residual is not None
        assert bits(cell.residual) == bits(0.0)


def test_ladder_combination_is_median_not_mean() -> None:
    """Three scales combine by middle order statistic, not by average."""
    rows = "".join(
        f"{impulse}.0000,1.0000,{value}.0000\n"
        for impulse, value in [
            (1, 0),
            (2, 0),
            (3, 0),
            (4, 0),
            (5, 100),
            (6, 100),
            (7, 100),
            (8, 100),
            (9, 100),
        ]
    )
    scan = read(HEAD + rows)
    by_key = residuals_by_key(scan)
    assert by_key[4, 1] is not None
    assert bits(by_key[4, 1]) == bits(0.0)


def test_convention_recorded_as_processing_metadata() -> None:
    """Windows, support rule and combination travel in scan context."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n")
    model = scan.background_model
    assert model.convention in property_registry.CONVENTIONS
    assert model.convention == background.CONVENTION
    assert tuple(model.windows) == (3, 5, 9)
    assert len(model.windows) == 3
    assert len(model.windows) % 2 == 1
    assert model.support == background.SUPPORT_RULE
    assert model.combination == background.COMBINATION
    assert model.trend == background.TREND


def test_no_trend_term_removed() -> None:
    """The rejection is recorded rather than left as an absence."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n")
    assert scan.background_model.trend == "none"


def test_support_derived_never_stored() -> None:
    """No per-scale support count travels on any record."""
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n")
    dumped = scan.model_dump()
    assert "support_count" not in dumped
    for cell_dump in dumped["cells"]:
        assert "support" not in cell_dump
        assert "background" not in cell_dump


def test_residual_rejects_non_finite() -> None:
    """The no-non-finite promise still holds with the residual field present."""
    with pytest.raises(ValueError, match="unrepresentable"):
        document.Cell(impulse=1, scan_line=1, response=1.0, residual=float("inf"))
    scan = read(HEAD + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n")
    for cell in scan.cells:
        assert cell.residual is None or cell.residual == cell.residual
        assert cell.residual is None or abs(cell.residual) != float("inf")

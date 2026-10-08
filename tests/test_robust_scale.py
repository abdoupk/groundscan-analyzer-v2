"""Robust scale: two median estimates with their agreement verdict.

Seam: the contract document. Every behavioural test runs the engine over
input bytes and asserts on the document it emits. Unit checks on the
pinned helpers cover only error branches with no record equivalent.
"""

from __future__ import annotations

import math
import struct

import pytest

from groundscan_analyzer import background, document, property_registry, quantity_registry, reader
from groundscan_analyzer import scale as scale_module

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

STATUSES = {
    "no-finite-residual-values",
    "constant-field",
    "median-atom-zero-scale",
    "tie-tolerance-saturated",
    "tie",
    "disagreement",
}

VIEW_STATUSES = {"emitted", "not-emitted", "indeterminate"}


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


def test_scale_is_per_scan_from_residuals() -> None:
    """Levels never depend on a detection; the scale reads the field once."""
    scan = read(TWO_BY_TWO)
    residuals = [cell.residual for cell in scan.cells if cell.residual is not None]
    assert len(residuals) == 4
    assert scan.robust_scale.median_atom_denominator == len(residuals)
    assert scan.hierarchy.level_kind == "raw-residual"
    assert scan.scale_normalised_view.status in VIEW_STATUSES


def test_two_estimators_share_one_calibration() -> None:
    """Both factors derive from the same constant, so they cannot drift."""
    assert math.isfinite(scale_module.Z_75)
    assert bits(scale_module.MAD_FACTOR) == bits(1.0 / scale_module.Z_75)
    assert bits(scale_module.IQR_DIVISOR) == bits(2.0 * scale_module.Z_75)
    assert scale_module.CONVENTION == "scale-agreement-v1"
    assert scale_module.CONVENTION in property_registry.CONVENTIONS
    assert scale_module.QUANTILE_CONVENTION in property_registry.CONVENTIONS
    scan = read(TWO_BY_TWO)
    assert scan.robust_scale.convention == scale_module.CONVENTION
    assert scan.robust_scale.quantile_convention == scale_module.QUANTILE_CONVENTION


def test_every_state_records_both_estimates() -> None:
    """No state omits an estimate; a tie stays a tie without fallback."""
    scan = read(TWO_BY_TWO)
    assert scan.robust_scale.sigma_mad is not None
    assert scan.robust_scale.sigma_iqr is not None
    assert scan.robust_scale.status in STATUSES
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert single.robust_scale.sigma_mad is not None
    assert single.robust_scale.sigma_iqr is not None
    assert single.robust_scale.status == "constant-field"
    assert "fallback" not in document.dumps(reader.read_document([TWO_BY_TWO.encode()]))


def test_atom_fraction_is_exact_evidence() -> None:
    """Numerator and denominator travel exact, with no threshold or cause."""
    scan = read(TWO_BY_TWO)
    numerator = scan.robust_scale.median_atom_numerator
    denominator = scan.robust_scale.median_atom_denominator
    assert isinstance(numerator, int)
    assert isinstance(denominator, int)
    assert denominator == 4
    assert numerator == 0
    assert "threshold" not in document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    dumped = scan.robust_scale.model_dump()
    assert "rounded" not in str(dumped)
    assert "processed" not in str(dumped)
    assert "quantised" not in str(dumped)


def test_atom_lemma_with_even_support() -> None:
    """MAD vanishes exactly where the atom outvotes the median, even or odd."""
    assert scale_module.estimate([0.0, 0.0, 0.0, 1.0, 2.0]).status == "median-atom-zero-scale"
    assert scale_module.estimate([0.0, 0.0, 1.0, 2.0]).status != "median-atom-zero-scale"
    even = scale_module.estimate([1.0, 2.0, 3.0, 4.0])
    assert even.median_atom_numerator == 0
    assert even.median_atom_denominator == 4


def test_disagreement_is_pinned_relative() -> None:
    """Dimensionless, in the unit interval, symmetric and Z-invariant."""
    scan = read(TWO_BY_TWO)
    gap = scan.robust_scale.disagreement
    assert gap is not None
    assert 0.0 <= gap <= 1.0
    direct = scale_module.estimate([-15.0, -5.0, 5.0, 15.0]).disagreement
    assert direct is not None
    assert bits(gap) == bits(direct)
    assert bits(scale_module._disagreement_from_raw(0.0, 0.0)) == bits(0.0)
    assert bits(scale_module._disagreement_from_raw(0.0, 5.0)) == bits(1.0)
    assert bits(scale_module._disagreement_from_raw(5.0, 5.0)) == bits(0.5)
    mad = 10.0
    iqr = 15.0
    scaled_gap = abs(mad * scale_module.MAD_FACTOR - iqr / scale_module.IQR_DIVISOR) / max(
        mad * scale_module.MAD_FACTOR, iqr / scale_module.IQR_DIVISOR
    )
    assert scale_module._disagreement_from_raw(mad, iqr) == pytest.approx(scaled_gap)


def test_tolerance_is_derived_not_chosen() -> None:
    """Unit roundoff, parity, modulus and spread ratio, catching ties only."""
    scan = read(TWO_BY_TWO)
    tolerance = scan.robust_scale.tolerance
    assert tolerance is not None
    assert tolerance < 1e-12
    assert tolerance > 0.0
    assert bits(scale_module.UNIT_ROUNDOFF) == bits(2.0**-53)
    assert scale_module.TOLERANCE_SLOPE_COUNT == 11
    assert scale_module._tolerance(5, 1.0) != scale_module._tolerance(6, 1.0)
    assert scale_module._tolerance(6, 1.0) != scale_module._tolerance(8, 1.0)


def test_five_precedence_levels() -> None:
    """No-finite, constant, atom, saturated, then tie or disagreement."""
    empty = read(HEAD + "1.0000,1.0000,\n")
    assert empty.robust_scale.status == "no-finite-residual-values"
    assert empty.robust_scale.sigma_mad is None
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert single.robust_scale.status == "constant-field"
    atom = scale_module.estimate([0.0, 0.0, 0.0, 1.0, 2.0])
    assert atom.status == "median-atom-zero-scale"
    assert atom.sigma_mad is not None
    assert bits(atom.sigma_mad) == bits(0.0)
    two = read(TWO_BY_TWO)
    assert two.robust_scale.status == "disagreement"
    assert two.scale_normalised_view.status == "indeterminate"
    assert two.scale_normalised_view.reason == "scale-not-warranted"


def test_saturated_is_decidable() -> None:
    """Disagreement cannot exceed one, so tolerance past one saturates."""
    assert bits(scale_module.SATURATION_LIMIT) == bits(1.0)
    assert scale_module._tolerance(1000000, 1e18) >= 1.0
    first = scale_module.estimate([0.0, 1.0]).disagreement
    assert first is not None
    assert first <= 1.0
    saturated = scale_module.estimate([1e17, 1e17 + 16.0, 1e17 + 32.0, 1e17 + 48.0])
    assert saturated.status == "tie-tolerance-saturated"
    assert saturated.tolerance is not None
    assert saturated.tolerance >= 1.0
    assert saturated.disagreement is not None
    assert bits(saturated.disagreement) == bits(0.0)
    overflowed = scale_module.estimate([-1e308, -1e308, 1e308, 1e308])
    assert overflowed.status == "tie-tolerance-saturated"
    assert overflowed.sigma_iqr is None


def test_view_withholding_names_reasons() -> None:
    """Zero scale withholds computation; disagreement withholds warrant."""
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert single.scale_normalised_view.status == "not-emitted"
    assert single.scale_normalised_view.reason == "scale-not-positive-finite"
    assert single.scale_normalised_view.levels_positive is None
    two = read(TWO_BY_TWO)
    assert two.scale_normalised_view.status == "indeterminate"
    assert two.scale_normalised_view.reason == "scale-not-warranted"
    assert two.scale_normalised_view.levels_positive is None
    assert str(two.robust_scale.status) not in {
        "scale-not-warranted",
        "scale-not-positive-finite",
    }
    assert str(single.robust_scale.status) not in {
        "scale-not-warranted",
        "scale-not-positive-finite",
    }


def test_agreement_is_never_convergence() -> None:
    """No emitted field claims convergence from agreement."""
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert "convergence" not in text
    assert "convergent" not in text
    scan = read(TWO_BY_TWO)
    assert scan.robust_scale.status in STATUSES
    assert "agreement" not in scan.robust_scale.status or scan.robust_scale.status == "disagreement"


def test_only_view_depends_on_scale() -> None:
    """Hierarchy stays raw; only the view reads the scale."""
    scan = read(TWO_BY_TWO)
    assert scan.hierarchy.level_kind == "raw-residual"
    residuals = {cell.residual for cell in scan.cells if cell.residual is not None}
    assert set(scan.hierarchy.levels_positive) | set(scan.hierarchy.levels_negative) <= residuals
    assert scan.scale_normalised_view.status == "indeterminate"
    assert scan.hierarchy.levels_positive


def test_view_withheld_not_warned() -> None:
    """Absence is the verdict, never a caveat beside a number."""
    two = read(TWO_BY_TWO)
    assert two.scale_normalised_view.levels_positive is None
    assert two.scale_normalised_view.scale is None
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert "warning" not in text.lower()
    assert "caveat" not in text.lower()


def test_thin_sample_is_emitted() -> None:
    """Sufficiency is the consumer judgement; the engine still emits."""
    single = read(HEAD + "1.0000,1.0000,7.5000\n")
    assert single.robust_scale.median_atom_denominator == 1
    assert single.robust_scale.sigma_mad is not None
    assert single.hierarchy.measured_cells == 1


def test_quantile_helpers_reject_bad_input() -> None:
    """Error branches with no record equivalent fail loudly."""
    with pytest.raises(ValueError, match="at least one"):
        scale_module._quantile_sorted([], 0.5)
    with pytest.raises(ValueError, match="unit interval"):
        scale_module._quantile_sorted([1.0], 2.0)
    with pytest.raises(ValueError, match="at least one"):
        scale_module.quartiles([])
    assert scale_module.quartiles([5.0]) == (5.0, 5.0, 5.0)
    assert bits(background.median([1.0, 2.0])) == bits(0.5 * 1.0 + 0.5 * 2.0)


def test_registry_entries_and_bounds() -> None:
    """New quantities travel versioned with ordered bounds."""
    assert quantity_registry.QUANTITY_REGISTRY_VERSION == 4
    by_name = {entry.name: entry for entry in quantity_registry.QUANTITIES}
    for name in (
        "robust-scale",
        "median-atom-fraction",
        "scale-disagreement",
        "scale-tie-tolerance",
        "scale-normalised-level",
    ):
        assert name in by_name
        assert by_name[name].owner == "groundscan_analyzer.scale"
    lower = by_name["median-atom-fraction"].lower
    assert lower is not None
    assert bits(lower) == bits(0.0)
    upper = by_name["median-atom-fraction"].upper
    assert upper is not None
    assert bits(upper) == bits(1.0)
    disagreement_lower = by_name["scale-disagreement"].lower
    assert disagreement_lower is not None
    assert bits(disagreement_lower) == bits(0.0)
    disagreement_upper = by_name["scale-disagreement"].upper
    assert disagreement_upper is not None
    assert bits(disagreement_upper) == bits(1.0)

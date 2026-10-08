"""Mask-invariance and the effective amplitude: the guard decided from the computation.

Seam: the contract document first. Every behavioural test runs the engine
over input bytes plus declared bounds and asserts on the document it emits.
Decision-function checks below cover only what the record cannot reach on
hierarchy-derived levels: a birth cell sits exactly at its threshold, so the
gap is exactly zero and the record reads not-guaranteed with no special
case. The invariant state is reachable in the function for compared levels
no cell coincides with, which is what keeps the four-state shape honest.
"""

from __future__ import annotations

import struct

import pytest

from groundscan_analyzer import background, document, property_registry, reader
from groundscan_analyzer import perturbation as perturbation_module

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

FLAT = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,10.0000\n"
    + "1.0000,2.0000,10.0000\n2.0000,2.0000,10.0000\n"
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


def bound(
    amplitude: float,
    boundedness: perturbation_module.Boundedness = "bounded",
    anchor: perturbation_module.Anchor = "residual",
) -> perturbation_module.Bound:
    """Build one declared bound for the decision function.

    Args:
        amplitude: The declared non-negative amplitude.
        boundedness: Whether the draw is bounded or unbounded.
        anchor: Whether the residual field or the payload was perturbed.

    Returns:
        The bound the guard reads.
    """
    return perturbation_module.Bound(amplitude=amplitude, boundedness=boundedness, anchor=anchor)


def test_lipschitz_constant_is_forced_to_one() -> None:
    """Shift-equivariance floors it and monotonicity ceilings it: no tuning."""
    assert bits(background.LAMBDA) == bits(1.0)
    assert bits(perturbation_module.LAMBDA) == bits(background.LAMBDA)


def test_median_is_shift_equivariant() -> None:
    """The floor of the forced constant, exactly on exact inputs."""
    values = [1.0, 2.0, 9.0, 4.0, 5.0]
    assert bits(background.median([value + 3.0 for value in values])) == bits(
        background.median(values) + 3.0
    )
    assert bits(background.median([value - 7.0 for value in values])) == bits(
        background.median(values) - 7.0
    )


def test_median_is_monotone() -> None:
    """The ceiling of the forced constant: raising an input never lowers it."""
    assert background.median([1.0, 2.0, 9.0]) <= background.median([1.0, 3.0, 9.0])
    assert background.median([1.0, 2.0]) <= background.median([1.0, 8.0])


def test_residual_anchor_reads_the_declared_amplitude() -> None:
    """Under the residual anchor the effective amplitude is the declared one."""
    assert bits(perturbation_module.effective_amplitude(0.25, "residual")) == bits(0.25)
    assert perturbation_module.CONVENTION in property_registry.CONVENTIONS


def test_residual_anchor_never_reads_lambda() -> None:
    """Branch selection, not cancellation: any Lipschitz constant gives it back."""
    assert bits(perturbation_module.effective_amplitude(0.5, "residual", 999.0)) == bits(0.5)


def test_payload_anchor_bound_is_exactly_double() -> None:
    """One plus the forced constant times the declared amplitude: twice, bit for bit."""
    assert bits(perturbation_module.effective_amplitude(0.25, "payload")) == bits(2.0 * 0.25)


def test_no_bound_withholds_with_its_own_reason() -> None:
    """Nothing declared: silence with the recorded-bound reason, never a negative."""
    result = perturbation_module.decide([5.0], [5.0], None)
    assert result.status == "not-emitted"
    assert result.reason == "requires-recorded-perturbation-bound"
    assert result.ordering_invariance == "withheld"
    assert result.magnitude_invariance == "withheld"


def test_unbounded_draw_withholds_outright() -> None:
    """An unbounded draw leaves the guard silent rather than negative."""
    result = perturbation_module.decide([1.0, 2.0], [100.0], bound(0.25, "unbounded"))
    assert result.status == "not-emitted"
    assert result.reason == "requires-bounded-perturbation"
    assert result.ordering_invariance == "withheld"
    assert result.magnitude_invariance == "withheld"


def test_zero_effective_amplitude_withholds_rather_than_guarantees() -> None:
    """At zero every gap clears vacuously: a guarantee about nothing withholds."""
    result = perturbation_module.decide([1.0, 2.0], [100.0], bound(0.0))
    assert result.status == "not-emitted"
    assert result.reason == "requires-bounded-perturbation"
    assert result.ordering_invariance == "withheld"
    assert result.magnitude_invariance == "withheld"


def test_exact_coincidence_reads_not_guaranteed() -> None:
    """A cell exactly at a threshold has gap zero: no special case needed."""
    result = perturbation_module.decide([5.0], [5.0], bound(0.25))
    assert result.status == "not-guaranteed"
    assert result.reason is None
    assert result.ordering_invariance == "not-established"
    assert result.magnitude_invariance == "not-established"


def test_clearance_decides_invariance_by_strict_inequality() -> None:
    """The comparison is strict with the error bound subtracted, nothing else."""
    assert perturbation_module.decide([0.0], [1.0], bound(0.25)).status == "mask-invariant"
    assert perturbation_module.decide([0.0], [1.0], bound(1.0)).status == "not-guaranteed"


def test_invariant_carries_both_corollaries() -> None:
    """A count that cannot change cannot reorder: both hold together or not at all."""
    result = perturbation_module.decide([0.0], [1.0], bound(0.25))
    assert result.status == "mask-invariant"
    assert result.ordering_invariance == "holds"
    assert result.magnitude_invariance == "holds"


def test_nothing_compared_establishes_nothing() -> None:
    """With no cell-threshold pair there is nothing to decide, so no guarantee."""
    assert perturbation_module.decide([], [1.0], bound(0.25)).status == "not-guaranteed"
    assert perturbation_module.decide([0.0], [], bound(0.25)).status == "not-guaranteed"


def test_larger_effective_amplitude_never_adds_invariant_fields() -> None:
    """Monotone in the effective amplitude: raising it only removes guarantees."""
    cells = [0.0]
    thresholds = [0.4]
    first = perturbation_module.decide(cells, thresholds, bound(0.25))
    second = perturbation_module.decide(cells, thresholds, bound(0.5))
    assert first.status == "mask-invariant"
    assert second.status == "not-guaranteed"
    assert perturbation_module.decide(cells, thresholds, bound(1.0)).status == "not-guaranteed"


def read_scan(
    export: str,
    perturbation: document.PerturbationBound | None = None,
    displacement: document.DisplacementBound | None = None,
) -> document.ScanRead:
    """Read one export with declared bounds to its read scan record.

    Args:
        export: The full export text.
        perturbation: The declared field perturbation bound, if any.
        displacement: The declared registration displacement bound, if any.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    doc = reader.read_document(
        [export.encode()],
        perturbation_bounds=[perturbation],
        displacement_bounds=[displacement],
    )
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    return scan


def field_bound(
    amplitude: float,
    boundedness: perturbation_module.Boundedness = "bounded",
    anchor: perturbation_module.Anchor = "residual",
) -> document.PerturbationBound:
    """Declare one field perturbation bound for the record seam.

    Args:
        amplitude: The declared non-negative amplitude.
        boundedness: Whether the draw is bounded or unbounded.
        anchor: Whether the residual field or the payload was perturbed.

    Returns:
        The bound as the record carries it.
    """
    return document.PerturbationBound(amplitude=amplitude, boundedness=boundedness, anchor=anchor)


def test_undeclared_bound_withholds_on_the_record() -> None:
    """Nothing declared: the guard is silent with its own named reason."""
    scan = read_scan(TWO_BY_TWO)
    assert scan.perturbation_bound is None
    assert scan.displacement_bound is None
    assert scan.mask_invariance.status == "not-emitted"
    assert scan.mask_invariance.reason == "requires-recorded-perturbation-bound"
    assert scan.mask_invariance.ordering_invariance == "withheld"
    assert scan.mask_invariance.magnitude_invariance == "withheld"


def test_recorded_residual_bound_decides_not_guaranteed_on_data() -> None:
    """Birth cells sit exactly at thresholds, so data reads not-guaranteed."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25))
    assert scan.perturbation_bound is not None
    assert scan.mask_invariance.status == "not-guaranteed"
    assert scan.mask_invariance.reason is None
    assert scan.mask_invariance.ordering_invariance == "not-established"
    assert scan.mask_invariance.magnitude_invariance == "not-established"


def test_recorded_payload_bound_decides_not_guaranteed_on_data() -> None:
    """Doubling the amplitude moves no verdict where a birth cell sits at a level."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25, anchor="payload"))
    assert scan.mask_invariance.status == "not-guaranteed"
    assert scan.mask_invariance.ordering_invariance == "not-established"


def test_unbounded_draw_withholds_on_the_record() -> None:
    """An unbounded draw is silence on the record, never a negative."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25, "unbounded"))
    assert scan.mask_invariance.status == "not-emitted"
    assert scan.mask_invariance.reason == "requires-bounded-perturbation"


def test_zero_amplitude_withholds_on_the_record() -> None:
    """At zero every gap clears vacuously: the record withholds, never guarantees."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.0))
    assert scan.mask_invariance.status == "not-emitted"
    assert scan.mask_invariance.reason == "requires-bounded-perturbation"
    assert scan.mask_invariance.precondition == "effective-amplitude-positive"
    assert scan.mask_invariance.zero_bound_condition == "effective-amplitude-positive"


def test_flat_field_establishes_nothing() -> None:
    """No compared level, no guarantee: a flat field reads not-guaranteed."""
    scan = read_scan(FLAT, perturbation=field_bound(0.25))
    assert scan.hierarchy.levels_positive == []
    assert scan.hierarchy.levels_negative == []
    assert scan.mask_invariance.status == "not-guaranteed"
    assert scan.mask_invariance.ordering_invariance == "not-established"


def test_displacement_bound_never_substitutes() -> None:
    """Declaring a displacement bound moves no guard byte, and vice versa."""
    displaced = read_scan(
        TWO_BY_TWO, displacement=document.DisplacementBound(amplitude=0.5, boundedness="bounded")
    )
    assert displaced.mask_invariance.status == "not-emitted"
    assert displaced.mask_invariance.reason == "requires-recorded-perturbation-bound"
    assert displaced.displacement_bound is not None
    assert displaced.perturbation_bound is None
    fielded = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25))
    assert fielded.displacement_bound is None
    assert fielded.mask_invariance.status == "not-guaranteed"
    assert displaced.mask_invariance == read_scan(TWO_BY_TWO).mask_invariance


def test_guard_cites_the_bound_it_reads() -> None:
    """The guard carries conventions and verdicts, never the amplitude itself."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25))
    guard = scan.mask_invariance.model_dump(mode="json")
    assert "amplitude" not in guard
    assert guard["anchor_rule"] in property_registry.CONVENTIONS
    assert guard["background_convention"] in property_registry.CONVENTIONS
    assert guard["sufficiency"] == "sufficient-and-not-necessary"
    assert guard["precondition"] == "effective-amplitude-positive"
    assert guard["zero_bound_condition"] == "effective-amplitude-positive"
    assert guard["conservativeness"] == "genuinely-invariant-fields-may-read-not-guaranteed"
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert "unstable" not in text
    assert "instability" not in text


def test_no_protocol_identifier_travels() -> None:
    """The bound owns amplitude, boundedness and anchor: no instrument is named."""
    scan = read_scan(TWO_BY_TWO, perturbation=field_bound(0.25, anchor="payload"))
    assert scan.perturbation_bound is not None
    assert scan.perturbation_bound.anchor == "payload"
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert "protocol" not in text
    assert "instrument" not in text


def test_negative_zero_amplitude_canonicalises() -> None:
    """A negative zero declares nothing negative: the record keeps positive zero."""
    declared = document.PerturbationBound(amplitude=-0.0, boundedness="bounded", anchor="residual")
    assert bits(declared.amplitude) == bits(0.0)
    scan = read_scan(TWO_BY_TWO, perturbation=declared)
    assert scan.mask_invariance.status == "not-emitted"
    assert "-0.0" not in document.dumps(reader.read_document([TWO_BY_TWO.encode()]))


def test_negative_amplitude_is_not_a_bound() -> None:
    """A negative declared amplitude fails intake rather than reaching the guard."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        document.PerturbationBound(amplitude=-1.0, boundedness="bounded", anchor="residual")


def test_misaligned_bounds_name_no_scan() -> None:
    """Bound declarations align with intake: a short list stops rather than shifts."""
    with pytest.raises(ValueError, match="perturbation bounds"):
        reader.read_document([TWO_BY_TWO.encode()], perturbation_bounds=[None, None])
    with pytest.raises(ValueError, match="displacement bounds"):
        reader.read_document(
            [TWO_BY_TWO.encode(), TWO_BY_TWO.encode()],
            displacement_bounds=[None],
        )

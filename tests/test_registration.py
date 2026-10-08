"""Registration evidence with recurrence and separation.

Seam: the contract document first. Every behavioural test runs the engine
over input bytes plus declared displacement bounds and asserts on the
document it emits. Decision-function checks cover only the derived bound
and the shift ordering where the record carries the value rather than the
derivation.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from groundscan_analyzer import document, frames, reader
from groundscan_analyzer import registration as registration_module

if TYPE_CHECKING:
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


def test_exact_tie_tolerance_is_derived_from_accumulation_length() -> None:
    """The bound grows with the accumulation length and is never chosen."""
    assert bits(registration_module.UNIT_ROUNDOFF) == bits(2.0**-53)
    small = registration_module.exact_tie_tolerance(4)
    large = registration_module.exact_tie_tolerance(5000)
    assert 0.0 < small < large
    assert 1e-13 < large < 1e-11
    assert registration_module.exact_tie_tolerance(5000) != registration_module.exact_tie_tolerance(
        5001
    )


def test_tolerance_catches_exact_coincidence_and_nothing_else() -> None:
    """Around 1e-12 for five thousand terms against margins of order 1e-1."""
    bound = registration_module.exact_tie_tolerance(5000)
    assert bound < 1e-11
    assert 0.1 / bound > 1e10
    assert bits(registration_module.exact_tie_tolerance(0)) == bits(0.0)
    assert registration_module.exact_tie_tolerance(10**18) == float("inf")


def test_pearson_is_undefined_where_structurally_undefined() -> None:
    """Fewer than two pairs or an exactly constant side defines nothing."""
    assert registration_module.pearson([1.0], [1.0]) is None
    assert registration_module.pearson([1.0, 1.0], [1.0, 2.0]) is None
    assert bits(registration_module.pearson([1.0, 2.0], [1.0, 2.0]) or 0.0) == bits(1.0)
    assert bits(registration_module.pearson([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) or 0.0) == bits(-1.0)
    assert registration_module.pearson([1e308, -1e308], [1e308, -1e308]) is None
    assert registration_module.pearson([1.0, 2.0], [1.0]) is None


def test_shifts_report_in_deterministic_order_never_ranked() -> None:
    """Report order is the fixed shift order, never sorted by correlation."""
    responses = {(1, 1): 10.0, (2, 1): 20.0, (1, 2): 30.0, (2, 2): 40.0}
    found = registration_module.score_shifts(responses)
    assert [(item.dy, item.dx) for item in found] == list(registration_module.CANDIDATE_SHIFTS)
    assert registration_module.DETERMINISTIC_ORDER_NOTE == (
        "deterministic-order-fixes-report-order-only"
    )


def test_zero_shift_is_identity_without_arithmetic() -> None:
    """Self-comparison is perfect by definition where any cell exists."""
    responses = {(1, 1): 10.0, (2, 1): 20.0, (1, 2): 30.0, (2, 2): 40.0}
    found = {(item.dy, item.dx): item for item in registration_module.score_shifts(responses)}
    assert found[0, 0].correlation is not None
    assert bits(found[0, 0].correlation or 0.0) == bits(1.0)
    assert found[0, 0].overlap == 4
    assert registration_module.score_shifts({})[4].correlation is None


def test_summarise_names_exact_winners_with_no_tolerance() -> None:
    """Two shifts on the same bits are two winners, never a near miss."""
    responses = {(1, 1): 10.0, (2, 1): 20.0, (1, 2): 30.0, (2, 2): 40.0}
    summary = registration_module.summarise(registration_module.score_shifts(responses))
    assert summary is not None
    assert bits(summary.best) == bits(1.0)
    assert summary.second <= 1.0
    assert summary.winners != ()
    assert registration_module.summarise(registration_module.score_shifts({})) is None


def test_perturbation_vector_stays_integral_along_the_chance_axis() -> None:
    """Float amplitudes move integer shifts with no interpolation anywhere."""
    assert registration_module.perturbation_vector(0.25) == (0, 0)
    assert registration_module.perturbation_vector(1.0) == (1, 0)
    assert registration_module.CHANCE_DISPLACEMENT == (1, 0)


def read_scan(
    export: str,
    displacement: document.DisplacementBound | None = None,
) -> document.ScanRead:
    """Read one export with its displacement bound to its read record.

    Args:
        export: The full export text.
        displacement: The declared registration displacement bound, if any.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    doc = reader.read_document([export.encode()], displacement_bounds=[displacement])
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert isinstance(scan, document.ScanRead)
    return scan


def test_four_quantities_travel_separately_with_no_composite() -> None:
    """Margin, correlation, stability and drift are independent, never blended."""
    scan = read_scan(
        TWO_BY_TWO, displacement=document.DisplacementBound(amplitude=0.5, boundedness="bounded")
    )
    registration = scan.registration
    assert registration.margin is not None
    assert registration.correlation is not None
    assert registration.margin_drift is not None
    assert registration.argmax_stable is not None
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    for word in ("composite", "quality", "support-score", "confidence", "readiness"):
        assert word not in text


def test_recurrence_eligibility_is_narrow_and_decidable() -> None:
    """Identical dimensions with a clean relation are eligible; else named."""
    eligible, reason = registration_module.decide_recurrence(
        (2, 2), (2, 2), has_relation=True, contradictory=False, same_frame=True
    )
    assert (eligible, reason) == ("eligible", "missing-comparability-warrant")
    ineligible, dimension_reason = registration_module.decide_recurrence(
        (2, 2), (3, 3), has_relation=True, contradictory=False, same_frame=True
    )
    assert (ineligible, dimension_reason) == ("ineligible", "differing-lattice-dimensions")
    _, relation_reason = registration_module.decide_recurrence(
        (2, 2), (2, 2), has_relation=False, contradictory=False, same_frame=True
    )
    assert relation_reason == "missing-declared-relation"
    _, refused_reason = registration_module.decide_recurrence(
        None, (2, 2), has_relation=False, contradictory=False, same_frame=False
    )
    assert refused_reason == "missing-orientation-path"
    _, tainted_reason = registration_module.decide_recurrence(
        (2, 2), (2, 2), has_relation=True, contradictory=True, same_frame=False
    )
    assert tainted_reason == "contradictory-relation"
    _, unframed_reason = registration_module.decide_recurrence(
        (2, 2), (2, 2), has_relation=True, contradictory=False, same_frame=False
    )
    assert unframed_reason == "missing-orientation-path"


FOUR_BY_FOUR = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,31.0000\n3.0000,1.0000,12.0000\n4.0000,1.0000,44.0000\n"
    + "1.0000,2.0000,25.0000\n2.0000,2.0000,8.0000\n3.0000,2.0000,37.0000\n4.0000,2.0000,19.0000\n"
    + "1.0000,3.0000,14.0000\n2.0000,3.0000,42.0000\n3.0000,3.0000,6.0000\n4.0000,3.0000,28.0000\n"
    + "1.0000,4.0000,33.0000\n2.0000,4.0000,17.0000\n3.0000,4.0000,45.0000\n4.0000,4.0000,11.0000\n"
)


def bound(
    amplitude: float, boundedness: perturbation_module.Boundedness = "bounded"
) -> document.DisplacementBound:
    """Declare one displacement bound for the record seam.

    Args:
        amplitude: The recorded non-negative amplitude.
        boundedness: Whether the draw is bounded or unbounded.

    Returns:
        The bound as the record carries it.
    """
    return document.DisplacementBound(amplitude=amplitude, boundedness=boundedness)


def test_ordering_is_report_order_only_never_a_ranking() -> None:
    """Shifts list in fixed shift order with the winner carried separately."""
    scan = read_scan(FOUR_BY_FOUR, displacement=bound(0.5))
    shifts = scan.registration.shifts
    assert [(item.dy, item.dx) for item in shifts] == list(registration_module.CANDIDATE_SHIFTS)
    defined = [item.correlation for item in shifts if item.correlation is not None]
    assert defined != sorted(defined, reverse=True)
    assert scan.registration.argmax_dy == 0
    assert scan.registration.argmax_dx == 0
    text = document.dumps(reader.read_document([FOUR_BY_FOUR.encode()]))
    for word in ("ranking", "preference", "priority"):
        assert word not in text


def test_non_unique_argmax_names_itself_before_any_bound() -> None:
    """Five exact 1.0 winners on two cells each: indeterminate without a bound."""
    scan = read_scan(TWO_BY_TWO)
    assert scan.registration.status == "indeterminate"
    assert scan.registration.reason == "non-unique-argmax"
    assert scan.registration.margin is not None
    assert bits(scan.registration.margin) == bits(0.0)
    assert scan.registration.correlation is not None
    assert bits(scan.registration.correlation) == bits(1.0)
    assert scan.registration.argmax_dy is None


def test_changing_the_recorded_bound_changes_tied_outcome() -> None:
    """The same near-tie passes under a tight bound and fails under a loose one."""
    near = registration_module.ShiftScore(0, 0, 1.0, 16)
    runner = registration_module.ShiftScore(0, 1, 1.0 - 1e-15, 12)
    summary = registration_module.Summary(1.0, 1.0 - 1e-15, (near,), (near, runner))
    tight = reader._verdict_defined(summary, 1e-15, 8.9e-16, bound(0.5), stable=True)
    loose = reader._verdict_defined(summary, 1e-15, 3.6e-15, bound(0.5), stable=True)
    assert tight == ("emitted", None)
    assert loose == ("indeterminate", "tied-within-recorded-bound")


def test_changing_the_recorded_displacement_changes_the_outcome() -> None:
    """The same well-defined scan withholds without a bound and emits with one."""
    without = read_scan(FOUR_BY_FOUR)
    assert without.registration.status == "not-emitted"
    assert without.registration.reason == "requires-recorded-displacement-bound"
    assert without.registration.margin is not None
    assert without.registration.argmax_stable is None
    assert without.registration.margin_drift is None
    bounded = read_scan(FOUR_BY_FOUR, displacement=bound(0.5))
    assert bounded.registration.status == "emitted"
    assert bounded.registration.reason is None
    assert bounded.registration.argmax_stable is True
    assert bounded.registration.margin_drift is not None
    assert bits(bounded.registration.margin_drift) == bits(0.0)
    unbounded = read_scan(FOUR_BY_FOUR, displacement=bound(0.5, "unbounded"))
    assert unbounded.registration.status == "not-emitted"
    assert unbounded.registration.reason == "requires-bounded-displacement"


def test_unstable_names_itself_on_synthetic_winners() -> None:
    """Perturbed winners differing from original winners read unstable."""
    near = registration_module.ShiftScore(0, 0, 1.0, 16)
    runner = registration_module.ShiftScore(0, 1, 0.5, 12)
    outer = registration_module.ShiftScore(2, 0, 0.9, 8)
    summary = registration_module.Summary(1.0, 0.5, (near,), (near, runner))
    perturbed = registration_module.Summary(1.0, 0.9, (outer,), (near, runner, outer))
    assert reader._stability_of(summary, perturbed) is False
    assert reader._drift_of(summary, perturbed) == abs(0.5 - 0.1)
    verdict = reader._verdict_defined(summary, 0.5, 1e-15, bound(2.0), stable=False)
    assert verdict == ("indeterminate", "unstable-under-recorded-perturbation")


def test_bound_is_never_a_doubt_measure_with_eleven_orders_clear() -> None:
    """Real margins of order 1e-1 stand eleven orders above the bound."""
    scan = read_scan(FOUR_BY_FOUR, displacement=bound(0.5))
    assert scan.registration.margin is not None
    assert scan.registration.exact_tie_tolerance > 0.0
    assert scan.registration.margin / scan.registration.exact_tie_tolerance > 1e10
    text = document.dumps(reader.read_document([FOUR_BY_FOUR.encode()]))
    assert "doubt" not in text
    assert "threshold" not in text


def test_chance_baseline_measures_chance_correspondence() -> None:
    """A fixed one-cell displacement larger than the zero-cell tolerance."""
    scan = read_scan(FOUR_BY_FOUR, displacement=bound(0.5))
    assert (scan.registration.chance_dy, scan.registration.chance_dx) == (1, 0)
    assert scan.registration.chance_correlation is not None
    assert scan.registration.chance_note == (
        "measures-chance-correspondence-not-real-world-behaviour"
    )


def test_separation_stays_provisional_with_no_threshold_anywhere() -> None:
    """Close cases stay indeterminate with the missing repeat data named."""
    scan = read_scan(TWO_BY_TWO, displacement=bound(0.5))
    assert scan.registration.separation_criterion == "provisional"
    assert scan.registration.separation_reason == "missing-independent-repeat-acquisitions"
    assert scan.registration.status == "indeterminate"
    text = document.dumps(reader.read_document([TWO_BY_TWO.encode()]))
    assert "separation_threshold" not in text
    assert "separation-threshold" not in text


def test_scope_travels_on_every_result_with_passing_meaning() -> None:
    """Self-alignment only, well-defined and stable, never physically real."""
    for export in (TWO_BY_TWO, FOUR_BY_FOUR):
        scan = read_scan(export, displacement=bound(0.5))
        assert scan.registration.evidence_scope == "self-alignment-only"
        assert scan.registration.passing_means == "well-defined-and-stable-under-recorded-bound"
        assert scan.registration.physical_disclaimer == "never-physically-real"
        assert scan.registration.repeat_limitation == "no-independent-repeat-acquisitions"
    passing = read_scan(FOUR_BY_FOUR, displacement=bound(0.5))
    assert passing.registration.status == "emitted"
    text = document.dumps(reader.read_document([FOUR_BY_FOUR.encode()]))
    for word in ("validated", "metal", "target", "tunnel", "cavity", "buried"):
        assert word not in text


def test_eligible_recurrence_is_indeterminate_with_no_match_rate() -> None:
    """Two identical lattices with a clean relation name the missing warrant."""
    doc = reader.read_document(
        [TWO_BY_TWO.encode(), TWO_BY_TWO.encode()],
        [frames.Relation(0, 1, "same")],
    )
    assert len(doc.recurrences) == 1
    pair = doc.recurrences[0]
    assert (pair.first, pair.second) == (0, 1)
    assert pair.eligibility == "eligible"
    assert pair.reason == "missing-comparability-warrant"
    assert pair.status == "indeterminate"
    assert pair.correspondence == "exact-index-identity-at-zero-cells"
    assert pair.fragility_reason == "scale-disagreement-makes-recurrence-fragile"
    assert pair.repeat_limitation == "no-independent-repeat-acquisitions"
    text = document.dumps(doc)
    assert "match_rate" not in text
    assert "match-rate" not in text
    assert "scale_fitting" not in text
    assert "comparability_test" not in text
    assert "offset" not in text


def test_differing_dimensions_are_ineligible_leaving_scans_read() -> None:
    """Ineligible rather than refused: both scans keep their read records."""
    doc = reader.read_document([TWO_BY_TWO.encode(), FOUR_BY_FOUR.encode()])
    assert [scan.status for scan in doc.scans] == ["read", "read"]
    assert len(doc.recurrences) == 1
    pair = doc.recurrences[0]
    assert pair.eligibility == "ineligible"
    assert pair.reason == "differing-lattice-dimensions"
    assert pair.status == "not-emitted"


def test_recurrence_carries_no_tunable_tolerance_or_offset() -> None:
    """Correspondence is exact at zero shifts; no tolerance, ratio or offset."""
    doc = reader.read_document(
        [TWO_BY_TWO.encode(), TWO_BY_TWO.encode()],
        [frames.Relation(0, 1, "same")],
    )
    pair = doc.recurrences[0]
    assert set(type(pair).model_fields) == {
        "first",
        "second",
        "eligibility",
        "reason",
        "status",
        "correspondence",
        "fragility_reason",
        "repeat_limitation",
    }

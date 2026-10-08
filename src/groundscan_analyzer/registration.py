"""Registration evidence with recurrence and separation.

Two scans walked across each other give a relation, never a merged grid;
registration evidence reports how well-defined that relation is without
ever aggregating heterogeneous quantities into one number. Margin,
correlation, argmax stability and margin drift travel separately, and no
composite or quality number exists anywhere.

Ordering inside registration computes the argmax and nothing more: shifts
are considered in a fixed deterministic order, and that order fixes the
order results are reported in without ever choosing which shift is
physically correct. Deterministic order is not selection.

Three separate checks each make a result indeterminate, and each names
which one failed: more than one shift sharing the maximal correlation
exactly, shifts tied within the recorded floating-point bound, and an
argmax unstable under the recorded displacement. Each references a
recorded bound rather than a fixed constant, so changing the recorded
bound changes the outcome consistently.

The floating-point bound derives from the scoring computation and its
accumulation length, not from a generic epsilon. It catches exact
coincidence and nothing else, and it is never presented as a doubt
measure. The chance baseline displaces a scan by a fixed vector larger
than the match tolerance and measures chance correspondence rather than
real-world behaviour. No separation threshold exists; the criterion stays
provisional and close cases stay indeterminate. The argmax check covers
self-alignment only, measured by comparing a source against a perturbed
copy of itself, and that scope travels with every result. A passing check
means the shift is well-defined and stable under the recorded bound,
never that the alignment is physically real.

Recurrence reports indeterminate for a permanent reason: its
comparability precondition cannot be established, because an
export-dialog flag transforms the values with no trace in the file. Every
eligible pair reports indeterminate, names the missing warrant, and emits
no match rate. Eligibility is decidable and narrow, differing lattice
dimensions make a pair ineligible rather than refused, and neither scan is
affected. Correspondence is exact index identity at zero shifts, with no
tunable tolerance. No comparability test exists in any form. The pair
survey scale disagreement is recorded as the reason recurrence is fragile,
and the gap in independent repeat data is recorded as a limitation the
results carry.

Legacy scored a composite over resampled grids with threshold ladders
(see, e.g., ``docs/legacy/groundscan/site/registration.py`` and its
``registration_evidence_score`` blending correlation, overlap, margin and
multiscale structure). This engine performs no resampling, blends nothing,
and holds no threshold: integer shifts only, exact arithmetic where
defined, and every comparison against a recorded bound.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Final

__all__ = [
    "CANDIDATE_SHIFTS",
    "CHANCE_DISPLACEMENT",
    "CHANCE_NOTE",
    "CORRESPONDENCE",
    "DETERMINISTIC_ORDER_NOTE",
    "EVIDENCE_SCOPE",
    "FRAGILITY_REASON",
    "MISSING_WARRANT",
    "PASSING_MEANS",
    "PHYSICAL_DISCLAIMER",
    "REPEAT_LIMITATION",
    "SEPARATION_CRITERION",
    "SEPARATION_REASON",
    "UNIT_ROUNDOFF",
    "RecurrenceReason",
    "RegistrationReason",
    "RegistrationStatus",
    "ShiftScore",
    "Summary",
    "decide_recurrence",
    "exact_tie_tolerance",
    "pearson",
    "perturbation_vector",
    "score_shifts",
    "shifted_union",
    "summarise",
]

MIN_PAIRS: Final[int] = 2

MIN_SUMMARY: Final[int] = 2

UNIT_ROUNDOFF: Final[float] = 2.0**-53

CANDIDATE_SHIFTS: Final[tuple[tuple[int, int], ...]] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 0),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

CHANCE_DISPLACEMENT: Final[tuple[int, int]] = (1, 0)

DETERMINISTIC_ORDER_NOTE: Final[str] = "deterministic-order-fixes-report-order-only"

EVIDENCE_SCOPE: Final[str] = "self-alignment-only"

PASSING_MEANS: Final[str] = "well-defined-and-stable-under-recorded-bound"

PHYSICAL_DISCLAIMER: Final[str] = "never-physically-real"

SEPARATION_CRITERION: Final[str] = "provisional"

SEPARATION_REASON: Final[str] = "missing-independent-repeat-acquisitions"

CHANCE_NOTE: Final[str] = "measures-chance-correspondence-not-real-world-behaviour"

CORRESPONDENCE: Final[str] = "exact-index-identity-at-zero-cells"

FRAGILITY_REASON: Final[str] = "scale-disagreement-makes-recurrence-fragile"

REPEAT_LIMITATION: Final[str] = "no-independent-repeat-acquisitions"

MISSING_WARRANT: Final[str] = "missing-comparability-warrant"

RegistrationStatus = Literal["emitted", "indeterminate", "not-emitted"]

RegistrationReason = Literal[
    "non-unique-argmax",
    "tied-within-recorded-bound",
    "unstable-under-recorded-perturbation",
    "requires-recorded-displacement-bound",
    "requires-bounded-displacement",
    "requires-scorable-shifts",
]

RecurrenceReason = Literal[
    "missing-comparability-warrant",
    "differing-lattice-dimensions",
    "missing-declared-relation",
    "contradictory-relation",
    "missing-orientation-path",
]


class ShiftScore(NamedTuple):
    """One shift with its correlation over the overlapping cells."""

    dy: int
    dx: int
    correlation: float | None
    overlap: int


class Summary(NamedTuple):
    """The best and second-best defined correlations with their winners."""

    best: float
    second: float
    winners: tuple[ShiftScore, ...]
    defined: tuple[ShiftScore, ...]


def _is_zero(value: float) -> bool:
    """Report whether a float is exactly zero without an equality test.

    Args:
        value: The finite value to test.

    Returns:
        True for positive or negative zero, False otherwise.
    """
    return not (value > 0.0 or value < 0.0)


def _exact_equal(first: float, second: float) -> bool:
    """Report whether two finite floats are exactly equal.

    Args:
        first: One finite value.
        second: Another finite value.

    Returns:
        True on exact equality, with no tolerance anywhere.
    """
    return not (first > second or first < second)


def exact_tie_tolerance(accumulation_length: int) -> float:
    """Return the floating-point bound for one accumulation length.

    The scoring behind registration accumulates one term per overlapping
    cell, so a sum over ``N`` terms carries a Higham-style error bounded
    by ``N * u * S / (1 - N * u)`` where ``u`` is the unit roundoff and
    ``S`` the summed magnitude. A correlation compares two such sums, a
    numerator and a denominator, hence the factor of two. The bound is a
    function of the computation and its length, never a chosen number.

    Args:
        accumulation_length: The overlapping cell count behind the comparison.

    Returns:
        The dimensionless bound, catching exact coincidence and nothing
        else, and never a doubt measure.
    """
    if accumulation_length <= 0:
        return 0.0
    numerator = 2.0 * float(accumulation_length) * UNIT_ROUNDOFF
    denominator = 1.0 - float(accumulation_length) * UNIT_ROUNDOFF
    if denominator <= 0.0 or not math.isfinite(numerator):
        return math.inf
    return numerator / denominator


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Return the Pearson correlation of two paired samples.

    Single-threaded accumulation through ``math.fsum`` keeps the reduction
    deterministic. The result is undefined where fewer than two pairs
    exist or where either sample is exactly constant, since the
    denominator is exactly zero there. Those are structural facts about
    the input, never a minimum in disguise.

    Args:
        xs: The first sample in deterministic pair order.
        ys: The second sample in the same pair order.

    Returns:
        The correlation in ``[-1, 1]``, or None where undefined.
    """
    if len(xs) != len(ys) or len(xs) < MIN_PAIRS:
        return None
    mean_x = math.fsum(xs) / float(len(xs))
    mean_y = math.fsum(ys) / float(len(ys))
    cross = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = math.fsum((x - mean_x) * (x - mean_x) for x in xs)
    var_y = math.fsum((y - mean_y) * (y - mean_y) for y in ys)
    if _is_zero(var_x) or _is_zero(var_y):
        return None
    value = cross / math.sqrt(var_x * var_y)
    if not math.isfinite(value):
        return None
    return max(-1.0, min(1.0, value))


def _pairs_in_order(
    responses: Mapping[tuple[int, int], float], dy: int, dx: int
) -> tuple[list[float], list[float]]:
    """Collect overlapping pairs for one shift in lattice order.

    Args:
        responses: Measured responses keyed by lattice coordinate.
        dy: The impulse shift.
        dx: The scan-line shift.

    Returns:
        The paired values, both in sorted coordinate order.
    """
    first: list[float] = []
    second: list[float] = []
    for key in sorted(responses):
        impulse, line = key
        other = (impulse + dy, line + dx)
        if other in responses:
            first.append(responses[key])
            second.append(responses[other])
    return first, second


def score_shifts(
    responses: Mapping[tuple[int, int], float],
    shifts: Sequence[tuple[int, int]] = CANDIDATE_SHIFTS,
) -> list[ShiftScore]:
    """Score shifts in the given order, never sorted by correlation.

    The zero shift is identity: comparing a field with itself is perfect
    by definition, recorded as exactly ``1.0`` where at least one cell
    exists, with no arithmetic behind it. Every other shift runs the
    Pearson computation over its overlapping cells, or records None where
    fewer than two overlap or either side is exactly constant.

    Args:
        responses: Measured responses keyed by lattice coordinate.
        shifts: The shifts to consider, in deterministic report order.

    Returns:
        One record per shift, in the input order.
    """
    found: list[ShiftScore] = []
    for dy, dx in shifts:
        first, second = _pairs_in_order(responses, dy, dx)
        if dy == 0 and dx == 0:
            correlation = 1.0 if responses else None
        else:
            correlation = pearson(first, second)
        found.append(ShiftScore(dy, dx, correlation, len(first)))
    return found


def summarise(scores: Sequence[ShiftScore]) -> Summary | None:
    """Reduce defined correlations to their best, second-best and winners.

    Winners share the maximal correlation exactly, with no tolerance
    anywhere: exact equality decides, so a second shift reaching the same
    bits is a second winner rather than a near miss.

    Args:
        scores: Shift records in deterministic report order.

    Returns:
        The summary where at least two shifts define a correlation, else
        None where no margin exists to report.
    """
    defined = tuple(item for item in scores if item.correlation is not None)
    if len(defined) < MIN_SUMMARY:
        return None
    ordered = sorted(
        (item.correlation for item in defined if item.correlation is not None),
        reverse=True,
    )
    best = ordered[0]
    second = ordered[1]
    winners = tuple(
        item
        for item in defined
        if item.correlation is not None and _exact_equal(item.correlation, best)
    )
    return Summary(best, second, winners, defined)


def perturbation_vector(amplitude: float) -> tuple[int, int]:
    """Return the integer position perturbation for one recorded amplitude.

    Candidate positions are integers, so a float amplitude perturbs them
    by its integer truncation along the chance axis: the same axis the
    chance baseline displaces along, so one construction serves both. No
    interpolation ever occurs, since every perturbed shift stays integral.

    Args:
        amplitude: The recorded non-negative displacement amplitude.

    Returns:
        The integer vector perturbing each candidate position.
    """
    return (math.floor(amplitude), 0)


def shifted_union(
    shifts: Sequence[tuple[int, int]], vector: tuple[int, int]
) -> tuple[tuple[int, int], ...]:
    """Return the union of shifts with their perturbed positions.

    Args:
        shifts: The original shifts in deterministic order.
        vector: The integer perturbation vector.

    Returns:
        The deduplicated union in deterministic sorted order.
    """
    moved = {(dy + vector[0], dx + vector[1]) for dy, dx in shifts}
    return tuple(sorted(set(shifts) | moved))


def decide_recurrence(
    first_dims: tuple[int, int] | None,
    second_dims: tuple[int, int] | None,
    *,
    has_relation: bool,
    contradictory: bool,
    same_frame: bool,
) -> tuple[Literal["eligible", "ineligible"], RecurrenceReason]:
    """Decide recurrence eligibility for one pair, narrowly.

    Eligibility needs all three: a declared non-contradictory relation, a
    complete path to the canonical reference where one is required, and
    identical lattice dimensions. Differing dimensions make the pair
    ineligible rather than refused, and neither scan is affected. Refused
    scans carry no dimensions, so a pair touching one is ineligible on
    that ground before any relation is read.

    Args:
        first_dims: The first scan dimensions, or None where not read.
        second_dims: The second scan dimensions, or None where not read.
        has_relation: Whether a declared relation connects the pair.
        contradictory: Whether the pair component holds a contradiction.
        same_frame: Whether both scans share one viable frame.

    Returns:
        The eligibility with the reason naming it.
    """
    reason: RecurrenceReason = "missing-comparability-warrant"
    if first_dims is None or second_dims is None:
        reason = "missing-orientation-path"
    elif first_dims != second_dims:
        reason = "differing-lattice-dimensions"
    elif contradictory:
        reason = "contradictory-relation"
    elif not has_relation:
        reason = "missing-declared-relation"
    elif not same_frame:
        reason = "missing-orientation-path"
    eligibility: Literal["eligible", "ineligible"] = (
        "eligible" if reason == "missing-comparability-warrant" else "ineligible"
    )
    return eligibility, reason

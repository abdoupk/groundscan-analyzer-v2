"""Independent reference for **candidate decomposition / resolution multiplicity** (S01 oracle).

Stage-3 S01 scope: how many top-level hypotheses the pipeline emits for one
response region, and whether the *spatial evidence* justifies that number.

## The question this module is built to answer

The production decomposition stage (``site.separation.separate_fused_candidates``)
splits one response region into ``N`` fragments whenever its seed operator finds
``N`` peaks, and then emits those fragments as **peers** -- indistinguishable, at
the level of the finding list, from ``N`` independently detected responses. This
module exists to answer, independently of that code:

* how many *continuous* local maxima the response field actually has;
* how many the *sampled* field has on a given lattice;
* how many the production seed operator finds on its own field;
* whether the two agree, and when they do not, **which mechanism** explains it.

## Independence: what "independent" is taken to mean here

The oracle never calls ``site.separation_seeds._find_seeds``,
``site.separation.separate_fused_candidates``, or any other production
decomposition routine, and never asks the pipeline what the answer should be.
Every expectation is derived from one of two places:

* the **forward model** -- a closed-form analytic field (:class:`PhysicalScene`
  from :mod:`.synthetic_core.cross_resolution`, which is itself pure algebra),
  so a construction's known structure is available before any detector runs; or
* the **field the forward model defines**, evaluated directly.

One quantity here *is* deliberately a replica of production:
:func:`production_seed_field` reconstructs the field the separation stage
actually searches. That is not an oracle, and it is never used to decide
anything. Its single job is to answer the question in
:func:`topology_separates_artifact_from_multimodality` -- *could any rule
reading production's own field tell a decomposition artifact from genuine
multimodality?* A replica is the right instrument for that and the wrong
instrument for an oracle, so the two are kept in separate functions with
separate names and the replica's docstring says so.

## Six levels, and what may not be inferred

This module is organised around the six-level model (Remediation Design v2
:math:`\\S`2.1) and never collapses two of them:

==============  ==============================================================
level 2         ``anomaly_region_count`` -- connected components of the
                thresholded z-field. A property of threshold and lattice.
level 3         ``response_region_count`` -- candidates grouped by the response
                components they belong to.
level 4         ``candidate_count`` / ``top_level_count`` -- hypotheses.
level 5         ``decomposition_count`` -- subordinate records.
level 6         **not measurable and not claimed.** A physical object requires
                external evidence. :func:`assert_no_object_count_claim` is the
                machine-checkable half of that prohibition.
==============  ==============================================================

A count of level-4 or level-5 records is never a count of buried objects, and
:data:`FORBIDDEN_OBJECT_COUNT_NAMES` exists so a test can prove the module has
not started implying otherwise.

## Calibration status: ``d_res`` is a parameter, not a number

v2 :math:`\\S`4.4 states the promotion rule as a *calibration rule*
(**C-RESOLV**): a level-5 record is promoted to top level iff its separation
exceeds the minimum resolvable separation :math:`d_{res}` for the acquisition.
:math:`d_{res}` is blocked on field or controlled-bench evidence (v2
:math:`\\S`15.1, :math:`\\S`15.3) and **no value is invented here**.
:class:`ResolvableSeparation` carries the parameter with its units, provenance,
geometry context and calibration status, and :data:`UNRESOLVED_SEPARATION` is the
only instance that has ever been constructed by default. Because
:math:`d_{res}` is unset, every policy this module can evaluate is
*nesting-by-default* (:data:`CONSERVATIVE_NEST`), which is exactly what
:math:`\\S`4.4 prescribes before calibration.

Why the pitch is not a substitute: grid pitch is a lower bound on *resolution*,
not on *positional accuracy*. A response much larger than one cell can be
localised far better than a cell, and two responses one cell apart may or may not
be separable depending on contrast. :func:`pitch_is_not_a_resolvability_bound`
pins that statement against a measurement, because it is the specific shortcut
this module exists to refuse.

## Mechanism taxonomy

Every multiplicity difference is classified into exactly one of
:data:`MECHANISMS`. Only :data:`GENUINE_MULTIMODALITY` and
:data:`INTENTIONAL_DECOMPOSITION_POLICY` are treated as legitimate outcomes;
:data:`UNKNOWN` is a real answer, not a failure to be tidied away. The taxonomy
is deliberately finer than "bug / not bug": mechanisms 2-8 are *observations*
about sampling and numerics, and calling any of them a scientific defect
requires evidence this module does not have and does not fabricate.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage

from .synthetic_core.cross_resolution import (
    PhysicalResponse,
    PhysicalScene,
    Resolution,
    continuous_maxima_count,
    isotropic_ladder,
    local_maxima_count,
)

# ---------------------------------------------------------------------------
# Contract guard (K3 / v2 §2.3)
# ---------------------------------------------------------------------------

#: Keys that would invite a consumer to read a level-4 or level-5 count as a
#: level-6 physical-object count. Checked by
#: :func:`assert_no_object_count_claim`.
FORBIDDEN_OBJECT_COUNT_NAMES: frozenset[str] = frozenset({
    "object_count",
    "target_count",
    "physical_objects",
    "physical_object_count",
})

#: Level labels, kept apart so a reader can see the module never merges them.
LEVEL_ACQUISITION = 1
LEVEL_ANOMALY_REGION = 2
LEVEL_RESPONSE_REGION = 3
LEVEL_CANDIDATE_HYPOTHESIS = 4
LEVEL_DECOMPOSITION = 5
LEVEL_PHYSICAL_OBJECT = 6

#: The one statement about level 6 this module is willing to make.
LEVEL_SIX_NOTE = (
    "Level 6 is not measurable from a field alone. A physical object requires "
    "external evidence (excavation, borehole, installation record, independent "
    "survey). No count produced here may be read as one."
)


def assert_no_object_count_claim(payload: dict[str, Any]) -> None:
    """Raise if any key invites a level-4/5 count to be read as level 6.

    The prohibition in v2 :math:`\\S`2.3 is only enforceable by naming, so it is
    checked by naming.
    """
    offenders = sorted(_find_forbidden_keys(payload))
    if offenders:
        raise AssertionError(f"level-6 count claim in payload: {offenders}")


def _find_forbidden_keys(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_OBJECT_COUNT_NAMES:
                found.append(str(key))
            found.extend(_find_forbidden_keys(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found.extend(_find_forbidden_keys(item))
    return found


# ---------------------------------------------------------------------------
# The d_res calibration parameter (v2 §4.4 C-RESOLV)
# ---------------------------------------------------------------------------

#: Calibration statuses, most honest first. ``UNCALIBRATED`` is the only status
#: :data:`UNRESOLVED_SEPARATION` carries.
STATUS_UNCALIBRATED = "uncalibrated"
STATUS_INDETERMINATE = "indeterminate"
STATUS_CALIBRATED = "calibrated"


@dataclass(frozen=True)
class ResolvableSeparation:
    """The minimum resolvable separation ``d_res`` -- a parameter, never a guess.

    Every field here exists because v2 :math:`\\S`4.4 requires the promotion rule
    to be stated *with its provenance*, so that a reader can tell an operating
    assumption apart from a measured constant:

    ``value_m``
        The distance itself, in metres. ``None`` means the parameter has not been
        calibrated, and every consumer must then take the conservative branch.
        This module never supplies a value.
    ``units``
        Always ``"m"``. A length-bearing quantity states its unit (contract K5).
    ``provenance``
        Where a value would come from if it existed. All three defensible forms
        are named in v2 :math:`\\S`4.4 and all three require evidence this
        repository does not have.
    ``geometry_context``
        The geometry the value is valid *for*. A ``d_res`` is a property of a
        line-spacing / contrast / SNR envelope, not of a grid.
    ``status``
        One of :data:`STATUS_UNCALIBRATED`, :data:`STATUS_INDETERMINATE`,
        :data:`STATUS_CALIBRATED`.
    ``meaning``
        Prose definition, carried in the object so a report cannot render the
        number without its meaning.
    """

    value_m: float | None = None
    units: str = "m"
    provenance: str = "uncalibrated: no line-spacing or contrast evidence available"
    geometry_context: str = "none: no operating envelope has been established"
    status: str = STATUS_UNCALIBRATED
    meaning: str = (
        "minimum separation at which two decomposition hypotheses from the same "
        "response region can be told apart reliably; below it they are reported as "
        "competing/unresolved structure rather than as independent top-level findings"
    )

    @property
    def is_calibrated(self) -> bool:
        return self.status == STATUS_CALIBRATED and self.value_m is not None

    @property
    def promotes(self) -> bool:
        """Whether promotion to top level is available at all.

        ``False`` while uncalibrated, which is what makes the conservative
        default (:data:`CONSERVATIVE_NEST`) the *only* available policy rather
        than a preference.
        """
        return self.is_calibrated and self.value_m is not None and self.value_m > 0.0

    def separates(self, distance_m: float) -> bool:
        """Whether *distance_m* clears the threshold.

        Returns ``False`` -- never ``True`` -- while uncalibrated. Under-
        promotion is the conservative direction, and a caller that needs the other
        direction must ask :attr:`promotes` first, so an uncalibrated parameter
        cannot silently pass for a permissive one.
        """
        if not self.promotes:
            return False
        assert self.value_m is not None
        return math.isfinite(distance_m) and distance_m > float(self.value_m)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_m": self.value_m,
            "units": self.units,
            "provenance": self.provenance,
            "geometry_context": self.geometry_context,
            "status": self.status,
            "meaning": self.meaning,
        }


#: The single instance any caller gets by default. ``d_res`` is in the
#: calibration register (v2 :math:`\\S`15.1) and this task does not invent it.
UNRESOLVED_SEPARATION = ResolvableSeparation()


#: The only policy evaluable while :data:`UNRESOLVED_SEPARATION` is uncalibrated.
#: v2 :math:`\\S`4.4 prescribes it verbatim: do not promote, nest.
CONSERVATIVE_NEST = "conservative-nest"


# ---------------------------------------------------------------------------
# Mechanism taxonomy (Phase C)
# ---------------------------------------------------------------------------

GENUINE_MULTIMODALITY = "genuine-multimodality"
RASTER_SAMPLING = "raster-sampling-effect"
NUMERICAL_LOCAL_MAX = "numerical-local-max-effect"
SEED_SPACING = "seed-spacing-effect"
NOISE_FRAGMENTATION = "noise-fragmentation"
ANISOTROPY = "anisotropy-effect"
THRESHOLD_MIN_SIZE = "threshold-min-size-effect"
UNRESOLVED_OVERLAP = "unresolved-overlap"
INTENTIONAL_DECOMPOSITION_POLICY = "intentional-decomposition-policy"
UNKNOWN_MECHANISM = "unknown"

#: Every multiplicity difference is classified into exactly one of these. The
#: first two are legitimate outcomes; the rest are observations, not verdicts.
MECHANISMS: tuple[str, ...] = (
    GENUINE_MULTIMODALITY,
    RASTER_SAMPLING,
    NUMERICAL_LOCAL_MAX,
    SEED_SPACING,
    NOISE_FRAGMENTATION,
    ANISOTROPY,
    THRESHOLD_MIN_SIZE,
    UNRESOLVED_OVERLAP,
    INTENTIONAL_DECOMPOSITION_POLICY,
    UNKNOWN_MECHANISM,
)

#: Mechanisms that count as legitimate, and are therefore not "bugs" even when
#: they change a count. v2 :math:`\\S`4.1 states the same list.
BENIGN_MECHANISMS: frozenset[str] = frozenset({
    GENUINE_MULTIMODALITY,
    INTENTIONAL_DECOMPOSITION_POLICY,
})


@dataclass(frozen=True)
class MultiplicityFinding:
    """One measured multiplicity difference with its mechanism assigned.

    A difference is *described*, never graded. ``mechanism`` says what produced
    it; ``evidence`` carries the measurements that produced that attribution, so
    a reader can disagree with the attribution without re-running anything.
    """

    label: str
    mechanism: str
    continuous_maxima: int
    sampled_maxima: int
    production_seed_maxima: int
    anomaly_region_count: int
    top_level_count: int
    decomposition_count: int
    excess_records: int = 0
    within_response_separations_m: tuple[float, ...] = ()
    notes: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mechanism not in MECHANISMS:
            raise ValueError(f"mechanism {self.mechanism!r} is outside the taxonomy {MECHANISMS}")

    @property
    def is_benign(self) -> bool:
        return self.mechanism in BENIGN_MECHANISMS

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "mechanism": self.mechanism,
            "benign": self.is_benign,
            "continuous_maxima": self.continuous_maxima,
            "sampled_maxima": self.sampled_maxima,
            "production_seed_maxima": self.production_seed_maxima,
            "anomaly_region_count": self.anomaly_region_count,
            "top_level_count": self.top_level_count,
            "decomposition_count": self.decomposition_count,
            "excess_records": self.excess_records,
            "within_response_separations_m": list(self.within_response_separations_m),
            "notes": self.notes,
            "evidence": dict(self.evidence),
        }


def classify_multiplicity(
    *,
    continuous_maxima: int,
    sampled_maxima: int,
    production_seed_maxima: int,
    record_count: int,
    anomaly_region_count: int,
    independent_components: int,
    separation_median_m: float | None,
    pitch_m: float,
    dy_ratio: float = 1.0,
) -> str:
    """Assign a mechanism to one measured multiplicity difference.

    A pure decision procedure over measurements. It is ordered so that the
    strongest available evidence is consulted first, and it returns
    :data:`UNKNOWN_MECHANISM` rather than guessing when nothing discriminates --
    because a mechanism that is wrong is worse than one that is absent.

    ``record_count`` is the number of **emitted** records, deliberately *not* the
    number the shadow role assignment calls top-level. The defect is that one
    response region produced several records the report presents as peers, so the
    multiplicity quantity is the record count; the role opinion is a separate
    measurement about the same data and using it here would let the shadow
    explain away the thing it is supposed to measure.

    The order encodes what the measurements can actually distinguish:

    1. **genuine multimodality** -- the continuous field has at least as many
       maxima as emitted records, so the multiplicity is a statement about the
       field rather than about the sampler. Checked first because it is the only
       mechanism that *justifies* multiplicity, and it must not be masked by a
       coincidental sampling artefact.
    2. **noise fragmentation** -- more anomaly regions than continuous maxima,
       i.e. the extra records are separate components rather than decomposition
       products of one response.
    3. **anisotropy** -- the lattice is anisotropic at this rung.
    4. **seed spacing** -- the seed field's basin count is the only stage that
       disagrees with the continuous field.
    5. **raster/sampling** -- the sampled field already disagrees with the
       continuous one, so the difference precedes the pipeline.
    6. **numerical local max** -- the count is a local-max artefact of a
       near-degenerate peak.
    7. **threshold / min_size** -- the component count moved instead.
    8. **intentional decomposition policy** -- the records are decomposition
       products of a field the sampler did resolve, and no earlier evidence
       discriminates.
    9. **unknown.**

    Note what is *not* a mechanism here: a decomposition that correctly resolves
    a multimodal field and a decomposition that manufactures multiplicity out of
    a unimodal one produce the same measurements at the seed stage. That is the
    reason the taxonomy cannot decide activation on its own, and it is measured
    explicitly by
    :func:`topology_separates_artifact_from_multimodality`.
    """
    del independent_components, separation_median_m
    if continuous_maxima >= record_count and continuous_maxima > 0:
        return GENUINE_MULTIMODALITY
    if anomaly_region_count > continuous_maxima:
        return NOISE_FRAGMENTATION
    if abs(dy_ratio - 1.0) > 1e-9:
        return ANISOTROPY
    if production_seed_maxima > sampled_maxima:
        return SEED_SPACING
    if sampled_maxima > continuous_maxima:
        return RASTER_SAMPLING
    if production_seed_maxima > continuous_maxima:
        return NUMERICAL_LOCAL_MAX
    if anomaly_region_count != continuous_maxima:
        return THRESHOLD_MIN_SIZE
    return INTENTIONAL_DECOMPOSITION_POLICY if record_count > 1 else UNKNOWN_MECHANISM


# ---------------------------------------------------------------------------
# Independent structural probes
# ---------------------------------------------------------------------------


def superlevel_basin_count(
    field: np.ndarray[Any, Any], mask: np.ndarray[Any, Any] | None = None, *, rel: float = 0.90
) -> int:
    """Merge-tree node count: superlevel components of *field* that carry a peak.

    A purely structural probe. It counts the connected components of
    ``{field >= rel * max(field)}`` (8-connected) and keeps those whose own
    maximum reaches the cut. This is the natural "how many basins does this field
    have" question, and it is answered here from the array alone -- no production
    peak finder is consulted.

    ``rel`` is stated rather than hidden because it *is* a threshold, and the
    honest description of what it measures is "basins at the 90 % of peak cut".
    The cross-resolution tests therefore compare *basin counts against each other*
    at a fixed cut, never against an absolute expectation.
    """
    work = np.where(
        mask if mask is not None else np.ones(field.shape, dtype=bool),
        np.asarray(field, dtype=float),
        0.0,
    )
    work = np.where(np.isfinite(work), work, 0.0)
    peak = float(np.max(work)) if work.size else 0.0
    if peak <= 0.0:
        return 0
    cut = rel * peak
    structure = ndimage.generate_binary_structure(2, 2)
    labels, count = ndimage.label(work >= cut, structure=structure)
    if count == 0:
        return 0
    kept = 0
    for label in range(1, count + 1):
        component = labels == label
        if float(np.max(np.where(component, work, -np.inf))) >= cut:
            kept += 1
    return int(kept)


def production_seed_field(
    zscore: np.ndarray[Any, Any], *, support_threshold: float = 0.28
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """**Replica, not oracle.** Rebuild the field the separation stage searches.

    ``site.separation.separate_fused_candidates`` forms
    ``pos_strength = clip(z, 0, inf) * clip(|z| / max|z|, 0, 1)`` and restricts it
    to ``support >= support_threshold`` before running the seed finder. This
    reproduces that construction so the field can be measured directly.

    It is a replica because it shares production's *definition*, which is
    precisely what is under evaluation. It is therefore never used to decide
    anything: :func:`topology_separates_artifact_from_multimodality` is the only
    consumer, and it consumes the replica to test whether a topological rule is
    even available, not to apply one.

    The mask threshold is the single-scan call site's value
    (``single_scan_stages.separate_single_scan_candidates``); the site call site
    uses 0.30. It is a parameter rather than a constant so the two call sites can
    both be measured.
    """
    z = np.nan_to_num(np.asarray(zscore, dtype=float), nan=0.0)
    peak = float(np.max(np.abs(z))) if z.size else 0.0
    support = np.clip(np.abs(z) / peak, 0.0, 1.0) if peak > 0 else np.zeros_like(z)
    positive = np.clip(z, 0.0, None)
    mask = support >= float(support_threshold)
    return positive * support, mask


def topology_separates_artifact_from_multimodality(
    artifact_basins: int, artifact_records: int, multimodal_basins: int, multimodal_records: int
) -> bool:
    """Could a rule reading the production seed field tell the two families apart?

    The decisive question for a threshold-free replacement. If the production
    field's own basin count is the same for a decomposition *artifact* (a
    strictly unimodal field that nonetheless produced several records) as it is
    for a *genuinely multimodal* field, then no rule that reads that field can
    separate them, and any promotion policy must instead threshold on a distance
    -- i.e. it needs ``d_res``.

    Measured: ``artifact_basins == multimodal_basins`` at the rungs where the
    defect appears, so this returns ``False``. That is the reason activation is
    blocked rather than a stylistic preference.
    """
    return artifact_basins != multimodal_basins


def pitch_is_not_a_resolvability_bound(
    *, localisation_error_m: float, pitch_m: float, response_extent_m: float
) -> bool:
    """Measure the claim that pitch bounds resolvability, and refuse it.

    v2 :math:`\\S`4.4 withdraws the v1 rule "closer than one grid pitch means the
    same response", on the grounds that pitch is a lower bound on *resolution*,
    not on *positional accuracy*. This function is the pinned counter-
    measurement of that statement.

    It is ``True`` when the pipeline localises a response to within a small
    fraction of one cell while the response itself spans many cells -- i.e. when
    positional accuracy is demonstrably *finer* than the pitch. A rule keyed on
    pitch would then merge records that are in fact well separated.

    ``response_extent_m`` is used only to reject a degenerate comparison (an
    error larger than the response is not a localisation measurement at all).
    """
    if pitch_m <= 0.0 or response_extent_m <= 0.0:
        raise ValueError("pitch and extent must be positive")
    error = float(localisation_error_m)
    if not math.isfinite(error) or error > float(response_extent_m):
        return False
    return error < 0.25 * float(pitch_m)


# ---------------------------------------------------------------------------
# Level-3 response identity, read from the graph production already records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResponseGroup:
    """One response region and the records the pipeline emitted for it.

    Response identity is read from ``separation_parent_id``, the pointer the
    separation stage *already* writes. That is deliberate: the brief requires the
    existing concepts to be reused rather than a parallel object model invented,
    and it is also the only grouping that does not depend on
    ``response_component_ids`` -- a field the single-scan stage back-fills with
    ``[own id]`` for every candidate, so it reports ``N`` response regions for the
    ``N`` fragments of one region and therefore cannot detect the defect it is
    supposed to measure.

    ``parent_id`` may collide with an emitted record's own id, because the
    separation stage re-numbers fragments after recording the pointer. The
    grouping is therefore by the pointer's *equality*, never by a lookup into the
    emitted list, which is the same reason
    :func:`groundscan.diagnostics.shadow.assign_role` derives its role from the
    record's own fields.
    """

    parent_id: int | None
    record_count: int
    positions_m: tuple[tuple[float, float], ...]
    patterns: tuple[str, ...]

    @property
    def is_multi_record(self) -> bool:
        """Whether one response region produced more than one emitted record."""
        return self.record_count > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_id": self.parent_id,
            "record_count": self.record_count,
            "multi_record": self.is_multi_record,
            "positions_m": [list(p) for p in self.positions_m],
            "patterns": list(self.patterns),
        }


def group_into_responses(records: Sequence[Mapping[str, Any]]) -> tuple[ResponseGroup, ...]:
    """Partition emitted records into level-3 response regions.

    A record that carries a ``separation_parent_id`` belongs to that parent; a
    record that does not is its own response region. Pure function of the
    records' own fields -- no pipeline call, no inference about the field.
    """
    order: list[tuple[str, int | None]] = []
    buckets: dict[tuple[str, int | None], list[Mapping[str, Any]]] = {}
    for record in records:
        status = str(record.get("separation_status", "none") or "none")
        raw = record.get("separation_parent_id")
        own = int(record.get("id", 0) or 0)
        parent = None if raw is None else int(raw)
        decomposed = status.startswith("decomposed") and parent is not None
        key: tuple[str, int | None] = ("parent", parent) if decomposed else ("record", own)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(record)
    groups = []
    for key in order:
        members = buckets[key]
        groups.append(
            ResponseGroup(
                parent_id=key[1] if key[0] == "parent" else None,
                record_count=len(members),
                positions_m=tuple(
                    (float(m.get("x", 0.0)), float(m.get("y", 0.0))) for m in members
                ),
                patterns=tuple(str(m.get("pattern", "")) for m in members),
            )
        )
    return tuple(groups)


def multiplicity_excess(groups: Sequence[ResponseGroup]) -> int:
    """Emitted records beyond one per response region.

    This is the size of the multiplicity claim, measured entirely from the graph
    the pipeline itself records. It is a count of *hypotheses*; per K3 it is not
    a count of objects, and no function here may be read as one.
    """
    return sum(max(0, g.record_count - 1) for g in groups)


# ---------------------------------------------------------------------------
# Perturbation / stability metrics (Phase G)
# ---------------------------------------------------------------------------

#: Declared tolerances. Instability is defined *only* by these, never by
#: intuition. Each is stated in the quantity it applies to.
COUNT_STABILITY_TOLERANCE = 0
LOCATION_TOLERANCE_PITCH_FACTOR = 2.0
ROLE_STABILITY_TOLERANCE = 0
CLASSIFICATION_STABILITY_TOLERANCE = 0
EVIDENCE_TOLERANCE = 0.05

#: The five instability kinds, kept separate because they are different findings.
COUNT_INSTABILITY = "count-instability"
LOCATION_INSTABILITY = "location-instability"
ROLE_INSTABILITY = "role-instability"
CLASSIFICATION_INSTABILITY = "classification-instability"
EVIDENCE_INSTABILITY = "evidence-instability"
STABLE = "stable"

#: Every instability vocabulary, closed so a test can assert nothing new appears.
INSTABILITIES: tuple[str, ...] = (
    COUNT_INSTABILITY,
    LOCATION_INSTABILITY,
    ROLE_INSTABILITY,
    CLASSIFICATION_INSTABILITY,
    EVIDENCE_INSTABILITY,
    STABLE,
)


@dataclass(frozen=True)
class PerturbedRun:
    """One run of a perturbed scene, with the quantities stability compares."""

    label: str
    candidate_count: int
    top_level_count: int
    positions_m: tuple[tuple[float, float], ...]
    roles: tuple[str, ...]
    patterns: tuple[str, ...]
    evidence: tuple[float, ...]
    pitch_m: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "candidate_count": self.candidate_count,
            "top_level_count": self.top_level_count,
            "positions_m": [list(p) for p in self.positions_m],
            "roles": list(self.roles),
            "patterns": list(self.patterns),
            "evidence": [round(float(e), 6) for e in self.evidence],
            "pitch_m": self.pitch_m,
        }


@dataclass(frozen=True)
class StabilityVerdict:
    """The declared-metric verdict for one perturbation family."""

    family: str
    runs: int
    instabilities: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_stable(self) -> bool:
        return not self.instabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "runs": self.runs,
            "instabilities": list(self.instabilities),
            "stable": self.is_stable,
            "metrics": dict(self.metrics),
        }


def compare_runs(family: str, runs: tuple[PerturbedRun, ...]) -> StabilityVerdict:
    """Apply the declared metrics to a perturbation family.

    Each kind is decided by its own rule, and a family can fail several at once
    -- a run family whose *count* holds but whose *label* flips is a
    classification-instability finding, not a stable one, and this function is
    required to say so rather than to report "count stable".

    A *count*-stable, *classification*-unstable family is the important case: it
    is invisible to any characterisation that only watches counts, and it is
    reported as its own finding.
    """
    if len(runs) < 2:
        raise ValueError("a stability comparison needs at least two runs")
    found: set[str] = set()
    counts = {r.candidate_count for r in runs}
    tops = {r.top_level_count for r in runs}
    if len(counts) > 1 + COUNT_STABILITY_TOLERANCE:
        found.add(COUNT_INSTABILITY)
    if len(tops) > 1 + ROLE_STABILITY_TOLERANCE:
        found.add(COUNT_INSTABILITY)

    patterns = {tuple(sorted(r.patterns)) for r in runs}
    if len(patterns) > 1:
        found.add(CLASSIFICATION_INSTABILITY)

    roles = {tuple(sorted(r.roles)) for r in runs}
    if len(roles) > 1:
        found.add(ROLE_INSTABILITY)

    # Location stability uses the coarser pitch in the family as its yardstick:
    # a position is "the same" when it moves by less than the declared number of
    # pitches. The tolerance comes from the lattice, never from the observed move.
    pitch = max(r.pitch_m for r in runs)
    tolerance = LOCATION_TOLERANCE_PITCH_FACTOR * pitch
    reference = runs[0]
    worst = 0.0
    for run in runs[1:]:
        for index in range(min(len(run.positions_m), len(reference.positions_m))):
            ax, ay = run.positions_m[index]
            bx, by = reference.positions_m[index]
            worst = max(worst, math.hypot(ax - bx, ay - by))
    if worst > tolerance:
        found.add(LOCATION_INSTABILITY)

    worst_evidence = 0.0
    for run in runs:
        for index in range(min(len(run.evidence), len(reference.evidence))):
            worst_evidence = max(
                worst_evidence, abs(float(run.evidence[index]) - float(reference.evidence[index]))
            )
    if worst_evidence > EVIDENCE_TOLERANCE:
        found.add(EVIDENCE_INSTABILITY)

    return StabilityVerdict(
        family=family,
        runs=len(runs),
        instabilities=tuple(v for v in INSTABILITIES if v in found),
        metrics={
            "candidate_counts": sorted(counts),
            "top_level_counts": sorted(tops),
            "distinct_label_sets": len(patterns),
            "distinct_role_sets": len(roles),
            "max_position_move_m": round(worst, 6),
            "position_tolerance_m": round(tolerance, 6),
            "max_evidence_move": round(worst_evidence, 6),
            "evidence_tolerance": EVIDENCE_TOLERANCE,
        },
    )


# ---------------------------------------------------------------------------
# Ladders and sweeps
# ---------------------------------------------------------------------------

#: The Phase F ladder. Includes 0.125 m, which the earlier three-rung ladder
#: omitted; the lattice permits it at the extents used here.
RESOLUTION_PITCHES: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125)

#: The aspect ratios swept at fixed ``dx``. Isolates anisotropy from resolution:
#: the physical field and the x pitch are both held constant.
ASPECT_RATIOS: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)


def resolution_ladder(
    width_m: float, height_m: float, pitches: tuple[float, ...] = RESOLUTION_PITCHES
) -> tuple[Resolution, ...]:
    """coarse -> fine isotropic ladder."""
    return isotropic_ladder(width_m, height_m, pitches)


def aspect_ladder(
    width_m: float,
    height_m: float,
    dx: float,
    ratios: tuple[float, ...] = ASPECT_RATIOS,
) -> tuple[Resolution, ...]:
    """Ladder over the lattice *aspect ratio* at a fixed ``dx``."""
    return tuple(
        Resolution(
            name=f"dx{dx:g}_dy{ratio:g}x",
            dx=float(dx),
            width_m=float(width_m),
            height_m=float(height_m),
            dy_ratio=float(ratio),
        )
        for ratio in ratios
    )


def aspect_sweep(
    scene: PhysicalScene, dx: float, ratios: tuple[float, ...] = ASPECT_RATIOS
) -> tuple[tuple[float, int, int], ...]:
    """Sampled vs continuous maxima against lattice aspect ratio, at fixed ``dx``.

    Returns ``(dy/dx, sampled_local_maxima, continuous_maxima)`` per rung.

    The earlier finding on this subject -- "seed count varies with resolution" --
    is reproduced here and is *incomplete*: for a fixed physical field the
    sampled local-maxima count is invariant under **isotropic** re-sampling and
    moves sharply with the lattice's **aspect ratio**. So the governing variable
    is the sampling geometry relative to the field's own aspect ratio, not
    resolution in the isotropic sense.

    The effect needs a *rotated* response. Measured: the rotated Case D field
    gives 1, 3, 1, 3, 3, 3 across the aspect rungs, while the axis-aligned
    6 m x 1 m ridge gives 1 at every rung and Case A gives 1 at every rung. So
    the sweep reports a real dependence, and reporting it as universal would be
    the error this docstring exists to prevent.

    Reported as a measurement; it selects nothing.
    """
    rows: list[tuple[float, int, int]] = []
    for ratio in ratios:
        resolution = Resolution(
            name=f"sweep_dx{dx:g}_dy{ratio:g}x",
            dx=float(dx),
            width_m=scene.width_m,
            height_m=scene.height_m,
            dy_ratio=float(ratio),
        )
        xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
        xx, yy = np.meshgrid(xs, ys, indexing="xy")
        rows.append((
            float(ratio),
            local_maxima_count(scene.value_at(xx, yy)),
            continuous_maxima_count(scene),
        ))
    return tuple(rows)


# ---------------------------------------------------------------------------
# Within-response separation distribution -- the empirical input d_res needs
# ---------------------------------------------------------------------------


def separation_distribution(values: tuple[float, ...]) -> dict[str, Any]:
    """Summarise measured within-response separations without selecting a threshold.

    v2 :math:`\\S`11.4 calls this distribution "the single most valuable artefact
    this whole wave produces: it is the only route to a *measured* ``d_res``
    rather than a guessed one". So the summary reports shape and range and
    **never** proposes a cut point. Adding a recommended value here would be
    exactly the invented calibration v2 :math:`\\S`15.1 forbids.
    """
    finite = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not finite:
        return {
            "count": 0,
            "min_m": None,
            "median_m": None,
            "max_m": None,
            "distinct_values": 0,
            "proposed_d_res_m": None,
            "note": "no within-response separation observed; nothing to calibrate from",
        }
    middle = len(finite) // 2
    median = finite[middle] if len(finite) % 2 else 0.5 * (finite[middle - 1] + finite[middle])
    return {
        "count": len(finite),
        "min_m": round(finite[0], 6),
        "median_m": round(median, 6),
        "max_m": round(finite[-1], 6),
        "distinct_values": len(set(finite)),
        "proposed_d_res_m": None,
        "note": (
            "measured range only; a d_res value requires a line-spacing / contrast "
            "sweep on field or bench data and is not derivable from this distribution"
        ),
    }


# ---------------------------------------------------------------------------
# Controlled case constructions (Cases A-F)
# ---------------------------------------------------------------------------

#: Shared extent so cases differ only in response placement.
EXTENT_M = 24.0

#: Noise sigma. Responses are placed at 10 sigma, matching the design's Case A
#: construction, so the detection regime is the ordinary one rather than the
#: degenerate near-zero-residual regime where the scale estimate is
#: indeterminate (an S03 matter, and one that makes multiplicity meaningless).
NOISE_SIGMA = 1.0
RESPONSE_SIGMAS = 10.0 * NOISE_SIGMA


def unimodal_scene(*, extent_m: float = EXTENT_M) -> PhysicalScene:
    """Case A -- one clearly unimodal response.

    A single isotropic Gaussian. Its superlevel set at any threshold below the
    peak is contractible, so there is exactly one connected response at *every*
    sampling density and one continuous maximum. Any top-level multiplicity the
    pipeline reports for this scene is therefore not a property of the field.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="case_a_unimodal",
        width_m=extent_m,
        height_m=extent_m,
        case_family="unimodal",
        noise_sigma=NOISE_SIGMA,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=centre,
                cy=centre,
                sigma_x=1.2,
                sigma_y=1.2,
                amplitude=RESPONSE_SIGMAS,
            ),
        ),
    )


def separated_scene(*, extent_m: float = EXTENT_M) -> PhysicalScene:
    """Case B -- two clearly separated responses.

    Centres 8 m apart against ``sigma = 1.2 m``, i.e. 6.7 sigma and four times
    the two-Gaussian bifurcation scale. The superlevel set is disconnected in
    the forward model, so two response regions are the *construction's own*
    statement, not a detector's opinion.

    This is the anti-test for over-correction: a policy that nests aggressively
    must leave this at two.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="case_b_separated",
        width_m=extent_m,
        height_m=extent_m,
        case_family="separated",
        noise_sigma=NOISE_SIGMA,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=centre - 4.0,
                cy=centre,
                sigma_x=1.2,
                sigma_y=1.2,
                amplitude=RESPONSE_SIGMAS,
            ),
            PhysicalResponse(
                label="r1",
                cx=centre + 4.0,
                cy=centre,
                sigma_x=1.2,
                sigma_y=1.2,
                amplitude=0.9 * RESPONSE_SIGMAS,
            ),
        ),
    )


def close_unresolved_scene(*, extent_m: float = EXTENT_M) -> PhysicalScene:
    """Case C -- two responses that are unresolved in *principle*.

    Centres 1.5 m apart against ``sigma = 1.2 m``. Since ``1.5 < 2 * 1.2``, the
    superposed field is strictly unimodal: one maximum, and the sub-structure is
    not recoverable at any sampling density. The oracle here is the forward
    model, so "unrecoverable" is a mathematical statement rather than an
    observation.

    Expected interpretation: preserved as unresolved/competing structure, and
    **not** two independent top-level findings. A physical-object count is not
    inferred.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="case_c_close_unresolved",
        width_m=extent_m,
        height_m=extent_m,
        case_family="close_unresolved",
        noise_sigma=NOISE_SIGMA,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=centre - 0.75,
                cy=centre,
                sigma_x=1.2,
                sigma_y=1.2,
                amplitude=RESPONSE_SIGMAS,
            ),
            PhysicalResponse(
                label="r1",
                cx=centre + 0.75,
                cy=centre,
                sigma_x=1.2,
                sigma_y=1.2,
                amplitude=0.9 * RESPONSE_SIGMAS,
            ),
        ),
    )


def multi_seed_scene(*, extent_m: float = EXTENT_M) -> PhysicalScene:
    """Case D -- one elongated, rotated response producing several seeds.

    ``sigma = 2.4 x 0.45 m`` at 30 degrees. The *continuous* field is strictly
    unimodal -- a rotated elliptical Gaussian has exactly one maximum whatever
    the lattice -- but its own aspect ratio against an axis-aligned lattice
    produces a discretisation staircase that carries several discrete local
    maxima.

    This is the case that must never assert a stable seed count. Measured, and
    more precisely than "seeds vary with resolution": for this field the sampled
    local-maxima count is **invariant** under isotropic re-sampling (3, 3, 3, 3 at
    pitches 1.0 / 0.5 / 0.25 / 0.125 m) and moves sharply with the lattice's
    *aspect ratio* (1, 3, 1, 3, 3, 3 at ``dy/dx`` = 0.5 / 1 / 1.5 / 2 / 3 / 4).
    The governing variable is therefore the sampling geometry relative to the
    field's own aspect ratio, not resolution in the isotropic sense.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="case_d_multi_seed",
        width_m=extent_m,
        height_m=extent_m,
        case_family="multi_seed",
        noise_sigma=NOISE_SIGMA,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=centre,
                cy=centre,
                sigma_x=2.4,
                sigma_y=0.45,
                amplitude=RESPONSE_SIGMAS,
                orientation_deg=30.0,
            ),
        ),
    )


def smooth_ridge_scene(*, extent_m: float = 24.0) -> PhysicalScene:
    """The Phase F historical shape: a 6 m x 1 m smooth response.

    ``sigma = 3.0 x 0.5 m``, i.e. a 6 m by 1 m smooth ridge -- the shape the
    earlier resolution experiments were run on. Kept as a distinct construction
    from Case D because it isolates a *different* mechanism.

    Measured: its sampled local-maxima count is **1 at every pitch and every
    aspect ratio** (1, 1, 1, 1, 1, 1 across ``dy/dx`` = 0.5 .. 4). So where the
    production decomposition emits several records for this field, the
    multiplicity is *not* a sampling artefact of the field -- it is manufactured
    downstream, on the support-weighted product the seed operator searches. That
    is a sharper finding than "seeds vary with resolution", and it is why this
    construction is kept separate from Case D.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="ridge_6x1",
        width_m=extent_m,
        height_m=extent_m,
        case_family="smooth-ridge",
        noise_sigma=NOISE_SIGMA,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=centre,
                cy=centre,
                sigma_x=3.0,
                sigma_y=0.5,
                amplitude=RESPONSE_SIGMAS,
            ),
        ),
    )


def multimodal_scene(*, extent_m: float = EXTENT_M) -> PhysicalScene:
    """Case E -- genuinely multimodal, three resolved maxima.

    Three equal Gaussians at 2 / 5 / 8 m with ``sigma = 1.0 m``. All three
    separations exceed the two-Gaussian bifurcation scale ``2 * sigma``, so the
    superposed field genuinely has three local maxima. Unlike Case C, the
    multiplicity here is a property of the field and survives re-sampling in
    principle.

    This is the anti-test against collapsing every multi-lobed response into one
    finding, and it is the case that decides the activation question: any
    candidate replacement must leave three.
    """
    centre = extent_m / 2.0
    return PhysicalScene(
        name="case_e_multimodal",
        width_m=extent_m,
        height_m=extent_m,
        case_family="multimodal",
        noise_sigma=NOISE_SIGMA,
        responses=tuple(
            PhysicalResponse(
                label=f"r{i}",
                cx=centre + offset,
                cy=centre,
                sigma_x=1.0,
                sigma_y=1.0,
                amplitude=RESPONSE_SIGMAS,
            )
            for i, offset in enumerate((-3.0, 0.0, 3.0))
        ),
    )


#: The controlled families, in case order. Case F (resolution sensitivity) is not
#: a construction but a protocol: the same scene run over
#: :data:`RESOLUTION_PITCHES`, measured by :mod:`.decomposition_shadow_report`.
CONTROLLED_CASES = (
    unimodal_scene,
    separated_scene,
    close_unresolved_scene,
    multi_seed_scene,
    smooth_ridge_scene,
    multimodal_scene,
)


def case_by_name(name: str) -> PhysicalScene:
    for builder in CONTROLLED_CASES:
        scene = builder()
        if scene.name == name:
            return scene
    raise KeyError(
        f"unknown controlled case {name!r}; known: {[b().name for b in CONTROLLED_CASES]}"
    )


__all__ = [
    "ASPECT_RATIOS",
    "BENIGN_MECHANISMS",
    "CONSERVATIVE_NEST",
    "CONTROLLED_CASES",
    "EVIDENCE_TOLERANCE",
    "EXTENT_M",
    "FORBIDDEN_OBJECT_COUNT_NAMES",
    "INSTABILITIES",
    "LEVEL_ANOMALY_REGION",
    "LEVEL_CANDIDATE_HYPOTHESIS",
    "LEVEL_DECOMPOSITION",
    "LEVEL_PHYSICAL_OBJECT",
    "LEVEL_RESPONSE_REGION",
    "LEVEL_SIX_NOTE",
    "MECHANISMS",
    "MultiplicityFinding",
    "NOISE_SIGMA",
    "PerturbedRun",
    "RESOLUTION_PITCHES",
    "RESPONSE_SIGMAS",
    "ResponseGroup",
    "ResolvableSeparation",
    "STATUS_CALIBRATED",
    "STATUS_INDETERMINATE",
    "STATUS_UNCALIBRATED",
    "StabilityVerdict",
    "UNRESOLVED_SEPARATION",
    "assert_no_object_count_claim",
    "aspect_ladder",
    "aspect_sweep",
    "case_by_name",
    "classify_multiplicity",
    "close_unresolved_scene",
    "compare_runs",
    "continuous_maxima_count",
    "group_into_responses",
    "local_maxima_count",
    "multi_seed_scene",
    "multimodal_scene",
    "multiplicity_excess",
    "pitch_is_not_a_resolvability_bound",
    "production_seed_field",
    "resolution_ladder",
    "separation_distribution",
    "separated_scene",
    "smooth_ridge_scene",
    "superlevel_basin_count",
    "topology_separates_artifact_from_multimodality",
    "unimodal_scene",
]

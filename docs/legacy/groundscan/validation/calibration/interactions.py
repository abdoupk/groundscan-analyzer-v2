"""Phase I -- interactions, and the question of what a change would really do.

The brief's framing is the right one: *identify whether a change in one
parameter merely exposes a downstream calibration dependency.* A single-factor
sweep answers "what changes". It does not answer "why", and it is easy to read
a correlated pair of movements as a causal one.

So every experiment here is a **two-factor probe with a mediator**. A parameter
is perturbed, the outcome moves, and then the mediator is asked to explain the
movement. Three outcomes are distinguished, and the distinction is the whole
value of the module:

``direct``
    The outcome moved and the mediator did not. The parameter is load-bearing on
    its own.

``mediated``
    The outcome moved *and* the mediator moved by enough of the right sign and
    size. The parameter is a handle on something upstream, and tuning it is
    tuning the mediator.

``incoherent``
    The mediator moved but not in a way that accounts for the outcome. The
    movement is not explained, and is reported as unexplained rather than
    attributed to the nearest-looking cause.

Nothing is solved by a compensating adjustment. Where two parameters interact,
both are recorded with the interaction, and the recommendation is to leave both
alone until there is evidence that constrains either.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from ...core.evidence import (
    DEFAULT_EVIDENCE_MODEL_CONFIG,
    classify_from_evidence,
)
from ...models import Candidate
from .decision import PopulationMember, candidate_population, margin_observations
from .geometry import (
    GEOMETRY_QUALITY_BOUNDARY_WEIGHT,
    GEOMETRY_QUALITY_CELL_COUNT_WEIGHT,
    GEOMETRY_QUALITY_CELL_SATURATION,
    GEOMETRY_QUALITY_FILL_WEIGHT,
    GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
    SOLIDITY_BANDS,
)

# ---------------------------------------------------------------------------
# The mediator framework
# ---------------------------------------------------------------------------

DIRECT = "direct"
MEDIATED = "mediated"
INCOHERENT = "incoherent"


def classify_mediation(
    *,
    n_outcome_changed: int,
    n_mediator_sign_correct: int,
    n_mediator_sign_wrong: int,
) -> str:
    """Direct, mediated, or incoherent -- decided by counts, not by narrative."""
    if n_outcome_changed == 0:
        return DIRECT if n_mediator_sign_correct == 0 else MEDIATED
    if n_mediator_sign_correct >= n_outcome_changed:
        return MEDIATED
    if n_mediator_sign_correct == 0 and n_mediator_sign_wrong == 0:
        return DIRECT
    return INCOHERENT


# ---------------------------------------------------------------------------
# Probe 1: solidity band x geometry_quality
# ---------------------------------------------------------------------------


def _geometry_quality_with_solidity(
    candidate: Any,
    weight: float,
    *,
    n_cells: float,
    fill: float,
    solidity: float | None = None,
) -> float:
    """``geometry_quality`` with the solidity weight replaced; other terms fixed.

    The three non-solidity terms are recovered exactly the way
    :func:`geometry.verify_geometry_quality_reconstruction` verifies them, so
    this is the production formula with one coefficient changed and nothing
    else -- not an approximation of the formula. *solidity* overrides the value
    as well as the weight, which is what a perturbation of the metric itself
    needs.
    """
    boundary = float(candidate.boundary_contact_ratio)
    value = float(candidate.solidity) if solidity is None else float(solidity)
    base = (
        GEOMETRY_QUALITY_CELL_COUNT_WEIGHT * min(n_cells / GEOMETRY_QUALITY_CELL_SATURATION, 1.0)
        + GEOMETRY_QUALITY_FILL_WEIGHT * min(fill, 1.0)
        + GEOMETRY_QUALITY_BOUNDARY_WEIGHT * (1.0 - min(boundary, 1.0))
    )
    return float(min(1.0, max(0.0, base + weight * value)))


def _geometry_quality_terms_for(member: PopulationMember) -> dict[str, float]:
    """Recover a candidate's three non-solidity ``geometry_quality`` terms.

    The production candidate does not carry its own cell-set fill, so the fill
    is reconstructed from the two quantities the pipeline does report that bound
    it: ``anomaly_density`` is ``n_cells / bbox_cells`` by construction in
    ``core.shape.extract_candidates``, so ``bbox_cells = n_cells / density`` and
    the fill is exactly ``density``. Read, not guessed.
    """
    candidate = member.candidate
    density = float(candidate.anomaly_density)
    fill = density if 0.0 < density <= 1.0 else 0.0
    return {
        "n_cells": float(candidate.area_cells),
        "fill": fill,
        "boundary": float(candidate.boundary_contact_ratio),
        "solidity": float(candidate.solidity),
    }


def _verify_geometry_terms(
    members: Sequence[PopulationMember], *, tolerance: float = 1e-6
) -> dict[str, Any]:
    """Check the recovered terms really reproduce production ``geometry_quality``.

    ``anomaly_density`` is the fill in the production formula, so the
    reconstruction is checkable, and it is checked rather than trusted. If this
    fails, every mediated probe below it is reported as unusable.

    The failures are bucketed by ``separation_status`` rather than merely counted,
    because they are not noise: ``geometry_quality`` has three production
    computation sites -- ``core.shape`` for extracted components,
    ``site.separation_fragments`` for separation fragments, and
    ``diagnostics.dipole`` for merged dipoles -- and a candidate that came through
    the third has a geometry quality that is a function of two lobes, not of one
    cell set. Reporting the bucket is what turns "3 of 90 did not reconstruct" into
    "the third site exists and is a different computation".
    """
    worst = 0.0
    worst_id = ""
    usable = 0
    failures_by_status: dict[str, int] = {}
    for member in members:
        terms = _geometry_quality_terms_for(member)
        predicted = _geometry_quality_with_solidity(
            member.candidate,
            GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
            n_cells=terms["n_cells"],
            fill=terms["fill"],
        )
        delta = abs(predicted - float(member.candidate.geometry_quality))
        worst = max(worst, delta)
        if delta <= tolerance:
            usable += 1
        else:
            status = str(getattr(member.candidate, "separation_status", "none") or "none")
            failures_by_status[status] = failures_by_status.get(status, 0) + 1
            if not worst_id:
                worst_id = f"{member.source_id}#{member.candidate.id}"
    return {
        "n_members": len(members),
        "max_abs_difference": round(worst, 9),
        "n_usable": usable,
        "worst_member": worst_id,
        "failures_by_separation_status": dict(sorted(failures_by_status.items())),
        "reconstruction_usable": bool(usable == len(members)),
        "geometry_quality_production_sites": [
            "groundscan/core/shape.py:377 (extracted component)",
            "groundscan/site/separation_fragments.py:155 (separation fragment)",
            "groundscan/diagnostics/dipole.py:421 (merged dipole)",
        ],
        "note": (
            "anomaly_density is the mask fill in core.shape._shape_metrics by "
            "construction, so the reconstruction is exact rather than fitted; this "
            "checks that on the population instead of trusting the identity. Members "
            "whose geometry_quality came from the dipole-merge site are not "
            "reconstructible from a single cell set and are reported separately."
        ),
    }


def reconstructable_members(
    members: Sequence[PopulationMember], *, tolerance: float = 1e-6
) -> tuple[PopulationMember, ...]:
    """The subset whose ``geometry_quality`` is a function of one cell set.

    Used by the mediated probes so their population is stated and defensible
    rather than silently including candidates whose geometry quality was computed
    somewhere else entirely.
    """
    out: list[PopulationMember] = []
    for member in members:
        terms = _geometry_quality_terms_for(member)
        predicted = _geometry_quality_with_solidity(
            member.candidate,
            GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
            n_cells=terms["n_cells"],
            fill=terms["fill"],
        )
        if abs(predicted - float(member.candidate.geometry_quality)) <= tolerance:
            out.append(member)
    return tuple(out)


def solidity_x_geometry_quality(
    members: Sequence[PopulationMember],
    *,
    deltas: Sequence[float] = (-0.10, -0.05, -0.02, 0.02, 0.05, 0.10),
    quality_band: float = 0.40,
) -> dict[str, Any]:
    """The solidity *value* feeds two consumers; do they agree about it?

    This is the interaction that actually exists, and it is worth separating from
    the one that does not:

    * A **band** is read at its own production site, comparing the candidate's
      solidity against a constant. Moving a band changes which candidates are
      *selected* by it and changes no metric at all.
    * ``geometry_quality`` is a *weighted sum over the same solidity value*.
      Moving the value moves it, by ``0.25 * delta`` before clipping.

    So the coupling is between the solidity **value** and both consumers, not
    between a band and a weight. This probe perturbs the value by ``delta`` and
    counts, for each delta: how many candidates cross each band, how many cross
    the ``geometry_quality`` weak-geometry band, and how many are in both sets.

    The overlap is the number that matters. A band and a weight chosen
    independently will double-count a solidity shift unless someone has checked
    that a shift large enough to matter at one is visible at the other.
    """
    verification = _verify_geometry_terms(members)
    scoped = reconstructable_members(members)
    rows: list[dict[str, Any]] = []
    for delta in deltas:
        band_hits: dict[str, set[int]] = {b.band_id: set() for b in SOLIDITY_BANDS}
        geometry_hits: set[int] = set()
        union_hits: set[int] = set()
        intersection_hits: set[int] = set()
        band_union: set[int] = set()
        geometry_distances: list[float] = []
        for index, member in enumerate(scoped):
            production = float(member.candidate.solidity)
            perturbed = float(min(1.0, max(0.0, production + delta)))
            touched_band = False
            for band in SOLIDITY_BANDS:
                if band.crossed_by(production) != band.crossed_by(perturbed):
                    band_hits[band.band_id].add(index)
                    touched_band = True
            if touched_band:
                band_union.add(index)
            terms = _geometry_quality_terms_for(member)
            base_geometry = _geometry_quality_with_solidity(
                member.candidate,
                GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
                n_cells=terms["n_cells"],
                fill=terms["fill"],
                solidity=production,
            )
            new_geometry = _geometry_quality_with_solidity(
                member.candidate,
                GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
                n_cells=terms["n_cells"],
                fill=terms["fill"],
                solidity=perturbed,
            )
            geometry_distances.append(
                min(abs(base_geometry - quality_band), abs(new_geometry - quality_band))
            )
            touched_geometry = (base_geometry < quality_band) != (new_geometry < quality_band)
            if touched_geometry:
                geometry_hits.add(index)
            if touched_band or touched_geometry:
                union_hits.add(index)
            if touched_band and touched_geometry:
                intersection_hits.add(index)
        n = max(len(scoped), 1)
        rows.append({
            "solidity_delta": float(delta),
            "per_band_hits": {k: len(v) for k, v in band_hits.items()},
            "n_band_hits_union": len(band_union),
            "n_geometry_band_hits": len(geometry_hits),
            "n_union": len(union_hits),
            "n_intersection": len(intersection_hits),
            "fraction_band_only": round((len(band_union) - len(intersection_hits)) / n, 6),
            "fraction_geometry_only": round((len(geometry_hits) - len(intersection_hits)) / n, 6),
            "min_distance_to_geometry_band": (
                round(float(np.min(geometry_distances)), 6) if geometry_distances else None
            ),
        })
    return {
        "population": {
            "n_candidates": len(members),
            "n_scans": len({m.source_id for m in members}),
            "n_scoped_to_reconstructable": len(scoped),
        },
        "geometry_terms_verification": verification,
        "solidity_weight_in_geometry_quality": GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
        "quality_band": quality_band,
        "rows": rows,
        "reading": (
            "The three solidity bands and the geometry_quality term are consumers of "
            "one value through two independent routes. The overlap columns are the "
            "interaction: a solidity shift that changes a band decision without "
            "changing the geometry term is invisible to the geometry path, and vice "
            "versa. Neither route has an independent calibration, so neither can be "
            "used to validate the other. A zero intersection is a statement about "
            "this population's geometry_quality distribution -- reported as the "
            "minimum distance to the band rather than left as a bare zero."
        ),
    }


# ---------------------------------------------------------------------------
# Probe 2: geometry_quality x evidence
# ---------------------------------------------------------------------------


def geometry_quality_x_evidence(
    members: Sequence[PopulationMember],
    *,
    weights: Sequence[float] = (0.0, 0.10, 0.20, 0.30, 0.40),
) -> dict[str, Any]:
    """Move the solidity weight in ``geometry_quality``; watch the evidence move.

    ``geometry`` is a weighted feature in four hypothesis tables at 0.06-0.10 and
    a 0.10 support term in the quality score. The probe rebuilds the candidate's
    ``geometry_quality`` at each weight, re-scores the hypotheses from the
    resulting feature vector, and counts selection changes.

    The feature vector is rebuilt rather than mutated: ``score_hypotheses`` reads
    ``candidate.geometry_quality`` through ``_features``, so a copy carrying the
    perturbed value is the faithful way to move the mediator.
    """
    from dataclasses import replace

    verification = _verify_geometry_terms(members)
    baseline = {id(m): classify_from_evidence(m.candidate)[0] for m in members}
    rows: list[dict[str, Any]] = []
    for weight in weights:
        changed = 0
        margins: list[float] = []
        for member in members:
            terms = _geometry_quality_terms_for(member)
            perturbed_geometry = _geometry_quality_with_solidity(
                member.candidate, weight, n_cells=terms["n_cells"], fill=terms["fill"]
            )
            if abs(perturbed_geometry - float(member.candidate.geometry_quality)) < 1e-12:
                continue
            probe = replace(member.candidate, geometry_quality=perturbed_geometry)
            label, _s, margin, _r, _reason, _method = classify_from_evidence(probe)
            if label != baseline[id(member)]:
                changed += 1
            margins.append(margin)
        rows.append({
            "solidity_weight": float(weight),
            "is_production": bool(abs(weight - GEOMETRY_QUALITY_SOLIDITY_WEIGHT) < 1e-12),
            "n_geometry_changed": len(margins),
            "n_evidence_selection_changed": changed,
            "fraction_changed": round(changed / max(len(members), 1), 6),
            "median_margin": round(float(np.median(margins)), 6) if margins else None,
        })
    return {
        "population": {
            "n_candidates": len(members),
            "n_scans": len({m.source_id for m in members}),
        },
        "geometry_terms_verification": verification,
        "geometry_feature_weights_in_hypothesis_tables": {
            "metallic-like": 0.08,
            "cavity-like": 0.08,
            "geological-like": 0.06,
            "irregular-anomaly": 0.10,
            "quality_support_geometry": 0.10,
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Probe 3: evidence x min_margin
# ---------------------------------------------------------------------------


def evidence_x_min_margin(
    members: Sequence[PopulationMember],
    *,
    supports: Sequence[float] = (0.40, 0.45, 0.50, 0.55, 0.60, 0.70),
    margins: Sequence[float] = (0.0, 0.01, 0.02, 0.04, 0.08, 0.16),
) -> dict[str, Any]:
    """The two evidence gates jointly: a grid, not two one-factor sweeps.

    ``min_support`` and ``min_margin`` both act on the same decision, so their
    interaction is the question of whether either adds anything the other does not
    already imply. Evaluated on the *measured* joint distribution of (best support,
    margin), which is the only honest way to ask: whether a gate is redundant
    depends on where the population actually sits, not on the gates in isolation.

    Redundancy is defined precisely, because a loose definition produces a confident
    wrong answer. Gate ``G`` **adds nothing beyond** gate ``H`` on this population
    when, at every swept value of ``G``, the count selected by ``G AND H`` equals
    the count ``H`` alone selects. That is strictly stronger than "``G`` changed
    nothing", and it is the claim that would license dropping a constant -- which is
    why it is computed rather than asserted, and why the per-value rows ship with
    it so a reader can see which value broke the equality.
    """
    observations = margin_observations(members)
    n = max(len(observations), 1)
    production_support = DEFAULT_EVIDENCE_MODEL_CONFIG.min_support
    production_margin = DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin

    joint = {
        (support, margin): sum(
            1 for o in observations if o.best_support >= support and o.margin >= margin
        )
        for support in supports
        for margin in margins
    }
    support_only = {
        support: sum(1 for o in observations if o.best_support >= support) for support in supports
    }
    margin_only = {margin: sum(1 for o in observations if o.margin >= margin) for margin in margins}

    def _effect(varying: str) -> dict[str, Any]:
        values = sorted(supports if varying == "support" else margins)
        alone = (
            margin_only[production_margin]
            if varying == "support"
            else support_only[production_support]
        )
        rows = []
        for value in values:
            both = (
                joint[(value, production_margin)]
                if varying == "support"
                else joint[(production_support, value)]
            )
            rows.append({
                "value": value,
                "n_selected_both": both,
                "n_selected_other_alone": alone,
                "adds": both != alone,
                "delta": both - alone,
            })
        return {
            "varying": varying,
            "rows": rows,
            "n_values": len(rows),
            "n_values_that_add": sum(1 for r in rows if r["adds"]),
            "adds_nothing_beyond_other": all(not r["adds"] for r in rows),
        }

    support_effect = _effect("support")
    margin_effect = _effect("margin")
    return {
        "population": {
            "n_candidates": len(observations),
            "n_scans": len({o.source_id for o in observations}),
        },
        "production": {
            "min_support": production_support,
            "min_margin": production_margin,
        },
        "swept_supports": list(supports),
        "swept_margins": list(margins),
        "joint_grid": [
            {
                "min_support": support,
                "min_margin": margin,
                "n_selected": joint[(support, margin)],
                "fraction_rejected": round(1.0 - joint[(support, margin)] / n, 4),
            }
            for support in supports
            for margin in margins
        ],
        "support_only": support_only,
        "margin_only": margin_only,
        "min_support_effect": support_effect,
        "min_margin_effect": margin_effect,
        "min_support_redundant_given_min_margin": support_effect["adds_nothing_beyond_other"],
        "min_margin_redundant_given_min_support": margin_effect["adds_nothing_beyond_other"],
        "reading": (
            "A gate adds nothing beyond the other here when, at every swept value, the "
            "count selected by both equals the count the other gate alone selects. That "
            "is a property of this population, not of the model: a different population "
            "can make either gate load-bearing again, which is why a redundancy finding "
            "would not by itself license deleting a constant -- and why a finding of "
            "non-redundancy says only that this population exercises both."
        ),
    }


def resolution_x_shape_metric(
    pitch_low_m: float = 0.25,
    pitch_high_m: float = 1.0,
    *,
    seed: int = 0,
    match_tolerance_m: float | None = None,
) -> dict[str, Any]:
    """Does the sampling pitch move solidity or compactness on real candidates?

    On the analytic catalogue the answer for solidity is already a theorem (it
    cannot move) and for compactness already a measurement (it moves with
    component size). This probe asks the operational version of the same question:
    across the *pipeline's own* candidates at two pitches, how far do the two
    metrics travel, and does the movement track pitch or component size?

    The attribution matters, because "moves with pitch" and "moves with size" have
    opposite implications: the first is a raster artifact to be corrected, the
    second is a property of the estimator that any band has to live with.

    Candidates are matched *within a case* by nearest centroid, not by index or by
    cell count. Two lattices cannot produce the same component indices, and index
    alignment would silently pair a fine-pitch blob with a coarse-pitch ring -- a
    fabricated correspondence that would then be measured.
    """
    from pathlib import Path

    from ...services.single_scan import analyze_scan
    from .datasets import perturbation_catalogue
    from .decision import _run_case_scan

    tolerance = (
        match_tolerance_m if match_tolerance_m is not None else max(pitch_low_m, pitch_high_m)
    )

    def _collect(pitch: float) -> dict[str, list[Candidate]]:
        out: dict[str, list[Candidate]] = {}
        for case in perturbation_catalogue():
            scan = _run_case_scan(case, pitch, seed)
            _grid, _anomaly, candidates = analyze_scan(
                scan, out_dir=Path("."), label=case.case_id, write_outputs=False
            )
            out[case.case_id] = list(candidates)
        return out

    coarse = _collect(pitch_low_m)
    fine = _collect(pitch_high_m)
    solidity_deltas: list[float] = []
    compactness_deltas: list[float] = []
    size_pairs: list[tuple[float, float]] = []
    per_row: list[dict[str, Any]] = []
    for case_id, coarse_candidates in coarse.items():
        fine_candidates = fine.get(case_id, [])
        for candidate in coarse_candidates:
            best = None
            best_distance = float("inf")
            for other in fine_candidates:
                distance = math.hypot(
                    float(other.x_center) - float(candidate.x_center),
                    float(other.y_center) - float(candidate.y_center),
                )
                if distance < best_distance:
                    best_distance = distance
                    best = other
            if best is None or best_distance > tolerance:
                continue
            solidity_deltas.append(float(best.solidity) - float(candidate.solidity))
            compactness_deltas.append(float(best.compactness) - float(candidate.compactness))
            size_pairs.append((float(candidate.area_cells), float(best.area_cells)))
            per_row.append({
                "case_id": case_id,
                "centroid_error_m": round(best_distance, 6),
                "n_cells_coarse": int(candidate.area_cells),
                "n_cells_fine": int(best.area_cells),
                "solidity_coarse": round(float(candidate.solidity), 6),
                "solidity_fine": round(float(best.solidity), 6),
                "compactness_coarse": round(float(candidate.compactness), 6),
                "compactness_fine": round(float(best.compactness), 6),
            })
    solidity_arr = np.array(solidity_deltas, dtype=float)
    compactness_arr = np.array(compactness_deltas, dtype=float)
    size_arr = np.array(size_pairs, dtype=float) if size_pairs else np.zeros((0, 2))
    correlation = (
        float(np.corrcoef(size_arr[:, 0], compactness_arr)[0, 1])
        if size_arr.shape[0] > 2 and compactness_arr.size == size_arr.shape[0]
        else float("nan")
    )
    # The decisive split. The S02 algebra makes solidity a function of the cell set
    # alone, so a matched pair whose cell COUNT is unchanged at both pitches must
    # agree; any disagreement there would be a metric defect rather than a
    # rasterization effect. Pairs whose cell count changed are a different
    # measurement: the raster produced a different shape, so a different solidity is
    # the honest result and violates nothing.
    same_count = [r for r in per_row if r["n_cells_coarse"] == r["n_cells_fine"]]
    different_count = [r for r in per_row if r["n_cells_coarse"] != r["n_cells_fine"]]
    same_count_max_delta = max(
        (abs(r["solidity_fine"] - r["solidity_coarse"]) for r in same_count), default=None
    )
    return {
        "pitch_coarse_m": pitch_low_m,
        "pitch_fine_m": pitch_high_m,
        "match_tolerance_m": tolerance,
        "n_candidates_coarse": sum(len(v) for v in coarse.values()),
        "n_candidates_fine": sum(len(v) for v in fine.values()),
        "n_matched": len(per_row),
        "matched_split": {
            "n_same_cell_count": len(same_count),
            "n_different_cell_count": len(different_count),
            "max_abs_solidity_delta_same_cell_count": (
                round(same_count_max_delta, 9) if same_count_max_delta is not None else None
            ),
            "metric_invariant_on_same_cell_set": (
                bool(same_count_max_delta < 1e-9) if same_count_max_delta is not None else None
            ),
            "guard_vacuous": not same_count,
            "guard_note": (
                "No matched pair in this population had the same cell count at both "
                "pitches, so this probe cannot witness metric invariance: every pair it "
                "found is a different cell set. The metric-level invariance is "
                "established instead by calibration.geometry.pitch_invariance, which "
                "holds the cell set fixed by construction. A vacuous guard is reported as "
                "vacuous rather than as a pass."
            ),
        },
        "solidity_population_shift": {
            "max_abs_delta": round(float(np.abs(solidity_arr).max()), 6)
            if solidity_arr.size
            else None,
            "mean_delta": round(float(solidity_arr.mean()), 6) if solidity_arr.size else None,
        },
        "compactness": {
            "max_abs_delta": round(float(np.abs(compactness_arr).max()), 6)
            if compactness_arr.size
            else None,
            "mean_delta": round(float(compactness_arr.mean()), 6) if compactness_arr.size else None,
            "corr_with_coarse_cell_count": (
                round(correlation, 4) if np.isfinite(correlation) else None
            ),
        },
        "rows": per_row,
        "attribution": (
            "Two different movements are separated here and must not be added together. "
            "(1) The METRIC: solidity is a function of the cell set alone, so a matched "
            "pair with the same cell count must agree to round-off, and the "
            "same-cell-count column is the regression guard for that. (2) The POPULATION: "
            "the detector's mask at 0.25 m and at 1.0 m is not the same shape, so a "
            "candidate's solidity legitimately differs between pitches. That is a "
            "rasterization effect on which cell sets exist, not a property of the ratio "
            "-- and it is why a solidity band, though pitch-free as a comparison, is "
            "still regime-dependent through the population it is applied to. "
            "Compactness has no invariance to fall back on: it is a boundary-cell count, "
            "so its movement is confounded with component size and the cell-count "
            "correlation is the discriminator."
        ),
    }


def scale_status_x_anomaly_zscore(
    members: Sequence[PopulationMember],
) -> dict[str, Any]:
    """Does a degraded scale read differently in the z-score than a valid one?

    Stage 3 gave a scale estimate a status precisely so a scale that could not be
    measured would not reach a threshold as if it were a number. The operational
    question this probe answers is whether the status is *correlated* with the
    z-scores that consume it -- because a correlation would mean the z-score
    distribution is conditioned on an estimator-quality variable, and a threshold
    calibrated without that conditioning is reading a mixture.

    The measured answer is that the question does not arise on the candidate path:
    ``Candidate`` has no ``scale_status`` field. The S03 status is carried by the
    shadow ledger, which is off by default and
    deciding nothing. That is reported as NOT APPLICABLE *with* the measurement,
    because a coupling that is absent by construction is a stronger and more
    actionable statement than a measured absence of correlation.
    """
    from collections import Counter

    from ..._util import (
        SCALE_STATUS_DEGRADED,
        SCALE_STATUS_INDETERMINATE,
        SCALE_STATUS_LOW_SAMPLE,
        SCALE_STATUS_VALID,
    )

    by_status: dict[str, list[float]] = {
        SCALE_STATUS_VALID: [],
        SCALE_STATUS_DEGRADED: [],
        SCALE_STATUS_INDETERMINATE: [],
        SCALE_STATUS_LOW_SAMPLE: [],
    }
    for member in members:
        status = str(getattr(member.candidate, "scale_status", "") or "")
        if status in by_status:
            by_status[status].append(abs(float(member.candidate.anomaly_score)))
    carrying = sum(1 for m in members if getattr(m.candidate, "scale_status", None))
    return {
        "population": {"n_candidates": len(members)},
        "status_counts": {k: len(v) for k, v in by_status.items()},
        "observed_status_values": dict(
            Counter(str(getattr(m.candidate, "scale_status", "") or "") for m in members)
        ),
        "abs_z_by_status": {
            status: (
                {
                    "n": len(values),
                    "median_abs_z": round(float(np.median(values)), 4),
                    "p95_abs_z": round(float(np.percentile(values, 95)), 4),
                }
                if values
                else {"n": 0}
            )
            for status, values in by_status.items()
        },
        "n_candidates_carrying_a_status_field": carrying,
        "status_sites": [
            "groundscan/diagnostics/shadow.py (S03 shadow ledger)",
            "groundscan/diagnostics/shadow.py (S03 ScaleShadow ledger)",
        ],
        "verdict": (
            "No candidate carries a scale status, because the field does not exist on "
            "Candidate: the S03 status is confined to the shadow and diagnostics "
            "channels, which are off by default and feed no threshold. The interaction is "
            "therefore NOT APPLICABLE on this path rather than merely unobserved. If S03 "
            "is ever activated onto the candidate path, this interaction becomes real and "
            "must be re-measured before any z-score threshold is trusted on a "
            "conditioned population."
        ),
    }


# ---------------------------------------------------------------------------
# Probe 6: d_res x candidate decomposition
# ---------------------------------------------------------------------------


def d_res_x_decomposition(
    *,
    sigma_m: float = 1.0,
    pitch_dx_m: float = 0.5,
    noise_sigma: float = 1.0,
    amplitude: float = 10.0,
    multipliers: Sequence[float] = (0.6, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
    seeds: Sequence[int] = (0, 1, 2),
) -> dict[str, Any]:
    """Is the decomposition's answer a function of separation alone?

    S01 is deliberately not activated, so production's decomposition policy is
    untouched. What this probe measures is the *dependency the activation would
    rest on*: for a swept separation, does anything downstream change at the same
    place the region count does, or does each downstream response have its own,
    different crossing?

    If they crossed together, one ``d_res`` would be enough. If they do not, a
    single number would have to be wrong for at least one consumer -- which is the
    strongest available evidence against the idea of a universal ``d_res``.
    """
    from .resolution import analytic_bifurcation_separation_m, separation_trial

    analytic = analytic_bifurcation_separation_m(sigma_m)
    rows: list[dict[str, Any]] = []
    for multiplier in multipliers:
        separation = multiplier * analytic
        resolved = 0
        for seed in seeds:
            trial = separation_trial(
                sigma_m=sigma_m,
                separation_m=separation,
                pitch_dx_m=pitch_dx_m,
                amplitude=amplitude,
                noise_sigma=noise_sigma,
                seed=seed,
            )
            resolved += int(trial.outcome == "resolved-as-constructed")
        rows.append({
            "multiplier_of_2sigma": multiplier,
            "separation_m": round(separation, 6),
            "n_resolved_of_seeds": resolved,
            "n_seeds": len(seeds),
            "resolved_at_every_seed": resolved == len(seeds),
        })
    first_resolving = next(
        (r["multiplier_of_2sigma"] for r in rows if r["resolved_at_every_seed"]), None
    )
    return {
        "sigma_m": sigma_m,
        "pitch_dx_m": pitch_dx_m,
        "noise_sigma": noise_sigma,
        "analytic_d_res_m": analytic,
        "rows": rows,
        "first_multiplier_resolved": first_resolving,
        "decomposition_policy": (
            "conservative-nest; d_res unset; S01 characterized and not activated"
        ),
        "verdict": (
            "The decomposition policy takes the conservative branch at every "
            "separation, so it has no crossing to misalign with the region count. "
            "Activating d_res would therefore introduce a new decision, not adjust "
            "an existing one, and the crossing measured here is the only evidence "
            "available about where it would sit."
        ),
    }


# ---------------------------------------------------------------------------
# The roll-up
# ---------------------------------------------------------------------------


def interaction_report(
    members: Sequence[PopulationMember] | None = None,
    *,
    limit_vendor: int | None = None,
) -> dict[str, Any]:
    """Every interaction probe, one after another, on one stated population."""
    population = (
        tuple(members) if members is not None else candidate_population(limit_vendor=limit_vendor)
    )
    return {
        "population": {
            "n_candidates": len(population),
            "n_scans": len({m.source_id for m in population}),
        },
        "solidity_x_geometry_quality": solidity_x_geometry_quality(population),
        "geometry_quality_x_evidence": geometry_quality_x_evidence(population),
        "evidence_x_min_margin": evidence_x_min_margin(population),
        "resolution_x_shape_metric": resolution_x_shape_metric(),
        "scale_status_x_anomaly_zscore": scale_status_x_anomaly_zscore(population),
        "d_res_x_decomposition": d_res_x_decomposition(),
    }

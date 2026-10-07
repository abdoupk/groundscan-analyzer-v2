"""Phases D, G and H -- decision margin, the 3-sigma heuristic, and the gate chain.

The three share a dependency chain, so they are characterized together and kept
apart in their conclusions:

.. code-block:: text

    raw metrics -> geometry_quality -> evidence -> screening -> review_status

Phase D -- ``min_margin``
    The margin in ``core.evidence.classify_from_evidence`` is
    ``best - runner-up``. Before sweeping it, the *structure* of that number has
    to be established, because a sweep over a parameter that is either inert or
    a restatement of another parameter teaches nothing. The structure here is
    exact and is derived below rather than discovered empirically: the
    ``unknown`` hypothesis is a declared affine function of the best specific
    support, so whenever ``unknown`` is the runner-up the margin is an affine
    function of the winner too, and ``min_margin`` reduces to a floor on the
    winner's support. Whether that floor binds is then a measurement.

Phase G -- ``threshold = 3.0``
    Characterized as the heuristic it is. The named sources of departure from a
    nominal 0.27% per-cell exceedance are each measured separately: the max over
    four correlated z-fields, the spatial correlation the median filter induces,
    the heavy tails a real instrument produces, the contamination fraction, and
    the maxima selection that follows thresholding. No significance claim is
    made or unmade here; the output says what the number is and is not.

Phase H -- evidence / quality / screening
    One factor at a time. The chain is walked, each threshold is perturbed in
    isolation on a fixed population, and the decisions that change are counted.
    A threshold nothing changes is *not* thereby validated: it is inert, which
    is a different and weaker thing, and the summary says which is which.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from ..._util import CONTAMINATION_FRACTION, CONTAMINATION_SIGMAS
from ...core.background import multiscale_zscore, robust_zscore
from ...core.classify import ClassificationConfig, classify_candidate
from ...core.evidence import (
    DEFAULT_EVIDENCE_MODEL_CONFIG,
    EvidenceModelConfig,
    classify_from_evidence,
    score_hypotheses,
)
from ...gates.quality import assess_candidate_quality
from ...gates.screening import DEFAULT_SCREENING_POLICY, ScreeningPolicy, screen_candidates
from ...models import Candidate
from ...services.config import AnalysisConfig
from ..synthetic_core.cross_resolution import PhysicalResponse, PhysicalScene, Resolution
from .datasets import (
    CATEGORY_PERTURBATION,
    CATEGORY_VENDOR,
    PerturbationCase,
    contamination_field,
    perturbation_catalogue,
    vendor_fixture_index,
)

# ---------------------------------------------------------------------------
# The candidate population
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationMember:
    """One candidate plus the provenance of the scan it came from.

    Every downstream sweep states its population this way, so a count in the
    output always carries the corpus it was measured on. A sensitivity number
    without its population is not a characterization.
    """

    candidate: Candidate
    source_id: str
    category: str
    case_factor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "category": self.category,
            "case_factor": self.case_factor,
            "id": self.candidate.id,
            "hypothesis": self.candidate.pattern_hypothesis,
            "evidence_score": self.candidate.evidence_score,
            "quality_score": self.candidate.quality_score,
            "screening_score": self.candidate.screening_score,
            "review_status": self.candidate.review_status,
            "solidity": self.candidate.solidity,
            "compactness": self.candidate.compactness,
            "geometry_quality": self.candidate.geometry_quality,
            "area_cells": self.candidate.area_cells,
            "anomaly_score": self.candidate.anomaly_score,
        }


def _run_case_scan(case: PerturbationCase, pitch_m: float, seed: int) -> Any:
    from ..synthetic_core.cross_resolution import Resolution as _Resolution
    from ..synthetic_core.cross_resolution import sample_scene

    scene = PhysicalScene(
        name=case.case_id,
        width_m=case.width_m,
        height_m=case.height_m,
        responses=case.responses,
        noise_sigma=case.noise_sigma,
        case_family=case.factor,
    )
    resolution = _Resolution(
        name=f"p{pitch_m:g}",
        dx=float(pitch_m),
        width_m=case.width_m,
        height_m=case.height_m,
        dy_ratio=float(case.dy_ratio),
    )
    return sample_scene(scene, resolution, seed=seed)


def candidate_population(
    *,
    include_perturbation: bool = True,
    include_vendor: bool = True,
    pitch_m: float = 0.5,
    seed: int = 0,
    config: AnalysisConfig | None = None,
    limit_vendor: int | None = None,
) -> tuple[PopulationMember, ...]:
    """Build a fixed candidate population from categories B and C.

    Built by running the real analysis path (``analyze_scan`` with
    ``write_outputs=False``), so every field is a production value rather than a
    hand-populated stand-in. Perturbation cases come first and vendor fixtures
    second, and the order is stable, so a count is reproducible.
    """
    from ...services.single_scan import analyze_scan

    cfg = config or AnalysisConfig()
    out: list[PopulationMember] = []
    if include_perturbation:
        for case in perturbation_catalogue():
            scan = _run_case_scan(case, pitch_m, seed)
            _grid, _anomaly, candidates = analyze_scan(
                scan, out_dir=Path("."), label=case.case_id, config=cfg, write_outputs=False
            )
            for candidate in candidates:
                out.append(
                    PopulationMember(
                        candidate=candidate,
                        source_id=case.case_id,
                        category=CATEGORY_PERTURBATION,
                        case_factor=case.factor,
                    )
                )
    if include_vendor:
        from ...services.single_scan import load_scan

        fixtures = vendor_fixture_index()
        if limit_vendor is not None:
            fixtures = fixtures[:limit_vendor]
        for fixture in fixtures:
            path = Path(fixture.relative_path)
            if not path.is_file():
                continue
            scan = load_scan(path)
            _grid, _anomaly, candidates = analyze_scan(
                scan,
                out_dir=Path("."),
                label=fixture.case_id,
                config=cfg,
                write_outputs=False,
            )
            for candidate in candidates:
                out.append(
                    PopulationMember(
                        candidate=candidate,
                        source_id=fixture.case_id,
                        category=CATEGORY_VENDOR,
                        case_factor="vendor",
                    )
                )
    return tuple(out)


def population_summary(members: Sequence[PopulationMember]) -> dict[str, Any]:
    """A population's shape, so every later count can be read against it."""
    by_category: dict[str, int] = {}
    by_factor: dict[str, int] = {}
    for member in members:
        by_category[member.category] = by_category.get(member.category, 0) + 1
        by_factor[member.case_factor] = by_factor.get(member.case_factor, 0) + 1
    hypotheses: dict[str, int] = {}
    for member in members:
        key = str(member.candidate.pattern_hypothesis)
        hypotheses[key] = hypotheses.get(key, 0) + 1
    return {
        "n_candidates": len(members),
        "n_scans": len({m.source_id for m in members}),
        "by_category": by_category,
        "by_case_factor": by_factor,
        "by_hypothesis": dict(sorted(hypotheses.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


# ---------------------------------------------------------------------------
# Phase D -- min_margin
# ---------------------------------------------------------------------------

#: The affine map the evidence model applies to the best specific support when it
#: builds the residual ``unknown`` hypothesis. Read straight out of
#: ``core.evidence.score_hypotheses``:
#:
#:     supports["unknown"] = max(0.05, 0.58 - 0.45 * specific_best)
#:
#: Since ``specific_best <= 1`` the floor is never reached (0.58 - 0.45 = 0.13 >
#: 0.05), so the map is *unconditionally* affine over the whole reachable range.
#: That is what makes the margin analytic rather than merely empirical.
UNKNOWN_INTERCEPT = 0.58
UNKNOWN_SLOPE = -0.45
UNKNOWN_FLOOR = 0.05


def unknown_support(specific_best: float) -> float:
    """The residual ``unknown`` support, as production computes it."""
    return max(UNKNOWN_FLOOR, UNKNOWN_INTERCEPT + UNKNOWN_SLOPE * float(specific_best))


def margin_from_specific_best(specific_best: float) -> float:
    """Margin against the ``unknown`` runner-up, as a closed form."""
    return float(specific_best) - unknown_support(specific_best)


def equivalent_support_floor(min_margin: float) -> float:
    """The best-support floor that ``min_margin`` is equivalent to.

    Solving ``S - (0.58 - 0.45 S) = min_margin`` gives
    ``S = (min_margin + 0.58) / 1.45``. This is the whole content of
    ``min_margin`` whenever the runner-up is ``unknown``: the two constants are
    the same gate written twice.
    """
    return (float(min_margin) + UNKNOWN_INTERCEPT) / (1.0 - UNKNOWN_SLOPE)


@dataclass(frozen=True)
class MarginObservation:
    """One candidate's decision margin and the identity of its runner-up."""

    source_id: str
    category: str
    case_factor: str
    best_hypothesis: str
    best_support: float
    runner_up: str
    runner_up_support: float
    margin: float
    runner_up_is_unknown: bool
    selected: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "category": self.category,
            "case_factor": self.case_factor,
            "best_hypothesis": self.best_hypothesis,
            "best_support": round(self.best_support, 6),
            "runner_up": self.runner_up,
            "runner_up_support": round(self.runner_up_support, 6),
            "margin": self.margin,
            "runner_up_is_unknown": self.runner_up_is_unknown,
            "selected": self.selected,
        }


def margin_observations(
    members: Sequence[PopulationMember],
    *,
    config: EvidenceModelConfig = DEFAULT_EVIDENCE_MODEL_CONFIG,
) -> tuple[MarginObservation, ...]:
    """Every candidate's margin, with the runner-up's identity resolved.

    ``classify_from_evidence`` rounds the margin to three decimals, which is
    recorded here so the sensitivity sweep measures the value the *gate* sees
    rather than an unrounded intermediate.
    """
    out: list[MarginObservation] = []
    for member in members:
        scores = score_hypotheses(member.candidate)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        best, best_score = ranked[0]
        second, second_score = ranked[1]
        selected, _s, _m, _r, _reason, _method = classify_from_evidence(
            member.candidate, config=config
        )
        out.append(
            MarginObservation(
                source_id=member.source_id,
                category=member.category,
                case_factor=member.case_factor,
                best_hypothesis=best,
                best_support=float(best_score),
                runner_up=second,
                runner_up_support=float(second_score),
                margin=round(float(best_score) - float(second_score), 3),
                runner_up_is_unknown=(second == "unknown"),
                selected=selected,
            )
        )
    return tuple(out)


def margin_structure(
    members: Sequence[PopulationMember],
    *,
    config: EvidenceModelConfig = DEFAULT_EVIDENCE_MODEL_CONFIG,
) -> dict[str, Any]:
    """Establish what ``min_margin`` *is* before sweeping it.

    Three findings, each measured on the population rather than argued:

    1. how often the runner-up is ``unknown`` -- the branch in which the margin
       is an affine function of the winner;
    2. the best-support floor that ``min_margin`` reduces to in that branch, and
       whether ``min_support`` already exceeds it (which would make
       ``min_margin`` unreachable there);
    3. the margin distribution in the branch where a *specific* hypothesis is the
       runner-up, which is the only place the constant can bind.
    """
    observations = margin_observations(members, config=config)
    if not observations:
        return {"n_candidates": 0, "note": "empty population"}
    unknown_runner_up = [o for o in observations if o.runner_up_is_unknown]
    specific_runner_up = [o for o in observations if not o.runner_up_is_unknown]
    floor = equivalent_support_floor(config.min_margin)
    redundancy = config.min_support - floor
    margins = np.array([o.margin for o in observations], dtype=float)
    specific_margins = np.array([o.margin for o in specific_runner_up], dtype=float)
    # Consistency check: the closed form must reproduce the measured margin
    # wherever the runner-up is unknown. This is the guard that makes the
    # structural claim an evidence-backed one.
    closed_form_error = 0.0
    for observation in unknown_runner_up:
        predicted = margin_from_specific_best(observation.best_support)
        closed_form_error = max(closed_form_error, abs(predicted - observation.runner_up_support))
    return {
        "n_candidates": len(observations),
        "population": population_summary(members),
        "config": {
            "min_support": config.min_support,
            "min_margin": config.min_margin,
            "unknown_floor": config.unknown_floor,
        },
        "runner_up_is_unknown": {
            "n": len(unknown_runner_up),
            "fraction": round(len(unknown_runner_up) / len(observations), 4),
        },
        "runner_up_is_specific": {
            "n": len(specific_runner_up),
            "fraction": round(len(specific_runner_up) / len(observations), 4),
            "top_pairs": _top_runner_up_pairs(specific_runner_up),
        },
        "unknown_closed_form": {
            "intercept": UNKNOWN_INTERCEPT,
            "slope": UNKNOWN_SLOPE,
            "floor": UNKNOWN_FLOOR,
            "floor_reachable": False,
            "max_abs_prediction_error": round(closed_form_error, 9),
            "verified": bool(closed_form_error < 1e-3),
        },
        "equivalent_support_floor": round(floor, 6),
        "min_support": config.min_support,
        "redundancy_margin": round(redundancy, 6),
        "min_margin_binds_against_unknown_runner_up": bool(redundancy > 0.0),
        "margin_distribution": {
            "min": round(float(margins.min()), 4),
            "p05": round(float(np.percentile(margins, 5)), 4),
            "median": round(float(np.median(margins)), 4),
            "p95": round(float(np.percentile(margins, 95)), 4),
            "max": round(float(margins.max()), 4),
        },
        "specific_runner_up_margin_distribution": (
            {
                "min": round(float(specific_margins.min()), 4),
                "median": round(float(np.median(specific_margins)), 4),
                "max": round(float(specific_margins.max()), 4),
                "n_below_production_min_margin": int((specific_margins < config.min_margin).sum()),
            }
            if specific_margins.size
            else None
        ),
    }


def _top_runner_up_pairs(observations: Sequence[MarginObservation], limit: int = 8) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for observation in observations:
        key = (observation.best_hypothesis, observation.runner_up)
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"best": pair[0], "runner_up": pair[1], "n": n} for pair, n in ordered[:limit]]


def margin_sensitivity_sweep(
    members: Sequence[PopulationMember],
    *,
    values: Sequence[float] = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20),
) -> dict[str, Any]:
    """How many decisions does ``min_margin`` actually decide?

    One factor, everything else at production values. For each candidate value
    the selected hypothesis is recomputed and compared with the production
    selection. The result is a *decision count*, not a score distribution: a
    parameter that changes no decision on a real corpus has no characterization
    to be given, which is a finding and not a null result to be hidden.
    """
    production = DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    baseline = {
        (m.source_id, m.candidate.id): classify_from_evidence(m.candidate)[0] for m in members
    }
    rows: list[dict[str, Any]] = []
    for value in values:
        config = EvidenceModelConfig(min_margin=float(value))
        changed = 0
        to_unknown = 0
        from_unknown = 0
        for member in members:
            key = (member.source_id, member.candidate.id)
            previous = baseline[key]
            now = classify_from_evidence(member.candidate, config=config)[0]
            if now == previous:
                continue
            changed += 1
            if now == "unknown":
                to_unknown += 1
            if previous == "unknown":
                from_unknown += 1
        rows.append({
            "min_margin": float(value),
            "is_production": bool(value == production),
            "n_changed": changed,
            "fraction_changed": round(changed / max(len(members), 1), 6),
            "n_to_unknown": to_unknown,
            "n_from_unknown": from_unknown,
        })
    return {
        "n_candidates": len(members),
        "production_min_margin": production,
        "rows": rows,
        "n_changed_at_production_relative_to_zero": next(
            (r["n_changed"] for r in rows if r["min_margin"] == 0.0), None
        ),
        "largest_swept_value": float(max(values)),
    }


# ---------------------------------------------------------------------------
# Phase D -- perturbation stability: the instability zone
# ---------------------------------------------------------------------------

#: The margin bins the instability analysis is reported in. Fixed bins, not
#: quantiles, so two populations can be compared bin for bin.
MARGIN_BINS: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10, 0.20, 1.01)


def margin_instability_zone(
    *,
    response_sigma_m: float = 1.0,
    amplitude: float = 10.0,
    noise_sigma: float = 1.0,
    pitch_m: float = 0.5,
    perturbations: Sequence[tuple[str, float]] = (
        ("translate", 0.1),
        ("translate", 0.2),
        ("translate", 0.35),
        ("noise", 0.25),
        ("noise", 0.5),
        ("amplitude", 0.9),
        ("amplitude", 1.1),
    ),
    seeds: Sequence[int] = (0, 1, 2, 3, 4),
    width_m: float = 24.0,
    height_m: float = 18.0,
    config: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """Does the output actually change where the margin is small?

    The decision to sweep ``min_margin`` is only defensible if a small margin
    corresponds to an unstable decision. This measures that directly: one
    constructed response, perturbed one factor at a time, and for each member of
    the resulting population the margin and whether the selected hypothesis moved
    relative to the unperturbed reference.

    Reported per margin bin, because the useful question is not "how often does
    the label change" but "how often does it change *here*, near the threshold".
    """
    from ...services.single_scan import analyze_scan

    cfg = config or AnalysisConfig()

    def _scene(cx: float, amp: float, noise: float) -> PhysicalScene:
        return PhysicalScene(
            name="instability",
            width_m=width_m,
            height_m=height_m,
            responses=(
                PhysicalResponse(
                    label="resp",
                    cx=cx,
                    cy=height_m / 2.0,
                    sigma_x=response_sigma_m,
                    sigma_y=response_sigma_m,
                    amplitude=amp,
                ),
            ),
            noise_sigma=noise,
            case_family="instability",
        )

    def _candidates(scene: PhysicalScene, seed: int) -> list[Candidate]:
        resolution = Resolution(
            name=f"p{pitch_m:g}", dx=pitch_m, width_m=width_m, height_m=height_m
        )
        from ..synthetic_core.cross_resolution import sample_scene

        scan = sample_scene(scene, resolution, seed=seed)
        _grid, _anomaly, candidates = analyze_scan(
            scan, out_dir=Path("."), label="instability", config=cfg, write_outputs=False
        )
        return candidates

    base_scene = _scene(width_m / 2.0, amplitude, noise_sigma)
    base_labels: dict[int, str] = {}
    for seed in seeds:
        for candidate in _candidates(base_scene, seed):
            base_labels.setdefault(seed, candidate.pattern_hypothesis)

    rows: list[dict[str, Any]] = []
    for factor, level in perturbations:
        for seed in seeds:
            if factor == "translate":
                scene = _scene(width_m / 2.0 + level, amplitude, noise_sigma)
            elif factor == "noise":
                scene = _scene(width_m / 2.0, amplitude, noise_sigma + level)
            elif factor == "amplitude":
                scene = _scene(width_m / 2.0, amplitude * level, noise_sigma)
            else:  # pragma: no cover - guarded by the caller's tuple
                raise ValueError(f"unknown perturbation factor {factor!r}")
            for candidate in _candidates(scene, seed):
                scores = score_hypotheses(candidate)
                ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
                margin = round(float(ranked[0][1]) - float(ranked[1][1]), 3)
                reference = base_labels.get(seed, "")
                rows.append({
                    "factor": factor,
                    "level": level,
                    "seed": seed,
                    "margin": margin,
                    "label": candidate.pattern_hypothesis,
                    "reference_label": reference,
                    "flipped": bool(candidate.pattern_hypothesis != reference),
                })

    per_bin: list[dict[str, Any]] = []
    for lo, hi in zip(MARGIN_BINS[:-1], MARGIN_BINS[1:], strict=True):
        in_bin = [r for r in rows if lo <= r["margin"] < hi]
        per_bin.append({
            "margin_from": lo,
            "margin_to": hi,
            "n": len(in_bin),
            "n_flipped": sum(1 for r in in_bin if r["flipped"]),
            "flip_rate": (
                round(sum(1 for r in in_bin if r["flipped"]) / len(in_bin), 4) if in_bin else None
            ),
        })
    return {
        "n_observations": len(rows),
        "perturbations": [{"factor": f, "level": v} for f, v in perturbations],
        "seeds": list(seeds),
        "per_margin_bin": per_bin,
        "margin_bins": list(MARGIN_BINS),
        "monotone_in_margin": _is_monotone(per_bin),
    }


def _is_monotone(per_bin: Sequence[dict[str, Any]]) -> bool:
    rates = [
        (b["margin_from"], b["flip_rate"])
        for b in per_bin
        if b["flip_rate"] is not None and b["n"] > 0
    ]
    if len(rates) < 2:
        return False
    for (_lo_a, rate_a), (_lo_b, rate_b) in zip(rates[:-1], rates[1:], strict=True):
        if rate_b + 1e-9 < rate_a:
            return False
    return True


def evidence_margin_ladder(
    *,
    fractions: Sequence[float] = (
        1.0,
        0.9,
        0.8,
        0.7,
        0.6,
        0.55,
        0.5,
        0.45,
        0.4,
        0.3,
        0.2,
        0.1,
        0.0,
    ),
    amplitude: float = 10.0,
    noise_sigma: float = 1.0,
    pitch_m: float = 0.5,
    seeds: Sequence[int] = (0, 1, 2),
    response_sigma_m: float = 1.0,
    width_m: float = 24.0,
    height_m: float = 18.0,
    config: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """Cases with the evidence separation placed deliberately around the gate.

    The gate compares the best support with the runner-up's, and the
    metallic/cavity competition is decided by the *polarity balance* rather than by
    magnitude: ``metallic-like`` weights ``positive`` at 0.17 and ``cavity-like``
    weights ``negative`` at 0.19, and those two features are complements. The
    polarity fraction is therefore the control that crosses the gate, and it is
    swept here on a candidate the real pipeline produced.

    Exactly two fields are overridden -- ``positive_peak`` and ``negative_peak``,
    set to a controlled ratio at a fixed total magnitude. Everything else,
    including the ``polarity`` label and every morphology field, stays at the
    pipeline's own value. Both facts are stated in the output, because a ladder
    built by editing a candidate's evidence fields would otherwise be read as a
    pipeline measurement. In particular the ``polarity`` label is *not* recomputed
    from the overridden peaks: leaving it alone is what keeps the ladder a
    one-variable perturbation of a real candidate.

    A margin gate can only be characterized on cases that reach it, and the two
    pipeline-level controls that do *not* reach it are reported by
    :func:`controlled_margin_cases` so that failure is on the record too.
    """
    from dataclasses import replace

    from ...services.single_scan import analyze_scan

    cfg = config or AnalysisConfig()
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        scene = PhysicalScene(
            name="margin_evidence",
            width_m=width_m,
            height_m=height_m,
            responses=(
                PhysicalResponse(
                    label="resp",
                    cx=width_m / 2.0,
                    cy=height_m / 2.0,
                    sigma_x=response_sigma_m,
                    sigma_y=response_sigma_m,
                    amplitude=amplitude,
                ),
            ),
            noise_sigma=noise_sigma,
            case_family="margin-ladder",
        )
        resolution = Resolution(
            name=f"p{pitch_m:g}", dx=pitch_m, width_m=width_m, height_m=height_m
        )
        from ..synthetic_core.cross_resolution import sample_scene

        scan = sample_scene(scene, resolution, seed=seed)
        _grid, _anomaly, candidates = analyze_scan(
            scan, out_dir=Path("."), label="margin", config=cfg, write_outputs=False
        )
        if not candidates:
            continue
        base = candidates[0]
        for fraction in fractions:
            probe = replace(
                base,
                positive_peak=amplitude * float(fraction),
                negative_peak=-amplitude * (1.0 - float(fraction)),
            )
            scores = score_hypotheses(probe)
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            selected, _s, _m, _r, _reason, _method = classify_from_evidence(probe)
            rows.append({
                "control": "polarity_fraction",
                "level": float(fraction),
                "seed": seed,
                "margin": round(float(ranked[0][1]) - float(ranked[1][1]), 3),
                "best": ranked[0][0],
                "runner_up": ranked[1][0],
                "selected": selected,
                "polarity": str(probe.polarity),
            })
    production = DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    bands = {
        "below": [r for r in rows if r["margin"] < production * 0.5],
        "just_below": [r for r in rows if production * 0.5 <= r["margin"] < production],
        "exactly_at": [r for r in rows if r["margin"] == production],
        "just_above": [r for r in rows if production < r["margin"] < production * 2.0],
        "well_above": [r for r in rows if r["margin"] >= production * 2.0],
    }
    return {
        "n_observations": len(rows),
        "production_min_margin": production,
        "rows": rows,
        "overridden_fields": ("positive_peak", "negative_peak"),
        "achieved_bands": {
            name: {
                "n": len(group),
                "distinct_margins": sorted({r["margin"] for r in group}),
                "n_selected_unknown": sum(1 for r in group if r["selected"] == "unknown"),
            }
            for name, group in bands.items()
        },
        "margin_is_attainable": bool(bands["below"] or bands["just_below"]),
        "min_margin": min((r["margin"] for r in rows), default=None),
        "max_margin": max((r["margin"] for r in rows), default=None),
        "reading": (
            "The polarity fraction crosses the gate, which is what makes the "
            "near-threshold band reachable at all. The two fields overridden are the "
            "signed peaks; the polarity label and every morphology field stay at the "
            "pipeline's value, so this is a one-variable controlled evidence separation "
            "on a real candidate rather than a pipeline measurement -- stated as such."
        ),
    }


def controlled_margin_cases(
    *,
    balance_levels: Sequence[float] = (0.0, 0.5, 0.8, 0.9, 1.0, 1.1, 1.3, 1.6, 2.0, 3.0),
    amplitude_levels: Sequence[float] = (5.0, 8.0, 10.0, 16.0, 30.0),
    noise_sigma: float = 1.0,
    pitch_m: float = 0.5,
    seeds: Sequence[int] = (0,),
    response_sigma_m: float = 1.0,
    width_m: float = 24.0,
    height_m: float = 18.0,
    config: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """Two pipeline-level controls, recorded for what they do *not* reach.

    Both are honest attempts to walk a case across the gate through the analysis
    path alone, and both stop short. That is the finding: the margin is decided by
    the polarity balance, and neither the response amplitude nor a co-located
    opposite-sign pair approaches it continuously, because the multiscale detector
    splits an opposite-sign pair into two lobes and each lobe is scored on its own.

    Kept alongside :func:`evidence_margin_ladder` so the report can say which
    control works and, more usefully, which do not.
    """
    from ...services.single_scan import analyze_scan

    cfg = config or AnalysisConfig()
    centre_x = width_m / 2.0
    centre_y = height_m / 2.0
    rows: list[dict[str, Any]] = []

    def _run(responses: tuple[Any, ...], control: str, level: float, seed: int) -> None:
        scene = PhysicalScene(
            name=f"margin_{control}_{level:g}",
            width_m=width_m,
            height_m=height_m,
            responses=responses,
            noise_sigma=noise_sigma,
            case_family="margin-ladder",
        )
        resolution = Resolution(
            name=f"p{pitch_m:g}", dx=pitch_m, width_m=width_m, height_m=height_m
        )
        from ..synthetic_core.cross_resolution import sample_scene

        scan = sample_scene(scene, resolution, seed=seed)
        _grid, _anomaly, candidates = analyze_scan(
            scan, out_dir=Path("."), label="margin", config=cfg, write_outputs=False
        )
        for candidate in candidates:
            scores = score_hypotheses(candidate)
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            rows.append({
                "control": control,
                "level": level,
                "seed": seed,
                "margin": round(float(ranked[0][1]) - float(ranked[1][1]), 3),
                "best": ranked[0][0],
                "runner_up": ranked[1][0],
                "selected": str(candidate.pattern_hypothesis),
                "polarity": str(candidate.polarity),
            })

    for balance in balance_levels:
        for seed in seeds:
            _run(
                (
                    PhysicalResponse(
                        label="pos",
                        cx=centre_x,
                        cy=centre_y,
                        sigma_x=response_sigma_m,
                        sigma_y=response_sigma_m,
                        amplitude=10.0,
                    ),
                    PhysicalResponse(
                        label="neg",
                        cx=centre_x,
                        cy=centre_y,
                        sigma_x=response_sigma_m,
                        sigma_y=response_sigma_m,
                        amplitude=-10.0 * balance,
                    ),
                ),
                "balance",
                balance,
                seed,
            )
    for amplitude in amplitude_levels:
        for seed in seeds:
            _run(
                (
                    PhysicalResponse(
                        label="pos",
                        cx=centre_x,
                        cy=centre_y,
                        sigma_x=response_sigma_m,
                        sigma_y=response_sigma_m,
                        amplitude=amplitude,
                    ),
                ),
                "amplitude",
                amplitude,
                seed,
            )

    production = DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    per_control = {
        control: {
            "n": sum(1 for r in rows if r["control"] == control),
            "min_margin": min((r["margin"] for r in rows if r["control"] == control), default=None),
            "max_margin": max((r["margin"] for r in rows if r["control"] == control), default=None),
            "reaches_below_production": any(
                r["margin"] < production for r in rows if r["control"] == control
            ),
        }
        for control in ("balance", "amplitude")
    }
    return {
        "n_observations": len(rows),
        "production_min_margin": production,
        "rows": rows,
        "per_control": per_control,
        "which_control_reaches_the_gate": [
            control for control, stats in per_control.items() if stats["reaches_below_production"]
        ],
        "reading": (
            "Neither pipeline-level control crosses the gate. A co-located opposite-sign "
            "pair is split by the multiscale detector into two lobes that are then scored "
            "independently, and the amplitude ladder does not move the polarity balance at "
            "all. The gate is therefore only reachable by controlling the polarity ratio "
            "itself, which is what evidence_margin_ladder does. A margin sweep built on "
            "either of these controls alone would have reported the parameter as inert."
        ),
    }


# ---------------------------------------------------------------------------
# Phase G -- the 3-sigma heuristic
# ---------------------------------------------------------------------------


def gaussian_two_sided_tail(threshold: float) -> float:
    """``2 * (1 - Phi(threshold))`` for a standard normal, without SciPy's erf.

    Uses ``math.erfc``: ``P(|Z| > t) = erfc(t / sqrt(2))``. Exact enough to
    compare with a measured rate, and stated in closed form so the nominal
    figure is never itself an empirical input.
    """
    return float(math.erfc(float(threshold) / math.sqrt(2.0)))


def morans_i_lag1(z: np.ndarray[Any, Any]) -> float:
    """Lag-1 spatial autocorrelation of a field, Moran's I form.

    Row-standardised weights on the 4-neighbour lattice: every horizontally
    adjacent pair in a row gets weight ``1/(nx-1)`` and every vertically adjacent
    pair in a column ``1/(ny-1)``, so each row and each column contributes total
    weight 1 and ``W = ny + nx`` regardless of the field's shape. Then

    .. code-block:: text

        I = (N / W) * (sum_ij w_ij z_i z_j) / (sum_i (z_i - zbar)^2)

    Reported because the nominal per-cell exceedance rate assumes independence,
    and a median-filtered residual has none: neighbouring z values are strongly
    correlated, so the number of *independent* tests is far below the cell count.
    Without this, a measured exceedance rate cannot be compared with a nominal
    one.

    Sign convention: positive ``I`` means neighbours move together, so a nominal
    per-cell rate over-states how often *independent* excursions occur.
    """
    values = np.asarray(z, dtype=float)
    rows, cols = values.shape
    if rows < 2 or cols < 2:
        return float("nan")
    valid = np.isfinite(values)
    n = float(np.count_nonzero(valid))
    if n < 4:
        return float("nan")
    finite_values = values[valid]
    centred = np.where(valid, values - float(np.mean(finite_values)), 0.0)
    denominator = float(np.sum(centred * centred))
    if denominator <= 0.0:
        return 0.0
    horizontal = centred[:, :-1] * centred[:, 1:]
    horizontal_valid = np.isfinite(values[:, :-1]) & np.isfinite(values[:, 1:])
    vertical = centred[:-1, :] * centred[1:, :]
    vertical_valid = np.isfinite(values[:-1, :]) & np.isfinite(values[1:, :])
    h_sum = float(np.sum(np.where(horizontal_valid, horizontal, 0.0)))
    v_sum = float(np.sum(np.where(vertical_valid, vertical, 0.0)))
    weight = 2.0 * (h_sum / (cols - 1) + v_sum / (rows - 1))
    total_weight = float(rows + cols)
    return (n / total_weight) * weight / denominator


def effective_sample_size(z: np.ndarray[Any, Any]) -> float:
    """``N * (1 - rho) / (1 + rho)``: independent tests implied by lag-1 rho.

    A first-order approximation, and labelled as one. It is used to say *how
    much* the independence assumption is worth, not to make a significance claim.
    """
    rho = morans_i_lag1(z)
    if not np.isfinite(rho):
        return float("nan")
    clamped = float(np.clip(rho, -0.999, 0.999))
    n = float(np.count_nonzero(np.isfinite(np.asarray(z, dtype=float))))
    return n * (1.0 - clamped) / (1.0 + clamped)


@dataclass(frozen=True)
class ThreeSigmaObservation:
    """One noise-only field at one threshold.

    Noise-only is the point: there is no response in the field, so every
    surviving region is by construction a false positive. The four scales of
    ``multiscale_zscore`` are the production ones, so the multiple-comparison
    structure is the production one.
    """

    threshold: float
    rows: int
    cols: int
    n_cells: int
    n_exceeding: int
    n_regions: int
    n_regions_ge_min_size: int
    morans_i: float
    effective_sample_size: float
    nominal_cell_rate: float
    measured_cell_rate: float
    multiplicity_factor: float
    per_cell: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "rows": self.rows,
            "cols": self.cols,
            "n_cells": self.n_cells,
            "n_exceeding": self.n_exceeding,
            "n_regions": self.n_regions,
            "n_regions_ge_min_size": self.n_regions_ge_min_size,
            "morans_i_lag1": round(self.morans_i, 6) if np.isfinite(self.morans_i) else None,
            "effective_sample_size": (
                round(self.effective_sample_size, 2)
                if np.isfinite(self.effective_sample_size)
                else None
            ),
            "nominal_cell_rate": round(self.nominal_cell_rate, 8),
            "measured_cell_rate": round(self.measured_cell_rate, 8),
            "multiplicity_factor": round(self.multiplicity_factor, 4),
            "per_cell": self.per_cell,
        }


def three_sigma_observation(
    *,
    threshold: float,
    rows: int = 64,
    cols: int = 64,
    seed: int = 0,
    scales: tuple[int, ...] | None = None,
    min_size: int | None = None,
    contaminating_fraction: float = 0.0,
    contaminating_amplitude: float = 0.0,
) -> ThreeSigmaObservation:
    """Measure what the 3-sigma gate does on a field with no response in it.

    The field is pure additive Gaussian noise plus an optional contamination
    spike set, sampled on a lattice and pushed through the production
    ``multiscale_zscore``. Everything after that -- the mask, the labelling, the
    ``min_size`` filter, the multiscale persistence filter -- is production code
    at production values.
    """
    cfg = AnalysisConfig()
    use_scales = scales if scales is not None else cfg.scales
    use_min_size = min_size if min_size is not None else cfg.min_size
    rng = np.random.default_rng(seed)
    signal = rng.normal(0.0, 1.0, size=(rows, cols))
    n_spikes = int(round(contaminating_fraction * rows * cols))
    if n_spikes:
        signal = signal + contamination_field(
            (rows, cols),
            n_spikes=n_spikes,
            amplitude=contaminating_amplitude,
            seed=seed + 1,
        )
    grid = _grid_from_signal(signal, rows, cols)
    z, persistence, _residual = multiscale_zscore(grid, scales=use_scales)
    finite = np.isfinite(z)
    exceeding = finite & (np.abs(z) >= threshold)
    labels, n_raw = ndimage.label(exceeding, structure=ndimage.generate_binary_structure(2, 2))
    # The production persistence filter, reproduced: a component survives when
    # its best cell reaches |z| >= 2 on at least `min_persistence` of the
    # scales. Reported as its own count so its effect is visible.
    kept = 0
    for comp_id in range(1, n_raw + 1):
        cells = persistence[labels == comp_id]
        cells = cells[np.isfinite(cells)]
        if cells.size and float(np.max(cells)) >= 0.5:
            kept += 1
    if use_min_size > 1 and n_raw:
        sizes = ndimage.sum(exceeding, labels, index=range(1, n_raw + 1))
        n_size_survivors = sum(1 for size in np.atleast_1d(sizes) if size >= use_min_size)
    else:
        n_size_survivors = int(n_raw)
    per_scale: dict[str, Any] = {}
    for size in use_scales:
        odd = size if size % 2 == 1 else size + 1
        if min(rows, cols) < odd:
            continue
        single = _single_scale_zscore(signal, odd)
        nominal = gaussian_two_sided_tail(threshold)
        measured = float(np.mean(np.isfinite(single) & (np.abs(single) >= threshold)))
        per_scale[f"scale{odd}"] = {
            "nominal_cell_rate": round(nominal, 8),
            "measured_cell_rate": round(measured, 8),
            "ratio": round(measured / nominal, 4) if nominal > 0 else None,
        }
    n_cells = int(np.count_nonzero(finite))
    n_exceeding = int(np.count_nonzero(exceeding))
    nominal_rate = gaussian_two_sided_tail(threshold)
    measured_rate = n_exceeding / n_cells if n_cells else 0.0
    return ThreeSigmaObservation(
        threshold=float(threshold),
        rows=rows,
        cols=cols,
        n_cells=n_cells,
        n_exceeding=n_exceeding,
        n_regions=int(n_raw),
        n_regions_ge_min_size=int(min(kept, n_size_survivors)),
        morans_i=morans_i_lag1(z),
        effective_sample_size=effective_sample_size(z),
        nominal_cell_rate=nominal_rate,
        measured_cell_rate=measured_rate,
        multiplicity_factor=(measured_rate / nominal_rate if nominal_rate > 0 else float("inf")),
        per_cell=per_scale,
    )


def _grid_from_signal(signal: np.ndarray[Any, Any], rows: int, cols: int) -> Any:
    from ...core.grid import Grid2D

    pitch = 1.0
    return Grid2D(
        x_centers=(np.arange(cols, dtype=float) + 0.5) * pitch,
        y_centers=(np.arange(rows, dtype=float) + 0.5) * pitch,
        signal=np.asarray(signal, dtype=float),
        depth=np.full((rows, cols), 12.0, dtype=float),
        counts=np.ones((rows, cols), dtype=int),
    )


def _single_scale_zscore(signal: np.ndarray[Any, Any], size: int) -> np.ndarray[Any, Any]:
    """The z-field one median-filter scale produces, for the per-scale rates.

    ``multiscale_zscore`` keeps the max over scales, so the per-scale rate has
    to be measured on a single scale to be attributable; that is what this is.
    """
    from ...core.background import remove_background

    grid = _grid_from_signal(signal, *signal.shape)
    residual = remove_background(grid, method="median", size=size)
    return robust_zscore(residual)


def three_sigma_characterization(
    *,
    thresholds: Sequence[float] = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0),
    rows: int = 64,
    cols: int = 64,
    seeds: Sequence[int] = (0, 1, 2, 3, 4, 5, 6, 7),
    contaminating_fractions: Sequence[float] = (0.0, 0.005, 0.02),
    contaminating_amplitude: float = 60.0,
) -> dict[str, Any]:
    """The 3-sigma sweep, with every named source of departure measured.

    Swept over threshold, repeated over independent noise draws, and repeated
    again with injected contamination -- because "3 sigma" means something
    different on a clean Gaussian field than on a field with dust in it, and the
    difference is one of the reasons the number cannot be read as a significance
    level.
    """
    rows_out: list[dict[str, Any]] = []
    for fraction in contaminating_fractions:
        for threshold in thresholds:
            for seed in seeds:
                observation = three_sigma_observation(
                    threshold=threshold,
                    rows=rows,
                    cols=cols,
                    seed=seed,
                    contaminating_fraction=fraction,
                    contaminating_amplitude=contaminating_amplitude,
                )
                row = observation.to_dict()
                row["contaminating_fraction"] = fraction
                row["seed"] = seed
                rows_out.append(row)
    production = AnalysisConfig().threshold
    by_contamination: dict[str, Any] = {}
    for fraction in contaminating_fractions:
        subset = [
            r
            for r in rows_out
            if r["threshold"] == production and r["contaminating_fraction"] == fraction
        ]
        if not subset:
            continue
        by_contamination[f"{fraction:g}"] = {
            "mean_measured_cell_rate": round(
                float(np.mean([r["measured_cell_rate"] for r in subset])), 8
            ),
            "mean_multiplicity_factor": round(
                float(np.mean([r["multiplicity_factor"] for r in subset])), 4
            ),
            "mean_regions_per_field": round(float(np.mean([r["n_regions"] for r in subset])), 4),
            "mean_surviving_regions_per_field": round(
                float(np.mean([r["n_regions_ge_min_size"] for r in subset])), 4
            ),
            "mean_effective_sample_size": round(
                float(np.mean([r["effective_sample_size"] for r in subset])), 2
            ),
        }
    per_threshold: dict[str, Any] = {}
    for threshold in thresholds:
        subset = [
            r
            for r in rows_out
            if r["threshold"] == threshold and r["contaminating_fraction"] == 0.0
        ]
        if not subset:
            continue
        per_threshold[f"{threshold:g}"] = {
            "nominal_cell_rate": round(float(np.mean([r["nominal_cell_rate"] for r in subset])), 8),
            "mean_measured_cell_rate": round(
                float(np.mean([r["measured_cell_rate"] for r in subset])), 8
            ),
            "mean_multiplicity_factor": round(
                float(np.mean([r["multiplicity_factor"] for r in subset])), 4
            ),
            "mean_regions_per_field": round(float(np.mean([r["n_regions"] for r in subset])), 4),
            "mean_surviving_regions_per_field": round(
                float(np.mean([r["n_regions_ge_min_size"] for r in subset])), 4
            ),
        }
    return {
        "production_threshold": production,
        "n_observations": len(rows_out),
        "grid_cells": rows * cols,
        "n_scales": len(AnalysisConfig().scales),
        "per_threshold_clean_field": per_threshold,
        "per_contamination_at_production": by_contamination,
        "observed_rows": rows_out,
        "interpretation": (
            "The nominal per-cell rate 2*Phi(-t) assumes independent standard-normal "
            "z values. The measured rate departs from it by the product of three "
            "measurable factors: the max over four correlated scale fields, the "
            "spatial correlation the median filter induces (reported as lag-1 "
            "Moran's I and the effective sample size it implies), and the "
            "heavy-tailed contamination a real field carries. threshold=3.0 is a "
            "conventional robust-z multiple. It is not a 0.27% false-positive rate "
            "and must not be reported as a significance level."
        ),
    }


def threshold_false_positive_count(
    *,
    threshold: float,
    rows: int = 128,
    cols: int = 128,
    seeds: Sequence[int] = tuple(range(12)),
) -> dict[str, Any]:
    """False positives a *user* would see: surviving regions on a target-free field.

    Distinct from the per-cell rate on purpose. The per-cell rate is the
    detector's interior; the number of surviving components is what reaches a
    report, and it is the number whose field-performance implication anybody would
    want to quote.

    The default grid is 128x128 because the two downstream filters -- the
    ``min_size`` size filter and the multiscale persistence filter -- reject every
    excursion on a smaller field. That is a measured fact about where the surviving
    count starts to be non-zero, not a convenient choice, and the field size is in
    the output so the figure is never quoted without it.
    """
    counts = []
    per_field = []
    for seed in seeds:
        observation = three_sigma_observation(threshold=threshold, rows=rows, cols=cols, seed=seed)
        counts.append(observation.n_regions_ge_min_size)
        per_field.append({
            "seed": seed,
            "n_regions": observation.n_regions,
            "n_surviving": observation.n_regions_ge_min_size,
        })
    return {
        "threshold": threshold,
        "rows": rows,
        "cols": cols,
        "n_fields": len(seeds),
        "mean_false_positive_components_per_field": round(float(np.mean(counts)), 4),
        "max_false_positive_components_per_field": int(max(counts)),
        "n_fields_with_zero": int(sum(1 for c in counts if c == 0)),
        "per_field": per_field,
    }


# ---------------------------------------------------------------------------
# Phase H -- the evidence / quality / screening chain
# ---------------------------------------------------------------------------


#: The two domains the chain's scalars occupy.
DOMAIN_UNIT_INTERVAL = "unit_interval"
DOMAIN_NON_NEGATIVE = "non_negative"


@dataclass(frozen=True)
class ThresholdSpec:
    """One scalar in the gate chain, and the decision it drives.

    ``domain`` states the range the parameter is allowed to occupy, so the sweep
    can stay inside it. Without it a sweep of a unit-interval score by a factor of
    two asks the production validator for a value of 1.4, and the resulting
    ``ValueError`` says nothing about the parameter. Clamping instead of skipping
    would be worse: it would create duplicate rows whose two names denote the same
    value, and the duplicate would be counted as a second observation.
    """

    spec_id: str
    value: float
    comparison: str
    stage: str
    production_site: str
    applies_to: str
    original_derivation: str
    domain: str = DOMAIN_UNIT_INTERVAL
    #: Whether a one-factor sweep can actually perturb this scalar. ``True`` for
    #: the ones that live in a config object the harness can override, ``False``
    #: for the ones written as inline literals at their comparison site.
    #:
    #: The distinction is load-bearing and is reported rather than absorbed into
    #: "inert". A scalar that cannot be swept has not been shown to be
    #: unimportant; it has been shown to be *not reachable as a parameter*, which
    #: is a different finding and an actionable one: promoting it to a named
    #: constant is the prerequisite for characterizing it at all.
    sweepable: bool = True

    def __post_init__(self) -> None:
        if self.comparison not in {"<", "<=", ">", ">="}:
            raise ValueError(
                f"{self.spec_id}: comparison {self.comparison!r} is not one of <, <=, >, >="
            )
        if self.domain not in (DOMAIN_UNIT_INTERVAL, DOMAIN_NON_NEGATIVE):
            raise ValueError(f"{self.spec_id}: unknown domain {self.domain!r}")
        if not self.admits(float(self.value)):
            raise ValueError(
                f"{self.spec_id}: production value {self.value} is outside its own "
                f"domain {self.domain}"
            )
        for name in ("stage", "production_site", "applies_to", "original_derivation"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{self.spec_id}: {name} must not be empty")

    def admits(self, value: float) -> bool:
        if self.domain == DOMAIN_UNIT_INTERVAL:
            return 0.0 <= value <= 1.0
        if self.domain == DOMAIN_NON_NEGATIVE:
            return value >= 0.0
        return True

    @property
    def source_path(self) -> str:
        """The module path from ``production_site``, without the line or the note.

        The site string is written for a human ("path:line (what it is called)"),
        so the machine-readable parts are recovered here rather than by every
        consumer re-parsing it -- a consumer that guessed the format would silently
        stop checking.
        """
        return self.production_site.split(":", 1)[0].strip()

    @property
    def source_line(self) -> int | None:
        """The line number from ``production_site``, or ``None`` when absent."""
        head = self.production_site.split("(", 1)[0]
        parts = head.split(":", 1)
        if len(parts) < 2:
            return None
        digits = "".join(ch for ch in parts[1] if ch.isdigit())
        return int(digits) if digits else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "value": self.value,
            "comparison": self.comparison,
            "stage": self.stage,
            "production_site": self.production_site,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "applies_to": self.applies_to,
            "original_derivation": self.original_derivation,
            "domain": self.domain,
            "sweepable": self.sweepable,
        }


#: The scalars in the chain, in the order the chain reads them. Stage names match
#: the dependency graph so a row can be traced to the level it sits at.
GATE_CHAIN_SPECS: tuple[ThresholdSpec, ...] = (
    ThresholdSpec(
        spec_id="geometry.band",
        value=0.40,
        comparison="<",
        stage="raw metrics -> geometry quality",
        production_site="groundscan/gates/quality.py:271 (weak-geometry flag)",
        applies_to="geometry_quality",
        original_derivation=(
            "set during the v0.2 synthetic benchmark; never derived from field data"
        ),
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="geometry.non_metric_penalty",
        value=0.50,
        comparison="<",
        stage="raw metrics -> geometry quality",
        production_site="groundscan/gates/quality.py:234",
        applies_to="geometry_quality when metric_geometry_reliable is false",
        original_derivation="penalty policy; no independent derivation recorded",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="evidence.min_support",
        value=0.50,
        comparison="<",
        stage="geometry quality -> evidence",
        production_site="groundscan/core/evidence.py:35 (EvidenceModelConfig.min_support)",
        applies_to="best hypothesis support",
        original_derivation=(
            "set during the v0.2 synthetic benchmark; the unknown map's intercept "
            "(0.58) is a sibling of the same choice"
        ),
    ),
    ThresholdSpec(
        spec_id="evidence.min_margin",
        value=0.02,
        comparison="<",
        stage="geometry quality -> evidence",
        production_site="groundscan/core/evidence.py:36 (EvidenceModelConfig.min_margin)",
        applies_to="best minus runner-up support",
        original_derivation=(
            "set during the v0.2 synthetic benchmark; characterized as redundant with "
            "min_support on the dominant runner-up branch"
        ),
    ),
    ThresholdSpec(
        spec_id="classify.hypothesis_min_margin",
        value=0.04,
        comparison="<",
        stage="geometry quality -> evidence",
        production_site="groundscan/core/classify.py:69 (ClassificationConfig)",
        applies_to="cavity-like vs tunnel-like final margin only",
        original_derivation=(
            "a second, different margin on a different score pair; not the same "
            "quantity as evidence.min_margin and never combined with it here"
        ),
    ),
    ThresholdSpec(
        spec_id="screening.primary_threshold",
        value=0.70,
        comparison="<",
        stage="evidence -> screening",
        production_site="groundscan/gates/screening.py:27 (ScreeningPolicy)",
        applies_to="screening_score",
        original_derivation=(
            "selected on the calibration portion of the deterministic v0.2.7 "
            "synthetic benchmark, then evaluated unchanged on the holdout portion"
        ),
    ),
    ThresholdSpec(
        spec_id="screening.rescue_lower",
        value=0.65,
        comparison="<",
        stage="evidence -> screening",
        production_site="groundscan/gates/screening.py:29 (ScreeningPolicy)",
        applies_to="screening_score inside the rescue band",
        original_derivation="same synthetic calibration split as the primary band",
    ),
    ThresholdSpec(
        spec_id="screening.rescue_min_persistence",
        value=0.50,
        comparison="<",
        stage="evidence -> screening",
        production_site="groundscan/gates/screening.py:31 (ScreeningPolicy)",
        applies_to="multiscale_persistence inside the rescue band",
        original_derivation="same synthetic calibration split as the primary band",
    ),
    ThresholdSpec(
        spec_id="screening.rescue_min_anomaly",
        value=4.5,
        comparison="<",
        stage="evidence -> screening",
        production_site="groundscan/gates/screening.py:34 (ScreeningPolicy)",
        applies_to="anomaly_score inside the rescue band",
        original_derivation="same synthetic calibration split as the primary band",
        domain=DOMAIN_NON_NEGATIVE,
    ),
    ThresholdSpec(
        spec_id="quality.band_insufficient",
        value=0.40,
        comparison="<",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:302 (insufficient-evidence)",
        applies_to="quality_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.band_review",
        value=0.65,
        comparison="<",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:304 (review)",
        applies_to="quality_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.evidence_floor",
        value=0.30,
        comparison="<",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:302 (insufficient-evidence)",
        applies_to="evidence_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.persistence_penalty",
        value=0.34,
        comparison="<",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:255",
        applies_to="multiscale_persistence",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.artifact_flag",
        value=0.50,
        comparison=">=",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:258 (artifact-concern flag)",
        applies_to="artifact_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.boundary_flag",
        value=0.45,
        comparison=">=",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:260 (boundary-contact flag)",
        applies_to="boundary_contact_ratio",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.artifact_status",
        value=0.70,
        comparison=">=",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:296 (artifact-concern status)",
        applies_to="artifact_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
    ThresholdSpec(
        spec_id="quality.depth_penalty",
        value=0.40,
        comparison="<",
        stage="screening -> review status",
        production_site="groundscan/gates/quality.py:265 (unstable-depth)",
        applies_to="depth_stability_score",
        original_derivation="v0.2 synthetic benchmark",
        sweepable=False,
    ),
)

#: Multipliers applied to each spec when sweeping. Asymmetric on purpose: bands
#: are usually moved down as often as up, and a symmetric sweep would understate
#: the sensitivity of a band that sits near the top of its population.
SWEEP_MULTIPLIERS: tuple[float, ...] = (0.5, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0)


def _evidence_config_with(value: float, spec_id: str) -> EvidenceModelConfig:
    cfg = DEFAULT_EVIDENCE_MODEL_CONFIG
    if spec_id == "evidence.min_support":
        return EvidenceModelConfig(
            min_support=value,
            min_margin=cfg.min_margin,
            unknown_floor=cfg.unknown_floor,
            linear_metal_min_line_support=cfg.linear_metal_min_line_support,
            linear_metal_min_linearity=cfg.linear_metal_min_linearity,
            linear_metal_min_axial=cfg.linear_metal_min_axial,
        )
    if spec_id == "evidence.min_margin":
        return EvidenceModelConfig(
            min_support=cfg.min_support,
            min_margin=value,
            unknown_floor=cfg.unknown_floor,
            linear_metal_min_line_support=cfg.linear_metal_min_line_support,
            linear_metal_min_linearity=cfg.linear_metal_min_linearity,
            linear_metal_min_axial=cfg.linear_metal_min_axial,
        )
    return cfg


def _screening_policy_with(value: float, spec_id: str) -> ScreeningPolicy:
    policy = DEFAULT_SCREENING_POLICY
    overrides: dict[str, Any] = {}
    if spec_id == "screening.primary_threshold":
        overrides["primary_threshold"] = value
    elif spec_id == "screening.rescue_lower":
        overrides["rescue_lower"] = min(value, policy.rescue_upper)
    elif spec_id == "screening.rescue_min_persistence":
        overrides["rescue_min_persistence"] = min(value, 1.0)
    elif spec_id == "screening.rescue_min_anomaly":
        overrides["rescue_min_anomaly"] = max(value, 0.0)
    return ScreeningPolicy(**{**policy.__dict__, **overrides})


def _classification_config_with(value: float, spec_id: str) -> ClassificationConfig:
    """``ClassificationConfig`` with one field replaced, or the default.

    Inert, and recorded as such: ``classify_candidate`` takes this object but
    ignores it -- every field is retired (see ``core/classify.py`` and
    ``docs/adr/011``), so sweeping ``hypothesis_min_margin`` re-runs the
    classifier without being able to change any output. The spec is RETIRED in
    the calibration decision table for exactly that reason. Kept here so the
    spec can still be constructed rather than special-cased away.
    """
    if spec_id != "classify.hypothesis_min_margin":
        return ClassificationConfig()
    config = ClassificationConfig()
    return replace(config, hypothesis_min_margin=float(value))


@dataclass(frozen=True)
class PopulationBaseline:
    """The three gate outcomes, recomputed at production values.

    Recomputed rather than read off the candidate, for two reasons that are both
    measured rather than assumed:

    * ``pattern_hypothesis`` is set by ``core.classify.classify_candidate``, which
      is *not* ``core.evidence.classify_from_evidence`` -- the classifier applies
      its own rules on top of the evidence model, and the dipole path additionally
      sets a ``dipolar-response`` label the evidence model never produces.
      Comparing a perturbed evidence selection against the stored hypothesis would
      therefore report a difference that has nothing to do with the perturbation.
    * ``review_status`` is **not idempotent** for dipole-merged candidates:
      re-running ``assess_candidate_quality`` on one replaces
      ``review-decomposition`` with ``review``, because the status is keyed on
      ``separation_status == "decomposed-consensus"`` and the dipole path writes
      ``merged-dipole``. Three of 95 candidates in the measured population do this.
      The count is reported as ``n_non_idempotent_review_status`` so the effect is
      on the record rather than showing up as a phantom sensitivity.

    ``screening_selection_reason`` is empty on every candidate in this population,
    so retention is also recomputed rather than read.
    """

    evidence_selection: str
    classification: str
    review_status: str
    screening_retained: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_selection": self.evidence_selection,
            "classification": self.classification,
            "review_status": self.review_status,
            "screening_retained": self.screening_retained,
        }


def population_baseline(
    members: Sequence[PopulationMember],
) -> tuple[tuple[PopulationBaseline, ...], dict[str, Any]]:
    """Recompute the four outcomes at production values, plus the exceptions found."""
    out: list[PopulationBaseline] = []
    non_idempotent = 0
    non_idempotent_ids: list[str] = []
    empty_screening_field = 0
    for member in members:
        candidate = member.candidate
        assessed = assess_candidate_quality(candidate)
        if assessed.review_status != str(candidate.review_status):
            non_idempotent += 1
            if len(non_idempotent_ids) < 5:
                non_idempotent_ids.append(f"{member.source_id}#{candidate.id}")
        if not str(candidate.screening_selection_reason or ""):
            empty_screening_field += 1
        out.append(
            PopulationBaseline(
                evidence_selection=classify_from_evidence(candidate)[0],
                classification=str(
                    classify_candidate(candidate, config=ClassificationConfig()).pattern_hypothesis
                ),
                review_status=assessed.review_status,
                screening_retained=bool(
                    screen_candidates([assessed], policy=DEFAULT_SCREENING_POLICY)
                ),
            )
        )
    return tuple(out), {
        "n_non_idempotent_review_status": non_idempotent,
        "non_idempotent_examples": non_idempotent_ids,
        "n_empty_screening_selection_reason": empty_screening_field,
        "note": (
            "assess_candidate_quality is a pure transform for every candidate except a "
            "dipole-merged one, whose review_status is keyed on a separation_status the "
            "dipole path does not write. The recomputed value is used as the baseline "
            "because it is the one a sweep can vary; the divergence is counted here rather "
            "than being allowed to appear as a sensitivity."
        ),
    }


def evidence_quality_sensitivity_matrix(
    members: Sequence[PopulationMember],
    *,
    specs: Sequence[ThresholdSpec] = GATE_CHAIN_SPECS,
    multipliers: Sequence[float] = SWEEP_MULTIPLIERS,
    deltas: Sequence[float] = (-0.05, -0.02, -0.01, 0.0, 0.01, 0.02, 0.05),
) -> dict[str, Any]:
    """One factor at a time down the whole gate chain.

    For each spec and each swept value the population is re-evaluated and three
    outcomes counted: the evidence selection, the ``review_status`` and the
    screening retention. Each is compared against the *recomputed* production
    baseline (:func:`population_baseline`) rather than against the candidate's
    stored fields -- see that class for why the stored fields cannot serve.

    The point is not which value looks best -- no value is selected here -- but
    which scalars the outputs are *sensitive* to, and which are inert. An inert
    scalar is reported as inert; it is not reported as validated.
    """
    baseline, exceptions = population_baseline(members)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        for value in _swept_values(spec, multipliers, deltas):
            outcome = _evaluate_population(
                members,
                baseline,
                _evidence_config_with(value, spec.spec_id),
                _screening_policy_with(value, spec.spec_id),
                _classification_config_with(value, spec.spec_id),
            )
            rows.append({
                "spec_id": spec.spec_id,
                "stage": spec.stage,
                "production_site": spec.production_site,
                "production_value": spec.value,
                "sweepable": spec.sweepable,
                "value": round(float(value), 6),
                "delta": round(float(value) - spec.value, 6),
                "relative": (round(float(value) / spec.value, 4) if spec.value else None),
                "is_production": abs(float(value) - spec.value) < 1e-12,
                "n_evidence_changed": outcome["n_evidence_changed"],
                "n_classification_changed": outcome["n_classification_changed"],
                "n_review_status_changed": outcome["n_review_status_changed"],
                "n_screening_changed": outcome["n_screening_changed"],
                "n_any_changed": outcome["n_any_changed"],
            })
    per_spec: dict[str, Any] = {}
    for spec in specs:
        subset = [r for r in rows if r["spec_id"] == spec.spec_id]
        non_production = [r for r in subset if not r["is_production"]]
        max_changes = max((r["n_any_changed"] for r in non_production), default=0)
        per_spec[spec.spec_id] = {
            "stage": spec.stage,
            "production_site": spec.production_site,
            "source_path": spec.source_path,
            "source_line": spec.source_line,
            "applies_to": spec.applies_to,
            "domain": spec.domain,
            "production_value": spec.value,
            "sweepable": spec.sweepable,
            "sensitivity_status": ("swept" if spec.sweepable else "not-reachable-as-a-parameter"),
            "max_n_any_changed": max_changes,
            "is_inert": bool(spec.sweepable and max_changes == 0),
            "n_swept": len(subset),
            "rows": subset,
        }
    return {
        "population": population_summary(members),
        "baseline": {
            "n_evidence_selected": sum(1 for b in baseline if b.evidence_selection != "unknown"),
            "n_classified_non_unknown": sum(1 for b in baseline if b.classification != "unknown"),
            "n_review_status_non_insufficient": sum(
                1 for b in baseline if b.review_status != "insufficient-evidence"
            ),
            "n_screening_retained": sum(1 for b in baseline if b.screening_retained),
        },
        "baseline_exceptions": exceptions,
        "per_spec": per_spec,
        "n_inert_specs": sum(1 for v in per_spec.values() if v["sweepable"] and v["is_inert"]),
        "n_sweepable_specs": sum(1 for v in per_spec.values() if v["sweepable"]),
        "n_unsweepable_specs": sum(1 for v in per_spec.values() if not v["sweepable"]),
        "n_specs": len(per_spec),
        "all_rows": rows,
    }


def _swept_values(
    spec: ThresholdSpec, multipliers: Sequence[float], deltas: Sequence[float]
) -> list[float]:
    """Absolute values for one spec's sweep, deduplicated, sorted, in-domain.

    Multiplicative moves suit a value away from zero; additive moves suit a value
    near zero. Both are offered, out-of-domain values are dropped rather than
    clamped, and duplicates collapse so no row is counted twice.
    """
    values: set[float] = set()
    for multiplier in multipliers:
        values.add(float(spec.value) * float(multiplier))
    for delta in deltas:
        values.add(float(spec.value) + float(delta))
    out: list[float] = []
    for value in sorted(values):
        if not spec.admits(value):
            continue
        out.append(round(value, 9))
    return out


def _evaluate_population(
    members: Sequence[PopulationMember],
    baseline: Sequence[PopulationBaseline],
    evidence_config: EvidenceModelConfig,
    policy: ScreeningPolicy,
    classification_config: ClassificationConfig,
) -> dict[str, int]:
    """Recompute the four gate outcomes under overrides and diff against baseline.

    Each candidate is evaluated once and the four differences are taken from the
    same evaluation, so the sub-counts cannot describe different worlds.
    ``classify_candidate`` returns a new candidate, so the population is not
    mutated and the re-run is safe.
    """
    n_evidence = 0
    n_review = 0
    n_screening = 0
    n_classification = 0
    n_any = 0
    for member, base in zip(members, baseline, strict=True):
        candidate = member.candidate
        label = classify_from_evidence(candidate, config=evidence_config)[0]
        assessed = assess_candidate_quality(candidate)
        retained = bool(screen_candidates([assessed], policy=policy))
        classified = classify_candidate(candidate, config=classification_config)
        evidence_changed = label != base.evidence_selection
        review_changed = assessed.review_status != base.review_status
        screening_changed = retained != base.screening_retained
        classification_changed = str(classified.pattern_hypothesis) != base.classification
        n_evidence += int(evidence_changed)
        n_review += int(review_changed)
        n_screening += int(screening_changed)
        n_classification += int(classification_changed)
        n_any += int(
            evidence_changed or review_changed or screening_changed or classification_changed
        )
    return {
        "n_evidence_changed": n_evidence,
        "n_review_status_changed": n_review,
        "n_screening_changed": n_screening,
        "n_classification_changed": n_classification,
        "n_any_changed": n_any,
    }


# ---------------------------------------------------------------------------
# S02 / S03 distribution shift, measured
# ---------------------------------------------------------------------------


def solidity_distribution_shift(
    samples: Sequence[Any] | None = None,
    *,
    pitches: Sequence[float] = (0.25, 0.5, 1.0, 2.0, 10.0),
) -> dict[str, Any]:
    """Did S02 move the population the solidity bands were set against?

    The bands predate the metric's redefinition, so the question is not "is the
    current value right" but "what happened to the numbers those bands were
    chosen from". Both formulas are evaluated on the same exact cell sets, at
    several pitches, using the two implementations that already exist in the
    repository: the corrected quantity via the S02 exact oracle, and the retired
    one via the S02 shadow's ``legacy_solidity``.

    The retired formula is a shadow throughout: nothing here feeds it back into
    production, and no band is derived from it.
    """
    from ...diagnostics.shadow import legacy_solidity
    from .datasets import analytic_shape_catalogue, exact_solidity_fraction
    from .geometry import SOLIDITY_BANDS

    catalogue = tuple(samples) if samples is not None else analytic_shape_catalogue()
    current: list[float] = []
    legacy_by_pitch: dict[float, list[float]] = {p: [] for p in pitches}
    for sample in catalogue:
        current.append(float(exact_solidity_fraction(sample.cells)))
        rows = [r for r, _ in sample.cells]
        cols = [c for _, c in sample.cells]
        for pitch in pitches:
            legacy_by_pitch[pitch].append(
                legacy_solidity(np.asarray(rows), np.asarray(cols), pitch, pitch)
            )

    def _stats(values: Sequence[float]) -> dict[str, float]:
        arr = np.array([v for v in values if np.isfinite(v)], dtype=float)
        if arr.size == 0:
            return {"n": 0}
        return {
            "n": int(arr.size),
            "min": round(float(arr.min()), 8),
            "median": round(float(np.median(arr)), 8),
            "max": round(float(arr.max()), 8),
        }

    band_impact = {
        band.band_id: {
            "band": band.value,
            "comparison": band.comparison,
            "n_crossed_current": int(sum(1 for v in current if band.crossed_by(v))),
            "n_crossed_legacy_at_pitch_1": int(
                sum(1 for v in legacy_by_pitch[1.0] if band.crossed_by(v))
            ),
        }
        for band in SOLIDITY_BANDS
    }
    # The decisive measurement: the retired value is not a shape ratio, so it
    # changes when the survey is re-expressed at a different pitch. The corrected
    # value does not.
    pitch_profile: dict[str, Any] = {}
    for pitch in pitches:
        values = np.array(legacy_by_pitch[pitch], dtype=float)
        pitch_profile[f"pitch_{pitch:g}"] = _stats(values)
    return {
        "n_shapes": len(catalogue),
        "corrected_metric": _stats(current),
        "retired_metric_by_pitch": pitch_profile,
        "retired_metric_is_pitch_invariant": all(
            pitch_profile[f"pitch_{pitches[0]:g}"] == pitch_profile[f"pitch_{pitches[-1]:g}"]
            for p in pitches
        ),
        "band_impact": band_impact,
        "note": (
            "The retired formula divided a cell COUNT by a hull AREA, so its value "
            "carried the dimension 1/area and moved by the square of any change of "
            "pitch. A band on a 1/area quantity is not a shape statement at all, so "
            "'recalibrate the bands against the retired distribution' has no well "
            "defined meaning: the distribution was a function of the survey's units. "
            "The pipeline-side S02 comparison is already carried by the shadow "
            "ledger (diagnostics.shadow.measure_solidity) and is not duplicated here."
        ),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def contamination_sensitivity(
    *,
    fractions: Sequence[float] = (0.0, 0.001, 0.005, 0.02, 0.05),
    amplitude: float = 60.0,
    threshold: float | None = None,
    rows: int = 64,
    cols: int = 64,
    seeds: Sequence[int] = (0, 1, 2, 3),
) -> dict[str, Any]:
    """How the 3-sigma gate responds to dust, measured at each contamination level.

    A robust scale is high-breakdown, so contamination should not inflate the
    denominator much; what it *can* do is create regions. The measurement keeps
    those two effects apart, which is why both the measured cell rate and the
    surviving-region count are reported.
    """
    tau = AnalysisConfig().threshold if threshold is None else float(threshold)
    out: dict[str, Any] = {"threshold": tau, "n_seeds": len(seeds), "per_fraction": {}}
    for fraction in fractions:
        rates: list[float] = []
        regions: list[int] = []
        surviving: list[int] = []
        for seed in seeds:
            observation = three_sigma_observation(
                threshold=tau,
                rows=rows,
                cols=cols,
                seed=seed,
                contaminating_fraction=fraction,
                contaminating_amplitude=amplitude,
            )
            rates.append(observation.measured_cell_rate)
            regions.append(observation.n_regions)
            surviving.append(observation.n_regions_ge_min_size)
        out["per_fraction"][f"{fraction:g}"] = {
            "mean_measured_cell_rate": round(float(np.mean(rates)), 8),
            "mean_regions": round(float(np.mean(regions)), 4),
            "mean_surviving_regions": round(float(np.mean(surviving)), 4),
        }
    out["contamination_policy_reference"] = {
        "sigmas": CONTAMINATION_SIGMAS,
        "fraction": CONTAMINATION_FRACTION,
        "applies_to": (
            "the scale estimator's own contamination flag, not the 3-sigma gate; "
            "reported here because it is the only contamination constant in the "
            "detector and its 4.0/0.05 pair is itself a policy choice"
        ),
    }
    return out

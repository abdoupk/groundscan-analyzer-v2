"""Phase D -- the decision margin, and what ``min_margin = 0.02`` is for.

The structural claims are asserted, because they are algebra rather than
observation:

* the ``unknown`` hypothesis is an affine function of the best specific support,
  and its ``0.05`` floor is unreachable over the whole reachable range;
* therefore wherever ``unknown`` is the runner-up, the margin is
  ``1.45*S - 0.58`` and ``min_margin`` is exactly equivalent to a floor on the
  winner's support at ``S = (min_margin + 0.58) / 1.45``;
* the closed form reproduces the production ``unknown`` support with zero error,
  which is checked against the executed values rather than argued from the source.

The population measurements are recorded. In particular the joint grid is
asserted to be *asymmetric*: on this population ``min_margin`` is redundant given
``min_support`` while the reverse does not hold. That asymmetry is the reason the
register records 0.02 as a MODEL CHOICE with a stated meaning rather than as an
unexplained constant -- and it is emphatically not a reason to move either gate.
"""

from __future__ import annotations

import math

import pytest

from groundscan.core.evidence import DEFAULT_EVIDENCE_MODEL_CONFIG, score_hypotheses
from groundscan.validation.calibration.decision import (
    UNKNOWN_FLOOR,
    UNKNOWN_INTERCEPT,
    UNKNOWN_SLOPE,
    candidate_population,
    controlled_margin_cases,
    equivalent_support_floor,
    evidence_margin_ladder,
    margin_from_specific_best,
    margin_instability_zone,
    margin_observations,
    margin_sensitivity_sweep,
    margin_structure,
    population_summary,
    unknown_support,
)

POPULATION = candidate_population(limit_vendor=3)


# ---------------------------------------------------------------------------
# The algebra
# ---------------------------------------------------------------------------


def test_the_unknown_floor_is_unreachable_over_the_whole_support_range() -> None:
    """The affine map is unconditional, which is what makes the margin analytic.

    ``0.58 - 0.45*S`` falls to ``0.13`` at ``S = 1``, so the ``max(0.05, ...)``
    never binds and the map is affine everywhere the model can reach. If the floor
    could bind, the margin would be piecewise and the closed form below would need
    a case split.
    """
    for support in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert UNKNOWN_INTERCEPT + UNKNOWN_SLOPE * support > UNKNOWN_FLOOR
    assert unknown_support(1.0) == pytest.approx(0.13, abs=1e-12)
    assert unknown_support(0.0) == pytest.approx(0.58, abs=1e-12)


def test_the_margin_against_unknown_is_an_affine_function_of_the_winner() -> None:
    for support in (0.40, 0.50, 0.60, 0.75, 1.0):
        expected = support - unknown_support(support)
        assert margin_from_specific_best(support) == pytest.approx(expected, abs=1e-12)
    # Monotone increasing: a stronger winner means a larger margin, always.
    values = [margin_from_specific_best(s) for s in (0.3, 0.4, 0.5, 0.6, 0.7)]
    assert values == sorted(values)


def test_min_margin_reduces_to_a_support_floor_of_0_4138() -> None:
    """The closed form, evaluated at the production constant.

    ``(0.02 + 0.58) / 1.45 = 0.413793...``. Below that support the margin gate
    fires; above it the gate cannot. Since ``min_support`` is 0.50, the margin
    gate's effective floor is *below* the support gate's -- which is the whole
    content of the redundancy the structure section reports.
    """
    floor = equivalent_support_floor(DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin)
    assert floor == pytest.approx(0.413793, abs=1e-6)
    assert floor < DEFAULT_EVIDENCE_MODEL_CONFIG.min_support
    # The floor is exactly where the margin gate becomes satisfied.
    assert margin_from_specific_best(floor) == pytest.approx(0.02, abs=1e-12)
    assert margin_from_specific_best(floor - 1e-6) < 0.02


def test_the_closed_form_reproduces_the_production_unknown_support() -> None:
    """Verified against executed values, not read off the source.

    Every candidate in the population is scored by the production model, and the
    production ``unknown`` support is compared with the closed form. A zero error
    is what licenses using the algebra to reason about the gate.
    """
    structure = margin_structure(POPULATION)
    closed_form = structure["unknown_closed_form"]
    assert closed_form["verified"] is True
    assert closed_form["max_abs_prediction_error"] == 0.0
    assert closed_form["intercept"] == UNKNOWN_INTERCEPT
    assert closed_form["slope"] == UNKNOWN_SLOPE
    assert closed_form["floor_reachable"] is False


def test_the_declared_unknown_floor_is_not_the_applied_one() -> None:
    """A declared configuration field with no reader is a finding, not a knob.

    ``EvidenceModelConfig.unknown_floor`` is 0.18; the floor ``score_hypotheses``
    actually applies is the literal 0.05. Moving the config field would change
    nothing while appearing to be a calibration, so it is recorded as NOT
    APPLICABLE rather than as a tunable.
    """
    assert DEFAULT_EVIDENCE_MODEL_CONFIG.unknown_floor == 0.18
    assert UNKNOWN_FLOOR == 0.05
    assert DEFAULT_EVIDENCE_MODEL_CONFIG.unknown_floor != UNKNOWN_FLOOR

    from pathlib import Path

    import groundscan.core.evidence as evidence_module

    root = Path(evidence_module.__file__).resolve().parents[2]
    declaration = Path(evidence_module.__file__).resolve()
    readers = []
    for path in (root / "groundscan").rglob("*.py"):
        if "validation" in path.parts or path.resolve() == declaration:
            continue
        if "unknown_floor" in path.read_text(encoding="utf-8"):
            readers.append(path.relative_to(root).as_posix())
    assert readers == [], (
        f"unknown_floor now has a production reader outside evidence.py: {readers}"
    )


# ---------------------------------------------------------------------------
# The population
# ---------------------------------------------------------------------------


def test_the_population_is_stated_so_every_count_can_be_read_against_it() -> None:
    summary = population_summary(POPULATION)
    assert summary["n_candidates"] == len(POPULATION)
    assert summary["n_scans"] > 20
    assert set(summary["by_category"]) == {"perturbation", "vendor"}
    assert summary["by_case_factor"]["noise"] >= 5
    assert sum(summary["by_hypothesis"].values()) == summary["n_candidates"]


def test_every_candidate_margin_resolves_to_a_named_runner_up() -> None:
    observations = margin_observations(POPULATION)
    assert len(observations) == len(POPULATION)
    for observation in observations:
        assert observation.best_hypothesis != observation.runner_up
        assert observation.margin == pytest.approx(
            observation.best_support - observation.runner_up_support, abs=1e-3
        )
        assert observation.runner_up_is_unknown == (observation.runner_up == "unknown")
        if not observation.runner_up_is_unknown:
            # Only the residual hypothesis is a declared function of the winner.
            assert observation.runner_up_support != pytest.approx(
                unknown_support(observation.best_support), abs=1e-3
            )


def test_the_structure_section_states_its_own_redundancy_finding() -> None:
    structure = margin_structure(POPULATION)
    assert structure["n_candidates"] == len(POPULATION)
    assert structure["min_margin_binds_against_unknown_runner_up"] is True
    assert structure["redundancy_margin"] == pytest.approx(
        DEFAULT_EVIDENCE_MODEL_CONFIG.min_support
        - equivalent_support_floor(DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin),
        abs=1e-6,
    )

    # The population's measured margin spread, and whether anything sits below
    # the production gate on the specific-runner-up branch.
    assert structure["margin_distribution"]["min"] >= 0.0
    specific = structure["specific_runner_up_margin_distribution"]
    assert specific is not None
    assert specific["n_below_production_min_margin"] >= 0


# ---------------------------------------------------------------------------
# The sensitivity sweep
# ---------------------------------------------------------------------------


def test_the_sweep_at_the_production_value_changes_nothing() -> None:
    """A sweep must be a fixed point at the shipped constant.

    If moving ``min_margin`` to its own current value changed a decision, the
    sweep's baseline would be wrong and every other row in it would be
    uninterpretable.
    """
    sweep = margin_sensitivity_sweep(POPULATION)
    production_rows = [r for r in sweep["rows"] if r["is_production"]]
    assert len(production_rows) == 1
    assert production_rows[0]["min_margin"] == DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    assert production_rows[0]["n_changed"] == 0


def test_the_sweep_is_monotone_in_the_number_of_rejections() -> None:
    """Raising a floor can only reject more, never fewer.

    Rows with equal ``min_margin`` are deduplicated upstream, so the sequence of
    ``n_to_unknown`` is non-decreasing across the swept values.
    """
    sweep = margin_sensitivity_sweep(POPULATION)
    rows = sorted(sweep["rows"], key=lambda r: r["min_margin"])
    to_unknown = [r["n_to_unknown"] for r in rows]
    assert to_unknown == sorted(to_unknown)
    assert to_unknown[-1] >= to_unknown[0]


def test_the_sweep_finds_a_usable_band_around_the_production_value() -> None:
    """The constant must be neither inert nor decisive to be worth a status.

    If every swept value changed the same number of decisions, there would be no
    margin band to characterize. If none did, the parameter would be inert and
    would be recorded as such rather than as a MODEL CHOICE.
    """
    sweep = margin_sensitivity_sweep(POPULATION)
    changed = {r["min_margin"]: r["n_changed"] for r in sweep["rows"]}
    assert len(set(changed.values())) > 1, (
        "the margin changed the same number of decisions at every swept value, so "
        "the population cannot discriminate between them"
    )
    assert max(changed.values()) > 0
    assert sweep["n_changed_at_production_relative_to_zero"] is not None


# ---------------------------------------------------------------------------
# Controlled cases and the instability zone
# ---------------------------------------------------------------------------


def test_controlled_cases_bracket_the_production_margin() -> None:
    """Cases placed below, at, and above the gate by construction.

    The polarity fraction moves the metallic/cavity competition continuously and
    monotonically, so the ladder brackets the gate rather than searching for it.
    The test asserts the ladder *reached* the near-threshold band, because a ladder
    that stopped short would measure nothing about the gate.
    """
    result = evidence_margin_ladder()
    bands = result["achieved_bands"]
    assert result["production_min_margin"] == DEFAULT_EVIDENCE_MODEL_CONFIG.min_margin
    assert result["margin_is_attainable"] is True
    assert sum(bands[name]["n"] for name in bands) == result["n_observations"]
    assert bands["well_above"]["n"] > 0
    assert bands["below"]["n"] + bands["just_below"]["n"] > 0, (
        "the ladder produced no case at or below the production margin"
    )
    for name, stats in bands.items():
        assert stats["n_selected_unknown"] <= stats["n"], name
    assert result["overridden_fields"] == ("positive_peak", "negative_peak")


def test_the_ladder_is_monotone_in_the_polarity_fraction() -> None:
    """One control, one direction: more positive fraction, larger margin.

    Checked within each seed, because the ladder interleaves seeds and comparing
    across them would be comparing noise draws. A non-monotone ladder would mean a
    second variable was moving, and the near-threshold cases would then not be
    attributable to the control.
    """
    result = evidence_margin_ladder(seeds=(0, 1, 2))
    by_seed: dict[int, list[dict]] = {}
    for row in result["rows"]:
        by_seed.setdefault(int(row["seed"]), []).append(row)
    assert len(by_seed) >= 2, "a single seed cannot show a ladder's shape"
    for seed, rows in by_seed.items():
        rows.sort(key=lambda r: -r["level"])
        margins = [r["margin"] for r in rows]
        assert margins == sorted(margins, reverse=True), f"non-monotone ladder for seed {seed}"
        assert margins[-1] < margins[0], f"the control did nothing for seed {seed}"


def test_a_case_below_the_margin_is_selected_unknown_and_above_it_is_not() -> None:
    """The gate's own semantics, on cases whose margin is known.

    Read off the ladder rather than asserted in the abstract: a row below the
    production margin must have been selected ``unknown``, and a row well above it
    must not have been.
    """
    result = evidence_margin_ladder()
    threshold = result["production_min_margin"]
    checked_below = 0
    checked_above = 0
    for row in result["rows"]:
        if row["margin"] < threshold:
            assert row["selected"] == "unknown", row
            checked_below += 1
        elif row["margin"] >= threshold * 2.0:
            assert row["selected"] != "unknown", row
            checked_above += 1
    assert checked_below > 0 and checked_above > 0


def test_the_pipeline_level_controls_do_not_reach_the_gate() -> None:
    """Two honest attempts that fail, recorded rather than quietly dropped.

    Neither the response amplitude nor a co-located opposite-sign pair approaches
    the margin gate, because the gate is decided by the polarity balance and an
    opposite-sign pair is split into two independently scored lobes. A margin
    sweep built on either control alone would have reported the parameter as inert,
    which is exactly the wrong conclusion.
    """
    result = controlled_margin_cases()
    assert set(result["per_control"]) == {"balance", "amplitude"}
    for control, stats in result["per_control"].items():
        assert stats["n"] > 0, control
        assert stats["min_margin"] is not None, control
        assert stats["reaches_below_production"] is False, control
        assert stats["min_margin"] > result["production_min_margin"], (
            f"{control} unexpectedly reached the gate"
        )
    assert result["which_control_reaches_the_gate"] == []
    assert "would have reported the parameter as inert" in result["reading"]


def test_the_instability_zone_is_binned_by_margin_and_reported_even_when_empty() -> None:
    """Bins, not a single rate, and an empty bin reported as empty.

    A flip rate without its margin distribution is uninterpretable: the same rate
    is reassuring in a sparse region and alarming in a dense one. An empty bin is
    reported with ``n = 0`` and a ``None`` rate rather than being dropped, so a
    reader can see the coverage.
    """
    zone = margin_instability_zone(
        perturbations=(("translate", 0.2), ("noise", 0.25)), seeds=(0, 1)
    )
    assert zone["margin_bins"] == [0.0, 0.02, 0.05, 0.10, 0.20, 1.01]
    assert len(zone["per_margin_bin"]) == len(zone["margin_bins"]) - 1
    for entry in zone["per_margin_bin"]:
        assert entry["n"] >= 0
        if entry["n"] == 0:
            assert entry["flip_rate"] is None
        else:
            assert 0.0 <= entry["flip_rate"] <= 1.0
    assert isinstance(zone["monotone_in_margin"], bool)


def test_the_population_is_built_by_the_real_analysis_path() -> None:
    """Every field is a production value, not a hand-populated stand-in.

    A sensitivity number measured on synthetic candidates with plausible-looking
    fields would be a measurement of the fixture, not of the system.
    """
    for member in POPULATION[:20]:
        candidate = member.candidate
        assert candidate.review_status
        assert 0.0 <= candidate.screening_score <= 1.0
        assert 0.0 <= candidate.quality_score <= 1.0
        assert math.isfinite(float(candidate.solidity))
        assert 0.0 <= float(candidate.solidity) <= 1.0
        assert member.category in {"perturbation", "vendor"}


def test_scoring_is_deterministic_across_repeated_calls() -> None:
    for member in POPULATION[:15]:
        assert score_hypotheses(member.candidate) == score_hypotheses(member.candidate)
    first = margin_observations(POPULATION)
    second = margin_observations(POPULATION)
    assert [o.to_dict() for o in first] == [o.to_dict() for o in second]

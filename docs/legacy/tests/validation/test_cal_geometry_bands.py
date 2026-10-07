"""Phases E and F -- post-S02 solidity bands, and the compactness estimator.

Two things are asserted here, and they are different in kind.

**Asserted** -- the metric's structural claims, because they are theorems with an
independent implementation behind them. The corrected solidity is pitch-free and
anisotropy-free to round-off; it equals the exact rational oracle on every
analytic shape; a convex cell set is exactly 1.0; and a corner-touching diagonal
run is 3/5 rather than the 1.0 the retired formula's degenerate branch reported.
Those are regression guards for S02 and they will fail loudly if the metric
changes.

**Recorded** -- the band census and the compactness matrix, plus the two
characterization findings that drive the register's statuses:

* the ``0.40`` weak-geometry band is not crossed by any solidity shift up to
  +/-0.10, and the compactness proxy cannot reject a thin shape at all;
* the compactness proxy is not scale-invariant, while the exact exposed-edge
  quotient is, and the difference is a measured size bias rather than a guess.

The band *decisions* are not pinned to single counts. Pinning them would make a
future, justified re-characterization look like a regression, and these are
measurements of a population rather than specifications for it.
"""

from __future__ import annotations

import pytest

from groundscan.validation.calibration import datasets as D
from groundscan.validation.calibration.geometry import (
    BAND_FRAGILITY_RADIUS,
    COMPACTNESS_CONSUMERS,
    GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
    SOLIDITY_BANDS,
    SQUARE_COMPACTNESS_TRUE,
    band_sensitivity,
    compactness_matrix,
    compactness_matrix_summary,
    compactness_scale_bias,
    compactness_thin_diagnostic,
    geometry_quality_weight_sweep,
    pitch_invariance,
    solidity_census,
    solidity_census_summary,
    verify_geometry_quality_reconstruction,
)

# ---------------------------------------------------------------------------
# Phase E -- the corrected solidity
# ---------------------------------------------------------------------------


def test_solidity_is_exactly_the_oracle_on_every_analytic_shape() -> None:
    rows = solidity_census()
    assert len(rows) >= 60
    for row in rows:
        assert row.solidity == pytest.approx(row.solidity_oracle, abs=1e-12), row.sample_id
        assert row.solidity_error == pytest.approx(0.0, abs=1e-12), row.sample_id


def test_solidity_is_pitch_invariant_to_round_off() -> None:
    """The S02 regression guard.

    The corrected definition divides the pitch out algebraically, so the metric is
    a function of the cell set alone. A deviation larger than round-off would mean
    the metric is not the dimensionless quantity its definition claims -- which is
    the S02 defect itself.
    """
    result = pitch_invariance()
    assert result["verified"] is True
    assert result["max_abs_deviation_overall"] < 1e-12
    pitches = {tuple(p) for p in result["pitches"]}
    assert (0.04, 0.04) in pitches, "a 25x rescaling must be swept"
    assert (0.5, 2.0) in pitches and (2.0, 0.5) in pitches, "anisotropy must be swept"
    for per_pitch in result["per_pitch"].values():
        assert per_pitch["max_abs_deviation"] < 1e-12


def test_a_convex_cell_set_is_exactly_solid_and_a_thin_one_is_not() -> None:
    for side in (1, 2, 5, 20, 50):
        assert D.production_shape_metrics(D.square(side)).solidity == 1.0
    # A 3-cell diagonal run: 3 occupied cells, 5 cell-regions of hull.
    assert D.production_shape_metrics(D.staircase(3)).solidity == pytest.approx(0.6, abs=1e-12)
    # A one-cell-thick line is a rectangle and is genuinely solid.
    assert D.production_shape_metrics(D.line(11)).solidity == 1.0


def test_a_ring_is_less_solid_than_a_block_of_the_same_cell_count() -> None:
    """A hole is invisible to a hull denominator and visible to a perimeter one.

    The 16-cell ring is 0.64 solid while its exact compactness is 0.196. The gap
    is the hole, and it is why solidity and compactness must not be used
    interchangeably: one of them cannot see a hole at all.
    """
    ring = D.production_shape_metrics(D.hollow_square(5, 1), sample_id="ring_5_t1")
    assert ring.n_cells == 16
    assert ring.solidity == pytest.approx(0.64, abs=1e-12)
    assert ring.compactness_oracle < 0.25
    assert ring.compactness_oracle < ring.solidity / 2.0


def test_the_production_bands_are_the_ones_the_code_reads() -> None:
    """The census describes the shipped constants, located by file and line.

    A band that has moved in the code and not in this table would make the whole
    characterization describe a parameter that no longer exists, so the values are
    pinned to the literals in the production source rather than to a copy.
    """
    by_id = {b.band_id: b for b in SOLIDITY_BANDS}
    assert by_id["shape.irregular"].value == 0.48
    assert by_id["classify.geology"].value == 0.75
    assert by_id["classify.recovery-note"].value == 0.50
    assert by_id["shape.irregular"].comparison == "<"
    assert by_id["classify.geology"].comparison == "<="
    assert by_id["classify.recovery-note"].comparison == "<"

    from groundscan.core import classify as classify_module
    from groundscan.core import shape as shape_module

    shape_source = shape_module.__file__
    classify_source = classify_module.__file__
    assert shape_source and classify_source
    for band in SOLIDITY_BANDS:
        path = shape_source if "core/shape" in band.production_site else classify_source
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        assert str(band.value) in text, f"{band.band_id} value is not in its production file"


def test_all_three_bands_are_active_on_the_analytic_catalogue() -> None:
    """A band that crosses nothing is either inert or untested; say which.

    Each band is checked to cross at least one analytic shape, which establishes
    that the catalogue exercises it at all. Whether a band is *meaningful* is a
    different question, answered in the report rather than here.
    """
    summary = solidity_census_summary()
    for band_id, stats in summary["bands"].items():
        assert stats["n_crossed"] > 0, f"{band_id} crosses nothing in the catalogue"
        assert stats["min_distance"] >= 0.0


def test_band_sensitivity_counts_decisions_not_values() -> None:
    """Moving a band must change a decision, not just a number.

    If a sweep reported only how far the band's value moved, any band would look
    responsive. What matters is the count of shapes whose comparison changes.
    """
    values = [r.solidity for r in solidity_census()]
    result = band_sensitivity(values)
    assert result["n_samples"] == len(values)
    for band_id, stats in result["per_band"].items():
        rows = stats["per_delta"]
        production = rows["+0.00"]
        assert production["n_changed"] == 0, band_id
        assert stats["n_crossed_at_production"] == production["n_crossed"], band_id
        moved = [r for key, r in rows.items() if key != "+0.00"]
        assert any(r["n_changed"] > 0 for r in moved), (
            f"{band_id} changes no decision anywhere in its swept range"
        )


def test_band_fragility_is_measured_against_a_stated_radius() -> None:
    summary = solidity_census_summary()
    for stats in summary["bands"].values():
        assert stats["fragility_radius"] == BAND_FRAGILITY_RADIUS
        assert 0 <= stats["n_fragile_within_radius"] <= stats["n_total"]


def test_the_0_75_band_is_the_most_active_and_the_0_50_band_the_most_fragile() -> None:
    """Two structural facts about the band set, recorded rather than tuned.

    The 0.75 band crosses the most analytic shapes, so it is the band a
    calibration would most change. The 0.50 band has the most shapes sitting
    within the fragility radius, and it is 0.02 from the 0.48 band. Both are
    arguments for leaving all three alone until there is evidence, not for moving
    any of them.
    """
    summary = solidity_census_summary()
    bands = summary["bands"]
    crossed = {k: v["n_crossed"] for k, v in bands.items()}
    fragile = {k: v["n_fragile_within_radius"] for k, v in bands.items()}
    assert max(crossed, key=crossed.get) == "classify.geology"
    assert max(fragile, key=fragile.get) == "classify.recovery-note"
    assert SOLIDITY_BANDS[0].value - SOLIDITY_BANDS[2].value == pytest.approx(-0.02, abs=1e-9)


def test_geometry_quality_terms_reconstruct_exactly() -> None:
    """The weight sweep's premise is checked, not assumed.

    ``_shape_metrics`` does not return its intermediates, so the sweep
    reconstructs the other three terms. If the reconstruction were approximate the
    sweep would be measuring a different formula, and this is what stops that.
    """
    result = verify_geometry_quality_reconstruction()
    assert result["reconstruction_exact"] is True
    assert result["max_abs_difference"] == 0.0


def test_the_solidity_weight_is_neither_calibrated_nor_inert() -> None:
    """Removing the term changes the weak-geometry decision for some shapes.

    The point of the assertion is the disjunction. A weight that changed nothing
    would be inert; a weight whose effect were pinned by evidence would be
    calibrated. It is neither, which is exactly the MODEL CHOICE status.
    """
    sweep = geometry_quality_weight_sweep()
    assert sweep["production_weight"] == GEOMETRY_QUALITY_SOLIDITY_WEIGHT
    free = sweep["solidity_free_row"]
    production = sweep["production_row"]
    assert free is not None and production is not None
    assert free["mean"] < production["mean"], "removing the term cannot raise the mean"
    assert sweep["decisions_attributable_to_the_weight"] is not None
    assert "policy choice" in sweep["claim"]


def test_the_retired_solidity_formula_is_not_a_shape_ratio() -> None:
    """The retired value moves with pitch; the corrected one does not.

    The retired formula divided a cell count by a hull area, so its value carried
    the dimension 1/area. This is the measurement that makes "recalibrate the bands
    against the retired distribution" meaningless rather than merely inadvisable.
    """
    from groundscan.validation.calibration.decision import solidity_distribution_shift

    shift = solidity_distribution_shift()
    assert shift["retired_metric_is_pitch_invariant"] is False
    corrected = shift["corrected_metric"]
    assert corrected["n"] == shift["n_shapes"]
    # A dimensionless ratio lives in [0, 1]; a 1/area quantity need not.
    assert corrected["min"] >= 0.0
    assert corrected["max"] <= 1.0
    profiles = shift["retired_metric_by_pitch"]
    medians = {key: stats["median"] for key, stats in profiles.items()}
    assert len(set(medians.values())) > 1, "the retired value did not move with pitch"
    assert "1/area" in shift["note"]


# ---------------------------------------------------------------------------
# Phase F -- compactness
# ---------------------------------------------------------------------------


def test_the_exact_quotient_is_scale_invariant_and_the_proxy_is_not() -> None:
    """The scale-bias measurement, isolated from every other consideration.

    A ``k x k`` block's exact exposed-edge quotient is exactly ``pi/4`` for every
    ``k``, so the proxy's departure from ``pi/4`` is entirely a size effect and
    needs no other explanation.
    """
    bias = compactness_scale_bias()
    assert bias["oracle_constant"] is True
    assert bias["square_true_value"] == pytest.approx(SQUARE_COMPACTNESS_TRUE, abs=1e-9)
    proxies = [row["proxy"] for row in bias["rows"]]
    assert proxies[0] > proxies[-1], "the proxy does not improve with size as it should"
    assert bias["n_saturated_at_one"] >= 3
    assert bias["proxy_at_largest_side"] < 1.0
    assert bias["proxy_at_largest_side"] > SQUARE_COMPACTNESS_TRUE


def test_a_thin_run_saturates_the_proxy_while_the_exact_quotient_keeps_falling() -> None:
    """The regime in which no compactness gate can reject anything.

    For a one-cell-thick run the erosion boundary ring *is* the component, so the
    quotient becomes ``4*pi`` and the clip saturates it to 1.0. Meanwhile the exact
    quotient falls as ``1/L^2``. In that regime both compactness gates are inert,
    however badly the shape would score on a real perimeter.
    """
    diagnostic = compactness_thin_diagnostic()
    assert diagnostic["n_saturated_at_one"] >= 5
    assert diagnostic["longest_saturated_length"] is not None
    rows = {row["length"]: row for row in diagnostic["rows"]}
    short = rows[3]
    longer = rows[10]
    assert short["ring_equals_area"] is True
    assert short["proxy"] == 1.0
    assert longer["proxy"] == 1.0
    assert longer["oracle"] < short["oracle"] / 2.0, "the exact quotient should have fallen"
    saturated = [r for r in diagnostic["rows"] if r["proxy"] >= 0.999]
    assert all(r["proxy"] >= r["oracle"] for r in saturated)


def test_the_proxy_is_non_monotone_across_the_smallest_shapes() -> None:
    """A two-cell run scores 0.0 and a three-cell run scores 1.0.

    ``digital_compactness`` returns 0.0 for one or two cells -- no measurable shape
    -- and then immediately saturates to 1.0 from three cells up. The response to
    component size is therefore not monotone in the region where the gates live,
    and no threshold on it can be read as "more compact than".
    """
    two = D.production_shape_metrics(D.line(2), sample_id="thin_2")
    three = D.production_shape_metrics(D.line(3), sample_id="thin_3")
    assert two.compactness == 0.0
    assert three.compactness == 1.0
    assert three.compactness > two.compactness


def test_the_compactness_matrix_shows_a_one_sided_bias_above_the_degenerate_floor() -> None:
    """The proxy over-estimates everywhere it measures anything.

    The erosion ring is a cell *count* and the exact perimeter is a length, and for
    every shape in this catalogue with three or more cells the ring is the smaller
    of the two -- so the quotient built from it is always too large. The direction
    matters: the gates admit rather than reject, so the failure mode is permissive
    and silent.

    The five shapes where the proxy is *below* the exact value are all one- or
    two-cell shapes, where ``digital_compactness`` returns a hard-coded ``0.0``
    because no shape is measurable. That is a documented degenerate-case rule, not
    an estimator error, and the test separates the two rather than averaging them.
    """
    rows = compactness_matrix()
    measured = [row for row in rows if row.n_cells > 2]
    degenerate = [row for row in rows if row.n_cells <= 2]
    assert degenerate, "the catalogue should contain the 1-2 cell regime"
    assert all(row.proxy == 0.0 for row in degenerate)
    assert all(row.error < 0.0 for row in degenerate)
    assert all(row.error > 0.0 for row in measured), (
        "a shape with three or more cells where the proxy understated compactness"
    )
    assert max(row.error for row in rows) == pytest.approx(0.93455, abs=1e-4)


def test_many_low_compactness_shapes_pass_every_gate() -> None:
    """The gate's practical effect, stated as a count.

    55 of the analytic shapes have a true compactness below 0.50, and 47 of them
    satisfy every production gate. A gate that admits the large majority of the
    genuinely non-compact shapes is not doing the work its name suggests.

    The count rose from 43 to 47 when the two dead ``classify.py`` gates were
    removed: with fewer gates to pass, more shapes pass all of them. That is the
    same conclusion as before -- the estimator is permissive -- reached with
    fewer comparisons pretending to be policy.
    """
    summary = compactness_matrix_summary()
    assert summary["n_oracle_below_0.50"] >= 40
    assert summary["n_low_oracle_shapes_that_pass_every_gate"] >= 40
    assert summary["n_proxy_saturated_at_one"] >= 30


def test_there_is_one_compactness_metric_and_two_different_thresholds() -> None:
    """A single quantity is compared against two distinct values.

    0.45 admits and 0.35 is a *rejection* rather than an admission, so there is
    no single compactness policy to calibrate -- there are two, and a change to
    the estimator would invalidate both at once, which is what makes it a larger
    piece of work than a retune.

    This asserted four thresholds until the dead rule cascade was removed from
    ``core/classify.py``. The two it dropped (``0.55`` and ``0.30``) were
    recorded as production consumers, but the branches they gated were
    overwritten before a candidate ever left ``classify_candidate``, so they
    compared compactness against nothing. The count is two because two is how
    many comparisons actually happen.
    """
    values = sorted(c["value"] for c in COMPACTNESS_CONSUMERS)
    assert values == [0.35, 0.45]
    comparisons = {c["comparison"] for c in COMPACTNESS_CONSUMERS}
    assert comparisons == {">=", "<"}
    sites = {c["production_site"] for c in COMPACTNESS_CONSUMERS}
    assert len(sites) == 2


def test_the_compactness_consumers_exist_where_the_table_says_they_do() -> None:
    """Each consumer's constant is verified against the production source file."""
    from pathlib import Path

    for consumer in COMPACTNESS_CONSUMERS:
        resolved = Path(consumer["source_path"])
        assert resolved.is_file(), consumer["consumer_id"]
        text = resolved.read_text(encoding="utf-8")
        assert str(consumer["value"]) in text, consumer["consumer_id"]
        # The recorded line must still be inside the file, and must actually be the
        # line the constant is on, so a constant that moved is noticed rather than
        # silently re-described at a stale line number.
        lines = text.splitlines()
        assert 0 < consumer["source_line"] <= len(lines), consumer["consumer_id"]
        on_line = lines[consumer["source_line"] - 1]
        assert str(consumer["value"]) in on_line, (
            f"{consumer['consumer_id']}: the value is no longer on the recorded line"
        )


def test_every_analytic_family_reaches_the_compactness_matrix() -> None:
    rows = compactness_matrix()
    families = {row.shape_family for row in rows}
    assert {"block", "concave", "ring", "diagonal", "thin", "disc"} <= families
    for row in rows:
        assert 0.0 <= row.proxy <= 1.0
        assert 0.0 <= row.oracle <= SQUARE_COMPACTNESS_TRUE + 1e-9


def test_compactness_characterization_is_deterministic() -> None:
    first = [r.to_dict() for r in compactness_matrix()]
    second = [r.to_dict() for r in compactness_matrix()]
    assert first == second
    assert compactness_scale_bias()["rows"] == compactness_scale_bias()["rows"]

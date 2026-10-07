"""Phase A -- the calibration datasets, and the licences their categories grant.

The tests here assert the *harness* is sound, not that the pipeline is correct:

* every analytic sample's exact solidity and exact compactness agree with the
  independent oracles by construction, and the production solidity agrees with
  the exact oracle;
* every perturbation case varies exactly one declared factor;
* every vendor fixture is content-addressed, and its provenance says
  behavioural-only in words that a test can grep;
* category D is empty *and* carries a recorded reason, so "we looked" and "we
  did not look" stay distinguishable;
* the analytic catalogue is digest-pinned, so a silent edit to a shape definition
  shows up as a test failure rather than as a new finding.

The licence tests are the load-bearing ones. A dataset that cannot say what it
forbids will eventually be used to justify something it cannot justify, and the
failure is silent.
"""

from __future__ import annotations

import json

import pytest

from groundscan.validation.calibration import datasets as D
from groundscan.validation.calibration.datasets import (
    CATEGORIES,
    CATEGORY_ANALYTICAL,
    CATEGORY_FIELD,
    CATEGORY_PERTURBATION,
    CATEGORY_VENDOR,
    FIELD_EVIDENCE_STATUS,
    PERTURBATION_FACTORS,
    analytic_shape_catalogue,
    border_bias_probe,
    calibration_datasets,
    dataset_report,
    exact_compactness,
    exact_solidity_fraction,
    exposed_edge_perimeter,
    face_adjacency_count,
    field_evidence_availability,
    perturbation_catalogue,
    production_shape_metrics,
    vendor_fixture_index,
)


def test_analytic_catalogue_is_constructible_and_non_trivial() -> None:
    catalogue = analytic_shape_catalogue()
    assert len(catalogue) >= 60
    families = {s.shape_family for s in catalogue}
    assert {"block", "concave", "ring", "diagonal", "thin", "disc"} <= families
    assert all(s.cells for s in catalogue), "no empty shape in the catalogue"
    assert len({s.sample_id for s in catalogue}) == len(catalogue), "duplicate sample_id"


def test_every_analytic_sample_carries_exact_independent_provenance() -> None:
    for sample in analytic_shape_catalogue():
        assert sample.provenance.category == CATEGORY_ANALYTICAL
        assert sample.provenance.truth_kind == D.TRUTH_EXACT
        assert sample.provenance.independent_of_pipeline is True


def test_exposed_edge_perimeter_is_exact_on_hand_checked_shapes() -> None:
    # A 3x3 block: 9 cells, 12 shared edges -> 4*9 - 2*12 = 12, and a square's
    # side is 3 so the perimeter is 4*3 = 12. Counted by hand, not derived.
    assert face_adjacency_count(D.square(3)) == 12
    assert exposed_edge_perimeter(D.square(3)) == 12
    assert exposed_edge_perimeter(D.square(1)) == 4
    # A 5-cell diagonal run has no face adjacency at all: 4*5 - 0 = 20.
    assert face_adjacency_count(D.staircase(5)) == 0
    assert exposed_edge_perimeter(D.staircase(5)) == 20


def test_exact_compactness_equals_pi_over_4_for_every_block() -> None:
    """The isoperimetric quotient of a square is pi/4, whatever its size.

    A shape ratio that depends on how many cells the shape occupies is not a
    shape ratio, so this is the single most informative check in this file: it is
    what the production estimator fails and what the oracle does not.
    """
    import math

    for side in (1, 2, 3, 5, 10, 25, 60):
        assert exact_compactness(D.square(side)) == pytest.approx(math.pi / 4.0, abs=1e-12)


def test_exact_compactness_falls_for_thin_shapes() -> None:
    values = [exact_compactness(D.line(n)) for n in (3, 6, 12, 24, 48)]
    assert values == sorted(values, reverse=True), "a longer run is not less compact"
    assert values[0] > 0.55
    assert values[-1] < 0.1


def test_ring_perimeter_counts_the_hole_as_exposed() -> None:
    """A hole is exposed boundary, and the oracle counts it; a hull cannot.

    A 5x5 ring of thickness 1 has 16 cells. Its exposed perimeter is the outer
    20 plus the inner 12 = 32, and the exact quotient is far below the pi/4 a
    solid 16-cell block would reach. This is the case where a convex-hull
    denominator and a perimeter denominator disagree most, and it is why the
    solidity of a ring (0.64) is nowhere near its compactness (0.196).
    """
    cells = D.hollow_square(5, 1)
    assert len(cells) == 16
    assert exposed_edge_perimeter(cells) == 32
    assert exact_compactness(cells) < 0.25


def test_production_solidity_equals_the_exact_oracle_on_every_analytic_shape() -> None:
    for sample in analytic_shape_catalogue():
        metrics = production_shape_metrics(sample.cells, sample_id=sample.sample_id)
        assert metrics.solidity == pytest.approx(metrics.solidity_oracle, abs=1e-12)
        assert metrics.solidity_oracle == pytest.approx(
            float(exact_solidity_fraction(sample.cells)), abs=1e-15
        )


def test_a_convex_block_has_solidity_exactly_one() -> None:
    for side in (1, 2, 3, 7, 20, 40):
        metrics = production_shape_metrics(D.square(side))
        assert metrics.solidity == 1.0


def test_a_corner_touching_diagonal_run_is_not_solid() -> None:
    """Three corner-touching cells have solidity 3/5, not 1.0.

    This is the case the retired formula reported as perfectly solid through its
    degenerate-hull branch, and it is the clearest single illustration of why
    the S02 correction mattered.
    """
    metrics = production_shape_metrics(D.staircase(3))
    assert metrics.solidity == pytest.approx(3.0 / 5.0, abs=1e-12)


def test_erosion_padding_cannot_contaminate_the_compactness_proxy() -> None:
    """A zero spread here closes off array padding as an explanation.

    ``binary_erosion`` pads with background, so a shape flush against the array
    edge could in principle be penalised for cells with no exposed boundary. It is
    not, because the production mask window is the component's own bounding box
    and every window-edge cell is already on the component's outer shell.
    """
    probe = border_bias_probe(6)
    assert probe["compactness_spread"] == 0.0
    assert probe["erosion_cell_spread"] == 0


def test_perturbation_cases_vary_exactly_one_declared_factor() -> None:
    cases = perturbation_catalogue()
    assert len(cases) >= 30
    declared = set(PERTURBATION_FACTORS)
    for case in cases:
        assert case.factor in declared or case.factor == "reference"
        assert case.provenance().category == CATEGORY_PERTURBATION
        assert case.provenance().independent_of_pipeline is True
        # A base case must hold every free parameter at the base value, or a
        # difference attributed to one factor would be confounded.
        if case.factor == "reference":
            assert case.noise_sigma == 1.0
            assert case.dy_ratio == 1.0
            assert case.base_pitch_m == D.BASE_PITCH_M
        if case.factor == "noise":
            assert case.base_pitch_m == D.BASE_PITCH_M
            assert case.dy_ratio == 1.0


def test_every_perturbation_factor_has_several_levels() -> None:
    counts: dict[str, int] = {}
    for case in perturbation_catalogue():
        if case.factor == "reference":
            continue
        counts[case.factor] = counts.get(case.factor, 0) + 1
    for factor in PERTURBATION_FACTORS:
        assert counts.get(factor, 0) >= 2, f"factor {factor} has too few levels"


def test_perturbation_noise_and_amplitude_brackets_the_detection_threshold() -> None:
    """The ladders must cross the production threshold, not sit on one side.

    A ladder entirely above threshold measures nothing about the threshold, and a
    ladder entirely below it measures nothing at all.
    """
    snrs = [
        c.responses[0].amplitude / c.noise_sigma
        for c in perturbation_catalogue()
        if c.noise_sigma > 0
    ]
    assert min(snrs) < 3.0, "no case below the production detection threshold"
    assert max(snrs) > 20.0, "no case well above the production detection threshold"


def test_polarity_family_covers_both_signs() -> None:
    signs = {c.responses[0].amplitude for c in perturbation_catalogue() if c.factor == "polarity"}
    assert any(s > 0 for s in signs) and any(s < 0 for s in signs)


def test_contamination_field_is_deterministic_and_sparse() -> None:
    first = D.contamination_field((32, 32), n_spikes=5, amplitude=40.0, seed=7)
    second = D.contamination_field((32, 32), n_spikes=5, amplitude=40.0, seed=7)
    assert (first == second).all()
    assert int(np_count_nonzero(first)) <= 5
    assert float(first.max()) == 40.0
    assert D.contamination_field((8, 8), n_spikes=0, amplitude=1.0, seed=0).sum() == 0.0


def np_count_nonzero(values: object) -> int:
    import numpy as np

    return int(np.count_nonzero(values))


def test_vendor_fixtures_are_content_addressed_and_behavioural_only() -> None:
    fixtures = vendor_fixture_index()
    assert len(fixtures) == 9
    for fixture in fixtures:
        assert len(fixture.content_sha256) == 64
        assert fixture.size_bytes > 0
        provenance = fixture.provenance()
        assert provenance.category == CATEGORY_VENDOR
        assert provenance.truth_kind == D.TRUTH_BEHAVIOURAL
        assert "BEHAVIOURAL REFERENCE ONLY" in provenance.detail
        assert "not a physical measurement" in provenance.detail


def test_field_evidence_is_empty_with_a_recorded_reason() -> None:
    availability = field_evidence_availability()
    assert availability["category"] == CATEGORY_FIELD
    assert availability["status"] == FIELD_EVIDENCE_STATUS
    assert availability["sample_count"] == 0
    assert availability["independent_calibration_possible"] is False
    assert len(availability["gaps"]) >= 4
    assert availability["vendor_annotation_is_not_ground_truth"] is True


def test_dataset_licences_forbid_the_obvious_category_leaks() -> None:
    """Each category must state, in its own words, what it cannot be used for.

    This is the test that stops a number being justified by a vendor case and
    reported as if a closed form had justified it.
    """
    table = calibration_datasets()
    assert set(table) == set(CATEGORIES)

    assert "any claim about a physical target" in table[CATEGORY_ANALYTICAL].forbids
    assert "false-positive rate on real data" in table[CATEGORY_ANALYTICAL].forbids
    assert "any operating envelope" in table[CATEGORY_ANALYTICAL].forbids

    assert "Vendor fixtures are a regression reference, not ground truth" in (
        table[CATEGORY_VENDOR].forbids
    )
    assert "selecting a threshold, weight or band" in table[CATEGORY_VENDOR].forbids

    assert "absolute false-positive rate" in table[CATEGORY_PERTURBATION].forbids

    assert table[CATEGORY_FIELD].samples == ()
    assert "there is nothing" in table[CATEGORY_FIELD].forbids


def test_dataset_permits_and_forbids_do_not_contradict_each_other() -> None:
    """No category may permit what another category forbids it from needing.

    Concretely: a category that permits choosing a number must not be the one
    whose forbids clause excludes physical ground truth, or the licence would
    authorise a calibration the evidence cannot support.
    """
    table = calibration_datasets()
    for name, dataset in table.items():
        if "selecting a threshold" in dataset.forbids:
            assert "selecting" not in dataset.permits, name
        if (
            "every physical target" in dataset.forbids
            or "any claim about a physical" in dataset.forbids
        ):
            assert "physical" not in dataset.permits, name


def test_dataset_report_is_json_serializable_and_complete() -> None:
    report = dataset_report()
    text = json.dumps(report, default=str)
    assert len(text) > 500
    assert set(report["datasets"]) == set(CATEGORIES)
    assert report["datasets"][CATEGORY_VENDOR]["fixtures"]
    assert report["datasets"][CATEGORY_ANALYTICAL]["families"]
    assert report["datasets"][CATEGORY_PERTURBATION]["factors"]
    assert report["datasets"][CATEGORY_FIELD]["status"] == FIELD_EVIDENCE_STATUS


#: Pinned so an edit to any shape definition is a visible test failure. Every band
#: characterization in this stage derives from this catalogue, so a changed shape
#: would otherwise become a new "finding" rather than an acknowledged input change.
#: Regenerate deliberately; never as a side effect of another edit.
CATALOGUE_DIGEST = "a27704fda1ba25b676ec319e3d5d192ad7b2b70ac65da6e5523eed172e3f3a5d"


def test_analytic_catalogue_digest_is_pinned() -> None:
    """A silent edit to a shape definition must be a visible change.

    Every band characterization in this stage is derived from this catalogue, so
    a changed shape would silently become a new "finding" rather than an
    acknowledged input change.
    """
    assert D.analytic_catalogue_digest() == CATALOGUE_DIGEST
    assert D.analytic_catalogue_digest() == D.analytic_catalogue_digest()


def test_production_shape_metrics_rejects_degenerate_input() -> None:
    with pytest.raises(ValueError):
        production_shape_metrics([], sample_id="empty")
    with pytest.raises(ValueError):
        production_shape_metrics(D.square(3), cell_dx=0.0)
    with pytest.raises(ValueError):
        production_shape_metrics(D.square(3), cell_dy=-1.0)


def test_harness_grid_size_is_recorded_so_grid_relative_metrics_are_readable() -> None:
    """``broadness_score`` divides by the grid, so the grid size is part of the result.

    ``shape_class`` is decided by ``broadness_score`` before the solidity branch
    is reached, so a shape's class from this harness is a statement about the
    shape *at this grid size*. The harness records it rather than letting a reader
    assume a survey-sized grid.
    """
    cramped = production_shape_metrics(D.square(8), min_grid_cells=8)
    roomy = production_shape_metrics(D.square(8), min_grid_cells=60)
    assert cramped.harness_grid != roomy.harness_grid
    assert cramped.broadness_score > roomy.broadness_score
    assert cramped.shape_class == "broad"
    assert roomy.shape_class != "broad"

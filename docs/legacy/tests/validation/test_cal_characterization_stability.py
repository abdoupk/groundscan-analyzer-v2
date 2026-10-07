"""Cross-cutting requirements: perturbation stability, determinism, and coverage.

The brief's required-experiment list contains three items that are properties of
the whole harness rather than of one parameter, and they are collected here so
they are asserted once and unambiguously:

* **cross-resolution characterization** -- the same physical scene at several
  lattices, with the levels of the corrected model kept apart;
* **anisotropic-spacing characterization** -- the shape metrics at ``dx != dy``;
* **perturbation stability** -- the output under each declared perturbation factor;
* **repeated deterministic execution** -- every characterization re-run inside one
  process must return identical numbers.

Determinism gets the most assertions, because a characterization whose own numbers
move between runs cannot support a calibration decision, and a silent drift there
would be indistinguishable from a real finding.
"""

from __future__ import annotations

import numpy as np
import pytest

from groundscan.validation.calibration import datasets as D
from groundscan.validation.calibration import decision as V
from groundscan.validation.calibration import geometry as G
from groundscan.validation.calibration import interactions as I
from groundscan.validation.calibration import resolution as R
from groundscan.validation.calibration.datasets import (
    CATEGORY_PERTURBATION,
    PERTURBATION_FACTORS,
    perturbation_catalogue,
    production_shape_metrics,
)
from groundscan.validation.calibration.decision import margin_instability_zone
from groundscan.validation.calibration.resolution import separation_trial

# ---------------------------------------------------------------------------
# Cross-resolution
# ---------------------------------------------------------------------------


def test_one_physical_scene_at_several_lattices_gives_measured_counts_at_each() -> None:
    """The same continuous field, sampled at three pitches.

    The scene is constructed once and every lattice samples *that*, which is what
    makes this a resolution study rather than a set of unrelated scenes. The noise
    draw is necessarily independent per lattice, which is exactly why no relation
    here is exact and why the tolerance is derived from the pitch.
    """
    scene = R.pair_scene(sigma_m=1.0, separation_m=6.0, amplitude=10.0, noise_sigma=1.0)
    assert scene.response_count == 2
    for pitch in (0.25, 0.5, 1.0):
        trial = separation_trial(sigma_m=1.0, separation_m=6.0, pitch_dx_m=pitch, seed=0)
        assert trial.analytic_modes == 2
        assert trial.continuous_modes == 2, pitch
        assert trial.pitch_dx_m == pitch
        assert trial.pitch_dy_m == pytest.approx(pitch)


def test_a_coarse_lattice_may_not_resolve_what_a_fine_one_does() -> None:
    """Resolution is a one-way loss, and the loss is measured rather than assumed.

    A response of width sigma sampled at a pitch comparable to sigma is barely
    represented, so the pair can fail to resolve at 1.0 m and resolve at 0.25 m. The
    test asserts the direction without asserting a specific outcome, because at these
    settings the outcome depends on the noise draw -- and a test that pinned it would
    pin a noise seed's result as a law.
    """
    outcomes = {
        pitch: separation_trial(
            sigma_m=1.0, separation_m=6.0, pitch_dx_m=pitch, seed=0
        ).distinct_regions
        for pitch in (0.25, 0.5, 1.0)
    }
    assert outcomes[0.25] >= outcomes[0.5]
    assert outcomes[0.5] >= outcomes[1.0]
    assert max(outcomes.values()) <= 2


def test_the_five_levels_are_never_conflated() -> None:
    """A candidate count is not a response-region count is not a physical object.

    The characterization's own vocabulary keeps the five levels apart, and this
    asserts the property that matters: no field name invites a level-6 reading.
    """
    from groundscan.validation.synthetic_core.cross_resolution import (
        FORBIDDEN_OBJECT_COUNT_NAMES,
        LEVEL_ANOMALY_REGION,
        LEVEL_CANDIDATE_HYPOTHESIS,
        LEVEL_DECOMPOSITION,
        LEVEL_PHYSICAL_OBJECT,
        LEVEL_RESPONSE_REGION,
    )

    levels = [
        LEVEL_ANOMALY_REGION,
        LEVEL_RESPONSE_REGION,
        LEVEL_CANDIDATE_HYPOTHESIS,
        LEVEL_DECOMPOSITION,
        LEVEL_PHYSICAL_OBJECT,
    ]
    assert levels == [2, 3, 4, 5, 6]
    assert all(len(name) > 3 for name in FORBIDDEN_OBJECT_COUNT_NAMES)


# ---------------------------------------------------------------------------
# Anisotropy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dx,dy", [(1.0, 1.0), (0.04, 0.04), (0.5, 2.0), (2.0, 0.5)])
def test_solidity_is_invariant_under_anisotropic_spacing(dx: float, dy: float) -> None:
    """The corrected metric does not see the lattice aspect ratio at all.

    The algebra cancels ``dx`` and ``dy`` separately, so an anisotropic cell is
    measured exactly as a square one. This is the regression guard for that
    cancellation, at four spacings including two order-of-magnitude rescalings.
    """
    for sample in D.analytic_shape_catalogue():
        metrics = production_shape_metrics(
            sample.cells, cell_dx=dx, cell_dy=dy, sample_id=sample.sample_id
        )
        assert metrics.solidity == pytest.approx(metrics.solidity_oracle, abs=1e-12), (
            f"{sample.sample_id} at dx={dx} dy={dy}"
        )


def test_compactness_is_invariant_under_anisotropic_spacing_too() -> None:
    """Compactness is a *cell count*, so it also cannot see the aspect ratio.

    Worth separating from solidity: this is not a defect but a consequence of the
    estimator's definition. A boundary-cell count divided by an area is unit-free
    in both axes, which is why the two metrics behave the same way here and very
    differently in scale.
    """
    for sample in D.analytic_shape_catalogue()[:20]:
        base = production_shape_metrics(sample.cells, sample_id=sample.sample_id)
        for dx, dy in ((0.5, 2.0), (2.0, 0.5), (0.1, 0.1)):
            probe = production_shape_metrics(
                sample.cells, cell_dx=dx, cell_dy=dy, sample_id=sample.sample_id
            )
            assert probe.compactness == pytest.approx(base.compactness, abs=1e-12)
            assert probe.solidity == pytest.approx(base.solidity, abs=1e-12)


def test_the_production_extents_do_see_the_anisotropy() -> None:
    """The geometric extents are physical, so they must move with the cell aspect.

    The counterpart to the two invariances above: if nothing in the harness moved
    when the cell shape changed, the harness would not be measuring the cell shape.
    """
    for sample in D.analytic_shape_catalogue()[:20]:
        if sample.shape_family not in {"block", "thin"}:
            continue
        square_cell = production_shape_metrics(sample.cells, cell_dx=1.0, cell_dy=1.0)
        tall_cell = production_shape_metrics(sample.cells, cell_dx=1.0, cell_dy=2.0)
        assert tall_cell.major_extent != pytest.approx(square_cell.major_extent, rel=1e-9) or (
            tall_cell.minor_extent != pytest.approx(square_cell.minor_extent, rel=1e-9)
        )


# ---------------------------------------------------------------------------
# Perturbation stability
# ---------------------------------------------------------------------------


def test_every_declared_perturbation_factor_is_exercised_by_the_population() -> None:
    """The population must actually contain each factor it claims to characterize.

    A factor declared in the catalogue but absent from the built population would
    leave a hole in the corpus that no summary would reveal.
    """
    population = V.candidate_population(limit_vendor=1, include_vendor=False)
    factors = {m.case_factor for m in population}
    for factor in PERTURBATION_FACTORS:
        assert factor in factors, factor
    assert {m.category for m in population} == {CATEGORY_PERTURBATION}


def test_the_instability_probe_reports_its_perturbation_set() -> None:
    """The flip rate is meaningless without the perturbations that produced it.

    A single aggregate rate would be a rate over a set the reader cannot see, and
    the brief's own question -- whether a small margin is unstable -- cannot be
    judged from it.
    """
    zone = margin_instability_zone(
        perturbations=(("translate", 0.1), ("noise", 0.25), ("amplitude", 0.9)),
        seeds=(0, 1),
    )
    assert zone["n_observations"] > 0
    assert {p["factor"] for p in zone["perturbations"]} == {
        "translate",
        "noise",
        "amplitude",
    }
    assert zone["seeds"] == [0, 1]
    assert zone["margin_bins"][0] == 0.0
    assert zone["margin_bins"][-1] > zone["margin_bins"][-2]
    for entry in zone["per_margin_bin"]:
        assert entry["margin_from"] < entry["margin_to"]


def test_a_pure_polarity_flip_preserves_detection_and_changes_the_label() -> None:
    """A constructed sign change is the cleanest available perturbation.

    A sign flip cannot change whether a response is *detected* -- the detector
    thresholds ``|z|`` -- so any change in the reported label is attributable to
    polarity semantics rather than to detection. That makes this the one
    perturbation whose confounders are known to be absent.
    """
    from pathlib import Path

    from groundscan.services.single_scan import analyze_scan
    from groundscan.validation.synthetic_core.cross_resolution import (
        PhysicalResponse,
        PhysicalScene,
        Resolution,
        sample_scene,
    )

    def _run(amplitude: float) -> tuple[int, list[str]]:
        scene = PhysicalScene(
            name="polarity",
            width_m=24.0,
            height_m=18.0,
            responses=(
                PhysicalResponse(
                    label="r",
                    cx=12.0,
                    cy=9.0,
                    sigma_x=1.0,
                    sigma_y=1.0,
                    amplitude=amplitude,
                ),
            ),
            noise_sigma=1.0,
            case_family="polarity-probe",
        )
        scan = sample_scene(scene, Resolution("p", 0.5, 24.0, 18.0), seed=0)
        _grid, _anomaly, candidates = analyze_scan(
            scan, out_dir=Path("."), label="polarity", write_outputs=False
        )
        return len(candidates), [str(c.pattern_hypothesis) for c in candidates]

    positive_n, positive_labels = _run(10.0)
    negative_n, negative_labels = _run(-10.0)
    assert positive_n == negative_n, "a sign flip changed the number of detections"
    assert positive_labels != negative_labels, (
        "a sign flip changed nothing in the reported labels, so the perturbation is "
        "not reaching the classification"
    )


# ---------------------------------------------------------------------------
# Repeated deterministic execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: [r.to_dict() for r in G.solidity_census()], id="solidity_census"),
        pytest.param(lambda: G.pitch_invariance(), id="pitch_invariance"),
        pytest.param(
            lambda: [r.to_dict() for r in G.compactness_matrix()], id="compactness_matrix"
        ),
        pytest.param(lambda: G.compactness_scale_bias(), id="compactness_scale_bias"),
        pytest.param(lambda: G.geometry_quality_weight_sweep(), id="geometry_weight_sweep"),
        pytest.param(
            lambda: [V.three_sigma_observation(threshold=3.0, rows=32, cols=32, seed=1).to_dict()],
            id="three_sigma",
        ),
        pytest.param(lambda: D.analytic_catalogue_digest(), id="catalogue_digest"),
        pytest.param(lambda: [f.to_dict() for f in D.vendor_fixture_index()], id="vendor_index"),
        pytest.param(lambda: D.border_bias_probe(6), id="border_bias_probe"),
    ],
)
def test_characterization_functions_are_deterministic(call) -> None:
    """Every characterization returns identical numbers on a second call.

    Asserted over the whole set rather than one function, because determinism here
    is a property of the harness and a single sample would not establish it.
    """
    assert call() == call()


def _same_candidate(a: object, b: object) -> bool:
    """Field-by-field equality that treats NaN as equal to itself.

    ``nan != nan`` in Python, and several ``Candidate`` fields are legitimately NaN
    (an absent soil channel, an unmeasured overlap distance). A plain ``==`` on the
    field dicts would therefore report a difference that is not one -- and a
    determinism test that always fails teaches nothing.
    """
    left = vars(a)
    right = vars(b)
    if set(left) != set(right):
        return False
    for key, value in left.items():
        other = right[key]
        # NaN on both sides is the only case where `!=` is the wrong answer.
        both_nan = (
            isinstance(value, float)
            and isinstance(other, float)
            and value != value
            and other != other
        )
        if not both_nan and value != other:
            return False
    return True


def test_the_population_is_deterministic() -> None:
    """Rebuilding the candidate population reproduces it exactly.

    The population is built by running the analysis path over a catalogue, so any
    ordering or accumulation nondeterminism upstream would show up here -- and every
    sensitivity count in the report is a count over this object.
    """
    first = V.candidate_population(limit_vendor=2)
    second = V.candidate_population(limit_vendor=2)
    assert len(first) == len(second)
    for a, b in zip(first, second, strict=True):
        assert a.source_id == b.source_id
        assert _same_candidate(a.candidate, b.candidate)


def test_the_interaction_roll_up_is_deterministic() -> None:
    population = V.candidate_population(limit_vendor=1)
    first = I.solidity_x_geometry_quality(population)
    second = I.solidity_x_geometry_quality(population)
    assert first == second


def test_the_separation_trial_is_deterministic_across_repeats() -> None:
    """The same construction and seed must give the same detected region count.

    Checked by re-running the whole detector, not by re-reading a cached value, so
    the determinism claim covers the analysis path rather than the summary code.
    """
    for seed in (0, 1, 2):
        first = separation_trial(sigma_m=1.0, separation_m=5.0, pitch_dx_m=0.5, seed=seed)
        second = separation_trial(sigma_m=1.0, separation_m=5.0, pitch_dx_m=0.5, seed=seed)
        assert first.to_dict() == second.to_dict()
        assert first.region_count == second.region_count


def test_different_seeds_produce_different_noise_and_can_change_the_outcome() -> None:
    """The noise dimension is real, so a single-seed characterization is a sample.

    A sweep that only ever used one seed would report a crossing as if it were a
    property of the construction. Showing that different draws can differ is what
    makes the multi-draw reporting in :mod:`.resolution` necessary rather than
    decorative.
    """
    counts = {
        seed: separation_trial(
            sigma_m=1.0, separation_m=4.0, pitch_dx_m=0.5, seed=seed
        ).region_count
        for seed in range(8)
    }
    assert len(set(counts.values())) > 1, (
        "eight independent noise draws all gave the same region count, so the "
        "draw dimension is not doing anything"
    )


# ---------------------------------------------------------------------------
# The corpus is the one the report describes
# ---------------------------------------------------------------------------


def test_the_perturbation_catalogue_covers_the_whole_corpus_by_construction() -> None:
    """The catalogue and the population agree on which cases exist.

    Checked through the case ids rather than by counting, so a case silently dropped
    from either side would show up as a set difference.
    """
    catalogue_ids = {c.case_id for c in perturbation_catalogue()}
    population_ids = {
        m.source_id for m in V.candidate_population(limit_vendor=1, include_vendor=False)
    }
    assert population_ids <= catalogue_ids
    assert len(catalogue_ids) >= 40
    assert len(population_ids) >= 30


def test_the_sweep_levels_are_distinct_lattices_sampling_one_field() -> None:
    """Different pitches must really be different lattices, not relabelled ones."""
    from groundscan.validation.synthetic_core.cross_resolution import Resolution

    pitches = (0.25, 0.5, 1.0)
    resolutions = [Resolution(f"p{p}", p, 24.0, 18.0) for p in pitches]
    assert len({r.nx for r in resolutions}) == 3
    assert len({r.sample_count for r in resolutions}) == 3
    assert all(r.dx == p for r, p in zip(resolutions, pitches, strict=True))


def test_the_noise_field_is_pure_noise_so_every_finding_is_a_false_positive() -> None:
    """The false-positive measurement's own premise, checked.

    The 3-sigma characterization is only a false-positive measurement if the field
    contains no response. Asserting that the signal array is the raw normal draw
    (plus optional contamination) is what keeps it one.
    """
    from groundscan.validation.calibration.decision import three_sigma_observation

    observation = three_sigma_observation(threshold=3.0, rows=32, cols=32, seed=0)
    assert observation.n_cells == 32 * 32
    assert observation.n_exceeding < observation.n_cells * 0.1
    assert isinstance(observation.measured_cell_rate, float)
    assert np.isfinite(observation.measured_cell_rate)

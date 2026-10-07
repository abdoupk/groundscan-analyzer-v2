"""The S03 shadow over the real fixtures, and the activation gate it feeds.

Three things are checked here, and they are checked differently on purpose:

* **Asserted.** The regime census. Production enters the regime Stage 3 could
  not fix three times out of 149 residuals, always on a lattice-quantised
  residual, and never once in the two regimes the activation changed. A number
  that is merely "small" is not a census; it is pinned so a fixture silently
  disappearing cannot quietly shrink the population being reasoned about.
* **Asserted.** Zero downstream change. The scale is what the whole chain reads,
  so if the activation moved a finding count, a pattern label or an evidence
  score on a corpus scan, this is where it must show.
* **Measured, and only measured.** How much contamination influence the three
  degenerate residuals actually carry. That is a disclosure, not a decision, and
  pinning it to a number would turn a measurement into a threshold.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from groundscan.validation import scale_reference as ref
from groundscan.validation.scale_shadow_report import (
    REGIME_DEGENERATE,
    REGIME_IQR,
    REGIME_LOW_SAMPLE,
    REGIME_MAD,
    REGIME_UNAVAILABLE,
    compare_downstream,
    compare_residual,
    full_census,
    golden_reports,
    residual_census,
    residual_regime,
    shipped_status_estimate,
    synthetic_reports,
    vendor_reports,
)

# ---------------------------------------------------------------------------
# The regime classification itself
# ---------------------------------------------------------------------------


def test_a_regime_is_assigned_from_the_definitions_not_from_production():
    """The instrument does not read the thing it measures.

    ``residual_regime`` classifies a sample from the reference module's own
    arithmetic. If it called production it could only ever agree with it, and a
    census built on it would be a census of the implementation.
    """
    rng = np.random.default_rng(4)
    cases = {
        "gaussian": (rng.normal(0.0, 1.0, 800), REGIME_MAD),
        "near_gauss_with_tail": (
            rng.normal(0.0, 1.0, 700).tolist() + [0.0] * 98 + [4.0],
            REGIME_MAD,
        ),
        "quantised_heavy_atom": (
            np.concatenate([np.zeros(700), rng.integers(-2, 3, 100).astype(float)]),
            REGIME_DEGENERATE,
        ),
        # A one-sided atom: 60 % of the mass on the median with the tail
        # entirely above it, so the MAD is zero while the upper quartile is not.
        # This is the shape of the two Gallery residuals that reach the second
        # rung, and the reason the second rung is reachable at all.
        "quantised_one_sided_atom": (
            np.concatenate([np.zeros(600), rng.integers(1, 5, 400).astype(float)]),
            REGIME_IQR,
        ),
        "constant": (np.full(500, 3.0), REGIME_UNAVAILABLE),
        "one_value": (np.full(1, 3.0), REGIME_UNAVAILABLE),
        "pair": (np.array([0.0, 1.0]), REGIME_LOW_SAMPLE),
    }
    for label, (values, expected) in cases.items():
        assert residual_regime(np.asarray(values))[0] == expected, label


def test_the_corpus_census_is_pinned() -> None:
    """149 residuals: 144 primary, 2 second, 3 degenerate, 0 unavailable.

    The zeros at the end are the load-bearing part. The activation's caller
    contract says an indeterminate scale must not reach a threshold, and the
    honest way to close a contract like that without a runtime cost is to show
    the branch is unreachable on the available evidence base -- and to keep
    showing it, so a future change that makes it reachable fails here.
    """
    census = full_census()
    assert census["residual_count"] == 149
    assert census["regime_census"]["counts"] == dict(ref.REAL_RESIDUAL_REGIMES)
    assert census["regime_census"]["counts"]["low_sample"] == 0
    assert census["regime_census"]["counts"]["unavailable"] == 0


# ---------------------------------------------------------------------------
# The activation gate
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_the_activation_changes_no_finding_and_no_score_on_the_corpus() -> None:
    """Phase H's regression protection, stated as a measurement of zero.

    The design predicted S03 would be "none for non-degenerate residuals" and
    called a change there a red flag to investigate. The investigation is this
    test: identical inputs, identical configuration, only the estimator
    differs, and nothing downstream of the scale moves. The result is a fact
    about the corpus, and the corpus is the only evidence base the project has.
    """
    from groundscan.services.config import AnalysisConfig
    from groundscan.services.single_scan import load_scan
    from groundscan.validation.fixtures import VENDOR_ROOT

    config = AnalysisConfig()
    compared = 0
    for name, scan in _catalog():
        impact = compare_downstream(scan, source=name, config=config)
        compared += 1
        _assert_identical(impact, name)
    for group in ("train", "validation"):
        for path in sorted((VENDOR_ROOT / group).glob("*.csv")):
            impact = compare_downstream(load_scan(path), source=path.name, config=config)
            compared += 1
            _assert_identical(impact, path.name)
    assert compared >= 20, f"only {compared} scans compared; the corpus shrank"


def _assert_identical(impact, label: str) -> None:
    assert impact.count_delta == 0, (
        f"{label}: {impact.candidate_count_legacy} -> {impact.candidate_count_candidate} findings"
    )
    assert not impact.hypothesis_changes, f"{label}: {impact.hypothesis_changes}"
    assert not impact.label_changes, f"{label}: {impact.label_changes}"
    assert not impact.field_deltas, f"{label}: {dict(impact.field_deltas)}"
    assert impact.peak_abs_z_candidate == pytest.approx(impact.peak_abs_z_legacy, rel=0.0, abs=0.0)


def _catalog():
    from groundscan.validation.synthetic_core.core import generate_scan, scenario_catalog

    return [(s.name, generate_scan(s)[0]) for s in scenario_catalog()]


# ---------------------------------------------------------------------------
# The three degenerate residuals, and the disclosure that replaced the fix
# ---------------------------------------------------------------------------


def test_the_degenerate_residuals_are_the_ones_the_measurement_named() -> None:
    """Two vendor scans, three channels, and no others anywhere.

    The design's warning was that a change in the degenerate regime "signals a
    degenerate vendor residual". This is the enumeration: if a third scan
    appears here, the activation's blast radius has grown and a reviewer needs
    to look at it.
    """
    from groundscan.core.grid import reconstruct_grid
    from groundscan.services.single_scan import load_scan
    from groundscan.validation.fixtures import VENDOR_ROOT
    from groundscan.validation.scale_shadow_report import _channel_residuals

    found: dict[str, list[str]] = {}
    for group in ("train", "validation"):
        for path in sorted((VENDOR_ROOT / group).glob("*.csv")):
            grid = reconstruct_grid(load_scan(path))
            for channel, residual in _channel_residuals(grid):
                if residual_regime(residual)[0] != REGIME_DEGENERATE:
                    continue
                found.setdefault(path.name, []).append(channel)
    assert found == {
        "Royal Tomb.csv": ["multiscale_median_3"],
        "Gallery and Tunnel.csv": ["multiscale_median_3", "multiscale_median_5"],
    }


@pytest.mark.slow
def test_every_degenerate_residual_is_disclosed_with_a_reliability_number() -> None:
    """The three residuals, and what the record now says about each.

    A ``degraded`` status with no number beside it is honest but unusable: an
    operator has no way to act on it. ``contamination_influence`` is the number,
    and the two degenerate residuals need *different* answers:

    * ``Royal Tomb`` has a high-breakdown reference available (its atom is
      lighter), so the influence is a number and it is above 1 -- the reported
      scale is nearly twice the robust estimate;
    * both ``Gallery and Tunnel`` residuals have no robust reference at all, so
      the influence is undefined. That is the *stronger* warning and it must not
      be smoothed into a number, because any number here would be invented.
    """
    from groundscan.core.grid import reconstruct_grid
    from groundscan.services.single_scan import load_scan
    from groundscan.validation.fixtures import VENDOR_ROOT
    from groundscan.validation.scale_shadow_report import _channel_residuals

    seen: dict[str, float] = {}
    for group in ("train", "validation"):
        for path in sorted((VENDOR_ROOT / group).glob("*.csv")):
            grid = reconstruct_grid(load_scan(path))
            for channel, residual in _channel_residuals(grid):
                record = compare_residual(residual, source=path.name, channel=channel)
                if record is None or record.regime != REGIME_DEGENERATE:
                    continue
                assert record.candidate_status == "degraded"
                assert record.quantisation_step == 1.0, (
                    "the degenerate residuals are lattice-quantised; that is the "
                    "regime's signature and it must be visible in the record"
                )
                seen[f"{path.name}/{channel}"] = record.contamination_influence
    assert len(seen) == 3
    tomb = seen["Royal Tomb.csv/multiscale_median_3"]
    assert tomb == tomb and tomb > 1.0, tomb
    for key in (
        "Gallery and Tunnel.csv/multiscale_median_3",
        "Gallery and Tunnel.csv/multiscale_median_5",
    ):
        assert seen[key] != seen[key], (
            f"{key}: no robust reference exists, so the influence is undefined -- "
            "which is a stronger warning than a number and must not be smoothed "
            "into one"
        )


def test_the_declarative_census_survives_a_changed_corpus() -> None:
    """The recorded census is a claim about *this* corpus, checked to be one.

    :data:`scale_reference.REAL_RESIDUAL_REGIMES` is the number the activation
    decision was argued from. A test that only re-derived it would let it drift;
    this one makes the drift loud by asserting against the recorded constant, and
    it walks the per-source counts so a fixture that silently stopped producing
    residuals is visible rather than averaged away.
    """
    with tempfile.TemporaryDirectory() as work:
        reports = [
            *synthetic_reports(),
            *vendor_reports(),
            *golden_reports(Path(work), downstream=False),
        ]
    census = residual_census(reports)
    assert census.counts == dict(ref.REAL_RESIDUAL_REGIMES)
    assert census.total == sum(ref.REAL_RESIDUAL_REGIMES.values())
    for source, counts in census.sources.items():
        assert sum(counts.values()) > 0, source
    assert len(census.sources) == 27, sorted(census.sources)


# ---------------------------------------------------------------------------
# The estimator table, on real residuals
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_no_reference_estimator_is_defensible_on_all_three_degenerate_residuals() -> None:
    """The finding that stopped the activation, stated as an exhaustive sweep.

    Two independent failures, both measured on the three real residuals rather
    than on a construction:

    1. **The median-centring family reads exactly zero** on all three. The MAD
       and the IQR are zero by construction and Sn's median-of-medians with
       them. Reporting zero for a population whose own dispersion is 0.82 erases
       the detections rather than merely inflating the threshold, which is
       strictly worse than the breakdown-0 number it would replace.
       (``Qn`` is the *quantum* on Royal Tomb rather than zero -- its median
       pairwise difference is 1 count -- which is a different failure, not a
       better answer: it is the lattice reporting itself, not the residual's
       spread. ``absdev_q75`` is non-zero on Royal Tomb for the same reason: its
       atom is lighter there.)
    2. **The candidates that stay non-zero disagree by an order of magnitude**
       on the same sample, so no reference table can adjudicate between them.
    """
    from groundscan.core.grid import reconstruct_grid
    from groundscan.services.single_scan import load_scan
    from groundscan.validation.fixtures import VENDOR_ROOT
    from groundscan.validation.scale_shadow_report import _channel_residuals

    residuals: list[tuple[str, np.ndarray]] = []
    for name, group in (("Royal Tomb.csv", "train"), ("Gallery and Tunnel.csv", "validation")):
        grid = reconstruct_grid(load_scan(VENDOR_ROOT / group / name))
        for channel, residual in _channel_residuals(grid):
            if residual_regime(residual)[0] == REGIME_DEGENERATE:
                residuals.append((f"{name}/{channel}", residual[np.isfinite(residual)]))
    assert len(residuals) == 3

    for label, values in residuals:
        for name in ("mad", "iqr", "sn"):
            assert ref.REFERENCE_ESTIMATORS[name](values) == 0.0, f"{name} on {label}"
    gallery = {label: values for label, values in residuals if label.startswith("Gallery")}
    assert len(gallery) == 2
    for label, values in gallery.items():
        assert ref.REFERENCE_ESTIMATORS["qn"](values) == 0.0, label
        assert ref.absdev_quantile_scale(values, 0.75) == 0.0, label
    tomb = next(values for label, values in residuals if label.startswith("Royal Tomb"))
    assert ref.qn_scale(tomb) == pytest.approx(ref.QN_C, rel=1e-9), (
        "on Royal Tomb Qn reports the lattice quantum times its consistency "
        "multiplier, not the residual spread: the median pairwise difference is "
        "exactly one count"
    )

    finite = {
        name: ref.REFERENCE_ESTIMATORS[name](tomb)
        for name in ("std", "absdev_q75", "absdev_q90", "absdev_q95", "trimmed_std_10")
    }
    positive = {k: v for k, v in finite.items() if v == v and v > 0.0}
    assert len(positive) == 5
    assert max(positive.values()) / min(positive.values()) > 3.0, positive


def test_the_pre_activation_estimator_and_the_shipped_one_agree_on_the_whole_corpus() -> None:
    """The shadow's own consistency check, per residual rather than per run.

    ``compare_residual`` reads the pre-activation estimator from a verbatim copy
    and the activated one from production. If the activation moved a number on a
    corpus residual, this is where it appears -- and the census says it does not,
    which is the strongest statement Stage 3 can make about its own risk.
    """
    for report in [*synthetic_reports(), *vendor_reports()]:
        for record in report.comparisons:
            assert not record.scale_changed, (
                f"{record.source}/{record.channel}: {record.legacy_scale} -> "
                f"{record.candidate_scale} in the {record.regime} regime"
            )
            assert record.legacy_status == record.candidate_status, record.channel


# ---------------------------------------------------------------------------
# The estimator table, generated rather than transcribed
# ---------------------------------------------------------------------------


def test_the_estimator_table_reports_a_ratio_against_the_known_clean_scale() -> None:
    """Every row that has an independently known clean scale carries its ratio.

    The table is generated from the reference module, so a candidate added there
    appears in the decision without anybody remembering to re-run a spreadsheet.
    """
    table = ref.estimator_table()
    with_known = [row for row in table["cases"] if row["clean_scale"]]
    assert with_known
    for row in with_known:
        assert any(
            entry.get("ratio_to_clean") is not None
            for name, entry in row.items()
            if isinstance(entry, dict) and "value" in entry
        ), row["name"]


def test_the_shipped_estimator_is_recorded_verbatim_and_is_not_production() -> None:
    """The baseline copy must stay a copy.

    It is what every "before" number in the shadow comes from. If it imported
    production it would track the code under test and the comparison would
    silently become ``x == x``.
    """
    import numpy as np

    from groundscan._util import robust_scale_with_status

    values = np.random.default_rng(1).normal(0.0, 1.0, 4000)
    before = shipped_status_estimate(values)
    after = robust_scale_with_status(values)
    assert before.legacy_scale == after.legacy_scale
    # And the one input where they part company is a dust field, because that is
    # the only place the pre-activation absolute test could misread a real
    # dispersion as no dispersion at all.
    dust = np.random.default_rng(2).normal(0.0, 1e-15, 4000)
    assert shipped_status_estimate(dust).legacy_scale == 1.0
    assert robust_scale_with_status(dust).legacy_scale != 1.0


def test_downstream_impact_uses_identical_configuration_on_both_sides() -> None:
    """The comparison is a controlled one or it is nothing.

    Same scan, same config, same seeds, one variable. Asserted structurally by
    checking that a run under each estimator reports the same number of
    candidates on a corpus scan whose scale did not change -- which is what
    "controlled" means operationally.
    """
    from groundscan.services.single_scan import load_scan
    from groundscan.validation.fixtures import VENDOR_ROOT

    scan = load_scan(VENDOR_ROOT / "validation" / "Iron Box.csv")
    impact = compare_downstream(scan, source="Iron Box.csv")
    assert impact.candidate_count_legacy == impact.candidate_count_candidate
    assert impact.count_delta == 0
    assert not impact.field_deltas

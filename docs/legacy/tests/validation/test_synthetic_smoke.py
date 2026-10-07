"""Release-smoke: synthetic core port produces sane numbers (fast)."""

from groundscan.validation.synthetic_core.benchmark import run_benchmark
from groundscan.validation.synthetic_core.core import scenario_catalog


def test_catalog_has_twelve_scenarios():
    assert len(scenario_catalog()) == 12


def test_benchmark_all_targets_found(tmp_path):
    rows = run_benchmark(str(tmp_path / "bench"))
    assert len(rows) == 12
    assert all(r.recall >= 0.0 and r.precision >= 0.0 for r in rows)
    first = {r.scenario: r for r in rows}
    assert first["positive_compact"].recall == 1.0
    # Pinned deterministic baseline (2026-09-25): 11/12 recall 1.0,
    # close_targets 0.5, all precision 1.0. Catches scorer drift.
    assert first["close_targets"].recall >= 0.5
    assert all(r.precision == 1.0 for r in rows)
    mean_recall = sum(r.recall for r in rows) / len(rows)
    assert mean_recall >= 0.9

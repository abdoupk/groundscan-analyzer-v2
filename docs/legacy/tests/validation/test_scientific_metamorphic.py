"""Scientific metamorphic/invariance validation (P3).

ScanData-space pairs through the public pipeline against frozen relation
specs. Array-space transform algebra is pinned in
tests/unit/test_math_contracts.py; this file asserts pipeline-level
relations (TOLERANCE), provenance flags (FLAGS_ONLY), and records
review-only transforms (REVIEW_REQUIRED).
"""

import numpy as np

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.validation.synthetic_core.core import generate_scan, scenario_catalog
from groundscan.validation.synthetic_core.metamorphic import (
    MIRROR_POSITION_TOLERANCE_M,
    evaluate_metamorphic_pair,
    flip_x_scan,
    flip_y_scan,
    index_frame_scan,
    rot90_scan,
    rot180_scan,
    translate_scan,
)

CONFIG = AnalysisConfig()
# Audit note: multiple_targets is the pairing-stress case -- flips reverse
# detection order, so pairing must be by mirrored proximity, never by id.
PAIR_SCENARIOS = ("positive_compact", "linear_tunnel", "rotated_tunnel", "multiple_targets")


def _run(scan, label, tmp_path):
    _, _, candidates = analyze_scan(
        scan, tmp_path / label, label=label, config=CONFIG, write_outputs=False
    )
    return candidates


def _extent_sums(scan):
    x = np.asarray(scan.x, dtype=float)
    y = np.asarray(scan.y, dtype=float)
    return float(np.nanmin(x) + np.nanmax(x)), float(np.nanmin(y) + np.nanmax(y))


def test_mirror_tolerance_constant_is_tight():
    assert MIRROR_POSITION_TOLERANCE_M == 0.01


def test_flip_x_mirrors_positions_preserves_scores(tmp_path):
    failures = []
    for name in PAIR_SCENARIOS:
        scenario = next(s for s in scenario_catalog() if s.name == name)
        base = _run(generate_scan(scenario)[0], f"{name}-base", tmp_path)
        moved_scan = flip_x_scan(generate_scan(scenario)[0])
        x_sum, _ = _extent_sums(moved_scan)
        moved = _run(moved_scan, f"{name}-flipx", tmp_path)
        record = evaluate_metamorphic_pair(base, moved, "flip_x", x_sum=x_sum)
        failures.extend(f"{name}: {f}" for f in record["failures"])
    assert failures == []


def test_translate_shifts_positions_preserves_scores(tmp_path):
    failures = []
    for name in PAIR_SCENARIOS:
        scenario = next(s for s in scenario_catalog() if s.name == name)
        base = _run(generate_scan(scenario)[0], f"{name}-base", tmp_path)
        moved = _run(
            translate_scan(generate_scan(scenario)[0], 5.0, -3.0),
            f"{name}-shift",
            tmp_path,
        )
        record = evaluate_metamorphic_pair(base, moved, "translate", shift=(5.0, -3.0))
        failures.extend(f"{name}: {f}" for f in record["failures"])
    assert failures == []


def test_flip_y_and_rot180_with_row_order_caveat(tmp_path):
    failures = []
    for name in PAIR_SCENARIOS:
        scenario = next(s for s in scenario_catalog() if s.name == name)
        base = _run(generate_scan(scenario)[0], f"{name}-base", tmp_path)
        moved_y_scan = flip_y_scan(generate_scan(scenario)[0])
        _, y_sum = _extent_sums(moved_y_scan)
        moved_y = _run(moved_y_scan, f"{name}-flipy", tmp_path)
        record = evaluate_metamorphic_pair(base, moved_y, "flip_y", y_sum=y_sum)
        failures.extend(f"{name}/flip_y: {f}" for f in record["failures"])
        moved_r_scan = rot180_scan(generate_scan(scenario)[0])
        x_sum, y_sum_r = _extent_sums(moved_r_scan)
        moved_r = _run(moved_r_scan, f"{name}-rot180", tmp_path)
        record = evaluate_metamorphic_pair(base, moved_r, "rot180", x_sum=x_sum, y_sum=y_sum_r)
        failures.extend(f"{name}/rot180: {f}" for f in record["failures"])
    assert failures == []


def test_index_frame_flips_provenance_flags_only(tmp_path):
    failures = []
    for name in ("positive_compact", "linear_tunnel"):
        scenario = next(s for s in scenario_catalog() if s.name == name)
        base = _run(generate_scan(scenario)[0], f"{name}-base", tmp_path)
        moved = _run(index_frame_scan(generate_scan(scenario)[0]), f"{name}-index", tmp_path)
        record = evaluate_metamorphic_pair(base, moved, "index_frame")
        failures.extend(f"{name}: {f}" for f in record["failures"])
    assert failures == []


def test_rot90_is_review_only_but_crash_free(tmp_path):
    scenario = next(s for s in scenario_catalog() if s.name == "linear_tunnel")
    base = _run(generate_scan(scenario)[0], "tunnel-base", tmp_path)
    moved = _run(rot90_scan(generate_scan(scenario)[0]), "tunnel-rot90", tmp_path)
    record = evaluate_metamorphic_pair(base, moved, "rot90")
    assert record["strength"] == "review_required"
    assert record["finite_scores"] is True
    assert record["passes"] is True


def test_transform_helpers_never_mutate_input():
    scenario = next(s for s in scenario_catalog() if s.name == "positive_compact")
    scan, _ = generate_scan(scenario)
    x_before = np.asarray(scan.x, dtype=float).copy()
    y_before = np.asarray(scan.y, dtype=float).copy()
    flip_x_scan(scan)
    flip_y_scan(scan)
    translate_scan(scan, 5.0, -3.0)
    rot180_scan(scan)
    rot90_scan(scan)
    index_frame_scan(scan)
    np.testing.assert_array_equal(np.asarray(scan.x, dtype=float), x_before)
    np.testing.assert_array_equal(np.asarray(scan.y, dtype=float), y_before)

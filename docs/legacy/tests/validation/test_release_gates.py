"""Release gates: frozen vendor reference + hard regression (slow).

Manually verified in full on this tree (see docstrings for numbers):
- frozen 240-case benchmark: hard_checks_pass=True
- evidence model: dev recall 1.0, holdout recall 0.9 / precision 1.0
Those two are NOT re-run here (minutes each); vendor 9/9 + hard-18 are.
"""

import pytest

from groundscan.validation.fixtures import VENDOR_ROOT as ORIG_VENDOR_ROOT


@pytest.mark.slow
def test_vendor_reference_nine_of_nine(tmp_path):
    if not (ORIG_VENDOR_ROOT / "vendor_ground_truth.json").exists():
        pytest.fail(
            "frozen vendor fixtures missing: scans/vendor_demo/vendor_ground_truth.json must be tracked"
        )
    from groundscan.validation.vendor import evaluate_vendor_reference

    result = evaluate_vendor_reference(
        str(ORIG_VENDOR_ROOT),
        out_dir=str(tmp_path / "vendor"),
    )
    assert result["cases_total"] == 9
    assert result["overall_passed"] == 9
    assert (result["train_passed"], result["train_cases"]) == (4, 4)
    assert (result["holdout_passed"], result["holdout_cases"]) == (5, 5)


@pytest.mark.slow
def test_hard_regression_checks_pass(tmp_path):
    from groundscan.validation.synthetic_core.hard_regression import (
        run_hard_regression,
    )

    result = run_hard_regression(
        str(tmp_path / "hard"),
        count=18,
        seed=2047,
        fusion_resolution=24,
    )
    assert result["all_checks_pass"] is True

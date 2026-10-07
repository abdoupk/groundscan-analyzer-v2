"""Scientific adversarial/negative validation (P2).

Target-free hostile scans through the public pipeline, evaluated at the
documented screening operating point with the frozen four-bin model.
Structured negatives (smooth noise, gradients) may retain review
candidates within allowance -- that is a documented limitation, not a
false positive and never field evidence of anything.
"""

from groundscan.validation.synthetic_core.negative import (
    all_negative_cases,
    run_negative_case,
)
from groundscan.validation.synthetic_core.oracles import (
    DOCUMENTED_LIMITATION,
    EXPECTED_BEHAVIOR,
    FALSE_POSITIVE,
    IMPLEMENTATION_REGRESSION,
    classify_negative,
)


def evaluate_negative_case(case, tmp_path, *, policy=None):
    """Test-local alias of the library case runner (single source of truth)."""
    return run_negative_case(case, tmp_path, policy=policy)


def test_negative_families_within_frozen_allowances(tmp_path):
    failures = []
    for case in all_negative_cases():
        record = evaluate_negative_case(case, tmp_path)
        if not record["passes"]:
            failures.append(f"{case.case_id}: {record['verdict']} -- {record['verdict_detail']}")
    assert failures == []


def test_smooth_noise_is_limitation_not_false_positive(tmp_path):
    """The object-mimic family must land in DOCUMENTED_LIMITATION or EXPECTED."""
    from groundscan.validation.synthetic_core.negative import smooth_noise_cases

    for case in smooth_noise_cases():
        record = evaluate_negative_case(case, tmp_path)
        assert record["verdict"] in (DOCUMENTED_LIMITATION, EXPECTED_BEHAVIOR)
        assert record["verdict"] != FALSE_POSITIVE or not record["passes"]


def test_classifier_bins_are_reachable():
    assert classify_negative("white_noise_empty", 0)[0] == EXPECTED_BEHAVIOR
    assert classify_negative("smooth_noise", 2)[0] == DOCUMENTED_LIMITATION
    assert classify_negative("smooth_noise", 9)[0] == FALSE_POSITIVE
    assert classify_negative("white_noise_empty", 0, crashed=True)[0] == (IMPLEMENTATION_REGRESSION)
    assert classify_negative("nan_block", 0, nonfinite_outputs=1)[0] == (IMPLEMENTATION_REGRESSION)
    assert classify_negative("no-such-family", 0)[0] == IMPLEMENTATION_REGRESSION


def test_negative_runs_are_deterministic(tmp_path):
    from groundscan.validation.synthetic_core.negative import white_noise_case

    first = evaluate_negative_case(white_noise_case(), tmp_path)
    second = evaluate_negative_case(white_noise_case(), tmp_path)
    assert first["retained_candidates"] == second["retained_candidates"]
    assert first["verdict"] == second["verdict"]

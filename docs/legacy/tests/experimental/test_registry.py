"""Experimental registry wiring: every runner resolves with valid kwargs (fast, no execution)."""

import inspect

from groundscan_research import EXPERIMENTAL_RUNNERS, RESEARCH_SUITES


def _resolve(dotted):
    module_name, func_name = dotted.split(":")
    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)


def test_registry_covers_all_facades():
    from groundscan_research import RESEARCH_SUITES

    facades = {dotted.split(":")[0].rsplit(".", 1)[-1] for _, dotted, _, _ in EXPERIMENTAL_RUNNERS}
    labels = [label for label, _, _, _ in EXPERIMENTAL_RUNNERS]
    assert len(labels) == len(set(labels)), "suite labels must be unique"
    assert set(RESEARCH_SUITES) <= facades, (
        f"facades without runner: {set(RESEARCH_SUITES) - facades}"
    )


def test_registry_runners_resolve_with_valid_kwargs():
    assert len(EXPERIMENTAL_RUNNERS) >= 5
    for label, dotted, smoke_kwargs, full_kwargs in EXPERIMENTAL_RUNNERS:
        func = _resolve(dotted)
        params = inspect.signature(func).parameters
        for kwargs in (smoke_kwargs, full_kwargs):
            assert isinstance(kwargs, dict)
            unknown = set(kwargs) - set(params)
            assert not unknown, f"{label}: unknown kwargs {unknown}"
        assert "out_dir" in params or "out" in params, f"{label}: no out dir param"


def test_research_suites_still_listed():
    assert set(RESEARCH_SUITES) == {
        "registration_atlas",
        "registration_recovery",
        "cross_scan_evidence",
        "generator_generalization",
        "background_separation",
    }

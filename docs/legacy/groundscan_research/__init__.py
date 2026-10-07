"""Research-only experiments. Never imported by groundscan/.

Suites (all non-gating; see facades for entry points):
registration_atlas, registration_recovery, cross_scan_evidence,
generator_generalization, background_separation.
"""

RESEARCH_SUITES: tuple[str, ...] = (
    "registration_atlas",
    "registration_recovery",
    "cross_scan_evidence",
    "generator_generalization",
    "background_separation",
)

# (label, "module:attribute" dotted runner, smoke kwargs, full kwargs).
# Smoke kwargs are tiny (1 seed, count 1-2, low resolution) so
# `validate experimental` finishes in minutes. Full kwargs are moderate
# research sizes — still non-gating. Runners must accept out_dir/out as
# their first positional arg and return a JSON-serializable dict.
EXPERIMENTAL_RUNNERS: tuple[tuple[str, str, dict, dict], ...] = (
    (
        "registration_semantics",
        "groundscan_research.registration_atlas:run_registration_semantics_benchmark",
        {"resolution": 20},
        {},
    ),
    (
        "registration_robustness",
        "groundscan_research.registration_recovery:run_registration_robustness_audit",
        {"count_per_family": 1, "resolution": 20},
        {"count_per_family": 4, "resolution": 32},
    ),
    (
        "cross_scan_evidence",
        "groundscan_research.cross_scan_evidence:run_cross_scan_evidence_audit",
        {"count_per_family": 1, "fusion_resolution": 20},
        {"count_per_family": 4, "fusion_resolution": 32},
    ),
    (
        "broad_response",
        "groundscan_research.generator_generalization:run_broad_response_representation_audit",
        {"seeds": (8601,), "count": 2},
        {"seeds": (8601, 8602), "count": 8},
    ),
    (
        "background_separation",
        "groundscan_research.background_separation:run_background_separation_audit",
        {"seeds": (8811,), "count": 2},
        {"seeds": (8811, 8812), "count": 8},
    ),
)

__all__ = ["RESEARCH_SUITES", "EXPERIMENTAL_RUNNERS"]

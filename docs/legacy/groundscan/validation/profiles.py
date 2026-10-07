"""Validation suite profiles (plain data, no heavy imports).

Profiles:
- fast: ``tests/unit`` only. Quick gating check for everyday development.
- full: ``tests/unit`` + ``tests/integration`` + ``tests/regression``.
  Broader correctness check before merging larger changes.
- release: frozen + vendor + evidence + golden suites under
  ``tests/validation`` (plus unit/integration/regression). Gating for
  releases; asserts behavior preservation on frozen reference sets.
- experimental: ``groundscan_research/*`` plus ``tests/experimental``.
  Explicitly non-gating exploratory work; failures never block release.
"""

from __future__ import annotations

#: Fast profile: unit tests only.
FAST_SUITES: list[str] = ["tests/unit"]

#: Full profile: unit + integration + regression.
FULL_SUITES: list[str] = ["tests/unit", "tests/integration", "tests/regression"]

#: Release profile: unit + integration + regression + the frozen
#: validation suites (schemas, goldens, equivalence, vendor/evidence gates).
RELEASE_SUITES: list[str] = [
    "tests/unit",
    "tests/integration",
    "tests/regression",
    "tests/validation",
]

#: Exact release enumeration: (step label, pytest args). The release gate is
#: precisely these 7 pytest steps in order; measured wall times on the
#: reference box: unit ~4s, integration ~5s, regression ~1s, contracts ~25s,
#: goldens ~15s, equivalence ~13s, release-gates ~25s. Everything stays
#: locally reproducible (no CI-only gates).
RELEASE_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("unit", ["tests/unit", "-q"]),
    ("integration", ["tests/integration", "-q"]),
    ("regression", ["tests/regression", "-q"]),
    (
        "contracts",
        ["tests/validation/test_schemas.py", "tests/validation/test_synthetic_smoke.py", "-q"],
    ),
    ("goldens", ["tests/validation/test_golden_outputs.py", "-q"]),
    ("equivalence", ["tests/validation/test_equivalence.py", "-q"]),
    ("release-gates", ["tests/validation/test_release_gates.py", "-q"]),
)

#: Experimental profile: research-only suites; non-gating by definition.
EXPERIMENTAL_SUITES: list[str] = ["groundscan_research", "tests/experimental"]

# The science profile's suite list is not carried here: `cli/validate.py`
# drives it through `validation.scientific.run_science`, which owns both the
# suite wiring and the graduation-rule record (status: RULE DOCUMENTED,
# graduation NOT PERFORMED). See also docs/validation-gates.md.

__all__ = [
    "FAST_SUITES",
    "FULL_SUITES",
    "RELEASE_SUITES",
    "RELEASE_STEPS",
    "EXPERIMENTAL_SUITES",
]

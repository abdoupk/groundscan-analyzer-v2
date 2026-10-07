"""Research boundary: groundscan/ never imports groundscan_research/ (fast).

Experimental suites run only via `groundscan validate experimental`
(non-gating) and `tests/experimental/test_registry.py`. Production imports
of research code would silently couple release behavior to experiments.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROD = ROOT / "groundscan"


def test_production_never_imports_research():
    offenders: list[str] = []
    for path in PROD.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "groundscan_research" in line:
                # Allowed exceptions:
                # - validation/profiles.py: docstring describing the runner registry.
                # - cli/validate.py: function-local `from groundscan_research
                #   import EXPERIMENTAL_RUNNERS` inside the non-gating
                #   `validate experimental` handler (never at import time).
                if path.name == "profiles.py":
                    continue
                if path.name == "validate.py" and "EXPERIMENTAL_RUNNERS" in line:
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")
    assert offenders == [], f"production imports research: {offenders}"


def test_wheel_excludes_research():
    import fnmatch

    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: tomllib is 3.11+ (tomli ships with pytest there)
        import tomli as tomllib

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(pyproject)
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]
    # Assert setuptools glob semantics, not a literal string: no pattern may
    # match groundscan_research (note "groundscan*" would wrongly match it),
    # while the production package and its subpackages stay covered.
    assert not any(
        fnmatch.fnmatchcase("groundscan_research", pat)
        or fnmatch.fnmatchcase("groundscan_research.foo", pat)
        for pat in include
    ), f"wheel would ship research: {include}"
    assert any(fnmatch.fnmatchcase("groundscan", pat) for pat in include)
    assert any(fnmatch.fnmatchcase("groundscan.core", pat) for pat in include)

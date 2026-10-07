"""Shared pytest options: explicit golden-update mechanism.

`pytest --update-goldens` (optionally `--update-goldens=<case_id>`) is the
controlled replacement for ambient `GOLDEN_UPDATE=1`. It refuses to run when
CI is detected (CI/GITHUB_ACTIONS env set) so update mode cannot execute in
CI. Legacy `GOLDEN_UPDATE` env remains honored locally for compatibility.
"""

from __future__ import annotations

import os


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens",
        action="store",
        nargs="?",
        const="1",
        default=None,
        metavar="[CASE_ID]",
        help="Regenerate golden baselines (local only; blocked in CI).",
    )


def pytest_configure(config):
    requested = config.getoption("--update-goldens", default=None)
    if requested is None:
        return
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError(
            "--update-goldens is blocked in CI; regenerate goldens locally with review."
        )
    # Bridge the explicit flag into the existing GOLDEN_UPDATE protocol.
    os.environ["GOLDEN_UPDATE"] = requested

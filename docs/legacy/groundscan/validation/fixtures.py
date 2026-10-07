"""Repo-local fixture locations (no machine-specific paths).

The 9 frozen OKM vendor files + manifest are vendored under
``scans/vendor_demo/``. ``GROUNDSCAN_VENDOR_ROOT`` may override the
location (e.g. to point at an external copy); otherwise the in-repo copy
is used so clones work out of the box.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

VENDOR_ROOT = Path(os.environ.get("GROUNDSCAN_VENDOR_ROOT", _REPO_ROOT / "scans" / "vendor_demo"))

VENDOR_TRAIN = VENDOR_ROOT / "train"

__all__ = ["VENDOR_ROOT", "VENDOR_TRAIN"]

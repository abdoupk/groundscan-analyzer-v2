"""
Adapter interface.

Adding support for a new device means writing a new class here that
implements `can_read` and `read` — nothing else in the codebase changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import ScanData

PathLike = str | Path

#: Refuse scan inputs larger than this (100 MB of text). OKM exports are
#: kilobytes to low megabytes; anything larger is a runaway log or a
#: wrong-file selection, and `read_text` would hold it all in memory twice
#: (raw text plus parsed rows). The CLI maps the ValueError to exit 1.
MAX_INPUT_BYTES = 100_000_000


def check_input_size(path: PathLike) -> int:
    """Return the file size, raising ValueError when it exceeds the cap."""
    size = Path(path).stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(
            f"{path}: input size {size} bytes exceeds the "
            f"{MAX_INPUT_BYTES}-byte scan cap; pass a single scan export"
        )
    return size


class ScannerAdapter(ABC):
    """Base class every device adapter must implement."""

    #: short machine-readable identifier, e.g. "rover", "generic_csv"
    name: str = "base"

    @abstractmethod
    def can_read(self, path: PathLike) -> bool:
        """
        Cheap, non-destructive check: could this adapter plausibly parse
        this file? Should never raise — return False on any doubt.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, path: PathLike) -> ScanData:
        """Parse `path` fully and return a standard ScanData instance.

        Numeric contract: every array in the returned ScanData is
        finite-or-NaN (±Inf is coerced to NaN at the adapter exit, so
        downstream statistics never see infinities). Malformed cells
        become NaN and are reported by the field-quality gate.
        """
        raise NotImplementedError

    def _read_text(self, path: PathLike) -> str:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")

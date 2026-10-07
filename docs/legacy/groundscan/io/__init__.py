from .base import PathLike, ScannerAdapter
from .generic_csv import GenericCSVAdapter
from .rover import RoverAdapter

#: Adapters tried in this order by `detect_adapter`. Add new devices here.
REGISTRY = [RoverAdapter(), GenericCSVAdapter()]


def detect_adapter(path: PathLike) -> ScannerAdapter:
    """Return the first adapter in REGISTRY that claims it can read `path`."""
    for adapter in REGISTRY:
        if adapter.can_read(path):
            return adapter
    raise ValueError(
        f"No registered adapter can read {path!s}. "
        f"Registered adapters: {[a.name for a in REGISTRY]}"
    )


__all__ = ["ScannerAdapter", "GenericCSVAdapter", "RoverAdapter", "REGISTRY", "detect_adapter"]

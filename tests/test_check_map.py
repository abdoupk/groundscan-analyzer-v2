"""The map hook degrades loudly, never silently, when offline.

Regression tests over the hook with the network stubbed at the `gh api`
boundary: a transport failure skips with notice, while any other `gh`
failure still fails loudly.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import types

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, types.ModuleType]:
    """Import the hook scripts with an isolated module path.

    Returns:
        The `map_body` and `check_map` modules.
    """
    monkeypatch.syspath_prepend(str(SCRIPTS))
    map_body = importlib.import_module("map_body")
    check_map = importlib.import_module("check_map")
    return map_body, check_map


def test_transport_failure_skips_with_notice(
    hook: tuple[types.ModuleType, types.ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    map_body, check_map = hook

    def failing(_args: list[str]) -> bytes:
        message = "gh api failed with exit code 1: dial tcp 140.82.121.5:443: connectex"
        raise SystemExit(message)

    monkeypatch.setattr(map_body, "api", failing)
    assert check_map.main() == 0
    assert "network-unavailable" in capsys.readouterr().out


def test_api_error_still_fails_loudly(
    hook: tuple[types.ModuleType, types.ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_body, check_map = hook

    def denied(_args: list[str]) -> bytes:
        message = "gh api failed with exit code 4: HTTP 404: Not Found"
        raise SystemExit(message)

    monkeypatch.setattr(map_body, "api", denied)
    with pytest.raises(SystemExit):
        check_map.main()

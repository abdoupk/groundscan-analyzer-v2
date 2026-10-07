"""Installed-wheel release integrity: runtime assets must be importable data.

Uses importlib.resources so the test passes from a source checkout AND from
an installed wheel; the clean-room job installs only the wheel from a
directory without the source tree.
"""

from __future__ import annotations

import importlib.resources as resources


def _assert_data_file(package: str, *parts: str) -> None:
    ref = resources.files(package)
    for part in parts:
        ref = ref / part
    assert ref.is_file(), f"missing package data: {package}/{'/'.join(parts)}"
    assert ref.stat().st_size > 0, f"empty package data: {package}/{'/'.join(parts)}"


def test_validation_schemas_ship():
    _assert_data_file("groundscan.validation", "schemas", "analysis.schema.json")
    _assert_data_file("groundscan.validation", "schemas", "site.schema.json")


def test_research_excluded_from_production_import():
    import groundscan

    assert "groundscan_research" not in str(getattr(groundscan, "__file__", ""))

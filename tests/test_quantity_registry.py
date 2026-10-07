"""Quantity registry: one home, one owner, one definition per quantity.

The registry carries every quantity's definition, derivation, unit,
population and definitional bounds. A contribution adding a quantity with
no registry entry fails here, and no quantity exists without exactly one
owner. Bound checks read the registry rather than restating numbers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from groundscan_analyzer import document, quantity_registry

if TYPE_CHECKING:
    from pydantic import BaseModel

FieldRef = tuple[str, str]


def field_kinds() -> dict[FieldRef, str | None]:
    """Classify every record field as a quantity name or structural.

    Returns:
        Quantity name per quantity field, None per structural field.
    """
    kinds: dict[FieldRef, str | None] = {
        ("Detection", "identity"): None,
        ("Detection", "number"): None,
        ("Detection", "polarity"): None,
        ("Detection", "birth_level"): None,
        ("Detection", "cells"): None,
        ("Detection", "cell_count"): "component-size-in-cells",
        ("Detection", "scan_local_position"): "scan-local-position",
        ("Detection", "field_position"): "field-position",
        ("Detection", "no_field_position_reason"): "field-position",
        ("Detection", "solidity"): "solidity",
        ("Detection", "compactness"): "compactness",
        ("Detection", "field_area"): "field-area",
        ("Detection", "field_area_withheld"): "field-area",
        ("Detection", "depth"): "depth-interval",
        ("Detection", "lattice_boundary_cells"): "lattice-boundary-contact",
        ("Detection", "padding_adjacent_cells"): "padding-adjacency-contact",
        ("Hierarchy", "connectivity"): None,
        ("Hierarchy", "level_kind"): None,
        ("Hierarchy", "cut_guarantee"): None,
        ("Hierarchy", "measured_cells"): None,
        ("Hierarchy", "cells_in_hierarchy"): None,
        ("Hierarchy", "levels_positive"): None,
        ("Hierarchy", "levels_negative"): None,
        ("Hierarchy", "detections"): None,
        ("Hierarchy", "parents"): None,
        ("Hierarchy", "detection_counts"): None,
        ("Hierarchy", "component_counts"): None,
        ("DepthInterval", "minimum"): "depth-interval",
        ("DepthInterval", "maximum"): "depth-interval",
        ("DepthInterval", "kind"): "depth-interval",
        ("DetectionCount", "polarity"): None,
        ("DetectionCount", "count"): "detection-count",
        ("DetectionCount", "denominator"): "detection-count",
        ("DetectionCount", "connectivity"): None,
        ("ComponentCount", "polarity"): "component-count",
        ("ComponentCount", "level"): "component-count",
        ("ComponentCount", "count"): "component-count",
        ("ComponentCount", "denominator"): "component-count",
        ("ComponentCount", "connectivity"): None,
        ("Scale", "span"): "field-position",
        ("Scale", "span_provenance"): "field-position",
        ("Scale", "count"): "field-position",
        ("Scale", "count_provenance"): "field-position",
        ("Scale", "quotient"): "field-position",
        ("ScanLocalAxis", "name"): "scan-local-position",
        ("ScanLocalAxis", "index"): "scan-local-position",
        ("ScanLocalAxis", "provenance"): "scan-local-position",
        ("ScanLocalPosition", "frame"): "scan-local-position",
        ("ScanLocalPosition", "origin"): "scan-local-position",
        ("ScanLocalPosition", "origin_limitation"): "scan-local-position",
        ("ScanLocalPosition", "along_line"): "scan-local-position",
        ("ScanLocalPosition", "across_lines"): "scan-local-position",
        ("FieldAxis", "name"): "field-position",
        ("FieldAxis", "coordinate"): "field-position",
        ("FieldAxis", "scale"): "field-position",
        ("FieldAxis", "provenance"): "field-position",
        ("FieldPosition", "frame"): "field-position",
        ("FieldPosition", "origin"): "field-position",
        ("FieldPosition", "origin_limitation"): "field-position",
        ("FieldPosition", "along_line"): "field-position",
        ("FieldPosition", "across_lines"): "field-position",
    }
    models: dict[str, type[BaseModel]] = {
        "Detection": document.Detection,
        "Hierarchy": document.Hierarchy,
        "DepthInterval": document.DepthInterval,
        "DetectionCount": document.DetectionCount,
        "ComponentCount": document.ComponentCount,
        "Scale": document.Scale,
        "ScanLocalAxis": document.ScanLocalAxis,
        "ScanLocalPosition": document.ScanLocalPosition,
        "FieldAxis": document.FieldAxis,
        "FieldPosition": document.FieldPosition,
    }
    seen = {(name, field) for name, model in models.items() for field in model.model_fields}
    assert seen == set(kinds), f"unclassified record fields: {seen ^ set(kinds)}"
    return kinds


def test_registry_is_versioned_and_closed() -> None:
    """One version, unique names, unique owners per quantity."""
    assert quantity_registry.QUANTITY_REGISTRY_VERSION == 2
    names = [entry.name for entry in quantity_registry.QUANTITIES]
    assert len(names) == len(set(names))
    assert len(names) == 11


def test_every_quantity_has_exactly_one_entry() -> None:
    """Quantity fields resolve to exactly one registry entry each."""
    by_name: dict[str, list[str]] = {}
    for entry in quantity_registry.QUANTITIES:
        by_name.setdefault(entry.name, []).append(entry.owner)
    for ref, name in field_kinds().items():
        if name is None:
            continue
        assert name in by_name, f"{ref} names no registry quantity"
        assert len(by_name[name]) == 1, f"{name} has owners {by_name[name]}"


def test_no_registry_entry_is_unreferenced() -> None:
    """Every entry owns a quantity the record actually carries."""
    used = {name for name in field_kinds().values() if name is not None}
    for entry in quantity_registry.QUANTITIES:
        assert entry.name in used, f"{entry.name} owns nothing on the record"


def test_bounds_are_ordered_where_both_ends_exist() -> None:
    """A two-ended bound names a non-empty interval."""
    for entry in quantity_registry.QUANTITIES:
        if entry.lower is not None and entry.upper is not None:
            assert entry.lower < entry.upper, f"{entry.name} bound is empty"

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

    Identity facts, withheld reasons, frame scaffolding, guard
    verdicts and declared bounds are structural here: guards live in the
    property world, bounds are declarations rather than measurements,
    while this registry holds analysis quantities and positions.

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
        ("Detection", "scan_payload_hash"): None,
        ("Detection", "shared_frame_position"): "shared-frame-position",
        ("Detection", "no_shared_position_reason"): None,
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
        ("SharedScale", "quotient"): "shared-frame-position",
        ("SharedScale", "declaration_scan"): "shared-frame-position",
        ("SharedScale", "declaration_span"): "shared-frame-position",
        ("SharedScale", "provenance"): "shared-frame-position",
        ("SharedFrameAxis", "name"): "shared-frame-position",
        ("SharedFrameAxis", "index"): "shared-frame-position",
        ("SharedFrameAxis", "scale"): "shared-frame-position",
        ("SharedFramePosition", "frame"): "shared-frame-position",
        ("SharedFramePosition", "origin"): "shared-frame-position",
        ("SharedFramePosition", "origin_limitation"): "shared-frame-position",
        ("SharedFramePosition", "scan_local"): "scan-local-position",
        ("SharedFramePosition", "along_line"): "shared-frame-position",
        ("SharedFramePosition", "across_lines"): "shared-frame-position",
        ("SharedFramePosition", "homogeneous"): "shared-frame-position",
        ("DeclaredRelation", "first"): None,
        ("DeclaredRelation", "second"): None,
        ("DeclaredRelation", "relation"): None,
        ("FrameRelation", "scan"): None,
        ("FrameRelation", "relation_class"): None,
        ("Frame", "name"): None,
        ("Frame", "label"): None,
        ("Frame", "members"): None,
        ("Frame", "relations"): None,
        ("Contradiction", "first"): None,
        ("Contradiction", "second"): None,
        ("Contradiction", "relation"): None,
        ("Contradiction", "expected_class"): None,
        ("Contradiction", "declared_class"): None,
        ("AspectVerdict", "first"): None,
        ("AspectVerdict", "second"): None,
        ("AspectVerdict", "relation"): None,
        ("AspectVerdict", "verdict"): None,
        ("AspectVerdict", "note"): None,
        ("RobustScale", "convention"): None,
        ("RobustScale", "quantile_convention"): None,
        ("RobustScale", "status"): None,
        ("RobustScale", "sigma_mad"): "robust-scale",
        ("RobustScale", "sigma_iqr"): "robust-scale",
        ("RobustScale", "disagreement"): "scale-disagreement",
        ("RobustScale", "tolerance"): "scale-tie-tolerance",
        ("RobustScale", "median_atom_numerator"): "median-atom-fraction",
        ("RobustScale", "median_atom_denominator"): "median-atom-fraction",
        ("ScaleNormalisedView", "status"): None,
        ("ScaleNormalisedView", "reason"): None,
        ("ScaleNormalisedView", "scale"): "robust-scale",
        ("ScaleNormalisedView", "levels_positive"): "scale-normalised-level",
        ("ScaleNormalisedView", "levels_negative"): "scale-normalised-level",
        ("PerturbationBound", "amplitude"): None,
        ("PerturbationBound", "boundedness"): None,
        ("PerturbationBound", "anchor"): None,
        ("DisplacementBound", "amplitude"): None,
        ("DisplacementBound", "boundedness"): None,
        ("MaskInvariance", "status"): None,
        ("MaskInvariance", "reason"): None,
        ("MaskInvariance", "anchor_rule"): None,
        ("MaskInvariance", "background_convention"): None,
        ("MaskInvariance", "precondition"): None,
        ("MaskInvariance", "zero_bound_condition"): None,
        ("MaskInvariance", "sufficiency"): None,
        ("MaskInvariance", "conservativeness"): None,
        ("MaskInvariance", "ordering_invariance"): None,
        ("MaskInvariance", "magnitude_invariance"): None,
        ("RegistrationShift", "dy"): None,
        ("RegistrationShift", "dx"): None,
        ("RegistrationShift", "correlation"): None,
        ("RegistrationShift", "overlap"): None,
        ("RegistrationEvidence", "status"): None,
        ("RegistrationEvidence", "reason"): None,
        ("RegistrationEvidence", "margin"): None,
        ("RegistrationEvidence", "correlation"): None,
        ("RegistrationEvidence", "argmax_dy"): None,
        ("RegistrationEvidence", "argmax_dx"): None,
        ("RegistrationEvidence", "argmax_stable"): None,
        ("RegistrationEvidence", "margin_drift"): None,
        ("RegistrationEvidence", "shift_count"): None,
        ("RegistrationEvidence", "scored_count"): None,
        ("RegistrationEvidence", "accumulation_length"): None,
        ("RegistrationEvidence", "exact_tie_tolerance"): None,
        ("RegistrationEvidence", "deterministic_order"): None,
        ("RegistrationEvidence", "evidence_scope"): None,
        ("RegistrationEvidence", "passing_means"): None,
        ("RegistrationEvidence", "physical_disclaimer"): None,
        ("RegistrationEvidence", "separation_criterion"): None,
        ("RegistrationEvidence", "separation_reason"): None,
        ("RegistrationEvidence", "chance_dy"): None,
        ("RegistrationEvidence", "chance_dx"): None,
        ("RegistrationEvidence", "chance_correlation"): None,
        ("RegistrationEvidence", "chance_note"): None,
        ("RegistrationEvidence", "repeat_limitation"): None,
        ("RegistrationEvidence", "shifts"): None,
        ("RecurrencePair", "first"): None,
        ("RecurrencePair", "second"): None,
        ("RecurrencePair", "eligibility"): None,
        ("RecurrencePair", "reason"): None,
        ("RecurrencePair", "status"): None,
        ("RecurrencePair", "correspondence"): None,
        ("RecurrencePair", "fragility_reason"): None,
        ("RecurrencePair", "repeat_limitation"): None,
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
        "SharedScale": document.SharedScale,
        "SharedFrameAxis": document.SharedFrameAxis,
        "SharedFramePosition": document.SharedFramePosition,
        "DeclaredRelation": document.DeclaredRelation,
        "FrameRelation": document.FrameRelation,
        "Frame": document.Frame,
        "Contradiction": document.Contradiction,
        "AspectVerdict": document.AspectVerdict,
        "RobustScale": document.RobustScale,
        "ScaleNormalisedView": document.ScaleNormalisedView,
        "PerturbationBound": document.PerturbationBound,
        "DisplacementBound": document.DisplacementBound,
        "MaskInvariance": document.MaskInvariance,
        "RegistrationShift": document.RegistrationShift,
        "RegistrationEvidence": document.RegistrationEvidence,
        "RecurrencePair": document.RecurrencePair,
    }
    seen = {(name, field) for name, model in models.items() for field in model.model_fields}
    assert seen == set(kinds), f"unclassified record fields: {seen ^ set(kinds)}"
    return kinds


def test_registry_is_versioned_and_closed() -> None:
    """One version, unique names, unique owners per quantity."""
    assert quantity_registry.QUANTITY_REGISTRY_VERSION == 4
    names = [entry.name for entry in quantity_registry.QUANTITIES]
    assert len(names) == len(set(names))
    assert len(names) == 17


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

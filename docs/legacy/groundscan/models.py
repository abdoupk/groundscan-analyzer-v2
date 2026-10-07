"""Device-agnostic data models shared by adapters and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Coordinate semantics (Remediation Design v2 §5.4, contract K5/K6)
# ---------------------------------------------------------------------------
# Three *independent* axes, kept separate on purpose. v1 conflated them and
# asserted "measured == metres", which is an assumption, not a guarantee:
#
#   provenance  -> "were these numbers produced by a measurement process?"
#   unit        -> "what do the numbers mean?"
#   reliability -> "can a physical area be computed from them to useful accuracy?"
#
# ``grid-cells`` is a frame, not a length: it has no conversion factor.
COORDINATE_UNITS: tuple[str, ...] = ("m", "cm", "mm", "ft", "in", "grid-cells")

METRES_PER_UNIT: dict[str, float] = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "in": 0.0254,
}

#: The unit was declared by the caller.
UNIT_SOURCE_DECLARED = "declared"
#: Nothing was declared, so metres were *assumed* to preserve historical
#: behaviour. The assumption is now explicit and greppable instead of living
#: implicitly inside a human-readable string.
UNIT_SOURCE_ASSUMED_METRES = "assumed-metres"
#: Coordinates are grid indices, not a physical length.
UNIT_SOURCE_GRID_FRAME = "grid-frame"


@dataclass(frozen=True)
class CoordinateSemantics:
    """The three coordinate axes resolved for one scan (v2 §5.4)."""

    provenance: str
    declared_unit: str | None
    effective_unit: str
    unit_source: str
    geometry_reliable: bool
    geometry_reliability_reason: str
    conversion_to_metres: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance,
            "declared_unit": self.declared_unit,
            "effective_unit": self.effective_unit,
            "unit_source": self.unit_source,
            "geometry_reliable": self.geometry_reliable,
            "geometry_reliability_reason": self.geometry_reliability_reason,
            "conversion_to_metres": self.conversion_to_metres,
        }


@dataclass
class ScanMetadata:
    """Free-form but normalized metadata about one scan."""

    device: str | None = None
    date: str | None = None
    time: str | None = None
    soil_type: str | None = None
    dielectric_constant: float | None = None
    relative_permeability: float | None = None
    mineralization_pct: float | None = None
    humidity_pct: float | None = None
    homogeneity_pct: float | None = None
    field_length_m: float | None = None
    field_width_m: float | None = None
    orientation_deg: float | None = None
    line_spacing_m: float | None = None
    point_spacing_m: float | None = None
    scan_pattern: str | None = None
    site_id: str | None = None
    notes: str | None = None
    source_file: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def coordinates_are_metric(self) -> bool:
        """True when both field dimensions are usable positive values."""
        return bool(
            self.field_length_m is not None
            and self.field_width_m is not None
            and self.field_length_m > 0
            and self.field_width_m > 0
        )


@dataclass
class ScanData:
    """
    Device-agnostic representation of one ground scan.

    x/y are physical coordinates when resolved, otherwise raw grid indices.
    z is the device-reported depth estimate and is never treated as verified
    physical depth. signal is the original measured quantity.
    """

    x: np.ndarray[Any, Any]
    y: np.ndarray[Any, Any]
    z: np.ndarray[Any, Any]
    signal: np.ndarray[Any, Any]
    twt_ns: np.ndarray[Any, Any] | None = None
    grid_i: np.ndarray[Any, Any] | None = None
    grid_j: np.ndarray[Any, Any] | None = None
    latitude: np.ndarray[Any, Any] | None = None
    longitude: np.ndarray[Any, Any] | None = None
    coords_are_index_only: bool = False
    # v0.4.2 (audit F-05): three-state coordinate provenance.
    #   "measured": physical coordinates verified by the source (metric columns
    #               with unit-bearing headers, user-asserted spacing, lat/lon).
    #   "derived":  reconstructed from self-reported metadata (e.g. index grid
    #               rescaled by header field dimensions) or unlabeled columns;
    #               metric geometry is NOT independently verified.
    #   "index":    raw grid indices; distances/areas are grid cells, not meters.
    coordinate_provenance: str = "measured"
    # Remediation Design v2 §5.4 (Wave 0): the unit is a *separate* axis from
    # provenance. ``None`` means "not declared", which for ``measured``
    # coordinates historically meant "assume metres" -- that default is kept so
    # behaviour is unchanged, and :attr:`coordinate_semantics` now records it as
    # an explicit assumption rather than an invisible one. Declaring a non-metre
    # length is accepted and normalised to metres once, at ingestion
    # (:func:`normalise_coordinate_units`); refusing good measured data would
    # have been the wrong fix.
    coordinate_unit: str | None = None
    # v2 §5.4: explicit reliability override. ``None`` derives it from
    # provenance, which is the historical (and unchanged) behaviour.
    geometry_reliable: bool | None = None
    metadata: ScanMetadata = field(default_factory=ScanMetadata)

    @property
    def effective_coordinate_provenance(self) -> str:
        """Provenance with the legacy boolean applied at read time.

        v0.4.2 (audit F-05): ``coords_are_index_only`` remains a public field
        that external code may set after construction (bypassing
        ``__post_init__``); when it is set, the coordinates are index-only
        regardless of the stored provenance state.

        v2 §5.4: a declared ``grid-cells`` unit also forces ``index``, because
        "these numbers are grid cells" and "these numbers are indices" are the
        same statement. Resolving it here rather than only in
        :attr:`coordinate_semantics` is what keeps ``geometry_reliable`` exactly
        equal to :func:`is_metric_coordinates` in every reachable state -- the
        two must never disagree, because the latter gates real decisions.
        """
        if self.coords_are_index_only:
            return "index"
        if self.coordinate_unit == "grid-cells":
            return "index"
        return self.coordinate_provenance

    @property
    def coordinate_semantics(self) -> CoordinateSemantics:
        """Resolve the three coordinate axes for this scan (v2 §5.4 matrix).

        Backward compatibility is load-bearing here. The matrix's
        "measured + unknown -> warn + reject" row is **not** active in Wave 0:
        today an undeclared unit on measured coordinates means metres, and
        ``is_metric_coordinates`` is True. Changing that would silently move
        every existing scan's ``metric_geometry_reliable`` and its downstream
        gating, which is behaviour activation, not a contract. What Wave 0 does
        is make the assumption *visible* -- ``unit_source == "assumed-metres"``
        -- so a consumer can tell that metres were assumed rather than
        verified, and so the stricter disposition can be activated later as a
        measured decision.

        ``geometry_reliable`` stays equal to ``provenance == "measured"`` in
        every state reachable today, so this property is consistent with
        :func:`is_metric_coordinates` without moving a single value.
        """
        provenance = self.effective_coordinate_provenance
        declared = self.coordinate_unit
        if declared is not None and declared not in COORDINATE_UNITS:
            raise ValueError(
                f"coordinate_unit must be one of {list(COORDINATE_UNITS)} or None, got {declared!r}"
            )

        base_reason = {
            "measured": "physical/metric coordinates available",
            "derived": (
                "coordinates derived from self-reported field dimensions or unlabeled columns; "
                "metric geometry is not independently verified"
            ),
            "index": "x/y are raw grid indices; metric distances/areas are not verified",
        }[provenance]
        derived_reliable = provenance == "measured"

        # Index coordinates are a frame, not a length. `effective_coordinate_provenance`
        # has already folded a declared `grid-cells` unit in, so provenance
        # alone decides here.
        if provenance == "index":
            return CoordinateSemantics(
                provenance=provenance,
                declared_unit=declared,
                effective_unit="grid-cells",
                unit_source=UNIT_SOURCE_GRID_FRAME,
                geometry_reliable=False
                if self.geometry_reliable is None
                else self.geometry_reliable,
                geometry_reliability_reason=f"{base_reason}; lengths are grid cells, not metres",
                conversion_to_metres=None,
            )

        if declared is None:
            return CoordinateSemantics(
                provenance=provenance,
                declared_unit=None,
                effective_unit="m",
                unit_source=UNIT_SOURCE_ASSUMED_METRES,
                geometry_reliable=(
                    derived_reliable if self.geometry_reliable is None else self.geometry_reliable
                ),
                geometry_reliability_reason=(
                    f"{base_reason}; no coordinate unit declared, so metres were ASSUMED "
                    "(not verified)"
                    if provenance == "measured"
                    else f"{base_reason}; no coordinate unit declared"
                ),
                conversion_to_metres=None,
            )

        factor = METRES_PER_UNIT[declared]
        return CoordinateSemantics(
            provenance=provenance,
            declared_unit=declared,
            effective_unit="m",
            unit_source=UNIT_SOURCE_DECLARED,
            geometry_reliable=derived_reliable
            if self.geometry_reliable is None
            else self.geometry_reliable,
            geometry_reliability_reason=(
                f"{base_reason}; declared unit {declared!r} "
                + ("already metres" if factor == 1.0 else f"normalised to metres (x{factor:g})")
            ),
            conversion_to_metres=factor if factor != 1.0 else None,
        )

    def __len__(self) -> int:
        return int(len(self.signal))

    def __post_init__(self) -> None:
        if self.twt_ns is not None and len(self.twt_ns) != len(self.signal):
            raise ValueError(
                f"ScanData.twt_ns must be an array of length {len(self.signal)}, "
                f"got {len(self.twt_ns)}"
            )
        allowed = {"measured", "derived", "index"}
        if self.coordinate_provenance not in allowed:
            raise ValueError(
                f"coordinate_provenance must be one of {sorted(allowed)}, "
                f"got {self.coordinate_provenance!r}"
            )
        if self.coordinate_unit is not None and self.coordinate_unit not in COORDINATE_UNITS:
            raise ValueError(
                f"coordinate_unit must be one of {list(COORDINATE_UNITS)} or None, "
                f"got {self.coordinate_unit!r}"
            )
        # Keep the legacy boolean and the provenance state consistent.
        if self.coords_are_index_only:
            self.coordinate_provenance = "index"
        elif self.coordinate_provenance == "index":
            self.coords_are_index_only = True
        n = len(self.signal)
        for name in ("x", "y", "z"):
            arr = getattr(self, name)
            if arr is None or len(arr) != n:
                raise ValueError(
                    f"ScanData.{name} must be an array of length {n} "
                    f"(len(signal)), got {None if arr is None else len(arr)}"
                )


def _provenance_of(scan: ScanData) -> str:
    """Effective coordinate provenance with the legacy default applied."""
    return str(getattr(scan, "effective_coordinate_provenance", "measured"))


def is_metric_coordinates(scan: ScanData) -> bool:
    """True when scan coordinates are verified metric (decision sites use this)."""
    return _provenance_of(scan) == "measured"


def is_derived_coordinates(scan: ScanData) -> bool:
    """True when metric geometry was reconstructed, not independently verified."""
    return _provenance_of(scan) == "derived"


def is_index_only_coordinates(scan: ScanData) -> bool:
    """True when x/y are raw grid indices (distances/areas are grid cells)."""
    return _provenance_of(scan) == "index"


def normalise_coordinate_units(scan: ScanData) -> float | None:
    """Convert *scan*'s x/y to metres once, at ingestion (v2 §5.4).

    Returns the factor applied, or ``None`` when nothing was converted.

    This is a strict no-op for every input reachable before Wave 0: an
    undeclared unit (``None``) and a declared ``"m"`` both return ``None`` and
    leave the arrays untouched, so all existing scans behave identically. The
    new path only runs when a caller explicitly declares a non-metre length.

    A measured centimetre value is *good* data -- v1 proposed refusing it, which
    would have thrown away a real measurement. The actual defect was never
    "non-metre coordinates exist"; it was "non-metre coordinates were silently
    interpreted as metres". Converting here fixes exactly that, and the original
    unit stays recorded on ``scan.coordinate_unit`` for auditability.
    """
    semantics = scan.coordinate_semantics
    factor = semantics.conversion_to_metres
    if factor is None:
        return None
    scan.x = np.asarray(scan.x, dtype=float) * factor
    scan.y = np.asarray(scan.y, dtype=float) * factor
    return factor


@dataclass
class Candidate:
    """One detected anomaly region described in pattern/evidence terms.

    The terminology intentionally avoids material identification. ``confidence``
    remains for API compatibility but is a bounded heuristic pattern-evidence
    score, not a calibrated probability.

    v0.5.1: this dataclass is intentionally still mutable because the
    multi-stage pipeline (extract -> classify -> separate -> gate) enriches
    candidates in place. Prefer :meth:`with_updates` (which uses
    :func:`dataclasses.replace`) for isolated/testable transforms.
    """

    id: int
    x_center: float
    y_center: float
    depth_mean: float
    depth_std: float
    n_points: int
    area_cells: int
    width: float
    height: float
    aspect_ratio: float
    orientation_deg: float
    peak_signal: float
    mean_signal: float
    anomaly_score: float
    shape_class: str
    pattern_hypothesis: str
    confidence: float
    cross_scan_agreement: float | None = None
    notes: str = ""

    # v0.2 rich evidence fields. Defaults keep older client code valid.
    signed_anomaly_mean: float = 0.0
    positive_peak: float = 0.0
    negative_peak: float = 0.0
    polarity: str = "mixed"  # positive / negative / mixed
    anomaly_density: float = 0.0  # |z| above threshold within bbox
    compactness: float = 0.0  # 1.0 ~= compact; lower ~= elongated/irregular
    continuity_score: float = 0.0  # line/region continuity evidence, 0..1
    artifact_score: float = 0.0  # 0..1; higher means more artifact-like
    multiscale_persistence: float = 0.0  # fraction of tested scales supporting anomaly
    evidence_score: float = 0.0  # bounded heuristic evidence, not probability
    scan_count: int = 1
    detection_rate: float = 1.0
    directional_persistence: float = 0.0
    spacing_persistence: float = 0.0
    traversal_persistence: float = 0.0
    polarity_consistency: float = 1.0
    position_stability: float = 1.0
    contributing_scans: list[str] = field(default_factory=list)
    # v0.2.1 geometry/depth robustness. Values are descriptive features in
    # scan-coordinate units unless the input coordinates are verified metric.
    major_extent: float = 0.0
    minor_extent: float = 0.0
    elongation_ratio: float = 1.0
    linearity_score: float = 0.0
    solidity: float = 1.0
    boundary_contact_ratio: float = 0.0
    broadness_score: float = 0.0
    centroid_weighted_x: float = 0.0
    centroid_weighted_y: float = 0.0
    geometry_quality: float = 0.0
    # v0.2.12 reliability provenance. False means x/y geometry is not verified
    # as metric (for example raw grid indices); shape analysis may still be valid.
    metric_geometry_reliable: bool = True
    geometry_reliability_reason: str = "metric-or-physical-coordinates"
    # v0.2.26 unified five-factor soil context copied from scan metadata.
    dielectric_constant: float | None = None
    relative_permeability: float | None = None
    mineralization_pct: float | None = None
    humidity_pct: float | None = None
    homogeneity_pct: float | None = None
    soil_context_completeness: float = 0.0
    mineralization_risk: float = 0.0
    depth_estimate: float = float("nan")
    depth_estimate_std: float = float("nan")
    depth_min: float = float("nan")
    depth_max: float = float("nan")
    depth_range: float = float("nan")
    depth_valid_fraction: float = 0.0
    depth_stability_score: float = 0.0
    depth_relative_dispersion: float = float("nan")
    depth_cross_scan_consistency: float = 1.0
    geometry_consistency: float = 1.0
    multiscan_signal_consistency: float = 0.0
    multiresolution_consensus: float = 0.0
    registration_consistency: float = 1.0
    multi_scan_status: str = "single-scan"
    scale_class: str = "local"  # local / broad
    separation_status: str = "none"  # none / decomposed-consensus
    separation_parent_id: int | None = None
    separation_quality: float = 0.0
    separation_fragment_count: int = 1
    # v0.2.4 quality / false-positive screening. These are auditable heuristics, not probabilities.
    quality_score: float = 0.0
    false_positive_risk: float = 1.0
    screening_score: float = 0.0
    review_status: str = "review"
    quality_flags: list[str] = field(default_factory=list)
    # v0.2.98 operational field-use gate. These are conservative use constraints,
    # not target/material probabilities.
    operational_status: str = "clear"
    operational_flags: list[str] = field(default_factory=list)
    operational_constraints: list[str] = field(default_factory=list)
    # v0.2.38 screening provenance. These fields describe post-analysis
    # retention by the screening policy; they do not alter anomaly detection
    # or imply a material/target probability.
    screening_rescue_applied: bool = False
    screening_selection_reason: str = ""
    screening_policy_version: str = ""
    # v0.2.5 multi-scan evidence / uncertainty. These are bounded screening
    # metrics, not probabilities and not a substitute for field ground truth.
    multi_scan_evidence_score: float = 0.0
    evidence_uncertainty: float = 1.0
    depth_uncertainty: float = 1.0
    geometry_uncertainty: float = 1.0
    signal_uncertainty: float = 1.0
    position_uncertainty: float = 1.0
    registration_uncertainty: float = 1.0
    leave_one_out_stability: float = 1.0
    effective_scan_count: int = 1
    uncertainty_flags: list[str] = field(default_factory=list)
    evidence_components: dict[str, float] = field(default_factory=dict)
    # v0.2.6 fused geometry/depth descriptors across the contributing scans.
    fused_depth_iqr: float = float("nan")
    fused_depth_consistency: float = 0.0
    fused_depth_quality: float = 0.0
    depth_measurement_count: int = 0
    orientation_dispersion_deg: float = float("nan")
    orientation_consistency: float = 0.0
    geometry_size_consistency: float = 0.0
    geometry_fusion_quality: float = 0.0
    geometry_measurement_count: int = 0
    # v0.2.8 morphology channels. These describe shape support; they are not
    # object/material probabilities.
    line_support_score: float = 0.0
    line_support_orientation_deg: float = float("nan")
    regional_support_score: float = 0.0
    axial_signal_continuity_score: float = 0.0
    # v0.2.18 generic response provenance. These fields describe how a response
    # was grouped; they are not material identification.
    response_family: str = "unclassified"  # unclassified / dipolar-response / linear-response / linear-metal-response / edge-limited / instrument-artifact
    response_component_ids: list[int] = field(default_factory=list)
    # v0.2.28 explicit dipole morphology diagnostics. These describe the paired
    # response lobes and are not material/object probabilities.
    dipole_pair_score: float = 0.0
    dipole_peak_balance: float = 0.0
    dipole_lobe_distance: float = float("nan")
    dipole_pair_count: int = 0
    # v0.2.29 second-generation morphology diagnostics. These describe local
    # geometric consistency and are not material/object probabilities.
    width_consistency_score: float = 0.0
    orientation_stability_score: float = 0.0
    morphology_line_coherence_score: float = 0.0
    morphology_axial_coverage_score: float = 0.0
    # v0.2.32 soil/TWT depth-channel diagnostics. These never replace the
    # device-reported depth automatically; they provide a second, explicit
    # depth channel when raw TWT and the two propagation factors are available.
    soil_twt_depth_estimate: float = float("nan")
    soil_twt_depth_std: float = float("nan")
    soil_twt_depth_min: float = float("nan")
    soil_twt_depth_max: float = float("nan")
    soil_twt_depth_valid_fraction: float = 0.0
    soil_depth_delta_m: float = float("nan")
    soil_depth_channel_status: str = "unavailable"
    # v0.2.37 multi-hypothesis classification diagnostics. These are
    # competing heuristic pattern supports, not probabilities.
    hypothesis_scores: dict[str, float] = field(default_factory=dict)
    selected_hypothesis_margin: float = 0.0
    second_hypothesis: str = ""
    classification_method: str = "evidence-model"
    # v0.2.40 classification diagnostics. These are competing heuristic
    # supports used only to expose internal disagreement; they do not alter
    # the selected hypothesis and are not probabilities.
    classification_conflict_score: float = 0.0
    classification_conflict_reason: str = ""
    classification_alternatives: dict[str, float] = field(default_factory=dict)
    # v0.4.0 evidence attribution. Each hypothesis keeps an auditable
    # feature/weight trace plus semantic modifiers; values are diagnostics,
    # not probabilities.
    hypothesis_evidence: dict[str, dict[str, object]] = field(default_factory=dict)
    # v0.2.43 unresolved-overlap diagnostics. These fields describe a possible
    # fused response that the current decomposition stage could not safely split.
    # They are diagnostics only and never alter detection or screening.
    unresolved_overlap_score: float = 0.0
    unresolved_overlap_distance_px: float = float("nan")
    unresolved_overlap_reason: str = ""
    # v0.2.46 under-segmentation diagnostics. These describe a broad/fused parent
    # that contains a plausible second same-sign peak but was not split safely.
    # They are diagnostics only and never alter detection or screening.
    undersegmentation_score: float = 0.0
    undersegmentation_peak_count: int = 0
    undersegmentation_peak_ratio: float = 0.0
    undersegmentation_distance_px: float = float("nan")
    undersegmentation_depth_delta_m: float = float("nan")
    undersegmentation_depth_layer_supported: bool = False
    undersegmentation_channel: str = ""
    undersegmentation_reason: str = ""
    # v0.4.2 cross-scan polarity conflict (audit F-03). Marks a fused
    # candidate built from contradicting opposite-sign observations, or a
    # retained fused candidate whose members split on polarity. The conflict
    # verdict forces the residual unknown hypothesis with capped confidence
    # instead of a specific pattern conclusion.
    polarity_conflict: bool = False

    def with_updates(self, **changes: object) -> Candidate:
        """Return a copy with *changes* applied (isolated/testable transforms).

        Wrapper around :func:`dataclasses.replace` so stage functions can
        avoid in-place mutation when a pure transform is clearer.
        """
        from dataclasses import replace as _replace

        return _replace(self, **changes)  # type: ignore[arg-type]

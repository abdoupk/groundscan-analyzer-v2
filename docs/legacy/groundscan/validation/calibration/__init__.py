"""Stage 4 -- calibration and model characterization.

This package is **measurement infrastructure**. It characterizes the production
parameters; it does not calibrate them, and it activates nothing.

Three rules govern every module under this package.

1. **The expectation is never the pipeline.** Every quantity a test compares
   against is derived from the *construction* -- an exact rational solidity
   (``validation.solidity_reference``), an exposed-edge perimeter, the analytic
   bifurcation scale of two Gaussians, the number of local maxima of a
   continuous field (``synthetic_core.cross_resolution``) -- or from an
   independently stated closed form. Where no independent construction exists,
   the experiment reports that it has none instead of grading the pipeline
   against itself.

2. **Vendor fixtures are behavioural references, not ground truth.** The vendor
   corpus is a category of its own (:mod:`.datasets`, category ``vendor``) and
   nothing in this package infers a physical truth from a vendor annotation. It
   is used to describe how the system behaves on real-shaped data, never to
   choose a number.

3. **A number is never "calibrated" because it works.** Every candidate
   parameter lands in exactly one status from
   :data:`.register.PARAMETER_STATUSES`, and the register
   (:mod:`.register`) records, per number, the dataset, the sample count, the
   derivation, the uncertainty and the applicability. ``CALIBRATED`` requires
   independent evidence; the overwhelmingly common outcome here is
   ``MODEL_CHOICE`` or ``INSUFFICIENT_EVIDENCE``.

Nothing in this package is imported by the analysis path. It adds no threshold,
no weight and no default, and every experiment runs the production functions
under their production arguments.
"""

from __future__ import annotations

from .datasets import (
    CATEGORY_ANALYTICAL,
    CATEGORY_FIELD,
    CATEGORY_PERTURBATION,
    CATEGORY_VENDOR,
    FIELD_EVIDENCE_STATUS,
    analytic_shape_catalogue,
    calibration_datasets,
    field_evidence_availability,
    vendor_fixture_index,
)
from .register import (
    PARAMETER_STATUSES,
    STATUS_CALIBRATED,
    STATUS_EMPIRICAL_VALIDATION_REQUIRED,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_MODEL_CHOICE,
    STATUS_NOT_APPLICABLE,
    STATUS_PROVISIONAL,
    activation_decisions,
    parameter_register,
)

__all__ = [
    "CATEGORY_ANALYTICAL",
    "CATEGORY_FIELD",
    "CATEGORY_PERTURBATION",
    "CATEGORY_VENDOR",
    "FIELD_EVIDENCE_STATUS",
    "PARAMETER_STATUSES",
    "STATUS_CALIBRATED",
    "STATUS_EMPIRICAL_VALIDATION_REQUIRED",
    "STATUS_INSUFFICIENT_EVIDENCE",
    "STATUS_MODEL_CHOICE",
    "STATUS_NOT_APPLICABLE",
    "STATUS_PROVISIONAL",
    "activation_decisions",
    "analytic_shape_catalogue",
    "calibration_datasets",
    "field_evidence_availability",
    "parameter_register",
    "vendor_fixture_index",
]

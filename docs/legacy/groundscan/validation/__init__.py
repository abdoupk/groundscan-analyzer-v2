"""Validation package: field ground truth, vendor reference, and suite profiles."""

from .field import evaluate_field_dataset, load_field_truth
from .vendor import VENDOR_TRUTH, evaluate_vendor_reference

__all__ = [
    "evaluate_field_dataset",
    "load_field_truth",
    "evaluate_vendor_reference",
    "VENDOR_TRUTH",
]

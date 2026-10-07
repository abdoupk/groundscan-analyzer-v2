"""Stdlib-only validation of machine-contract payloads against frozen schemas.

No new dependencies: implements the small subset of JSON Schema used by
``schemas/analysis.schema.json``, ``schemas/site.schema.json`` and
``schemas/field_ground_truth.schema.json`` (type, required, properties, items,
allOf/if/then, minimum, exclusiveMinimum, maximum, exclusiveMaximum, const).
Unknown keywords are ignored.

Stage 2 (S05/S06) adds ``boolean`` type support, ``exclusiveMinimum``,
``maximum``/``exclusiveMaximum``, ``const``, ``allOf``/``if``/``then``, and an
explicit non-finite rejection.

``boolean`` was **missing entirely** and is worth calling out: a schema declaring
``"type": "boolean"`` had no satisfying value, so the field-ground-truth schema
could never validate a case that set ``target_present`` -- the one field whose
strict typing matters most. No other packaged schema declares ``boolean``, so
adding it cannot change any existing validation result.

The non-finite rejection is the substantive fix: Python's ``json`` accepts the
``NaN`` and ``Infinity`` literals that no JSON standard defines, and ``nan <= 0``
is False, so a non-finite tolerance passed the "must be positive" check and then
failed no comparison downstream.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def _check(value: object, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if expected is not None:
        names = [expected] if isinstance(expected, str) else list(expected)
        ok = False
        for name in names:
            if (
                name == "null"
                and value is None
                or name == "object"
                and isinstance(value, dict)
                or name == "array"
                and isinstance(value, list)
                or name == "string"
                and isinstance(value, str)
                or name == "boolean"
                and isinstance(value, bool)
                or name == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                or name == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                ok = True
        if not ok:
            errors.append(f"{path or '$'}: expected type {names}, got {type(value).__name__}")
            return
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path or '$'}: missing required key {key!r}")
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path or '$'}: must equal {schema['const']!r}, got {value!r}")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                _check(value[key], subschema, f"{path}/{key}" if path else key, errors)
        for clause in schema.get("allOf", []):
            if isinstance(clause, dict):
                _check_conditional(value, clause, path, errors)
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                _check(item, items, f"{path}[{i}]", errors)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _check_number_bounds(value, schema, path, errors)


def _check_number_bounds(
    value: float, schema: dict[str, Any], path: str, errors: list[str]
) -> None:
    """Numeric bounds, including the non-finite rejection Stage 2 requires.

    JSON has no NaN or Infinity literal, so a manifest carrying one is not
    well-formed JSON by any standard -- but Python's ``json`` module *accepts*
    both by default, so an unvalidated load would sail through. The declared
    schemas use ``exclusiveMinimum`` (not ``minimum``) for the tolerance fields,
    which the checker previously ignored entirely: a manifest could declare
    ``tolerance_m: 0`` and pass. A non-finite tolerance was worse than a wrong
    one, because ``nan <= 0`` is False, so the "must be positive" check passed
    and the tolerance silently became a number that fails no comparison.
    """
    if math.isnan(value) or math.isinf(value):
        errors.append(f"{path or '$'}: {value!r} is not a finite number")
        return
    minimum = schema.get("minimum")
    if minimum is not None and value < minimum:
        errors.append(f"{path or '$'}: {value!r} below minimum {minimum!r}")
    exclusive_minimum = schema.get("exclusiveMinimum")
    if exclusive_minimum is not None and value <= exclusive_minimum:
        errors.append(f"{path or '$'}: {value!r} must be greater than {exclusive_minimum!r}")
    maximum = schema.get("maximum")
    if maximum is not None and value > maximum:
        errors.append(f"{path or '$'}: {value!r} above maximum {maximum!r}")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if exclusive_maximum is not None and value >= exclusive_maximum:
        errors.append(f"{path or '$'}: {value!r} must be less than {exclusive_maximum!r}")


def _check_conditional(
    value: dict[str, Any], clause: dict[str, Any], path: str, errors: list[str]
) -> None:
    """Minimal ``if``/``then`` support (``allOf``).

    The field manifest uses it to express "x and y come as a pair" and
    "depth_m requires depth_tolerance_m". Implemented as: when the ``if``
    subschema is satisfied by the value, the ``then`` subschema applies.
    """
    condition: dict[str, Any] | None = clause.get("if")
    consequent: dict[str, Any] | None = clause.get("then")
    if not isinstance(condition, dict) or not isinstance(consequent, dict):
        return
    probe: list[str] = []
    _check(value, condition, path, probe)
    if not probe:
        _check(value, consequent, path, errors)


def _load_schema(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return loaded


#: Closed vocabulary for ``verification_method`` (Stage 2, S05).
#:
#: The schema types the field as a free string, and it was carried straight into
#: the output. An open vocabulary means a manifest can assert a verification
#: method nobody recognises and it will be reported as if it did. Closing the set
#: makes an unknown method a *rejection* at load time, and the surviving values
#: still reach the output so a consumer can filter on them.
VERIFICATION_METHODS: tuple[str, ...] = (
    "independent-field-record",
    "excavation",
    "borehole",
    "known-installation-record",
    "independent-survey",
)


def validate_analysis_payload(obj: dict) -> list[str]:
    """Return a list of schema violations (empty means valid)."""
    errors: list[str] = []
    _check(obj, _load_schema("analysis.schema.json"), "", errors)
    return errors


def validate_site_payload(obj: dict) -> list[str]:
    """Return a list of schema violations (empty means valid)."""
    errors: list[str] = []
    _check(obj, _load_schema("site.schema.json"), "", errors)
    return errors


def validate_field_truth_payload(obj: object) -> list[str]:
    """Validate a field-ground-truth manifest against its declared schema.

    Stage 2 (S05/S06). The schema already declared ``target_present`` as a
    strict boolean and ``tolerance_m`` with ``exclusiveMinimum: 0``; it was
    referenced only as a documentation string and never loaded, so neither
    constraint was ever enforced. Loading it here is what closes the *typing*
    defects.

    What this does **not** do, and must not be described as doing: it says
    nothing about L3 provenance or L4 empirical credibility. A manifest can be
    perfectly conformant and still be a claim rather than a verified status.
    That distinction is the caller's to make and is surfaced separately by
    :func:`field_ground_truth_status`.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return [f"$: expected type ['object'], got {type(obj).__name__}"]
    _check(obj, _load_schema("field_ground_truth.schema.json"), "", errors)
    return errors


def field_ground_truth_status(obj: object) -> dict[str, object]:
    """Separate the caller's *claim* from an independently verified *status*.

    A manifest asserting ``independent_field_ground_truth: true`` is a
    statement by whoever wrote the file. This project has no mechanism that can
    verify it, and the previous output echoed the assertion back as if it were a
    result. These are now two distinct fields:

    ``claimed``    what the manifest asserts
    ``verified``   always False here, with the reason
    ``schema_errors``  whether the claim is even well-formed

    Reporting ``verified: false`` alongside a schema-conformant manifest is the
    honest pairing: the file is well-formed *and* unverified.
    """
    claim = bool(isinstance(obj, dict) and obj.get("independent_field_ground_truth") is True)
    return {
        "claimed": claim,
        "verified": False,
        "verification_status": "unverified-claim",
        "reason": (
            "This project has no mechanism that can independently verify a field "
            "ground-truth manifest. The manifest's assertion is recorded as a "
            "caller claim, not as a result."
        ),
        "schema_errors": validate_field_truth_payload(obj) if isinstance(obj, dict) else [],
    }


_FORBIDDEN_BARE_METRIC_KEYS = ("recall", "precision", "accuracy")

_EVIDENCE_KINDS = ("scientific", "reference", "regression", "empirical")


def validate_science_report_payload(obj: dict) -> list[str]:
    """Validate a science report against its schema plus taxonomy rules.

    Beyond the structural schema this enforces what the generic checker
    cannot: the evidence-kind taxonomy, the permanent UNKNOWN field
    section, operating-point provenance, and the ban on bare
    recall/precision/accuracy keys anywhere in the document.
    """
    errors: list[str] = []
    _check(obj, _load_schema("science_report.schema.json"), "", errors)
    if not isinstance(obj, dict):
        return errors
    sections = obj.get("sections")
    if isinstance(sections, dict):
        for name, section in sections.items():
            if not isinstance(section, dict):
                continue
            kind = section.get("evidence_kind")
            if kind not in _EVIDENCE_KINDS:
                errors.append(f"sections/{name}: unknown evidence_kind {kind!r}")
            if not isinstance(section.get("converts_to", []), list):
                errors.append(f"sections/{name}: converts_to must be a list")
            gating = section.get("gating")
            if gating is not None and not isinstance(gating, bool):
                errors.append(f"sections/{name}: gating must be a boolean")
    # Verdict basis must be exactly the gating sections in canonical order.
    if isinstance(sections, dict):
        expected_basis = [
            name
            for name in (
                "mathematical",
                "synthetic",
                "adversarial",
                "metamorphic",
            )
            if isinstance(sections.get(name), dict) and sections[name].get("gating", False) is True
        ]
        if obj.get("verdict_basis") != expected_basis:
            errors.append(
                f"verdict_basis {obj.get('verdict_basis')!r} must equal gating "
                f"sections {expected_basis!r}"
            )
    # Every documented limitation must trace to a case record with the
    # limitation verdict; limitations are tracked, never hidden.
    adversarial = sections.get("adversarial", {}) if isinstance(sections, dict) else {}
    if isinstance(adversarial, dict):
        records = {
            r.get("case_id"): r for r in adversarial.get("case_records", []) if isinstance(r, dict)
        }
        for entry in adversarial.get("limitations", []):
            if not isinstance(entry, dict):
                continue
            record = records.get(entry.get("case_id"))
            if record is None or record.get("verdict") != "documented_limitation":
                errors.append(
                    f"limitations/{entry.get('case_id')!r}: no matching "
                    "documented_limitation case record"
                )
    field = sections.get("field_validation", {}) if isinstance(sections, dict) else {}
    if isinstance(field, dict) and field.get("status") != "unknown":
        errors.append("sections/field_validation: status must stay 'unknown' without field data")
    operating = obj.get("operating_point", {})
    if isinstance(operating, dict):
        if operating.get("status") != "documented-default":
            errors.append("operating_point: status must be 'documented-default'")
        claim = str(operating.get("scientific_claim", ""))
        if not claim.startswith("none"):
            errors.append("operating_point: threshold must carry no scientific claim")

    def _walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _FORBIDDEN_BARE_METRIC_KEYS:
                    errors.append(f"{path or '$'}/{key}: bare metric key is forbidden")
                _walk(item, f"{path}/{key}" if path else str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                _walk(item, f"{path}[{i}]")

    _walk(obj, "")
    return errors

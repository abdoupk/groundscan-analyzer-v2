"""Evaluator for independently verified field ground truth.

Vendor reference examples and synthetic cases are intentionally not promoted to
independent field truth by this module.
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ..services.single_scan import analyze_scan, load_scan
from .payload_schema import VERIFICATION_METHODS, field_ground_truth_status

#: Placeholder output directory used when the caller asked for no output.
#: Never created: ``analyze_scan(..., write_outputs=False)`` goes through the K9
#: choke point, which creates nothing. It exists only because ``out_dir`` is a
#: required argument. Deliberately under the system temp dir so that even a
#: future regression cannot touch the caller's working directory.
_UNUSED_OUTPUT_DIR = Path(tempfile.gettempdir()) / "groundscan-field-no-output"


@dataclass(frozen=True)
class FieldTruthCase:
    case_id: str
    scan_path: str
    verification_method: str = "independent-field-record"
    acquisition: dict[str, object] | None = None
    expected_patterns: tuple[str, ...] = ()
    target_present: bool = True
    x: float | None = None
    y: float | None = None
    tolerance_m: float = 3.0
    depth_m: float | None = None
    depth_tolerance_m: float | None = None


def _require_bool(raw: dict, key: str, *, case_id: str) -> bool:
    """Strict boolean read (Stage 2, S05). Absent is the default; present-but-wrong is an error.

    The previous ``bool(raw.get("target_present", True))`` coerced whatever it
    found, and the coercions were not neutral:

    =======================================  =====================
    input                                   coerced to
    =======================================  =====================
    ``"false"``                             ``True``  (inverted!)
    ``0`` / ``1``                           a bool
    ``null``                                ``False`` (≠ absent)
    ``[]`` / ``{}``                         ``False``
    =======================================  =====================

    So a manifest that wrote ``"false"`` to mean *no target* was read as *target
    present*, and the case was then scored as a detection. The string form is
    the plausible typo, and it silently inverted the answer.

    Absent still defaults to ``True``; only an explicit wrong-typed or null
    value is rejected, which keeps "omitted" distinct from "present but null".
    """
    if key not in raw:
        return True
    value = raw[key]
    if isinstance(value, bool):
        return value
    raise ValueError(
        f"Field-truth case {case_id!r}: {key} must be a JSON boolean, got "
        f'{type(value).__name__} ({value!r}). Strings such as "true"/"false" and '
        f"numbers 0/1 are rejected: {key} is a measured fact, and coercing it "
        f"silently inverts the case's meaning."
    )


def _require_finite_positive(
    raw: dict, key: str, *, case_id: str, default: float | None = None
) -> float:
    """Finite, strictly positive number (Stage 2, S06).

    The old check was ``tolerance <= 0``, and both non-finite values sail
    through it: ``nan <= 0`` is False and ``inf <= 0`` is False. A NaN tolerance
    is the worst case because it fails *no* comparison downstream either -- it
    turns the case's pass/fail into a coin flip decided by which side of the
    comparison the other operand happens to land.

    A plausibility *ceiling* is deliberately not added here: the maximum
    plausible locator error is a calibration decision (Remediation Design v2
    §15.1) and is not derivable from the schema.
    """
    if key not in raw or raw[key] is None:
        if default is None:
            raise ValueError(f"Field-truth case {case_id!r} requires {key}")
        return float(default)
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Field-truth case {case_id!r}: {key} must be a number, got "
            f"{type(value).__name__} ({value!r})"
        )
    out = float(value)
    if math.isnan(out) or math.isinf(out):
        raise ValueError(
            f"Field-truth case {case_id!r}: {key} must be finite, got {out!r}. "
            "A non-finite tolerance fails no comparison, so it would decide the "
            "case silently."
        )
    if out <= 0.0:
        raise ValueError(f"Field-truth case {case_id!r} has non-positive {key}: {out!r}")
    return out


def load_field_truth(path: str | Path) -> list[FieldTruthCase]:
    # Stage 2 (S05/S06/U06): the declared schema is now actually loaded and
    # enforced. It was previously referenced only as a documentation string, so
    # neither `target_present: {"type": "boolean"}` nor
    # `tolerance_m: {"exclusiveMinimum": 0}` was ever checked. Schema conformance
    # is layer L1 only -- it says nothing about L3 provenance or L4 empirical
    # credibility, and must not be reported as if it did (contract K8).
    from .payload_schema import validate_field_truth_payload

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    schema_errors = validate_field_truth_payload(data)
    if schema_errors:
        raise ValueError(
            "Field truth manifest does not conform to field_ground_truth.schema.json:\n  - "
            + "\n  - ".join(schema_errors[:20])
            + ("\n  ... (and more)" if len(schema_errors) > 20 else "")
        )
    raw_cases = data.get("cases", data) if isinstance(data, dict) else data
    if not isinstance(raw_cases, list):
        raise ValueError("Field truth manifest must contain a list or a 'cases' list")
    if not isinstance(data, dict) or data.get("independent_field_ground_truth") is not True:
        raise ValueError(
            "Field truth manifest must explicitly set independent_field_ground_truth=true"
        )
    result = []
    for raw in raw_cases:
        if not isinstance(raw, dict) or "case_id" not in raw or "scan_path" not in raw:
            raise ValueError("Each field-truth case needs case_id and scan_path")
        case_id = str(raw["case_id"])
        x = float(raw["x"]) if raw.get("x") is not None else None
        y = float(raw["y"]) if raw.get("y") is not None else None
        for name, value in (("x", x), ("y", y)):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"Field-truth case {case_id!r} has non-finite {name}: {value!r}")
        if (x is None) != (y is None):
            raise ValueError(f"Field-truth case {case_id!r} must provide both x and y, or neither")
        tolerance = _require_finite_positive(raw, "tolerance_m", case_id=case_id, default=3.0)
        depth_m = float(raw["depth_m"]) if raw.get("depth_m") is not None else None
        if depth_m is not None and not math.isfinite(depth_m):
            raise ValueError(f"Field-truth case {case_id!r} has non-finite depth_m: {depth_m!r}")
        depth_tol = (
            _require_finite_positive(raw, "depth_tolerance_m", case_id=case_id, default=None)
            if raw.get("depth_tolerance_m") is not None
            else None
        )
        if depth_m is not None and depth_tol is None:
            raise ValueError(
                f"Field-truth case {case_id!r} needs positive depth_tolerance_m when depth_m is supplied"
            )
        # Closed vocabulary: an unrecognised verification method is rejected
        # rather than reported as if it meant something. The surviving value
        # still reaches the output so a consumer can filter on it.
        method = str(raw.get("verification_method", "independent-field-record"))
        if method not in VERIFICATION_METHODS:
            raise ValueError(
                f"Field-truth case {case_id!r}: unknown verification_method {method!r}; "
                f"expected one of {list(VERIFICATION_METHODS)}"
            )
        result.append(
            FieldTruthCase(
                case_id=case_id,
                scan_path=str(raw["scan_path"]),
                verification_method=method,
                acquisition=dict(raw.get("acquisition", {}))
                if isinstance(raw.get("acquisition", {}), dict)
                else None,
                expected_patterns=tuple(str(x) for x in raw.get("expected_patterns", [])),
                target_present=_require_bool(raw, "target_present", case_id=case_id),
                x=x,
                y=y,
                tolerance_m=tolerance,
                depth_m=depth_m,
                depth_tolerance_m=depth_tol,
            )
        )
    return result


def evaluate_field_dataset(manifest_path: str | Path, *, out_dir: str | Path | None = None) -> dict:
    from .._util import artifact_identity, contained_path, sanitize_label
    from ..services.config import AnalysisConfig

    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    # Load first so the reported claim/status comes from the file that was
    # actually evaluated, not from an assumption about it.
    cases = load_field_truth(manifest_path)
    status = field_ground_truth_status(json.loads(manifest_path.read_text(encoding="utf-8")))
    rows = []
    for case in cases:
        requested = Path(case.scan_path)
        if requested.is_absolute():
            raise ValueError(
                f"Field-truth case {case.case_id!r}: absolute scan_path is not allowed"
            )
        scan_path = (root / requested).resolve()
        try:
            scan_path.relative_to(root)
        except ValueError:
            raise ValueError(
                f"Field-truth case {case.case_id!r}: scan_path escapes manifest directory"
            ) from None
        if not scan_path.exists():
            raise FileNotFoundError(f"Field truth scan missing: {scan_path}")
        # Stage 2 (S10): the run directory is named from the artifact identity,
        # so two case ids that sanitize alike ("Case A" / "case_a") no longer
        # write into the same folder and overwrite each other's results. The
        # human-readable label is still what the report shows.
        identity = artifact_identity(case.case_id)
        safe_case = sanitize_label(identity.display_label)
        if out_dir is not None:
            run_dir = contained_path(Path(out_dir), identity.filesystem_stem)
            write_outputs = True
        else:
            # Stage 2 (S11 / contract K9): this used to be ``Path(".")``, so
            # ``evaluate_field_dataset(..., out_dir=None)`` handed the pipeline the
            # *current working directory* as its output directory, and the scan
            # landed in whatever folder the operator happened to be standing in.
            # The pollution was invisible because the mkdir that "created" it was
            # the caller's own folder. With no output directory there is no
            # output directory: nothing is written, and since `write_outputs` is
            # False the S11 choke point never creates this path at all -- the
            # value only exists to satisfy the required argument.
            run_dir = _UNUSED_OUTPUT_DIR
            write_outputs = False
        _, _, candidates = analyze_scan(
            load_scan(scan_path),
            run_dir,
            label=safe_case,
            config=AnalysisConfig(),
            write_outputs=write_outputs,
        )
        if not case.target_present:
            false_positive = len(candidates) > 0
            rows.append({
                **asdict(case),
                "candidates": len(candidates),
                "detected": false_positive,
                "passed": not false_positive,
                "false_positive": false_positive,
                "pattern_ok": False,
                "position_ok": True,
                "depth_ok": True,
                "reason": "expected no retained candidate",
            })
            continue

        compatible = [
            c
            for c in candidates
            if not case.expected_patterns or c.pattern_hypothesis in case.expected_patterns
        ]
        pattern_ok = bool(compatible) if case.expected_patterns else bool(candidates)
        selected = None
        center_error = float("nan")
        position_ok = True
        if compatible:
            if case.x is None and case.y is None:
                selected = max(compatible, key=lambda c: float(c.evidence_score))
            else:
                selected = min(
                    compatible,
                    key=lambda c: math.hypot(
                        float(c.x_center) - case.x, float(c.y_center) - case.y
                    ),
                )
                center_error = math.hypot(
                    float(selected.x_center) - case.x, float(selected.y_center) - case.y
                )
                position_ok = center_error <= case.tolerance_m

        detected = pattern_ok
        depth_ok = True
        depth_error = float("nan")
        if case.depth_m is not None:
            depth_ok = False
            if selected is not None:
                depth = (
                    float(selected.depth_estimate)
                    if math.isfinite(float(selected.depth_estimate))
                    else float(selected.depth_mean)
                )
                depth_error = abs(depth - case.depth_m) if math.isfinite(depth) else float("nan")
                depth_ok = (
                    case.depth_tolerance_m is not None
                    and math.isfinite(depth_error)
                    and depth_error <= case.depth_tolerance_m
                )
        passed = bool(pattern_ok and position_ok and depth_ok)
        rows.append({
            **asdict(case),
            "candidates": len(candidates),
            "detected": detected,
            "passed": passed,
            "pattern_ok": pattern_ok,
            "position_ok": position_ok,
            "depth_ok": depth_ok,
            "center_error_m": center_error,
            "depth_error_m": depth_error,
            "selected_candidate_id": int(selected.id) if selected is not None else None,
            "selected_pattern": selected.pattern_hypothesis if selected is not None else None,
            "selected_evidence": float(selected.evidence_score) if selected is not None else None,
        })
    positive_rows = [r for r in rows if r.get("target_present") is True]
    negative_rows = [r for r in rows if r.get("target_present") is False]
    detected_positives = sum(bool(r.get("detected")) for r in positive_rows)
    false_positive_negatives = sum(bool(r.get("false_positive")) for r in negative_rows)
    result = {
        "benchmark": "independent_field_ground_truth",
        # Stage 2 (S04 / contract K8): the caller's *claim* and the independently
        # *verified status* are now separate fields. The previous output set
        # ``independent_field_ground_truth: True``, which read as a result while
        # being nothing more than an assertion by whoever wrote the manifest.
        # Schema conformance (L1) is reported too, and only L1: a conformant
        # manifest is well-formed, not verified.
        "ground_truth_claim": status["claimed"],
        "ground_truth_verified": status["verified"],
        "ground_truth_verification_status": status["verification_status"],
        "ground_truth_verification_reason": status["reason"],
        "manifest_schema_conformant": not status["schema_errors"],
        "manifest_schema_errors": status["schema_errors"],
        "cases": len(rows),
        "positive_cases": len(positive_rows),
        "negative_cases": len(negative_rows),
        "detected_positive_cases": detected_positives,
        "detection_rate": detected_positives / max(len(positive_rows), 1),
        "false_positive_negative_cases": false_positive_negatives,
        "false_positive_case_rate": false_positive_negatives / max(len(negative_rows), 1),
        "passed": sum(1 for r in rows if r["passed"]),
        "pass_rate": sum(1 for r in rows if r["passed"]) / max(len(rows), 1),
        "matching_policy": "nearest compatible candidate when independent surface coordinates are supplied; otherwise highest-evidence compatible candidate is reported",
        "rows": rows,
        "note": "Requires independently verified field labels; vendor and synthetic data are not accepted as independent field ground truth. Detection and false-positive case rates are evaluation metrics, not forecasts.",
    }
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "field_validation.json").write_text(
            json.dumps(result, indent=2, allow_nan=True, ensure_ascii=False), encoding="utf-8"
        )
        lines = [
            "# Independent field validation",
            "",
            f"Cases: **{result['cases']}**; passed: **{result['passed']}**; pass rate: **{result['pass_rate']:.1%}**.",
            "",
            f"Positive-case detection rate: **{result['detection_rate']:.1%}**; negative-case false-positive case rate: **{result['false_positive_case_rate']:.1%}**.",
            "",
            "Only independently verified field labels are valid for this evaluation.",
            "",
            "| Case | Detected | Pass | Pattern | Position error (m) | Depth error (m) |",
            "|---|---|---|---|---:|---:|",
        ]
        for row in rows:
            lines.append(
                f"| `{row['case_id']}` | {'YES' if row.get('detected') else 'NO'} | {'PASS' if row['passed'] else 'FAIL'} | {row.get('selected_pattern') or '—'} | {row.get('center_error_m', '—')} | {row.get('depth_error_m', '—')} |"
            )
        (out / "field_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result

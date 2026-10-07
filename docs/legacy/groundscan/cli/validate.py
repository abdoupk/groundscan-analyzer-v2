"""Validation profiles handler (lazy heavy imports)."""

from __future__ import annotations

import sys
from pathlib import Path

_FAST_SUITES = ["tests/unit"]


def cmd_validate(args) -> int:
    profile = getattr(args, "validate_command", None)

    if profile == "fast":
        import subprocess

        print("validate profile: fast")
        print(f"suites: {', '.join(_FAST_SUITES)}")
        print("running: pytest tests/unit -q")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit", "-q"],
            capture_output=False,
        )
        if proc.returncode not in (0, 1):
            print(f"validate fast: pytest exited with code {proc.returncode}", file=sys.stderr)
        if proc.returncode == 0:
            print("validate fast: PASS (subprocess exit 0)")
            return 0
        print("validate fast: FAIL (subprocess exit != 0)")
        return 1

    if profile in ("full", "release"):
        import subprocess
        import time

        if profile == "full":
            from ..validation.profiles import FULL_SUITES

            print("validate profile: full")
            print(f"suites: {', '.join(FULL_SUITES)}")
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *FULL_SUITES, "-q"],
                capture_output=False,
            )
            if proc.returncode == 0:
                print("validate full: PASS (subprocess exit 0)")
                return 0
            print(f"validate full: FAIL (subprocess exit {proc.returncode})")
            return 1

        from ..validation.profiles import RELEASE_STEPS

        print("validate profile: release (exact enumerated gate)")
        failed: list[str] = []
        for label, pytest_args in RELEASE_STEPS:
            started = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *pytest_args],
                capture_output=False,
            )
            elapsed = time.perf_counter() - started
            status = "PASS" if proc.returncode == 0 else "FAIL"
            print(f"step {label}: {status} ({elapsed:.1f}s, exit {proc.returncode})")
            if proc.returncode != 0:
                failed.append(label)
        if not failed:
            print("validate release: PASS (failed: [])")
            return 0
        print(f"validate release: FAIL (failed: {failed})")
        return 1

    if profile == "experimental":
        import json
        import time
        import traceback

        from groundscan_research import EXPERIMENTAL_RUNNERS

        mode = getattr(args, "mode", "smoke")
        out_root = Path(getattr(args, "out", "experimental_out"))
        print(
            "validate profile: experimental "
            f"(mode={mode}; non-gating research outcomes — "
            "they never authorize production behavior)"
        )
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"error: cannot create output dir: {exc}", file=sys.stderr)
            return 3
        try:
            runners = list(EXPERIMENTAL_RUNNERS)
            if not runners:
                raise ValueError("EXPERIMENTAL_RUNNERS registry is empty")
        except (ImportError, ValueError) as exc:
            print(f"error: experimental harness broken: {exc}", file=sys.stderr)
            return 3
        rows: list[dict] = []
        for label, dotted, smoke_kwargs, full_kwargs in runners:
            suite_out = out_root / label
            kwargs = dict(full_kwargs if mode == "full" else smoke_kwargs)
            started = time.perf_counter()
            try:
                module_name, func_name = dotted.split(":")
                module = __import__(module_name, fromlist=[func_name])
                result = getattr(module, func_name)(suite_out, **kwargs)
                summary = (
                    {
                        k: result[k]
                        for k in ("sites", "cases", "recall", "precision")
                        if isinstance(result, dict) and k in result
                    }
                    if isinstance(result, dict)
                    else {}
                )
                rows.append({
                    "suite": label,
                    "status": "ok",
                    "elapsed_s": round(time.perf_counter() - started, 1),
                    "out": str(suite_out),
                    **summary,
                })
            except Exception as exc:  # noqa: BLE001 — research failures are data, not crashes
                rows.append({
                    "suite": label,
                    "status": "failed",
                    "elapsed_s": round(time.perf_counter() - started, 1),
                    "out": str(suite_out),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=5),
                })
            print(f"suite {label}: {rows[-1]['status']} ({rows[-1]['elapsed_s']}s)")
        (out_root / "experimental_report.json").write_text(
            json.dumps({"mode": mode, "suites": rows}, indent=2), encoding="utf-8"
        )
        print(
            f"experimental report: {out_root / 'experimental_report.json'} "
            "(RESEARCH-OUTCOME, non-gating)"
        )
        return 0

    if profile == "field":
        from ..validation.field import evaluate_field_dataset

        manifest = getattr(args, "manifest", None)
        out_dir = getattr(args, "out", "field_validation")
        try:
            min_rate = float(getattr(args, "min_pass_rate", 1.0))
        except (TypeError, ValueError):
            print("error: --min-pass-rate must be a number in [0, 1]", file=sys.stderr)
            return 2
        if not 0.0 <= min_rate <= 1.0:
            print("error: --min-pass-rate must be in [0, 1]", file=sys.stderr)
            return 2
        try:
            result = evaluate_field_dataset(manifest, out_dir=out_dir)
        except (ValueError, FileNotFoundError) as exc:
            print(f"validate field: FAIL — {exc}", file=sys.stderr)
            return 1
        passed = result.get("passed", 0)
        cases = result.get("cases", 0)
        pass_rate = result.get("pass_rate", 0.0)
        print(
            f"Independent field validation: {passed}/{cases} passed ({pass_rate:.1%}, required {min_rate:.0%})"
        )
        print(f"Report written to {Path(out_dir) / 'field_validation.md'}")
        return 0 if pass_rate >= min_rate else 1

    if profile == "science":
        from ..validation.scientific import run_science

        mode = getattr(args, "mode", "smoke")
        out_dir = getattr(args, "out", "science_out")
        if mode not in ("smoke", "full"):
            print("error: --mode must be smoke or full", file=sys.stderr)
            return 2
        print(f"validate profile: science (mode={mode}; gating scientific layers)")
        try:
            report = run_science(out_dir, mode=mode)
        except (ValueError, OSError) as exc:
            print(f"validate science: FAIL — {exc}", file=sys.stderr)
            return 1
        verdict = report.get("verdict", "fail")
        print("field validation: UNKNOWN (no independent field dataset evaluated)")
        print(f"science report: {Path(out_dir) / 'science_report.md'}")
        if verdict == "pass":
            print("validate science: PASS")
            return 0
        print("validate science: FAIL (gating section below floor)")
        return 1

    print(f"error: unknown validate profile {profile!r}", file=sys.stderr)
    return 2

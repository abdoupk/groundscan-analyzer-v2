"""Lazy command dispatcher for GroundScan Analyzer (refactored).

Only stdlib argument parsing lives at import time. Every subcommand handler
imports heavy analysis modules *inside* the handler function so that
``groundscan --help`` stays fast and side-effect free.

Exit codes: 0 success, 1 validation/domain failure, 2 usage, 3 infrastructure.
"""

from __future__ import annotations

import argparse
import sys


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--out",
        default=None,
        help="output directory (default: results/<scan-or-site-name>/, timestamped on collision)",
    )
    p.add_argument("--threshold", type=float, default=3.0)
    p.add_argument("--min-size", type=int, default=3)
    p.add_argument(
        "--quiet",
        action="store_true",
        help="suppress informational prints; errors still go to stderr",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable JSON summary to stdout on success",
    )
    p.add_argument("--zigzag", choices=["auto", "force", "off"], default="auto")
    p.add_argument("--line-spacing", type=float, default=None)
    p.add_argument("--point-spacing", type=float, default=None)
    p.add_argument(
        "--fusion-resolution",
        type=int,
        default=40,
        help="common grid resolution for site registration/fusion",
    )
    p.add_argument(
        "--soil-mode",
        choices=["diagnostic", "experimental"],
        default="diagnostic",
        help="soil-aware processing mode; experimental creates an A/B background map without replacing baseline detection",
    )
    p.add_argument(
        "--extraction-rescue",
        choices=["off", "conservative-geology"],
        default="off",
        help="optional secondary median-background geology extraction channel; off by default",
    )
    p.add_argument(
        "--fusion-pruning",
        choices=["off", "conservative-repeatability"],
        default="off",
        help="post-fusion candidate pruning using existing cross-scan repeatability evidence; off by default",
    )
    p.add_argument(
        "--field-quality-mode",
        choices=["enforce-hard-block", "report-only"],
        default="enforce-hard-block",
        help="field-quality behavior: block candidate extraction on critical failures, or record the failure only",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundscan",
        description="Device-agnostic ground scan analyzer",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_analyze = sub.add_parser("analyze", help="Analyze a single scan file")
    p_analyze.add_argument("file")
    _add_common(p_analyze)

    p_site = sub.add_parser(
        "analyze-site", help="Analyze and fuse 2+ scans from the same physical site"
    )
    p_site.add_argument(
        "inputs", nargs="+", help="scan files and/or directories containing scan files"
    )
    p_site.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        help="search input directories recursively (default: on)",
    )
    p_site.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="only top-level files of input directories",
    )
    p_site.set_defaults(recursive=True)
    p_site.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="input filename pattern; repeat for multiple patterns (default: *.csv, *.tsv, *.txt)",
    )
    _add_common(p_site)

    p_quality = sub.add_parser(
        "quality-check", help="Run the conservative field-operational quality gate on scan files"
    )
    p_quality.add_argument("inputs", nargs="+", help="scan files or directories")
    p_quality.add_argument(
        "--out", default="field_quality", help="output directory (default: field_quality)"
    )
    p_quality.add_argument(
        "--quiet",
        action="store_true",
        help="suppress informational prints; errors still go to stderr",
    )
    p_quality.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable JSON summary to stdout on success",
    )

    p_diag = sub.add_parser("diagnose", help="OKM signal diagnostics (characterize|fingerprint)")
    p_diag.add_argument(
        "--mode",
        choices=["characterize", "fingerprint"],
        default="characterize",
        help="diagnostic mode (default: characterize)",
    )
    p_diag.add_argument("inputs", nargs="+", help="OKM CSV/TXT files or directories")
    p_diag.add_argument("--out", default="okm_diagnostics")
    p_diag.add_argument(
        "--no-baseline", action="store_true", help="skip baseline detector signature"
    )

    p_validate = sub.add_parser(
        "validate", help="Validation profiles and field-ground-truth evaluation"
    )
    vsub = p_validate.add_subparsers(dest="validate_command", required=True, metavar="<profile>")
    vsub.add_parser("fast", help="Fast unit-test profile (pytest tests/unit -q)")
    vsub.add_parser("full", help="Full validation profile (unit+integration+regression)")
    vsub.add_parser("release", help="Release gate: exact 7-step enumerated profile")
    p_exp = vsub.add_parser("experimental", help="Research suites in smoke mode (non-gating)")
    p_exp.add_argument(
        "--out", default="experimental_out", help="output directory for suite artifacts"
    )
    p_exp.add_argument(
        "--mode",
        choices=["smoke", "full"],
        default="smoke",
        help="smoke: tiny params (minutes); full: moderate research sizes",
    )
    p_field = vsub.add_parser("field", help="Evaluate an independent field-ground-truth manifest")
    p_field.add_argument("manifest", help="path to field-truth manifest JSON")
    p_field.add_argument("--out", default="field_validation")
    p_field.add_argument(
        "--min-pass-rate",
        type=float,
        default=1.0,
        help="minimum pass rate for exit 0 (default: 1.0; lower for noisy field data)",
    )
    p_science = vsub.add_parser(
        "science", help="Scientific validation layers (gating; separate from release)"
    )
    p_science.add_argument(
        "--mode",
        choices=["smoke", "full"],
        default="smoke",
        help="smoke: frozen fast suites (seconds); full: + 240-case breadth (minutes)",
    )
    p_science.add_argument("--out", default="science_out")

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "analyze":
            from .analyze import cmd_analyze

            return cmd_analyze(args, parser)
        if args.command == "analyze-site":
            from .analyze import cmd_site

            return cmd_site(args, parser)
        if args.command == "quality-check":
            from .quality import cmd_quality

            return cmd_quality(args)
        if args.command == "diagnose":
            from .diagnose import cmd_okm

            return cmd_okm(args)
        if args.command == "validate":
            from .validate import cmd_validate

            return cmd_validate(args)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(f"error: failed to load analysis modules: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"No handler implemented for command {args.command!r}")
    return 2  # unreachable; parser.error exits with code 2


if __name__ == "__main__":
    raise SystemExit(main())

"""OKM signal diagnostics handler (lazy heavy imports)."""

from __future__ import annotations

from pathlib import Path


def cmd_okm(args) -> int:
    from ..diagnostics.okm import characterize_okm, fingerprint_okm

    mode = getattr(args, "mode", "characterize")
    if mode == "fingerprint":
        result = fingerprint_okm(args.inputs, args.out, run_baseline=not args.no_baseline)
        print(
            f"OKM fingerprint complete: files={result['files']}, device_groups={list(result['device_groups'])}"
        )
        print(f"Report written to {Path(args.out) / 'okm_signal_fingerprint.md'}")
        return 0
    result = characterize_okm(args.inputs, args.out, run_baseline=not args.no_baseline)
    print(
        f"OKM characterization complete: files={result['files']}, hardware_mentions={result['device_mentions_observed']}"
    )
    print(f"Report written to {Path(args.out) / 'okm_signal_characterization.md'}")
    return 0

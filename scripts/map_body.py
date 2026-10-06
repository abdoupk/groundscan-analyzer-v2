"""Byte-exact round-trip for a GitHub issue body.

The wayfinder map is one issue body that gets edited in a file and pushed back.
Reading it through a shell redirect corrupts it, because PowerShell decodes the
process's UTF-8 stdout as the console codepage and re-encodes it. This module
captures raw bytes instead, so the console encoding layer is never involved.

Usage:
    python scripts/map_body.py pull   [-o FILE]   capture the live body to a file
    python scripts/map_body.py push   FILE         push a file, then prove it round-tripped
    python scripts/map_body.py verify             report the live body's stats

`push` completes only when a re-fetch is byte-identical to what was sent. It
refuses before sending if any --expect marker is missing from the file, so a
truncated edit cannot be published.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "abdoupk/groundscan-analyzer-v2"
DEFAULT_ISSUE = 1
ASCII_LIMIT = 127


def api(args: list[str]) -> bytes:
    """Run `gh api` and return raw stdout bytes, never decoded.

    Args:
        args: arguments to pass to `gh api`, after the subcommand name.

    Returns:
        Whatever `gh` wrote to stdout, as bytes.

    Raises:
        SystemExit: If `gh` exits non-zero. Its stderr is forwarded first.
    """
    result = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", "replace"))
        message = f"gh api failed with exit code {result.returncode}"
        raise SystemExit(message)
    return result.stdout


def fetch_body(repo: str, issue: int) -> bytes:
    """Return the issue body as bytes, exactly as GitHub stores it.

    `gh api --jq` terminates every result with one newline of its own, so exactly
    one is removed. Whether the body itself ended in a newline does not matter:
    the removed byte is gh's, not the body's.
    """
    raw = api([f"repos/{repo}/issues/{issue}", "--jq", ".body"])
    return raw[:-1] if raw.endswith(b"\n") else raw


def describe(raw: bytes) -> str:
    """Summarise a body: its size, and whether it carries any non-ASCII.

    A non-ASCII count above zero means the body needs the file tools, not a
    shell redirect, to survive the round trip.
    """
    text = raw.decode("utf-8")
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return (
        f"chars={len(text)} lines={text.count(chr(10)) + 1} "
        f"bytes={len(raw)} non_ascii={non_ascii}"
    )


def command_pull(args: argparse.Namespace) -> int:
    raw = fetch_body(args.repo, args.issue)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    print(f"pulled -> {out}")
    print(describe(raw))
    return 0


def command_push(args: argparse.Namespace) -> int:
    payload = Path(args.file).read_bytes()
    print(f"sending  {describe(payload)}")

    missing = [m for m in (args.expect or []) if m.encode("utf-8") not in payload]
    if missing:
        print("refusing to push, these markers are absent from the file:", file=sys.stderr)
        for marker in missing:
            print(f"  {marker}", file=sys.stderr)
        return 1

    api(
        [
            "--method",
            "PATCH",
            f"repos/{args.repo}/issues/{args.issue}",
            "-F",
            f"body=@{args.file}",
            "--jq",
            ".html_url",
        ]
    )

    landed = fetch_body(args.repo, args.issue)
    if landed != payload:
        print("push did not round-trip", file=sys.stderr)
        print(f"  sent    {describe(payload)}", file=sys.stderr)
        print(f"  landed  {describe(landed)}", file=sys.stderr)
        return 1

    print(f"pushed   {describe(landed)}")
    print("verified byte-identical")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    raw = fetch_body(args.repo, args.issue)
    print(describe(raw))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--issue", type=int, default=DEFAULT_ISSUE)
    sub = parser.add_subparsers(dest="command", required=True)

    pull = sub.add_parser("pull", help="capture the live body to a file")
    pull.add_argument("-o", "--out", default="map_body.md")
    pull.set_defaults(func=command_pull)

    push = sub.add_parser("push", help="push a file, then prove it round-tripped")
    push.add_argument("file")
    push.add_argument(
        "--expect",
        action="append",
        help="marker that must be present; repeatable",
    )
    push.set_defaults(func=command_push)

    verify = sub.add_parser("verify", help="report the live body's stats")
    verify.set_defaults(func=command_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

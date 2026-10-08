"""Check the map body's open-ticket list against the tracker.

The map's `## Open tickets` section is a hand-maintained list, and every wayfinding
defect this repo has recorded is that list drifting from the issues it describes.
This check closes the three that are mechanically decidable.

Run by pre-commit rather than by the test suite, because it calls the network:
[#88](https://github.com/abdoupk/groundscan-analyzer-v2/issues/88) ruled a tracker
call out of `pytest` on the grounds that a network call in a unit test is a flake
source with no diagnostic value. That reasoning is about a test whose subject is
the artefact under test. This check's subject is the *relationship* between two
systems, which is what a hook is for.

Completes only when all three assertions hold. A real mismatch fails loudly
rather than skipping: a gate that skips is a gate that reads as enforcement
while enforcing nothing. An unreachable network is the one exception: with
no data no assertion can be evaluated either way, so the check reports
`network-unavailable, skipping map check` and exits zero. Only
connection-level failures skip; every other `gh` failure still fails loudly.

    python scripts/check_map.py
"""

from __future__ import annotations

import re
import subprocess
import sys

from map_body import api, fetch_body

BULLET = re.compile(r"^- \[.+\]\(#(\d+)\)", re.MULTILINE)
REPO = "abdoupk/groundscan-analyzer-v2"
ISSUE = 1

SECTION_START = "## Open tickets"
SECTION_END = "## Decisions so far"

NETWORK_MARKERS = (
    "dial tcp",
    "connectex",
    "etimedout",
    "econnrefused",
    "econnreset",
    "temporary failure",
    "could not resolve",
    "no such host",
    "network is unreachable",
    "failed to connect",
)


def is_network_failure(message: str) -> bool:
    """Report whether a `gh` failure is the transport, not the tracker.

    Only connection-level failures skip: with no data no assertion can be
    evaluated either way. Every other `gh` failure still fails loudly.
    """
    lowered = message.lower()
    return any(marker in lowered for marker in NETWORK_MARKERS)


def listed_tickets(body: str) -> list[str]:
    """Return the ticket numbers the map's open list names, in order."""
    start = body.find(SECTION_START)
    end = body.find(SECTION_END)
    if start == -1 or end == -1 or end < start:
        msg = "the map body has no usable '## Open tickets' section"
        raise SystemExit(msg)
    return BULLET.findall(body[start:end])


def open_native_children() -> list[str]:
    """Return the open tickets the tracker reports as native children of the map."""
    out = api(
        [
            "--paginate",
            f"repos/{REPO}/issues/{ISSUE}/sub_issues",
            "--jq",
            ".[] | select(.state == \"open\") | .number",
        ]
    )
    return out.decode("utf-8").split()


def state_of(number: str) -> str:
    """Return the state of one issue."""
    return api([f"repos/{REPO}/issues/{number}", "--jq", ".state"]).decode("utf-8").strip()


def main() -> int:
    try:
        listed = listed_tickets(fetch_body(REPO, ISSUE).decode("utf-8"))
        native = open_native_children()
        closed = [n for n in listed if state_of(n) == "closed"]
    except SystemExit as exc:
        if is_network_failure(str(exc.code)):
            print("network-unavailable, skipping map check")
            return 0
        raise

    failures: list[str] = []

    duplicates = sorted({n for n in listed if listed.count(n) > 1})
    if duplicates:
        failures.append(f"listed more than once: {', '.join(duplicates)}")

    if closed:
        failures.append(
            "listed as open but closed on the tracker: "
            + ", ".join(closed)
            + " - a closed ticket is neither an index entry nor an open ticket"
        )

    missing = [n for n in native if n not in listed]
    if missing:
        failures.append(
            "open native children absent from the map's list: "
            + ", ".join(missing)
            + " - the list is the index, and an unlisted ticket is unreachable"
        )

    print(f"map lists {len(listed)} open tickets; tracker reports {len(native)} open native children")
    if failures:
        print("\nFAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("all three assertions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The closed column and section registries behind the input contract.

Every name the contract recognises lives here with its role, its field
provenance, and whether a supported export may omit it. Matching is exactly
trimming surrounding whitespace and comparing case-insensitively, and nothing
else: the unit is part of the name, so ``Impulse X [ft]`` is an unknown
column rather than a convertible variant. There is no alias table until the
vendor is shown to publish a real alias.

The section registry sits beside the column registry and never inside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Final


class ColumnEntry(NamedTuple):
    """One registered column: its canonical name, role, provenance and load."""

    name: str
    role: str
    provenance: str
    required: bool


class SectionEntry(NamedTuple):
    """One registered section: its canonical name and its presence condition."""

    name: str
    presence: str


REQUIRED_SECTION: Final[str] = "required"
EXTENT_SECTION: Final[str] = "extent-carrying"
PLAIN_OPTIONAL_SECTION: Final[str] = "plain-optional"

COLUMNS: Final[tuple[ColumnEntry, ...]] = (
    ColumnEntry("Impulse X", "impulse", "device-index", required=True),
    ColumnEntry("Scan Line Y", "scan-line", "device-index", required=True),
    ColumnEntry(
        "Scan Value",
        "response",
        "instrument-produced-and-software-transformed",
        required=True,
    ),
    ColumnEntry(
        "Impulse X [m]",
        "impulse-metric",
        "derived-by-vendor-software-from-operator-assertion",
        required=False,
    ),
    ColumnEntry(
        "Scan Line Y [m]",
        "scan-line-metric",
        "derived-by-vendor-software-from-operator-assertion",
        required=False,
    ),
    ColumnEntry(
        "Depth Z [m]",
        "context-only",
        "derived-by-vendor-software-from-operator-assertion",
        required=False,
    ),
    ColumnEntry("Latitude", "context-only", "operator-asserted", required=False),
    ColumnEntry("Longitude", "context-only", "operator-asserted", required=False),
)

SECTIONS: Final[tuple[SectionEntry, ...]] = (
    SectionEntry("Measuring Values", REQUIRED_SECTION),
    SectionEntry("Characteristics", EXTENT_SECTION),
    SectionEntry("Soil Type", PLAIN_OPTIONAL_SECTION),
    SectionEntry("Meta Data", PLAIN_OPTIONAL_SECTION),
)

ROLES: Final[tuple[str, ...]] = (
    "impulse",
    "scan-line",
    "response",
    "impulse-metric",
    "scan-line-metric",
    "context-only",
    "reserved",
)

REQUIRED_ROLES: Final[tuple[str, ...]] = ("impulse", "scan-line", "response")


def normalise(name: str) -> str:
    """Match a name the only way the contract allows.

    Args:
        name: The raw header or section name as written in the file.

    Returns:
        The trimmed, case-folded form used for every registry comparison.
    """
    return name.strip().casefold()


def find_column(name: str) -> ColumnEntry | None:
    """Look a column name up in the closed registry.

    Args:
        name: The raw header cell as written in the file.

    Returns:
        The registry entry, or None when the name is not registered.
    """
    wanted = normalise(name)
    for entry in COLUMNS:
        if normalise(entry.name) == wanted:
            return entry
    return None


def find_section(name: str) -> SectionEntry | None:
    """Look a section name up in the closed registry.

    Args:
        name: The raw section name as written between the +++ markers.

    Returns:
        The registry entry, or None when the name is not registered.
    """
    wanted = normalise(name)
    for entry in SECTIONS:
        if normalise(entry.name) == wanted:
            return entry
    return None

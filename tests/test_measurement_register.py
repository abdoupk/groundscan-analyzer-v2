"""Static lint over the measurement register, separate from the glossary lint.

Seam three (static lint over committed artefacts), second document. The
register's check covers row-local token well-formedness plus cross-row
semantics. Tokens live in known columns, so a parse does not miss where
a search does. A wrong count is fixed by being derived rather than by
being checked: every present-tense count is deleted and past-state counts
stay, and the absence of any numeral the derivation produces is itself
checked. Cross-row expectations are read from the rows rather than
asserted, so no cross-row check is formally unsound. The check is offline
and calls no tracker.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

REPO = Path(__file__).resolve().parents[1]
REGISTER = REPO / "docs" / "measurements.md"

FIGURE_HEADER = ["figure", "measures", "settings needed", "standing", "note"]

VALID_STANDING_TOKENS = frozenset({
    "recorded",
    "swept",
    "unpinned",
    "unrecoverable",
    "exempt",
    "legacy-sweep",
})

#: Present-tense row-count claims deleted by this slice. Each is a numeral
#: (word or figure) asserting how many rows carry a token. Past-state counts
#: stay; these must stay absent.
FORBIDDEN_CLAIMS = (
    "written on 90 rows",
    "repeated 90 times",
    "It now reads nine",
    "the ninth is a malformed row",
    "now reads nine",
    "the ninth sitting",
    "15 of the other 16",
    "the twelve rows carrying",
    "The twelve are the rows carrying",
    "All twelve stand",
    "all three of [#61]",
    "three rows now separate the two",
    "out of the twelve that used",
    "Twelve rows name a perturbation protocol",
    "for all twelve",
    "One of the twelve names a draw",
    "All twelve already stand",
    "This section holds four things",
)

#: Declarations and past-state history that must remain.
REQUIRED_HISTORY = (
    "No sentence in this file asserts a current row count.",
    "Membership is the token, so the count is derived by counting it and is not written here.",
    "the count is read off the rows, not written here",
    "This count was wrong three times over",
    "is what last read it",
    "The graph is a star, and that is the finding.",
    "that list is provenance, not the enumeration",
)


def split_row(line: str) -> list[str]:
    """Split one markdown table row into its cells.

    Args:
        line: The raw table line including its outer pipes.

    Returns:
        The stripped cell values in order.
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def tables() -> list[list[tuple[int, str]]]:
    """Read the register's tables with their line numbers.

    Returns:
        One list of (line number, line) pairs per table.
    """
    lines = REGISTER.read_text(encoding="utf-8").splitlines()
    found: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if line.strip().startswith("|"):
            current.append((number, line))
        elif current:
            found.append(current)
            current = []
    if current:
        found.append(current)
    return found


def figure_tables() -> list[tuple[str, list[str], list[list[str]]]]:
    """Parse figure tables with their section headings.

    A figure table is headed exactly by figure, measures, settings needed,
    standing and note. The section is the nearest preceding ### heading.

    Returns:
        One (section, header, rows) triple per figure table, read from the
        rows rather than asserted, so cross-row checks stay sound.
    """
    lines = REGISTER.read_text(encoding="utf-8").splitlines()
    headings: list[tuple[int, str]] = [
        (number, line) for number, line in enumerate(lines, start=1) if line.startswith("### ")
    ]
    parsed = []
    for table in tables():
        header = split_row(table[0][1])
        if [cell.lower() for cell in header] != FIGURE_HEADER:
            continue
        first_number = table[0][0]
        section = ""
        for number, line in headings:
            if number < first_number:
                section = line
            else:
                break
        rows = []
        for _, line in table[2:]:
            rows.append(split_row(line))
        parsed.append((section, header, rows))
    return parsed


def standing_ok(cell: str) -> bool:
    """Check one standing cell for closed tokens only.

    Args:
        cell: The standing cell as written.

    Returns:
        True where every backticked token is a closed standing or label,
        or the cell is an exempt row.
    """
    if "exempt" in cell:
        return True
    parts: set[str] = set()
    for token in re.findall(r"`([^`]+)`", cell):
        parts.update(part for part in re.split(r"[,\s]+", token) if part)
    return bool(parts) and parts <= VALID_STANDING_TOKENS


def settings_carries(cell: str, token: str) -> bool:
    """Check whether one settings cell carries a backticked token.

    Args:
        cell: The settings cell as written.
        token: The token to look for.

    Returns:
        True where the cell carries the token in backticks.
    """
    return token in re.findall(r"`([^`]+)`", cell)


def derive_token_count(token: str) -> int:
    """Count figure rows whose settings cell carries a token.

    The count is read from the rows rather than asserted, so a later
    table edit moves the count without touching this function.

    Args:
        token: The settings token to count.

    Returns:
        The number of figure rows carrying the token.
    """
    total = 0
    for _, header, rows in figure_tables():
        settings_index = [cell.lower() for cell in header].index("settings needed")
        for cells in rows:
            if len(cells) != len(header):
                continue
            if settings_carries(cells[settings_index], token):
                total += 1
    return total


def prose_text() -> str:
    """Read the register's non-table prose.

    Returns:
        Every non-table line joined with newlines.
    """
    lines = REGISTER.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.strip().startswith("|")]
    return "\n".join(kept)


def row_has_citation(row_text: str, section: str) -> bool:
    """Check one figure row for a citation in the row or its section.

    Args:
        row_text: The row's cells joined as text.
        section: The section heading above the row.

    Returns:
        True where either names an issue.
    """
    return bool(
        re.search(r"#\d+", row_text)
        or re.search(r"issues/\d+", row_text)
        or re.search(r"#\d+", section)
        or re.search(r"issues/\d+", section)
    )


def verify_claim(prose_numeral: int, derived: int) -> None:
    """Fail where a prose numeral differs from the rows it claims.

    Args:
        prose_numeral: The numeral as written in prose.
        derived: The count read from the rows.
    """
    assert prose_numeral == derived


def test_figure_tables_well_formed() -> None:
    """Every figure table has five columns with no ragged row."""
    parsed = figure_tables()
    assert parsed != []
    for _, header, rows in parsed:
        assert rows != []
        for cells in rows:
            assert len(cells) == len(header), f"ragged row: {cells[0][:80]}"


def test_standing_cells_carry_closed_tokens() -> None:
    """A corrupted standing token fails the row-local check."""
    for _, header, rows in figure_tables():
        standing_index = [cell.lower() for cell in header].index("standing")
        for cells in rows:
            if len(cells) != len(header):
                continue
            assert standing_ok(cells[standing_index]), f"bad standing: {cells[standing_index][:80]}"
    assert not standing_ok("`bogus-standing`")


def test_settings_cells_present() -> None:
    """No figure row leaves its settings cell empty."""
    for _, header, rows in figure_tables():
        settings_index = [cell.lower() for cell in header].index("settings needed")
        for cells in rows:
            if len(cells) != len(header):
                continue
            assert cells[settings_index], f"empty settings: {cells[0][:80]}"


def test_token_counts_derived_by_reading() -> None:
    """Both label counts are read from the settings column, not asserted."""
    undeclared = derive_token_count("undeclared-protocol")
    unlocated = derive_token_count("unlocated-estimator")
    assert undeclared > 0
    assert unlocated > 0


def test_drifted_count_fails() -> None:
    """A prose numeral differing from its rows is a check failure."""
    derived = derive_token_count("undeclared-protocol")
    with pytest.raises(AssertionError):
        verify_claim(derived + 1, derived)


def test_present_tense_counts_deleted() -> None:
    """No deleted claim returns; the derivation's numerals stay unwritten."""
    prose = prose_text()
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in prose, f"present-tense count remains: {claim!r}"


def test_past_state_counts_remain() -> None:
    """History and declarations survive the deletion as record, not claim."""
    prose = prose_text()
    for required in REQUIRED_HISTORY:
        assert required in prose, f"history missing: {required!r}"


def test_every_figure_row_cites() -> None:
    """A row without a citation in itself or its section fails."""
    missing = []
    for section, header, rows in figure_tables():
        for cells in rows:
            if len(cells) != len(header):
                continue
            if not row_has_citation(" ".join(cells), section):
                missing.append(cells[0][:80])
    assert missing == []
    assert not row_has_citation("a figure with no ticket anywhere", "### No ticket here")


def imported_roots(path: Path) -> set[str]:
    """Read a file's top-level imported module roots.

    Returns:
        The first component of every import in the file.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_suppression_over_committed_artefacts() -> None:
    """A register failure is fixed, never excepted with a marker."""
    markers = ("vocabulary: ignore", "vocabulary: pardon", "vocab: ignore", "noqa")
    artefacts = [
        REPO / "CONTEXT.md",
        REPO / "docs" / "contract.md",
        REPO / "docs" / "measurements.md",
        REPO / "docs" / "capabilities.md",
    ]
    hits = [
        f"{path}:{number}"
        for path in artefacts
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(marker in line.lower() for marker in markers)
    ]
    assert hits == []


def test_check_is_offline() -> None:
    """The register check reads a local file and calls no tracker."""
    assert REGISTER.is_file()
    assert REGISTER.is_relative_to(REPO)
    assert REGISTER.suffix == ".md"
    network = {"socket", "urllib", "requests", "http", "subprocess"}
    own = imported_roots(Path(__file__))
    declaring = imported_roots(REPO / "src" / "groundscan_analyzer" / "vocabulary.py")
    assert own.isdisjoint(network)
    assert declaring.isdisjoint(network)

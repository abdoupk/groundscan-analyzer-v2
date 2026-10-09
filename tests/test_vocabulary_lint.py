"""Static vocabulary lint: mechanical rule plus reviewed semantic category.

Seam three (static lint over committed artefacts). The mechanical rule
checks the shipped contract surface, its enumeration values, and its
limitation and error strings against one declared module per vocabulary
(:mod:`groundscan_analyzer.vocabulary`). Tokenisation splits hyphens, so
a forbidden phrase re-spelled with a hyphen still fails. The reviewed
semantic category catches synonyms the word list misses. The glossary is
inside the overall lint for equality and avoidance; the excluded corpora
stay outside because they exist to quote the forbidden vocabulary, while
an avoidance line is where the glossary records it as forbidden.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import typing
from typing import TYPE_CHECKING

from groundscan_analyzer import document, input_contract, reader, vocabulary
from groundscan_analyzer import property_registry as registry
from groundscan_analyzer import scale as scale_module
from groundscan_analyzer.cli import main

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "groundscan_analyzer"
GLOSSARY = REPO / "CONTEXT.md"
ARTEFACT = REPO / "docs" / "contract.md"

HEAD = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Scan Value
"""

TWO_BY_TWO = (
    HEAD
    + "1.0000,1.0000,10.0000\n2.0000,1.0000,20.0000\n"
    + "1.0000,2.0000,30.0000\n2.0000,2.0000,40.0000\n"
)

#: Headwords whose avoidance lines carry forbidden material by design.
#: Each is declaration, not use: the line records the ban for that term.
DECLARING_HEADWORDS = frozenset({
    "Vendor corpus",
    "Licensed source",
    "Synthetic scenario",
    "Instrument",
    "Depth",
    "Anomaly",
    "Detection",
    "Characterisation",
})

HEAD_PATTERN = re.compile(r"^\*\*([^*]+?)\*\*:")
AVOID_PATTERN = re.compile(r"^_Avoid_:")
SECTION_PATTERN = re.compile(r"^#+ ")


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Collect docstring constant identities in one parsed module.

    Returns:
        The identities of the module, class and function docstrings.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            found.add(id(body[0].value))
    return found


def _file_strings(path: Path, non_outputs: set[str]) -> list[str]:
    """Collect shipped strings from one file excluding declarations.

    Returns:
        The non-docstring strings that are not non-output markers.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc_nodes = _docstring_ids(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in doc_nodes or node.value in non_outputs:
            continue
        found.append(node.value)
    return found


def shipped_strings() -> list[str]:
    """Collect shipped surface strings excluding declarations of absence.

    Reads every non-docstring string constant from the shipped package
    except the declaring vocabulary module itself, and drops registry
    non-output markers, which record what is not emitted.

    Returns:
        The surface strings in file order.
    """
    non_outputs = {entry.output for entry in registry.NON_OUTPUTS}
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "vocabulary.py":
            continue
        found.extend(_file_strings(path, non_outputs))
    return found


def true_headwords() -> list[tuple[int, str, list[str]]]:
    """Glossary entries as (line number, headword, block lines to Avoid).

    Returns:
        One tuple per glossary entry with its line number and following block.
    """
    lines = GLOSSARY.read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str, int]] = []
    last_sig = "start"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if SECTION_PATTERN.match(line):
            last_sig = "header"
            continue
        if AVOID_PATTERN.match(line):
            last_sig = "avoid"
            continue
        match = HEAD_PATTERN.match(line)
        if match:
            if last_sig in {"start", "avoid", "header"}:
                found.append((index + 1, match.group(1), index))
            last_sig = "head"
            continue
        last_sig = "text"
    entries = []
    for pos, (lineno, head, line_index) in enumerate(found):
        end = found[pos + 1][2] if pos + 1 < len(found) else len(lines)
        block = lines[line_index + 1 : end]
        entries.append((lineno, head, block))
    return entries


def glossary_standing_terms() -> set[str]:
    """Read the four standing terms from the glossary list items.

    Returns:
        The backticked head terms of the standing list.
    """
    text = GLOSSARY.read_text(encoding="utf-8")
    head, _, rest = text.partition("**Measurement standing**:")
    assert head, "the glossary states no Measurement standing entry"
    items = set()
    for line in rest.splitlines():
        if line.startswith("- `"):
            items.add(line.split("`")[1])
        if line.startswith("_Avoid_:"):
            break
    return items


def glossary_result_states() -> set[str]:
    """Read the three result states from the glossary entry.

    Returns:
        The backticked result-state values named there.
    """
    text = GLOSSARY.read_text(encoding="utf-8")
    head, _, rest = text.partition("**Result state**:")
    assert head, "the glossary states no Result state entry"
    segment = rest.split("_Avoid_:")[0]
    return set(re.findall(r"`(emitted|not-emitted|indeterminate)`", segment))


def glossary_grades() -> set[str]:
    """Read the two grades from the glossary entry.

    Returns:
        The backticked grade values named there.
    """
    text = GLOSSARY.read_text(encoding="utf-8")
    head, _, rest = text.partition("**Grade**:")
    assert head, "the glossary states no Grade entry"
    segment = rest.split("_Avoid_:")[0]
    return set(re.findall(r"`(exact|bounded)`", segment))


def glossary_refusal_reasons() -> set[str]:
    """Read the seven per-scan refusal reasons from the glossary entry.

    Returns:
        The backticked reason values named there.
    """
    text = GLOSSARY.read_text(encoding="utf-8")
    head, _, rest = text.partition("There are seven per-scan reasons")
    assert head, "the glossary states no seven per-scan reasons"
    segment = rest.split("**Reason names live here")[0]
    names = set(re.findall(r"`([a-z][a-z0-9-]+)`", segment))
    return {
        name
        for name in names
        if "unparseable" in name
        or "unknown" in name
        or "duplicate" in name
        or "missing" in name
        or "invalid" in name
    }


def test_both_layers_run() -> None:
    """The mechanical rule and the reviewed category both execute."""
    assert vocabulary.mechanical_hits("a clean field position") == ()
    assert vocabulary.semantic_hits("a clean field position") == ()
    assert vocabulary.SEMANTIC_CATEGORY


def test_hyphen_respelling_fails_mechanical() -> None:
    """A forbidden stem re-spelled with a hyphen still fails mechanically."""
    assert "metal" in vocabulary.mechanical_hits("metal-like")
    assert "metal" in vocabulary.mechanical_hits("metal_like")
    assert vocabulary.mechanical_hits("hollow-like") == ()


def test_phrase_forms_fail_mechanical() -> None:
    """Underscore and space spellings fail like the hyphenated phrase."""
    assert "x-axis" in vocabulary.mechanical_hits("x-axis")
    assert "x-axis" in vocabulary.mechanical_hits("x_axis")
    assert "x-axis" in vocabulary.mechanical_hits("x axis")
    assert "support-score" in vocabulary.mechanical_hits("support_score")


def test_semantic_catches_what_mechanical_misses() -> None:
    """Reviewed synonyms fail the category while passing the word list."""
    assert vocabulary.mechanical_hits("hollow-like") == ()
    assert "hollow" in vocabulary.semantic_hits("hollow-like")
    assert vocabulary.mechanical_hits("confirmed") == ()
    assert "confirmed" in vocabulary.semantic_hits("confirmed")
    assert vocabulary.mechanical_hits("linear-response") == ()
    assert vocabulary.semantic_hits("linear-response") != ()


def test_contract_surface_inside_mechanical_scope() -> None:
    """Every shipped string passes both layers with no exception."""
    failures = [
        (text, vocabulary.mechanical_hits(text), vocabulary.semantic_hits(text))
        for text in shipped_strings()
        if vocabulary.mechanical_hits(text) or vocabulary.semantic_hits(text)
    ]
    assert failures == []


def test_enumeration_limitation_and_error_strings_in_scope() -> None:
    """Literals, reasons, census outputs and quantity names are all scanned."""
    assert set(typing.get_args(document.WithheldReason)) == {
        "requires-declared-extent",
        "requires-homogeneous-axes",
    }
    assert set(typing.get_args(document.RefusalReason)) == {
        "unknown-column-name",
        "duplicate-normalised-name",
        "missing-required-column",
        "unparseable-row",
        "invalid-index-value",
        "duplicate-coordinate",
        "unparseable-under-assumed-reading",
    }
    assert set(typing.get_args(scale_module.ScaleStatus)) == {
        "no-finite-residual-values",
        "constant-field",
        "median-atom-zero-scale",
        "tie-tolerance-saturated",
        "tie",
        "disagreement",
    }
    candidates = [
        *list(typing.get_args(document.WithheldReason)),
        *list(typing.get_args(document.RefusalReason)),
        *list(typing.get_args(scale_module.ScaleStatus)),
        *[entry.output for entry in registry.OUTPUT_CENSUS],
    ]
    for text in candidates:
        assert vocabulary.mechanical_hits(text) == (), text
        assert vocabulary.semantic_hits(text) == (), text


def test_emitted_documents_clean() -> None:
    """Representative emitted bytes carry no banned vocabulary either layer."""
    doc = reader.read_document([TWO_BY_TWO.encode()])
    text = document.dumps(doc)
    assert vocabulary.mechanical_hits(text) == ()
    assert vocabulary.semantic_hits(text) == ()
    for word in ("validated", "metal", "target", "tunnel", "cavity", "buried"):
        assert word not in text


def test_cli_text_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Help and diagnostic strings ship no banned vocabulary."""
    assert main([]) == 2
    help_text = capsys.readouterr().out
    assert vocabulary.mechanical_hits(help_text) == ()
    assert vocabulary.semantic_hits(help_text) == ()
    missing = tmp_path / "missing-export.txt"
    assert main(["scan", str(missing)]) == 1
    error_text = capsys.readouterr().err
    assert vocabulary.mechanical_hits(error_text) == ()
    assert vocabulary.semantic_hits(error_text) == ()


def test_glossary_inside_scope_with_reason_stated() -> None:
    """The artefact states why the glossary is in and the corpora are out."""
    text = ARTEFACT.read_text(encoding="utf-8")
    assert "records forbidden vocabulary on its avoidance lines" in text
    assert "corpora quoting that vocabulary stay outside" in text


def test_avoidance_carrying_banned_material_is_declaration() -> None:
    """The eight declaring headwords keep their avoidance lines without failing."""
    entries = {head: block for _, head, block in true_headwords()}
    assert set(entries) >= DECLARING_HEADWORDS
    for head in DECLARING_HEADWORDS:
        avoid_lines = [line for line in entries[head] if AVOID_PATTERN.match(line)]
        assert avoid_lines, f"{head} carries no avoidance line"


def test_declaring_avoidance_lines_would_fail_in_scope() -> None:
    """The eight declaring lines hit mechanically, so excluding them matters."""
    entries = {head: block for _, head, block in true_headwords()}
    hitting = [
        head
        for head in DECLARING_HEADWORDS
        for line in entries[head]
        if AVOID_PATTERN.match(line) and vocabulary.mechanical_hits(line)
    ]
    assert hitting != []


def test_headword_losing_avoidance_line_fails() -> None:
    """A block stripped of its avoidance line carries no declaration."""
    entries = {head: block for _, head, block in true_headwords()}
    for head in DECLARING_HEADWORDS:
        stripped = [line for line in entries[head] if not AVOID_PATTERN.match(line)]
        assert stripped, f"{head} has no non-avoidance lines to keep"
        assert not any(AVOID_PATTERN.match(line) for line in stripped)


def test_every_headword_carries_avoidance() -> None:
    """No headword is without its declaration line."""
    missing = [
        f"{lineno}: {head}"
        for lineno, head, block in true_headwords()
        if not any(AVOID_PATTERN.match(line) for line in block)
    ]
    assert not missing


def test_glossary_result_states_match_module() -> None:
    """The glossary's three result states equal the declaring module's."""
    assert glossary_result_states() == set(registry.RESULT_STATES)


def test_glossary_grades_match_module() -> None:
    """The glossary's two grades equal the declaring module's."""
    assert glossary_grades() == set(registry.GRADES)


def test_glossary_refusal_reasons_match_module() -> None:
    """The glossary's seven per-scan reasons equal the document module's."""
    assert glossary_refusal_reasons() == set(typing.get_args(document.RefusalReason))


def test_glossary_standings_match_module() -> None:
    """The glossary's four standings equal the vocabulary module's."""
    assert glossary_standing_terms() == set(vocabulary.STANDINGS)


def test_roles_match_module() -> None:
    """The input contract's seven roles are closed in the declaring module."""
    assert set(input_contract.ROLES) == {
        "impulse",
        "scan-line",
        "response",
        "impulse-metric",
        "scan-line-metric",
        "context-only",
        "reserved",
    }


def test_no_vocabulary_suppression_over_shipped_tree() -> None:
    """A vocabulary failure is fixed, never excepted with a marker."""
    markers = ("vocabulary: ignore", "vocabulary: pardon", "vocab: ignore", "noqa")
    hits = [
        f"{path}:{number}"
        for path in sorted(SRC.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(marker in line.lower() for marker in markers)
    ]
    assert hits == []


def test_check_is_offline() -> None:
    """The declaring module imports no network capability."""
    text = (SRC / "vocabulary.py").read_text(encoding="utf-8")
    for token in ("urllib", "http.client", "socket", "gh api", "map_body", "requests"):
        assert token not in text

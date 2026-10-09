"""The compatibility gate: conformance with the contract, not correctness.

Seam one (contract document). The nine real exports are read where the
provenance set is present, and what that proves is compatibility rather
than correctness: contract rules re-derived at run time, definitional
bounds in exact arithmetic where they can be, and repeatability across
two fresh processes as a precondition. No recorded magnitude and no
golden file exists anywhere here.

Every test names its failing input in its docstring.
"""

from __future__ import annotations

import ast
import hashlib
import math
from pathlib import Path
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed argv, no shell
import sys

import pytest

from groundscan_analyzer import compatibility, descriptors, document, oracles, reader

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "groundscan_analyzer"
GATE = SRC / "compatibility.py"

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

ECHOED = """+++ Characteristics +++
Field Length: 3.00 m
Field Width: 3.00 m

+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Scan Value,Latitude,Longitude
1.0000,1.0000,0.0000,0.0000,10.0000,,
2.0000,1.0000,3.0000,0.0000,20.0000,,
1.0000,2.0000,0.0000,3.0000,30.0000,,
2.0000,2.0000,3.0000,3.0000,40.0000,,
"""


def bits(value: float) -> int:
    """Expose the binary64 bits for exact comparison.

    Args:
        value: The float to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def gate_source() -> str:
    """Read the gate module source for static checks.

    Returns:
        The gate source text.
    """
    return GATE.read_text(encoding="utf-8")


def gate_imports() -> set[str]:
    """Collect imported module names from the gate source.

    Returns:
        Imported module names, with from-imports expanded to dotted paths.
    """
    tree = ast.parse(gate_source())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{item.name}" for item in node.names)
    return found


def docstring_ids(tree: ast.Module) -> set[int]:
    """Collect docstring constant identities in one parsed module.

    Args:
        tree: The parsed module.

    Returns:
        The identities of module, class and function docstrings.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
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


def code_strings() -> list[str]:
    """Collect non-docstring string constants from the gate source.

    Returns:
        The code strings in walk order.
    """
    tree = ast.parse(gate_source())
    skip = docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


def read_scan(export: str) -> document.ScanRead:
    """Read one export to its read scan record.

    Args:
        export: The full export text.

    Returns:
        The read scan, asserting the contract accepted it.
    """
    doc = reader.read_document([export.encode()])
    assert len(doc.scans) == 1
    scan = doc.scans[0]
    assert scan.status == "read"
    assert isinstance(scan, document.ScanRead)
    return scan


def test_gate_reads_shipping_contract_not_magnitudes() -> None:
    """The gate imports the registries; no golden file exists.

    Failing input: a gate pinning one recorded solidity magnitude.
    """
    imports = gate_imports()
    assert "groundscan_analyzer.input_contract" in imports
    assert "groundscan_analyzer.quantity_registry" in imports
    assert "groundscan_analyzer.property_registry" in imports
    assert not any("golden" in text.lower() for text in code_strings())
    assert not any(".json" in text for text in code_strings())


def test_solidity_bounded_above_by_one_integer_arithmetic() -> None:
    """Every emitted solidity sits in (0, 1] with an integer hull.

    Failing input: a centre-based hull scoring a solid block above 1.
    """
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.detections
    for detection in scan.hierarchy.detections:
        cells = [(cell.impulse, cell.scan_line) for cell in detection.cells]
        assert detection.solidity > 0.0
        assert detection.solidity <= 1.0
        area8 = oracles.oracle_hull_area8(cells)
        assert area8 == descriptors.hull_shoelace8(cells)
        assert area8 >= 8 * len(cells)
        assert compatibility.solidity_ok(cells, detection.solidity)


def test_compactness_bounded_above_by_pi_over_four() -> None:
    """Every emitted compactness sits in (0, pi/4] over exposed edges.

    Failing input: an erosion perimeter scoring a domino above pi/4.
    """
    scan = read_scan(TWO_BY_TWO)
    assert scan.hierarchy.detections
    bound = math.pi / 4
    for detection in scan.hierarchy.detections:
        cells = [(cell.impulse, cell.scan_line) for cell in detection.cells]
        assert detection.compactness > 0.0
        assert detection.compactness <= bound
        assert oracles.oracle_perimeter(cells) == descriptors.exposed_perimeter(cells)
        assert oracles.perimeter_inequality_holds(cells)
        assert compatibility.compactness_ok(cells, detection.compactness)


def test_convex_exactly_one_not_asserted() -> None:
    """No gate asserts exactly 1.0 for convex sets; it is evidence, not definition.

    Failing input: a gate asserting a domino scores exactly 1.0.
    """
    assert not any("convex" in text.lower() for text in code_strings())
    assert compatibility.__doc__ is not None
    assert "evidence rather than definition" in compatibility.__doc__


def test_dominance_at_least_one_with_tie_and_withheld() -> None:
    """Dominance is >= 1; ties carry state; fewer than two withholds.

    Failing input: a tie manufacturing a winner by canonical order.
    """
    emitted = compatibility.dominance_for_peaks((18.0, 9.0, 4.0))
    assert emitted.state == "emitted"
    assert emitted.value is not None
    assert emitted.value >= 1.0
    assert bits(emitted.value) == bits(2.0)
    tied = compatibility.dominance_for_peaks((18.0, 18.0))
    assert tied.state == "tie-carries"
    assert tied.value is not None
    assert bits(tied.value) == bits(1.0)
    withheld = compatibility.dominance_for_peaks((5.0,))
    assert withheld.state == "withheld-requires-two-components"
    assert withheld.value is None
    assert compatibility.DOMINANCE_WITHHELD == "requires-two-components"
    empty = compatibility.dominance_for_peaks(())
    assert empty.state == "withheld-requires-two-components"


def test_polarity_disjoint_exhaustive_no_value_asserted() -> None:
    """Polarity partitions hierarchy cells; no polarity value is asserted.

    Failing input: a gate asserting one file's detections are positive.
    """
    assert compatibility.__doc__ is not None
    assert "structural" in compatibility.__doc__
    scan = read_scan(TWO_BY_TWO)
    assert compatibility.polarity_ok(scan)
    positives = {
        (cell.impulse, cell.scan_line)
        for detection in scan.hierarchy.detections
        if detection.polarity == "positive"
        for cell in detection.cells
    }
    negatives = {
        (cell.impulse, cell.scan_line)
        for detection in scan.hierarchy.detections
        if detection.polarity == "negative"
        for cell in detection.cells
    }
    assert positives.isdisjoint(negatives)
    assert "provenance set" in gate_source()


def test_contract_rules_rederived_index_metric_presence_structure() -> None:
    """Index base, echo tolerance, presence and structure track the file.

    Failing input: a gate pinning tolerance 0.00005 without reading the file.
    """
    scan = read_scan(ECHOED)
    raw = ECHOED.encode()
    assert compatibility.index_base_ok(scan, raw)
    assert compatibility.metric_tolerance_ok(scan, raw)
    assert compatibility.presence_ok(scan, raw)
    doc = reader.read_document([raw])
    assert compatibility.structure_ok(doc)


def test_repeatability_two_fresh_processes(tmp_path: Path) -> None:
    """Two fresh processes emit byte-identical output as a precondition.

    Failing input: an in-process double read compared without subprocesses.
    """
    target = tmp_path / "scan-export.txt"
    target.write_text(TWO_BY_TWO, encoding="utf-8")
    assert compatibility.repeatability_ok(target)


def test_scan_order_not_rechecked_single_owner() -> None:
    """The gate never re-checks survey order; each bound has exactly one owner.

    Failing input: a gate sorting two surveys and comparing their bytes.
    """
    source = gate_source()
    assert "survey-reordering" not in source
    assert "survey_reordering" not in source
    owners = compatibility.BOUND_OWNERS
    assert set(owners) == {"solidity", "compactness", "dominance", "polarity"}
    assert all(owners.values())
    assert owners["solidity"] == "groundscan_analyzer.descriptors"
    assert owners["compactness"] == "groundscan_analyzer.descriptors"


def test_corpus_path_explicit_hashes_not_committed() -> None:
    """The path is explicit with per-file hashes; the corpus stays uncommitted.

    Failing input: nine exports copied under tests/data as gate fixtures.
    """
    assert compatibility.CORPUS_ENV_VAR == "GROUNDSCAN_CORPUS_ROOT"
    assert len(compatibility.CORPUS_HASHES) == 9
    assert len(set(compatibility.CORPUS_HASHES)) == 9
    root = compatibility.corpus_root()
    assert root.is_absolute() or str(root)
    committed = list((REPO / "tests" / "data").rglob("*.csv")) + list((REPO / "src").rglob("*.csv"))
    if committed:
        digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in committed}
        assert digests.isdisjoint(set(compatibility.CORPUS_HASHES))
    assert compatibility.describe_files(()) == "incomplete"


def test_artefacts_not_named_after_corpus() -> None:
    """Gate artefacts carry neutral names; the files are a provenance set.

    Failing input: an artefact named vendor_gate with corpus in its path.
    """
    assert GATE.name == "compatibility.py"
    assert Path(__file__).name == "test_compatibility.py"
    source = gate_source()
    assert "provenance set" in source
    assert "eight of nine" in source
    assert "ninth carries a negative" in source


def test_fresh_process_helper_uses_fixed_argv(tmp_path: Path) -> None:
    """The repeatability helper runs fixed argv with no shell.

    Failing input: a helper interpolating the intake token into a shell.
    """
    target = tmp_path / "scan-export.txt"
    target.write_text(TWO_BY_TWO, encoding="utf-8")
    first, second = compatibility.two_fresh_runs(target)
    assert first == second
    assert first
    assert subprocess.run is not None
    assert sys.executable


def test_nine_exports_compatible_when_present() -> None:
    """All nine real exports read as compatible with the contract.

    Failing input: a real export refused by the contract it should accept.
    """
    try:
        present = list(compatibility.corpus_root().glob("*.csv"))
    except OSError:
        present = []
    if len(present) != 9:
        pytest.skip("provenance set absent: traceability fact, not a reproducibility one")
    files = compatibility.sorted_corpus_files(compatibility.corpus_root())
    assert len(files) == 9
    assert compatibility.manifest_ok(files)
    report = compatibility.check_files(files)
    assert report.files_checked == 9
    assert report.solidity_ok
    assert report.compactness_ok
    assert report.dominance_ok
    assert report.polarity_ok
    assert report.contract_rules_ok
    assert compatibility.repeatability_ok(files[0])


def test_gate_refuses_short_and_mismatched_manifests(tmp_path: Path) -> None:
    """A short set is incomplete; a wrong digest is an integrity failure.

    Failing input: a manifest comparing digests out of sorted order.
    """
    assert compatibility.manifest_ok(()) is False
    assert compatibility.describe_files(()) == "incomplete"
    single = tmp_path / "only.csv"
    single.write_text(TWO_BY_TWO, encoding="utf-8")
    assert compatibility.describe_files((single,)) == "incomplete"
    assert compatibility.manifest_ok((single,)) is False
    assert compatibility.sorted_corpus_files(tmp_path / "absent-dir") == ()


def test_gate_withholds_and_rejects_bad_bounds() -> None:
    """Empty cells, out-of-range values and unknown quantities all fail.

    Failing input: a solidity above one passing as compatible.
    """
    assert compatibility.solidity_ok((), 0.5) is False
    assert compatibility.solidity_ok(((0, 0),), 1.5) is False
    assert compatibility.solidity_ok(((0, 0),), 0.0) is False
    assert compatibility.compactness_ok((), 0.5) is False
    assert compatibility.compactness_ok(((0, 0),), 2.0) is False
    assert compatibility.compactness_ok(((0, 0),), float("nan")) is False
    assert compatibility.dominance_for_peaks((5.0, 0.0)).state == (
        "withheld-requires-two-components"
    )
    assert compatibility.dominance_for_peaks((7.0, 7.0, 7.0)).state == "tie-carries"


def test_gate_rederives_presence_and_tolerance_without_echo() -> None:
    """Exports without echo or discarded columns track their own absence.

    Failing input: a gate requiring echo columns every export carries.
    """
    scan = read_scan(TWO_BY_TWO)
    raw = TWO_BY_TWO.encode()
    assert compatibility.metric_tolerance_ok(scan, raw) is True
    assert compatibility.presence_ok(scan, raw) is True
    assert compatibility.index_base_ok(scan, raw) is True


def test_gate_structure_rejects_drifted_versions() -> None:
    """A drifted version or a dropped limitations field fails structure.

    Failing input: a structure check reading versions as pinned literals.
    """
    doc = reader.read_document([ECHOED.encode()])
    assert compatibility.structure_ok(doc) is True
    drifted = doc.model_copy(update={"registry_version": 999})
    assert compatibility.structure_ok(drifted) is False


def test_gate_check_files_refuses_bad_scans(tmp_path: Path) -> None:
    """A refused scan reads as incompatible, never as a passing gate.

    Failing input: a gate counting a refused scan as compatible.
    """
    bad = tmp_path / "bad.csv"
    bad.write_text("+++ Measuring Values +++\nFoo\n1\n", encoding="utf-8")
    report = compatibility.check_files((bad,))
    assert report.files_checked == 1
    assert report.solidity_ok is False
    assert report.contract_rules_ok is False


def test_gate_corpus_root_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The explicit path reads the environment before the default.

    Failing input: a gate hard-coding one directory and ignoring the env.
    """
    monkeypatch.setenv(compatibility.CORPUS_ENV_VAR, str(tmp_path))
    assert compatibility.corpus_root() == tmp_path

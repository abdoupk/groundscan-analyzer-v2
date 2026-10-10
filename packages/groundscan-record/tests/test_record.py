"""Field acceptance record: rendering, self-containment and drift."""

from __future__ import annotations

import html
from pathlib import Path
import re

from groundscan_analyzer import document as document_module
from groundscan_analyzer import reader, synthetic
from groundscan_record import RECORD_SECTIONS, render
from groundscan_record import record as record_module

DATA = Path(__file__).resolve().parent / "data"
ENGINE_DATA = Path(__file__).resolve().parents[3] / "tests" / "data"

FULL = """+++ Characteristics +++
Project Title: Iron Box
Date: 21.03.2020
Time: 07:51
Field Length: 3.00 m
Field Width: 3.00 m
Notes: the user has performed a control scan
Operating Mode: 3D Ground Scan
Scan Mode: Zigzag
Impulse Mode: Automatic

+++ Meta Data +++
Date / Time: 21.03.2020, 07:51
Scan Mode: Zigzag
Impulse Mode: Automatic

+++ Soil Type +++
Title: Gravel
Dielectric Constant: 2.60
Relative Permeability: 1.00
Mineralization: 30 %
Humidity: 20 %
Homogeneity: 50 %

+++ Measuring Values +++
Impulse X,Scan Line Y,Impulse X [m],Scan Line Y [m],Depth Z [m],Scan Value,Latitude,Longitude
1.0000,1.0000,0.0000,0.0000,0.1000,10.0000,,
2.0000,1.0000,3.0000,0.0000,0.2000,20.0000,,
1.0000,2.0000,0.0000,3.0000,0.3000,30.0000,,
2.0000,2.0000,3.0000,3.0000,0.4000,40.0000,,
"""


def _single() -> document_module.Document:
    text = (ENGINE_DATA / "acceptance_single.json").read_text(encoding="utf-8")
    return document_module.loads(text)


def _survey() -> document_module.Document:
    text = (ENGINE_DATA / "acceptance_survey.json").read_text(encoding="utf-8")
    return document_module.loads(text)


def _full_case() -> document_module.Document:
    cases = synthetic.build_required_cases()
    return synthetic.read_synthetic_document(cases["contradictory"])


def _main(html_text: str) -> str:
    return html_text.split("<details>", maxsplit=1)[0]


def test_one_template_renders_both_shapes() -> None:
    single = render(_single())
    survey = render(_survey())
    assert "Field acceptance record" in single
    assert "Field acceptance record" in survey
    assert "Scan at position 0" in single
    assert "Scan at position 0" in survey
    assert "Scan at position 1" in survey


def test_survey_sections_appear_only_when_non_empty() -> None:
    single = render(_single())
    main_single = _main(single)
    assert "Declared relations" not in main_single
    assert "Shared frames" not in main_single
    assert "Contradictions" not in main_single
    assert "Recurrences" not in main_single
    survey = render(_survey())
    main_survey = _main(survey)
    assert "Declared relations" not in main_survey
    assert "Recurrences" in main_survey
    full = render(_full_case())
    main_full = _main(full)
    assert "Declared relations" in main_full
    assert "Shared frames" in main_full
    assert "Contradictions" in main_full
    assert "Recurrences" in main_full


def test_output_is_self_contained_without_network() -> None:
    page = render(_single())
    assert "<style>" in page
    assert "<link" not in page
    assert "<script" not in page
    assert "<img" not in page
    assert "http://" not in page
    assert "https://" not in page
    assert "url(" not in page
    assert "@import" not in page
    assert "src=" not in page
    assert "href=" not in page


def test_two_runs_are_byte_identical() -> None:
    doc = _single()
    assert render(doc) == render(doc)
    clone = document_module.loads(document_module.dumps(doc))
    assert render(clone) == render(doc)


def test_write_record_is_byte_identical(tmp_path: Path) -> None:
    doc = _single()
    first = record_module.write_record(doc, tmp_path / "first.html")
    second = record_module.write_record(doc, tmp_path / "second.html")
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == render(doc)


def test_machinery_stays_out_of_headline() -> None:
    main = _main(render(_single()))
    assert "Measuring Values" not in main
    assert "Impulse X [m]" not in main
    assert "background-model-v1" not in main
    assert "measured-cells-only" not in main
    assert '"windows"' not in main
    assert '"combination"' not in main


def test_every_doubt_appears_beside_its_headline() -> None:
    single = render(_single())
    for token in [
        "disagreement",
        "scale-not-warranted",
        "requires-recorded-perturbation-bound",
        "non-unique-argmax",
        "missing-orientation-path",
    ]:
        assert token in single
    survey = render(_survey())
    for token in [
        "missing-required-column",
        "ineligible",
        "missing-orientation-path",
        "not-emitted",
    ]:
        assert token in survey
    full = render(_full_case())
    for token in [
        "contradictory-relation",
        "frame-1",
        "fixture-asserted-declaration",
    ]:
        assert token in full


def test_document_appears_verbatim_in_appendix() -> None:
    doc = _single()
    page = render(doc)
    assert "<details>" in page
    assert "<pre>" in page
    embedded = page.split("<pre>", maxsplit=1)[1].split("</pre>", maxsplit=1)[0]
    assert html.unescape(embedded) == document_module.dumps(doc)
    assert "Contract 1" in page
    assert "registry 3" in page
    assert "quantities 4" in page
    assert doc.scans[0].payload_hash in page  # type: ignore[union-attr]


def test_no_aggregate_no_readiness_figure() -> None:
    page = render(_single()).lower()
    for word in ["readiness", "fitness", "quality", "confidence", "total", "average"]:
        assert word not in page


def test_record_vocabulary_is_own() -> None:
    gate_states = {
        "emitted",
        "tie-carries",
        "withheld-requires-two-components",
        "complete",
        "incomplete",
        "integrity-failure",
    }
    scenario_states = {
        "absent",
        "present-but-empty",
        "present-with-value",
        "operator-asserted",
        "fixture-asserted",
        "perp-equal",
        "synthetic-only",
    }
    assert not set(RECORD_SECTIONS) & gate_states
    assert not set(RECORD_SECTIONS) & scenario_states
    assert "report" not in RECORD_SECTIONS


def test_free_text_substitution_moves_no_figure() -> None:
    variant = FULL
    for old, new in [
        ("Iron Box", "It is located in a depth of approx. 4 m"),
        ("21.03.2020", "yesterday, more or less"),
        ("the user has performed a control scan", "lorem ipsum dolor sit amet"),
        ("Zigzag", "Widdershins"),
        ("Gravel", "Some other ground"),
    ]:
        variant = variant.replace(old, new)
    first = render(reader.read_document([FULL.encode()]))
    second = render(reader.read_document([variant.encode()]))
    assert first == second


def test_render_does_not_measure() -> None:
    doc = _single()
    before = document_module.dumps(doc)
    render(doc)
    assert document_module.dumps(doc) == before
    body = render(doc).split("<body>", maxsplit=1)[1].split("<details>", maxsplit=1)[0]
    text = re.sub(r"<[^>]+>", " ", body)
    numbers = re.findall(r"-?\d+\.\d+|-?\d+", text)
    frozen = document_module.dumps(doc)
    for token in numbers:
        assert token in frozen


def test_import_direction_holds() -> None:
    src = Path(__file__).resolve().parents[3] / "src" / "groundscan_analyzer"
    for path in src.glob("*.py"):
        assert "groundscan_record" not in path.read_text(encoding="utf-8")
        assert "groundscan-record" not in path.read_text(encoding="utf-8")
    own = Path(record_module.__file__).read_text(encoding="utf-8")
    assert "groundscan_analyzer" in own


def test_acceptance_goldens_do_not_drift() -> None:
    single_golden = (DATA / "acceptance_single.html").read_text(encoding="utf-8")
    survey_golden = (DATA / "acceptance_survey.html").read_text(encoding="utf-8")
    assert render(_single()) == single_golden
    assert render(_survey()) == survey_golden

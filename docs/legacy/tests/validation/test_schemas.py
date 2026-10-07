"""Machine-contract schemas validate real producer output (fast)."""

import json

from groundscan.services.config import AnalysisConfig
from groundscan.services.single_scan import analyze_scan
from groundscan.site.analyze_site import analyze_site
from groundscan.validation.payload_schema import validate_analysis_payload, validate_site_payload
from groundscan.validation.synthetic_core.core import (
    SyntheticScenario,
    SyntheticTarget,
    generate_scan,
)


def test_analysis_and_site_payloads_validate(tmp_path):
    target = SyntheticTarget(kind="positive_compact", x=10.0, y=10.0, depth=2.0, amplitude=12.0)
    scenario = SyntheticScenario(
        name="schema_probe",
        width_m=20.0,
        height_m=20.0,
        nx=30,
        ny=30,
        targets=[target],
        noise_sigma=0.5,
        seed=99,
    )
    scan, _ = generate_scan(scenario)
    out = tmp_path / "single"
    out.mkdir()
    analyze_scan(scan, out, label="probe", config=AnalysisConfig())
    analysis = json.loads((out / "probe_analysis.json").read_text(encoding="utf-8"))
    assert validate_analysis_payload(analysis) == []

    scenario2 = SyntheticScenario(
        name="schema_probe_b",
        width_m=20.0,
        height_m=20.0,
        nx=30,
        ny=30,
        targets=[target],
        noise_sigma=0.5,
        seed=100,
    )
    scan2, _ = generate_scan(scenario2)
    site_out = tmp_path / "site"
    site_out.mkdir()
    analyze_site([("a", scan), ("b", scan2)], site_out)
    site = json.loads((site_out / "site_fused_candidates.json").read_text(encoding="utf-8"))
    assert validate_site_payload(site) == []


def test_validator_rejects_missing_keys():
    assert validate_analysis_payload({}) != []
    assert validate_site_payload({"reference_label": "x"}) != []

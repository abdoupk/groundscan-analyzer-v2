# Legacy capability census

The census that discharges **destination item 5**: the per-legacy-scientific-capability verdicts. It is a **census and not a verdict table** -- every row asserts that a verdict exists and where it is decided, and **no row states a verdict**. Two vocabularies carry the verdicts themselves; those are decided at map level, one row at a time, and they land in the verdict columns of this file.

Every row's verdict is **empty on arrival, deliberately**. An enumeration whose verdicts were all filled in would tell a reader the question is settled, and it is not: a capability nobody has adjudicated has to be *visible as unadjudicated*, which is the whole reason this file exists. **A red suite on arrival is how a gate gets switched off**, and an enumeration arriving complete is read as an enumeration that was never needed.

Rows are **retrospective** -- a fact about what a legacy module had -- so **no row and no verdict carries a version**. The two vocabularies are the exception, because they are a promise about the present rather than a record of the past.

## Rules

Stated rather than only enforced, in the shape of an `_Avoid_` line, so a reader can see the rule without running the check.

- **The denominator is every `.py` under `docs/legacy/` except any path with a `tests` or `results` component.** `tests/` asserts about capabilities and does not have them; dropping 64 files quietly would make the row count look complete while excluding a third of the tree. `results/` holds only `.gitkeep`.
- **No row carries verdict prose.** A row asserts that a verdict exists and where it lives. The verdict travels by citation, never by restatement -- the `Field area` rule applied to a verdict.
- **Rows are legacy-side. The property registry's output census is v2-side.** They are two subjects: this one answers *what the legacy had*, the registry answers *what a convention bump can move*. Both are headed "outputs", so the difference is **declared here** rather than assumed. Do not merge them.
- **Row existence is derived; verdicts are decided.** A legacy module either exists or does not, so re-running the derivation reproduces the row set and the count cannot drift. A verdict is a map-level act, so the verdict column is maintained and *can* drift -- which is why every row cites the issue that decides it.
- **The lint verifies that a name exists, never that a list is complete.** A closed vocabulary here is closed against the file's own members, not against the legacy tree.
- **The two vocabularies carry no version on any row.** Only the vocabularies themselves are map-versioned.
- **`reserved` is not a member of either vocabulary.** It names a slot in a contract, not the fate of a capability; it belongs to `Reserved` in `CONTEXT.md`.
- **`docs/measurements.md` is not widened.** A row may cite a registered figure. The register remains the only home for figures and their standings, and this file adds no fifth standing.
- **`CONTEXT.md` gains nothing.** Neither vocabulary is a domain noun; they are fates, not kinds of thing.

## Vocabularies

Both are closed, both are map-versioned at **v1** under [#1](https://github.com/abdoupk/groundscan-analyzer-v2/issues/1), and both are linted here in the same pattern the property registry uses. A classification that cannot represent a real hazard is wrong, so re-opening either vocabulary is a map act.

**`concept`** -- what became of the idea:

| value | meaning |
| --- | --- |
| `preserved` | the concept survives unchanged in v2 |
| `redesigned` | the concept survives in a different form |
| `removed` | the concept does not survive |
| `deferred` | the concept is named, kept, and not yet settled |

**`implementation`** -- what became of the machinery:

| value | meaning |
| --- | --- |
| `preserved` | the legacy implementation is carried across |
| `corrected` | the legacy implementation is kept and fixed |
| `replaced` | the legacy implementation is dropped for another one |
| `removed` | the machinery does not survive |

**Every capability has two fates, which is why there are two coordinates and not three values.** `preserve` and `redesign` overlap -- solidity was preserved *and* corrected, because legacy mixed a cell-area numerator with a centre-based hull and scored a solid 2x2 block at `4.0` where `1.0` was meant. Neither single word is honest alone.

## Derivation

**AST only.** The derivation parses every denominator file and reads no prose from it. A legacy docstring asserting a false claim is not evidence, and this project has already recorded that legacy prose contradicts its own code more than once.

Reproduce the whole census with:

```
python scripts/derive_capabilities.py report     # counts, breakdown, findings
python scripts/derive_capabilities.py table      # the row table below, verbatim
```

The predicates, in full:

1. **An `output` row is one public record class declared at module level** -- a `dataclass`, `NamedTuple`, `TypedDict`, `Protocol` or `Enum`, under any of those names, public meaning not underscore-prefixed. A module may host zero or more of them, which is why a module is not the row.
2. **A `no-output` row is one per denominator module that declares no record class.** Its name is the module path, because that is the identity a search would use. **It is marked by the token, never by absence** -- a row identifiable only by having no output-row cite it is invisible to a search.
3. **A package marker takes no row.** A module named `__init__.py` that declares no record class and no public definition of its own is a re-export surface, not a capability. The list is below, so the exclusion is applied in the open.
4. **Every other module takes a `no-output` row**, including one that declares no public definition at all. Coverage is the invariant the conditional check tests, so a module the record grain cannot see still gets a row rather than vanishing.

Every `no-output` row carries a **derived shape**, which is what makes the row readable without opening the file:

| shape | derived by | what it means |
| --- | --- | --- |
| *(empty)* | it declares at least one public definition | an ordinary callable surface emitting no declared record |
| `facade` | it declares no definition of any kind and imports from a sibling in the tree | its capability is already enumerated under the module it re-exports |
| `private-only` | it declares definitions, none of them public | its behaviour is reachable only through a sibling's public name |
| `constants-only` | it declares no definition and imports nothing from the tree | a settings or path surface with no behaviour |

## Rows

Sorted by module, then by capability. `concept` and `implementation` are **empty in every row**. The verdict-issue column carries the issue that decides the row; `#1` is the map, which is where a verdict is decided unless a narrower ticket takes it.

<!-- BEGIN DERIVED TABLE -->
| capability | kind | shape | legacy module | concept | implementation | verdict issue |
| --- | --- | --- | --- | --- | --- | --- |
| `groundscan/__init__.py` | `no-output` | `facade` | `groundscan/__init__.py` |  |  | #1 |
| `groundscan/__main__.py` | `no-output` | `facade` | `groundscan/__main__.py` |  |  | #1 |
| `ArtifactIdentity` | `output` |  | `groundscan/_util.py` |  |  | #1 |
| `ScaleEstimate` | `output` |  | `groundscan/_util.py` |  |  | #1 |
| `ScanAnalysisResult` | `output` |  | `groundscan/api.py` |  |  | #1 |
| `groundscan/cli/__init__.py` | `no-output` |  | `groundscan/cli/__init__.py` |  |  | #1 |
| `groundscan/cli/analyze.py` | `no-output` |  | `groundscan/cli/analyze.py` |  |  | #1 |
| `groundscan/cli/diagnose.py` | `no-output` |  | `groundscan/cli/diagnose.py` |  |  | #1 |
| `groundscan/cli/quality.py` | `no-output` |  | `groundscan/cli/quality.py` |  |  | #1 |
| `groundscan/cli/validate.py` | `no-output` |  | `groundscan/cli/validate.py` |  |  | #1 |
| `groundscan/core/__init__.py` | `no-output` | `facade` | `groundscan/core/__init__.py` |  |  | #1 |
| `AnomalyMap` | `output` |  | `groundscan/core/anomaly.py` |  |  | #1 |
| `ArtifactMap` | `output` |  | `groundscan/core/anomaly.py` |  |  | #1 |
| `groundscan/core/artifact.py` | `no-output` | `facade` | `groundscan/core/artifact.py` |  |  | #1 |
| `groundscan/core/background.py` | `no-output` |  | `groundscan/core/background.py` |  |  | #1 |
| `ClassificationConfig` | `output` |  | `groundscan/core/classify.py` |  |  | #1 |
| `EvidenceModelConfig` | `output` |  | `groundscan/core/evidence.py` |  |  | #1 |
| `Grid2D` | `output` |  | `groundscan/core/grid.py` |  |  | #1 |
| `groundscan/core/morphology.py` | `no-output` |  | `groundscan/core/morphology.py` |  |  | #1 |
| `ExtractionRescuePolicy` | `output` |  | `groundscan/core/rescue.py` |  |  | #1 |
| `groundscan/core/shape.py` | `no-output` |  | `groundscan/core/shape.py` |  |  | #1 |
| `ZigzagDiagnosis` | `output` |  | `groundscan/core/zigzag.py` |  |  | #1 |
| `groundscan/diagnostics/__init__.py` | `no-output` | `facade` | `groundscan/diagnostics/__init__.py` |  |  | #1 |
| `DipoleMergeConfig` | `output` |  | `groundscan/diagnostics/dipole.py` |  |  | #1 |
| `DipolePairAssessment` | `output` |  | `groundscan/diagnostics/dipole.py` |  |  | #1 |
| `LoadedExport` | `output` |  | `groundscan/diagnostics/okm.py` |  |  | #1 |
| `groundscan/diagnostics/quality_probe.py` | `no-output` |  | `groundscan/diagnostics/quality_probe.py` |  |  | #1 |
| `RoleShadow` | `output` |  | `groundscan/diagnostics/shadow.py` |  |  | #1 |
| `ScaleShadow` | `output` |  | `groundscan/diagnostics/shadow.py` |  |  | #1 |
| `ShadowMeasurement` | `output` |  | `groundscan/diagnostics/shadow.py` |  |  | #1 |
| `SolidityShadow` | `output` |  | `groundscan/diagnostics/shadow.py` |  |  | #1 |
| `groundscan/gates/__init__.py` | `no-output` | `facade` | `groundscan/gates/__init__.py` |  |  | #1 |
| `FieldQualityAssessment` | `output` |  | `groundscan/gates/field_quality.py` |  |  | #1 |
| `GeometrySummary` | `output` |  | `groundscan/gates/geometry.py` |  |  | #1 |
| `OperationalAssessment` | `output` |  | `groundscan/gates/operational.py` |  |  | #1 |
| `QualityAssessment` | `output` |  | `groundscan/gates/quality.py` |  |  | #1 |
| `ScreeningPolicy` | `output` |  | `groundscan/gates/screening.py` |  |  | #1 |
| `groundscan/gates/thresholds.py` | `no-output` |  | `groundscan/gates/thresholds.py` |  |  | #1 |
| `groundscan/io/__init__.py` | `no-output` |  | `groundscan/io/__init__.py` |  |  | #1 |
| `groundscan/io/base.py` | `no-output` |  | `groundscan/io/base.py` |  |  | #1 |
| `groundscan/io/generic_csv.py` | `no-output` |  | `groundscan/io/generic_csv.py` |  |  | #1 |
| `groundscan/io/rover.py` | `no-output` |  | `groundscan/io/rover.py` |  |  | #1 |
| `Candidate` | `output` |  | `groundscan/models.py` |  |  | #1 |
| `CoordinateSemantics` | `output` |  | `groundscan/models.py` |  |  | #1 |
| `ScanData` | `output` |  | `groundscan/models.py` |  |  | #1 |
| `ScanMetadata` | `output` |  | `groundscan/models.py` |  |  | #1 |
| `groundscan/services/__init__.py` | `no-output` | `facade` | `groundscan/services/__init__.py` |  |  | #1 |
| `AnalysisConfig` | `output` |  | `groundscan/services/config.py` |  |  | #1 |
| `groundscan/services/machine_contract.py` | `no-output` |  | `groundscan/services/machine_contract.py` |  |  | #1 |
| `groundscan/services/single_scan.py` | `no-output` |  | `groundscan/services/single_scan.py` |  |  | #1 |
| `CandidateEnrichment` | `output` |  | `groundscan/services/single_scan_stages.py` |  |  | #1 |
| `groundscan/site/__init__.py` | `no-output` | `facade` | `groundscan/site/__init__.py` |  |  | #1 |
| `groundscan/site/agreement.py` | `no-output` |  | `groundscan/site/agreement.py` |  |  | #1 |
| `MultiScanResult` | `output` |  | `groundscan/site/analyze_site.py` |  |  | #1 |
| `ScanObservation` | `output` |  | `groundscan/site/analyze_site.py` |  |  | #1 |
| `SiteRegistration` | `output` |  | `groundscan/site/analyze_site.py` |  |  | #1 |
| `ConflictBuildContext` | `output` |  | `groundscan/site/conflict_verdicts.py` |  |  | #1 |
| `groundscan/site/consensus.py` | `no-output` | `private-only` | `groundscan/site/consensus.py` |  |  | #1 |
| `DepthFusion` | `output` |  | `groundscan/site/fusion.py` |  |  | #1 |
| `GeometryFusion` | `output` |  | `groundscan/site/fusion.py` |  |  | #1 |
| `AlignmentResult` | `output` |  | `groundscan/site/registration.py` |  |  | #1 |
| `SeparationConfig` | `output` |  | `groundscan/site/separation.py` |  |  | #1 |
| `groundscan/site/separation_diagnostics.py` | `no-output` |  | `groundscan/site/separation_diagnostics.py` |  |  | #1 |
| `groundscan/site/separation_dipole.py` | `no-output` |  | `groundscan/site/separation_dipole.py` |  |  | #1 |
| `groundscan/site/separation_fragments.py` | `no-output` | `private-only` | `groundscan/site/separation_fragments.py` |  |  | #1 |
| `groundscan/site/separation_seeds.py` | `no-output` | `private-only` | `groundscan/site/separation_seeds.py` |  |  | #1 |
| `UncertaintyProfile` | `output` |  | `groundscan/site/uncertainty.py` |  |  | #1 |
| `groundscan/site/verdicts.py` | `no-output` | `private-only` | `groundscan/site/verdicts.py` |  |  | #1 |
| `groundscan/soil/__init__.py` | `no-output` | `facade` | `groundscan/soil/__init__.py` |  |  | #1 |
| `groundscan/soil/context.py` | `no-output` |  | `groundscan/soil/context.py` |  |  | #1 |
| `SoilPhysicsDiagnostics` | `output` |  | `groundscan/soil/experimental.py` |  |  | #1 |
| `groundscan/validation/__init__.py` | `no-output` | `facade` | `groundscan/validation/__init__.py` |  |  | #1 |
| `groundscan/validation/calibration/__init__.py` | `no-output` | `facade` | `groundscan/validation/calibration/__init__.py` |  |  | #1 |
| `CalibrationDataset` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `PerturbationCase` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `ProductionShapeMetrics` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `Provenance` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `ShapeSample` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `VendorFixture` | `output` |  | `groundscan/validation/calibration/datasets.py` |  |  | #1 |
| `MarginObservation` | `output` |  | `groundscan/validation/calibration/decision.py` |  |  | #1 |
| `PopulationBaseline` | `output` |  | `groundscan/validation/calibration/decision.py` |  |  | #1 |
| `PopulationMember` | `output` |  | `groundscan/validation/calibration/decision.py` |  |  | #1 |
| `ThreeSigmaObservation` | `output` |  | `groundscan/validation/calibration/decision.py` |  |  | #1 |
| `ThresholdSpec` | `output` |  | `groundscan/validation/calibration/decision.py` |  |  | #1 |
| `EnvelopeRow` | `output` |  | `groundscan/validation/calibration/envelope.py` |  |  | #1 |
| `CompactnessRow` | `output` |  | `groundscan/validation/calibration/geometry.py` |  |  | #1 |
| `SolidityBand` | `output` |  | `groundscan/validation/calibration/geometry.py` |  |  | #1 |
| `SolidityCensusRow` | `output` |  | `groundscan/validation/calibration/geometry.py` |  |  | #1 |
| `groundscan/validation/calibration/interactions.py` | `no-output` |  | `groundscan/validation/calibration/interactions.py` |  |  | #1 |
| `ParameterRecord` | `output` |  | `groundscan/validation/calibration/register.py` |  |  | #1 |
| `DetectorRun` | `output` |  | `groundscan/validation/calibration/resolution.py` |  |  | #1 |
| `MinSizeObservation` | `output` |  | `groundscan/validation/calibration/resolution.py` |  |  | #1 |
| `SeparationSummary` | `output` |  | `groundscan/validation/calibration/resolution.py` |  |  | #1 |
| `SeparationTrial` | `output` |  | `groundscan/validation/calibration/resolution.py` |  |  | #1 |
| `MultiplicityFinding` | `output` |  | `groundscan/validation/decomposition_reference.py` |  |  | #1 |
| `PerturbedRun` | `output` |  | `groundscan/validation/decomposition_reference.py` |  |  | #1 |
| `ResolvableSeparation` | `output` |  | `groundscan/validation/decomposition_reference.py` |  |  | #1 |
| `ResponseGroup` | `output` |  | `groundscan/validation/decomposition_reference.py` |  |  | #1 |
| `StabilityVerdict` | `output` |  | `groundscan/validation/decomposition_reference.py` |  |  | #1 |
| `InputCensus` | `output` |  | `groundscan/validation/decomposition_shadow_report.py` |  |  | #1 |
| `RunObservation` | `output` |  | `groundscan/validation/decomposition_shadow_report.py` |  |  | #1 |
| `groundscan/validation/extraction.py` | `no-output` | `private-only` | `groundscan/validation/extraction.py` |  |  | #1 |
| `FieldTruthCase` | `output` |  | `groundscan/validation/field.py` |  |  | #1 |
| `groundscan/validation/fixtures.py` | `no-output` | `constants-only` | `groundscan/validation/fixtures.py` |  |  | #1 |
| `groundscan/validation/golden.py` | `no-output` |  | `groundscan/validation/golden.py` |  |  | #1 |
| `groundscan/validation/payload_schema.py` | `no-output` |  | `groundscan/validation/payload_schema.py` |  |  | #1 |
| `groundscan/validation/profiles.py` | `no-output` | `constants-only` | `groundscan/validation/profiles.py` |  |  | #1 |
| `ContaminationOutcome` | `output` |  | `groundscan/validation/scale_contamination_experiment.py` |  |  | #1 |
| `Criterion` | `output` |  | `groundscan/validation/scale_reference.py` |  |  | #1 |
| `QuantisationVerdict` | `output` |  | `groundscan/validation/scale_reference.py` |  |  | #1 |
| `RegimeCensus` | `output` |  | `groundscan/validation/scale_reference.py` |  |  | #1 |
| `ScaleCase` | `output` |  | `groundscan/validation/scale_reference.py` |  |  | #1 |
| `ResidualComparison` | `output` |  | `groundscan/validation/scale_shadow_report.py` |  |  | #1 |
| `ScaleImpact` | `output` |  | `groundscan/validation/scale_shadow_report.py` |  |  | #1 |
| `ScaleShadowReport` | `output` |  | `groundscan/validation/scale_shadow_report.py` |  |  | #1 |
| `groundscan/validation/science_reporting.py` | `no-output` |  | `groundscan/validation/science_reporting.py` |  |  | #1 |
| `groundscan/validation/scientific.py` | `no-output` |  | `groundscan/validation/scientific.py` |  |  | #1 |
| `ReferenceCase` | `output` |  | `groundscan/validation/solidity_reference.py` |  |  | #1 |
| `SolidityReference` | `output` |  | `groundscan/validation/solidity_reference.py` |  |  | #1 |
| `ClassificationImpact` | `output` |  | `groundscan/validation/solidity_shadow_report.py` |  |  | #1 |
| `ComponentComparison` | `output` |  | `groundscan/validation/solidity_shadow_report.py` |  |  | #1 |
| `SolidityShadowReport` | `output` |  | `groundscan/validation/solidity_shadow_report.py` |  |  | #1 |
| `groundscan/validation/synthetic_core/acquisition_stress.py` | `no-output` |  | `groundscan/validation/synthetic_core/acquisition_stress.py` |  |  | #1 |
| `BenchmarkRow` | `output` |  | `groundscan/validation/synthetic_core/benchmark.py` |  |  | #1 |
| `AggregateMetrics` | `output` |  | `groundscan/validation/synthetic_core/benchmark_large.py` |  |  | #1 |
| `CaseResult` | `output` |  | `groundscan/validation/synthetic_core/benchmark_large.py` |  |  | #1 |
| `SyntheticScenario` | `output` |  | `groundscan/validation/synthetic_core/core.py` |  |  | #1 |
| `SyntheticTarget` | `output` |  | `groundscan/validation/synthetic_core/core.py` |  |  | #1 |
| `CrossResolutionFinding` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `LevelRecord` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `PhysicalResponse` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `PhysicalScene` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `Resolution` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `ResolutionEnsemble` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `ResolutionObservation` | `output` |  | `groundscan/validation/synthetic_core/cross_resolution.py` |  |  | #1 |
| `groundscan/validation/synthetic_core/cross_resolution_cases.py` | `no-output` |  | `groundscan/validation/synthetic_core/cross_resolution_cases.py` |  |  | #1 |
| `Variation` | `output` |  | `groundscan/validation/synthetic_core/cross_scan_variation_audit.py` |  |  | #1 |
| `StressCaseResult` | `output` |  | `groundscan/validation/synthetic_core/geology_local.py` |  |  | #1 |
| `groundscan/validation/synthetic_core/hard_regression.py` | `no-output` |  | `groundscan/validation/synthetic_core/hard_regression.py` |  |  | #1 |
| `groundscan/validation/synthetic_core/metamorphic.py` | `no-output` |  | `groundscan/validation/synthetic_core/metamorphic.py` |  |  | #1 |
| `MultiScanSiteSpec` | `output` |  | `groundscan/validation/synthetic_core/multiscan_benchmark.py` |  |  | #1 |
| `NegativeCase` | `output` |  | `groundscan/validation/synthetic_core/negative.py` |  |  | #1 |
| `groundscan/validation/synthetic_core/oracles.py` | `no-output` |  | `groundscan/validation/synthetic_core/oracles.py` |  |  | #1 |
| `PerturbationProfile` | `output` |  | `groundscan/validation/synthetic_core/robustness.py` |  |  | #1 |
| `VendorTruthCase` | `output` |  | `groundscan/validation/vendor.py` |  |  | #1 |
| `groundscan_research/adaptive_scale_separation.py` | `no-output` |  | `groundscan_research/adaptive_scale_separation.py` |  |  | #1 |
| `groundscan_research/background_decomposition.py` | `no-output` |  | `groundscan_research/background_decomposition.py` |  |  | #1 |
| `groundscan_research/background_factor_attribution.py` | `no-output` |  | `groundscan_research/background_factor_attribution.py` |  |  | #1 |
| `groundscan_research/background_independent_separation.py` | `no-output` |  | `groundscan_research/background_independent_separation.py` |  |  | #1 |
| `groundscan_research/background_separation.py` | `no-output` | `facade` | `groundscan_research/background_separation.py` |  |  | #1 |
| `groundscan_research/background_separation_audit.py` | `no-output` |  | `groundscan_research/background_separation_audit.py` |  |  | #1 |
| `groundscan_research/broad_response_representation.py` | `no-output` |  | `groundscan_research/broad_response_representation.py` |  |  | #1 |
| `groundscan_research/compound_interaction_analysis.py` | `no-output` |  | `groundscan_research/compound_interaction_analysis.py` |  |  | #1 |
| `groundscan_research/cross_scan_evidence.py` | `no-output` | `facade` | `groundscan_research/cross_scan_evidence.py` |  |  | #1 |
| `groundscan_research/cross_scan_evidence_audit.py` | `no-output` |  | `groundscan_research/cross_scan_evidence_audit.py` |  |  | #1 |
| `groundscan_research/cross_scan_evidence_calibration.py` | `no-output` |  | `groundscan_research/cross_scan_evidence_calibration.py` |  |  | #1 |
| `groundscan_research/cross_scan_evidence_repeated_holdouts.py` | `no-output` |  | `groundscan_research/cross_scan_evidence_repeated_holdouts.py` |  |  | #1 |
| `groundscan_research/cross_scan_evidence_stability.py` | `no-output` |  | `groundscan_research/cross_scan_evidence_stability.py` |  |  | #1 |
| `groundscan_research/extraction_rescue_discriminants.py` | `no-output` |  | `groundscan_research/extraction_rescue_discriminants.py` |  |  | #1 |
| `groundscan_research/forward_background_interaction.py` | `no-output` |  | `groundscan_research/forward_background_interaction.py` |  |  | #1 |
| `groundscan_research/generator_c_mechanism.py` | `no-output` |  | `groundscan_research/generator_c_mechanism.py` |  |  | #1 |
| `groundscan_research/generator_generalization.py` | `no-output` | `facade` | `groundscan_research/generator_generalization.py` |  |  | #1 |
| `groundscan_research/generator_shift_analysis.py` | `no-output` |  | `groundscan_research/generator_shift_analysis.py` |  |  | #1 |
| `groundscan_research/geology_extraction_independence.py` | `no-output` |  | `groundscan_research/geology_extraction_independence.py` |  |  | #1 |
| `groundscan_research/geology_extraction_shift.py` | `no-output` |  | `groundscan_research/geology_extraction_shift.py` |  |  | #1 |
| `groundscan_research/registration_atlas.py` | `no-output` | `facade` | `groundscan_research/registration_atlas.py` |  |  | #1 |
| `groundscan_research/registration_compound_atlas.py` | `no-output` |  | `groundscan_research/registration_compound_atlas.py` |  |  | #1 |
| `groundscan_research/registration_compound_recovery.py` | `no-output` |  | `groundscan_research/registration_compound_recovery.py` |  |  | #1 |
| `groundscan_research/registration_failure_semantics.py` | `no-output` |  | `groundscan_research/registration_failure_semantics.py` |  |  | #1 |
| `groundscan_research/registration_recovery.py` | `no-output` | `facade` | `groundscan_research/registration_recovery.py` |  |  | #1 |
| `groundscan_research/registration_recovery_coverage.py` | `no-output` |  | `groundscan_research/registration_recovery_coverage.py` |  |  | #1 |
| `groundscan_research/registration_recovery_experiments.py` | `no-output` |  | `groundscan_research/registration_recovery_experiments.py` |  |  | #1 |
| `groundscan_research/registration_recovery_repeated.py` | `no-output` |  | `groundscan_research/registration_recovery_repeated.py` |  |  | #1 |
| `groundscan_research/registration_robustness.py` | `no-output` |  | `groundscan_research/registration_robustness.py` |  |  | #1 |
| `groundscan_research/registration_semantics.py` | `no-output` |  | `groundscan_research/registration_semantics.py` |  |  | #1 |
| `groundscan_research/spatial_context_audit.py` | `no-output` |  | `groundscan_research/spatial_context_audit.py` |  |  | #1 |
| `groundscan_research/synthetic_generator_independence.py` | `no-output` |  | `groundscan_research/synthetic_generator_independence.py` |  |  | #1 |
| `tools/benchmark.py` | `no-output` |  | `tools/benchmark.py` |  |  | #1 |
| `tools/calibration_report.py` | `no-output` |  | `tools/calibration_report.py` |  |  | #1 |
| `tools/decomposition_shadow_report.py` | `no-output` |  | `tools/decomposition_shadow_report.py` |  |  | #1 |
| `Mutation` | `output` |  | `tools/mutation_ratchet.py` |  |  | #1 |

<!-- END DERIVED TABLE -->

## What the derivation found

Counts here are **derived, not maintained**. Any figure in this section is reproduced by `python scripts/derive_capabilities.py report`, and a figure restated without that command beside it is a maintained count, which is what this project has been bitten by.

**Denominator: 135 files.** 199 `.py` under `docs/legacy/`, less 64 under `tests/`.

**Rows: 181** -- 98 `output`, 83 `no-output`.

| subtree | rows |
| --- | --- |
| `groundscan/` (top level) | 9 |
| `groundscan/cli/` | 5 |
| `groundscan/core/` | 12 |
| `groundscan/diagnostics/` | 9 |
| `groundscan/gates/` | 7 |
| `groundscan/io/` | 4 |
| `groundscan/services/` | 5 |
| `groundscan/site/` | 17 |
| `groundscan/soil/` | 3 |
| `groundscan/validation/` | 30 |
| `groundscan/validation/calibration/` | 22 |
| `groundscan/validation/synthetic_core/` | 22 |
| `groundscan_research/` | 32 |
| `tools/` | 4 |

**Verdicts: 0 located, 181 empty.** The second number is the work queue, and it could not be written before this derivation ran -- a count written from a plan is the defect this project has recorded twice over.

**134 of the 135 denominator modules carry a row.** The one that does not is `groundscan_research/__init__.py`, a package marker by rule 3.

### Findings, each needing a decision that is not this artefact's to make

**A settings surface is not an output, and the derivation has no mechanical way to know that.** `core/rescue.py` emits no declared output -- its diagnostics are an untyped `dict`, and its single record, `ExtractionRescuePolicy`, is a caller-supplied guardrail set -- yet the rule above gives it an `output` row, because the record is declared at module level like any other. The same holds for six more: `AnalysisConfig`, `ClassificationConfig`, `EvidenceModelConfig`, `DipoleMergeConfig`, `ScreeningPolicy`, `SeparationConfig`. Every one of them is a set of knobs whose fate is a real verdict, so none of them should disappear, and **no predicate tried here separates them from a result without misclassifying something** -- an all-fields-defaulted test drops `ShadowMeasurement`, `ResolvableSeparation` and `RegimeCensus`, which are results, and keeps `ScanMetadata`, which is an input. **Deciding whether a settings surface is an output, and what row carries it, is open.**

**A `no-output` row is not always one capability.** 16 of the 83 are facades, whose capability is already enumerated under the module they re-export -- `core/artifact.py` over `core/anomaly.py`, and five in `groundscan_research/`. 5 are private-only, and these are the sharpest: `site/consensus.py`, `site/separation_fragments.py`, `site/separation_seeds.py`, `site/verdicts.py` and `validation/extraction.py` hold **190 to 262 lines each of implementation behind underscore-prefixed names**, imported by sibling modules *only* for their private names. The fusion and separation stages those four implement are enumerated against `site/analyze_site.py` and `site/separation.py` instead, so **a verdict recorded against them is a verdict on a private surface, and a verdict recorded against the stage silently covers them.** 2 are constants-only -- `validation/fixtures.py` and `validation/profiles.py` -- a settings surface with no behaviour at all.

**The record grain cannot exhibit a name collision, and the callable grain would have had eleven.** Rows are keyed by record class and no two denominator modules declare the same one, so the collision question is empty at this grain and recorded rather than answered. At callable grain the tree carries 11: `aggregate` (4 modules), `main` (5), `finite_values` (3), and `analyze_site`, `aspect_sweep`, `assert_no_object_count_claim`, `case_by_name`, `compare_scan`, `exact_solidity`, `robust_scale`, `run_registration_recovery_audit` (2 each). `run_registration_recovery_audit` is the sharp one: two research modules declare it, and the `registration_recovery.py` facade re-exports both under one name, so one of them is unreachable through the facade.

**The research subtree does not close at 32 rows.** Each of its 32 modules contributes exactly one `no-output` row, and the subtree was already found to hold a programme whose modules cluster into families -- registration recovery, cross-scan evidence, generator and generalisation, background separation and attribution, geology independence. **A verdict per module is a different act from a verdict per family**, and nothing here decides which grain the subtree is adjudicated at.

### What reproduced from [#89](https://github.com/abdoupk/groundscan-analyzer-v2/issues/89)

**All five of the research subtree's pure facades reproduce**, and the derivation finds eleven more outside it -- the ten package markers with re-exports, `groundscan/__main__.py`, and `core/artifact.py`. The first pass found only two of the five, because two of them use absolute imports and the rest relative; the facade predicate now accepts either, and the miss is recorded because it is the shape of error this map exists to prevent: a count written from one reading rather than measured. The subtree's private-symbol coupling, its 27-study structure and its absent study outputs are outside this artefact's question and were not re-measured.

## Checks

Two, both owed here rather than later, and they have different reach.

**The unconditional check** lives in `tests/test_capabilities.py` and runs offline. It asserts that every row's kind and shape tokens are in the closed sets, that every row cites an issue number in the right form, that the two verdict columns are empty or hold a member of their vocabulary, and that no row carries verdict prose. **It does not call the tracker.** A network call in a unit test is a flake source with no diagnostic value, in a repository already running `timeout = 120`, `filterwarnings = ["error"]` and `-n=auto`.

**What the unconditional check cannot do, stated rather than left implied:** it cannot tell whether a cited issue still exists. That residual is undetectable offline and **costs nothing real, because issues are not deleted on this tracker** -- so a citation to a vanished issue would be caught by a reader and by nothing else.

**The conditional check** asserts that every `.py` in the denominator carries a row, and that the row set equals what the derivation produces. **`docs/legacy/` is untracked** -- present on disk, absent from git and absent from `.gitignore` -- so **for any reader without the archaeology this check records "not checked", never "passed."** The mechanism is real and the guarantee is not universal, and that is a condition already recorded elsewhere on this map: the precedent it would otherwise follow is one whose cited artefacts are themselves untracked.

**No path manifest is committed to make the conditional check universal.** Two committed lists can be edited to agree with each other, so such a check could never catch a capability added to the archaeology -- which is the failure it exists to fix.

## Out of the census

- **`tests/`** -- 64 files. They assert about capabilities and have none. The map already disposes of preserving legacy tests.
- **`results/`** -- holds only `.gitkeep`.
- **`docs/legacy/groundscan_research/__init__.py`** -- a package marker by rule 3, and the only denominator module carrying no row.
- **`tools/` is in the census and is not science.** Four files take four rows. Whether a developer-facing ratchet is a legacy scientific capability is a question the rows make visible rather than one they answer.

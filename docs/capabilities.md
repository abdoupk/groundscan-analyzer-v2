# Legacy capability census

The census that discharges **destination item 5**: the per-legacy-scientific-capability verdicts. It is a **census and not a verdict table** -- every row asserts that a verdict exists and where it is decided, and **no row states a verdict**. Two vocabularies carry the verdicts themselves; those are decided at map level, one row at a time, and they land in the verdict columns of this file.

Every row's verdict is **empty on arrival, deliberately**. An enumeration whose verdicts were all filled in would tell a reader the question is settled, and it is not: a capability nobody has adjudicated has to be *visible as unadjudicated*, which is the whole reason this file exists. **A red suite on arrival is how a gate gets switched off**, and an enumeration arriving complete is read as an enumeration that was never needed.

Rows are **retrospective** -- a fact about what a legacy module had -- so **no row and no verdict carries a version**. The two vocabularies are the exception, because they are a promise about the present rather than a record of the past.

## Rules

Stated rather than only enforced, in the shape of an `_Avoid_` line, so a reader can see the rule without running the check.

- **The denominator is every `.py` under `docs/legacy/` except any path with a `tests` or `results` component.** `tests/` asserts about capabilities and does not have them; dropping 64 files quietly would make the row count look complete while excluding a third of the tree. `results/` holds only `.gitkeep`.
- **No row carries verdict prose.** A row asserts that a verdict exists and where it lives. The verdict travels by citation, never by restatement -- the `Field area` rule applied to a verdict.
- **Rows are legacy-side. The property registry's output census is v2-side.** They are two subjects: this one answers *what the legacy had*, the registry answers *what a convention bump can move*. Both are headed "outputs", so the difference is **declared here** rather than assumed. Do not merge them.
- **This census holds two subjects inside one file, beside the two it already declares across two.** A `declared-record` row is a capability and destination item 5's unit; a `no-output` row is a location and coverage bookkeeping. A `no-output` row's verdict is a decision about code at a location, not about a capability, so the surviving rows are the record of where item 5's units were *not* found.
- **Row existence is derived; verdicts are decided.** A legacy module either exists or does not, so re-running the derivation reproduces the row set and the count cannot drift. A verdict is a map-level act, so the verdict column is maintained and *can* drift -- which is why every row cites the issue that decides it.
- **A re-export surface takes no row, and the derivation names the excluded set.** A module that declares no definition of its own and re-exports from a module in the tree takes no row. Every target takes a row already with zero chains, so the coverage check needs one hop and not a fixpoint -- a fixpoint would be machinery for a case the tree does not contain.
- **The old package-marker reason was false and is restated by predicate.** The artefact once called a package marker a re-export surface, while the derivation drops an `__init__.py` only when its role is `constants-only`. The `__init__.py` facades therefore take no row as facades, not as markers. The one module the rule actually excludes carries zero imports and the module-level names `RESEARCH_SUITES` and `EXPERIMENTAL_RUNNERS`: a registry of the research runners, which [#91](https://github.com/abdoupk/groundscan-analyzer-v2/issues/91) ruled takes no `declared-record` row.
- **`role` is populated exactly when `kind` is `no-output`.** The vocabulary is closed at `callable-surface`, `private-only`, `constants-only`, matching no row name and no legacy module-level definition. Every ordinary row carries the token, by the same rule that a `no-output` row is marked by the token and never by absence. `surface` was refused because [#91](https://github.com/abdoupk/groundscan-analyzer-v2/issues/91) was chartered on whether a settings surface is a declared record.
- **A private-only row's verdict is decided at the row, in the row's own subtree, and the row set stays derived and unconditional.** No new column: `verdict issue` already names the owning ticket and is cited, not derived, while any added column would be maintained. Consumed in-tree rows are decided in `groundscan/site`; cross-subtree consumption is a fact about legacy recorded here in prose, not a field; the unreferenced row is decidable only at itself, which is the argument that such a row is a location and not a pointer. `constants-only` stays a `no-output` row as [#91](https://github.com/abdoupk/groundscan-analyzer-v2/issues/91) ruled: that ticket rules what a verdict on such a row may say, not whether the row exists, because a row set that depends on a decision can only report *inconsistent*, never *wrong*.
- **The count of covered modules is derived and is never written here.** Run `python scripts/derive_capabilities.py report` for it. A derived count cannot drift and a maintained one only can, so no numeral the derivation produces is written as a numeral in this file outside the derived table.
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

1. **A `declared-record` row is one public record class declared at module level** -- a `dataclass`, `NamedTuple`, `TypedDict`, `Protocol` or `Enum`, under any of those names, public meaning not underscore-prefixed. A module may host zero or more of them, which is why a module is not the row.
2. **A `no-output` row is one per denominator module that declares no record class and is not excluded below.** Its name is the module path, because that is the identity a search would use. **It is marked by the token, never by absence** -- a row identifiable only by having no declared-record-row cite it is invisible to a search.
3. **A re-export surface takes no row.** A module that declares no definition of its own and re-exports from a module in the tree takes no row, and the derivation names the excluded set. The runner registry takes no row as a settings surface.
4. **Every other module takes a `no-output` row**, including one that declares no public definition at all. Coverage is the invariant the conditional check tests, so a module the record grain cannot see still gets a row rather than vanishing.

Every `no-output` row carries a **derived role**, which is what makes the row readable without opening the file:

| role | derived by | what it means |
| --- | --- | --- |
| `callable-surface` | it declares at least one public definition | an ordinary callable surface emitting no declared record |
| `private-only` | it declares definitions, none of them public | its behaviour is reachable only through a sibling's public name |
| `constants-only` | it declares no definition | a settings or path surface with no behaviour |

The `constants-only` rule is what the code implements: `scripts/derive_capabilities.py` tests definitions only, while the table once stated an import conjunct the code lacks. Checked, and it is unexercised: zero rows change under either rule, so this is latent, not live. The conditional repair is recorded so it is not rediscovered: if the declared guardrail sets ever drop, `constants-only` must become *no public function **and** no tree import*, which moves exactly one row (`services/config.py`); the looser variants move three and mislabel `io/generic_csv.py` and `io/rover.py`.

## Rows

Sorted by module, then by capability. `concept` and `implementation` are **empty in every row**. The verdict-issue column carries the issue that decides the row; `#1` is the map, which is where a verdict is decided unless a narrower ticket takes it.

<!-- BEGIN DERIVED TABLE -->
| capability | kind | role | legacy module | concept | implementation | verdict issue |
| --- | --- | --- | --- | --- | --- | --- |
| `ArtifactIdentity` | `declared-record` |  | `groundscan/_util.py` | `preserved` | `preserved` | #95 |
| `ScaleEstimate` | `declared-record` |  | `groundscan/_util.py` | `preserved` | `corrected` | #95 |
| `ScanAnalysisResult` | `declared-record` |  | `groundscan/api.py` | `redesigned` | `replaced` | #95 |
| `groundscan/cli/__init__.py` | `no-output` | `callable-surface` | `groundscan/cli/__init__.py` | `removed` | `removed` | #96 |
| `groundscan/cli/analyze.py` | `no-output` | `callable-surface` | `groundscan/cli/analyze.py` | `removed` | `removed` | #96 |
| `groundscan/cli/diagnose.py` | `no-output` | `callable-surface` | `groundscan/cli/diagnose.py` | `removed` | `removed` | #96 |
| `groundscan/cli/quality.py` | `no-output` | `callable-surface` | `groundscan/cli/quality.py` | `removed` | `removed` | #96 |
| `groundscan/cli/validate.py` | `no-output` | `callable-surface` | `groundscan/cli/validate.py` | `removed` | `removed` | #96 |
| `AnomalyMap` | `declared-record` |  | `groundscan/core/anomaly.py` | `preserved` | `corrected` | #97 |
| `ArtifactMap` | `declared-record` |  | `groundscan/core/anomaly.py` | `preserved` | `preserved` | #97 |
| `groundscan/core/background.py` | `no-output` | `callable-surface` | `groundscan/core/background.py` | `preserved` | `corrected` | #97 |
| `ClassificationConfig` | `declared-record` |  | `groundscan/core/classify.py` | `removed` | `removed` | #97 |
| `EvidenceModelConfig` | `declared-record` |  | `groundscan/core/evidence.py` | `preserved` | `preserved` | #97 |
| `Grid2D` | `declared-record` |  | `groundscan/core/grid.py` | `redesigned` | `replaced` | #97 |
| `groundscan/core/morphology.py` | `no-output` | `callable-surface` | `groundscan/core/morphology.py` | `preserved` | `preserved` | #97 |
| `ExtractionRescuePolicy` | `declared-record` |  | `groundscan/core/rescue.py` | `deferred` | `preserved` | #97 |
| `groundscan/core/shape.py` | `no-output` | `callable-surface` | `groundscan/core/shape.py` | `preserved` | `corrected` | #97 |
| `ZigzagDiagnosis` | `declared-record` |  | `groundscan/core/zigzag.py` | `removed` | `removed` | #97 |
| `DipoleMergeConfig` | `declared-record` |  | `groundscan/diagnostics/dipole.py` | `preserved` | `preserved` | #98 |
| `DipolePairAssessment` | `declared-record` |  | `groundscan/diagnostics/dipole.py` | `preserved` | `corrected` | #98 |
| `LoadedExport` | `declared-record` |  | `groundscan/diagnostics/okm.py` | `removed` | `removed` | #98 |
| `groundscan/diagnostics/quality_probe.py` | `no-output` | `callable-surface` | `groundscan/diagnostics/quality_probe.py` | `preserved` | `preserved` | #98 |
| `RoleShadow` | `declared-record` |  | `groundscan/diagnostics/shadow.py` | `removed` | `removed` | #98 |
| `ScaleShadow` | `declared-record` |  | `groundscan/diagnostics/shadow.py` | `removed` | `removed` | #98 |
| `ShadowMeasurement` | `declared-record` |  | `groundscan/diagnostics/shadow.py` | `removed` | `removed` | #98 |
| `SolidityShadow` | `declared-record` |  | `groundscan/diagnostics/shadow.py` | `removed` | `removed` | #98 |
| `FieldQualityAssessment` | `declared-record` |  | `groundscan/gates/field_quality.py` | `redesigned` | `replaced` | #99 |
| `GeometrySummary` | `declared-record` |  | `groundscan/gates/geometry.py` | `redesigned` | `replaced` | #99 |
| `OperationalAssessment` | `declared-record` |  | `groundscan/gates/operational.py` | `redesigned` | `replaced` | #99 |
| `QualityAssessment` | `declared-record` |  | `groundscan/gates/quality.py` | `removed` | `removed` | #99 |
| `ScreeningPolicy` | `declared-record` |  | `groundscan/gates/screening.py` | `removed` | `removed` | #99 |
| `groundscan/gates/thresholds.py` | `no-output` | `callable-surface` | `groundscan/gates/thresholds.py` | `removed` | `removed` | #99 |
| `groundscan/io/__init__.py` | `no-output` | `callable-surface` | `groundscan/io/__init__.py` | `removed` | `removed` | #100 |
| `groundscan/io/base.py` | `no-output` | `callable-surface` | `groundscan/io/base.py` | `removed` | `removed` | #100 |
| `groundscan/io/generic_csv.py` | `no-output` | `callable-surface` | `groundscan/io/generic_csv.py` | `removed` | `removed` | #100 |
| `groundscan/io/rover.py` | `no-output` | `callable-surface` | `groundscan/io/rover.py` | `redesigned` | `replaced` | #100 |
| `Candidate` | `declared-record` |  | `groundscan/models.py` | `redesigned` | `replaced` | #95 |
| `CoordinateSemantics` | `declared-record` |  | `groundscan/models.py` | `redesigned` | `replaced` | #95 |
| `ScanData` | `declared-record` |  | `groundscan/models.py` | `redesigned` | `replaced` | #95 |
| `ScanMetadata` | `declared-record` |  | `groundscan/models.py` | `redesigned` | `replaced` | #95 |
| `AnalysisConfig` | `declared-record` |  | `groundscan/services/config.py` | `redesigned` | `replaced` | #101 |
| `groundscan/services/machine_contract.py` | `no-output` | `callable-surface` | `groundscan/services/machine_contract.py` | `redesigned` | `replaced` | #101 |
| `groundscan/services/single_scan.py` | `no-output` | `callable-surface` | `groundscan/services/single_scan.py` | `redesigned` | `replaced` | #101 |
| `CandidateEnrichment` | `declared-record` |  | `groundscan/services/single_scan_stages.py` | `preserved` | `corrected` | #101 |
| `groundscan/site/agreement.py` | `no-output` | `callable-surface` | `groundscan/site/agreement.py` | `preserved` | `corrected` | #102 |
| `MultiScanResult` | `declared-record` |  | `groundscan/site/analyze_site.py` | `redesigned` | `replaced` | #102 |
| `ScanObservation` | `declared-record` |  | `groundscan/site/analyze_site.py` | `redesigned` | `replaced` | #102 |
| `SiteRegistration` | `declared-record` |  | `groundscan/site/analyze_site.py` | `redesigned` | `replaced` | #102 |
| `ConflictBuildContext` | `declared-record` |  | `groundscan/site/conflict_verdicts.py` | `preserved` | `corrected` | #102 |
| `groundscan/site/consensus.py` | `no-output` | `private-only` | `groundscan/site/consensus.py` | `preserved` | `corrected` | #102 |
| `DepthFusion` | `declared-record` |  | `groundscan/site/fusion.py` | `redesigned` | `replaced` | #102 |
| `GeometryFusion` | `declared-record` |  | `groundscan/site/fusion.py` | `redesigned` | `replaced` | #102 |
| `AlignmentResult` | `declared-record` |  | `groundscan/site/registration.py` | `redesigned` | `replaced` | #102 |
| `SeparationConfig` | `declared-record` |  | `groundscan/site/separation.py` | `preserved` | `preserved` | #102 |
| `groundscan/site/separation_diagnostics.py` | `no-output` | `callable-surface` | `groundscan/site/separation_diagnostics.py` | `preserved` | `preserved` | #102 |
| `groundscan/site/separation_dipole.py` | `no-output` | `callable-surface` | `groundscan/site/separation_dipole.py` | `preserved` | `preserved` | #102 |
| `groundscan/site/separation_fragments.py` | `no-output` | `private-only` | `groundscan/site/separation_fragments.py` | `preserved` | `corrected` | #102 |
| `groundscan/site/separation_seeds.py` | `no-output` | `private-only` | `groundscan/site/separation_seeds.py` | `preserved` | `preserved` | #102 |
| `UncertaintyProfile` | `declared-record` |  | `groundscan/site/uncertainty.py` | `redesigned` | `replaced` | #102 |
| `groundscan/site/verdicts.py` | `no-output` | `private-only` | `groundscan/site/verdicts.py` | `removed` | `removed` | #102 |
| `groundscan/soil/context.py` | `no-output` | `callable-surface` | `groundscan/soil/context.py` | `preserved` | `corrected` | #103 |
| `SoilPhysicsDiagnostics` | `declared-record` |  | `groundscan/soil/experimental.py` | `removed` | `removed` | #103 |
| `CalibrationDataset` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `redesigned` | `removed` | #105 |
| `PerturbationCase` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `redesigned` | `removed` | #105 |
| `ProductionShapeMetrics` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `preserved` | `removed` | #105 |
| `Provenance` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `preserved` | `removed` | #105 |
| `ShapeSample` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `preserved` | `removed` | #105 |
| `VendorFixture` | `declared-record` |  | `groundscan/validation/calibration/datasets.py` | `redesigned` | `removed` | #105 |
| `MarginObservation` | `declared-record` |  | `groundscan/validation/calibration/decision.py` | `removed` | `removed` | #105 |
| `PopulationBaseline` | `declared-record` |  | `groundscan/validation/calibration/decision.py` | `removed` | `removed` | #105 |
| `PopulationMember` | `declared-record` |  | `groundscan/validation/calibration/decision.py` | `removed` | `removed` | #105 |
| `ThreeSigmaObservation` | `declared-record` |  | `groundscan/validation/calibration/decision.py` | `removed` | `removed` | #105 |
| `ThresholdSpec` | `declared-record` |  | `groundscan/validation/calibration/decision.py` | `removed` | `removed` | #105 |
| `EnvelopeRow` | `declared-record` |  | `groundscan/validation/calibration/envelope.py` | `redesigned` | `removed` | #105 |
| `CompactnessRow` | `declared-record` |  | `groundscan/validation/calibration/geometry.py` | `preserved` | `removed` | #105 |
| `SolidityBand` | `declared-record` |  | `groundscan/validation/calibration/geometry.py` | `removed` | `removed` | #105 |
| `SolidityCensusRow` | `declared-record` |  | `groundscan/validation/calibration/geometry.py` | `preserved` | `removed` | #105 |
| `groundscan/validation/calibration/interactions.py` | `no-output` | `callable-surface` | `groundscan/validation/calibration/interactions.py` | `removed` | `removed` | #105 |
| `ParameterRecord` | `declared-record` |  | `groundscan/validation/calibration/register.py` | `redesigned` | `removed` | #105 |
| `DetectorRun` | `declared-record` |  | `groundscan/validation/calibration/resolution.py` | `removed` | `removed` | #105 |
| `MinSizeObservation` | `declared-record` |  | `groundscan/validation/calibration/resolution.py` | `removed` | `removed` | #105 |
| `SeparationSummary` | `declared-record` |  | `groundscan/validation/calibration/resolution.py` | `removed` | `removed` | #105 |
| `SeparationTrial` | `declared-record` |  | `groundscan/validation/calibration/resolution.py` | `removed` | `removed` | #105 |
| `MultiplicityFinding` | `declared-record` |  | `groundscan/validation/decomposition_reference.py` | `removed` | `removed` | #104 |
| `PerturbedRun` | `declared-record` |  | `groundscan/validation/decomposition_reference.py` | `removed` | `removed` | #104 |
| `ResolvableSeparation` | `declared-record` |  | `groundscan/validation/decomposition_reference.py` | `removed` | `removed` | #104 |
| `ResponseGroup` | `declared-record` |  | `groundscan/validation/decomposition_reference.py` | `removed` | `removed` | #104 |
| `StabilityVerdict` | `declared-record` |  | `groundscan/validation/decomposition_reference.py` | `removed` | `removed` | #104 |
| `InputCensus` | `declared-record` |  | `groundscan/validation/decomposition_shadow_report.py` | `removed` | `removed` | #104 |
| `RunObservation` | `declared-record` |  | `groundscan/validation/decomposition_shadow_report.py` | `removed` | `removed` | #104 |
| `groundscan/validation/extraction.py` | `no-output` | `private-only` | `groundscan/validation/extraction.py` | `removed` | `removed` | #104 |
| `FieldTruthCase` | `declared-record` |  | `groundscan/validation/field.py` | `removed` | `removed` | #104 |
| `groundscan/validation/fixtures.py` | `no-output` | `constants-only` | `groundscan/validation/fixtures.py` | `removed` | `removed` | #104 |
| `groundscan/validation/golden.py` | `no-output` | `callable-surface` | `groundscan/validation/golden.py` | `removed` | `removed` | #104 |
| `groundscan/validation/payload_schema.py` | `no-output` | `callable-surface` | `groundscan/validation/payload_schema.py` | `removed` | `removed` | #104 |
| `groundscan/validation/profiles.py` | `no-output` | `constants-only` | `groundscan/validation/profiles.py` | `removed` | `removed` | #104 |
| `ContaminationOutcome` | `declared-record` |  | `groundscan/validation/scale_contamination_experiment.py` | `removed` | `removed` | #104 |
| `Criterion` | `declared-record` |  | `groundscan/validation/scale_reference.py` | `removed` | `removed` | #104 |
| `QuantisationVerdict` | `declared-record` |  | `groundscan/validation/scale_reference.py` | `removed` | `removed` | #104 |
| `RegimeCensus` | `declared-record` |  | `groundscan/validation/scale_reference.py` | `removed` | `removed` | #104 |
| `ScaleCase` | `declared-record` |  | `groundscan/validation/scale_reference.py` | `removed` | `removed` | #104 |
| `ResidualComparison` | `declared-record` |  | `groundscan/validation/scale_shadow_report.py` | `removed` | `removed` | #104 |
| `ScaleImpact` | `declared-record` |  | `groundscan/validation/scale_shadow_report.py` | `removed` | `removed` | #104 |
| `ScaleShadowReport` | `declared-record` |  | `groundscan/validation/scale_shadow_report.py` | `removed` | `removed` | #104 |
| `groundscan/validation/science_reporting.py` | `no-output` | `callable-surface` | `groundscan/validation/science_reporting.py` | `removed` | `removed` | #104 |
| `groundscan/validation/scientific.py` | `no-output` | `callable-surface` | `groundscan/validation/scientific.py` | `removed` | `removed` | #104 |
| `ReferenceCase` | `declared-record` |  | `groundscan/validation/solidity_reference.py` | `removed` | `removed` | #104 |
| `SolidityReference` | `declared-record` |  | `groundscan/validation/solidity_reference.py` | `removed` | `removed` | #104 |
| `ClassificationImpact` | `declared-record` |  | `groundscan/validation/solidity_shadow_report.py` | `removed` | `removed` | #104 |
| `ComponentComparison` | `declared-record` |  | `groundscan/validation/solidity_shadow_report.py` | `removed` | `removed` | #104 |
| `SolidityShadowReport` | `declared-record` |  | `groundscan/validation/solidity_shadow_report.py` | `removed` | `removed` | #104 |
| `groundscan/validation/synthetic_core/acquisition_stress.py` | `no-output` | `callable-surface` | `groundscan/validation/synthetic_core/acquisition_stress.py` | `removed` | `removed` | #106 |
| `BenchmarkRow` | `declared-record` |  | `groundscan/validation/synthetic_core/benchmark.py` | `removed` | `removed` | #106 |
| `AggregateMetrics` | `declared-record` |  | `groundscan/validation/synthetic_core/benchmark_large.py` | `removed` | `removed` | #106 |
| `CaseResult` | `declared-record` |  | `groundscan/validation/synthetic_core/benchmark_large.py` | `removed` | `removed` | #106 |
| `SyntheticScenario` | `declared-record` |  | `groundscan/validation/synthetic_core/core.py` | `preserved` | `removed` | #106 |
| `SyntheticTarget` | `declared-record` |  | `groundscan/validation/synthetic_core/core.py` | `preserved` | `removed` | #106 |
| `CrossResolutionFinding` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `LevelRecord` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `PhysicalResponse` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `PhysicalScene` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `Resolution` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `ResolutionEnsemble` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `ResolutionObservation` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_resolution.py` | `removed` | `removed` | #106 |
| `groundscan/validation/synthetic_core/cross_resolution_cases.py` | `no-output` | `callable-surface` | `groundscan/validation/synthetic_core/cross_resolution_cases.py` | `removed` | `removed` | #106 |
| `Variation` | `declared-record` |  | `groundscan/validation/synthetic_core/cross_scan_variation_audit.py` | `removed` | `removed` | #106 |
| `StressCaseResult` | `declared-record` |  | `groundscan/validation/synthetic_core/geology_local.py` | `removed` | `removed` | #106 |
| `groundscan/validation/synthetic_core/hard_regression.py` | `no-output` | `callable-surface` | `groundscan/validation/synthetic_core/hard_regression.py` | `removed` | `removed` | #106 |
| `groundscan/validation/synthetic_core/metamorphic.py` | `no-output` | `callable-surface` | `groundscan/validation/synthetic_core/metamorphic.py` | `removed` | `removed` | #106 |
| `MultiScanSiteSpec` | `declared-record` |  | `groundscan/validation/synthetic_core/multiscan_benchmark.py` | `removed` | `removed` | #106 |
| `NegativeCase` | `declared-record` |  | `groundscan/validation/synthetic_core/negative.py` | `preserved` | `removed` | #106 |
| `groundscan/validation/synthetic_core/oracles.py` | `no-output` | `callable-surface` | `groundscan/validation/synthetic_core/oracles.py` | `removed` | `removed` | #106 |
| `PerturbationProfile` | `declared-record` |  | `groundscan/validation/synthetic_core/robustness.py` | `removed` | `removed` | #106 |
| `VendorTruthCase` | `declared-record` |  | `groundscan/validation/vendor.py` | `removed` | `removed` | #104 |
| `groundscan_research/adaptive_scale_separation.py` | `no-output` | `callable-surface` | `groundscan_research/adaptive_scale_separation.py` | `removed` | `removed` | #111 |
| `groundscan_research/background_decomposition.py` | `no-output` | `callable-surface` | `groundscan_research/background_decomposition.py` | `removed` | `removed` | #111 |
| `groundscan_research/background_factor_attribution.py` | `no-output` | `callable-surface` | `groundscan_research/background_factor_attribution.py` | `removed` | `removed` | #111 |
| `groundscan_research/background_independent_separation.py` | `no-output` | `callable-surface` | `groundscan_research/background_independent_separation.py` | `removed` | `removed` | #111 |
| `groundscan_research/background_separation_audit.py` | `no-output` | `callable-surface` | `groundscan_research/background_separation_audit.py` | `removed` | `removed` | #111 |
| `groundscan_research/broad_response_representation.py` | `no-output` | `callable-surface` | `groundscan_research/broad_response_representation.py` | `removed` | `removed` | #111 |
| `groundscan_research/compound_interaction_analysis.py` | `no-output` | `callable-surface` | `groundscan_research/compound_interaction_analysis.py` | `removed` | `removed` | #111 |
| `groundscan_research/cross_scan_evidence_audit.py` | `no-output` | `callable-surface` | `groundscan_research/cross_scan_evidence_audit.py` | `removed` | `removed` | #111 |
| `groundscan_research/cross_scan_evidence_calibration.py` | `no-output` | `callable-surface` | `groundscan_research/cross_scan_evidence_calibration.py` | `removed` | `removed` | #111 |
| `groundscan_research/cross_scan_evidence_repeated_holdouts.py` | `no-output` | `callable-surface` | `groundscan_research/cross_scan_evidence_repeated_holdouts.py` | `removed` | `removed` | #111 |
| `groundscan_research/cross_scan_evidence_stability.py` | `no-output` | `callable-surface` | `groundscan_research/cross_scan_evidence_stability.py` | `removed` | `removed` | #111 |
| `groundscan_research/extraction_rescue_discriminants.py` | `no-output` | `callable-surface` | `groundscan_research/extraction_rescue_discriminants.py` | `removed` | `removed` | #111 |
| `groundscan_research/forward_background_interaction.py` | `no-output` | `callable-surface` | `groundscan_research/forward_background_interaction.py` | `removed` | `removed` | #111 |
| `groundscan_research/generator_c_mechanism.py` | `no-output` | `callable-surface` | `groundscan_research/generator_c_mechanism.py` | `removed` | `removed` | #111 |
| `groundscan_research/generator_shift_analysis.py` | `no-output` | `callable-surface` | `groundscan_research/generator_shift_analysis.py` | `removed` | `removed` | #111 |
| `groundscan_research/geology_extraction_independence.py` | `no-output` | `callable-surface` | `groundscan_research/geology_extraction_independence.py` | `removed` | `removed` | #111 |
| `groundscan_research/geology_extraction_shift.py` | `no-output` | `callable-surface` | `groundscan_research/geology_extraction_shift.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_compound_atlas.py` | `no-output` | `callable-surface` | `groundscan_research/registration_compound_atlas.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_compound_recovery.py` | `no-output` | `callable-surface` | `groundscan_research/registration_compound_recovery.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_failure_semantics.py` | `no-output` | `callable-surface` | `groundscan_research/registration_failure_semantics.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_recovery_coverage.py` | `no-output` | `callable-surface` | `groundscan_research/registration_recovery_coverage.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_recovery_experiments.py` | `no-output` | `callable-surface` | `groundscan_research/registration_recovery_experiments.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_recovery_repeated.py` | `no-output` | `callable-surface` | `groundscan_research/registration_recovery_repeated.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_robustness.py` | `no-output` | `callable-surface` | `groundscan_research/registration_robustness.py` | `removed` | `removed` | #111 |
| `groundscan_research/registration_semantics.py` | `no-output` | `callable-surface` | `groundscan_research/registration_semantics.py` | `removed` | `removed` | #111 |
| `groundscan_research/spatial_context_audit.py` | `no-output` | `callable-surface` | `groundscan_research/spatial_context_audit.py` | `removed` | `removed` | #111 |
| `groundscan_research/synthetic_generator_independence.py` | `no-output` | `callable-surface` | `groundscan_research/synthetic_generator_independence.py` | `removed` | `removed` | #111 |
| `tools/benchmark.py` | `no-output` | `callable-surface` | `tools/benchmark.py` | `removed` | `removed` | #107 |
| `tools/calibration_report.py` | `no-output` | `callable-surface` | `tools/calibration_report.py` | `removed` | `removed` | #107 |
| `tools/decomposition_shadow_report.py` | `no-output` | `callable-surface` | `tools/decomposition_shadow_report.py` | `removed` | `removed` | #107 |
| `Mutation` | `declared-record` |  | `tools/mutation_ratchet.py` | `removed` | `removed` | #107 |

<!-- END DERIVED TABLE -->

## What the derivation found

Counts here are **derived, not maintained**. Any figure in this section is reproduced by `python scripts/derive_capabilities.py report`, and a figure restated without that command beside it is a maintained count, which is what this project has been bitten by.

**Denominator: 135 files.** 199 `.py` under `docs/legacy/`, less 64 under `tests/`.

**Rows: 165** -- 98 `declared-record`, 67 `no-output`.

| subtree | rows |
| --- | --- |
| `groundscan/` (top level) | 7 |
| `groundscan/cli/` | 5 |
| `groundscan/core/` | 10 |
| `groundscan/diagnostics/` | 8 |
| `groundscan/gates/` | 6 |
| `groundscan/io/` | 4 |
| `groundscan/services/` | 4 |
| `groundscan/site/` | 16 |
| `groundscan/soil/` | 2 |
| `groundscan/validation/` | 72 |
| `groundscan_research/` | 27 |
| `tools/` | 4 |

**Verdicts: 0 located, 165 empty.** The second number is the work queue, and it could not be written before this derivation ran -- a count written from a plan is the defect this project has recorded twice over.

**Every denominator module carries a row except the excluded set, which the derivation names.** Run `python scripts/derive_capabilities.py report` for `modules_covered` and `excluded_modules`; the covered count is never written here. The excluded set is the re-export facades plus the runner registry below.

### Findings, each needing a decision that is not this artefact's to make

**A settings surface keeps its row, as a `declared-record`, and no rule can say otherwise.** `core/rescue.py` holds no capability -- its diagnostics are an untyped `dict`, and its single record, `ExtractionRescuePolicy`, is a declared guardrail set -- yet the rule above gives it a `declared-record` row, because the record is declared at module level like any other. The same holds for six more: `AnalysisConfig`, `ClassificationConfig`, `EvidenceModelConfig`, `DipoleMergeConfig`, `ScreeningPolicy`, `SeparationConfig`. **Not a third kind, and not a `no-output` row.** `core/rescue.py` therefore keeps its row and takes no location row: #90's expectation that it belongs as a `no-output` row was right that the module holds no capability and wrong about the row, and it is answered rather than satisfied. A named exclusion set of seven was refused, because #88's own stated reason the artefact exists is that a capability nobody decided about was unnoticeable rather than merely discouraged -- a named set can report a stale entry but can never detect a new one. **Row set untouched at 165 and still fully derived.** Collision-free: `declared-record` matches no row name and no legacy module-level definition, by #92's own test.

**Five predicates tried, none separating -- recorded qualitatively, with no counts.** The predicates were: every annotated field carries a default; never in a return position anywhere in the tree; never serialised by class name at a serialisation site; returned by a function in its own declaring module; declaration-suffix name probe. The structural blocker is `ResolvableSeparation`: frozen, every field defaulted, a module singleton consumed as a parameter default, never returned anywhere -- and not a settings surface -- so any predicate catching `ExtractionRescuePolicy` catches it too. Three counterexamples name the failure: an all-fields-defaulted test drops `ShadowMeasurement` and `RegimeCensus`, which are results, and keeps `ScanMetadata`, which is an input. No counts are recorded here, because the five predicates have no committed producer under `scripts/` and a count with no producer can only drift.

**No knob has a fate of its own; each field's fate is decided at the row of the capability that reads it.** Every field of all seven is read by zero or more capabilities, and every one of those readers is a row already or becomes one. `SeparationConfig` fields are read only inside `separate_fused_candidates`; `ExtractionRescuePolicy` fields only inside `propose_conservative_geology_rescues`; `AnalysisConfig` fields across `api.analyze`, `single_scan` and `single_scan_stages`. `ClassificationConfig` fields are read by nothing -- `del config` at `core/classify.py:155`, with the comment "config is accepted and ignored" -- so they have no capability to attach to and die with nothing to decide. The instrument is per-field by construction, because each field lands on a different row.

**The verdict vocabulary does not change.** Both coordinates stand on every row, and #92's `fixtures.py` ruling generalises from `constants-only` to every row whose subject is a declaration: a verdict on such a row is about the surface, never about behaviour, and `preserved` is honest only when the surface's meaning survives rather than its value. No third coordinate, and no new value. This artefact decides no verdict; it rules only on what a verdict may say.

**The settings-provenance echo is contract fact, recorded as prose and never as a row.** Three of the seven copy field values into what reaches `analysis.json`, always as scalars and never the record: `AnalysisConfig.threshold` and `.scales` as `anomaly_threshold`/`background_scales` (`machine_contract.py:200-201`); five of nine `ScreeningPolicy` fields via `screening_summary` into `metadata.extra["screening_policy"]`; six of ten `ExtractionRescuePolicy` fields via `diagnostics["guardrails"]` into `metadata.extra["extraction_rescue"]`. #35 and #70 already rule that conventions travel where they are determined, so this is what the frozen contract's convention-travelling rules catch, and destination item 5 -- which is about capabilities -- is not its subject.

**The census records a declared guardrail set, with caller-settable a separate fact four of the seven fail.** `DipoleMergeConfig`, `SeparationConfig`, `ClassificationConfig` and `EvidenceModelConfig` have zero caller-supplied construction anywhere in the tree, only their own `DEFAULT_*` singleton. `ClassificationConfig` gates nothing; `EvidenceModelConfig` gates 2 of its 6 fields in production, the other 4 read only by the calibration harness. No live/inert gradation column.

**A `no-output` row is a location, not a capability.** The facade shape is dropped: a module that declares no definition of its own and re-exports from a module in the tree takes no row, so a duplicate location is not a double verdict. The private-only rows are the sharpest: `site/consensus.py`, `site/separation_fragments.py`, `site/separation_seeds.py`, `site/verdicts.py` and `validation/extraction.py` hold implementation behind underscore-prefixed names, imported by sibling modules *only* for their private names. They are three cases, not one: consumed in-tree rows decided in `groundscan/site`; cross-subtree consumption recorded here in prose, not as a field; and the unreferenced row decidable only at itself. The fusion and separation stages those four implement are enumerated against `site/analyze_site.py` and `site/separation.py` instead, so **a verdict recorded against the stage silently covers code the census names only at the private row.** The constants-only rows -- `validation/fixtures.py` and `validation/profiles.py` -- are a settings surface with no behaviour at all, and stay `no-output` rows as [#91](https://github.com/abdoupk/groundscan-analyzer-v2/issues/91) ruled.

**`fixtures.py` takes a note, not a verdict.** A `constants-only` row's verdict is about the surface, never about behaviour. `VENDOR_ROOT` reads `GROUNDSCAN_VENDOR_ROOT` from the environment, so the path is operator-supplied and absent from the corpus, and the corpus is not committed pending redistribution rights. A verdict there decides a surface whose value the census cannot state.

**The record grain cannot exhibit a name collision, and the callable grain would have had eleven.** Rows are keyed by record class and no two denominator modules declare the same one, so the collision question is empty at this grain and recorded rather than answered. At callable grain the tree carries 11: `aggregate` (4 modules), `main` (5), `finite_values` (3), and `analyze_site`, `aspect_sweep`, `assert_no_object_count_claim`, `case_by_name`, `compare_scan`, `exact_solidity`, `robust_scale`, `run_registration_recovery_audit` (2 each). `run_registration_recovery_audit` is the sharp one: two research modules declare it, and the `registration_recovery.py` facade re-exports both under one name, so one of them is unreachable through the facade.

**The research subtree does not close at its module count.** Each of its non-excluded modules contributes exactly one `no-output` row, and the subtree was already found to hold a programme whose modules cluster into families -- registration recovery, cross-scan evidence, generator and generalisation, background separation and attribution, geology independence. **A verdict per module is a different act from a verdict per family**, and nothing here decides which grain the subtree is adjudicated at.

### What reproduced from [#89](https://github.com/abdoupk/groundscan-analyzer-v2/issues/89)

**All five of the research subtree's pure facades reproduce as excluded surfaces**, and the derivation finds eleven more outside it -- nine `__init__.py` facades, `groundscan/__main__.py`, and `core/artifact.py`. Every target takes a row already with zero chains, so the coverage check is one hop and not a fixpoint. The first pass found only two of the five, because two of them use absolute imports and the rest relative; the facade predicate now accepts either, and the miss is recorded because it is the shape of error this map exists to prevent: a count written from one reading rather than measured. The subtree's private-symbol coupling, its study structure and its absent study outputs are outside this artefact's question and were not re-measured.

## Checks

Two, both owed here rather than later, and they have different reach.

**The unconditional check** lives in `tests/test_capabilities.py` and runs offline. It asserts that every row's kind and role tokens are in the closed sets, that role is populated exactly when kind is `no-output`, that every row cites an issue number in the right form, that the two verdict columns are empty or hold a member of their vocabulary, and that no row carries verdict prose. It also asserts that a facade target takes a row with one hop and that the excluded set is the derived one. **It does not call the tracker.** A network call in a unit test is a flake source with no diagnostic value, in a repository already running `timeout = 120`, `filterwarnings = ["error"]` and `-n=auto`.

**What the unconditional check cannot do, stated rather than left implied:** it cannot tell whether a cited issue still exists. That residual is undetectable offline and **costs nothing real, because issues are not deleted on this tracker** -- so a citation to a vanished issue would be caught by a reader and by nothing else.

**The conditional check** asserts that every `.py` in the denominator carries a row, and that the row set equals what the derivation produces. **`docs/legacy/` is untracked** -- present on disk, absent from git and absent from `.gitignore` -- so **for any reader without the archaeology this check records "not checked", never "passed."** The mechanism is real and the guarantee is not universal, and that is a condition already recorded elsewhere on this map: the precedent it would otherwise follow is one whose cited artefacts are themselves untracked.

**No path manifest is committed to make the conditional check universal.** Two committed lists can be edited to agree with each other, so such a check could never catch a capability added to the archaeology -- which is the failure it exists to fix.

## Out of the census

- **`tests/`** -- 64 files. They assert about capabilities and have none. The map already disposes of preserving legacy tests.
- **`results/`** -- holds only `.gitkeep`.
- **Re-export facades** -- excluded by rule 3. The derivation names the set; run `python scripts/derive_capabilities.py report` for `excluded_modules` and `re_export_facades`. No list is maintained here.
- **`docs/legacy/groundscan_research/__init__.py`** -- a registry of the research runners carrying `RESEARCH_SUITES` and `EXPERIMENTAL_RUNNERS` with no record class, so it takes no `declared-record` row like any other package marker. Excluded by rule 3; its fate travels with [#93](https://github.com/abdoupk/groundscan-analyzer-v2/issues/93), as [#91](https://github.com/abdoupk/groundscan-analyzer-v2/issues/91) ruled.
- **`tools/` is in the census and is not science.** Four files take four rows. Whether a developer-facing ratchet is a legacy scientific capability is a question the rows make visible rather than one they answer.

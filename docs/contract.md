# Contract vocabulary

The shipped, versioned home of every closed vocabulary the contract has. The
module `groundscan_analyzer.property_registry` declares the same five sets;
this file states them where a reader can see them, so the two cannot drift.

Contract version: 1, Registry version: 3. The two travel once at the document
root, beside each other, so a registry change is never mistakable for a change
of record shape.

## Rules

Stated rather than only enforced, so a reader can see each rule without
running the check.

- **The module is the single home of the five closed vocabularies.** The nine output classes, the five scope footprint groups, the transform vocabulary with its refusal register, the eight contract conventions, and the output census live in one shipped module. A contributor placing an output, a mover, or a convention finds all three in the same place rather than in the decision that created each.
- **A closed set is closed against its own members, never against the world.** The lint verifies that a name exists in the declaring module, never that the list is complete. A member name must resolve, and an unknown member name fails the checks.
- **An `_Avoid_` line is declaration, not use.** The glossary records forbidden vocabulary on its avoidance lines, which is why the glossary is inside the lint's scope while corpora quoting that vocabulary stay outside. A headword carrying banned material by design on its avoidance line is not a violation, and a headword that loses its avoidance line is a check failure.
- **The placement test is the only way an output enters a class.** An output is a registry output only when it is decided from the computation, carried on the record, and a state that is withheld rather than a caveat. Three clauses, all three required, and no fourth way in.
- **Failing the placement test is an answer, not a gap.** An output failing the test is registered as a non-output carrying which clause it failed: decided-from-computation, carried-on-record, or withheld-state-not-caveat. A contributor who cannot place an output does not create a class; the partition reopens deliberately or not at all.
- **A census edit is a semantic contract change.** The census holds one line per registry output carrying its class, or the non-output marker with its failed clause. Added, reclassed, or removed alike, a census edit bumps the registry version beside the contract version.

## Vocabularies

All five are closed and versioned together with the module above. A
corruption of any declared set fails the checks; filling every set correctly
turns them green.

### `output-classes`

| value | meaning |
| --- | --- |
| `identity` | measured content and frame naming |
| `lattice-structure` | observed lattice facts |
| `analysis-quantity` | computed evidence quantities |
| `hierarchy-structure` | component tree facts |
| `positional-expression` | positions in declared extents |
| `numbered-presentation` | lattice-order numbering |
| `boundary-evidence` | adjacency and contact facts |
| `recorded-fact` | decided guards and relations |
| `limitation` | withheld reasons a quantity emits |

### `scope-groups`

| value | meaning |
| --- | --- |
| `residual-field` | outputs the residual derivation moves |
| `effective-amplitude` | outputs the amplitude derivation moves |
| `scale-agreement` | outputs the scale computation moves |
| `field-position` | outputs the metric series moves |
| `frame-relation` | outputs the frame composition moves |

### `transforms`

| value | meaning |
| --- | --- |
| `identity` | the reflection orbit's fixed point |
| `reflect-along-line` | reflection along the line axis |
| `reflect-across-lines` | reflection across the lines axis |
| `reflect-both` | composition of both reflections |
| `index-relabelling` | relabelling of lattice indices |
| `row-permutation` | permutation of file rows |
| `survey-reordering` | reordering of named survey inputs |
| `padding-addition` | adding empty cells only |
| `non-load-bearing-field-substitution` | free-text field substitution |
| `context-column-substitution` | context column substitution |
| `metric-echo-substitution` | vendor echo substitution |
| `unframed-position-value-substitution` | discarded coordinate substitution |
| `dialect-substitution` | separator reading substitution |
| `re-rooting` | change of canonical reference |
| `level-cut` | cutting the hierarchy at a level |
| `convention-bump` | re-deriving a named convention |

### `refusal-register`

| value | meaning |
| --- | --- |
| `rot90` | a quarter turn maps no lattice to itself |
| `padding-relocation` | turning a measured cell into padding removes content |
| `sub-lattice-resampling` | resampling manufactures values |
| `perturbation` | deliberately changing the measurement |
| `physical-reading` | interpreting measurement as ground |

### `conventions`

| value | meaning |
| --- | --- |
| `quantile-v1` | which quantile definition is of record |
| `background-model-v1` | which background model is of record |
| `scale-agreement-v1` | which scale estimators and tolerance are of record |
| `anchor-rule-v1` | how a declared amplitude becomes effective |
| `field-position-v1` | which metric series is of record |
| `relative-turn-v1` | which turn mapping table is of record |
| `canonical-reference-v1` | which reference rule is of record |
| `default-numeric-reading-v1` | which numeric reading is of record |

### `grades`

| value | meaning |
| --- | --- |
| `exact` | invariance holds identically, proved from construction |
| `bounded` | deviation is bounded, with the bound derived |

### `warrant-kinds`

| value | meaning |
| --- | --- |
| `shared-order-statistic` | a shared order statistic over a census |
| `transitive-closure` | a transitive closure checkable against the record |
| `monotonicity` | monotonicity in a quantity the output is compared against |
| `dominance` | dominance between footprints |
| `non-constancy-in-metric-scale` | non-constancy in the metric scale, one scalar only |
| `direct-dependence-on-declared-data` | direct dependence on declared convention data |
| `reference-relativity` | reference-relativity, not determined by relations alone |
| `route-independence` | route-independence, reads nothing the convention acts on |

### `evidence-coverage`

| value | meaning |
| --- | --- |
| `real-data` | exercised on operator-shaped vendor exports |
| `synthetic-only` | exercised on manufactured surveys only |
| `unexercised` | no sweep varies the convention at all |

## Census

One line per registry output, keyed on the registry rather than on the
record. Each line carries its class and, where a footprint is a strict
subset, its members as glossary terms. A census edit is a semantic
contract change: added, reclassed or removed alike, it bumps the registry
version beside the contract version.

<!-- BEGIN VOCABULARY -->
| output | class | members |
| --- | --- | --- |
| `solidity` | `analysis-quantity` |  |
| `compactness` | `analysis-quantity` |  |
| `field-area` | `analysis-quantity` | `Field area` |
| `depth-interval` | `analysis-quantity` |  |
| `lattice-boundary-contact` | `boundary-evidence` |  |
| `padding-adjacency-contact` | `boundary-evidence` |  |
| `component-size-in-cells` | `analysis-quantity` |  |
| `detection-count` | `hierarchy-structure` |  |
| `component-count` | `hierarchy-structure` |  |
| `scan-local-position` | `positional-expression` | `Scan-local position` |
| `field-position` | `positional-expression` | `Field position`, `Survey position`, `Shared-frame position` |
| `shared-frame-position` | `positional-expression` | `Survey position`, `Shared-frame position` |
| `robust-scale` | `analysis-quantity` |  |
| `median-atom-fraction` | `analysis-quantity` |  |
| `scale-disagreement` | `analysis-quantity` |  |
| `scale-tie-tolerance` | `analysis-quantity` |  |
| `scale-normalised-level` | `analysis-quantity` |  |
| `payload-hash` | `identity` |  |
| `frame-identity` | `identity` | `Shared frame` |
| `lattice` | `lattice-structure` |  |
| `parent-map` | `hierarchy-structure` |  |
| `detection-number` | `numbered-presentation` |  |
| `mask-invariance` | `recorded-fact` | `Effective amplitude` |
| `frame-relation` | `recorded-fact` | `Frame relation` |
| `aspect-consistency` | `recorded-fact` | `Aspect consistency` |
| `registration-evidence` | `recorded-fact` |  |
| `recurrence` | `recorded-fact` |  |
| `requires-declared-extent` | `limitation` | `requires-declared-extent` |
| `requires-homogeneous-axes` | `limitation` | `requires-homogeneous-axes` |
| `requires-bounded-perturbation` | `limitation` | `requires-bounded-perturbation` |
| `requires-recorded-perturbation-bound` | `limitation` | `requires-recorded-perturbation-bound` |
| `missing-orientation-path` | `limitation` | `missing-orientation-path` |
| `scale-not-warranted` | `limitation` | `scale-not-warranted` |
| `scale-not-positive-finite` | `limitation` | `scale-not-positive-finite` |
| `non-unique-argmax` | `limitation` | `non-unique-argmax` |
| `tied-within-recorded-bound` | `limitation` | `tied-within-recorded-bound` |
| `unstable-under-recorded-perturbation` | `limitation` | `unstable-under-recorded-perturbation` |
| `requires-recorded-displacement-bound` | `limitation` | `requires-recorded-displacement-bound` |
| `requires-bounded-displacement` | `limitation` | `requires-bounded-displacement` |
| `requires-scorable-shifts` | `limitation` | `requires-scorable-shifts` |
| `missing-comparability-warrant` | `limitation` | `missing-comparability-warrant` |
| `differing-lattice-dimensions` | `limitation` | `differing-lattice-dimensions` |
| `missing-declared-relation` | `limitation` | `missing-declared-relation` |
| `contradictory-relation` | `limitation` | `contradictory-relation` |
<!-- END VOCABULARY -->

# Measurement register

The single home for every **corpus-derived number** quoted on this project, and for its **standing**.

A number measured against the nine real OKM exports is admissible as support for a decision only if it can say what produced it. A number that cannot is not thereby wrong — it is **untraceable**, and a traceable-sounding figure that nobody can reproduce is worse than an absent one, because it gets quoted. This register exists so that a figure's standing is written down **once**, where a later correction can reach it.

That last clause is the whole point, and it is not hypothetical. GitHub issue **comments are immutable**, so every withdrawal this project has made until now landed as a *later comment that the withdrawn text cannot see*. The withdrawn `51 / 4 / 11 / 6` was still unmarked live prose in four places, including the hazard table in the resolution of [The order-dependence inventory and its tie rules](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15). This file is editable. That is why it is here and not there.

## The rule

A corpus-derived number used as evidence must carry the settings that produced it. It is quoted from this register, by entry, never restated at the point of use.

Seven axes may bear on a figure. State the ones that apply; a figure needing none of them is exempt.

| Axis | Pinned by |
| --- | --- |
| lattice / padding state | the export itself |
| background window, shape, support rule, combination | **`background-model-v1`** — [The background model](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39) |
| quantile convention | **`quantile-v1`** (H&F type 2, pinned by both stated criteria) — [The quantile convention](https://github.com/abdoupk/groundscan-analyzer-v2/issues/36) |
| scale estimator and its calibration constants | MAD + IQR on a σ target — [Which two robust-scale estimators](https://github.com/abdoupk/groundscan-analyzer-v2/issues/31) |
| connectivity | fixed convention, 4 or 8, named per figure |
| level / threshold | named where the figure is a count or a thresholded set |
| perturbation protocol — kind, magnitude, reference quantity, seed, trial count | all five, or not a stability figure |

**Three of the seven are now pinned**, so a sweep run today has only **connectivity, level and the perturbation protocol** free.

### Standing

Every entry carries exactly one. The vocabulary is **closed**.

| Standing | Means | May be quoted as |
| --- | --- | --- |
| `recorded` | every applicable axis is carried | a **point value** |
| `swept` | a declared sweep (axes **and extent**) plus a measured spread across it are carried | the sweep's **interval** — never as a point |
| `unpinned` | settings were not carried, and no sweep exists | **not evidence.** History only. |
| `unrecoverable` | a declared sweep exists and the figure is **not reachable** in it | **retired.** Supports nothing. |

`legacy-sweep` is the **provenance label**, not a standing: it marks a figure whose settings were not carried. A `legacy-sweep` figure becomes `swept` once a sweep is supplied and becomes `unrecoverable` when a sweep proves it absent; it stays `unpinned` until then.

### The two properties that make this a rule and not a caveat

1. **The spread never decides anything.** It *is* the figure's interval. There is no threshold anywhere in this file, so there is no number here that a judgement about acceptability can move.
2. **The rule binds the ticket that declares it.** [The background model](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39) declared every residual-field-dependent figure stale and then reused one unmarked in the same comment. That is the shape every future violation will take if the declarer is exempt. It is not exempt.

### Exempt

Not corpus-derived measurements, and so not bound by the rule. Recorded here so the exemption is **visible rather than assumed**:

- **Definitional** — bounds and identities proved from a definition (`ceil(L·W/2)` as the independence number of the connectivity graph).
- **Synthetic** — results over constructed grids, probes or fixtures. A manufactured field says nothing about a real export.
- **Exact-oracle derived** — computations from rational arithmetic or an exact-integer oracle, independent of any corpus (`C₀ = 4/5`, `c₁` by `n mod 4`, the median-atom lemma's 2,011-case verification).
- **Raw-column** — statistics read off a column with no processing convention applied (value integrality, index origin, a raw median).

## Measurement environment

Recorded because the rule requires the environment fingerprint and, until now, no figure on this project carried one.

```
python      3.13.15 (CPython)
platform    Windows-11-10.0.26200-SP0, AMD64, little-endian
numpy       2.5.3
scipy       1.18.1
```

**Known deviation, recorded rather than hidden.** The `background-model-v1` census below was taken with the scale factor written as `1.4826`. The pinned constant is `1/Z₇₅ = 1.482602218505602`. These are not equal. The discrepancy is `1.5 × 10⁻⁶` relative, which moves the quoted σ values in their eighth significant figure and changes **no** zero-versus-non-zero determination — every MAD-zero result in that table is zero under either constant. The constant as written is the one that produced the figures.

---

## Entries

`—` in the settings column means the figure needs none of the seven axes.

### [Detection core: background, scale, threshold, connectivity](https://github.com/abdoupk/groundscan-analyzer-v2/issues/11)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| fitted plane leaves trend exceeding residual spread in **6 of 9 files**; `Anomaly at the Edge` 2.56×, `Royal Tomb` 2.51×, `Pipeline` 1.47× | whether a global trend exceeds residual spread | background, lattice | `unpinned` | Named stale by [The background model](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39), then reused unmarked there. **Supports nothing.** The trend-term rejection now rests on the claim boundary alone: a plane is a geometric claim about ground shape. |
| `Gallery and Tunnel` **53 → 167-186**, `Royal Tomb` **164 → 245-285** | node count before → range across perturbation trials | perturbation protocol, background, connectivity, level, lattice | `unpinned` | Withdrawn by [The order-dependence inventory](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15). Unmarked in its resolution and in two others. **Retirement confirmed** by [Which residual-field figures survive re-measurement](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42): the perturbation protocol's five axes were never carried and the pipeline that produced the figure is gone, so no re-measurement recovers it. Replaced there by a node-count measurement under a declared protocol — a **different quantity at a declared level**, not a reproduction. |
| top-8 lifetimes move **~0.5% median** | hierarchy stability under perturbation | as above | **`unrecoverable`** | **Withdrawn by #42.** Declared sweep: the protocol of record below, over four readings of "top" and both connectivities; the figure as stated is not reachable, and the magnitude moves by **two orders of magnitude** across the corpus under one declared protocol. Replaced by a `recorded` entry in the re-measurement section. |
| `Anomaly at the Edge` **24 → 32**, `Royal Tomb` **164 → 201** | node count under 4- vs 8-connectivity | connectivity (**recorded**), background, level | `unpinned` | Connectivity is the one axis this figure carries. |
| top-lifespan ÷ residual sd falls between **0.00 and 0.06** | level comparability across scans | scale estimator, background, lattice, level | **`unrecoverable`** | **Withdrawn by #42.** Zero of the sixteen declared settings reproduce it, and on **3 of 9** exports the *smallest possible* node lifespan already exceeds `0.06` of the spread, so the band is unreachable under **any** reading of "top" rather than merely un-reproduced. The non-transferability conclusion does **not** rest on this figure — it rests on the tree and the residual scale being per scan — and it is unaffected by the withdrawal. |
| `min ImpulseX = 1`, `min ScanLineY = 1` in all nine | index origin | — | exempt (raw column) | Normative via [The input contract](https://github.com/abdoupk/groundscan-analyzer-v2/issues/23). |
| six of nine exports are **100% integral** | value integrality | — | exempt (raw column) | Re-confirmed under the pinned ladder. |
| `Gallery and Tunnel` median 176, range 163-177, **MAD exactly 0.000** | raw `Scan Value` statistics | — | exempt (raw column) | **Not** #31's residual-field MAD. Do not conflate the two. |
| one contaminated cell among 200 inflating scale by **three orders of magnitude** | legacy's documented scale failure | — | exempt (legacy quotation) | Legacy's own documented failure, not a v2 measurement. |
| excursion rate **4.9×** nominal; **0.5-1.1×**; **zero** components survive a 3-cell cut from 16×16 to 128×128 | false-positive rate on white noise | — | exempt (synthetic) | Not corpus. |

### [Characterisation: what a detection is made of](https://github.com/abdoupk/groundscan-analyzer-v2/issues/13)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| dominance **13 stable / 0 drifting / 0 unstable**, worst **0.0101** | stability of the peak-magnitude ratio | perturbation protocol, level, connectivity, background, scale | **`unrecoverable`** | **Withdrawn by #42**, on two independent grounds. **The classification half has no admissible form**: `stable` / `drifting` / `unstable` are three bands, and a band is a threshold, which [#7](https://github.com/abdoupk/groundscan-analyzer-v2/issues/7) deletes and [#28](https://github.com/abdoupk/groundscan-analyzer-v2/issues/28) forbids. There is no threshold anywhere in this file to recover them from. **The magnitude half is unreachable as a worst case**: under the protocol of record, **0 of 18** (export, polarity) pairs have a maximum relative deviation of `0.0101` and **3 of 18** exceed it, the sweep's worst case being `0.055107`. Replaced by a `recorded` entry. Dominance's structural stability was never a corpus result — see the ticket's own audit note. |
| `Tunnel - Original` **3.87**, `Tunnel - Control` **2.97** | robust scale of the one repeat pair | scale estimator, background, quantile, lattice | `unpinned` | **This refutes the hint that opened this audit.** It was floated as a candidate for admission precisely because a dispersion scalar is less sensitive than a count. It has no recorded settings and no sweep, so it is `unpinned` like everything else. Sensitivity was never the test; **traceability** is. |
| **0 of 1** match at 2 sd, **1 of 2** at 3 sd | recurrence on the only real pair | the sd's estimator and convention, correspondence rule, cell tolerance, relative orientation | `unpinned` | The tolerance is stated in sd units; nothing behind that sd is stated. |
| component count drifts **0-8** at a fixed level | count spread across trials | perturbation protocol, level, connectivity, background, scale | `unpinned` | Superseded by #42's per-trial **multisets** at a declared level, which is the form [#32](https://github.com/abdoupk/groundscan-analyzer-v2/issues/32) decision 4 requires. A drift *range* is what this ticket recorded and a multiset is what the contract ships. |
| solidity / compactness **exact per-component, matched by position, in every file, all trials** | ratio stability under perturbation | perturbation protocol, level, connectivity, background | `unpinned` | Trial count and seed not recorded. |
| compactness **0.5890** vs **0.6702** | ring vs notched pair | connectivity, level, lattice | `unpinned` | The source cells are not identified in the ticket. |
| `Tunnel - Original` **1** distinct fractional part, `Tunnel - Control` **106** | value integrality | — | exempt (raw column) | |

### [The order-dependence inventory and its tie rules](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| `Royal Tomb` **51 / 4 / 11 / 6** at 1/2/3/4 sd | component count at four levels | background, scale, connectivity, level, lattice | **`unrecoverable`** | **Zero of 2,260 settings**, untuned, across a declared sweep (background window per axis, edge/detrending mode, connectivity, scale estimator, sigma source). No interval exists. Retired. |
| **`51`** at 1 sd, in **59 of 2,260** settings | one component of the retired tuple | as above | `unpinned` | The sweep exists and is declared, but no spread was computed and no per-setting record was kept — so there is no interval to quote. **Adjudicated by #42 as out of that ticket's scope**, on two grounds. It is a **sweep** figure, so closing it means re-running the declared sweep with the three now-pinned axes fixed — a *new* declared sweep, not a re-measurement of a stale figure, and #42 is chartered to re-measure rather than to sweep. And it is a **component of a retired tuple**: promoting one element of a figure already `unrecoverable` would invert that retirement rather than complete it. It needs a sweep ticket, which must keep the per-setting record this entry lacks. |
| three-cell witness `1 0 1`, counts **1 → 2** | minimal non-monotone witness | — | exempt (constructed) | The replacement evidence, and reproducible by inspection. |
| `51 / 4 / 11 / 6` nearest misses `(51,6,7,8)`, `(49,4,9,9)`, … | partial reproduction | as above | `unpinned` | Tuples given, settings not. |
| duplicated row gives an **exact** peak tie (`18.0 == 18.0`) | tie behaviour | background, connectivity, level, scale | `unpinned` | Row and level not identified. |
| **1,352** candidates, zero shift a unique maximum with margin **0.033** | registration margin | perturbation protocol (6 trials), search space, seed | `unpinned` | Count of trials recorded; the rest were not. |
| margin distribution **0.1373-0.6881** relative; **0.9998** constructed vs **0.7678** real pair | separation margin | construction recipe, scale estimator, background | `unpinned` | The constructed-repeat recipe was not recorded; the real pair needs the background. |
| argmax invariant across **6** perturbations on all **7** sources | self-alignment stability | perturbation protocol | `unpinned` | Count and scope recorded; kind, magnitude and seed were not. |
| three scans × six permutations → **three distinct bitwise results**, spread **~1e-16** | float non-associativity | summation routine, quantile, environment | `unpinned` | Routines were named; the environment fingerprint was not — this file's first entry. |
| **0** exact ties in **400** constructed equal-blob trials; `[0,1,1,1,1]` gives MAD and IQR both exactly **0.0** | tie rate; estimator blind spot | — | exempt (constructed) | |

### [Which two robust-scale estimators, and what agreement tolerance](https://github.com/abdoupk/groundscan-analyzer-v2/issues/31)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| **43** residual fields across the nine exports | field count | background, lattice | `unpinned` | Its *meaning* changed: clipping removed the per-scan scale set, so a "residual field" is no longer one of several per export. |
| precedence census **0 / 0 / 5 / 38** | which scale-status state fired | background, scale, quantile, lattice | `unpinned` | This is #39's "MAD-zero file list", declared stale there. **Confirmed and superseded by #42**: the "2 of 9" reachability came from the four-scale ladder `{3,5,9,15}` (two exports had at least one MAD-zero field). Under the pinned ladder `{3,5,9}` the state is reached on **1 of 9**, and that figure is `recorded` in the `scale_status` census above. Standing here stays `unpinned` because *its own* settings were not carried; it is superseded, not admitted. |
| **`Gallery and Tunnel` atom fractions 0.8063 / 0.7550 / 0.6587 / 0.6450** at windows 3/5/9/15; `Royal Tomb` window 3 at **0.5708** | median-atom fraction per window | background, lattice | `unpinned` | Superseded — see the `background-model-v1` census below. |
| **6** exact agreements; disagreement min **1.668e-03**, median **0.040633**, max **0.253847** | estimator agreement | background, scale, quantile, lattice | `unpinned` | Superseded in-ticket by **1.118568233e-03 / 0.04761905 / 0.25878215**. Both unpinned. |
| **2** rows with `MAD == 0`, `IQR == 0.741301`, atom fractions 0.6587 and 0.6450 | the saturated-tolerance rows | background | `unpinned` | |
| corpus max **`L/s = 1.178688`** | distance from `tie-tolerance-saturated` | background, scale | `unpinned` | |
| MAD bit-identical on **43/43** fields across the convention change | convention-invariance | background, scale, quantile | `unpinned` | Evidence **coverage** only. #30 forbids a measured agreement from justifying or strengthening a grade. |
| **6 ties / 32 disagreements / 5 median-atom-zero / 0 constant / 0 no-finite**, 43 total, 0 misclassifications | partition under the final pin | background, scale, quantile | `unpinned` | |
| corpus cannot discriminate `c₁ = 0` at `n = 75`, `n = 247` | discriminating power of the corpus | background, scale, environment | `unpinned` | Every `c₁ ≥ 0` is consistent with the corpus. |
| `C₀ = 4/5`; `c₁` by `n mod 4`; **0 / 8,035** odd-`n` fields exceed `C₀ = 4`; **347 / 431** offset-0 cases; median-atom lemma over **2,011** cases with 0 disagreements | derived constants and exact verifications | — | exempt (exact oracle) | The model of what a traceable figure looks like: the constants are **derived**, so they do not depend on a corpus at all. |

### [Magnitude-instability as a hazard class](https://github.com/abdoupk/groundscan-analyzer-v2/issues/32)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| `Royal Tomb` **53 → 167-186**, second file **164 → 245-285** (body, `→` and en-dashes) | node count under perturbation | perturbation protocol, background, connectivity, level | `unpinned` | **Attribution conflict, retired rather than resolved.** #11 and two others attribute these to `Gallery and Tunnel` / `Royal Tomb`; this body swaps them. The figure is unpinned under an unpinned background either way, so the standing does not depend on which export produced it — and a sweep cannot recover it, because the pipeline that made it is gone. Measured effort here would answer a question the rule has already answered. **#42 confirms the retirement is the right call** and adds that the withdrawal is not merely procedural: the exported hierarchy's node count moves by **an order of magnitude** under a protocol of record, so the pair is unreachable in the declared sweep as well. |
| **4 → `ceil(L·W/2)`**, **8 → `ceil(L/2)·ceil(W/2)`** | maximum component count per connectivity | — | exempt (definitional) | Proved as the independence number of the connectivity graph, verified over 632,084 pairs. A **theorem**, so it needs no corpus. **Re-established by #42 against the [quantity registry](https://github.com/abdoupk/groundscan-analyzer-v2/issues/34)** and unmoved: the bound is a function of the lattice's two dimensions and of the connectivity alone, and no corpus count touches it. The registry's oracle is independent by construction here, since nothing computes the quantity twice. |
| the corpus ceiling figures in this ticket's closing table (`Royal Tomb` **257 / 233**, `Gallery and Tunnel` **144 / 111**, `Pipeline` **60 / 49**, `Anomaly at the Edge` **33 / 28**, `Iron Box` **21 / 17**, 4- then 8-connectivity) | the largest component count reached at any level | background, connectivity, level | `recorded` — **and inadmissible as a per-polarity witness** | **Read by #42 and re-registered here.** The column is not a component *size* but the **cross-polarity total**: the maximum over levels of the positive count **plus** the negative count. Six of nine reproduce exactly on 4-connectivity and three of four on 8-connectivity; `Anomaly at the Edge` is `32` against `33`, `Pipeline` `59` against `60`, `Tunnel - Control Scan` `20` against `23`, and the two 8-connectivity figures are each one low — recorded rather than smoothed. **This is the defect:** decision 2 above states *"No cross-polarity total is shipped"*, and the amendment's own text presents the table as sharpening a **per-polarity** ceiling. A cross-polarity total is not admissible evidence for a per-polarity bound, so the table does not witness what it is offered as witnessing. The **bound** is unaffected; only the corpus witness is. |
| `N = 9` gives **5** on `1x9` and **4** on `3x3` | that the 8-bound needs both dimensions | — | exempt (definitional) | |
| **94.28%** of **41.6M** grids non-monotone | prevalence in the uniform `4×4` three-value family | — | exempt (synthetic) | **Correction: the two tickets frame 41.6M differently.** #32 reads it as the total grid count at 94.28% non-monotone; [Non-monotone component counts](https://github.com/abdoupk/groundscan-analyzer-v2/issues/33) reads 41.6M as *already* the non-monotone count. `0.9428 × 41.6M = 39.2M`, so they are not the same set. |
| single-bridge **39.6%** / **46.29%** / **~52%**; **44.1M**, **43,046,721** grids; ring-cut **4 / 12 / 24 / 48 / 72** | synthetic-family properties | — | exempt (synthetic) | |

### [Non-monotone component counts in the level](https://github.com/abdoupk/groundscan-analyzer-v2/issues/33)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| the declared sweep: **2,260 settings**, **zero** reproductions; **27 real settings each listed with its setting**; **648** complete four-tuples of which **72** degenerate | the sweep itself | — | `recorded` | **The one fully declared sweep on this project, and the model for every other.** Each row carries window, height, edge mode, connectivity and estimator. |
| `Royal Tomb`, zero ordering flips in **31,680** | ordering stability | perturbation protocol, background, scale, connectivity, level | `unpinned` | Already reclassified in place as "not robustness". |
| 2 sd threshold clears by **0.0348 = 2.35×** the noise amplitude | lattice clearance | perturbation protocol, scale, background | `unpinned` | |
| guard over **1,188 settings**: TP 820 / FN 152 / **FP 0** / TN 216 | mask-invariance guard accuracy | perturbation protocol, background, scale, connectivity | `unpinned` | Sweep declared; no per-setting record kept, so no interval. |
| **59** settings give `count(1sd) = 51`; **8** give both | partial reproduction | as the 51 entry above | `unpinned` | |
| **2,590** (setting, mode) pairs with zero spread; **62 of 2,376** with genuine variation | ordering vs magnitude | perturbation protocol, background, scale | `unpinned` | **Retracted by the ticket itself** — measured under a fixed sigma against a recomputed one. Recorded so it is not re-quoted. |

### `background-model-v1` — census taken under [The background model](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| per-export σ, polarity counts, extreme residuals, **median-atom fractions 0.7525 and 0.4792**, median-of-3 = B₅ on **80.8%** of cells, unusable-scale state on **1 of 9** | properties of the pinned residual field | background (**recorded**), lattice and zero padding (**recorded**), quantile convention (**recorded**), scale estimator (**recorded**, with the `1.4826` deviation above) | `recorded` | The first figure on this project that passes this rule, and it needed only the environment fingerprint added. Connectivity, level and perturbation protocol do not apply to a census. |

### `scale_status` census — taken under [The not-emitted reason for an unusable robust scale](https://github.com/abdoupk/groundscan-analyzer-v2/issues/37)

Same residual field as the census above, so the same background, lattice and fingerprint. Two additions of its own: the **quantile convention** was computed in the pinned floor form (`j = floor(np)`, `gamma = 1/2` at `g = 0` else `1`, no endpoint clamping) rather than through a library, and the **scale estimator** is the pinned pair on one σ target — `σ(MAD) = MAD / Z₇₅` and `σ(IQR) = IQR / (2·Z₇₅)` with `Z₇₅ = Φ⁻¹(0.75) = 0.6744897501960817`.

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| state census: **1** `median-atom`, **2** `exact-agreement`, **6** `disagreement`, **0** `no-finite-values`, **0** `constant-field` | which `scale_status` state each export reaches | background, lattice, quantile convention, scale estimator, environment | `recorded` | Connectivity, level and perturbation protocol do not apply. |
| the census's median-atom fractions, **0.7525** and **0.4792** | how much of a residual field is **exactly** its median | background, lattice, quantile convention, scale estimator | `recorded` | **This entry measures the corpus's lattice, not the engine**, and it is the structural reason both other states exist: a large atom is a large `IQR / MAD` ratio, and an exact equality in the data is what makes the two σ-estimates bit-identical. **No continuous draw can reach any of it.** Independence per measured cell plus continuity make pairwise-distinct residuals a probability-one event, so `MAD` is nonzero everywhere and the median atom is a single cell — `median-atom` becomes **unreachable**, `exact-agreement` stops being an exact float identity, and `disagreement` becomes an ordinary comparison. What that means for quoting this census: it describes the **unperturbed** field under `residual-perturbation-v1`, and per [#45](https://github.com/abdoupk/groundscan-analyzer-v2/issues/45) **the only instrument that can perturb a tied field is a `lattice-preserving` draw** — so the tied case is reachable in principle, and its coverage is a thing to be measured rather than assumed. |
| disagreement sizes `d/σ` of **0.500**, 0.169, 0.130, 0.069, 0.034, 0.016 | how far apart the two estimates are | as above | `recorded` | Smallest real `d` is **0.0304**, against a derived tolerance band of `4.44e-16` … `9.43e-16` — fifteen orders of magnitude clear, so none is a near-tie. |
| `IQR / MAD` of **1.0** (`Royal Tomb`) and **2.0** (`Error Signal`, `Tunnel - Original Scan`) | why the estimates differ, or coincide | as above | `recorded` | `2.0` makes the two σ-estimates bit-identical, so both "agreements" are an **exact float identity on an integral export** — a lattice artefact, not a fact about the estimators. `1.0` makes the IQR estimate *exactly half* the MAD estimate, hence the 50% disagreement. |
| `tie-tolerance-saturated` reached on **0 of 9** | whether the derived saturation state ever fires | as above | `recorded` | Registered by [#34](https://github.com/abdoupk/groundscan-analyzer-v2/issues/34) and **unreached**. Recorded so it is not mistaken for something observed. |
| `σ(MAD) × Z₇₅ − MAD` = `0.0` on seven exports, **2.22e-16** on `Iron Box`, **3.55e-15** on `Iron Treasure` | whether σ inverts exactly | as above | `recorded` | σ is **not** an exact inverse of MAD on two files in nine. Nothing in the record depends on recovering MAD from σ, so this is a fact rather than a defect — recorded because the assumption would be wrong if made. |

### `payload-perturbation-v1` — declared by [#45](https://github.com/abdoupk/groundscan-analyzer-v2/issues/45), no figures yet

The second anchor exists and is declared here so that its emptiness is **visible rather than inferred**. It answers the only question the first cannot: *what would change if the measurement were different.* Every axis is as declared under `residual-perturbation-v1` above — seed, trial count, level handling, draw, lattice applicability — **except two**.

| axis | value |
| --- | --- |
| anchor | **payload** — the **response column** is perturbed and the **background model is re-run**, so the residual moves by the perturbation *minus* the background's own response to it. Depth is **not** perturbed: it is evidence about a different question, and mixing two instruments into one figure would confound them |
| magnitude | **the same absolute amplitude** as `residual-perturbation-v1` — 1% of the residual field's population sd, injected into the payload. Matched **deliberately**, so a difference in outcome is attributable to the background model rather than to the magnitude rule. **Not** 1% of the payload's own spread, which is orders of magnitude larger and would make the two protocols incomparable. **Neither figure is a physical sensitivity**: the corpus has no repeat acquisition with known variation, so every magnitude here is a declared choice |

**What the second anchor already settles, with no run at all.** Three consequences follow from the declarations rather than from a measurement, and each retires a worry that was carried as open:

- **The detection count still saturates at the cell count.** Independent continuous noise on the payload leaves the residual's values pairwise distinct just as it does under the residual anchor, so `N = n` per polarity and [#43](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43)'s attainment holds under either protocol. The corpus witnesses the bound's sharpness either way, and the anchor was never what decided it.
- **Payload-protocol mask-invariance is strictly rarer than residual-protocol.** A median never moves further than the largest movement of its inputs, so a payload amplitude `a` bounds the residual at `2a` — tight, because raising more than half a window's values by `a` leaves the cell at its centre free to move the other way. Every threshold distance must clear twice the amplitude, so the guard reads `not-guaranteed` more often.
- **A `lattice-preserving` draw is what keeps the exact-equality machinery reachable.** It is the only declared draw under which the median atom, the MAD-zero state and the `IQR == 2·MAD` float identity can survive at all — every continuous draw destroys all three at once. That is the instrument this corpus needs and the one nothing has yet run.

### [The granularity of a level-derived output](https://github.com/abdoupk/groundscan-analyzer-v2/issues/40) — figures registered here by #42

The first entries this register holds from that ticket. Its tables were `background-model-v1` measurements sitting in an immutable comment, unregistered and therefore unquotable.

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| measured cells / residual-exactly-zero / cells entering the hierarchy, **per export**: `Gallery and Tunnel` **1600 / 1204 / 396**, `Royal Tomb` **2400 / 1150 / 1250**, `Iron Box` **247 / 15 / 232**, `Anomaly at the Edge` **240 / 17 / 223**, `Pipeline` **320 / 22 / 298**, `Tunnel - Control Scan` **248 / 32 / 216**, `Tunnel - Original Scan` **248 / 45 / 203**, `Iron Treasure with Silver and Gold Coins` **156 / 11 / 145**, `Error Signal` **75 / 19 / 56** | the hierarchy's population | background, lattice | `recorded` | **Reproduced exactly, all nine.** **Labelled per export deliberately**: the run that produced these listed them in an order that is *not* sorted-filename order, so the figures were unattributable until re-derived — the register's own known-limits section names this failure mode. The zero-residual column is [#31](https://github.com/abdoupk/groundscan-analyzer-v2/issues/31)'s median atom appearing as geometry, and it is the reason the largest per-level count sits so far below the definitional bound. `CONTEXT.md` quotes `1,150 of 2,400` and `1,204 of 1,600`; both are `Royal Tomb` and `Gallery and Tunnel` respectively, and both are now traceable here. |
| distinct residual magnitudes **per polarity, summed**, **per export**: `Royal Tomb` **29**, `Gallery and Tunnel` **18**, `Iron Box` **222**, `Anomaly at the Edge` **209**, `Pipeline` **153**, `Tunnel - Control Scan` **207**, `Tunnel - Original Scan` **35**, `Iron Treasure with Silver and Gold Coins` **117**, `Error Signal` **15**; levels with simultaneous entry, **same order**: **22 / 11 / 9 / 14 / 42 / 9 / 23 / 21 / 10**; cells in simultaneous entry: **1243 / 389 / 19 / 28 / 187 / 18 / 191 / 49 / 51**; largest single group: **480 / 213 / 3 / 2 / 17 / 2 / 30 / 5 / 15** | the hierarchy's level structure | background, lattice | `recorded` | **Reproduced exactly, all nine** — and only under the **per-polarity** reading, which is a definitional point rather than a tuning one: a level is a **(polarity, magnitude)** pair, so a magnitude occurring in both polarities is **two** levels, and simultaneous entry is counted within one polarity. Grouping across polarities reproduces **none** of the three columns. Taking the union of magnitudes gives `16` for `Royal Tomb` where the ticket records `29`. `CONTEXT.md`'s **Component hierarchy** entry said *"one level per distinct residual magnitude"* without saying per polarity; that is now **corrected in the glossary**, since the reading is ambiguous rather than merely terse and the figures depend on it. |
| detection (node) count, all nine exports | the hierarchy's size | background, lattice, connectivity, level | **`unpinned`** | **Does not reproduce, and three defensible readings of "node" give three different numbers.** For `Royal Tomb`: **932** summing the component count over levels, **435** counting each distinct cell-set node once, against **1,509** recorded by [#43](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43). The population and level-structure columns of the *same* tables reproduce exactly, and so do `n` and `m` for every export #43 lists — so the divergence is **localised to this one column**, and the construction behind it was never stated. Recorded because it is quoted as a ticket headline. **One lead, worth checking before the figure is relied on**: #43's `Error Signal` count of `75` is also that export's measured-cell count, and it is load-bearing for that ticket's refutation of `n + m − 1`. Needs a stated construction before it can be quoted; the bound `nodes ≤ 2n − 1` is untouched either way. **The construction is now stated, by [#44](https://github.com/abdoupk/groundscan-analyzer-v2/issues/44), and this column is not it.** Decided on the arithmetic rather than on provenance: the recorded figure **exceeds the cells entering the hierarchy on 9 of 9** exports, where the adopted construction falls **below** that count on **6 of 6**, and the sum-over-levels reading straddles it — so no reading of "node" reproduces this column, and since **two further constructions remain untested** (levels as the union of magnitudes across polarities; components taken over the merged cross-polarity mask), three readings is a **floor rather than a count**. The standing is unchanged and deliberately so: with neither a declared sweep nor carried settings the vocabulary already gives **`unpinned` — not evidence**. What changed is the **uses**: the figures are struck from [#43](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43)'s bound table and from the map's #40 entry. **The `Error Signal` lead is closed, and it indicts the column rather than exonerating it**: `75` is exactly `19` zero-residual `+ 56` entering, and measured `=` zero `+` entering identically, so that figure is the row's own first two columns added — a **transcription**, not a coincidence — and it was the one carrying #43's refutation of `n + m − 1`. |

### Re-measurement under `background-model-v1` — taken under [Which residual-field figures survive re-measurement](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42)

**Two perturbation protocols, not one.** [#42](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42) chose an anchor and recorded it without naming it; [#45](https://github.com/abdoupk/groundscan-analyzer-v2/issues/45) named both anchors, made the anchor a property of the **protocol** rather than of the figure, and ruled that **no stability figure may be quoted for a question its anchor does not answer**. A figure names its protocol and the question it answers; a figure with neither has no anchor and no claim. Both are **research instruments** — [#30](https://github.com/abdoupk/groundscan-analyzer-v2/issues/30) forbids a measured agreement from establishing or strengthening a property grade — so **neither appears in the contract**, and both live in this file.

**`residual-perturbation-v1`** — every figure in the entries below is taken under it. Newly chosen by #42 because **none** of #11's five axes survived; declared once here and cited by name rather than restated per entry.

| axis | value |
| --- | --- |
| anchor | **residual** — the residual field is perturbed directly and the **background model is not re-run**. Answers *what would change if this derived field were different*, with background estimation held fixed |
| draw | **continuous** — the uniform draw below, unmodified. The alternative is **`lattice-preserving`**: the same additive, independent, zero-mean draw **quantised to the scan's value lattice**, so every response stays a lattice point and the exact ties a lattice makes possible recur. Named for the **mechanism**; *tie-preserving* is the effect it has, not the name of the axis |
| kind | additive, independent per measured cell, zero-mean, **uniform on `[-1, 1]`**. **Bounded**, which is the choice that matters: [#33](https://github.com/abdoupk/groundscan-analyzer-v2/issues/33)'s mask-invariance guard is defined only for a bounded protocol, and an unbounded one leaves every field unguaranteed |
| magnitude | **1%** |
| reference quantity | the residual field's **population standard deviation** (`ddof=0`) over measured cells, computed once from the unperturbed field and held fixed. Chosen because it is **positive on all nine** exports, where `σ(MAD)` is exactly `0.0` on one — a stated reason, not a threshold |
| seed | `numpy.random.default_rng(20261004 + scan_index)`, `scan_index` the 0-based position in sorted-filename order; one generator per scan |
| trial count | **20** per scan, with the unperturbed field as the baseline |
| level handling | held **fixed in absolute residual units** across trials, per [#32](https://github.com/abdoupk/groundscan-analyzer-v2/issues/32) decision 4 |

**The value lattice, and when `lattice-preserving` applies at all.** The quantum `g` is the largest value every observed response is an exact multiple of, computed on the printed decimals — a **per-scan fact carried in scan context**, not an axis, and never the declared precision. A draw of amplitude `a` quantises to a realised `±q·g` at `q = round(a/g)`, so **a scan where `q = 0` is not applicable**: the trial perturbs nothing, no figure is quoted from it, and the count of applicable scans travels with every figure taken under this draw. **Expect that count to be small** — a 1% amplitude is below one quantum wherever the residual spread is under `50·g`, which on an integral export means it bites only on the widest fields. An export whose responses are all identical has no lattice at all, and is likewise not applicable.

**The level rule of record**, also newly chosen by #42 and needed because a level is a named axis: dominance and the per-level component counts are read at **the polarity's own median residual magnitude** — the level at which half of that polarity's cells are inside the cut and half outside. It is per scan, per polarity, and depends on no count and no connectivity, so it cannot be tuned toward a stability verdict.

**Implementation validation, recorded because it is what makes the entries below usable.** The `background-model-v1` + `quantile-v1` + pinned-scale implementation reproduces the `background-model-v1` census and the `scale_status` census **exactly**: median-atom fractions `0.7525` and `0.4792`, median-of-3 = B₅ on `80.8%` of exports, unusable-scale on **1 of 9**, the state census `1 / 2 / 6 / 0 / 0`, all nine per-export σ values, all eighteen polarity counts, all eighteen extreme-residual values, all nine `IQR/MAD` ratios and both invertibility exceptions. It used the **pinned** constant `1/Z₇₅ = 1.482602218505602`, not the census's rounded `1.4826`, and **no** determination moved. One recorded detail is worth keeping: the corpus `80.8%` is the **per-export mean** of the nine fractions, not a cell-weighted mean, which is `0.9028`. Read cell-weighted the figure does not reproduce.

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| dominance, worst relative deviation across **18** (export, polarity) pairs: per-pair maxima **0.001137 to 0.055107**, corpus worst **0.055107** | stability of the peak-magnitude ratio at a declared level | perturbation protocol (above), level (above), connectivity **4**, background, lattice | `recorded` | The replacement for the withdrawn `13 / 0 / 0` table. **Evidence coverage only** — it says how far the ratio moved under one declared protocol, and #30 forbids a measured agreement from establishing or strengthening a grade. The ratio's stability is argued from being a ratio over a thresholded set, which is where it comes from. All **18** pairs admit a level with ≥2 components, so existence never withheld here; the component count at the declared level runs **3 to 132** and travels with the figure. |
| dominance under the mask-invariance guard: **`not-guaranteed` on 18 of 18** | whether the ratio is *decided* rather than measured | as above | `recorded` | **Recorded because it is the honest ceiling on the entry above.** The guard reads `not-guaranteed` on every pair, for the reason #33 named: on an atom-heavy field the declared level collapses onto the median atom, so cells sit exactly at a threshold and the required gap is `0` or negative. Nothing here is decided; all of it is measured. `not-guaranteed` does **not** mean unstable. |
| top-lifespan ÷ residual spread, four declared readings of "top" × 2 connectivities × 2 denominators = **16 settings** | where a selected level sits in the hierarchy | background, lattice, connectivity, level (every level of the hierarchy), scale estimator for one denominator | `recorded` | The replacement for the withdrawn `0.00–0.06` band. Max-over-all-nodes runs **1.58 to 15.50** of the residual sd; median-of-the-eight-longest-lived **0.28 to 7.68**; max among the eight largest-by-area **0.017 to 2.26**; and over `σ(MAD)` **0.84 to 5.40** with **1 of 9 undefined** because `σ(MAD)` is exactly zero. **Reading 1 is uninformative and is recorded as such**: the longest-lived node spans nearly the whole magnitude range, so that reading restates the spread rather than measuring anything. Every informative reading sits **one to three orders of magnitude above** the withdrawn band. |
| provable floor on **any** node lifespan: smallest gap between consecutive distinct residual magnitudes, over `0.00000 to 0.45200` of the residual sd and `0.00000 to 0.33724` of `σ(MAD)` | the smallest lifespan the level grid admits | background, lattice | `recorded` | **This is what makes the withdrawal an impossibility rather than a non-reproduction.** A node cannot be born and die between two levels closer than the smallest gap, so on **3 of 9** exports (`Gallery and Tunnel`, `Royal Tomb`, `Tunnel - Original Scan` over the sd; `Error Signal`, `Royal Tomb`, `Tunnel - Original Scan` over `σ(MAD)`) **every** node already outlives the withdrawn band's upper edge. `Royal Tomb`'s magnitudes are half-integer spaced, so nothing there can have a lifespan below `0.34 σ`. The band was unreachable, not merely unmatched. |
| top-8 lifetimes, median relative deviation per trial: **0.005270 to 0.149736** across the nine exports | hierarchy stability at the top | perturbation protocol, background, lattice, connectivity **4**, level (every level) | `recorded` | The replacement for the withdrawn `~0.5%`. The withdrawn magnitude is corroborated at the **low** end — the smallest is `0.53%` — and exceeded by a factor of **28** at the high end, on `Error Signal`, the corpus's smallest lattice at `75` cells. A single magnitude quoted from a spread spanning two orders of magnitude was never a stable figure to quote. |
| detection count under the protocol, **summed over both polarities**: per-trial multiset is the **constant measured-cell count on 9 of 9** — **2400**, **1600**, **320**, **248**, **248**, **247**, **240**, **156**, **75** | whether the hierarchy's size is a stable quantity | `residual-perturbation-v1` (**anchor**, draw), background, lattice, connectivity **4**, level | `recorded` | The replacement for the withdrawn `53 → 167-186` pair, and the strongest form the hazard takes. **The median atom is destroyed by any continuous draw on the residual field**, because the atom is an *exact equality*: the zero-residual cells stop being zero, every measured cell enters the hierarchy, and each becomes its own node. So the detection count does not drift on this corpus — it **saturates**, at the measured cell count, on every trial. Nothing may depend on it as a stable quantity, and the reason is structural rather than statistical. **Taken under the construction [#44](https://github.com/abdoupk/groundscan-analyzer-v2/issues/44) settled — one node per birth — and summed over both polarities, which the contract does not itself emit.** That is legitimate here and only here: this entry measures the engine's *behaviour*, not a quantity it ships. **Its admissibility no longer rides on [#45](https://github.com/abdoupk/groundscan-analyzer-v2/issues/45) — that dependency is discharged, and the anchor plays no part in the figure.** What produces it is the **`anchor` axis not mattering plus two declared axes that do**: independence per measured cell and continuity. Together they make pairwise-distinct residuals a probability-one event, and distinct residuals give one cell and one birth per level. Moving the draw to the payload leaves the residual pairwise-distinct too, so `N = n` holds under either anchor — which is why [#43](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43)'s attainment is not at this ticket's mercy. **So read the entry as a fact about exact ties, not about the hierarchy**: it is a theorem about tie-free fields that this corpus happens to witness. **A `lattice-preserving` draw is the instrument that tests the tied case**, and it is the only one that can — no stability claim from this entry may be quoted without citing the protocol by name. |
| component count at the declared level, per-trial multisets: `24 → 24-25`, `13 → 8-13`, `141 → 111-138`, `14 → 14-16`, `23 → 22-24`, `52 → 49-51`, `257 → 282-317`, `19 → 19-19`, `20 → 21-27` | a count's own sensitivity | perturbation protocol, background, lattice, connectivity **4**, level (above) | `recorded` | Reported as the **multiset of per-trial counts plus the trial count**, never a reduced drift figure, because #32 decision 4 rules out a drift figure and the instability is a jump. Six of nine move; three are constant across all twenty trials. `Gallery and Tunnel` and `Royal Tomb` move in **opposite directions** — the count rises on one and falls on the other — which is the non-monotone-in-level mechanism seen in the perturbation direction instead of the level direction. |

### [The definitional bound on the detection count](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43) — three checks, kept separate

[#34](https://github.com/abdoupk/groundscan-analyzer-v2/issues/34) requires bound validity, witness attainment and production agreement to be **three** obligations rather than one, so they are three entries. Only the third is a measurement; the first two are definitional, and neither is established by the third.

| check | statement | basis | standing |
| --- | --- | --- | --- |
| **validity** | per polarity, **`c₁ ≤ N ≤ n`**, where `N` is the detection count, `n` the cells entering the hierarchy for that polarity, and `c₁` the components of that polarity's cell set. The summed count satisfies it too. | **Definitional, by charging.** Order levels by ascending magnitude, `g_j` the tie group at level `j`, so `Σ g_j = n`. Build active sets from the top magnitude down, adding one tie group at a time. The top level contributes at most `g_m` births. At each later step every component of the new active set either contains a cell of the group just added — new, hence a birth, at most `g_j` of them — or contains none, hence identical as a set to a component before, hence a continuation. So `N ≤ g_m + Σ_{j<m} g_j = n`. **Connectivity and `m` are never used.** | not a measurement |
| **attainment** | both ends reachable, and the **upper end is `n`**. | **Constructed, never read off the corpus.** Give every cell a **distinct magnitude**: each level then adds exactly one cell and yields exactly one birth, so `N = 1 + (n − 1) = n`, for any region under either connectivity — held in **2989 of 2989** randomised regions, and a theorem rather than a delicate arrangement. The lower end: with a single magnitude no component ever changes, so `N = c₁`. `N = n` is likewise attainable at **every** `(n, m)` including `m = 1` (scatter `n` mutually non-adjacent cells), so **no bound over `(n, m)` is tighter than `n`** and the bound is stated over `n` alone. | not a measurement |
| **production agreement** | 18 of 18 (export, polarity) pairs obey `N ≤ n`; **smallest margin `0`**. | measured, 4-connectivity, `background-model-v1`, the [#44](https://github.com/abdoupk/groundscan-analyzer-v2/issues/44) construction | `recorded` |

The production-agreement table, per polarity — `N/n` runs **0.328 to 1.000**, mean **0.768**, and 8-connectivity `N` is **≤** 4-connectivity `N` on **18 of 18**:

| export | pol | `n` | `m` | `N` | `n − N` | `N/n` | `c₁` | 8-conn `N` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Anomaly at the Edge` | pos | 111 | 104 | **111** | **0** | **1.000** | 12 | 108 |
| `Anomaly at the Edge` | neg | 112 | 105 | 111 | 1 | 0.991 | 6 | 111 |
| `Error Signal` | pos | 25 | 6 | 19 | 6 | 0.760 | 10 | 16 |
| `Error Signal` | neg | 31 | 9 | 21 | 10 | 0.677 | 9 | 19 |
| `Gallery and Tunnel` | pos | 108 | 5 | 53 | 55 | 0.491 | 53 | 48 |
| `Gallery and Tunnel` | neg | 288 | 13 | 124 | 164 | 0.431 | 91 | 90 |
| `Iron Box` | pos | 123 | 116 | 119 | 4 | 0.967 | 9 | 119 |
| `Iron Box` | neg | 109 | 106 | 108 | 1 | 0.991 | 9 | 108 |
| `Iron Treasure with Silver and Gold Coins` | pos | 73 | 60 | 71 | 2 | 0.973 | 12 | 70 |
| `Iron Treasure with Silver and Gold Coins` | neg | 72 | 57 | 70 | 2 | 0.972 | 12 | 70 |
| `Pipeline` | pos | 149 | 88 | 141 | 8 | 0.946 | 21 | 136 |
| `Pipeline` | neg | 149 | 65 | 135 | 14 | 0.906 | 21 | 125 |
| `Royal Tomb` | pos | 662 | 14 | 217 | 445 | 0.328 | 119 | 201 |
| `Royal Tomb` | neg | 588 | 15 | 218 | 370 | 0.371 | 129 | 207 |
| `Tunnel - Control Scan` | pos | 119 | 115 | 118 | 1 | 0.992 | 4 | 116 |
| `Tunnel - Control Scan` | neg | 97 | 92 | 96 | 1 | 0.990 | 6 | 96 |
| `Tunnel - Original Scan` | pos | 108 | 16 | 57 | 51 | 0.528 | 5 | 51 |
| `Tunnel - Original Scan` | neg | 95 | 19 | 48 | 47 | 0.505 | 4 | 47 |

**Three things this table is not evidence for.** The corpus **attains** the bound on `Anomaly at the Edge` positive at `N = n = 111`, and per [#30](https://github.com/abdoupk/groundscan-analyzer-v2/issues/30) that is **corroboration, not the witness** — the witness is the construction, and the bound is argued from it. The spread tracks `m/n` and not the ground: the near-saturated polarities carry many distinct magnitudes, the wide-margin ones are the integral exports where a few tie groups hold hundreds of cells each. And 8-connectivity never raising `N` is a **fact about this corpus**, not part of the bound, which never invokes connectivity.

**Saturation is attainment.** [#42](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42)'s per-trial multiset being the constant measured-cell count on 9 of 9 is this bound being reached: perturbing the residual destroys the median atom, every measured cell enters, and near-surely distinct magnitudes give `N = n` per polarity. The node count cannot drift, because the ceiling is the cell count and the ceiling is reachable. **Its admissibility therefore rides on [#45](https://github.com/abdoupk/groundscan-analyzer-v2/issues/45)**: under a payload-perturbation protocol the atom may survive and this corpus may never attain the bound at all.

**Refuted, not superseded: the `2n − 1` bound.** [#40](https://github.com/abdoupk/groundscan-analyzer-v2/issues/40)'s premise was a **merge-tree** bound, and this is not a merge tree — the active set shrinks as the level rises, so components **split**, and the nodes are merged cell sets forming a laminar family rather than a tree. `2n − 1` is attained **only at `n = 1`**. `n + m − 1` is valid and weaker than `n`, and is dropped rather than stated alongside; its refutation was already void per [#44](https://github.com/abdoupk/groundscan-analyzer-v2/issues/44).

**Also retired here: the 2.3% connectivity sensitivity.** [#40](https://github.com/abdoupk/groundscan-analyzer-v2/issues/40) and [#43](https://github.com/abdoupk/groundscan-analyzer-v2/issues/43) both leaned on *"changing node counts by at most 2.3% between 4- and 8-connectivity"*. It appears in **no** register entry, its standing is `unpinned`, and the 8-connectivity counts behind it are recorded **nowhere** for the node count. It was never load-bearing: the bound does not need it, and the connectivity question is closed on the proof instead.

### [The lattice and the impulse index](https://github.com/abdoupk/groundscan-analyzer-v2/issues/41) — the parse protocol of record

Declared because every figure below is a reading of the corpus and the rule requires the settings. Chosen once, held for all entries here.

| axis | value |
| --- | --- |
| encoding | `utf-8-sig` — all nine files carry a UTF-8 BOM, use bare LF, and no file parses without the BOM stripped |
| sections | located by **exact** match of `+++ Characteristics +++`, `+++ Meta Data +++`, `+++ Soil Type +++`, `+++ Measuring Values +++` |
| header row | the last line inside the Measuring Values block equal to the 8-column header after `strip()`. Its offset is **not** constant across the corpus — **26**, **28** or **30** — and it occurs exactly once per file |
| data row | any subsequent non-blank line with ≥ 6 comma fields whose first four parse as decimals. **0 lines dropped in 9 of 9**; every row carries exactly 8 fields, and latitude/longitude are empty in **21,085 of 21,085** |
| decimals | compared **as printed**, via `Decimal`, never as float. Printed precision is 4 dp in all six numeric columns of all nine files |
| derived quantity | implied spacing = `declared extent / (observed count − 1)`. The printed metric series reproduces as `round_half_up(spacing · k, 4)` with **0 divergences in 18 of 18** file-axes |

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| impulses per line × lines × rows, per export: `Gallery and Tunnel` **50 × 32 = 1600**, `Royal Tomb` **30 × 80 = 2400**, `Tunnel - Control Scan` **31 × 8 = 248**, `Tunnel - Original Scan` **31 × 8 = 248**, `Iron Treasure with Silver and Gold Coins` **26 × 6 = 156**, `Iron Box` **19 × 13 = 247**, `Anomaly at the Edge` **20 × 12 = 240**, `Pipeline` **10 × 32 = 320**, `Error Signal` **15 × 5 = 75** | the realised lattice size | parse protocol (above) | `recorded` | **Reproduced exactly, all nine, and `rows == count × lines` in 9 of 9** — so these counts **independently corroborate** the measured-cell counts [#42](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42) registered, cell for cell, by a route that never touched a residual field |
| declared `Field Length` → impulses per line: **3.00 m → 10, 19, 26**; **10.00 m → 20, 31, 31**; 6.00 m → 15; 15.00 m → 50; **20.00 m → 30**. Declared `Field Width` → lines: **3.00 m → 6, 13**; **8.00 m → 12, 32**; 9.00 m → 32; **10.00 m → 8**; 35.00 m → 80. `n_y = 32` under **both** 8.00 m and 9.00 m | whether the realised count is determined by the declared extent | parse protocol | `recorded` | **The load-bearing entry of this ticket.** No function of the declaration fits: the mapping is **non-monotone in both axes** and, in the `Field Width` case, **not single-valued**. So the count is not derivable from the declaration, nor the declaration from the count. What that leaves open is **causal, not derivable** — see the ticket's resolution |
| **no file declares a count.** The complete set of field names across all nine is identical in shape; the only length-like declarations are `Field Length` and `Field Width`, both in metres, once each. `Impulse Mode: Automatic` in **9 of 9** | whether a declared count exists to be compared against at all | parse protocol | `recorded` | A whole-file sweep for count-like fields returns only the header, `Impulse Mode`, and free-text prose in two `Notes`. **Zero** observations contrast automatic with operator-triggered counts, so the corpus can say nothing about how a *manual* mode would behave |
| metric echo: `max` equals the declared extent and `min` is `0.0000` in **18 of 18** file-axes | whether the vendor's series spans exactly the declared extent | parse protocol | `recorded` | **Re-confirms `metric-coordinate-v1`**, already measured by [#23](https://github.com/abdoupk/groundscan-analyzer-v2/issues/23) and [#8](https://github.com/abdoupk/groundscan-analyzer-v2/issues/8); registered here so the amendment of #23's short-line rule can cite a standing figure rather than a fresh claim |
| implied spacing **0.1200 – 0.6897 m** along the impulse axis, **0.2500 – 1.4286 m** across lines | how far apart the sampled positions are | parse protocol | `recorded` | Density runs **1.45 to 8.33** samples per metre along the impulse axis and **0.7 to 4** across lines. Printed adjacent differences take **two** distinct values in **14 of 18** axes — 4-dp rounding alone, not varying spacing; the 4 axes with a single printed difference are exactly those whose spacing is representable in ≤ 4 dp |
| **0** short lines in **9 of 9** — every line exactly `count` rows; indices contiguous from `1.0000` on both axes in 9 of 9; no gaps, no duplicate coordinate pairs, row order grouped by line throughout | whether the lattice is complete as exported | parse protocol | `recorded` | **This is what makes the observed-against-observed line check decidable on this corpus — and unexercised by it.** The genuine repeat pair agrees on every structural quantity (`10.00 m` both axes, **31 × 8**, **248** rows, index and metric columns byte-identical across all **248** rows; only depth and response differ) |

## Withdrawn by this audit

Recorded so they are not re-quoted. All are `unpinned` or `unrecoverable` above; this is the index of what changed.

| figure | now | was still unmarked in |
| --- | --- | --- |
| `51 / 4 / 11 / 6` | `unrecoverable` | #33 body, #13 comment 4, **#15 resolution's hazard table**, #33 comment 1 |
| `53 → 167-186`, `164 → 245-285` | `unpinned`, and the retirement **confirmed** below | #11 resolution, #13 comments 3 and 4, #15 comments 2 and 7, #32 body |
| `3.87`, `2.97` | `unpinned` | #13 resolution, #15 comment 4 |
| `13 stable`, `0.0101` | **`unrecoverable`**, by the residual-field re-measurement below | #13 resolution, #15 comments 4 and 7, the map's own index entry |
| `6 of 9` | `unpinned` | #11 resolution, **#39's own resolution**, the map's #11 entry |
| `1.427 m²` | corrected to `1.4283` | #11 resolution |
| `41.6M` framing | conflict recorded | #32 body vs #33 comment 1 |

## Withdrawn by the residual-field re-measurement

[Which residual-field figures survive re-measurement](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42) closed six figures and registered seven replacements. A withdrawal is recorded **here**, in the one place a later correction can reach it; the immutable comments that quote the originals are superseded and cannot be repaired.

| figure | now | replaced by |
| --- | --- | --- |
| median atom `5/9` and `5/7`, fractions `0.57–0.81` | `recorded` under `background-model-v1`, **not withdrawn** | `0.7525` and `0.4792`, the second **not an atom**. Already registered by [#39](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39); #42 confirms closure and adds that "5 of 7 points" has no counterpart under the pinned ladder, which has three scales |
| MAD-zero file list, `2 of 9` | superseded by `1 of 9`, `recorded` | #39's census. The `2 of 9` came from the four-scale ladder `{3,5,9,15}`, not from a second export under the pinned one |
| component counts and their bound witnesses | the **bounds stay `exempt (definitional)`**; the corpus ceiling is `recorded` and **inadmissible as a per-polarity witness** | a cross-polarity total, which #32 decision 2 forbids shipping |
| `53 → 167-186`, `164 → 245-285` | `unpinned`, retirement **confirmed** | a node-count multiset that saturates at the measured cell count on 9 of 9 |
| top-8 lifetimes `~0.5%` | **`unrecoverable`** | `0.005270` to `0.149736`, one declared protocol |
| top-lifespan ÷ residual sd `0.00–0.06` | **`unrecoverable`** | four readings over sixteen declared settings, plus a provable floor that excludes the band |
| `13 stable / 0 drifting / 0 unstable`, worst `0.0101` | **`unrecoverable`** | per-pair maxima `0.001137` to `0.055107` over 18 pairs, and `not-guaranteed` on 18 of 18 |

## Known limits of this file

Stated here rather than discovered later.

- **Enforcement is procedural, not mechanical.** A lint cannot work: a literal search for `53 -> 167-186` misses the body of [Magnitude-instability](https://github.com/abdoupk/groundscan-analyzer-v2/issues/32) entirely, because it writes `→` and en-dashes, and that class of miss is not fixable by trying harder. Nor can the existing quote sites be retrofitted, because most are immutable comments. What *can* be checked by reading: this file is the only place a figure's standing is written, and the specification cites entries here rather than restating figures.
- **A gate that can be evaded by typing an en-dash is worse than an honest rule**, because it reads as enforcement while enforcing nothing. Hence no lint.
- **Unmarked figures in immutable comments cannot be repaired**, only superseded. That is why the withdrawn tuple is quoted in this file with its standing attached: a reader who reaches the old comment finds the number, and a reader who reaches this file finds out not to use it. The first reader is not protected, and no mechanism available here can protect them.
- **The residual-field subset is now here.** It was tracked in [Which residual-field figures survive re-measurement](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42) and that ticket has closed, so the figures live in this file. One consequence is worth stating plainly: closing it produced a **protocol of record and a level rule of record** that did not exist before, and both are declared in the re-measurement section. Every later stability figure cites one of them rather than choosing its own.
- **A reproduction is not always a reproduction.** Re-measuring under `background-model-v1` reproduced the residual-field and scale censuses exactly, and reproduced the hierarchy's **population** and **level-composition** columns exactly too — but **not** the hierarchy's node count, which sits in the same tables as the columns that do reproduce. So a table can be seven columns traceable and one not, and "the same ticket measured it" is not a construction. The node-count entry above is left `unpinned` rather than replaced by a number of my own, because three readings of "node" give three numbers and I cannot show which produced the recorded one.
- **A per-export figure must be labelled by export, and this file got that wrong first.** The re-measurement's three per-export columns were written as bare sequences in the order the run produced them, which was **not** sorted-filename order — so the figures were unattributable to an export until re-derived, and one sequence was ordered differently from its neighbour. Nine bare triples look like a table and are not one. It is now labelled, and the general rule is the obvious one that was nonetheless missed: **a figure about "the corpus" is nine figures**, and a sequence is not a table.
- **Two readings of one concept, both measured, one wrong.** The level-composition columns reproduce **only** when a level is read as a **(polarity, magnitude)** pair and simultaneous entry is counted within one polarity. Grouped across polarities, the same computation reproduces **none** of the three columns. That is not a tuning knob but a definitional fact, and it was settled by the glossary correction rather than by the numbers — the numbers only ever had one answer. Recorded because the wrong reading produced a confident mismatch, and a confident mismatch is indistinguishable from a real defect until the definition is pinned.
- **One column was read wrongly before it was read right, and the wrong reading is the instructive one.** `Royal Tomb`'s largest per-level component count was first read as a component *size* and appeared to breach a provable upper bound on four of nine exports. It is a *count*, and specifically a **cross-polarity total** — which is a different defect, not the absence of one. Recorded because the failure mode is the general one: a corpus column whose name admits two readings can be made to look refuted, and a confident refutation is worse than an unmatched figure.
- **Nothing here may be described as field-validated.** The corpus is vendor educational material with `independent_field_ground_truth: false`, and every entry above is a fact about **nine vendor exports**, never about ground. No entry in this file supports a statement about what is buried.
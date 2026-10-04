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
| `Gallery and Tunnel` **53 → 167-186**, `Royal Tomb` **164 → 245-285** | node count before → range across perturbation trials | perturbation protocol, background, connectivity, level, lattice | `unpinned` | Withdrawn by [The order-dependence inventory](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15). Unmarked in its resolution and in two others. |
| top-8 lifetimes move **~0.5% median** | hierarchy stability under perturbation | as above | `unpinned` | Magnitude recorded (`1%`); kind, reference, seed and trial count were not. |
| `Anomaly at the Edge` **24 → 32**, `Royal Tomb` **164 → 201** | node count under 4- vs 8-connectivity | connectivity (**recorded**), background, level | `unpinned` | Connectivity is the one axis this figure carries. |
| top-lifespan ÷ residual sd falls between **0.00 and 0.06** | level comparability across scans | scale estimator, background, lattice, level | `unpinned` | The non-transferability conclusion does **not** rest on this figure — it rests on the tree and the residual scale being per scan. |
| `min_size = 3` spans **33×**: **0.043 m²** to **1.427 m²** | physical area of a 3-cell floor across pitches | — | exempt (arithmetic on operator-asserted pitch) | **Correction: `1.427` is wrong.** `3 × 0.690² = 1.4283`. The ratio is `33.06×`, so `33×` stands. |
| `min ImpulseX = 1`, `min ScanLineY = 1` in all nine | index origin | — | exempt (raw column) | Normative via [The input contract](https://github.com/abdoupk/groundscan-analyzer-v2/issues/23). |
| six of nine exports are **100% integral** | value integrality | — | exempt (raw column) | Re-confirmed under the pinned ladder. |
| `Gallery and Tunnel` median 176, range 163-177, **MAD exactly 0.000** | raw `Scan Value` statistics | — | exempt (raw column) | **Not** #31's residual-field MAD. Do not conflate the two. |
| one contaminated cell among 200 inflating scale by **three orders of magnitude** | legacy's documented scale failure | — | exempt (legacy quotation) | Legacy's own documented failure, not a v2 measurement. |
| excursion rate **4.9×** nominal; **0.5-1.1×**; **zero** components survive a 3-cell cut from 16×16 to 128×128 | false-positive rate on white noise | — | exempt (synthetic) | Not corpus. |

### [Characterisation: what a detection is made of](https://github.com/abdoupk/groundscan-analyzer-v2/issues/13)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| dominance **13 stable / 0 drifting / 0 unstable**, worst **0.0101** | stability of the peak-magnitude ratio | perturbation protocol, level, connectivity, background, scale | `unpinned` | Marked stale in `CONTEXT.md`. |
| `Tunnel - Original` **3.87**, `Tunnel - Control` **2.97** | robust scale of the one repeat pair | scale estimator, background, quantile, lattice | `unpinned` | **This refutes the hint that opened this audit.** It was floated as a candidate for admission precisely because a dispersion scalar is less sensitive than a count. It has no recorded settings and no sweep, so it is `unpinned` like everything else. Sensitivity was never the test; **traceability** is. |
| **0 of 1** match at 2 sd, **1 of 2** at 3 sd | recurrence on the only real pair | the sd's estimator and convention, correspondence rule, cell tolerance, relative orientation | `unpinned` | The tolerance is stated in sd units; nothing behind that sd is stated. |
| component count drifts **0-8** at a fixed level | count spread across trials | perturbation protocol, level, connectivity, background, scale | `unpinned` | |
| solidity / compactness **exact per-component, matched by position, in every file, all trials** | ratio stability under perturbation | perturbation protocol, level, connectivity, background | `unpinned` | Trial count and seed not recorded. |
| compactness **0.5890** vs **0.6702** | ring vs notched pair | connectivity, level, lattice | `unpinned` | The source cells are not identified in the ticket. |
| `Tunnel - Original` **1** distinct fractional part, `Tunnel - Control` **106** | value integrality | — | exempt (raw column) | |

### [The order-dependence inventory and its tie rules](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15)

| figure | measures | settings needed | standing | note |
| --- | --- | --- | --- | --- |
| `Royal Tomb` **51 / 4 / 11 / 6** at 1/2/3/4 sd | component count at four levels | background, scale, connectivity, level, lattice | **`unrecoverable`** | **Zero of 2,260 settings**, untuned, across a declared sweep (background window per axis, edge/detrending mode, connectivity, scale estimator, sigma source). No interval exists. Retired. |
| **`51`** at 1 sd, in **59 of 2,260** settings | one component of the retired tuple | as above | `unpinned` | The sweep exists and is declared, but no spread was computed and no per-setting record was kept — so there is no interval to quote. **Cheap to close**: #42 can compute it. |
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
| precedence census **0 / 0 / 5 / 38** | which scale-status state fired | background, scale, quantile, lattice | `unpinned` | This is #39's "MAD-zero file list", declared stale there. |
| `Gallery and Tunnel` atom fractions **0.8063 / 0.7550 / 0.6587 / 0.6450** at windows 3/5/9/15; `Royal Tomb` window 3 at **0.5708** | median-atom fraction per window | background, lattice | `unpinned` | Superseded — see the `background-model-v1` census below. |
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
| `Royal Tomb` **53 → 167-186**, second file **164 → 245-285** (body, `→` and en-dashes) | node count under perturbation | perturbation protocol, background, connectivity, level | `unpinned` | **Attribution conflict, retired rather than resolved.** #11 and two others attribute these to `Gallery and Tunnel` / `Royal Tomb`; this body swaps them. The figure is unpinned under an unpinned background either way, so the standing does not depend on which export produced it — and a sweep cannot recover it, because the pipeline that made it is gone. Measured effort here would answer a question the rule has already answered. |
| **4 → `ceil(L·W/2)`**, **8 → `ceil(L/2)·ceil(W/2)`** | maximum component count per connectivity | — | exempt (definitional) | Proved as the independence number of the connectivity graph, verified over 632,084 pairs. A **theorem**, so it needs no corpus. |
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
| disagreement sizes `d/σ` of **0.500**, 0.169, 0.130, 0.069, 0.034, 0.016 | how far apart the two estimates are | as above | `recorded` | Smallest real `d` is **0.0304**, against a derived tolerance band of `4.44e-16` … `9.43e-16` — fifteen orders of magnitude clear, so none is a near-tie. |
| `IQR / MAD` of **1.0** (`Royal Tomb`) and **2.0** (`Error Signal`, `Tunnel - Original Scan`) | why the estimates differ, or coincide | as above | `recorded` | `2.0` makes the two σ-estimates bit-identical, so both "agreements" are an **exact float identity on an integral export** — a lattice artefact, not a fact about the estimators. `1.0` makes the IQR estimate *exactly half* the MAD estimate, hence the 50% disagreement. |
| `tie-tolerance-saturated` reached on **0 of 9** | whether the derived saturation state ever fires | as above | `recorded` | Registered by [#34](https://github.com/abdoupk/groundscan-analyzer-v2/issues/34) and **unreached**. Recorded so it is not mistaken for something observed. |
| `σ(MAD) × Z₇₅ − MAD` = `0.0` on seven exports, **2.22e-16** on `Iron Box`, **3.55e-15** on `Iron Treasure` | whether σ inverts exactly | as above | `recorded` | σ is **not** an exact inverse of MAD on two files in nine. Nothing in the record depends on recovering MAD from σ, so this is a fact rather than a defect — recorded because the assumption would be wrong if made. |

## Withdrawn by this audit

Recorded so they are not re-quoted. All are `unpinned` or `unrecoverable` above; this is the index of what changed.

| figure | now | was still unmarked in |
| --- | --- | --- |
| `51 / 4 / 11 / 6` | `unrecoverable` | #33 body, #13 comment 4, **#15 resolution's hazard table**, #33 comment 1 |
| `53 → 167-186`, `164 → 245-285` | `unpinned` | #11 resolution, #13 comments 3 and 4, #15 comments 2 and 7, #32 body |
| `3.87`, `2.97` | `unpinned` | #13 resolution, #15 comment 4 |
| `13 stable`, `0.0101` | `unpinned` | #13 resolution, #15 comments 4 and 7, the map's own index entry |
| `6 of 9` | `unpinned` | #11 resolution, **#39's own resolution**, the map's #11 entry |
| `1.427 m²` | corrected to `1.4283` | #11 resolution |
| `41.6M` framing | conflict recorded | #32 body vs #33 comment 1 |

## Known limits of this file

Stated here rather than discovered later.

- **Enforcement is procedural, not mechanical.** A lint cannot work: a literal search for `53 -> 167-186` misses the body of [Magnitude-instability](https://github.com/abdoupk/groundscan-analyzer-v2/issues/32) entirely, because it writes `→` and en-dashes, and that class of miss is not fixable by trying harder. Nor can the existing quote sites be retrofitted, because most are immutable comments. What *can* be checked by reading: this file is the only place a figure's standing is written, and the specification cites entries here rather than restating figures.
- **A gate that can be evaded by typing an en-dash is worse than an honest rule**, because it reads as enforcement while enforcing nothing. Hence no lint.
- **Unmarked figures in immutable comments cannot be repaired**, only superseded. That is why the withdrawn tuple is quoted in this file with its standing attached: a reader who reaches the old comment finds the number, and a reader who reaches this file finds out not to use it. The first reader is not protected, and no mechanism available here can protect them.
- **The residual-field subset is not here.** The figures that need re-measurement under `background-model-v1` are tracked in [Which residual-field figures survive re-measurement](https://github.com/abdoupk/groundscan-analyzer-v2/issues/42).
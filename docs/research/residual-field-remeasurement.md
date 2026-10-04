# R4 — Which residual-field figures survive re-measurement under `background-model-v1`

**Ticket:** #42 in `abdoupk/groundscan-analyzer-v2` ("Which residual-field figures survive re-measurement under background-model-v1").
**Author:** research subagent.
**Date:** 2026-10-04.
**Register:** every figure below is registered in `docs/measurements.md` and **cited by entry there, never restated as authority**. This file carries the method and the reasoning; the register carries the number and its standing.
**Status of ground truth:** none, and nothing here may be described as field-validated. The corpus is nine vendor *educational* exports whose own manifest declares `independent_field_ground_truth: false`.

---

## 1. What was asked, and what turned out to be true about it

The ticket asked which of six residual-field-dependent figures survive re-measurement under [`background-model-v1`](https://github.com/abdoupk/groundscan-analyzer-v2/issues/39), each either **re-measured** or **withdrawn** with the withdrawal recorded.

Two of the six were already closed by later tickets and needed confirmation rather than measurement. Two needed a definitional re-establishment rather than a number. Two genuinely needed measuring. And one figure nobody had flagged turned out to need a new entry, because a whole table of `background-model-v1` measurements was sitting unregistered in an immutable comment.

The load-bearing result of the session is not any single figure. It is that **the pinned residual field reproduces exactly** — every value in two recorded censuses, all nine per-export values, all eighteen polarity counts, all nine `IQR/MAD` ratios, both invertibility exceptions — and that **the hierarchy built on top of it does not fully reproduce the hierarchy tables that claim to be built on it**. That split is the finding.

| # | Figure | Verdict | Standing now |
| --- | --- | --- | --- |
| 1 | median atom `5/9`, `5/7`, fractions `0.57–0.81` | **re-measured** (already, by #39) | `recorded` — `0.7525` and `0.4792`, the second **not an atom** |
| 2 | MAD-zero file list, `2 of 9` | **superseded, not withdrawn** | `recorded` — **1 of 9**; the `2 of 9` came from the four-scale ladder |
| 3 | component counts and their bound witnesses | **bounds re-established**; corpus ceiling re-read | bounds `exempt (definitional)`; the ceiling column is `recorded` and **inadmissible as a per-polarity witness** |
| 4 | hierarchy stability: `~0.5%`; `53 → 167-186`; `164 → 245-285` | **withdrawn**, with declared replacements | `~0.5%` → `unrecoverable`; the node-count pair stays `unpinned`, retirement confirmed |
| 5 | top-lifespan ÷ residual sd, `0.00–0.06` | **withdrawn** — the band is *unreachable*, not merely unmatched | `unrecoverable`; replaced by four readings over sixteen declared settings |
| 6 | dominance `13 stable / 0 drifting / 0 unstable`, worst `0.0101` | **withdrawn**, with a declared replacement | `unrecoverable`; replaced by per-pair maxima `0.001137`–`0.055107` |

---

## 2. Method

### 2.1 The conventions, and the code for each

Every convention below is implemented from its **transcription**, never delegated to a library. `np.quantile` and `np.percentile` are not called anywhere in the harness — [#36](https://github.com/abdoupk/groundscan-analyzer-v2/issues/36) §5 records that NumPy's `_lerp` is not the contract's arithmetic, differing in `440` of `602,400` dyadic cases.

**`quantile-v1` — H&F type 2 in the contract's floor form** (#36 §5). No endpoint blending; the endpoints are clipped *to the sample*, which #36 records as load-bearing, and the scale never evaluates `p = 0` or `p = 1`.

```python
def q2(xs_sorted, p):
    """quantile-v1: H&F type 2, contract floor form. xs_sorted ascending."""
    n = xs_sorted.size
    if p <= 0.0: return float(xs_sorted[0])
    if p >= 1.0: return float(xs_sorted[n - 1])
    h = n * p
    j = math.floor(h)
    g = h - j
    if g != 0.0:
        return float(xs_sorted[j])                      # gamma == 1: selects x_(j+1)
    if j == 0:
        return float(xs_sorted[0])
    # #34 s5 averaging arithmetic, that operand order, rounded once.
    return 0.5 * float(xs_sorted[j - 1]) + 0.5 * float(xs_sorted[j])
```

The last line is deliberately **not** `0.5 * (lo + hi)`. #39 records the operand order as part of the convention; #36 §5 records that the contract's form equals `fl((lo+hi)/2)` in `440/440`, so either is arithmetically defensible and only this one is the contract.

**`background-model-v1`** (#39): windows `{3, 5, 9}` = Chebyshev radii `{1, 2, 4}`; centred; clipped to the lattice; the median over **measured cells only**; combined by the **median across the three scales**. The odd count is load-bearing, and the harness makes that structural rather than incidental:

```python
WINDOWS, RADII = (3, 5, 9), (1, 2, 4)

for k, (w, r) in enumerate(zip(WINDOWS, RADII)):
    for i, j in measured_cells:                       # centred square, intersected
        i0, i1 = max(0, i - r), min(n_lines, i + r + 1)      # with the lattice —
        j0, j1 = max(0, j - r), min(n_cols, j + r + 1)      # never a fill
        block = values[i0:i1, j0:j1][mask[i0:i1, j0:j1]]     # measured cells only
        per_scale[k][i, j] = median_of(np.sort(block))

bg = np.sort(per_scale, axis=0)[1]   # median ACROSS three scales: an order
residual = values[mask] - bg[mask]   # statistic, so no averaging rule at all
```

`np.sort(...)[1]` rather than `np.median(...)` so that the "order statistic, not an average" property is visible at the point of use rather than asserted in prose. No trend term: the largest window *is* the low-frequency removal.

**Robust scale** (#31): MAD and IQR on one σ target, both factors derived from the one constant.

```python
Z75 = 0.6744897501960817            # Phi^-1(0.75); asserted equal to norm.ppf(0.75)
med = median_of(sort(R))                       # centring median, quantile-v1
mad = median_of(sort(abs(R - med)))            # MAD's inner median, same convention
iqr = q2(sort(R), 0.75) - q2(sort(R), 0.25)
a, b = mad / Z75, iqr / (2.0 * Z75)            # sigma(MAD), sigma(IQR)
```

**The pinned constant was used, not the census's rounded one.** `1/Z₇₅ = 1.482602218505602`; the recorded `background-model-v1` census used `1.4826`. The harness asserts `Z75 == norm.ppf(0.75)` and derives `1/Z75`. The `1.5e-6` relative discrepancy the register already records changed no determination here, and `MAD == 0.0` on `Gallery and Tunnel` under either.

**`scale_status`** (#31 precedence, #34's `C₀`/`c₁`/`K`, #37's names): `no-finite-residual-values → constant-field → median-atom → tie-tolerance-saturated → exact-agreement | disagreement`, with `C₀ = 4` odd / `5` even, `c₁` by `n mod 4`, `K = 11`, `u = 2⁻⁵³`, `L = max(|m̃|, |Q₂₅|, |Q₇₅|)`, `s = max(a, b)`.

**Reading the exports**: by the section grammar (`+++ Measuring Values +++`), then by **column name**, never position (#23) — `Impulse X`, `Scan Line Y`, `Scan Value`, matched after trimming and case-insensitively, with the unit part of the name. The lattice is built from **observed** coordinates, so no declared count creates a cell (#39).

### 2.2 The declared perturbation protocol of record

**No protocol survived.** #11 recorded the magnitude (`1%`) and nothing else; #13 and #15 inherited the same undeclared "1% noise". A figure with an undeclared protocol is `unpinned`, so the protocol had to be chosen. It is chosen here, fully, and **becomes the declared protocol of record** — this ticket is its author.

| Axis | Value |
| --- | --- |
| **kind** | additive, independent per measured cell, zero-mean, **uniform on `[-1, 1]`** |
| **magnitude** | `1%` |
| **reference quantity** | the residual field's population standard deviation (`ddof=0`) over measured cells, computed once from the unperturbed field and held fixed |
| **seed** | `numpy.random.default_rng(20261004 + scan_index)`, `scan_index` the 0-based position in sorted-filename order; one generator per scan |
| **trial count** | `20` per scan, unperturbed field as baseline |

Three choices are argued rather than made.

**Uniform, not Gaussian, because boundedness is what buys a decided answer.** #33's mask-invariance guard is defined only for a bounded protocol; `CONTEXT.md`'s **Mask-invariance** entry says an unbounded one "leaves every field unguaranteed". Choosing a bounded protocol means every figure below can be accompanied by the guard's verdict, which distinguishes *decided* from *measured*. It does not, on this corpus — see §5.2 — and that is itself worth having known.

**The reference quantity is the plain sd, not `σ(MAD)`, because `σ(MAD)` is exactly zero on one export.** #11 wrote "1%" without saying 1% *of what*, and the corpus does not permit the robust scale as the denominator: `Gallery and Tunnel` has `MAD == 0.0` exactly, so any fraction of `σ(MAD)` is a zero-amplitude protocol on a quarter of the corpus. Stated as a reason; it is not a threshold, and no acceptability judgement is involved.

**The level is held fixed in absolute residual units across trials**, per #32 decision 4 — the question is the perturbation's effect on the thresholded set at a fixed level, not the effect of re-deriving the level per trial.

### 2.3 The declared level rule of record

A level is a named axis, and no transferable default exists (#11, `CONTEXT.md` **Level**), so a rule had to be declared rather than inherited:

> **The polarity's own median residual magnitude** — the level at which half of that polarity's cells are inside the cut and half are outside.

It is per scan, per polarity; it depends on no count, no connectivity and no other declared figure; and it therefore cannot be tuned toward a stability verdict. It is used for dominance and for the per-level component counts. For the hierarchy-wide figures the level set is *every* level of the emitted hierarchy, named as such.

### 2.4 Reproducibility

The harness lives outside the tracked tree, at `C:\Users\abdou\AppData\Local\Temp\opencode\issue42\`:

| File | Role |
| --- | --- |
| `remeasure.py` | the conventions above, verbatim as quoted |
| `validate.py` | the reproduction check against every recorded census |
| `bounds_check.py` | the upper-bound check on the ceiling column |
| `measure.py` | the two measurements and the declared replacements |
| `results.json` | every per-trial value, machine-readable |

Run with `uv run --frozen python <file>` from the repository root. Environment: `python 3.13.15`, `numpy 2.5.3`, `scipy 1.18.1`, `Windows-11-10.0.26200-SP0` — **identical to the register's recorded fingerprint**, so nothing was added to it.

---

## 3. Validation against the recorded census

This is the load-bearing check, because every figure below is worthless if the implementation is wrong. **The recorded censuses reproduce exactly.**

| Recorded figure | Source | Reproduced |
| --- | --- | --- |
| median-atom fractions **0.7525** (`Gallery and Tunnel`) and **0.4792** (`Royal Tomb`) | #39 census | **exact, both** |
| median-of-3 = B₅ on **80.8%** | #39 | **exact**, and all nine per-file values (`0.5705` … `0.9819`) |
| unusable-scale state on **1 of 9** | #39, #37 | **exact** |
| state census **1 / 2 / 6 / 0 / 0** | #37 | **exact** |
| per-export `σ(MAD)` — `240.18`, `1.4826`, `0.0000`, `2.5019`, `43.7367`, `1.4826`, `1.4826`, `1.9054`, `2.9652` | #39 | **exact to the recorded precision, all nine** — **SUPERSEDED DUPLICATE, [#55](https://github.com/abdoupk/groundscan-analyzer-v2/issues/55):** a bare sequence in the order the run produced it, which is **not** sorted-filename order, so unattributable to an export. The labelled figures are in `docs/measurements.md`; see its rule that a figure about "the corpus" is nine figures. **This is `σ(MAD)`, not the residual population sd**, so it cannot serve as the amplitude reference and was not used as one. Attribution and correction are [#56](https://github.com/abdoupk/groundscan-analyzer-v2/issues/56)'s; do not write a fourth copy. |
| polarity counts `R>0`/`R<0`, all eighteen | #39 | **exact, all eighteen** |
| extreme residuals `max R+`, `max abs R−`, all eighteen | #39 | **exact, all eighteen** |
| `IQR/MAD` — `1.0`, `2.339`, `2.259`, `2.139`, `1.932`, `2.032`, `2.0`, `2.0` | #37 | **exact, all eight** — **and eight is the right count, [#55](https://github.com/abdoupk/groundscan-analyzer-v2/issues/55).** This was read as eight values for nine exports, i.e. as a defect. It is not: `Gallery and Tunnel` has **`MAD = 0` and `IQR = 0`**, so its ratio is **`0/0` and undefined**, and all eight quoted values reproduce exactly. The defect was only that the note did not say which export was absent or why, and a **non-finite value is unrepresentable in v2**, so the register states it as an undefined quantity and quotes no number. **`docs/measurements.md`'s implementation-validation entry had claimed "all nine" and was wrong on exactly this one export** — the one carrying the corpus's only `median-atom`, so the slip sat on the most load-bearing field in the file; corrected there. **SUPERSEDED DUPLICATE**: the labelled ratios are in `docs/measurements.md`, whose `IQR / MAD` entry already quoted only the defined values — which is why the two disagreed. Attribution is [#56](https://github.com/abdoupk/groundscan-analyzer-v2/issues/56)'s; do not write a fourth copy. |
| `σ(MAD)·Z₇₅ − MAD` = `2.22e-16` (`Iron Box`), `3.55e-15` (`Iron Treasure`), `0.0` elsewhere | #37 | **exact, all nine** |
| #40's level-structure columns — distinct magnitudes, simultaneous-entry levels, cells in simultaneous entry, largest single group | #40 | **exact, all nine × four** — see §6.1 |
| #40's population columns — measured cells, residual-exactly-zero, cells entering the hierarchy | #40 | **exact, all nine × three** |

**One recorded detail is worth keeping, because reading it the other way does not reproduce.** The corpus `80.8%` is the **per-export mean** of the nine fractions (`7.2734 / 9 = 0.808139`), not a cell-weighted mean, which is `0.9028`. Both are defensible readings of "across the corpus"; only the per-export one is the recorded figure, and the register does not say which it is. **The register should say so.**

**A note on #37's disagreement column.** #37 tabulates `d` and `d/σ`, and its `d/σ` values are `|σ(MAD) − σ(IQR)| / σ(MAD)` — whereas the pinned `d` in #31 and #34 is `|a − b| / max(a, b)`. Both normalisations reproduce their own column exactly (e.g. `Royal Tomb`: `0.7413 / 1.4826 = 0.500`), so the ticket is internally consistent and nothing is wrong with it. But **the two columns do not carry the same quantity**, and a reader comparing #37's `d/σ` against a pinned `d` will find a discrepancy that looks like an error. Worth a footnote in the register.

**Correction, [#46](https://github.com/abdoupk/groundscan-analyzer-v2/issues/46):** this note originally put the discrepancy at "a factor of two". **Measured, it is at most `1.17×`** (`Pipeline`, `0.169` against `0.145`). The two coincide *exactly* wherever `σ(MAD) ≥ σ(IQR)` — 3 of the 6 — and the ratio elsewhere is bounded by the ratio of the two estimates, which cannot exceed `1.17` on this corpus. An inflated warning is worse than none: it is the number a reader remembers instead of the correction. The reconciliation this note asked for is now made: the pinned form is **of record**, the `σ(MAD)` form is a reporting column, and the absolute difference is struck.

---

## 4. Figure 5 — top-lifespan ÷ residual sd: withdrawn, and provably so

**#11 recorded** "top-lifespan divided by residual sd falls between 0.00 and 0.06 across the corpus." **Verdict: withdrawn, `unrecoverable`.**

Two independent grounds, and the second is the stronger one.

**The band is not reproduced under any reading of "top".** #11 does not say what "top" selects. Four readings were declared and measured, over both connectivities and both denominators — sixteen settings:

| Reading of "top" | ÷ residual sd | ÷ `σ(MAD)` |
| --- | --- | --- |
| max lifespan over all nodes | 1.580 – 15.500 | 2.023 – 66.774 (1 of 9 undefined) |
| median of the eight longest-lived | 0.279 – 7.684 | 0.843 – 5.396 (1 of 9 undefined) |
| max among the eight largest-by-area | 0.017 – 2.260 | 0.043 – 2.361 (1 of 9 undefined) |
| max excluding nodes born at the lowest level | 1.580 – 15.500 | 2.023 – 66.774 (1 of 9 undefined) |

Only the third reading has a minimum inside the old band, and its maximum is **38× the band's upper edge**. The first and fourth are *uninformative as measurements*: the longest-lived node spans nearly the whole magnitude range, so that reading restates the residual spread rather than measuring a property of a detection. The fourth equalling the first is itself a finding — a component whose cell set is unchanged while other components are born and die around it persists for many levels, so excluding "roots" removes nothing.

**The band is unreachable, not merely unmatched.** A node cannot be born and die between two levels closer together than the smallest gap between consecutive distinct residual magnitudes of its polarity. That gives a *provable floor* on every node's lifespan, and on **3 of 9** exports the floor alone already exceeds `0.06`:

| Denominator | Exports whose provable floor exceeds `0.06` |
| --- | --- |
| residual sd | `Gallery and Tunnel`, `Royal Tomb`, `Tunnel - Original Scan` |
| `σ(MAD)` | `Error Signal`, `Royal Tomb`, `Tunnel - Original Scan` |

`Royal Tomb` is the clearest case: its residual magnitudes are half-integer spaced, so **no node on that export can have a lifespan below `0.34 σ`**. There is no level grid, connectivity or reading of "top" that puts a lifespan inside `0.00–0.06` there. The band was wrong, not merely unmatched — which is a different and stronger statement than "we could not reproduce it".

**A third, smaller reason:** the denominator. `Gallery and Tunnel` has `σ(MAD)` exactly `0.0`, so under the scale reading the quotient is **undefined on 1 of 9** — the same `not-emitted: scale-not-positive-finite` condition #37 registered for the normalised view.

**What the conclusion does not rest on.** `CONTEXT.md`'s **Level** entry already says the non-transferability of a level "rests on the tree and the residual scale being per scan rather than on that figure". The withdrawal changes no decision: the tree is per scan, the residual field is per scan, so a level chosen on one scan has no meaning on another regardless of this number. The register's note on the entry already said this and it is now load-bearing rather than precautionary.

**What replaces it** is registered, and it says something the old figure could not: top-lifespans are **large** fractions of the residual spread, not small ones. That strengthens the case for per-scan levels rather than weakening it.

---

## 5. Figure 6 — dominance: withdrawn, replaced by a declared measurement

**#13 recorded** "13 stable / 0 drifting / 0 unstable, worst case 0.0101 relative deviation under 1% noise". **Verdict: withdrawn, `unrecoverable`, replaced by a `recorded` entry.**

### 5.1 Why the original cannot be admitted, in two independent ways

**The classification half has no admissible form.** `stable` / `drifting` / `unstable` are three bands. A band is a threshold, and #7's retention rule deletes every number whose only function is to change whether a result is "acceptable, ready, safe, strong or weak"; #28 forbids a fixed constant where a recorded protocol belongs. There is **no threshold anywhere in the register** to recover the three bands from, and inventing one would reintroduce exactly the magic minimum the map deleted. So `13 / 0 / 0` is not reproducible in principle, and its three counts cannot be restated as anything else.

**The magnitude half is unreachable as a worst case.** Under the protocol of record, over **18** (export, polarity) pairs:

| Quantity | Value |
| --- | --- |
| per-pair maximum relative deviation | **0.001137 to 0.055107** (median of the per-pair maxima `0.005510`) |
| corpus worst case | **0.055107** (`Error Signal`, positive polarity, `D₀ = 1.33333`) |
| pairs whose maximum equals `0.0101` | **0 of 18** |
| pairs whose maximum **exceeds** `0.0101` | **3 of 18** |

So `0.0101` is not unreachable as a *value* — it sits inside the corpus interval — but it is unreachable as the **worst case**, which is what the figure claimed. The sweep's worst case is **5.5× larger**.

The three pairs that exceed it are `Error Signal` positive (`0.055107`), `Iron Treasure` negative (`0.015391`) and `Error Signal` negative (`0.014222`). Both extremes are on `Error Signal`, the corpus's smallest lattice at `75` measured cells, where `1%` of the sd is a large perturbation relative to the magnitude spacing — the same reason its provable lifespan floor is the second-highest in the corpus.

### 5.2 The guard, which is the honest ceiling

All **18 of 18** pairs read **`not-guaranteed`** under #33's mask-invariance guard. Not one is decided.

The reason is the one #33 named in advance: the declared level is the polarity's own median residual magnitude, and on an atom-heavy field that level **collapses onto the median atom**, so cells sit exactly at a threshold, the required gap is `0`, and the guard reads `not-guaranteed` with no special case. The measured gaps are negative on every pair — from `-0.0057` to `-5.28` — so the cells nearest the level are closer than the declared amplitude.

**What follows, stated carefully.** Every dominance figure here is **measured and none is decided**. That is not a defect in the measurement; it is the corpus's property, and it is the same property #31 established for the estimators: the atom makes the field's central structure exact, and no bounded perturbation survives an exact structure. `not-guaranteed` does **not** mean unstable.

**And the reason this is worth reporting at all**: the recorded figures supported a *structural* claim — that dominance is a ratio and ratios are stable — and per #30 a measured agreement may support a property's evidence coverage and may **never** justify or strengthen a grade. So this measurement cannot be used to argue that dominance is stable. That argument was never available from the corpus: it rests on dominance being a ratio over a thresholded set. #13's own audit note already said so, and nothing here disturbs it.

### 5.3 What replaces it

The register carries the per-pair maxima and the trial counts, the declared level, the component count at that level (`3` to `132`), and the guard verdict on each pair. Existence was never withheld: all 18 pairs admit a level with ≥2 components under the declared rule.

---

## 6. Figures 3 and 4 — component counts, bounds, hierarchy stability

### 6.1 The bounds stand; the corpus witness beside them does not

The definitional bounds are `exempt (definitional)` and **untouched**, and this was worth establishing rather than assuming. `ceil(L·W/2)` under 4-connectivity and `ceil(L/2)·ceil(W/2)` under 8 are the independence number of the connectivity graph: they are functions of the lattice's two dimensions and the connectivity, and **no residual field and no corpus count bears on them**. #34's oracle is independent here by construction rather than by second implementation, since nothing computes the quantity twice — which is the stronger position #34 argued for. A corpus count moving cannot touch a theorem, and #32's payoff — *the ceiling survives the perturbation the count does not* — is unaffected.

**The corpus column beside the bounds is a different matter.** #32's closing amendment and #40 both carry a "largest component at any level" figure per connectivity. Read first as a component **size**, it appeared to breach a provable upper bound on four of nine exports — a component at level `t` is a subset of the polarity's whole cell set, so the largest connected component at the *coarsest* level bounds every finer one, and four recorded figures sat above it.

**That reading was wrong, and the right one is a worse defect.** The column is a component **count**, and specifically the **cross-polarity total** — the maximum over levels of the positive count *plus* the negative count. Under that reading, six of nine reproduce exactly on 4-connectivity (`257`, `144`, `21`, `31`, `19`, `24`) and three of four on 8-connectivity (`233`, `111`, `49`); `Anomaly at the Edge` is `32` against `33`, `Pipeline` `59` against `60`, `Tunnel - Control Scan` `20` against `23`, and the two 8-connectivity figures are each one low. Recorded rather than smoothed.

**Why that is a defect.** #32 decision 2 states *"No cross-polarity total is shipped"*, and the amendment presents the table as sharpening a **per-polarity** ceiling. The table is therefore not admissible evidence for the per-polarity bound it is offered as witnessing — not because the arithmetic is wrong, but because the quantity is one the map has ruled inadmissible. The bound is unaffected; the witness is. This is registered as `recorded` **and** flagged inadmissible, because the figure is real and a reader must not be able to cite it as a per-polarity bound.

*This is also the session's one instructive error, recorded in the register's Known limits: a corpus column whose name admits two readings can be made to look refuted, and a confident refutation is worse than an unmatched figure.*

### 6.2 The hierarchy tables are half traceable, which is the finding

#40's tables are the ticket's first `background-model-v1` hierarchy measurements, and they were **unregistered** — corpus figures in an immutable comment, therefore unquotable under #38. Registering them was part of this ticket's work. The result splits:

| #40 column | Reproduces? | Standing |
| --- | --- | --- |
| measured cells / residual-exactly-zero / entering the hierarchy | **exact, 9 × 3** | `recorded` |
| distinct residual magnitudes | **exact, 9**, **only under the per-polarity reading** | `recorded` |
| levels with simultaneous entry | **exact, 9** | `recorded` |
| cells in simultaneous entry | **exact, 9** | `recorded` |
| largest single group | **exact, 9** | `recorded` |
| detection (node) count | **no** | `unpinned` |
| "largest component at any level" | only as a **cross-polarity total** | `recorded`, flagged inadmissible |

**The per-polarity level set is a real correction to the glossary.** `CONTEXT.md`'s **Component hierarchy** entry says the tree is built "per polarity … with **one level per distinct residual magnitude**". Reading that as a union of magnitudes across both polarities gives `16` levels for `Royal Tomb`; reading it per polarity gives `29`, which is what #40 recorded. **A magnitude occurring in both polarities is two levels, not one.** The glossary sentence is ambiguous rather than wrong, and it should be tightened — this is a live ambiguity in the domain model, not a measurement nicety.

**The node count is left `unpinned` rather than replaced, deliberately.** It does not reproduce: `Royal Tomb` is `435` under both readings I could construct — the sum over levels of the component count, and the number of distinct cell-set nodes — against `1,509` recorded, and the other eight are off by factors of `1.5` to `11`. I could have registered my own number, and did not, for two reasons. I cannot show *which* reading produced the ticket's, so I cannot claim mine is the correction rather than a fourth reading; and the two columns that do reproduce come from the **same table**, so the table cannot have been produced by one implementation. The honest entry is "does not reproduce, construction never stated". The bound `nodes ≤ 2n − 1` is untouched either way, and #40's own ratio claim (`Royal Tomb` at `0.60` of the bound) is arithmetically consistent with `1,509 / 2,499`.

### 6.3 Figure 4 — hierarchy stability, withdrawn with declared replacements

**`~0.5%` median top-8 lifetime movement → `unrecoverable`.** Declared sweep: the protocol of record, four readings of "top", both connectivities. Replaced by a `recorded` measurement: the **median relative deviation per trial runs `0.005270` to `0.149736`** across the nine exports. The withdrawn magnitude is corroborated at the **low** end — `0.53%` on `Anomaly at the Edge` is within a whisker of `~0.5%` — and exceeded by a factor of **28** on `Error Signal`. A magnitude quoted from a spread spanning two orders of magnitude was never a figure to quote, which is the whole content of the rule this register implements.

**`53 → 167-186`, `164 → 245-285` → retirement confirmed, and a stronger replacement exists.** #38 retired the attribution conflict between #11 and #32 on the grounds that a sweep cannot recover a figure whose pipeline is gone. **That call is right, and #42 confirms it** — but the confirmation is not merely procedural. Under the protocol of record the node count does not drift at all: **the per-trial multiset is the constant measured-cell count on 9 of 9**.

The reason is structural, and it is the strongest form the hazard takes on this corpus. **The median atom is an exact equality, so any perturbation of the residual field destroys it.** The zero-residual cells — `1,150` of `2,400` on `Royal Tomb`, `1,204` of `1,600` on `Gallery and Tunnel` — stop being zero, every measured cell enters the hierarchy, and each becomes its own node. The node count therefore **saturates** rather than spreading: `435 → 2400` on `Royal Tomb`, `177 → 1600` on `Gallery and Tunnel`, on every trial. Nothing may depend on a node count as a stable quantity, and here the reason is a property of the corpus's exact arithmetic rather than a statistical observation about noise.

**The per-level component counts are reported as multisets**, which is the form #32 decision 4 requires and which the withdrawn `0-8` drift range was not. Six of nine move; three are constant across all twenty trials. And two move in **opposite directions** — `Gallery and Tunnel` `141 → 111-138` falls, `Royal Tomb` `257 → 282-317` rises — which is #33's non-monotone-in-level mechanism appearing in the *perturbation* direction rather than the level direction. That is a genuine structural parallel and is recorded as an observation, never as a claim about any scan.

---

## 7. Figures 1 and 2 — already closed, confirmed precisely

Both needed verification, not measurement, and both verify.

**Figure 1, the median atom.** #39's census records `Gallery and Tunnel` at **0.7525** (past halfway, so `MAD == 0.0` exactly) and `Royal Tomb` at **0.4792**, which is **not an atom**. Both reproduce exactly, and #31's lemma predicts the `MAD` outcome from the atom fraction alone in **9 of 9** cases — the one file above `n/2` is the one file at `σ = 0`, and all eight below are non-zero. So figure 1 is closable, with one addition: **`5 of 7 points` has no counterpart under the pinned ladder**, which has three scales rather than four. The `0.57–0.81` figures were per-window fractions across the four-scale ladder, and `0.5708` in particular was `Royal Tomb` at **window 3 alone** — a single-scale atom that is not an atom of the composed background. `CONTEXT.md`'s parenthetical about them is accurate as history and needs its "pending re-measurement" clause removed, because the re-measurement has now happened and is in the register.

**Figure 2, the MAD-zero file list.** The claimed reachability of **2 of 9** came from the four-scale ladder `{3,5,9,15}`, where two exports had at least one `MAD`-zero field (`Gallery and Tunnel` at all four windows, `Royal Tomb` at window 3). Under the pinned ladder `{3,5,9}` it is reached on **1 of 9**, and that figure is `recorded` in #37's census. So the ticket's note is right, and the reason is worth stating because it is the mechanism rather than a discrepancy: **a ladder that stops at radius 4 has fewer windows in which the atom can dominate**, and #39's rejection of the `15` window for exactly this reason — dropping it forfeits measurable trend removal — is a trade, not a free choice.

---

## 8. Adjudication requested by the register: the `51` at 1 sd in 59 of 2,260 settings

The register's entry says *"**Cheap to close**: #42 can compute it."* **#42 adjudicates this as out of its own scope**, on two grounds, and the second is decisive.

**It is a sweep figure, not a stale figure.** Closing it means re-running the declared sweep with the three now-pinned axes fixed. That is a *new* declared sweep — axes and extent, with a per-setting record kept — and the register's `swept` standing requires exactly that record, which the entry says was never kept. #42 is chartered to re-measure figures computed on a superseded background; a sweep over the axes as they were declared is a different piece of work.

**It is a component of a retired tuple.** `51 / 4 / 11 / 6` is `unrecoverable`: zero of 2,260 settings reproduces it. Promoting `51` — one element of a figure already retired — to evidence would **invert** that retirement rather than complete it. The register's own reasoning gets here: reachability discriminates per figure, and the tuple's retirement is a statement about the tuple.

**What a closing ticket would need:** a declared sweep over the now-pinned axes (background fixed, quantile fixed, scale estimator fixed, connectivity free, level free), with **every per-setting record kept** so that a spread exists, and — the part that makes it a decision rather than bookkeeping — a ruling on whether the four-tuple's retirement extends to its elements or whether `51` is severable. That last question is the actual content, and it is not a measurement question. **A fog patch, not a ticket**, until someone wants the number.

---

## 9. What remains unresolved

1. **#40's node count.** Does not reproduce under any reading constructed, from the same table whose other columns reproduce exactly. Needs a stated construction. **Not closable by measurement** — it needs the original code path, which is gone, or an admission that the figure is retired.
2. **The three ceiling figures that miss by 1 to 3** (`Anomaly at the Edge` `32`/`33`, `Pipeline` `59`/`60`, `Tunnel - Control Scan` `20`/`23`, and two 8-connectivity rows one low). The reading is identified and the near-misses are small, which suggests a slightly different level grid. Worth one focused follow-up; it does not change any decision, since the column is inadmissible as a per-polarity witness either way.
3. **Why a residual-field perturbation must destroy the median atom, and whether a payload perturbation would too.** #33 decision 4 bounds a residual perturbation at `2a` for a window-median model but records that the end-to-end payload equivalence "was not measured". If a payload perturbation also destroys the atom, the node-count saturation is universal rather than a quirk of perturbing the derived field; if it does not, a payload-level protocol is the better choice of record and this ticket's protocol should be revisited. **This is the most consequential open item here**, because it decides whether the protocol of record is the right one.
4. **Whether `d/σ` in #37 and the pinned `d` should be reconciled in the register.** Both reproduce their own column; they are different quantities.

---

## 10. What the map should now do

**Add**

- A ticket for **the node count and the hierarchy's stated construction** — the only remaining unregistered residual-field figure that is quoted as a headline. It blocks nothing and is closable by a ruling rather than by measurement, which is why it should be filed as a decision.
- A **payload-versus-residual perturbation protocol** ticket (§9.3). It decides whether the protocol of record survives contact with a better choice, and the protocol is now load-bearing for every stability figure on the project.
- ~~A ticket to **reconcile `d/σ` with the pinned `d`** in the register, so a future reader does not read a factor of two as an error.~~ **Done — [#46](https://github.com/abdoupk/groundscan-analyzer-v2/issues/46).** The pinned relative form is of record, `d/σ(MAD)` is a reporting column with its denominator named, the absolute difference is struck, and both rows are labelled per export. The "factor of two" was itself wrong: the measured maximum is **1.17×**.

**Change**

- `CONTEXT.md` **Median atom**: remove "pending re-measurement" from the parenthetical. The re-measurement happened and is `recorded`; the `0.57–0.81` figures are history, correctly labelled as such. Add that `5 of 7 points` has no counterpart under a three-scale ladder.
- `CONTEXT.md` **Level**: the `0.00–0.06` figure is `unrecoverable` and its band is *provably* unreachable on 3 of 9 exports. The sentence must not keep it as a measurement. The non-transferability conclusion is unaffected and should say so without the figure.
- `CONTEXT.md` **Dominance**: `13 stable / 0 drifting / 0 unstable` and `0.0101` are `unrecoverable`. The entry's "structurally stable" claim stands **on being a ratio over a thresholded set** and must cite the register, not a corpus table it no longer has. This is the one place where a stale figure is currently doing load-bearing prose work.
- `CONTEXT.md` **Component hierarchy**: "one level per distinct residual magnitude" needs **"per polarity"**, because a magnitude present in both polarities is two levels and the recorded figures depend on it.
- `docs/measurements.md`: record that the corpus `80.8%` is the **per-export** mean, not cell-weighted.

**Remove**

- Nothing. No decision is disturbed by any withdrawal here. Every conclusion that cited a withdrawn figure either already named a non-corpus ground (the level non-transferability on per-scan-ness; the trend-term rejection on the claim boundary; dominance's stability on being a ratio) or is an annotation that no corpus result was ever load-bearing for.

**Already closed, verified not re-opened**

- The median-atom figures and the `1 of 9` unusable-scale state (#39, #37).
- The node-count attribution conflict between #11 and #32 — correctly retired, and #42's stronger result (saturation at the measured cell count) makes the retirement moot rather than merely defensible.
- The definitional bounds — theorems, and no corpus count touches them.

**Contradictions found between tickets**

1. **#32 decision 2 vs #32's own closing table.** "No cross-polarity total is shipped", beside a table that is a cross-polarity total presented as a per-polarity ceiling. Both are in one comment; neither can be repaired, only superseded.
2. **#40's node count vs #40's own level-structure columns.** Reproducible and irreproducible in one table, which means the table was not produced by one implementation.
3. **`CONTEXT.md`'s level definition vs #40's measurements.** The glossary's wording is ambiguous where the measurements are unambiguous.
4. **#37's `d/σ` vs the pinned `d`.** Two normalisations of one comparison, both internally consistent.

**Still quoted as current, where it should not be**

| Site | Figure | Note |
| --- | --- | --- |
| `CONTEXT.md:278` (**Level**) | `0.00–0.06` | editable — needs the withdrawal now |
| `CONTEXT.md:366` (**Dominance**) | `13 stable / 0 drifting / 0 unstable`, `0.0101` | editable — needs the withdrawal now |
| `CONTEXT.md:466` (**Median atom**) | `0.57 to 0.81`, "pending re-measurement" | editable — history clause only |
| `CONTEXT.md:236` (**Component hierarchy**) | "one level per distinct residual magnitude" | editable — needs "per polarity" |
| `docs/wayfinder/groundscan-v2-map.md:63` and `:88`, `groundscan-v2-map-full.md:63` | `13 stable / 0 drifting / 0 unstable`, `0.0101`, `53 → 167-186`, `164 → 245-285` | editable local archive of the map body; `:241` of the full file already marks the dominance figure `unpinned` |
| #11 resolution, #13 comments 3–4, #15 comments 2/4/7, #32 body, #39's own resolution | all six | **immutable GitHub comments. Superseded, not repairable.** The register's index names each site; this file is the only thing a reader arriving at one of them can be sent to |
# R5 — Does anything import `groundscan_research/`, and what does the subtree hold?

**Ticket:** #89 in `abdoupk/groundscan-analyzer-v2` ("Does anything in the engine import groundscan_research/, and what does that subtree hold?").
**Map:** #1, Notes section, the `docs/legacy/` paragraph.
**Author:** research subagent.
**Date:** 2026-10-06.
**Method:** static only. Every `.py` file in the repository was parsed with Python's `ast` module — never imported, never executed, never regex-matched on the raw text. Relative imports were resolved against `docs/legacy` as the import root. No file under `docs/legacy/` was created, modified, or deleted.
**Status of ground truth:** none, and nothing here may be described as field-validated. `docs/legacy/scans/vendor_demo/vendor_ground_truth.json` declares `independent_field_ground_truth: false`, and every module in the subtree carries its own synthetic-only disclaimer.

---

## 1. The premise, and its verdict

The map Notes say, of `docs/legacy/groundscan_research/`:

> 33 diagnostic modules, **never imported by the engine**

Both halves are wrong, and they are wrong in different ways. One is wrong by a small factual
margin; the other is wrong in substance.

### 1.1 "never imported by the engine" — **false as stated**

**One module in the engine imports it**, on exactly one code path:

```
docs/legacy/groundscan/cli/validate.py:77
    from groundscan_research import EXPERIMENTAL_RUNNERS
```

That import is function-local, inside the `experimental` branch of `cmd_validate`
(`cli/validate.py:72`), and it is reached only when `args.validate_command == "experimental"`.
It is not at import time, it is not on any analysis path, and the branch's own banner calls the
outcome non-gating (`cli/validate.py:81-85`: *"non-gating research outcomes — they never authorize
production behavior"*).

**This is a known and deliberate exception in the legacy source, not an oversight.** Legacy's own
boundary test names it and whitelists it:

```
docs/legacy/tests/unit/test_research_boundary.py:27-33
    # - cli/validate.py: function-local `from groundscan_research
    #   import EXPERIMENTAL_RUNNERS` inside the non-gating
    #   `validate experimental` handler (never at import time).
    ...
    if path.name == "validate.py" and "EXPERIMENTAL_RUNNERS" in line:
        continue
```

So the map did not miss a violation — it **dropped the exception the legacy codebase documents
two lines above the code it describes.** The corrected statement is:

> The engine imports the research registry on exactly one CLI path — the explicitly non-gating
> `validate experimental` profile — and nowhere else.

### 1.2 …and the CLI path reaches *all five* facades

`cli/validate.py:99-106` iterates `EXPERIMENTAL_RUNNERS` and `__import__`s each dotted target at
runtime. Resolving all five entries in `groundscan_research/__init__.py:21-52`:

| registry label | target module | is a facade? |
| --- | --- | --- |
| `registration_semantics` | `groundscan_research.registration_atlas` | yes |
| `registration_robustness` | `groundscan_research.registration_recovery` | yes |
| `cross_scan_evidence` | `groundscan_research.cross_scan_evidence` | yes |
| `broad_response` | `groundscan_research.generator_generalization` | yes |
| `background_separation` | `groundscan_research.background_separation` | yes |

Four of the five facades carry a docstring claim that is therefore false as written:

- `registration_atlas.py:9` — *"no CLI path imports this package"*
- `registration_recovery.py:8` — *"No CLI path imports this package."*
- `background_separation.py:9` — *"no CLI path imports this package"*
- `generator_generalization.py:9` — *"no CLI path imports this package"*

(The fifth, `cross_scan_evidence.py:4-6`, makes the weaker and *correct* claim — *"never gates
production"* — which is not the same statement.)

The claim was presumably true of `registration_atlas.py` and `registration_recovery.py` when they
were written, and was falsified later when the registry in `__init__.py` began routing through
them. **`__init__.py`'s own docstring (`groundscan_research/__init__.py:1`) repeats it too:
*"Research-only experiments. Never imported by groundscan/."***

### 1.3 "33 diagnostic modules" — off by one, and off by six more than that

`docs/legacy/groundscan_research/` holds **33 `.py` files**, of which **1 is `__init__.py`** and
**32 are modules**. Of those 32, **5 are pure re-export facades** with no `run_*` entry point of
their own (`registration_atlas.py` 22 lines, `registration_recovery.py` 27,
`background_separation.py` 27, `cross_scan_evidence.py` 27, `generator_generalization.py` 34), and
each contains nothing but a docstring, `from`-imports, and `__all__`.

So the count of **studies** — modules that actually run something — is **27**, not 33 and not 32.

### 1.4 Verdict

> The premise is **false as stated and correct only after two corrections**, neither of which is
> in the map:
>
> 1. *One whitelisted, function-local, non-gating CLI import exists* — and it reaches all five
>    facades, falsifying four docstrings that deny it.
> 2. *33 is the file count.* The module count is 32; the study count is 27.

The "dead code" reading of the map does not survive measurement. What survives is narrower and
more interesting: **a research subtree with a live, documented, deliberately non-gating entry
point from the product CLI.** Whether that makes it *live code* or *dead code with a research arm*
is [#88](https://github.com/abdoupk/groundscan-analyzer-v2/issues/88)'s verdict to assign, not this
ticket's.

---

## 2. The measured import graph

### 2.1 What was enumerated, and over what

**Corpus:** every `.py` file reachable from the repository root, walked with `os.walk`, excluding
the directory names `.venv`, `.git`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`,
`.gremlins_cache`, `.eggs`, `node_modules`, `build`, `dist`.

**Result: 203 `.py` files parsed. Zero parse errors.** Of those, **98** are under
`docs/legacy/groundscan/` (the engine), **33** under `docs/legacy/groundscan_research/`, **68**
under `docs/legacy/tests/` and `docs/legacy/tools/`.

Because the method is AST-based, docstrings and comments **cannot** produce a false positive. That
distinction matters twice below, because the string `groundscan_research` appears in the engine
three times and only once of those is an import.

### 2.2 (b) Engine → research: **one importer, one import statement**

The complete set of non-comment occurrences of the string in `docs/legacy/groundscan/`:

| location | kind | is it an import? |
| --- | --- | --- |
| `cli/validate.py:77` | `from groundscan_research import EXPERIMENTAL_RUNNERS` | **yes — the only one** |
| `validation/profiles.py:10` | docstring line describing the experimental suite list | no |
| `validation/profiles.py:50` | `EXPERIMENTAL_SUITES: list[str] = ["groundscan_research", ...]` | no — a string constant naming a pytest target |

**Exact importer list: `docs/legacy/groundscan/cli/validate.py`. One module of 98. One statement.**

The `profiles.py` occurrences matter for a different reason: `groundscan_research` is a **declared
test-suite target** in `groundscan/validation/profiles.py:50`, so the subtree is wired into legacy's
own release-profile vocabulary, not merely tolerated.

### 2.3 (c) Outside `docs/legacy/`: **zero, and verified rather than assumed**

- `.py` files outside `docs/legacy/` that **mention the string at all** (crude text search, so an
  upper bound): **0**.
- `.py` files outside `docs/legacy/` that **import it** (AST): **0**.

The greenfield claim holds. `src/groundscan_analyzer/` contains 3 import statements in total and
none of them is this.

### 2.4 Importers elsewhere inside `docs/legacy/`

Of the 68 `.py` files under `docs/legacy/tests/` and `docs/legacy/tools/`, exactly **one** imports
the subtree:

```
docs/legacy/tests/experimental/test_registry.py:5,15
    from groundscan_research import EXPERIMENTAL_RUNNERS, RESEARCH_SUITES
```

That is legacy's own test tree, not the engine. It does mean the subtree had a live test.

### 2.5 (d) Research → engine: **24 of 32 modules import the engine**

The dependency runs **one way**: research imports the engine heavily, and the engine imports
research exactly once, non-gating.

- **24 of 32** research modules import from `groundscan.` — `groundscan.api`,
  `groundscan.core.*`, `groundscan.models`, `groundscan.services.*`, `groundscan.site.*`,
  `groundscan.validation.synthetic_core.*`.
- **25 of 32** import another `groundscan_research` module.
- **0 of 32** do neither — every research module is connected in at least one direction.
- Exactly **one** module uses a *dynamic* import: `registration_compound_recovery.py`, whose
  function-local `__import__("groundscan_research.registration_failure_semantics", ...)` appears at
  `:127-130`, and which also has a plain function-local
  `from groundscan_research.registration_failure_semantics import _physical_rotate_anomaly` at
  `:287-289` in the sibling study.

**19 distinct private engine symbols** are imported by the subtree — names beginning with `_`:

| engine module | private symbols taken |
| --- | --- |
| `groundscan.site.registration` | `_TRANSFORMS`, `_multiscale_maps`, `_resample_to`, `_safe_correlation`, `_shift_with_mask`, `_shift_array_integer` (6) |
| `groundscan.validation.synthetic_core.acquisition_stress` | `_scenario`, `_safe_mean`, `_build_scan`, `_designs`, `_profiles` (5) |
| `groundscan.validation.synthetic_core.cross_scan_variation_audit` | `_scenario`, `_apply_variation`, `_families`, `_variations`, `_fuse` (5) |
| `groundscan.core.anomaly` | `_broad_component_selection`, `_regional_trend_zscore` (2) |
| `groundscan.validation.synthetic_core.geology_local` | `_make_scenario` (1) |

That is a substantial coupling to implementation details, and it is the reason a module named
`groundscan/research_api.py` used to exist — see §6.

### 2.6 The internal shape is a star, like #56's

In-degree within `groundscan_research/`:

| in-degree | module |
| ---: | --- |
| **12** | `synthetic_generator_independence` |
| 6 | `forward_background_interaction` |
| 6 | `registration_failure_semantics` |
| 3 | `cross_scan_evidence_calibration` |
| 3 | `registration_recovery_coverage` |
| 2 | `background_separation_audit`, `background_decomposition`, `registration_compound_atlas`, `cross_scan_evidence_audit` |
| 1 each | 17 modules |
| **0** | the 5 facades |

Two hubs, for two different reasons: `synthetic_generator_independence` is the shared scene
generator; `registration_failure_semantics` holds the shared `_build_semantic_scan` /
`_expected_family` / `_failure_flags` contract that every registration study builds on.

The **5 modules with in-degree 0 are exactly the 5 facades** — which is the whole point: they are
entry points, not participants. Nothing inside the subtree imports them; only `__init__.py`'s
registry does, and through it, the CLI.

---

## 3. The module inventory by family

Grouping rule: **each of the 32 modules is assigned to exactly one family**, by its own docstring's
stated subject and its public entry point. 27 modules expose a `run_*` entry point; 5 are facades.
All 33 files total **8,391 lines**.

### Family A — Registration: failure taxonomy and recovery (11 modules)

| module | version | what it does |
| --- | --- | --- |
| `registration_semantics.py` | v0.2.74 | Controlled 5-case benchmark deciding whether `orientation_deg` means **scan-frame** or **heading-only**. |
| `registration_failure_semantics.py` | v0.2.75 | Reproducible failure atlas; supplies the shared semantics-aware scan builder and the 7-flag taxonomy. |
| `registration_robustness.py` | v0.2.72 | Compares the production aligner against conservative diagnostic scoring under acquisition stress. |
| `registration_recovery_experiments.py` | v0.2.76 | Two recovery ideas: winsorized correlation, and relaxed-overlap search. |
| `registration_recovery_coverage.py` | v0.2.78 | Coverage-aware + robust recovery search; **holds the three frozen recovery thresholds**. |
| `registration_recovery_repeated.py` | v0.2.79 | Re-runs the frozen v0.2.78 alternatives over six unseen seeds. |
| `registration_compound_atlas.py` | v0.2.77 | Decomposes compound corruption into singles, pairs, selected triples. |
| `registration_compound_recovery.py` | v0.2.81 | Consensus recovery: two independent searches must agree on transform *and* shift. |
| `compound_interaction_analysis.py` | v0.2.80 | Nonlinear degradation from combinations, measured against the worst relevant lower-order condition. |
| `registration_atlas.py` | — | *Facade*, re-exporting 4 of the above. |
| `registration_recovery.py` | — | *Facade*, re-exporting 5 of the above. |

### Family B — Cross-scan evidence: calibration, stability, holdouts (5 modules)

| module | what it does |
| --- | --- |
| `cross_scan_evidence_audit.py` | Tests whether patch-based cross-scan evidence already separates matched from unmatched fused candidates; reports sweeps, selects no gate. |
| `cross_scan_evidence_calibration.py` | Fits a bounded 4-feature ranking score; **selects a threshold on a calibration split, evaluates once on an independent holdout.** |
| `cross_scan_evidence_stability.py` | Repeated multi-seed stability of that frozen threshold. |
| `cross_scan_evidence_repeated_holdouts.py` | Five further independent holdouts of the same frozen threshold. |
| `cross_scan_evidence.py` | *Facade*, re-exporting all four plus two Family-F modules. |

### Family C — Generator independence and generalisation (4 modules)

| module | what it does |
| --- | --- |
| `synthetic_generator_independence.py` | Renders one ground-truth plan through **two independent forward models** (A/B/C); the subtree's shared scene generator. |
| `generator_shift_analysis.py` | Same plans, three generators; separates extraction miss / classification mismatch / correct match. |
| `generator_c_mechanism.py` | Isolates geological broad-response loss by adding Generator-C ingredients one stage at a time. |
| `generator_generalization.py` | *Facade*, re-exporting all of Family C **and Family E**. |

### Family D — Background separation and attribution (7 modules)

| module | version | what it does |
| --- | --- | --- |
| `background_separation_audit.py` | v0.2.88 | Attributes broad-response loss to background estimation; compares practical estimators against an oracle ceiling. |
| `background_decomposition.py` | v0.2.92 | Compares practical residualisation families after periodic / radial-curvature backgrounds were identified as dominant. |
| `background_factor_attribution.py` | v0.2.91 | Varies **one** background component at a time to find which property causes geological extraction loss. |
| `background_independent_separation.py` | v0.2.93 | Prototype of a background-independent separation (DoG + shape gate). |
| `adaptive_scale_separation.py` | v0.2.89 | Unsupervised multiscale representation vs a fixed background scale. |
| `forward_background_interaction.py` | v0.2.87 | Attributes generator-shift loss to forward response, background field, or their interaction. |
| `background_separation.py` | — | *Facade*, re-exporting five of the above. |

### Family E — Geology / broad-response extraction under generator shift (2 modules)

| module | version | what it does |
| --- | --- | --- |
| `geology_extraction_shift.py` | v0.2.84 | Separates broad-component **extraction coverage** from downstream **classification**, so generator-shift failure is not misread as classifier failure. |
| `geology_extraction_independence.py` | v0.2.85 | Same, across three generators, with a 5-state taxonomy: `correct_broad`, `suppressed_broad`, `present_misclassified`, `component_absent`, `extraction_miss`. |

### Family F — Rescue discriminants and spatial support (2 modules)

| module | what it does |
| --- | --- |
| `extraction_rescue_discriminants.py` | Labels synthetic rescue candidates `recovered` / `unmatched` against truth and compares their observable features. |
| `spatial_context_audit.py` | Clones a base scan three times with **lattices held exactly identical**, varying only gain and noise, and asks whether a rescue candidate reappears near the same physical coordinates on repeats. |

### Family G — Single-purpose tail (1 module)

| module | version | what it does |
| --- | --- | --- |
| `broad_response_representation.py` | v0.2.86 | Compares alternative low-frequency broad-response representations. Sits in Family C's dependency closure but is not a generator study. |

### 3.1 Is the clustering honest? — yes, with three named caveats

The grouping above is defensible but **not clean**, and three specific frictions should not be
hidden:

1. **`forward_background_interaction.py` is claimed by two families.** Its own docstring
   (v0.2.87) frames it as a *generator-shift* attribution study; six modules import it; the ticket's
   own estimate puts background separation at 6. I counted it in Family D, making D 7. Counting it
   in C instead would make C 5 and D 6. **The 6-vs-7 disagreement is entirely this one module.**

2. **`cross_scan_evidence.py` (facade) re-exports two Family-F modules.**
   `cross_scan_evidence.py:15-18` pulls in `run_extraction_rescue_discriminant_audit` and
   `run_spatial_context_audit`. So "cross-scan evidence" as a family name does not match what the
   cross-scan facade actually exposes. The facade is grouped by name; its contents straddle F.

3. **`generator_generalization.py` (facade) re-exports all of Family E.**
   `generator_generalization.py:20-21`. So Family C's facade is also Family E's facade. Again
   grouped by name; contents straddle.

Against the clustering named in [#89](https://github.com/abdoupk/groundscan-analyzer-v2/issues/89)
(registration 11, cross-scan 5, generator 4, background 6, geology 2, plus a tail), **this
reproduction agrees exactly on 11 / 5 / 4 / 2 and differs by one module on the background family
(7 vs 6).** The clustering is real and the ticket's estimate was close.

### 3.2 The "eleven registration-recovery studies" does not reproduce

No single rule yields 11 for "registration-recovery studies". The derivable counts:

| rule | count |
| --- | --- |
| filename prefix `registration_` | **10** (of which 2 are facades, 8 are studies) |
| filename contains `registration_recovery` | **4** (of which 1 is a facade) |
| filename prefix `registration_` **plus** `compound_interaction_analysis` | **11** |
| modules that import `registration_failure_semantics` | **6** |
| study modules reachable from the two registration facades | **8** |

**11 is reachable only** as "registration-*themed*, counting the two facades and counting
`compound_interaction_analysis` as registration despite its name." That is the reading used in
Family A above. A reader who means "recovery studies" proper gets **4**. The ticket's phrase
should not be repeated without saying which rule produced it.

---

## 4. Cross-check against the decided registration tickets

Six tickets are checked. For each: did its reasoning need something a research module contains,
and fail to cite it?

### 4.1 #4 — "How does the engine learn the orientation of a scan?" — **needed, and uncited**

**The most on-point artefact in the entire tree is `registration_semantics.py` (v0.2.74)**, and
[#4](https://github.com/abdoupk/groundscan-analyzer-v2/issues/4) does not cite it. #4's archaeology
cites only production files: `registration.py:16-25`, `:208-219`, `cli/analyze.py:151-157`,
`analyze_site.py:48-59`.

What #4's reasoning needed and did not have:

- **A measurement of what the orientation field's two possible readings *do*.** #4 asks "where
  does orientation come from" and correctly declines to answer it. But the prior question — *if you
  have one, what does it mean?* — was answered. `registration_semantics.py:53-96` runs five cases
  (same frame; **metadata-only 90**; **physical rotation 90 with metadata**; physical rotation 90
  **without** metadata; metadata-only 180) and computes a `frame_contract_pass` predicate requiring
  metadata-only-90 evidence **< 0.50** while both physical-rotation cases reach **≥ 0.80** with a
  `rot90`/`rot270` winner. The load-bearing conclusion is recorded verbatim in the payload at
  `:125-130`: *"The current implementation is compatible with **scan-frame** orientation metadata,
  not heading-only metadata."*
- **A data-model mechanism for carrying which semantics an orientation field has.**
  `registration_failure_semantics.py:156-158` stamps
  `designed.metadata.extra["orientation_semantics"] = "scan-frame"` into the payload. Legacy built
  the thing #10 later asks for; no ticket records that it existed.
- **An explicit refusal to over-claim.** `registration_semantics.py:170-172`: *"This benchmark
  characterizes GroundScan behavior; it does not prove what an external/vendor metadata field
  means."* That is the epistemic-regime caveat stated in 2019-era code, in the exact place a reader
  would look.

**Verdict: needed and uncited.** The map's own summary sentence — *"no adapter ever set scan
orientation"* — is correct, and is *why* `registration_semantics.py` matters: it measures the
consequence of that gap rather than restating it.

### 4.2 #9 — "What frame do fused detections live in, and what is the reference scan?" — **nothing in the subtree bears on it**

This is the one clear **negative**, and it is a real hole rather than an omission.

**No research module varies the reference scan.** Every registration study constructs one fixed
reference at orientation `0.0` with the `clean` profile and probes it against variants:

- `registration_failure_semantics.py:217-234`
- `registration_recovery_coverage.py:252-269`
- `registration_compound_recovery.py:133-149`

A literal search for `re-root`, `reroot`, `swap`, `permut`, `invarian` across all 33 files returns
**no** study of reference choice. The seed-varying modules
(`cross_scan_evidence_stability.py`, `cross_scan_evidence_repeated_holdouts.py`) vary **seeds**,
not the reference. `spatial_context_audit.py` varies gain and noise on lattice-identical clones and
measures `position_dispersion_m` — that is repeat-consistency of **one** lattice, not frame
invariance under re-rooting.

So: **#9's core question — is fused output physically invariant under a change of reference — has
no study anywhere in `docs/legacy/`, research subtree included.** That is a finding about the
absence of evidence, and it cuts against any argument that the subtree is the surviving record of
the registration programme. It is equally a finding about the archaeology's limits.

### 4.3 #10 — "The perpendicular survey: a 90-degree turn, two scans, one answer" — **needed, uncited, plus a contradiction**

Three findings.

**(a) The only controlled study of the 90° case in the tree is uncited.** The 5-case matrix above is
precisely the distinction #10 must draw. #10's archaeology cites production only
(`registration.py:148-163`, `:166-180`, `core/shape.py:160-171`).

**(b) The transform-family narrowing — the data-model answer — is recorded in code and in no
ticket.** Once *both* orientations are known, the family collapses from 8 members to **4
rotations only**:

```
docs/legacy/groundscan/site/registration.py:209-217      (production)
    if orientation_a_deg is not None and orientation_b_deg is not None:
        delta = (float(orientation_b_deg) - float(orientation_a_deg)) % 180.0
        if min(delta, 180.0 - delta) < 22.5:   allowed = {"rot0", "rot180"}
        elif abs(delta - 90.0) < 22.5:        allowed = {"rot90", "rot270"}
        else:                                 allowed = {"rot0","rot90","rot180","rot270"}
        transforms = [(n, f) for n, f in _TRANSFORMS if n in allowed]
```

mirrored at `registration_recovery_coverage.py:64-74`. **All four `flip_*` transforms become
unreachable** whenever orientation is known. The map's Notes say the 8-member family was searched
"*every time*" on real files — true, because no adapter ever set orientation — but the ticket that
decides the perpendicular case never records that **knowing orientation would remove the reflections
entirely**, by a ±22.5° band on `delta mod 180`.

**(c) A contradiction between what the search permits and what the atlas expects.** The
*expected*-family helper still counts reflections as legitimate outcomes:

```
docs/legacy/groundscan_research/registration_failure_semantics.py:79-85
    if min(delta, 180.0 - delta) < 22.5:
        return {"rot0", "rot180", "flip_rot0", "flip_rot180"}
    if abs(delta - 90.0) < 22.5:
        return {"rot90", "rot270", "flip_rot90", "flip_rot270"}
```

while `_orientation_allowed` permits rotations only. So in the both-known case **every `flip_*` row
is a miss**, and the atlas's `transform_family_match_rate` is computed against a set the search
cannot produce. Any figure read from that rate is a floor, not a measurement of correctness.

**#10's guard is respected by the code**: `orientation_deg` is only ever read from
`scan.metadata`, never from a candidate — so "scan orientation is not candidate orientation" holds
in the code, and `core/shape.py`'s `orientation_deg` PCA axis is a separate name in a separate
module.

### 4.4 #15 — "The order-dependence inventory and its tie rules" — **directly relevant, uncited**

**Production already has a documented tie-break, and #15's cited range stops just before it.**
[#15](https://github.com/abdoupk/groundscan-analyzer-v2/issues/15) cites
`site/registration.py:198-243` and describes the search as having "no documented tie-break among
equal scores". The tie-break is at **`registration.py:267-273`**, outside the cited range:

```python
    # Rank by composite score, then prefer the smallest displacement. Python's
    # sort is stable, so without this tiebreak a flat (zero-correlation) surface
    # resolved to the first candidate enumerated -- (-max_shift, -max_shift) --
    # and displaced the scan by twelve cells on both axes. Ties now resolve to
    # the origin, which is the only shift that is defensible when the data
    # cannot distinguish the candidates.
    scored.sort(key=lambda row: (row[0], -abs(row[4]) - abs(row[5])), reverse=True)
```

That is a five-line rationale naming the exact failure mode. **This is a citation-range defect in
#15, not a research-tree finding** — but it means #15's premise about the search must be re-read
before the tie rules are written, or a rule will be written for a hazard that no longer exists.

The subtree then supplies **two further, different** rules for the *same* search:

| site | sort key | runner-up | margin unit |
| --- | --- | --- | --- |
| `registration.py:273-284` | `(score, -\|dy\|-\|dx\|)` desc | best **raw correlation** among **strictly different transforms** | raw Pearson correlation |
| `registration_recovery_experiments.py:136-148` | `score` alone, reverse | next in sorted order | composite score |
| `registration_robustness.py:115` | `score` alone, reverse | — | composite score |
| `registration_recovery_coverage.py:132-145` | `(-score, name, dy, dx)` — a full total order | next in sorted order | composite score |

**Three rules for one search, in one tree.** `registration_robustness.py:115` and
`registration_recovery_experiments.py:136` are stable sorts with no tie-break, i.e. they reproduce
precisely the twelve-cell-displacement failure that production's `:267-272` comment documents.

### 4.5 #28 — "The separation margin and stability criteria" — **needed, uncited, and the densest overlap in the subtree**

This is where the subtree would justify *preserve* rather than *remove*. It cuts both ways.

**What the subtree holds that #28 needed**

1. **Three different definitions of the quantity #28 must threshold, all named
   `ambiguity_margin`.** Worse, **two of the three store a composite score into a field named
   `correlation`** — `registration_recovery_experiments.py:147`
   (`second_best_correlation=float(second_score)`) and `registration_recovery_coverage.py:144`
   (`second_best_correlation=float(second[0])`, where `x[0]` is the composite score). **No figure
   from these two modules may be read as a correlation figure.**
2. **Two unreconciled thresholds on that name**, differing by 50% with no recorded rationale:
   - `registration_failure_semantics.py:47` — `FAILURE_THRESHOLDS["ambiguous_transform_margin"] = 0.03`
   - `registration_recovery_coverage.py:46` — `RECOVERY_MARGIN_MIN = 0.02`
   For scale: #28's body reports the corpus's only real multi-scan pair at a **0.033** correlation
   margin, which clears `0.03` by `0.003`. *(My comparison of two independently-sourced numbers; I
   am not asserting the 0.033 is a `recorded` figure, and #28 itself says it "is not a threshold".*
   *It is recorded here because it is the only place in the repo where a real-corpus margin and a
   legacy threshold can be set side by side, and the margin is thinner than the two legacy
   thresholds' own 50% spread.)*
3. **A worked example of the derivation route #28 calls the only defensible one.**
   [#28](https://github.com/abdoupk/groundscan-analyzer-v2/issues/28) point 2: *"a measured
   distribution of margins over many synthetic cases is the only route that produces a defensible
   number rather than a chosen one."* That was done once, on a different quantity:
   `cross_scan_evidence_calibration.py:98-104` sweeps **101 score quantiles**, selects on a
   **calibration split only**, with a stated sort `(f1, recall, precision)` and a stated rationale
   for recall's priority (`:101-102`, *"to avoid trading away many true candidates simply to reduce
   false positives"*), then evaluates **once** on an independent holdout with three declared seeds
   (`train_seed=7068`, `calibration_seed=9092`, `holdout_seed=10092`).
4. **A derived threshold with recorded provenance, frozen.**
   `FIXED_THRESHOLD = 0.3462032574991704` with `BASELINE_THRESHOLD = 0.7190799999999999`, declared
   identically in `cross_scan_evidence_stability.py:28-29` and
   `cross_scan_evidence_repeated_holdouts.py:22-23`, and labelled at `:77`
   `"thresholds_frozen_from_v0268_calibration"`. **This is the single most register-shaped object
   in the subtree: a number, a provenance label, an independent-holdout discipline, and a stability
   re-run over six seeds.** It is currently in **zero** entries of `docs/measurements.md`.
5. **Seeds and trial counts declared in the protocol, not the test** — #28 point 4 verbatim:
   - `registration_recovery_repeated.py:17` — 6 seeds; `:20` — 4 modes; `:33-36` — run signature
   - `cross_scan_evidence_stability.py:27` — 6 seeds
   - `cross_scan_evidence_repeated_holdouts.py:21` — 5 holdout seeds
6. **A per-quantity-class perturbation protocol with magnitudes** — #28 point 3 verbatim (*"the
   protocol's magnitude should be justified per quantity class"*).
   `registration_failure_semantics.py:52-76` declares nine named profiles with explicit magnitudes:
   noise σ=1.6; dropout 12% missing / 6% rows; partial coverage 22% / 18%; drift (+0.10, −0.07)
   with line bias 0.9; outliers 2.5% at σ=18; jitter 0.16 m; and `compound` = nine effects
   simultaneously, including `quantization_step=0.08`. `registration_compound_atlas.py`'s
   `SELECTED_TRIPLES` enumerates the chosen compound combinations.
7. **Two independently-scoped margins already measured in their own spaces** — answering #28 point
   1 (*"whether the margin applies to the transform search, to the component hierarchy, to fusion,
   or to each independently"*). The subtree's `ambiguity_margin` is scoped to the **transform
   search**; `cross_scan_evidence_calibration`'s threshold is scoped to a **fused cross-scan
   evidence score**. Neither is compared to the other.

**Why the subtree cannot be a figure source**

- Every module self-declares non-gating and synthetic-only, and states *"No independently verified
  field ground truth is available"* in its emitted payload (e.g.
  `registration_failure_semantics.py:347`, `registration_recovery_coverage.py:359`).
- **The outputs are not in this copy** — see §6. No number any of these studies would produce is
  available to be quoted.
- `registration_recovery_repeated.py:89` hard-codes `"compound_unresolved": True` — a **literal,
  not a measurement**. The study that would have resolved compound corruption never did.
- `registration_recovery_experiments.py:85` runs the **full 8-member family with no orientation
  narrowing**, ignoring the v0.2.74 frame contract, and its empty-search fallback at `:128-135`
  calls `align_grids` **without** `orientation_a_deg` / `orientation_b_deg`, silently switching to
  the unknown-orientation path. So v0.2.76 does not implement the contract its own docstring implies,
  while v0.2.78 does. **The subtree contradicts itself across versions on which transform family
  is admissible.**

**Verdict: needed and uncited, and the strongest preserve signal in the subtree — but as *design*
evidence (protocols, taxonomies, divergences, provenance), not as a figure source.**

### 4.6 #29 — "The synthetic perpendicular scenario" — **partly needed and uncited; one hard negative**

**Supports.** #29 asks where the synthetic-only caveat should live "*so it travels with the result
instead of living in a comment*". `registration_failure_semantics.py:156-158` answers that
question: synthetic-ness is carried **in the payload as data** —
`metadata.extra["synthetic_ny"]`, `["synthetic_nx"]`, `["orientation_semantics"]`.

And #29's acceptance assertion "*measurement lattices remain independent and unresampled* /
*primary positions remain exact scan-local integer indices*" has a working precedent in
`spatial_context_audit.py:35-53`: `_clone_scan` copies `x`, `y`, `z`, `twt_ns`, `grid_i`, `grid_j`,
`latitude`, `longitude` and `coords_are_index_only` **exactly**, and varies **only** gain and
additive noise — then measures `position_dispersion_m` across three repeats at a 2.5 m spatial
radius against a 3.0 m truth radius. That is lattice identity held exact under value variation,
which is the mechanism the unequal-pitch case would need.

**The hard negative.** #29 requires the scenario to contain **both 90° CW and 90° CCW
declarations**, inheriting #10's assertion that "*CW and CCW declarations are preserved exactly
and never repaired into one another*". **The archived code cannot express that distinction.** Every
orientation delta in the registration tree is reduced modulo 180:

- `registration_failure_semantics.py:80` — `delta = float(delta_deg) % 180.0`
- `registration.py:210` — same
- `registration_recovery_coverage.py:67` — same

and both the expected family and the allowed family distinguish only `{rot0, rot180}` from
`{rot90, rot270}`. **A 90° CW survey and a 90° CCW survey are the same set to this code.** The
`rot90` / `rot270` names that *do* appear in `registration_semantics.py:92,94` are distinguished —
but only as an outcome label, never as an input declaration, and never modulo 360.

**Verdict: partly needed and uncited, and the CW/CCW collapse is a finding that bears directly on
#29's required assertions.** It is a reason the subtree cannot be treated as a template for the
perpendicular scenario — and, read the other way, a reason the assertions in #10 and #29 are
*new* work rather than a port.

### 4.7 Summary of Part 4

| ticket | needed something the subtree holds? | cited it? |
| --- | --- | --- |
| #4 orientation | **yes** — the frame-vs-heading measurement, and a payload-level semantics declaration | no |
| #9 reference scan / frame | **no** — no such study exists anywhere in `docs/legacy/` | n/a |
| #10 perpendicular | **yes** — the 90° case matrix, and the orientation-known narrowing that removes all reflections | no |
| #15 order-dependence | **yes** — three competing tie-break rules for one search | no |
| #28 margin / stability | **yes, most of all** — 3 margin definitions, 2 thresholds, a calibration/holdout route, a frozen derived threshold, seed and perturbation protocols | no |
| #29 synthetic scenario | **partly** — a declaration mechanism and a lattice-exactness precedent | no |
| | **and a hard negative** — the tree cannot represent CW vs CCW | |

**And one citation-range defect found outside the subtree:** #15 cites `registration.py:198-243` and
describes a search with no tie-break; the tie-break is at `:267-273`.

---

## 5. Prior art in `docs/research/`

`docs/research/` holds five reports. Measured occurrences of the string `docs/legacy` and of
`groundscan_research` in each:

| report | lines | mentions `docs/legacy` | mentions `groundscan_research` |
| --- | ---: | ---: | ---: |
| `okm-device-and-export.md` (R1) | 555 | 0 | 0 |
| `prior-art-and-tooling.md` (R3) | 597 | 0 | 0 |
| `interpretation-literature.md` (R2) | 592 | 0 | 0 |
| `okm-impulse-count-and-spacing.md` (R4) | 458 | 0 | 0 |
| `residual-field-remeasurement.md` (R4) | 344 | 0 | 0 |

**No prior report covers any of this.** All five are external-evidence reports (device
documentation, published literature, package prior art, corpus re-measurement) and none reads the
vendored source tree at all. There is nothing to cite and nothing to duplicate.

The convention followed here is `residual-field-remeasurement.md`'s (R4, ticket #42): a stated
method, a stated corpus, and the discipline that a number's authority lives in
`docs/measurements.md` and never in the report. **This report deliberately registers no figures.**
§4.5 item 4 names one candidate for registration and §4.6 names one negative; both are for #88 and
its owner to admit or reject, and neither is entered in the register by this file.

---

## 6. Counts I derived, and exactly how

**Every number in this report is derived by enumerating files in this working tree at
2026-10-06. None is a maintained count, and none is registered in `docs/measurements.md`.** If any
of them is later quoted, it must be re-derived rather than trusted, because `docs/legacy/` is
untracked and can change underneath the reader.

| figure | value | derivation |
| --- | ---: | --- |
| `.py` files in the subtree | **33** | `glob("docs/legacy/groundscan_research/*.py")`, top level only. Verified: the sole subdirectory is `__pycache__`, and there are no non-`.py` source files. |
| of which `__init__.py` | **1** | filename test |
| **modules** (the map's disputed number) | **32** | 33 − 1 |
| facades (no `run_*` entry point of its own) | **5** | AST: no top-level `FunctionDef` whose name starts with `run_`. Names: `registration_atlas`, `registration_recovery`, `background_separation`, `cross_scan_evidence`, `generator_generalization`. (A sixth file, `__init__.py`, also has no `run_*`, but it is not a module.) |
| **studies** | **27** | 32 − 5 |
| total lines across the 33 files | **8,391** | sum of `splitlines()` per file |
| `__pycache__` `.pyc` files | **33** | `glob("__pycache__/*.pyc")` — consistent with 33 source files |
| `.py` files parsed repo-wide | **203** | `os.walk` from the repo root, excluding 11 directory names listed in §2.1. Zero parse errors. |
| engine `.py` files | **98** | subset under `docs/legacy/groundscan/` |
| engine modules importing the subtree | **1** | AST, non-comment occurrences in `docs/legacy/groundscan/`: 3 string occurrences, 1 `ImportFrom` |
| `.py` files outside `docs/legacy/` mentioning the subtree | **0** | text search (upper bound) then AST (exact) |
| research modules importing the engine | **24 / 32** | AST `ImportFrom`/`Import` with top-level segment `groundscan` |
| research modules importing the subtree | **25 / 32** | same, top-level segment `groundscan_research`; relative imports resolved against `docs/legacy` as root |
| research modules importing neither | **0 / 32** | set difference |
| distinct private engine symbols taken | **19** | AST `ImportFrom` from `groundscan.*` with a leaf name beginning `_`, deduplicated |
| distinct private research-internal symbols taken | **27** | same, `groundscan_research.*` |
| research internal import statements: absolute / relative | **49 / 9** | AST; the 9 relative are all in `registration_atlas.py` and `registration_recovery.py` |
| research modules using a dynamic import | **1** | `registration_compound_recovery.py` |
| Family counts | **11 / 5 / 4 / 7 / 2 / 2 / 1** | each of the 32 modules assigned exactly once, by its own docstring and public entry point; see §3 and the three caveats in §3.1 |
| largest in-degree in the subtree | **12** | `synthetic_generator_independence` |

**On the map's "33 diagnostic modules":** the map's number is the **file** count, not the module
count and not the study count. It is off by one against "modules" and off by six against "studies".

---

## 7. What I could **not** establish

1. **Any measured result of any study in the subtree.** `docs/legacy/results/` contains exactly one
   file, `.gitkeep`. Every study writes a `.json` + `.md` pair (e.g.
   `registration_recovery_coverage.py:361,410`) into an output directory, and **none of those
   artefacts is present**. The `.pyc` files prove the subtree was compiled and that legacy's
   `tests/` were run under pytest, but no figure is recoverable. **Every threshold, seed,
   taxonomy and protocol in this report is read from source, never reproduced by running it.**
   This is the single largest limitation and it is why §4.5 recommends *preserve* as design
   evidence rather than as a figure source.

2. **Whether "eleven registration-recovery studies" is the intended set.** §3.2 gives five
   derivable counts and none other equals 11 except one specific rule. I could not find the rule
   the phrase was written from, and the phrase should not be repeated unqualified.

3. **Whether `groundscan/research_api.py` existed when this vendored copy was cut.**
   `docs/legacy/groundscan/__pycache__/research_api.cpython-313.pyc` survives with **no `.py`
   source**. Its embedded docstring reads: *"Stable research facade: public aliases for internals
   research needs. `groundscan_research/` historically imports private helpers … are
   implementation details and may move. New research code should import …"*, and its `co_filename`
   is `C:\Users\abdou\Desktop\groundscan_analyzer_refactored\groundscan\research_api.py` — an
   unshippable path from the author's machine. So the 19 private engine symbols in §2.5 are a
   **known, once-acknowledged problem** that legacy had begun to fix and did not finish. I cannot
   date the removal or tell whether the fix was complete.

4. **Whether `test_research_boundary.py` currently passes.** `test_wheel_excludes_research`
   (`:38-58`) reads `ROOT / "pyproject.toml"` where `ROOT = parents[2]`, i.e.
   `docs/legacy/pyproject.toml` — **which does not exist in this copy** (the directory holds only
   `.pre-commit-config.yaml`, `requirements.txt`, `requirements-dev.txt`). Running legacy's tests
   would write into the archaeology tree, which the constraints forbid, so I did not run it. My
   claim that the *first* test would pass is a **static inference** from the AST: the one engine
   reference to `groundscan_research` is `cli/validate.py:77`, whose line contains
   `EXPERIMENTAL_RUNNERS`, which is exactly what `:32-33` whitelists.

5. **Whether the subtree was ever in a released artefact.** `test_wheel_excludes_research` records
   the *intent* — `groundscan_research` must not match any
   `tool.setuptools.packages.find.include` pattern — but that test cannot be run here (§7.4), so I
   can report the recorded intent and not the fact.

6. **The map author's process.** I can measure the tree as it stands. I cannot audit whether the
   "never imported by the engine" sentence was ever checked, or whether the exception was known and
   dropped. [#89](https://github.com/abdoupk/groundscan-analyzer-v2/issues/89) states that no
   ticket records the check; I found no ticket that contradicts that, and the one place the check
   *is* recorded — `test_research_boundary.py` — is inside the archaeology, untracked and uncited.

7. **Any conflict between this report and a *decided* ticket.** #4, #9, #10, #15, #28 and #29 stand.
   §4.3's contradiction (allowed family = rotations only, expected family includes flips) and
   §4.6's CW/CCW collapse are recorded as findings about the **legacy tree**, not as grounds to
   reopen anything. Nothing here re-decides a registration question.

8. **Console encoding.** The map Notes were read through `gh --jq`; one glyph in the `groundscan_research`
   highlight renders as a replacement character crossing PowerShell's cp1256 boundary. It has been
   normalised to `-` throughout. **No mojibake was treated as source damage**, and no file was read
   through the shell for any quoted string — all quoted text comes from the file tools, which go
   through disk.
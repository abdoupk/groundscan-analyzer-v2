# R3 — Prior art and reusable tooling for ground-scan processing

**Ticket:** #22 "Prior art and reusable tooling for ground-scan processing" (abdoupk/groundscan-analyzer-v2)
**Author:** research subagent
**Date:** 2026-10-01
**Scope:** survey of open-source / maintained tooling that could replace or justify parts of a ~56,500-line legacy OKM ground-scan analysis system, re-evaluated against Python 3.13.

## How this was researched

* Package metadata (current version, exact last-release date, `requires_python`, release cadence) is taken from the **PyPI JSON API** (`https://pypi.org/pypi/<name>/json`) — not from search snippets. Where a "latest" version had no files uploaded, the most recent version with actual files is reported.
* Maintenance state is taken from the **GitHub REST API** (`pushed_at`, `archived`, open issue counts, last commit subjects) via `gh`.
* Behavioural claims are **empirically verified** in a throwaway venv (Python 3.13, outside the repo) against the exact resolved versions the project already pins: numpy 2.5.3, scipy 1.18.1, pint 0.26.1, pydantic 2.13.5, orjson 3.12.0, plus candidate additions. Nothing in the repository was modified; the repo working tree is clean.
* Format/prior-art claims about OKM are taken from **OKM's own documentation** (first-party), not third-party write-ups.

Everything below marked "verified" was run. Everything marked "docs" is quoted from the package's own documentation.

---

## 1. Straight verdicts

These are the things that should change a decision immediately.

1. **`orjson` must not be the frozen scientific contract's serializer. It silently converts NaN/±Infinity to `null` on `dumps` and refuses to parse them back on `loads`.** Verified on 3.12.0: `orjson.dumps([nan, inf, -inf])` → `b'[null,null,null]'`; `orjson.dumps({"v": nan})` → `b'{"v":null}'`; `orjson.loads('{"v": NaN}')` → `JSONDecodeError`. There is no `allow_nan` switch, and that is not the only problem: the data loss is **silent**, not an error. For a contract that must round-trip, that is the worst possible failure mode. `numpy.save` (already available) round-trips `nan`/`inf` exactly — verified.

2. **`audit-requirements.txt` is stale, and `AGENTS.md`'s claim that it "is currently in sync with uv.lock" is false.** Re-running the exact recorded command (`uv export --no-emit-project --frozen`) produces 76 packages including `vulture`; the committed file has 75 and is missing `vulture` and nothing else. This is a **real packaging gap, not an export artefact** — one command fixes it. Verified with uv 0.12.6.

3. **Drop `natsort`.** It is the only dependency in the project that is stale on PyPI: last release 8.4.0 on **2023-06-20** — over three years ago. The git repository *is* still receiving merged community PRs (last push 2026-09-19, 6 open PRs, 13 open issues), so it is not abandoned, but fixes merged in Aug/Sep 2026 are not on PyPI. Against that, the vendored corpus has no numeric tokens in any filename and the only concrete requirement (`scan_2.csv` before `scan_10.csv`) is a one-line key function. A stale-on-PyPI dependency to sort filenames is a bad trade.

4. **Pint *can* represent a "grid frame with no conversion to metres" — and this is a rare case where a package does the modelling for you.** Verified: `ureg.define("[gridframe]"); ureg.define("frame = [gridframe]")` gives a quantity that does arithmetic and `frame→frame` conversion freely, and raises `DimensionalityError` for `frame→m` **and** `m→frame`. That is exactly the required semantics. But: **pint cannot then be made to convert a frame to metres**, even via a `pint.Context` with a transformation — verified `DimensionalityError: Cannot convert from 'frame' ([gridframe]) to 'meter' ([length])`. So the *uncalibrated* case is solved by pint; the *calibrated* case needs a thin layer of your own.

5. **This is corroborated by the vendor, not invented by the legacy system.** OKM's own docs define a scan field's "field length" in **impulses** and its "field width" in **scan lines** ([OKM Scan Analysis](https://www.okmdetectors.com/pages/scan-analysis)). The grid genuinely has no metres in it. The legacy's "grid frame" model is a correct reading of the instrument, not a quirk.

6. **There is no open-source OKM / OKM Rover parser. None.** Confirmed by GitHub repo search (`okm rover`, `okm ground scan`, `ground penetrating radar csv`, `metal detector scan data parser` — all empty or irrelevant), GitHub code search, and web search across OKM's own documentation. The parser must be written from the format spec, and the format is user-configurable in ways that make this harder than it looks (verdict 7).

7. **The OKM CSV is not a fixed schema and the parser must be column-name-driven.** Per [OKM's Export as CSV documentation](https://www.okmamericas.com/blogs/v3ds-documentation/export-as-csv): the *column separator*, *string delimiter*, *decimal separator* (`,` or `.`) and *decimal places* (0–8) are all user-configurable, and — decisively — "**the number and type of available columns may vary from measurement to measurement**". A positional parser will silently mis-read real files.

8. **There is also a reproducibility flag the parser must capture: "Apply Active Modifiers".** Per the same doc, the same scan can be exported raw *or* with Interpolation / Subdivision / Rotational Correction applied. A ground-scan export without that bit recorded is not reproducible, full stop.

9. **`scipy` (already declared) covers ~80% of the "hand-rolled numeric work" the ticket lists.** Verified present and working in 1.18.1: `ndimage.label` (4- and 8-connectivity), the full binary + grey morphology set, `find_objects`, `distance_transform_edt`, `uniform_filter` / `gaussian_filter1d` / `median_filter` / `percentile_filter`, `signal.savgol_filter`, `stats.median_abs_deviation(scale="normal")`, `stats.iqr`, `stats.zmap(nan_policy="omit")`, `optimize.linear_sum_assignment` (Hungarian), `scipy.sparse.csgraph.min_weight_full_bipartite_matching`, `cluster.hierarchy.linkage`, `interpolate.griddata` / `CloughTocher2DInterpolator` / `RBFInterpolator`, `spatial.ConvexHull`. The Hungarian solver and the MAD are *not* things this project needs a new dependency for.

10. **Keep the independent convex-hull oracle. It is load-bearing, not ceremony.** Verified: `scipy.spatial.ConvexHull` (Qhull) raises `QhullError: QH6154 ... Initial simplex is flat` on **collinear** input. A hand-rolled Andrew's monotone chain handles that case and will not raise. So the oracle genuinely covers an input class the production hull cannot. Bonus: verified that Qhull and GEOS (via `shapely`) agree to `rtol=1e-9` on **500/500** random point sets, so a three-way cross-check (legacy oracle ↔ scipy ↔ shapely) is achievable for free.

11. **`jsonschema` does not ship `py.typed`.** Verified on 4.26.0: `(Path(jsonschema.__file__).parent / "py.typed").exists()` → `False`. Under this project's `mypy` config — `disallow_any_explicit = true`, `disallow_any_unimported = true`, `disallow_any_decorated = true` — an untyped third-party library that returns schema-validated data will force `Any` into `src/`, which is a hard error. **pydantic is the only one of the three candidates that plays cleanly here**, and it is already declared, already has the mypy plugin wired (`plugins = ["pydantic.mypy"]` in `pyproject.toml`), and already has `init_forbid_extra`/`init_typed` configured. The legacy's 305-line hand-rolled validator was a defensible call *only* if the constraint was "no dependencies at all" — that constraint does not apply now.

12. **Mutation testing *is* meaningful for this code, but only in a disciplined form — and `pytest-gremlins` ships the right mechanism.** Verified from source: it supports inline `# gremlin: pardon[reason]` suppression for equivalent/untestable mutants, plus `--strict-pardons`, `--gremlin-audit-pardons`, `--gremlin-max-pardons-pct` and `max-pardons` in `[tool.pytest-gremlins]`. For floating-point code the *only* workable policy is: run mutation testing, and require every pardon to carry a written justification with a hard cap on the pardon rate. Do not treat the raw mutation score as a target.

13. **`pytest-gremlins` coexists with `-n=auto`; the AGENTS.md caveat is out of date, but there is a real gotcha.** The v1.3.0 changelog claimed `ERROR: --gremlins and -n (pytest-xdist) cannot be combined`. The current `main` `plugin.py` instead runs a **two-phase mode**: xdist distributes the normal test phase, then the controller runs the mutation phase after xdist tears down. The repo's `[tool.pytest-gremlins] workers = "auto"` is valid — verified in `config.py`, `merge_configs` calls `_resolve_workers()`, which maps `"auto"` → `os.cpu_count()`. Two warts remain: the TOML key is `max-pardons-pct` (dashes) but `max_pardons` (underscore), and `--gremlins` needs `--no-cov` or it piggybacks on pytest-cov.

14. **The "geophysics ecosystem" is a dead end for this project — and that is the most important negative finding.** There is no maintained, PyPI-published, SciPy-adjacent Python geostatistics library for 2D ground-scan raster work. See §5. "Geophysics tooling" here is either (a) a forward/inverse *simulator* for EM/GPR, which is a different problem, or (b) a thin academic wrapper with a 57–93 star GitHub presence and a multi-year release gap. Recommend none of it.

15. **The one real gap in the whole numeric story: exhaustive/global transform search with normalized cross-correlation. No maintained package offers it for 2D rasters.** Verified: `skimage.registration` in 0.26.0 exposes exactly three functions — `phase_cross_correlation`, `optical_flow_ilk`, `optical_flow_tvl1`. There is no global search, no affine grid search, no NCC. `skimage.transform` gives the *transform objects* (`AffineTransform`, `EuclideanTransform`, `SimilarityTransform`, `warp`) but no search. This is build-it-yourself, and that is fine — the algorithm is small.

16. **`statsmodels` has no `Sn` scale estimator and no geostatistics module.** Verified on 0.15.0: `statsmodels.robust.scale` exports `mad`, `iqr`, `qn_scale`, `hubers_scale`, `scale_tau`, `scale_trimmed`, `MScale`, `HuberScale`, `TrimmedMean` — and **no `sn_scale`**. Also verified `pkgutil` over the installed `statsmodels` package directory: modules are `_version, api, base, compat, conftest, datasets, discrete, distributions, duration, emplike, formula, gam, genmod, graphics, imputation, includes, iolib, miscmodels, multivariate, nonparametric, othermod, regression, robust, sandbox, stats, tests, tools, treatment, tsa` — no `geostat`, no `spatial`. If Sn is a requirement, it is ~15 lines (a pairwise-difference median) and is not worth a 20 MB dependency.

17. **`scikit-image`'s `regionprops` already computes `solidity` — but adopting it buys less than it looks and costs a deprecation.** Verified on 0.26.0: `regionprops(mask)[0].solidity` → `0.8889` (= `area` / `convex_area`, 32/36) on a ring-with-a-hole mask. But `RegionProperties.convex_area` emits `FutureWarning: ... deprecated starting in version 0.26 and will be removed in version 2.0. Use RegionProperties.area_convex instead`. With `filterwarnings = ["error"]` in `pyproject.toml`, **a third-party deprecation will break your test suite on upgrade.** It also drags in `networkx`, `pillow`, `imageio`, `tifffile`, `packaging`, `lazy-loader` — six transitive deps for a `numpy`+`scipy` project that already has the morphology it needs.

---

## 2. Package-by-package catalogue

### 2a. Already-declared runtime dependencies — re-evaluation

| Package | Version / last release | `requires_python` | Maintenance | Already declared | Transitive weight | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `numpy` | 2.5.3 / 2026-09-06 | `>=3.12` | Active (repo pushed 2026-10-01, ★15,067) | yes | 0 | **KEEP.** Also the right answer to array storage with non-finite semantics (`.npy`/`.npz` round-trips `nan`/`inf` exactly — verified). |
| `scipy` | 1.18.1 / 2026-08-21 | `>=3.12` | Active (repo pushed 2026-10-01) | yes | 0 | **KEEP, and lean on it hard.** Verified to supply: connected-component labelling, full morphology, background/trend removal filters, MAD/IQR, `zmap`, Hungarian `linear_sum_assignment`, hierarchical `linkage`, `griddata`/`CloughTocher2D`/`RBFInterpolator`, `ConvexHull`. See §4 for the per-item mapping. |
| `pydantic` | 2.13.5 / 2026-08-28 | `>=3.9` | Active | yes | `annotated-types`, `pydantic-core` (Rust), `typing-inspection`, `typing-extensions` | **KEEP and use for validation.** *Removes work*: replaces a hand-rolled validator, gives a typed model, and the mypy plugin is already configured. Under `disallow_any_explicit` it is the only one of {pydantic, jsonschema, hand-rolled} that types cleanly. |
| `orjson` | 3.12.0 / 2026-08-14 | `>=3.10` | Active | yes | 0 | **KEEP for stdout/CLI/logs. NEVER for the frozen artifact contract.** Verified: silently writes `null` for `nan`/`inf`; rejects `NaN` on read. Silent data loss is disqualifying for a scientific contract. |
| `pint` | 0.26.1 / 2026-09-10 | `>=3.12` | Active (repo pushed 2026-10-01, ★2,808) | yes | `platformdirs`, `flexcache`/`flexparser`, `typing-extensions` | **KEEP — it solves the "grid frame" requirement correctly.** Verified: a `[gridframe]` dimension gives free frame↔frame arithmetic and hard `DimensionalityError` for frame↔metre in both directions. But pint will *not* let you convert a calibrated frame to metres; budget your own thin wrapper for that. |
| `rich` | 15.0.0 | — | Active | yes | `markdown-it-py`, `mdurl`, `pygments` | **KEEP** for CLI output. No change. |
| `typer` | 0.27.2 | — | Active | yes | `click`, `annotated-doc`, `shellingham` | **KEEP** for the CLI. No change. |
| `natsort` | 8.4.0 / **2023-06-20** | `>=3.7` | Repo active (pushed 2026-09-19, ★1,013, 13 open issues, 6 open PRs) but **no release in 3+ years**; fixes merged Aug/Sep 2026 are unreleased | yes | 0 | **DROP.** *Removes a dependency and removes risk.* Verified: it works (`natsorted(["scan_10.csv","scan_2.csv","scan_1.csv"])` → `['scan_1.csv','scan_2.csv','scan_10.csv']` vs plain `sorted` → `['scan_1.csv','scan_10.csv','scan_2.csv']`) — but the corpus has no numeric tokens and a documented 6-line key function covers the real case. Choosing a 3-year-stale package for filename ordering is not defensible. |

### 2b. Candidate additions — genuinely recommended

| Package | What it does | Version / last release | `requires_python` | Maintenance | Declared? | Transitive weight | **Removes work or adds it?** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `statsmodels` | Robust scale/dispersion estimators: `mad`, `iqr`, `qn_scale`, `HuberScale`, `MScale`, `scale_tau`, `TrimmedMean` | 0.15.0 / 2026-08-30 | `>=3.10` | Active | no | `patsy`, `formulas` | **ADDS.** Verified `mad` (c=0.6744897501960817) and `iqr` (c=1.3489795003921634) are exactly what `scipy.stats` already gives, and `qn_scale` (c=2.219144465985076) is the only genuine extra. One estimator does not justify 20 MB + 2 deps. **Skip.** |
| `shapely` | GEOS-backed planar geometry: `convex_hull`, `Polygon.area`, robust predicates | 2.1.2 / 2025-09-24 (2.2.0rc1 2026-09-21) | `>=3.10` | Active (pushed 2026-09-29, ★4,516) | no | 1 compiled wheel, no Python deps | **ADDS — but cheaply, and only if you want a second hull.** Verified Qhull≡GEOS to `rtol=1e-9` on 500/500 random sets, so it is a *valid* cross-check but it duplicates the oracle you already have. Only adopt if you also need polygon ops beyond hulls (clipping, buffering, validity repair). Otherwise `scipy.spatial.ConvexHull` + your monotone chain is enough. **Optional.** |
| `scikit-image` | Image analysis: `measure.label`, `measure.regionprops` (incl. `solidity`), `morphology`, `transform` | 0.26.0 / 2025-12-20 | `>=3.11` (classifiers list 3.11–3.14) | Active (pushed 2026-10-01, ★6,601) | no | `networkx`, `pillow`, `imageio`, `tifffile`, `packaging`, `lazy-loader` (+ `numpy`, `scipy` already present) | **ADDS.** You already have `scipy.ndimage.label` + morphology — the only thing scikit-image uniquely buys is `regionprops.solidity`. Cost: 6 transitive deps and a *live deprecation* (`convex_area` → `area_convex`) that `filterwarnings = ["error"]` will turn into a test failure on the next bump. **Skip unless region descriptors (eccentricity, extent, perimeter) become a real requirement** — and if they do, adopt it deliberately with the deprecation handled. |
| `zarr` | Chunked, compressed, versioned N-D array store; handles `nan` natively | 3.4.0 / 2026-09-15 | `>=3.12` | Active | no | `numcodecs`, `donfig`, `crc32c`… | **ADDS, conditionally.** *Removes work* if and only if artifact sizes exceed what `.npz` handles. For field-scan rasters (tens of MB) `numpy.save` is sufficient and already available. **Defer** until a real size problem exists. |
| `msgspec` | Rust-core JSON *and* schema validation; `msgspec.json.decode(..., type=Model)` | 0.22.0 / 2026-09-29 | `>=3.10` | Active | no | 0 (single Rust wheel) | **ADDS — tempting but the NaN behaviour disqualifies it for this job.** Verified via CPython issue #134717: `msgspec.json.encode([nan, inf, -inf])` → `b'[null,null,null]'`, same silent-null trap as orjson. Great library, wrong property here. **Skip for contracts;** consider only if you later want fast *non-contract* validation. |

### 2c. Candidate additions — evaluated and rejected

| Package | Version / last release | Why rejected |
| --- | --- | --- |
| `jsonschema` | 4.26.0 / 2026-01-07 | **Does not ship `py.typed`** (verified). Under `disallow_any_explicit = true` + `disallow_any_unimported = true` + `disallow_any_decorated = true`, untyped imports force `Any` into `src/` = hard mypy error. Adds ~3-4 deps (`rpds-py`, `referencing`, `attrs`, `jsonschema-specifications`). Also slower cadence than pydantic (2026-01 vs 2026-08). pydantic is already declared and already plugin-configured. |
| `simplejson` | 4.1.2 / 2026-08-27 | *Would* preserve NaN via `allow_nan=True`, but it is a C-speedup wrapper over stdlib `json` and adds a dependency to solve a problem `numpy.save` solves better. Only relevant if you must stay in JSON *and* keep NaN. Not recommended; see §4.6 for the better answer. |
| `pyarrow` | 25.0.1 / 2026-08-10 | Parquet is an excellent, deterministic, NaN-preserving array container. But 40+ MB, no need at current scale, and it is not a *contract* format humans can diff. Premature. |
| `h5py` | 3.16.0 / 2026-03-06 | Correct and NaN-preserving, but HDF5 embeds timestamps/CPU-dependent layout in some paths, which fights a golden-hash contract. `numpy.save` is simpler. |
| `scikit-learn` | 1.9.1 / 2026-09-10 | Excellent library, but `scipy` already covers `linkage`/`fcluster` (hierarchical) and greedy matching is `argmin` over a `KDTree`. Adds `joblib`, `threadpoolctl`, `narwhals` for algorithms you mostly do not need. **Skip unless** you need `IsolationForest`/`KMeans`/`DBSCAN` specifically — and even then, prefer `scipy` unless the requirement is genuinely non-hierarchical clustering. |
| `opencv-python` | 5.0.0.93 / 2026-07-02 | `findTransformECC` and `matchTemplate` *are* the exhaustive-affine-search primitives the project needs — but ~60 MB, no stubs for mypy strict, and it pulls in an enormous API surface. A 40-line exhaustive NCC search over a bounded transform grid is a better trade here. **Skip.** |
| `dipy` | repo active (pushed 2026-10-01, ★846) | The one real *candidate* for "exhaustive transform search with a similarity metric": `dipy.align.ima.search_global` does a grid search over affine parameters maximising a structural-similarity metric, and `dipy.align.imaffine` does affine registration. **But** it is a neuroimaging library — its metrics, masking and cost model are tuned for brain MRI, and adopting it for soil EM rasters means fighting its assumptions. It is also effectively unmaintained in practice (846 stars, tiny contributor base). **Skip; build the ~40-line search instead.** |
| `itk` | 5.4.7 / 2026-08-07 | Registration is its core competency, but it is a C++ toolkit with enormous build weight and a Python surface that fights strict mypy. Disproportionate. |
| `nanopandas` | 0.0.dev1 / 2024-02-24 | Pre-release, effectively unmaintained. Not a serious candidate. |
| `pyntcloud` | 0.3.1 / **2022-07-31** | **Abandoned.** Not for a greenfield 2026 project. |
| `welly` | 0.5.2 / **2022-02-28** | **Stale 4 years.** Borehole geophysics, wrong problem. |
| `harmonica` | 0.7.0 / **2024-08-12** | Last release >2 years ago. Potential field-separation, but not maintained. |
| `pygeostat` | 1.2.0 / 2025-06-24, preceded by 2021-11 | Repo `CcgAlanta/pygeostat` (57★). One release after a **4-year gap**. Effectively dormant. |
| `pyGeoStatistics` | (no PyPI release found) | Repo `whimian/pyGeoStatistics` (93★), not published. Same verdict. |
| `simpeg` | 0.25.2 / 2026-03-16 | Maintained, and the reference for EM forward/inverse modelling — but that is a *different problem* from post-processing a measured raster. Huge. Not now. |
| `discretize` | 0.12.0 / 2025-10-09 | Maintained, but finite-volume simulation. Not raster post-processing. |
| `pygimli` | 1.6.1 / 2026-09-18 | Genuinely active. But a full inversion suite for a pipeline that reads already-measured rasters. Not now. |
| `verde` | 1.9.0 / 2026-03-19 | Spatial interpolation for potential-field data. Decent, but `scipy.interpolate` already covers the three interpolators the project needs. Would be a second way to do one thing. |
| `gprMax` | 4.0.0 / 2026-09-14 | Active and the right tool for GPR *simulation*. Note `requires_python: <3.14, >=3.11` — it will block a future 3.14 upgrade. Forward modelling ≠ export parsing. Out of scope for this ticket. |
| `pyfar` | 0.8.1 / 2026-08-14 | Active, acoustics (room impulse responses). Not applicable. |
| `lasio` | 0.32 / 2025-08-01 | The best-maintained borehole-log reader in Python. Useful as a *design reference* for a vendor-format parser (per-curve mnemonic dispatch, header index, depth-indexed records) — **read it, do not depend on it.** |
| `obspy` | 1.5.1 / 2026-08-28 | Active seismology I/O. Read as a parser reference; not a dependency. |
| `xarray` | 2026.9.0 / 2026-09-29 | Genuinely good for labelled gridded data with explicit NaN-aware encodings. But a single-scan raster is an `ndarray`; xarray earns its keep with multi-scan, multi-dimension, multi-attribute collections. **Defer** — revisit when the corpus model has to hold many scans at once. |
| `metpy` | 1.7.1 / **2025-08-29** | Maintained but slow cadence (2025-08, 2025-08, 2025-04, 2025-04, 2024-08). Weather. Not applicable. |
| `scikit-rf` | 2.1.0 / 2026-08-13 | Active RF/frequency-domain. Not applicable to near-field depth scans. |
| `mutmut` | 3.8.0 / 2026-09-12 | **Actively maintained** (this is not the old abandoned mutmut). But: not a pytest plugin, its own README notes Unix/`fork()`-oriented design, and it has no equivalent-mutant governance. `pytest-gremlins` is better integrated with a suite that already uses pytest + xdist + cov. **Do not switch.** |
| `cosmic-ray` | 8.7.0 / 2026-08-09 | Maintained, but heavyweight (git-diff-based, multiprocessing, historically Celery for distribution). Worst ergonomics of the three for a small suite. **Do not adopt.** |
| `MutPy`, `mutatest` | — | Explicitly documented as unmaintained (MutPy: last update 2019, Python 3.4–3.7; mutatest: 2022). **Never.** |

### 2d. Dev tooling verdicts

| Tool | Version / last release | Maintenance | Verdict |
| --- | --- | --- | --- |
| `vulture` | 2.16 / 2026-03-25 | **Active** — repo pushed 2026-09-25, ★4,829 | **KEEP.** Actively maintained and cheap. It does have a known blind spot (dynamic/decorator-based references), so pair it with the `mypy` `warn_unused_ignores`-style strictness the project already has. Note: `vulture` ships **no runtime dependencies**, which is why the missing audit entry is trivially fixable. |
| `deptry` | 0.25.1 / 2026-03-18 | **Active** — repo pushed 2026-10-01, ★1,488 | **KEEP.** The right tool for "declared but unused". Note the 7 × `DEP002` failures are *expected* (deps pre-declared ahead of implementation) — record that as a known-allowlist rather than pretending it is clean. |
| `pytest` | 9.1.1 / 2026-06-19 | Active | **KEEP.** |
| `pytest-cov` | 7.1.0 / 2026-03-21 | Active | **KEEP.** Pairs with coverage 7.16.2 / 2026-09-27. |
| `pytest-xdist` | 3.8.0 | Active | **KEEP** — and now safe alongside `--gremlins` (two-phase mode). |
| `pytest-randomly` | 5.0.0 | Active — repo pushed 2026-09-29, ★722, 3 open issues | **KEEP, but be honest about the cost.** It is genuinely valuable here because it catches hidden inter-test ordering dependencies, which is a real risk for a numerical suite with module-level caches. The cost is that no ordering bug is ever reproducible without `-p no:randomly`. Keep it; make `-p no:randomly` part of the debugging muscle memory. |
| `pytest-timeout` | 2.4.0 | Active | **KEEP** — genuinely important for numerical code, where a degenerate input can hang a test instead of failing it. |
| `hypothesis` | 6.168.3 / 2026-09-28 | Active | **KEEP — but only where it pays.** See §4.7. |
| `pytest-gremlins` | 1.9.0 / 2026-07-01 | Active (young project — treat as such) | **KEEP, with a pardon policy.** See §4.7. |

---

## 3. Prior art: OKM export parsers

### 3a. Direct prior art: none

Exhaustive negative result. Searched:

* `gh search repos "okm rover"`, `"okm ground scan"`, `"okm"`, `"ground penetrating radar csv"`, `"metal detector scan data parser"` — no relevant hits. The only near-match is `mrk7711/Ground-Scanner-System` (Dart, ★0, last updated 2025-12-03) — *"A research-grade ground scanning and anomaly-detection system inspired by OKM Rover devices"* — which is an **inspired-by** project, not a parser, and has zero stars.
* `gh search code "OKM" --language python` — only unrelated substring matches (`okm` inside `mechanika`, `age.py`, etc.).
* Web search across OKM's own documentation.

**Conclusion: the OKM parser is net-new work. Budget for it. Do not go looking for prior art to adapt.**

### 3b. What the format actually is (from OKM's own documentation)

Primary source: [OKM Visualizer 3D Studio — Export as CSV](https://www.okmamericas.com/blogs/v3ds-documentation/export-as-csv), and the [Visualizer 3D Studio changelog](https://www.okmamericas.com/blogs/v3ds-documentation/changelog).

* **Introduced in Visualizer 3D Studio 3.1.1, Professional Edition only.** CSV export exists for Ground Scans, GPR data, and geoelectric measurements. (Standard Edition has no CSV export.)
* **UTF-8** encoded.
* **Everything about the dialect is user-configurable**, which is the single most important fact for parser design:
  * *Column separator* — a single arbitrary character, not necessarily `,`.
  * *String delimiter* — arbitrary, default `"`.
  * *Decimal separator* — `,` **or** `.`. A locale hazard: a comma decimal separator plus a comma column separator is a genuine ambiguity case.
  * *Decimal places* — 0 to 8. So **the file loses precision relative to the instrument**; the parser must not assume full float fidelity.
* **Optional embedded sections**, each independently toggled:
  * *Characteristics* — project title, description, GPS coordinates, **field length and width**, operating mode.
  * *Meta Data* — user-defined scan metadata.
  * *Soil Type* — dielectric constant, relative permeability, mineralization, humidity, homogeneity.
* **Column set is not fixed**: "The number and type of available columns may vary from measurement to measurement."
* **"Apply Active Modifiers" is a semantic fork**: checked = Interpolation, Subdivision, Rotational Correction are applied before export; unchecked = raw values as received from the detector. **A parser must record this bit**, because raw and processed rasters are not the same measurement and the whole downstream analysis is only reproducible if you know which one you got.

Related native formats, from the changelog: the older `*.v3d` scan files, the **OKM Exchange Format `*.okm`** (added in 3.2.1 for the eXp 5500, adapted in 3.3.0 for the eXp 7000), `*.gpr`/`*.nx` (Gepard GPR), `*.geo` (GeoSeeker). None are publicly specified; none have open-source readers.

Also relevant competitive context: **OKM now ships a paid "AI Scan Analysis" feature** (Visualizer 3D Studio 3.4.0, V3DS Credits, requires an internet connection) for 3D ground scans. The vendor is competing with exactly this project's output. It is also an argument *for* deterministic, auditable local analysis.

### 3c. What a robust parser for this domain needs

Drawn from the OKM format above plus the general genre:

1. **Sniff the dialect, do not hard-code it.** Detect the delimiter, the string quote, the decimal mark, and the decimal count from the first records. Do not assume RFC 4180.
2. **Dispatch on column *names*, not positions.** The column set varies by instrument and by mode.
3. **Record provenance explicitly** — instrument, mode, field length (impulses), field width (scan lines), soil type, whether modifiers were applied, decimal places. These belong in the artifact, not in a sidecar.
4. **Be loss-aware.** 0–8 decimal places means the export is already quantized. Do not compare export-derived values against raw instrument values with a tight tolerance.
5. **Treat the grid as a frame grid.** The grid is in impulses × scan lines, not metres. This is the vendor's own model (see verdict 5) and it is the strongest argument for pint's `[gridframe]` dimension.
6. **Design reference worth reading before writing:** `lasio` (LAS 2.0 borehole logs — mnemonic dispatch, header index, per-curve metadata) and `obspy` (SEED — a thoroughly hostile binary/text format family). Neither is a dependency; both are worth an hour of reading for the *shape* of a vendor-format reader.

---

## 4. The specific numeric work: what replaces what

### 4.1 Convex hull / polygon geometry → "solidity" descriptor

**What the legacy did:** hand-rolled convex hull, plus a deliberate *exact independent oracle* using Andrew's monotone chain, specifically so the production hull could be checked against something that shares no code.

**Options evaluated:**

| Option | Status | Note |
| --- | --- | --- |
| `scipy.spatial.ConvexHull` (Qhull) | Available in declared `scipy` | **Fails on collinear input** — verified `QhullError: QH6154 ... Initial simplex is flat`. Handles duplicate points fine. |
| `shapely` (GEOS) | Candidate addition | Verified: agrees with Qhull to `rtol=1e-9` on 500/500 random point sets. One compiled wheel, no Python deps. |
| `skimage.measure.regionprops(...).solidity` | Candidate addition | Verified: returns `area / convex_area` (0.8889 = 32/36) — the solidity descriptor *already implemented*. But costs 6 transitive deps, and `convex_area` is deprecated in 0.26 → will break `filterwarnings = ["error"]`. |
| Hand-rolled monotone chain (existing) | Already exists | ~30 lines, no deps, **handles the collinear case without raising**. |

**Verdict: keep all three that are cheap, and keep the oracle.** The legacy's instinct was right, and the reason is now concrete rather than theoretical: Qhull *raises* on an input class (collinear point sets) that a degenerate ground-scan anomaly can absolutely produce, and that the legacy's oracle handles. The cross-check is not paranoia; it is covering a real behavioural gap.

Concretely: **keep the hand-rolled monotone chain as the production hull** (it is smaller, dependency-free, and total on the inputs that matter), **keep it as the oracle** for whatever you adopt, and treat `scipy`/`shapely` agreement as a *third* independent witness. If you adopt `shapely`, it is for a three-way check, not because you need its polygon algebra. `regionprops.solidity` is worth revisiting only if a richer set of shape descriptors becomes a requirement.

### 4.2 Connected-component labelling and binary morphology

**`scipy.ndimage` — already declared, and complete.** Verified present in 1.18.1:

* `ndimage.label` — with explicit `structure` for 4- vs 8-connectivity. Verified: 4 and 8 both correct on a diagonal test pattern. **This connectivity choice is scientifically load-bearing** (a diagonal-only touch is either one anomaly or two) and must be a named parameter, not a default.
* Binary morphology: `binary_dilation`, `binary_erosion`, `binary_opening`, `binary_fill_holes` — all present.
* Grey morphology: `grey_dilation`, `grey_erosion` — present.
* `find_objects` (bounding boxes per label, without a full pass), `distance_transform_edt` (distance to nearest background — directly useful for an anomaly-core/extent split).

**Verdict: adds nothing if you use this. Do not add scikit-image or OpenCV for this.** The `scipy-stubs` package is already in the dev group, so these are all typed.

### 4.3 Robust scale / dispersion estimators (MAD, IQR, Sn, Qn with a consistency constant)

**Already in declared `scipy`:**

* `scipy.stats.median_abs_deviation(x, scale="normal")` — verified → `1.4826` on `[1,2,3,4,100]`. This is MAD × Φ⁻¹(0.75), i.e. the Rousseeuw–Croux normal-consistency constant, applied for you.
* `scipy.stats.iqr(x)` — verified → `2.0` on the same data. Raw IQR; multiply by 1.349 for normal consistency.
* `scipy.stats.zmap(x, y, nan_policy="omit")` — verified working; note it happily returns `-inf`/`nan`/`inf` when the reference is degenerate. **That is a live bug source**: z-scoring a scan against a local background estimated from a region that happens to be flat produces infinities, which then flow into the serialization question. Gate the scale estimate on a minimum spread.

**In `statsmodels.robust.scale` (candidate addition):** verified exports `mad` (c=0.6744897501960817), `iqr` (c=1.3489795003921634), `qn_scale` (c=2.219144465985076), plus `hubers_scale`, `scale_tau`, `scale_trimmed`, `MScale`, `HuberScale`, `TrimmedMean`.
**Verified absent: `sn_scale`.** Sn is not implemented anywhere in statsmodels 0.15.0.

**Verdict: no new dependency.**

* MAD and IQR → `scipy.stats`, already there, already consistent-scaled.
* Qn → if genuinely required, it is a *pairwise-difference* statistic: `Qn = 1.2218584 · c · nth smallest of |xᵢ − xⱼ|` (the Croux–Rousseeuw constant). A naive O(n²) implementation on a raster is O(n²) in cells and will need a subsample or a `scipy.spatial.KDTree` radius query. This is a *real* implementation task, not a package install — and it is the kind of thing that should be its own ticket with its own test.
* Sn → the same shape of work: `Sn = 1.1926 · c · median(|xᵢ − xⱼ|)`. ~15 lines plus the same O(n²)→KDTree concern.
* If you find yourself wanting `MScale` / `scale_tau` / `scale_trimmed` together, that *is* the moment `statsmodels` earns its weight — but it should be triggered by a requirement, not adopted pre-emptively.

**Design note that matters more than the package choice:** pin and *name* your consistency constant per estimator in the artifact. A "solidity/score" number is meaningless without knowing whether the scale was `1.4826 × MAD` or raw MAD, and this is exactly the kind of thing that a frozen contract should make explicit rather than leave to the reader's memory.

### 4.4 Clustering, including deterministic/greedy variants and hierarchical methods

**Already in declared `scipy`:**

* **Hierarchical:** `scipy.cluster.hierarchy.linkage` (verified: `ward` on a 3-point set gives the expected merge sequence) + `fcluster` / `cut_tree`. This is deterministic, O(n²)-ish memory, and has tie-breaking rules that are stable for a given input.
* **Greedy / deterministic assignment:** `scipy.spatial.KDTree` (nearest-neighbour queries) or, for a greedy one-to-one matching over a cost matrix, `scipy.optimize.linear_sum_assignment` — see 4.5.
* **Connected-component grouping:** `ndimage.label` with an appropriate `structure` *is* a clustering — and for anomaly blobs on a raster it is the *correct* one, because it respects spatial adjacency, which a feature-space clustering does not.

**Verdict: adds nothing if you use this.** Strongly prefer `ndimage.label` (spatial, deterministic, adjacency-aware) over feature-space clustering for blob-shaped anomalies. Reach for `scipy.cluster.hierarchy` when the objects are point-like measurements that need grouping on a feature vector, and for `sklearn` only if a genuinely non-hierarchical algorithm (DBSCAN density clustering, k-means) is a stated requirement.

### 4.5 Linear assignment problem (Hungarian) for one-to-one target matching

**`scipy.optimize.linear_sum_assignment` — already declared.** Verified working on a 3×3 cost matrix, returning the expected row/column index arrays. This is Jonker–Volgenant (a Hungarian-algorithm variant), which is what you want. Also available: `scipy.sparse.csgraph.min_weight_full_bipartite_matching` for a sparse cost matrix, if the target set is large.

**Verdict: this was never a reason to add a dependency, and it is not one now.** The legacy hand-rolled it; `scipy` has had it for two decades. **Delete the hand-rolled implementation.**

Two correctness notes that are easy to get wrong and worth an explicit test:
* **`linear_sum_assignment` requires a finite cost matrix.** A NaN or `inf` in the cost matrix does not raise a helpful error — it produces a silently wrong assignment. Sanitize and validate the cost matrix *before* the call. This connects directly to 4.3's degenerate-scale warning.
* **Rectangular matrices are fine**, and the "rectangular" result (more targets than matches) is the normal case for anomaly-to-hypothesis matching. Make the surplus-handling rule explicit.

### 4.6 Rigid and affine registration, including exhaustive transform search with NCC

**Split this into two halves, because one is solved and one is not.**

**(a) Transform application — solved, no new dependency.** `skimage.transform` would give you `AffineTransform` / `EuclideanTransform` / `SimilarityTransform` / `warp` — but `scipy.ndimage` plus your own 3×3 matrix is a few lines and keeps the dependency count flat. A 2D rigid transform is 3 parameters; affine is 6. Apply with `scipy.ndimage.affine_transform` (or `map_coordinates` for arbitrary displacement fields). Note that resampling is where non-finite values get *invented*: `affine_transform` with `mode="constant"` and a finite `cval` will fill outside-the-field with `cval`; if that is `nan` you have chosen to propagate non-finite data, and if it is `0.0` you have chosen to invent data. **Decide this explicitly per call site.**

**(b) Exhaustive/global transform search with normalized cross-correlation — NOT solved by any maintained package.** Verified on scikit-image 0.26.0: `skimage.registration` exposes exactly `['optical_flow_ilk', 'optical_flow_tvl1', 'phase_cross_correlation']`. `phase_cross_correlation` gives a sub-pixel *translation* only. There is no global search, no affine grid search, no NCC metric. `opencv-python` has `findTransformECC` and `matchTemplate`; `dipy` has `dipy.align.ima.search_global` (a grid search over affine parameters maximising structural similarity) — but dipy is a neuroimaging library tuned for brain MRI with a tiny contributor base, and adapting its cost model and masking to soil-EM rasters is more work than writing the search.

**Verdict: build it. It is small.**

The algorithm is a nested loop over a bounded grid of transform parameters, an NCC evaluation per candidate, and an argmax — roughly 40 lines with `numpy`. Make it **deterministic by construction** (fixed grid, fixed iteration order, no random restarts), because it feeds a frozen contract. Two domain-specific cautions:

* **NCC on a raw anomaly raster is dominated by the background.** If the field is 95% background, the NCC is high for almost every transform and the argmax is noise. Normalize against a *local* background estimate, restrict the search to a region of interest, or NCC only the anomaly mask's bounding box. This is the most likely place for a subtle, silent correctness bug in the whole pipeline.
* **Report the search grid and the NCC score in the artifact.** An exhaustive search that returns a transform without its search space and score is not reproducible.

**If you want a cross-check on the search itself:** `dipy.align.ima.search_global` is the reference implementation to read (docs, not dependency), and `opencv.findTransformECC` is the reference for gradient-based refinement. Reading both is cheap; depending on either is not.

### 4.7 Array storage with non-finite-value semantics

**The question is the serialization question (see §5), and the answer is: do not put non-finite floats in JSON at all.**

**`numpy.save` / `np.savez` — already declared, and verified correct.** Round-trips `nan` and `inf` exactly, bit-for-bit, and is deterministic (fixed-width little-endian by default). Zero new dependencies. **This should be the format for rasters in every frozen artifact.**

If artifacts outgrow one file, **`zarr` 3.4.0 / 2026-09-15** is the right escalation: chunked, compressed, versioned, NaN-preserving, and actively maintained. Not needed yet.

**Verdict: the whole non-finite problem is solved by `numpy` for the array payload. The remaining question is what to do about the *metadata*, and the answer is "do not put NaN in it."**

### 4.8 Unit handling that can represent a "grid frame" with NO conversion factor to metres

This is the most interesting requirement in the ticket, and pint handles it well — with one real limitation.

**Verified behaviour of pint 0.26.1:**

```python
ureg = pint.UnitRegistry()
ureg.define("[gridframe]")
ureg.define("frame = [gridframe] = fr")

q = 12.5 * ureg.frame
q.dimensionality  # -> [gridframe]
q.to("m")  # -> DimensionalityError: Cannot convert from 'frame' ([gridframe]) to 'meter' ([length])
(3.0 * ureg.m).to(
    "frame"
)  # -> DimensionalityError: Cannot convert from 'meter' ([length]) to 'frame' ([gridframe])
(q * 2).to("frame")  # -> 25.0 frame
(q - 1.0 * ureg.frame)  # -> 11.5 frame   (arithmetic works)
```

That is **exactly** the required semantics: a grid frame is a legitimate spatial quantity, arithmetic and same-unit conversion work freely, and it is **type-incompatible with a length in both directions** — the type system, not a runtime check, prevents a frame from silently being treated as a metre. This is the "a unit library must be able to say *this is a frame, not a length*" requirement, satisfied by the library.

**The limitation, verified:** pint will not let you *then* convert a calibrated frame to metres, even via an explicit `pint.Context` with a transformation function — `DimensionalityError: Cannot convert from 'frame' ([gridframe]) to 'meter' ([length])`. Cross-dimension conversion is not a pint feature.

**Verdict: KEEP pint, and it removes real work — but budget a thin wrapper for calibration.** The shape should be:

* A `pint` `[gridframe]` dimension and a `frame` reference unit. Free, correct, and type-safe.
* A small domain type (or a plain validated dataclass / pydantic model) for the *calibration* — "this survey's grid is 4.2 cm per frame" — that owns the frame↔metre relationship outside pint, and is the single place a conversion factor is allowed to exist.
* The conversion itself as one function that takes a calibration and a frame quantity and returns a metre quantity, refusing to guess when no calibration is supplied.

This is strictly better than hand-rolling unit handling, and strictly better than pretending a frame *is* metres with a magic scale factor. **Note the alternative you are rejecting:** defining `frame = 0.042 * meter` in the registry would make every conversion "work" — and would silently let a frame be added to a metre, and would bake one survey's calibration into a global registry. Don't.

One more practical pint note: `ureg.define(...)` calls are **process-local and are forgotten when the program ends** (documented). Put the definition in a module-level registry constructed once, or it will be missing in a fresh process and in the CLI entry point.

---

## 5. Data validation and schema

### The question

The legacy hand-rolled a **305-line stdlib-only JSON-Schema subset validator** to avoid a dependency. Was that the right call?

### Verdict: it was defensible under its actual constraint, and that constraint no longer holds. Use pydantic; do not rebuild the validator, and do not add `jsonschema`.

**The decisive technical fact** is that the project's own mypy configuration makes `jsonschema` a liability. Verified: **jsonschema 4.26.0 does not ship `py.typed`.** Under

```toml
strict = true
disallow_any_explicit = true
disallow_any_unimported = true
disallow_any_decorated = true
disallow_subclassing_any = true
```

a library that is untyped and whose whole purpose is to return dynamically-validated data will force `Any` into `src/`, which is a hard error in this project. You would end up with `# type: ignore[...]` sprinkles or a `cast()` wall — i.e. the hand-rolled validator's typing burden *plus* a dependency. That is strictly worse than either alternative.

| Option | Verdict | Reasoning |
| --- | --- | --- |
| **pydantic 2.13.5** (already declared) | **RECOMMENDED** | Shipped `py.typed`; mypy plugin already configured in `pyproject.toml` (`plugins = ["pydantic.mypy"]`, plus `init_forbid_extra = true`, `init_typed = true`); gives you a *typed model* not just validation, so `src/` gets real types instead of `Any`; can emit JSON Schema when you need to publish a schema; fast (Rust core). **Removes work.** Also: it is the natural place to hang the "grid frame" and "calibration" types from 4.8. |
| `jsonschema` 4.26.0 | **REJECT** | No `py.typed` (verified) → `Any` leakage into `src/` → mypy gate failure. Adds `rpds-py`/`referencing`/`attrs`/`jsonschema-specifications`. It validates *documents*; pydantic validates *and types* your domain, which is what a `py.typed` package needs. Slower release cadence than pydantic. |
| Hand-rolled subset (status quo) | **REJECT for new work** | 305 lines of code that is *itself* a source of bugs, that must be tested to 95% branch coverage, that does not generate types, and that you would have to re-audit for every keyword you decide to support. It was the right call when "no dependencies" was a rule. It is not now. |
| `msgspec` 0.22.0 | **REJECT (for now)** | Genuinely excellent (Rust core, zero deps, validation *and* typing, and much faster than pydantic). Tempting. But its JSON encoder has the same silent NaN→null behaviour as orjson (documented in CPython issue #134717), and it is a new dependency alongside an already-declared, already-configured pydantic. Revisit only if pydantic's validation throughput becomes a measured bottleneck. |
| `fastjsonschema` 2.22.2 | **REJECT** | Actively maintained and fast, but it *compiles* JSON Schema to Python — a generated-code-in-`src/` problem under strict mypy, for the same typing reason as `jsonschema`. |

### What this means concretely

* Model every frozen artifact as a **pydantic model** with `extra="forbid"`, and get the JSON Schema out of it (`model_json_schema()`) if a schema needs publishing.
* Keep one hand-written **JSON Schema** as the *published* contract (generated from pydantic, not hand-maintained) if external consumers need it. Generation avoids the two drifting apart.
* **Do not** keep the 305-line validator in the greenfield path. If the legacy's *schema files* are worth preserving, preserve the schema, not the validator.

---

## 6. Serialization

### The problem, stated precisely

The legacy used stdlib `json` in 63 files, and its golden-hash test contract depended on `sort_keys=True` and `allow_nan=True`. `orjson` is declared. The question: what is a deterministic, non-finite-aware, round-trippable serialization for a frozen scientific contract?

### The `orjson` finding — and why it is disqualifying

Verified on orjson 3.12.0:

```
orjson.dumps([nan, inf, -inf])        -> b'[null,null,null]'
orjson.dumps({"v": float("nan")})     -> b'{"v":null}'
orjson.loads('{"v": NaN}')            -> JSONDecodeError
json.dumps([nan])                     -> '[NaN]'
```

Three separate problems, in increasing severity:

1. **No `allow_nan` switch** — there is no way to ask orjson to emit `NaN`.
2. **It does not raise on `dumps`.** It **silently** writes `null`. This is the disqualifying part. Compare stdlib `json`, which can be configured to *fail loudly* (`allow_nan=False` → `ValueError`) and which round-trips the literal `NaN` token. orjson offers neither loudness nor fidelity — it offers silent lossy coercion. In a frozen scientific contract, a NaN that becomes `null` on disk and then becomes a *legitimate measurement* on load is a data-integrity incident that no test will catch unless you specifically test for it.
3. **It is asymmetric**: it will not read back what stdlib `json` wrote.

`msgspec` has the same silent-null behaviour. `rapidjson` emits `[NaN,Infinity,-Infinity]` but rejects 6 invalid-JSON fixtures. `ujson` raises `OverflowError` on encode. **No JSON library round-trips non-finite floats while also being strict JSON** — because JSON has no representation for them. This is a hard constraint of the format, not a packaging problem.

### The verdict

**Split by payload type. This is the whole answer.**

| Payload | Format | Why |
| --- | --- | --- |
| **Rasters / numeric arrays** | **`numpy.save` / `np.savez` (`.npy` / `.npz`)** | Already declared. Verified exact round-trip of `nan` and `inf`. Deterministic (fixed-width little-endian). Lossless. Bit-for-bit reproducible. **Zero new dependencies.** |
| **Metadata** | **pydantic model → JSON, containing no non-finite floats** | Non-finite measurements belong in the array payload. Metadata (shapes, dtypes, units, instrument, calibration, provenance, search grids, consistency constants) is finite by construction. |
| **Grandfathered machine contracts** (the legacy's NaN-permitting golden-hash tests) | **stdlib `json` with `allow_nan=True, sort_keys=True`** | Keep exactly as-is. Do not migrate. |

**The concrete rule: forbid non-finite floats in metadata at the model layer** (a pydantic validator that rejects `nan`/`inf` in any metadata field), and let the array payload carry them in `.npy`. That turns a hard serialization problem into a modelling rule, and it makes the contract self-documenting.

If you must, for some reason, keep non-finite floats *in* JSON: use **stdlib `json` with `allow_nan=True`** (loud, round-trippable, deterministic under `sort_keys=True`) and mark those artifacts as non-standard-JSON in their own metadata. `simplejson` 4.1.2 is a drop-in alternative with the same semantics if you want the C speedup — but it is a dependency to solve a problem the design fix above removes.

### Is the legacy's two-regime split still the right shape?

**Yes — and you should keep it, but sharpen what goes in each regime.**

The two-regime split (frozen machine contracts grandfathered with NaN; new artifacts strict) is correct and should not be collapsed. The reason to keep it is that a frozen contract cannot change: existing golden hashes encode the exact bytes, so re-serializing them with a different library is a breaking change regardless of correctness. That is a legitimate reason to carry historical debt.

Two clarifications worth making explicit in the design:

* **"Grandfathered" must mean *frozen*, not *unspecified*.** Grandfathered artifacts get a documented, tested reader and a documented rule that they are never re-emitted. New artifacts get a documented rule that they are strict. Anything ambiguous will be discovered in production.
* **The third regime nobody has written down: array payloads.** The legacy had two JSON regimes and no mention of `.npy`. The greenfield design needs to say, in one sentence per artifact kind, which of the three formats above it uses and why. That sentence is the contract.

---

## 7. Natural sort

### The question

The legacy used plain `sorted()` on globbed filenames. `natsort` is declared. Is the need real or speculative? Note the vendored corpus has no numeric tokens in any filename, but real field survey exports plausibly do (`scan_2.csv` vs `scan_10.csv`).

### Verdict: **the need is real but small; `natsort` is the wrong instrument; drop it.**

**The need is real.** Verified behaviour:

```
natsorted(["scan_10.csv", "scan_2.csv", "scan_1.csv"]) -> ['scan_1.csv', 'scan_2.csv', 'scan_10.csv']
sorted([...])                                          -> ['scan_1.csv', 'scan_10.csv', 'scan_2.csv']
```

Plain `sorted()` puts `scan_10` before `scan_2`. Survey operators count lines, so `scan_2.csv` and `scan_10.csv` will both exist, and a lexicographic order that interleaves them is a genuine correctness hazard *if* anything downstream depends on scan order. This is not speculative — it is a predictable failure. (Whether it is a failure *today* depends on whether scan order is load-bearing; that is worth answering explicitly, because if scans are processed independently and identified by filename, order does not matter at all and the whole question evaporates. **Answer that first.**)

**But `natsort` is the wrong tool.** It is the only dependency in this project that is stale on PyPI: last release **8.4.0, 2023-06-20** — over three years. The repository is not dead (last push 2026-09-19; PRs #191, #196, #199 merged in Aug/Sep 2026; 6 open PRs; 13 open issues), but **the fixes are not on PyPI**. Adopting a 3-year-stale package — in a project whose whole premise is a *frozen, auditable scientific contract* — to save roughly six lines of code is a bad trade. It also creates a specific operational hazard: if a PyTorch/Pillow/`setuptools` dependency later pulls a newer `natsort`, you get a behavioural change in filename ordering inside a frozen contract, with no changelog to check.

**What to do instead:**

* **If scan order is not load-bearing** (most likely): use plain `sorted()` and **delete the dependency**. Document in the ingest module that file order is lexicographic and carries no meaning. Done.
* **If scan order *is* load-bearing**: sort on an explicit, documented key extracted from the file — the scan-line index, the survey metadata, or a parsed numeric field — and make the key a required, validated attribute of the input record. Do not infer ordering from a filename at all. This is both smaller than `natsort` and more honest, because it makes the ordering criterion an explicit part of the contract instead of a side effect of a glob.
* Only if you need generic natural ordering across an unpredictable corpus should you reach for a package — and then re-evaluate `natsort`'s release cadence at that time, not now.

---

## 8. Testing infrastructure

### Is the declared set sensible for a scientific/numerical Python project?

| Tool | Verdict | Note |
| --- | --- | --- |
| `pytest` 9.1.1 | **KEEP** | Non-negotiable. |
| `pytest-cov` 7.1.0 + `--cov-branch --cov-fail-under=95` | **KEEP, with a caveat** | Branch coverage is the right setting for numerical code (the branches are the NaN/empty/degenerate guards). A flat 95% gate is a *floor*, not a target — a numerical module can be 95% covered and still be wrong. Do not let the coverage number substitute for property tests. |
| `pytest-xdist` 3.8.0 + `-n=auto` | **KEEP** | Verified compatible with `--gremlins` in two-phase mode. |
| `pytest-timeout` 2.4.0 + `timeout = 120` | **KEEP — arguably more valuable here than most of the rest** | Numerical code can *hang* rather than fail: an O(n²) estimator on a large raster, a non-converging optimization, a pathological `interpolate` call. A timeout converts a hung CI job into a legible failure with a stack. Raise it for the known-slow tests rather than globally. |
| `pytest-randomly` 5.0.0 | **KEEP, accept the cost** | Real value: catches hidden inter-test ordering dependencies, which is a genuine risk for a numerical suite with module-level state. Real cost: no ordering bug is reproducible without `-p no:randomly`. Both are true. Keep the tool, and make the debug flag standard practice. |
| `hypothesis` 6.168.3 | **KEEP, but narrowly** | See below. |
| `pytest-gremlins` 1.9.0 | **KEEP, with a pardon policy** | See below. |

### Is mutation testing meaningful for floating-point numerical code?

**Yes, but only in a disciplined form, and only for the control flow — not for the arithmetic.**

The honest split:

* **Mutation testing is *excellent* for the guard logic** that surrounds the numerics: the empty-raster check, the `scale == 0` guard, the NaN filter, the connectivity branch, the depth-bounds check, the "is this calibration present" branch. These are `if` statements and comparisons, they mutate cleanly, and a surviving mutant there is a real test gap. This is most of the legacy's defensive surface and exactly where mutation testing pays.
* **Mutation testing is *weak* for the arithmetic itself.** An operator that mutates `+` to `-` or `*` to `/` inside a numeric expression will usually produce a *large* result change that any tolerant assertion catches, or a *small* one that a tolerance-based assertion deliberately does not care about. Both outcomes are uninformative: the first is a mutant your tests already kill, the second is a mutant that is arguably equivalent given your tolerance. This is where the "equivalent mutant" noise comes from, and it is why a raw mutation-score target is the wrong goal for a numerical suite.

**The right form, which `pytest-gremlins` supports natively** (all verified in source):

* **Inline pardoning**: `# gremlin: pardon[reason]` to suppress an equivalent or untestable mutant, with a **written** reason. A pardon without a reason is not acceptable.
* **Hard cap on the pardon rate**: `max-pardons-pct` in `[tool.pytest-gremlins]`, or `--gremlin-max-pardons-pct`, or `--strict-pardons` to fail on any pardon. Verified these exist and are enforced.
* **Audit**: `--gremlin-audit-pardons` lists every active pragma with its location, reason, and justification. Run it; that listing *is* the record of which numeric assumptions the suite does not actually test.
* **Do not switch to `mutmut` (3.8.0, actively maintained) or `cosmic-ray` (8.7.0, maintained).** Neither is a pytest plugin, so neither integrates with an existing pytest + xdist + cov suite; and neither has the inline-pardon governance that makes mutation testing viable on numerical code. `MutPy` (2019, Python 3.4–3.7) and `mutatest` (2022) are unmaintained — never.

*Practical note:* the `[tool.pytest-gremlins] workers = "auto"` in `pyproject.toml` is valid (verified: `merge_configs` → `_resolve_workers` maps `"auto"` to `os.cpu_count()`). One wart: the TOML key is `max-pardons-pct` (dashes) while `max_pardons` uses an underscore — an easy typo to make. And run mutation testing with `--no-cov`, or gremlins piggybacks on pytest-cov and the modes interact.

### What does hypothesis give you for numerical algorithms, and what are its real limits?

**What it genuinely gives you:**

* **Edge-case discovery you would not have written.** Shrinking produces a *minimal* counterexample. For a raster descriptor, "the smallest failing input" is often a 1×1 or 2×2 array — precisely the degenerate cases that break morphology, hull, and robust-scale code, and precisely the ones hand-written example tests skip.
* **Metamorphic properties** are where hypothesis is strongest for numerics, and they are tolerance-free by construction:
  * translation invariance — shifting a raster by one frame must not change a translation-invariant descriptor;
  * permutation invariance — reordering the input points must not change a point-set descriptor;
  * monotonicity — increasing every value by a constant must shift a location statistic by exactly that constant;
  * idempotence — labelling twice is the same as labelling once; opening an already-open mask is a no-op;
  * identity — `linear_sum_assignment` on an identity cost matrix returns the identity permutation (this is a *free* exact test of the Hungarian solver with no floating point involved);
  * triangle/area sanity — the convex hull area of a triangle is at least the triangle's own area and at most the bounding box area.

  **These are the highest-value tests in the whole project and they need no tolerances at all.** Prioritise them.

**The real limits — and they are not small:**

1. **Hypothesis's default float strategy excludes NaN and Infinity.** Verified from the docs: `st.floats()` defaults to `allow_nan=None` (exclude) and `allow_infinity=None` (exclude), and "if `min_value` or `max_value` is not None, it is an error to enable `allow_nan`". The Hypothesis tutorial's own worked example is a sort test that fails on `[1.0, nan, 0.0]` and is fixed with `floats(allow_nan=False)`. **This is a double-edged sword for this project**: it is *good* that the default protects you from NaN-ordering chaos, and it is *bad* that a project whose whole data model is concerned with NaN will silently never generate one. You must opt in explicitly, per property.
2. **Tolerances are still your problem.** Hypothesis shrinks toward "human-readable" values but cannot reason about ULP-level differences. A property like "descriptor is within 1e-9 of the reference" either passes or it is flaky-looking; hypothesis has no notion of a legitimate floating-point tolerance. Metamorphic properties avoid this entirely — another reason to prefer them.
3. **`hypothesis.extra.numpy` needs a sub-extra.** `from hypothesis.extra import numpy` requires installing `hypothesis[numpy]`, which pulls `numpy` and `pandas`. **Verify the extra is installed** if you use `arrays()` — this is a classic "works in my head, ImportError in CI" and the project's `pyproject.toml` currently declares plain `hypothesis`. Also note `hypothesis.extra.numpy.arrays(...)` defaults to integer-ish dtypes unless you pass `elements=`; float arrays need `elements=st.floats(allow_nan=False, allow_infinity=False, width=64)`.
4. **Performance and `HealthCheck`.** Hypothesis on a real-sized raster is slow. Constrain `max_side` in your shape strategy, and be ready for `HealthCheck.too_slow` / `filter_too_much`. The project's global `timeout = 120` and `filterwarnings = ["error"]` will surface a `FailedHealthCheck` as an error — which is correct, but means the strategy must be sized deliberately.
5. **It will not find your real bugs.** Hypothesis explores the *input space you described*. If the model of the input is wrong (e.g. you only generate convex blobs when the real failures are in concave ones), hypothesis explores your wrong model perfectly. **Metamorphic properties on realistic fixtures are the complement, not the substitute.**
6. **Determinism and `pytest-randomly` interact.** Hypothesis uses a database keyed by test; combined with random ordering the same test can be run with different `derandomize` behaviour. If a hypothesis test is flaky, check this before blaming the algorithm. Prefer `@settings(derandomize=True)` on the properties you intend to treat as a regression suite.

**Practical recommendation:** use hypothesis for **discrete structural properties** (shapes, connectivity, permutation/translation invariance, exact integer/arithmetic identities) on small inputs, and use **fixture-based metamorphic tests** for anything touching real rasters. Do not try to property-test a floating-point detector end-to-end with tight tolerances.

---

## 9. Dead code and dependency auditing

### `vulture` — is its absence from `audit-requirements.txt` a real gap or an export artefact?

**It is a REAL gap, and it is a stale generated file — not an export artefact.**

Verified with uv 0.12.6:

* Committed `audit-requirements.txt`: **75** packages. `vulture` is **absent**. `deptry`, `hypothesis`, `pytest-gremlins`, `pytest-cov`, `pytest-randomly`, `pytest-timeout`, `pytest-xdist`, `mypy`, `ruff`, `scipy-stubs`, `pre-commit`, `pip-audit` are all **present**.
* Re-running the exact command recorded in the file header (`uv export --no-emit-project --frozen`) produces **76** packages, and `vulture==2.16` is present.
* Full set diff: the **only** difference in either direction is `vulture`. Nothing extra, nothing missing.
* `uv.lock` does contain vulture (`uv.lock:1623`, `version = "2.16"`, sdist uploaded 2026-03-25), and the dev group requires `vulture>=2.16`.

**Diagnosis:** the file was generated before `vulture` was added to the dev group and never regenerated. The command works correctly; the artefact is out of date.

**Consequence:** `pip-audit -r audit-requirements.txt` is not scanning vulture. The practical severity is **low** — vulture is a dev-only AST scanner, it has zero runtime dependencies, and its blast radius is "a developer runs a linting tool." But the *documented* invariant in `AGENTS.md` ("Its contents are currently in sync with `uv.lock`") is **false**, and a false invariant in `AGENTS.md` is the real cost: an agent or developer will trust it and not re-check.

**Fix:** re-run the recorded command. One line, no decisions. Then either correct the `AGENTS.md` claim or — better — add a check that the file is in sync, so it cannot silently rot again. (Note that rot is exactly what happened the last time vulture was added to `pyproject.toml`.)

**Verdict on `vulture` itself: KEEP.** 2.16 / 2026-03-25, repo pushed 2026-09-25, ★4,829, actively maintained. It is the right tool for "unused function/attribute/variable" in a codebase where a linter like ruff's `F401` cannot see cross-module dead code. Two honest caveats: it has a well-known false-positive profile for dynamically-referenced names (pydantic validators, `__getattr__`, typer/click callbacks, entry points), so expect a small allowlist; and `min_confidence = 80` in the current config is a reasonable threshold, but treat its output as a review list, not a build gate, until the false positives are whitelisted.

### `deptry` — verdict

**KEEP.** 0.25.1 / 2026-03-18, repo pushed 2026-10-01, ★1,488, actively maintained. It is the correct and current tool for `DEP002` (declared but unused) and `DEP001` (transitively required but not declared), and its Python-3.13 / `uv`-native behaviour is exactly what this project needs.

On the 7 × `DEP002` currently reported (`natsort`, `numpy`, `orjson`, `pint`, `pydantic`, `scipy`, `typer`): **`AGENTS.md` is right that these must not be "fixed" by deleting the declarations** — the deps are intentionally pre-declared ahead of the implementation. But "don't delete the deps" is not a durable answer for a gate that reports a failure on every run. The durable answer is to encode the expectation: deptry supports per-rule ignores in config, so once the greenfield implementation starts importing a declared dep, its `DEP002` should disappear *naturally*. If a dep is genuinely never going to be used (and my verdicts above say **`natsort` is one of them**), the right move is to remove it, not to suppress the finding.

**One gap worth closing:** `deptry` checks the *declared* dependency set. It cannot tell you that a declared dependency is **unmaintained** — which is precisely the `natsort` problem in §7. A release-cadence check (e.g. `uv list --outdated`, or `pip list --outdated` in a scheduled job) is the missing companion gate, and it is the one that would have caught natsort's 3-year-stale-on-PyPI state automatically.

---

## 10. Gaps where nothing suitable exists

This section is the most important one for planning. Each item is a case where the survey found **no maintained package** that solves the requirement, and the honest conclusion is that the work must be built.

### 10.1 OKM / OKM Rover export parser — **BUILD IT**

No open-source or public parser exists. Confirmed across GitHub repo search, GitHub code search, and web search (§3a). The native formats (`*.v3d`, `*.okm`) are undocumented and have no readers at all.

The difficulty is not the CSV — it is that the CSV is a *user-configured serialisation of a non-fixed schema*, with a decimal separator that may be a comma and a modifier flag that changes the scientific meaning of the values. Budget this as a first-class module with its own fixture corpus and its own adversarial tests (comma-decimal, tab-separated, 0-decimal-places, missing characteristics block, modifiers-applied).

### 10.2 Exhaustive transform search with normalized cross-correlation — **BUILD IT (~40 lines)**

No maintained package offers it for 2D rasters. `skimage.registration` (verified: three functions, translation-only via `phase_cross_correlation`), OpenCV, and DIPY were all evaluated and rejected (§4.6). Build the bounded grid search over the 3 (rigid) or 6 (affine) parameters, with NCC evaluated per candidate and a deterministic argmax. The algorithm is small; the domain care needed around background dominance (§4.6) is the actual work.

### 10.3 Sn and Qn robust scale estimators — **BUILD THEM (~15 lines each)**

Verified: `statsmodels.robust.scale` 0.15.0 has `qn_scale` but **no `sn_scale`**, and nothing else in the surveyed ecosystem implements either at a quality worth depending on. The formulae are short; the real work is the **O(n²) → sub-quadratic** problem, which needs a `scipy.spatial.KDTree` radius query or a documented subsample. This is a genuine algorithm ticket, not a `pip install`.

### 10.4 A "grid frame" that is type-incompatible with length *and* calibratable to metres — **BUILD THE CALIBRATION LAYER (~30 lines)**

Pint 0.26.1 gives you the first half for free and correctly (verified: `[gridframe]` gives free frame arithmetic and hard `DimensionalityError` in both directions against metres). It does **not** give you the second half — verified, pint refuses frame→metre conversion even via an explicit `pint.Context`. So: use pint's dimension, and build a small calibration type that owns the frame↔metre relationship and refuses to convert when no calibration is supplied. This is a case where the package does most of the work and the gap is a thin, well-specified layer on top.

### 10.5 Non-finite-aware, deterministic, round-trippable serialization — **RESOLVE BY MODELLING, NOT BY PACKAGE**

There is no such library, and there cannot be: **JSON has no representation for NaN or Infinity**, so any strict JSON library must either fail or coerce. Verified: orjson coerces silently, msgspec coerces silently, rapidjson emits non-standard tokens, ujson raises. The resolution is a design decision, not a dependency (§6): **non-finite values live in `.npy` array payloads; metadata is finite by construction and validated as such; grandfathered machine contracts keep stdlib `json` with `allow_nan=True`.**

### 10.6 The legacy's exact-oracle pattern for degenerate geometry — **KEEP IT, IT IS NOT VESTIGIAL**

This is a "gap" in the sense that no package provides what the legacy provided. `scipy.spatial.ConvexHull` **raises `QhullError` on collinear input** (verified) — an input a degenerate anomaly can produce. The hand-rolled Andrew's monotone chain handles it, is ~30 lines, has no dependencies, and is genuinely independent of Qhull. Verified additionally that Qhull and GEOS agree to `rtol=1e-9` on 500/500 random point sets, so a three-way check is available for free. **Do not remove the oracle in the name of "reinventing less."**

### 10.7 (Noted, out of scope for this ticket) EM/GPR forward and inverse modelling

`simpeg` 0.25.2 / 2026-03-16, `discretize` 0.12.0 / 2025-10-09, `pygimli` 1.6.1 / 2026-09-18 and `gprMax` 4.0.0 / 2026-09-14 are all genuinely maintained and would be the right tools — for *simulating* or *inverting* EM/GPR data, which is a different problem from post-processing a measured raster. Flagged so the greenfield plan does not accidentally assume they are candidates for the ingest/analysis path. (`gprMax` additionally caps at `<3.14`, which would block a future Python 3.14 upgrade.)

---

## 11. Summary of recommended changes

| # | Change | Rationale |
| --- | --- | --- |
| 1 | **Stop using `orjson` for frozen artifacts.** Keep it for CLI/stdout/logs only. | Verified: silently writes `null` for `nan`/`inf`; refuses to read them back. Silent data loss. |
| 2 | **Adopt `numpy.save`/`.npz` for all raster payloads; forbid non-finite floats in metadata at the model layer.** | Verified exact `nan`/`inf` round-trip. Zero new dependencies. Turns a hard problem into a modelling rule. |
| 3 | **Re-run `uv export --no-emit-project --frozen -o audit-requirements.txt`.** Correct the false "in sync" claim in `AGENTS.md`. | Verified: the committed file is missing exactly `vulture`; regenerating adds it and nothing else. |
| 4 | **Drop `natsort`.** Delete it from `pyproject.toml`; decide explicitly whether scan order is load-bearing and sort on an explicit key if so. | Verified: no PyPI release since 2023-06-20. Repo is alive but fixes are unreleased. 6 lines of code does not justify a stale-on-PyPI dependency in a frozen-contract project. |
| 5 | **Adopt pydantic for all validation; delete the hand-rolled validator from the greenfield path. Do not add `jsonschema`.** | Verified: `jsonschema` ships no `py.typed` → `Any` leakage → fails this project's mypy gate. pydantic is already declared and already plugin-configured. |
| 6 | **Keep `numpy` + `scipy` as the workhorses; delete the hand-rolled Hungarian solver, and use `scipy.ndimage` for all labelling/morphology.** | Verified all present and working in the pinned 1.18.1. |
| 7 | **Keep the convex-hull oracle.** Optionally add `shapely` as a third witness; do not adopt `scikit-image` for `regionprops.solidity`. | Verified: Qhull raises on collinear input (the oracle does not). Verified Qhull≡GEOS on 500/500. `scikit-image` costs 6 deps and carries a live deprecation that `filterwarnings=["error"]` will break on. |
| 8 | **Keep `pint` and define a `[gridframe]` dimension; build a ~30-line calibration layer on top.** | Verified: pint gives the correct type-incompatibility semantics for free, but refuses frame→metre conversion even via a Context. |
| 9 | **Budget four build items as tickets:** the OKM parser, the exhaustive NCC transform search, Sn/Qn, and the calibration layer.** | §10. No maintained package covers any of them. |
| 10 | **Keep `pytest-gremlins` and adopt a pardon policy** (`# gremlin: pardon[reason]`, `max-pardons-pct`, `--gremlin-audit-pardons`). Do not switch to mutmut/cosmic-ray. | Verified: the pardon mechanism is exactly the governance mutation testing needs on floating-point code. |
| 11 | **Narrow `hypothesis` to discrete metamorphic properties on small inputs; use fixtures for real rasters. Verify the `[numpy]` extra is installed.** | Verified: `st.floats()` excludes NaN/Inf by default; `hypothesis.extra.numpy` requires the extra. |
| 12 | **Add a release-cadence check (`uv list --outdated`) alongside deptry.** | deptry finds unused deps but cannot find a dep that is unused *because* it should be removed, nor one that is stale-on-PyPI. That is exactly the natsort failure. |
| 13 | **Do not add any of: scikit-image, statsmodels, shapely (yet), scikit-learn, opencv, dipy, itk, jsonschema, msgspec, zarr, xarray, or anything in the geophysics ecosystem.** | §2c, §5. Each was evaluated; the cost exceeds the benefit at current requirements. |
| 14 | **Update `AGENTS.md`'s pytest-gremlins caveat** — `-n` and `--gremlins` now coexist in two-phase mode; and note the `max-pardons-pct` (dashes) vs `max_pardons` (underscore) key inconsistency. | Verified in `plugin.py` and `config.py` source. |

---

## 12. Sources

**Primary (package metadata, queried 2026-10-01 via PyPI JSON API):** `numpy`, `scipy`, `pydantic`, `pint`, `orjson`, `natsort`, `rich`, `typer`, `scikit-image`, `shapely`, `statsmodels`, `scikit-learn`, `jsonschema`, `hypothesis`, `pytest`, `pytest-cov`, `pytest-gremlins`, `pytest-randomly`, `pytest-timeout`, `pytest-xdist`, `vulture`, `deptry`, `mutmut`, `cosmic-ray`, `zarr`, `msgspec`, `simplejson`, `pyarrow`, `h5py`, `xarray`, `opencv-python`, `dipy`, `itk`, `simpeg`, `discretize`, `pygimli`, `verde`, `gprMax`, `pyfar`, `lasio`, `obspy`, `scikit-rf`, `metpy`, `pygeostat`, `pyGeoStatistics`, `welly`, `harmonica`, `pyntcloud`, `nanopandas`, `fastjsonschema`, `shapely`, `coverage`.

**Primary (maintenance state, queried 2026-10-01 via GitHub REST API):** `scipy/scipy`, `scikit-image/scikit-image`, `shapely/shapely`, `hgrecco/pint`, `SethMMorton/natsort`, `jendrikseipp/vulture`, `fpgmaas/deptry`, `pytest-dev/pytest-randomly`, `nedbat/coveragepy`, `dipy/dipy`, `CcgAlberta/pygeostat`, `whimian/pyGeoStatistics`.

**Primary (source code read):**
* `mikelane/pytest-gremlins` — `src/pytest_gremlins/plugin.py` and `src/pytest_gremlins/config.py` (two-phase xdist mode, `workers = "auto"` resolution, `max-pardons-pct` vs `max_pardons` key names, pardon pragmas).
* `python/cpython` issue #134717 — non-finite serialization behaviour of orjson / msgspec / simplejson / stdlib json.
* `HypothesisWorks/hypothesis` — `src/hypothesis/extra/array_api.py`, `reference/strategies.html`, `tutorial/introduction.html`.
* `pint` — `docs/advanced/defining.html`, `api/base.html` (reference-unit/dimension model, `define` persistence warning).

**Primary (vendor documentation, first-party):**
* OKM — [Export as CSV](https://www.okmamericas.com/blogs/v3ds-documentation/export-as-csv) (column/string/decimal separators, decimal places, optional Characteristics / Meta Data / Soil Type blocks, variable column set, "Apply Active Modifiers").
* OKM — [Visualizer 3D Studio Changelog](https://www.okmamericas.com/blogs/v3ds-documentation/changelog) (CSV export added 3.1.1 Professional Edition; `*.okm` exchange format 3.2.1/3.3.0; `*.gpr`/`*.nx`/`*.geo`; AI Scan Analysis 3.4.0).
* OKM — [Scan Analysis](https://www.okmdetectors.com/pages/scan-analysis) (**field length in impulses, field width in scan lines** — the vendor's own grid-frame model).
* OKM — [Visualizer 3D user manual](https://manualzilla.com/doc/5654281/visualizer-3d---okm-metal-detectors) (control scans, mineralised-ground discrimination, colour filter).

**Primary (upstream docs):** scikit-image `INSTALL.rst` / `pyproject.toml` v0.26.0 (Python 3.11–3.14, dependency set); `scikit-image` `measure` / `registration` / `transform` API; `orjson` README (JSON conformance table); `pytest-gremlins` docs and v1.3.0 changelog (DEV); `CPython json` stdlib docs (`allow_nan`, `parse_constant`); `pint` docs; `hypothesis` strategies reference; `numpy.testing.assert_allclose` (NaN-compares-equal semantics, `equal_nan`).

**Empirical verification** (Python 3.13, isolated venv outside the repo, pinned versions as declared): pint `[gridframe]` semantics and `Context` limitation; `orjson` NaN→null on dump and `JSONDecodeError` on load; `numpy.save` `nan`/`inf` round-trip; `jsonschema` `py.typed` absence; `scipy` 1.18.1 API surface for `ndimage` / `stats` / `optimize` / `cluster.hierarchy` / `interpolate` / `spatial` / `sparse.csgraph`; `statsmodels.robust.scale` contents and absence of `sn_scale`; `statsmodels` module list (no geostatistics module); `skimage` 0.26.0 `regionprops.solidity` = 0.8889 and the `convex_area` → `area_convex` deprecation; `skimage.registration` public API (3 functions); Qhull `QhullError QH6154` on collinear input; Qhull vs shapely agreement on 500 random point sets; `natsort` vs `sorted` on `scan_{1,2,10}.csv`; `uv export` package-set diff against the committed `audit-requirements.txt`.

# R1 — What an OKM device actually measures, and what its documentation says

Target ticket: #20 in `abdoupk/groundscan-analyzer-v2`.
Scope: the CSV that OKM **Visualizer 3D Studio** writes via `File > Export > CSV`, for 3D Ground Scans produced by OKM's Rover / Evolution / Fusion / eXp families.

Every factual claim below is tagged:

| Tag | Meaning |
| --- | --- |
| **[V]** | Official OKM vendor documentation (manual, V3DS docs, official site/page image). Primary source. |
| **[3P]** | Third-party / forum / reseller / mirror. Weaker than [V]; used only for corroboration or to show a doc is mirrored. |
| **[INF]** | My inference. Reasoned from [V]/[3P] evidence. Not stated by OKM. |
| **[UNRES]** | Not found. Described below with what was searched. |

I did **not** find, and did not invent, any statement of OKM's depth-computation formula or of the numeric type of `Scan Value`.

---

## 0. The single most important framing fact

**The CSV is not a device export. It is a software export.**

`File > Export > CSV` lives in Visualizer 3D Studio, not in a detector. The device-to-software channel is a raw flat stream (Bluetooth serial / USB / `.v3d` / `.v3ds` / `.okm`). **[V]**

- V3DS import is a wizard that asks the operator for things the device did not record — the device list, then *operating mode*, then **"Enter the Field Length and select the Scan Mode"**, then **"Enter title and scan field dimensions"**, then **soil type**. Rover C4 import: <https://euro-technologygroup.com/wp-content/uploads/2025/11/OKM-Manual-Rover-C4-EN.pdf> and <https://southafrica.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-C4-202108-EN.pdf> **[V]**; Rover UC: <https://www.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-UC-202209-EN.pdf> **[V]**; generic wizard: <https://www.okmdetectors.com/blogs/v3ds-documentation/importing-3d-scan-data> **[V]**
- The Scan Analysis Guide's "Missing Scan Data" section says the software receives **one flat impulse count** and *redistributes it across scan lines itself*: *"the preset number of impulses per scan line is 30, but the total number of impulses transfered is only 80. These 80 impulses are automatically distributed across the three scan lines as 30, 30, 20 — leaving the final section of the third scan line empty. As a result, the measuring values are shifted within the scan field."* <https://www.okmdetectors.com/cdn/shop/files/OKM-Scan-Analysis-Guide-EN-V1-digital-komprimiert.pdf> §6.5.2, p.42 **[V]**

Consequence for the whole ticket: **every column except `Scan Value` is computed by the software from operator-entered metadata plus a flat accumulator index.** Nothing in the CSV is a position the hardware measured. This is stated by OKM for position in the legacy software manual in unusually blunt terms:

> "To locate the exact position of an object **you have to enter the field length and width at first**." — *Visualizer 3D Software Manual EN (2008)* §5.1.5.1, <https://www.okmamericas.com/cdn/shop/files/OKM-Manual-Visualizer-3D-200810-EN.pdf> **[V]**

---

## What is settled

Short version. Details, sources and caveats per question below.

1. **`Scan Value` has no unit, no declared scale, and is not comparable across scans.** OKM calls it "the actual value detected by the sensor", "the intensity of the signal", and — for the 3D Studio panel — "the **raw** value of the measured data… mostly interesting for support issues". OKM's *own* worked examples span **−78 … +50**, **−1,385.30 … +1,471.83**, and **131,511 … 131,696** in three consecutive examples. **Values can be negative.** It is sign-bearing and represents pole polarity (red = positive/highest, blue = negative/lowest). Ratios-within-one-scan are the only sanctioned use. **[V]**
2. **`Depth Z [m]` is a software estimate, not a measurement.** It depends entirely on the operator-selected soil type; OKM quantifies the error: *"Normally depth differences of about 0,50m are possible."* OKM calls it "the indicated depth is an estimate". The mapping from scan value to Z is **not documented anywhere I could find**. **[V]** for the estimate/soil-type/error claims, **[UNRES]** for the formula.
3. **OKM itself labels the integer columns as an *index* and the metric columns as a separate *unit* representation.** The export dialog groups them literally as `Scan Field Position (Index)` → `Impulse X`, `Scan Line Y`, and `Scan Field Position (Unit)` → `Impulse X [m]`, `Scan Line Y [m]`. **[V]**
4. **The metric columns are divided by (n−1), i.e. the axis is inclusive of both endpoints.** Confirmed by arithmetic on an official OKM screenshot (81 impulses spanning exactly 5,00 m ⇒ step 5/80 = 0,0625 m) and by OKM's own wording for Field Width: *"corresponds to the total distance between the first and the last scan line."* **[INF]**, two independent official artifacts, not stated in prose.
5. **All-zero metric columns are consistent with the operator never entering Field Length/Width.** OKM documents that position is unobtainable until those are typed, and both import wizards require typing them. **[INF]** — mechanism is strongly supported; I found **no user report** confirming it, and no OKM statement about it.
6. **Scan Mode is metadata only.** *"In Characteristics, this information is displayed for reference only. **Changing this option does not affect the graphical representation of your scan result.**"* **[V]** ⇒ the raster is in **raw accumulation order**; the software does not un-mirror Zigzag rows. **[INF]**, high confidence.
7. **The 8-column body is NOT fixed.** The CSV dialog is a checklist of individually tickable columns; the user chooses. OKM: *"you can decide which columns you want to embed… The number and type of available columns may vary from measurement to measurement."* **[V]** ⇒ the product requirement "all in-scope OKM devices share one export structure" is **false as stated**, and additionally the delimiter, string delimiter, decimal separator and decimal places are all user-configurable.
8. **There is no orientation, bearing, grid-direction or start-point field, anywhere, in any OKM software version.** The only carriers are free text: legacy `Remarks` (*"…the distance between impulses, width of measured lines, walking direction"*) and V3DS `Notes` / `Meta Data` (arbitrary name/value pairs, e.g. *"Scan Direction: North-East"*). OKM instructs the operator to *remember and mark the start point on the ground*. **[V]**
9. **Latitude/Longitude are a whole optional group that can be `N/A` or absent.** OKM's own panel shows `Latitude: N/A`, `Longitude: N/A`, and `"Open Google Maps"` is *"only enabled if valid GPS coordinates are attached"*. **[V]**
10. **Soil-type parameters: OKM explicitly says Humidity *"does not affect 3D Ground Scans"* (only GPR).** Dielectric Constant is *"particularly relevant for… GPR"*. Mineralization reduces depth; Homogeneity increases it. OKM does **not** publish the numeric values of its built-in soil types, so the identical-Dielectric/Permeability observation is **[UNRES]**.
11. **No third-party parser exists that I could find.** Q11 is a clean null result.

---

## 1. `Scan Value` — what is it physically?

### Settled

- **"The SCAN VALUE is the actual value detected by the sensor at that specific impulse (measurement point) after modification — if filters were applied. This value indicates the signal strength."** — Scan Analysis Guide §5.5.2, p.29. **[V]** <https://www.okmdetectors.com/cdn/shop/files/OKM-Scan-Analysis-Guide-EN-V1-digital-komprimiert.pdf>
- **"Measuring Values represent the total number of impulses, or scan points… The Scan Value, on the other hand, indicates the intensity of the signal recorded at each specific scan point."** — V3DS FAQ, 2025-11-25. **[V]** <https://www.okmdetectors.com/blogs/videos-tutorials/quick-scan-check-4-faq-3dgs-values>
- **"Scan Value … indicates the **raw** value of the measured data. This value is mostly interesting for **support issues** (and must be enabled in the General Preferences)."** — V3DS docs, Scan Information / Characteristics. **[V]** <https://www.okmdetectors.com/blogs/v3ds-documentation/3d-analysis-scan-information-characteristics>
  - This is the single most load-bearing sentence for our purposes: the vendor positions it as a **diagnostic integer**, not a scientific observable.
- **"The scan values are processed relative to each other in the software."** — Scan Analysis Guide §5.3.3, p.25. **[V]**

### The scale is not stable, even by OKM's own published examples

Scan Analysis Guide §6.4.3–6.4.4 (pp.39–41) gives three worked examples with explicit min/max/average/deviation figures **[V]**:

| Example | min | max | mean | Δ | OKM's verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | −1,385.30 | 1,471.83 | ⌀ 80 | ≈ 1,300 | "clearly distinguishable signature… potential target object" |
| 2 | 131,511 | 131,696 | ⌀ 131,630 | ≈ 93 | "amplitudes are very low given the overall high scan values of >130,000… **questionable** whether real target objects are present" |
| 3 | −78 | 50 | ⌀ −3 | ≈ 64 | "confirms that **no relevant signals** are present… indicates soil mineralization" |

Three consequences, all of them load-bearing:

- **It can be negative.** Examples 1 and 3 both have negative minima. So `Scan Value` is a signed quantity and **not** an unsigned ADC count. **[V]**
- **A Δ of ~1,300 is a strong target; a Δ of ~93 and ~64 are nothing.** The absolute offset and the absolute scale are both irrelevant. **[V]**
- **A scan at "131,630 mean" and a scan at "−3 mean" are the same kind of object.** The 131,000-scale scan in Example 2 is, on the vendor's own arithmetic, *noise* — and the vendor describes it as *"the overall high scan values of >130,000"*. This is **exactly the regime our nine real files live in** (27.5 … 131,000), which is the strongest possible external corroboration that an absolute threshold is meaningless here.

### Sign meaning

- *"A **verified SINGLE SIGNAL** usually indicates one pole of a ferromagnetic object that is vertically oriented: either the **negative** pole that is represented by a **blue** signal (lowest values) or the **positive** pole by a **red** signal (highest values)."* — Scan Analysis Guide §6.3, p.37. **[V]**
- *"The maximum value is displayed as red signal, while the minimum value is shown in blue."* — §5.3.3. **[V]**

So the sign of `Scan Value` is a **polarity** flag (OKM's reading of a dipolar magnetostatic response), and the magnitude is a relative strength. **This corroborates, and does not merely restate, that the value has no physical unit** — it is not a field strength in T/mV/m, and there is no published conversion.

### Is it an ADC count, a computed amplitude, or a dB-like figure?

**UNRES, but the useful negative results are solid.** OKM never says. It is called variously "the raw value", "the actual value detected by the sensor", "the intensity of the signal", and "amplitude" (the word "amplitude" appears only as a *visualization* concept — red/blue colour intensity — and in the "sufficient signal amplitudes" sense of a relative range, never with a unit). **[V]**

Two adjacent facts that bear on the question without settling it:

- `Apply Active Modifiers` on the export dialog: *"Check this option if all active Modifiers (Interpolation, Subdivision, etc.) should be applied before exporting the scan values. If you intend to export **raw scan values, as received from the detector itself**, keep this option unchecked."* **[V]** <https://www.okmdetectors.com/blogs/v3ds-documentation/export-as-csv>
  → **There is an undocumented fork: an export with "Apply Active Modifiers" ticked contains *interpolated / subdivided / corrected* values, not the device's.** Interpolation and Subdivision **generate additional data points** — the V3DS product page says modifiers cause measured values to be *"corrected, extended by additional measuring points and recalculated"*. **[V]** <https://okm-turkiye.com/products/visualizer-3d>
  → **Our nine files' provenance under this flag is unknown and unrecorded in the export.** This is a live reproducibility hazard, not a formality.
- Cross-device comparability is actively broken by the vendor's own product line: V3DS's Scan Information panel for a *3D VLF Scan* (eXp 7000 Pro Plus) shows `Amplitude: 125` and `Threshold: 81` — a different quantity, on a different scale, in a different measurement type. **[V]** <https://cdn.shopify.com/s/files/1/0274/1154/6156/files/v3ds-scan-information-panel.jpg>

### Verdict for the engine

Comparable **within one scan only**, and only in relative terms. Do not threshold absolutely. Do not pool raw `Scan Value` across files; normalise per scan, or better, carry the ordering rather than the numbers. This matches what legacy already did (ratios only) — legacy was right for a reason it did not know.

---

## 2. `Depth Z [m]` — what does the device claim this is?

### Settled: it is a software estimate whose magnitude is set by an operator-chosen soil type

- *"**Depth** … indicates the depth of the selected scan value (blue axis). **The depth value depends on the selected soil type**."* — V3DS docs, Scan Information / Characteristics. **[V]**
- *"Assigning the correct soil type is essential for any depth measurement… All those parameters are **necessary to calculate the approximate depth** of potential targets within the scan images."* — V3DS docs, Soil Types. **[V]** <https://www.okmdetectors.com/blogs/v3ds-documentation/3d-analysis-soil-types>
- *"By selecting the appropriate soil type, **the calculation of the depth values is adjusted** according to the stored soil properties such as dielectric constant, relative permeability, homogeneity, mineralization and moisture. The selection of the correct soil type is essential, as **the calculation of the measurement depth is significantly influenced by it**."* — V3DS product page. **[V]** <https://okm-turkiye.com/products/visualizer-3d>
- **Quantified accuracy**: *"To determine the depth differences are quite possible. The deeper the object is located in the ground the higher can be the variance from the real depth. **Normally depth differences of about 0,50m are possible.** If there is a strong mineralization of the ground higher differences can arise."* — Visualizer 3D Software Manual EN (2008) §5.1.5.2, p.39. **[V]**
- *"**The indicated depth is an estimate**, as it depends on various factors such as soil structure and soil composition. During excavation, the target object may therefore be encountered at a shallower depth than indicated… or it may be located deeper than expected."* — Scan Analysis Guide §5.5.3, p.29. **[V]**
- *"To obtain precise depth values, the object must be positioned in the center of the scan image and be surrounded by normal reference values (neutral ground). If the object is located at the edge… an accurate statement about the depth is not possible."* — Scan Analysis Guide §2 checklist. **[V]** — i.e. depth is a **whole-raster** inference, not a per-point fact.

### Settled: it is not a nominal depth for the operating mode, and not a permittivity-derived depth in the GPR sense

Nothing in any OKM source describes `Depth Z [m]` as a mode constant. It varies per point, per anomaly, per soil type, and per scan field, and OKM's own method section is *geometric*, not physical:

> *"If a **combined red-blue signal** is detected… **place the crosshairs between the two signals**… Based on our experience, this method has repeatedly provided fairly RELIABLE DEPTH ESTIMATES."* — §5.5.3. **[V]**

And in the legacy software the depth readout is literally the Z coordinate of the rendered 3-D point cloud, found by dragging a "line of depth" down to *"the deepest point of the object"*, with *"At this place (deepest point inside the graphic) there is an anomaly of the underground."* — Visualizer 3D Manual (2008) §5.1.5.2, §6.10. **[V]**

**[INF], well-supported:** Z is a *rendering coordinate* that the software assigns to each scan value from its amplitude/sign and the selected soil profile — not an independently sensed depth. The evidence chain: (a) depth requires a soil type, and the soil type is a human selection; (b) depth is read off a rendered 3-D shape whose vertical placement tracks amplitude ("the deepest point of the object", "the measure point whose depth you want to determine"); (c) OKM describes depth as an estimate with a ±0.5 m error that grows with depth and mineralization; (d) no OKM device documents any depth-sensing mechanism, and none exists — these are walked magnetometric measurements, not time-domain instruments. (Note: OKM's **Gepard GPR** *is* a ground-penetrating radar, and for it the GPR soil types and dielectric constant are the relevant physics. Do not transfer GPR reasoning to a 3D Ground Scan.)

### UNRES

**The actual mapping from `Scan Value` to `Depth Z [m]` is not published.** I searched the Scan Analysis Guide (all 28 pages, extracted in full), all V3DS doc pages (Soil Types, Scan Information/Characteristics, Visualization, Modifiers, Changelog), the 2008 Visualizer 3D manual, the product pages, and the downloads index. OKM describes the *inputs* and the *error*, never the *function*. There is no patent, no white paper and no API reference found.

Searched for: depth calculation formula, permittivity depth model, OKM depth algorithm, Visualizer 3D depth equation.

**This is a hard limit.** `Depth Z [m]` must be treated as an opaque, vendor-supplied, device-independent-of-hardware estimate. Any engine that reinterprets it as physical depth will be wrong by ±0.5 m *before* any modelling error, and by more on mineralised ground.

---

## 3. `Impulse X` and `Scan Line Y` — what are they officially defined to be?

### Settled: OKM's own export dialog names them an INDEX, in a group explicitly contrasted with a UNIT

The official **Export as CSV** dialog (Figure 1 of the V3DS docs; I downloaded the image and read it) shows a **Columns** checklist with these groups **[V]** — <https://cdn.shopify.com/s/files/1/0274/1154/6156/files/v3ds-export-csv.jpg>:

```
Columns
  ▣ Scan Field Position (Index)
      ▣ Impulse X
      ▣ Scan Line Y
  ▣ Scan Field Position (Unit)
      ▣ Impulse X [m]
      ▣ Scan Line Y [m]
  ▣ Measuring Values
      ▣ Depth Z [m]
      ▣ Scan Value
  ▣ GPS Location
      ▣ Latitude
      ▣ Longitude            (partially below the scroll fold)
  ▣ Apply Active Modifiers   (unchecked in the published figure)
```

That grouping is the vendor's own classification: the integers are a **grid index**, the `[m]` columns are a **derived metric representation of the same index**. **[V]**

Supporting prose:

- *"**Impulse** … indicates the distance to the starting point (red axis). **Scan Line** … indicates the distance to the right side of the scan area (green axis)."* — V3DS docs. **[V]** (note: "distance" here is loose prose for an index; the diagram caption in the Scan Analysis Guide is explicit — *"The red axis represents the impulses along a scan line, while the green axis represents the scan lines next to each other"* and *"Field Length (Impulses) / Field Width (Scan Lines)"*. **[V]**)
- *"The red axis represents the impulses along a scan line, while the green axis represents the scan lines next to each other."* — Scan Analysis Guide §5.2.1, p.22. **[V]**
- V3DS Visualization docs: axes are *"Red = Length of the scan field (impulses); Green = Width of the scan field (scan lines); Blue = Depth of the scan field."* **[V]** <https://www.okmdetectors.com/blogs/v3ds-documentation/3d-analysis-visualization>
- Legacy software rendered these as **metres**, not integers: the status bar shows *"Scan line : 5,00 m"* and *"Impulse : 1,30 m"*, and *"beginning from your start position you have to walk 5,00 m to the left side and 1,30 m in front"*. — Visualizer 3D Manual (2008) §6.9. **[V]** ⇒ the index→metres conversion is a long-standing *display* feature of the software, which is exactly why a CSV column carrying both exists.

### 0-based or 1-based? — the decisive arithmetic

OKM's own **Scan Information panel** screenshot (a 3D VLF Scan; I downloaded and read it) **[V]** — <https://cdn.shopify.com/s/files/1/0274/1154/6156/files/v3ds-scan-information-panel.jpg>:

```
General      Date / Time:  27.08.2025, 16:35
             Operating Mode: 3D VLF Scan
             Measuring Values:  324
GPS Location Latitude:  N/A      Longitude:  N/A
Crosshairs  Impulse:    17,00 / 81,00      1,00 m / 5,00 m
            Scan Line:   1,00 /  4,00      0,00 m / 5,00 m
            Depth:       N/A
```

- `Measuring Values: 324`, `81,00` impulses-per-line, `4,00` scan lines ⇒ 81 × 4 = **324**. **[V]** Confirms the FAQ's arithmetic convention ("7 lines and 115 impulses per line results in 805"). **[V]**
- Line 1 of the `Scan Line` readout is `1,00 / 4,00` with metric `0,00 m`. A 0-based counter at line 0 would give `0,00 / 4,00`. A 1-based counter at line 1 gives metric 0. ⇒ **the panel displays 1-based and the metric origin is at index 0.**
- The `Impulse` readout is `17,00 / 81,00` with metric `1,00 m` over a 5,00 m field. Now:
  - If `17,00` is the **0-based index**, step = 5,00/80 = 0,0625 m, and 17 × 0,0625 = **1,0625 m** → would display "1,06 m". ✗
  - If `17,00` is a **1-based display of 0-based index 16**, 16 × 0,0625 = **1,0000 m** → displays "1,00 m". ✓ **Exact.**
  - Ratio check: 16/80 = 0,200 = 1,00/5,00 = 0,200 exactly. ✓ **Exact.** (17/81 = 0,2099, which would render 1,05 m.)

**[INF], strong:** the internal grid index is **0-based**, running `0 … n−1`, and the UI displays it **1-based** (`index+1`). The panel's two readings are mutually inconsistent unless index = 16, and consistent if index = 16.

**This does not, by itself, tell us what the CSV column contains.** The CSV column is `Impulse X` under `Scan Field Position (Index)`, and it is not stated whether the exporter writes the raw 0-based index or the 1-based display value. Either way, the metric column satisfies:

```
metric = (Impulse X − b) * Field Length / (n_points − 1),   b ∈ {0, 1}
```

See §"What the sources do NOT settle" for the precise test that would settle `b`.

### 1-based or 0-based on the *device display* (a separate, corroborating data point)

Legacy detector manuals show the on-device counter running from zero:

- *"The display shows the message **"Press Start, L:1, I:0/30"**. As soon as you press the start button… the display shows **"Press Start, L:1, I:1/30"**, which means that 1 of 30 impulses has been measured."* — Rover C II Manual (2009), <https://kuwait.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-C-II-New-Edition-092009-EN.pdf> **[V]**; identical text in the Rover Deluxe Manual (2009) <https://okm-usa.com/cdn/shop/files/OKM-Manual-Rover-Deluxe-New-Edition-v4-200910-EN.pdf> **[V]**
- Same `L:1, I:0/25` / `L:2, I:0/25` pattern in the Rover Gold and 3D Ground Navigator 2.0 manuals. **[V]** <https://rojmd.okmdetectors.com/cdn/shop/files/OKM-Manual-3D-Ground-Navigator-2-201903-EN.pdf>

Note the asymmetry inside one string: **L (scan line) is 1-based, I (impulse) is 0-based.** `I:0/30` then `I:1/30`. **[V]** This is strong evidence that at least one of the two counters is 0-based, and it is the along-line one. It also independently corroborates `b = 0` for the impulse index. **[INF]**

### "Is the convention documented, or inferred?"

**Inferred.** No OKM document states a base for `Impulse X` or `Scan Line Y` in the export. The evidence above is all circumstantial-but-strong. Legacy's admission that it could not tell is honest, and legacy was right to be unsure — but the vendor evidence now points firmly at **0-based internal index, 1-based display**.

---

## 4. `Impulse X [m]` and `Scan Line Y [m]` — is it `Field Length / (n − 1)`?

### Confirmed, by two independent official artifacts. Not documented in prose.

**(a) The Scan Information panel arithmetic (above).** 81 impulses, field 5,00 m, `I = 17,00 → 1,00 m`. Only `L/(n−1)` reproduces that exactly. `L/n = 5/81 = 0,06173` gives 1,049 for index 17 and 0,988 for index 16 — neither is 1,00. **[INF from [V] image]**

**(b) OKM's own definition of Field Width.** *"The FIELD WIDTH is related to the number of scan lines and **corresponds to the total distance between the first and the last scan line**."* — Scan Analysis Guide §5.1.1, p.21. **[V]**

The distance between the first and last of `n` lines is spanned by `n−1` intervals. That sentence is, read literally, a statement that the axis spans `0 … Field Width` inclusive — i.e. step = `W/(n−1)`. **[INF from [V] prose]**

**So: the axis is inclusive of both endpoints, and the divisor is (n−1), not n.** Both of your competing hypotheses are now decided, and the answer agrees with what the nine real files already show.

*Note the field-length sentence is weaker*: *"The FIELD LENGTH corresponds to the length of the scan lines and is directly related to the number of impulses recorded."* — it says "length of the scan lines", not "distance between first and last". By parallel construction it means the same thing, and the panel arithmetic settles it, but if you want a single citable sentence, the **Width** one is the one that says "inclusive". **[V]**

### Why the columns look measured but are not

Because the software *converts* them. The conversion is `index × step`, where `step` comes from **operator-typed** `Field Length`/`Field Width`. The device has no idea how long a metre is. Three official statements nail this:

1. *"To locate the exact position of an object **you have to enter the field length and width at first**."* — Visualizer 3D Manual (2008) §5.1.5.1. **[V]**
2. *"The more accurately the length and width are defined, the more reliably the position and size of potential targets can be determined."* — Scan Analysis Guide §5.1. **[V]**
3. V3DS warns that a wrong impulse count silently *shifts every value within the field* — because the grid is a software construct. **[V]** §6.5.2.

A real measurement would not degrade when you mistype the field size. This one does.

### When are they all `0.0000`? — mechanism confirmed, user report not found

**Your prior is correct.** Mechanism: `metric = index × (FieldLength / (n−1))`. If the operator left `Field Length` / `Field Width` at 0 — or the export was taken from a measurement where those were never entered — the divisor is 0 or the field value is 0, and every metric column is exactly `0.0000` while the index columns remain correct. **[INF]**, strongly supported by [V] §0 above.

Supporting procedural facts, all **[V]**:

- Both import wizards make field dimensions a **required operator step**: *"Enter the Field Length and select the Scan Mode, then click Next"* and *"Enter title and scan field dimensions"* (Rover C4); the same two-step pattern for Rover UC.
- Legacy V3DS also made it a required dialog field: `Field length` / `Field width` in the Characteristics dialog, *"Essential information are not only length and width of your measured field… **Only with these values you can determine the correct position and depth of objects.**"* — Visualizer 3D Manual (2008) §4.4.2.6. **[V]**
- OKM documents that users **can and do get this wrong**, with the consequence named: *"If you are using the predefined number of impulses, this number defines how many values will be recorded in each scan line"* — wrong counts shift everything. **[V]**

**Caveat, stated plainly:** I found **no OKM documentation and no forum/forum-thread user report** that says "metric columns are 0.0000 when the operator never entered the field dimensions". The mechanism is inferred from the documented formula and the documented mandatory-entry workflow; the specific failure is not attested. Do not record this as a vendor claim.

### A related, documented failure worth knowing about

The **"Missing Scan Data"** case (§6.5.2, [V]) is *not* the same thing and must not be confused with it: there, the index and metric columns are populated but the **raster is misaligned** because the software distributed a wrong number of impulses across the lines (80 impulses spread as 30/30/20 instead of 30/30/30). A detector for "last scan line is short / the row count doesn't divide evenly" would catch that; it is distinct from all-zero metrics.

---

## 5. `Field Length` and `Field Width` — what do they mean?

**Settled [V]** (Scan Analysis Guide §5.1.1 and §5.1, p.20–21; V3DS Characteristics):

- *"The **FIELD LENGTH** corresponds to the length of the scan lines and is directly related to the number of impulses recorded. It is either set before starting the scan or, when using Auto mode, at the end of the first scan line."*
- *"The **FIELD WIDTH** is related to the number of scan lines and corresponds to the total distance between the first and the last scan line."*
- Diagram captions: **Field Length (Impulses)** / **Field Width (Scan Lines)**.
- *"The scan field size is — unlike what is common in graphic design — always defined as **SCAN FIELD LENGTH FIRST, then width**. This is based on the fact that the length of the first scan line is set first. The number of scan lines is determined afterwards, which defines the scan field width."*

So yes: **Field Length = extent along a scan line (the red axis), Field Width = extent across scan lines (the green axis).** They are the two side lengths of the scanned rectangle, entered by the operator, in metres or feet depending on the global `Measurement System` preference (*"The units can be switched between metric (m) and imperial (ft) via Main Menu > Extras > Preferences > Measurement System."*). **[V]**

**Does the device lay out points inclusive of both ends?** Yes — see §4. `W/(n−1)`, both endpoints reached. **[INF]**, confirmed.

**Caution on units [V]:** the metric columns are labelled `[m]` and OKM says the *display* unit is switchable. Whether the **CSV exporter** honours the preference or hard-codes metres is **UNRES** — the column header says `[m]`, which is weak evidence it is always metres, but I found no explicit statement.

---

## 6. `Scan Mode` and `Impulse Mode`

### Scan Mode: exactly two values, and it is inert metadata

Values: **Parallel** and **Zigzag**. **No third value. "Linear" is not an OKM term** — the closest is "Parallel". **[V]**

- *"**Parallel**: This scan mode is used to scan all scan lines into the same direction. So you will scan the first path to its end and then come back to the starting point without further scanning. Now you step to the left and scan the next path."*
- *"**Zigzag**: This scan mode is used to scan all scan lines in zigzag style. Here you will scan the first path to its end, then you step to the left and you scan the second path in reverse."* — Rover C4 Manual §5.1.1 step 5. **[V]**

Same definitions, verbatim, in the 3D Ground Navigator 2.0, Rover UC v3, Future 2018 and Fusion manuals. **[V]** Consistent across the whole line.

### What Zigzag means for the exported coordinates — the decisive point

> *"In Characteristics, this information is displayed for reference only. **Changing this option does not affect the graphical representation of your scan result.**"*
> — Scan Analysis Guide §5.1, p.20. **[V]**

**[INF], high confidence:** because toggling Scan Mode provably does not change the raster, **the software does not use Scan Mode to un-mirror (reverse) alternate rows.** The stored grid is therefore in **raw accumulation order** — impulse index always counts 0,1,2,… along the direction of travel, regardless of which way the operator walked that line.

Corroborating, and it also explains why the legacy zigzag correction was even needed:

- OKM documents a **Zigzag-specific artefact**: *"Vertically striped signal structures are usually caused by **ROTATIONAL ERRORS**. … In both Parallel and Zigzag mode, the probe must always point in the same direction as in the first scan line. If this is not maintained, rotational errors can occur in the scan image."* Remedies offered: repeat in Zigzag correctly, repeat in Parallel, **or apply the `Rotational Correction` modifier**. — §6.5.4, p.43. **[V]**
- The reference case study (p.52) shows a scan *declared* Parallel that was *actually* walked Zigzag producing vertical striping, fixed by re-scanning. **[V]**

That the vendor ships a dedicated rotational-correction filter and documents a zigzag-only striping artefact is coherent only if the raster is not geometrically corrected for walking direction.

- Direction of the raster relative to the field: *"every scan always starts on the **bottom right** corner of your scan area. Starting from this point, you should walk scan path by scan path, whereby every following path is situated on the **left** side of its previous path."* — Rover C4 / 3D Ground Navigator / Future 2018 / Fusion manuals, and the 3D Ground Scan Guide. **[V]** Corroborated by the Scan Analysis Guide's Top View note: *"the starting point is located in the bottom right corner."* **[V]**

### Impulse Mode: exactly two values, and it does not change the data

Values: **Automatic** and **Manual**. **[V]**

- *"**Automatic**: Each measure value will be recorded automatically and continuously without any break."*
- *"**Manual**: One measure value will only be recorded after you have pressed the button."* — Rover C4 Manual §5.1.1 step 4. **[V]**
- Rover UC: *"Automatic: All scan values will be recorded continuously line by line without any break. Manual: Every single scan value will only be recorded by pressing the Trigger."* **[V]**
- 3D Ground Scan Guide: *"Large even or passable surfaces are commonly measured in the automatic mode. The manual impulse mode is mainly used for difficult uneven terrain, areas where there is quite a bit of growth and if the measurement result needs to be very accurate."* **[V]** <https://kuwait.okmdetectors.com/cdn/shop/files/OKM-3D-Ground-Scan-Guide-202108-EN.pdf>

**Impulse Mode is a trigger policy, not a data transform.** It changes *where* the operator stood when each sample was taken, not *what* was recorded. It therefore matters for **survey accuracy**, not for file interpretation. All nine real files declaring `Automatic` is unremarkable and consistent with the manuals' recommendation.

---

## 7. `Operating Mode: 3D Ground Scan` — what is it, and what else exists?

`3D Ground Scan` is OKM's walked **magnetostatic** survey mode: *"The operating mode '3D Ground Scan' provides a graphical measurement of any area for analysis on a computer."* — Rover C4 Manual §5.1. **[V]** The whole family works *"on the principle of Electro-Magnetic Signature Reading (EMSR)"* **[V]** — **not** ground-penetrating radar. Rover C4 supports it with either the Standard Probe or the higher-resolution Super Sensor. **[V]**

Alternatives in the same software **[V]**:

| Mode | Where documented | Notes |
| --- | --- | --- |
| **Mineral Scan** | Rover C4 / Rover Gold manuals; V3DS changelog | Super Sensor only; imported as `Operating mode = "Ground Scan"`, `Scan mode = "Zig-Zag"`, **`Impulses = "2"`** — i.e. **it masquerades as a 2-impulse ground scan** |
| **Pinpointer** | Rover C4 §5.2 | Single-object discrimination, post-GS localisation |
| **Magnetometer** | Rover C4 §5.3 | Acoustic ferrous detection; pre-scan clearance tool |
| **Tunnel Scan** | V3DS changelog (`Visualization of Mineral and Tunnel Scans`) | |
| **Thermo Scan** | V3DS changelog | |
| **3D VLF Scan** | V3DS ≥3.3.0, eXp 7000 Professional Plus | Has extra Target-ID Zone data; `Amplitude`/`Threshold` on a wholly different scale |
| **Gepard GPR 3D** (`*.gpr`) | V3DS changelog | Real GPR; separate physics |
| **GeoSeeker** (`*.nx`), **Geoelectric** (`*.geo`) | V3DS changelog | Different instruments entirely |

**Critically for us [V]:** the Mineral Scan case is a documented, vendor-endorsed way to get an export whose header says `Operating mode: 3D Ground Scan` while the data is a 2-impulse-per-line trace. So `Operating Mode` in the header is **not** a reliable filter for "this is a raster". Column counts and per-line point counts must be validated independently.

Also **[V]**: the export dialog's own filename example is `…\Visualizer 3D Studio\Tunnel - Original Scan.csv` — OKM's own screenshot demonstrates a non-ground-scan export.

---

## 8. The `Soil Type` section

The six keys — `Title`, `Dielectric Constant`, `Relative Permeability`, `Mineralization`, `Humidity`, `Homogeneity` — correspond 1:1 to the fields of the V3DS Soil Type Dialog, and are emitted only when the operator ticks the **Soil Type** checkbox in the export dialog. **[V]**

OKM's stated effect of each on depth, from the Scan Analysis Guide §5.4.1, p.27 **[V]** — this is the best statement OKM publishes:

| Parameter | OKM's stated effect | Applies to a 3D Ground Scan? |
| --- | --- | --- |
| **Dielectric Constant** | *"a measure of the conductivity of electric fields. The higher the value, the lower the depth penetration. This is **particularly relevant for scans with the Ground Penetrating Radar (GPR)**."* | **Probably minimal.** Qualified as GPR-relevant; for EMSR ground scans it is at best weakly used. **[INF]** |
| **Relative Permeability** | *"PERMEABILITY is the measure of the conductivity of magnetic fields. The higher the value, the lower the depth penetration."* | Yes — magnetic conductivity is on-axis for a magnetostatic instrument. **[INF]** |
| **Mineralization** | *"defines the metal content of the soil. Higher mineralization reduces the detection depth."* | Yes. **[INF]** Corroborated: *"If there is a strong mineralization of the ground higher differences can arise"* (2008 manual). **[V]** |
| **Humidity** | *"Higher HUMIDITY values of the soil reduce the depth performance of GPR, **but do not affect 3D Ground Scans**."* | **NO — explicitly inert.** **[V]** |
| **Homogeneity** | *"defines the compactness of the soil. Higher homogeneity increases the detection depth."* | Yes. **[INF]** |

Note the explicit carve-out for **Humidity**. That is the sharpest available statement that the soil-type block is a **union of parameters for several measurement technologies (GPR and magnetostatics)**, not a uniform set of five live inputs. A fourth field is inert for our modality.

**A documented inconsistency between two official OKM sources, on Relative Permeability:**

| Source | Description |
| --- | --- |
| Scan Analysis Guide §5.4.1 **[V]** | *"PERMEABILITY is the measure of the **conductivity of magnetic fields**."* |
| V3DS Soil Types page **[V]** | *"In electromagnetism, permeability is the measure of the **magnetization that a material obtains in response to an applied magnetic field**."* |

These are different (and both loose) statements. The Guide's is an effect statement, the doc page is a definition. **I do not resolve this**; note it and do not build on either wording. The German V3DS page carries a *third*, different wording for Dielectric Constant (*"Die Dämpfung des Ausgangssignals führt zu einer Dämpfung der Amplitude"*), so the EN/DE drift is real. **[V]**

### Why Dielectric Constant and Relative Permeability carry identical values — UNRES

**I could not find any OKM statement about this, and I will not guess a mechanism.**

OKM does **not publish the numeric parameters of its 12 OKM Standard Soil Types** — the values are only visible in the running application (as a hover tooltip: *"The parameters of the predefined soil types are displayed as tooltip when hovering the mouse over the individual soil types"*, and in the PDF Report under Soil Type Information **[V]**). So I cannot check whether OKM's own library ships identical values, and I cannot tell whether your files are reading one shared field twice, or genuinely two equal numbers.

What I can say without inventing anything **[V]**: for EMSR ground scans the dielectric constant is documented as GPR-relevant, so **a single shared value stored under both labels would be observationally indistinguishable from two equal ones**, given that the depth formula is unpublished in any case.

Searched for: OKM soil type tables, built-in soil parameter values, dielectric constant list, the source of the built-in library. Nothing published. **This needs either a licensed V3DS install to inspect the library, or a reply from OKM support.** Do not encode a rule that collapses the two fields on the strength of a guess.

**Engineering-safe fallback:** carry both values, provenance-tag them, and do not let the depth path depend on distinguishing them — which it provably cannot, since the formula is unpublished anyway.

---

## 9. The `+++ Section +++` structure and the 8-column body

### Section grammar

**UNRES as to the grammar itself.** No OKM document describes the `+++ Section +++` container format. This is a V3DS **CSV-export** artefact (introduced in **3.1.1**, Professional Edition, per the docs banner and the V3DS changelog **[V]**), and OKM documents only *which checkboxes produce which content*, never the serialisation.

What is documented **[V]**:
- **Characteristics** checkbox → *"embed your individual project information (title, description, GPS coordinates, field length and width, operating mode)"*.
- **Meta Data** checkbox → *"include all your individual Meta Data in the exported CSV file"*.
- **Soil Type** checkbox → *"embed additional information regarding the selected soil type (dielectric constant, relative permeability, mineralization, humidity, homogeneity)"*.
- Separator / string delimiter / decimal separator / decimal places are all user-chosen. UTF-8 encoding.
- **`Apply Active Modifiers`** — a fifth, separate toggle affecting the values themselves.

So the three sections in your files correspond to three independently-ticked checkboxes, and **the format's variability is by design**.

### Are the 8 columns fixed? **No. This is the most consequential finding in the ticket.**

The official Export as CSV dialog is a **checklist**. Columns are individually tickable and untickable. Every column is optional. **[V]** (image, §3 above; and prose: *"you can decide which columns you want to embed into the resulting CSV file. **The number and type of available columns may vary from measurement to measurement.**"* **[V]**)

Corollaries, each from **[V]**:

- A perfectly legal export can have **0** of `Impulse X [m]`/`Scan Line Y [m]`, **0** of `Latitude`/`Longitude`, **0** of the header sections, and can use `;` as separator, `"` as delimiter, `,` as decimal separator.
- The dialect is **user-configurable**: column separator, string delimiter, decimal separator, decimal places (0–8). Your eight-column/`.`-decimal/`4`-place corpus is *one configuration*, not the format.
- `Apply Active Modifiers` changes the *values*, not the columns — so two files with byte-identical headers can contain fundamentally different data. Unrecorded in the export. **Provenance hazard.**

### Do other OKM models / devices / firmware versions produce different column sets?

**Yes, by official design — and for at least three independent reasons, all [V]:**

1. **Operator choice.** Same device, same firmware, different tick boxes ⇒ different columns. Universal across every model.
2. **Measurement type.** *"The number and type of available columns may vary from measurement to measurement."* The docs' own examples span a 3D Ground Scan and a Tunnel Scan. Gepard GPR / GeoSeeker / Geoelectric are separate file types (`*.gpr`, `*.nx`, `*.geo`) with their own CSV columns — the changelog records *"CSV export for GeoSeeker now shows **correct start depth**"* and *"CSV export for Ground Scans, GPR data and Geoelectric measurements"*, i.e. **one CSV exporter serving at least three different data models.**
3. **Scan Mode is not stored by some detectors.** *"With detectors such as the Rover C4, **the correct scan mode must be selected during the file transfer**."* **[V]** So the same physical instrument, transferred through different software versions, yields different header content.

Also **[V]**: the **OKM Exchange Format (`*.okm`)** is a *different, separately-evolving* container — *"Import of OKM Exchange Format (*.okm) as used by OKM eXp 5500"*, later *"OKM Exchange Format (*.okm) adapted for the OKM eXp 7000"*. **It was changed specifically to accommodate a new device.** That is the vendor's own precedent for a shared format breaking per device.

### Verdict on the product requirement

> "all in-scope OKM devices share one export structure"

**This is false, and it is false in the vendor's own documented design.** What *is* defensible: *for a 3D Ground Scan exported with the default/all-ticked settings from V3DS ≥ 3.1.1, the eight named columns are the expected set.* Anything stronger is not supportable.

The right shape for the engine is a **column-set validator with an explicit tolerance list** (the F1 ticket's framing), where every tolerated deviation carries a defined meaning — not a fixed 8-column assertion.

---

## 10. Orientation and georeferencing

### Settled: OKM records **no** orientation, bearing, grid direction, azimuth, or start-point, in any version of any of its software.

**Visualizer 3D Studio (current) — the Characteristics dialog has exactly:** Project Title, Notes, Scan Mode, Field Length, Field Width, Latitude, Longitude, Scan Field Overlay (an operator-supplied photo), Soil Type, Meta Data (free-text name/value pairs), AI Scan Analysis result. **[V]** No bearing field. The only orientation-adjacent carrier is Meta Data, whose own documentation example is *"**Scan Direction:** North-East"* **[V]** — an arbitrary string in an arbitrary user-defined key.

**Visualizer 3D (2008) — the Characteristics dialog has exactly:** Title of project, Remarks, Field length, Field width, Soil type. **[V]** <https://www.okmamericas.com/cdn/shop/files/OKM-Manual-Visualizer-3D-200810-EN.pdf> §4.4.2.6. No GPS, no orientation. The only carrier was `Remarks`: *"In this field you can enter additional information like the distance between impulses, width of measured lines, **walking direction** and others."* **[V]** — i.e. orientation was, and is, **operator free text**.

### OKM explicitly tells the operator the file cannot tell them

> *"Now you may see that it is **important to remember the exact location of your starting point**. Note this information always in the information dialog… Additionally it is advised to **place a little marking on the ground where your starting point is situated**."*
> — Visualizer 3D Manual (2008) §5.1.5.1. **[V]**

And on the required perpendicular control scan:

> *"A further control scan should be performed from the side, **rotated by 90°** relative to the original scan."* — Scan Analysis Guide §4.1. **[V]**
> *"**ROTATE THE SCAN IMAGE if you scanned from a 90° angle.**"* — Scan Analysis Guide, Evaluation checklist. **[V]**

Both instructions only make sense if the file does not carry orientation. The second one, especially: if orientation were stored, V3DS could rotate it; instead the operator must rotate the image **by hand**.

### Orientation as *field technique* — and the trap in it

OKM *does* discuss direction, but only as a **technique recommendation**, never as a recorded quantity **[V]**:

> *"Experience shows that scans in north–south (or south–north) orientation produce better scan image results. If you can, follow the natural magnetic field of the earth when measuring."* — 3D Ground Scan Guide, rule 2; Scan Analysis Guide §"ALIGN SCAN LINES IN NORTH–SOUTH DIRECTION". **[V]**
> *"the more stable the natural magnetic field of the earth when measuring, i.e. ideally perform your scan by walking your scan lines parallel to the meridians (longitudes)."* — V3DS blog, "How to Achieve Best 3D Scan Images". **[V]** <https://www.okmdetectors.com/blogs/videos-tutorials/how-to-create-best-scan-images>

**This is the trap.** N–S is recommended *because of the Earth's magnetic field*, and OKM elsewhere reasons about magnetic polarity and dipolar response. It would be easy to over-read it as a convention attaching North to an axis. It is not. There is **no documented statement anywhere that `Impulse X` points North, or that scan lines are oriented to the meridians**. The axes are unambiguously named only as *"the red axis"* and *"the green axis"* / *"the starting point is in the bottom right corner"* — a **scan-local** frame. **[V]**

### Georeferencing

- Latitude/Longitude are an **optional group**, applied at the **scan-field level, not per point** (Characteristics dialog: *"Enter the GPS Latitude of your scan area to mark its position for Google Maps"* **[V]**). They are one position for the whole rectangle.
- *"This button [Open Google Maps] is only enabled if **valid GPS coordinates are attached** to the current measurement."* **[V]** ⇒ the common state is "not attached". OKM's own published panel shows `Latitude: N/A`, `Longitude: N/A`. **[V]**
- The Rover UC app has a **Settings > GPS** menu (§5.6.4 **[V]**), so *some* devices can attach a position — but nothing documents it as a per-sample or oriented georeference, and no export format for it is documented.
- OKM's guidance on GPS is archival, not analytical: *"ADD GPS LOCATION INFORMATION — Whenever possible, record GPS coordinates of the scan field. This helps precisely **relocate** the scan field, supports documentation…"* **[V]** — *"relocate"*, i.e. find it again. Not *"orient"* or *"register"*.

### Verdict

**Orientation must come from the operator.** It is absent from the file, absent from every OKM software version documented, and OKM's own documentation assumes its absence. Any coordinate-frame decision must treat the scan-local frame as the *only* frame the file can supply, and must require orientation as an external input. The legacy registration code's 8-member transform family and its filename-based orientation guess were correct responses to a genuine absence, not a workaround for missing implementation.

---

## 11. Third-party parsers

**None found. Clean null result.**

Searched:

| Where | Query | Result |
| --- | --- | --- |
| GitHub repository search API | `okm rover detector ground scan` | 0 results |
| GitHub repository search API | `okmdetectors` | 0 results |
| GitHub repository search API | `ground scan detector data csv parser treasure hunting` | 0 results |
| GitHub code search API | `"Scan Line Y" "Scan Value"` | HTTP 401 — requires auth, **not searched** |
| grep.app code search API | `Scan Line Y` | 50 hits, **none OKM-related** (Leptonica, JTS, OpenEXR, POV-Ray — all coincidental) |
| searchcode.com API | `Scan Line Y Impulse X` | endpoint returns 404 (service retired) |
| Web search (6 queries) | `github OKM Rover csv parser`, `"Scan Line Y" "Impulse X" OKM csv`, `"Measuring Values" OKM parse python`, `v3d v3ds reverse engineering`, `"Visualizer 3D" OKM csv to python / qgis`, `OKM Rover CSV export sample file download forum` | nothing |

**The one near-miss is a name collision, not a hit:** `jaromirnyklicek/OkmExportParser` (Packagist, GitHub) is a parser for *Komerční banka*'s Czech bank-statement `.okm` "OKM (BEST KB)" format. Entirely unrelated. Worth noting so the next agent does not re-find it and mistake it for evidence. **[3P]** <https://github.com/jaromirnyklicek/OkmExportParser>

Also checked and **negative**: `convert.guru`'s V3D page describes OKM `.v3d` as *"highly proprietary"*, *"locked to specific rendering engines"*, with no working converter — i.e. third parties have **not** cracked it. **[3P]** <https://convert.guru/v3d-converter> (low-quality SEO content; cited only for the absence of any working tool.)

### What this means

The premise of question 11 — that "third-party parsers are often the highest-value source" — **does not hold for OKM.** Nobody outside OKM appears to have published a parser or a reverse-engineered description of either the `.v3d`/`.v3ds` format or the CSV export. Every fact in this document therefore comes from OKM's own documentation, and the inferences are labelled as such.

**Practical consequence:** there is no independent oracle for the format. Where OKM is silent (the depth formula, the base of `Impulse X` in the CSV, the soil-type tables, the reason Dielectric == Permeability), there is no third party to ask. Those must be settled by a licensed V3DS install (export a controlled scan with a known geometry and read the numbers) or by OKM support — or they stay UNRESOLVED, and the engine must be built not to need them.

---

## What the sources do NOT settle

Explicit list. Each item says what I searched. **None of these should be guessed at.**

### A. The `Scan Value → Depth Z [m]` mapping function
- Searched: full text of all 28 pages of the Scan Analysis Guide; V3DS docs (Soil Types, Scan Information/Characteristics, Visualization, Modifiers, AI Scan Analysis, Changelog); Visualizer 3D Manual (2008), all 51 pages; V3DS product pages; downloads index. Web searches for a depth formula, permittivity model, algorithm, patent.
- Not found in any form. OKM publishes the *inputs*, the *error* (±0.5 m typical, worse with depth and mineralization) and the *interpretation heuristic* (read the crosshairs between a red and a blue lobe), never the equation.
- **Do not model it.** Carry `Depth Z [m]` as opaque, vendor-reported, and flag it as such.

### B. Whether the CSV's `Impulse X` / `Scan Line Y` are written 0-based or 1-based
- The evidence (§3) says the **internal index is 0-based** and the **UI displays 1-based**, but nothing states what the exporter writes.
- Precise test that would settle it: take a scan with a **known, deliberately non-symmetric** grid — e.g. 100 impulses over exactly 10.00 m — export it, and read `Impulse X [m]` at the row's first line. If it is `0.0000`, the exporter writes 0-based; if `0.1000`, 1-based. A symmetric even-N scan cannot distinguish these, which is precisely why legacy could not tell.
- Until then: `metric = (Impulse X − b)·L/(n−1)`, `b ∈ {0,1}`, and treat `b` as a detected-per-file property if you can, or as an assumption with a stated failure mode.

### C. The all-zero-metric case as an *attested* failure mode
- The mechanism is strongly inferred (§4) but **no OKM document and no user report** states that omitting field dimensions yields `0.0000` metric columns.
- Needs: a controlled export with Field Length/Width set to 0, or a reply from OKM support.

### D. The values of OKM's built-in soil types, and whether Dielectric Constant and Relative Permeability are one field or two
- OKM does not publish the tables; they are visible only as an in-application tooltip and in the PDF Report. (§8)
- I did **not** guess a mechanism for the observed identical values.

### E. Whether the CSV exporter honours the metric/imperial preference or always writes metres
- Column headers say `[m]`; the display-unit preference is switchable; no statement either way. (§5)

### F. Whether `Apply Active Modifiers` was ticked on any of the nine real files
- Not recorded in the export, by design. The nine-file corpus may already be a mix of raw and interpolated/subdivided data — which would also change the point count and therefore change the metric axis. **[V]** that this toggle exists and changes the values; **UNRES** which state our files are in.

### G. The `+++ Section +++` grammar as a specification
- Undocumented. I can enumerate what each checkbox contributes (**[V]**) but not the serialisation rules, section ordering, escaping, encoding edge cases, or whether sections may repeat.
- Note the docs say UTF-8 and offer a string delimiter because *"if one of the selected column contains the character that has been chosen as column separator, any external program interprets this as the end of the column"* — so **the delimiter can appear inside values** (titles, notes, soil-type names, meta data). Any parser must handle that.

### H. Whether any OKM model, device or firmware writes a *different column set* for 3D Ground Scans specifically
- Settled that the set is operator-choosable for every device (**[V]**), and that the exporter spans at least three data models (ground scan / GPR / geoelectric) with a documented past bug in one of them (**[V]**).
- **Not** settled: a device-specific *mandatory* deviation from the 8-column ground-scan set. The Rover C4's operator-supplied Scan Mode (§9) is the closest documented candidate and affects the header, not the columns.
- Settled for *other* operating modes: Mineral Scan masquerades as `Operating mode: Ground Scan` with `Impulses = "2"`; 3D VLF Scan adds Target-ID data.

### I. Per-point GPS
- Latitude/Longitude are scan-field-level and optional. **[V]** Nothing found on per-point positioning. The Rover UC has a `Settings > GPS` menu **[V]** with no documented export semantics.

### J. Any absolute calibration, transfer function, or sensitivity spec for the EMSR sensor
- OKM publishes *probe* specifications for some products — e.g. the Fusion manual lists *"Sensor technology SCMI-15-D, Coil technology SRIS-18K, Sample rate 1024 values/second, Measurement resolution 6 bit"* **[V]** — but that is the **Live Sound search coil**, not the ground-scan measurement path, and I found **no** corresponding specification for the 3D Ground Scan sensor, and none linking any spec to the `Scan Value` numbers.
- **Do not** carry "6 bit" or "1024 values/second" across to `Scan Value`. They are different subsystems.

### K. Whether `Scan Value` sign/magnitude flips with probe orientation
- OKM documents that probe rotation produces artefacts and ships a `Rotational Correction` modifier **[V]**, which implies sign sensitivity to probe direction. **Not documented**: whether the exported raw sign is probe-frame or scan-frame. This is the deepest remaining hole under question 6 and it bears directly on the zigzag/reversal decision.

---

## Practical summary for the coordinate tickets

| Column | Physical status | Provenance | Safe use |
| --- | --- | --- | --- |
| `Scan Value` | Signed, unitless, **software-supplied relative amplitude**; range varies by ~4 orders of magnitude between scans | Device, then optionally modified by V3DS modifiers | Relative/ordinal **within one scan** only. Never an absolute threshold. Never pooled raw across files. |
| `Depth Z [m]` | **Software estimate**, soil-type dependent, ±0.5 m typical | V3DS, from operator-selected soil type + unpublished formula | Opaque, vendor-reported, provenance-tagged. Never presented as verified physical depth. No engine-derived depth from it. |
| `Impulse X`, `Scan Line Y` | **Grid index**, not a distance | V3DS, by re-segmenting the flat device stream | The raster frame. Internally 0-based (§3); exported base **UNRES** (B). |
| `Impulse X [m]`, `Scan Line Y [m]` | **Derived**, `index × L/(n−1)`, inclusive of both ends | V3DS, from **operator-typed** Field Length/Width | Fine as a *scale*, once the `(n−1)` divisor and the 0-or-1 offset are handled. All-zero ⇒ field dimensions were never entered (§4). |
| `Field Length`, `Field Width` | **Operator-asserted** rectangle extents | Human, typed into the import wizard / Characteristics | The only source of scale. Must be validated, never trusted. |
| `Scan Mode` | Inert metadata; **not** used to un-mirror | Human (Rover C4) or device (newer) | Header info only. Raster is in **raw accumulation order** — correct for zigzag if you mirror; **do not** mirror Parallel. |
| `Impulse Mode` | Trigger policy | Human | Survey-accuracy metadata. No effect on file interpretation. |
| Soil type block | Partly live, partly inert (**Humidity explicitly inert for 3D GS**) | Human | Carry for provenance. Do not model depth from it. |
| `Latitude`, `Longitude` | Optional, scan-field-level, usually absent/N-A | Human, rarely | Not a georeference. Not per-point. Orientation must come from the operator (§10). |
| **Orientation / bearing** | **Does not exist in the format** | — | **Must be supplied externally.** The legacy 8-transform family + filename guess was the correct response to a real absence. |

### The one sentence to carry forward

OKM's own documentation calls `Scan Value` *"the raw value of the measured data… mostly interesting for support issues"*, calls the depth *"an estimate"* with ±0.5 m error, calls the position something you can only get *"if you have to enter the field length and width at first"*, and instructs the operator to *"remember the exact location of your starting point"* and *"place a little marking on the ground where your starting point is situated."*

**Everything the file gives you about position, depth and orientation is an assertion by the operator, laundered through the software.** That is the finding that unblocks the coordinate tickets — and it is not a guess. It is what the vendor's own documentation says.

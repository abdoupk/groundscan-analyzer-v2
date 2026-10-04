# R4 — Does OKM documentation state how a scan's impulse count or spacing is determined?

Target ticket: [#48](https://github.com/abdoupk/groundscan-analyzer-v2/issues/48) in `abdoupk/groundscan-analyzer-v2`.

Predecessor note: [`okm-device-and-export.md`](okm-device-and-export.md) (ticket #20). That note established that the CSV is a **Visualizer 3D Studio software export**, that `Impulse Mode` is a **trigger policy with exactly two values**, that the **software receives one flat impulse count and redistributes it**, and that `L/(n−1)` is the metric-coordinate arithmetic. **Nothing below re-derives any of that.** This note answers only the four questions #48 opened.

Every claim carries a tag:

| Tag | Meaning |
| --- | --- |
| **[V]** | Official OKM vendor documentation, read in the artifact itself. Primary source. |
| **[INF]** | My inference, reasoned from [V] evidence. Not stated by OKM. |
| **[UNRES]** | Not found. Named searches and artifacts are listed. |

---

## The short answer

**A software-side layout rule is documented, quantified, and reproducible. A device-side sampling rule is not published — with one exception, in one model family.**

OKM states plainly that the software discards whatever real spacing existed and lays the flat count on a uniform grid, and the current software **computes the resulting spacing and gates it at 25 cm**. That part is closed.

What is *not* published is the number that would let you go the other way — from a realised lattice back to a distance. OKM asserts that automatic mode fires at a *predefined speed*, never says what it is, and for exactly one model family (**eXp 4500 NT**) publishes a density (**6 impulses per metre**). For every other device generation, the count is an **operator selection or an operator outcome**, transcribed by hand into the software.

There is also a **per-generation difference of the first order**, which #48 predicted would be the highest-value outcome if it existed. It exists: in the newest devices the impulse-count parameter **does not exist at all**.

| Gap | Answer |
| --- | --- |
| **1 — device-side sampling rule** | Asserted as existing ("predefined speed"), **never quantified**. One exception: **eXp 4500 NT = 6 impulses/metre**, stated twice. Sample rates are published per device but **never linked to the impulse count**. |
| **2 — per-version sweep** | **Three distinct operator-facing contracts across three generations.** The newest generation (Rover UC 2022, eXp 5500 Pro 2024) has **no impulse-count parameter and no count in the import wizard**. eXp 4500 Professional **is** the one manual that states a metric density. |
| **3 — operator influence on the count** | **Total and documented.** `Impulses` is a first-class operator parameter with a published choice list `10, 20, …, 200` (or `Auto`), factory default **20**; `Impulse Mode` factory default **Automatic**. |
| **4 — does `Missing Scan Data` imply an expected count?** | **Yes, and the expectation is operator-supplied, not a software constant.** "Preset" in the Scan Analysis Guide means *preset on the device*. The operator must transcribe the count into the transfer dialog. |

---

## Gap 1 — the causal, device-side question

### 1a. A signal sample rate *is* published for some generations — and never connected to the impulse count

Read from the technical-specification tables, verbatim **[V]**:

| Artifact | Section | Sample rate | Measurement resolution | Sensor |
| --- | --- | --- | --- | --- |
| Rover C4 manual, 2021-08 / 2025-11 | §2.1 *Control Unit*, p.7 | `Sample rate  1024 values / second` | `Measurement resolution  16 bit` | `SCMI-15-D` |
| 3D Ground Navigator 2 manual, 2019-03 | §2.1 *Control unit*, p.14 | `Sample rate  1024 values / second` | `Measurement resolution  16 bit` | `SCMI-15-D` |
| **Rover UC manual, 2022-09** | §2.1 *Telescopic Probe*, p.7 | **`Sample rate  240 values / second`** | **`Measurement resolution  15 bit`** | `SCMI-15-D` |
| Rover UC product page | Technical Specifications | `Samples: 240 per second @ 15 bit` | — | `SCMI-15-D` |
| Rover C II manual, 2009-09 | §3.1 *Control unit*, p.22 | **absent** | **absent** | `SCMI-15-D` |
| Rover Deluxe v4 manual, 2009-10 | §3.1, p.22 | **absent** | **absent** | `SCMI-15-D, VLF` |
| eXp 4500 NT manual, 2020-05 and 2021-07 | §3.1, p.36 (both revisions) | **absent** | **absent** | `TCFX-01-A` |
| eXp 5500 Pro manual, 2024-11 | §9.1, p.63 | **absent** | **absent** | `SCMI-15-D` |

Product pages for **Rover C4, Fusion Light, Fusion Pro, Evolution NTX** all carry `Sample rate: 1024 values / second` and `Measurement resolution: 16 bit`; the **eXp 5500** product page carries **neither** **[V]**.

> The following technical indications are medial values. During operation small variations are quite possible. Technical changes due to development are possible!
> — Rover C II (2009) §3, p.22; the same sentence appears verbatim in every manual in the table **[V]**

**[UNRES], a discrepancy to carry forward not resolve:** the predecessor note records the **Fusion manual** listing `Measurement resolution 6 bit` alongside `Sample rate 1024 values/second`, while the **Fusion product page** today says `16 bit`. I did not open the Fusion manual and cannot say whether that is a manual revision, a different subsystem in the same table, or an error. **[V]** for both figures, at those two locations; the reconciliation is not mine to make.

**[INF], load-bearing:** these are **signal-acquisition** specifications for the control unit's DSP. No document in any artifact I opened states any relation between a sample rate and an impulse. Multiplying 1024 values/s by a line duration to get an impulse count would be an invention. The 2009 manuals replace the sample rate with a **capacity** instead — `Data memory (control chip)  about 32700 measured values` **[V]** — which is an upper bound on how many values a scan could hold, not a rule for how many it emits.

**Do not carry "1024 values per second" / "240 values per second" / any `N bit` figure into a model of the lattice.** They describe a different subsystem from the one that lays out scan lines, and they are not even self-consistent across OKM's own artifacts.

### 1b. OKM names the automatic cadence, and never quantifies it

Two independent official sources, and they are the closest OKM comes to a device-side rule **[V]**:

> In this way the scan points (impulses) are **not collected in the predefined speed**, but only whenever you press the button on the probe / control unit. This ensures similar distances between the measuring points (grid).
> — *How to Achieve Best 3D Scan Images*, OKM blog, 2020-10-07, Tip #11 "Advantages of the Manual Mode"

> In Impulse Mode Manual, impulses are not recorded automatically at the **preset intervall**. Instead, a scan value is only collected when you press the button on the probe or Control Unit. This gives you **FULL CONTROL OVER WHEN SCAN VALUES ARE RECORDED** and helps you keep similar distances between impulses, resulting in a more even scan grid and more reliable scan images.
> — *Scan Analysis Guide* §4.4 *Consider Manual Impulse Mode*, p.17

The operative word in both is **speed** / **intervall**, not *distance*. OKM asserts a predefined automatic cadence exists, and gives **no value, no units, no owner**. Note also that `intervall` is spelled that way in the source.

**[INF], the causal statement this ticket was after:** OKM's own framing is that automatic mode is a **temporal** cadence and the metric spacing is an **emergent property of the operator's walking speed** over that cadence. That is why every field-procedure document says *"walk slowly and evenly"* and *"on the basis of these acoustic signals you can coordinate your walking speed"* — the acoustic beep on each emitted impulse is the only pacing instrument the operator gets.

Confirmed as procedure, Rover C II (2009) p.57 **[V]**:

> As soon as you press the start button **the measure values will be recorded continuously**. You will hear the acoustical signals via the integrated speakers or the headphones. **On the basis of these acoustic signals you can coordinate your walking speed.**

And the same in the newest flagship, eXp 5500 Pro (2024-11) §5.5.2, p.30 **[V]**: *"Walk parallel to your first scan line and at the same speed. **The impulse sound should stop at the end of the line.**"*

### 1c. The one published device-side density: eXp 4500 NT, 6 impulses per metre

**This is the only metric sampling density stated in any OKM document I reached** **[V]**, and it appears **twice** in the same section, in two successive manual revisions:

> **Field Length (Auto, 5 m, 10 m ..., 50 m)**
> Number of measured values per search line (**the eXp 4500 uses 6 impulses per meter**). If you select "Auto", the number of impulses can be adapted to the current length of your search line. During the first line the device will read values regularly without stopping. When you want to finish your first line you have to depress the multifunction control knob to stop the measuring process of the current line. The device will store the number of impulses and use it for all further scan lines on the same scan. By selecting the value 5 m, 10 m, 20 m, …, or 50 m you can preset the distance or the number of impulses you need in one measured line.
> — eXp 4500 NT manual, §7.1.1 *New Ground Scan*, printed **p.49** — identical text and page in both the v2 (2020-05) and the 2021-07 revision

> – In the Automatic mode, the eXp 4500 will take the measurements automatically as predetermined in the "Field Length" selection.
> – In the Manual mode, the eXp 4500 will record a measurement point only when using the Joystick or by depressing the Power Switch. **The eXp 4500 uses 6 impulses per meter.**
> — eXp 4500 NT manual, printed **p.50** (2021-07 revision; **p.50** in the v2, 2020-05 revision — same pagination)

Arithmetic: `6 impulses/m ⇒ 1/6 m ≈ 16.7 cm` between impulses. That lands **inside** OKM's own recommended band (§1d), which is a strong internal consistency check on the figure. **[INF]**

Two scoping caveats, both load-bearing:

- It is stated for **one model family**, the eXp 4500 / 4500 NT, which uses a different sensor (`TCFX-01-A`, *Dual Geophysical Phase Reader*) from the `SCMI-15-D` used by the Rover and eXp 5500 lines. It does **not** transfer.
- The parameter is a **length**, not a count: `Auto, 5 m, 10 m …, 50 m`. Count = 6 × length. The operator never sees a count on this device.

### 1d. Everything else is field technique, not a rule

All **[V]**, all recommendation:

| Source | Statement |
| --- | --- |
| *Scan Analysis Guide* §3.4 *Ensure High Scan Accuracy*, p.13 | "The distance between scan lines and impulses should be consistent to avoid gaps or overlaps. **SMALLER DISTANCE BETWEEN IMPULSES — ideally 15 to 20 cm (6 to 8")** — further increases the precision of the scan image" |
| eXp 4500 NT §8.2.2, pp.74–75 | "**A preferable distance between two impulses is about 15 cm to 30 cm.** The smaller the distance between two impulses is, the more exact the graphical representation will be." |
| eXp 4500 NT §7.1, p.48 | "**Start with a scan that has an impulse approximately every 30 to 60 cm (1 to 2 ft)** forward and to the sides. Do not go too detailed on the first scans until you have a possible anomaly." |
| *3D Ground Scan Guide*, *Major Rules* rule 5, p.15 | "Move the probe at the same speed! … In Automatic mode, the speed of the probe during a scan line must remain the same. **The distance between the impulses must be the same.**" |
| *3D Ground Scan Guide* §2.3 *Scanning Speed*, p.8 | "Using different walking speeds throughout the scan lines will cause **displacements within the scan field**. As a matter of fact, a potential target can get cut into several small pieces or completely lost because it was missed out." |
| *Scan Analysis Guide*, "Know the expected size of your target object", p.7 | "If you are looking for large target structures such as tombs, tunnels, or treasure chests, you can **increase** the distance between impulses and scan lines. For small objects … collect more scan data by **reducing** the distance between impulses and scan lines." |

Note that the **three numeric bands are mutually inconsistent** — 15–20 cm, 15–30 cm, 30–60 cm — and each is scoped to a different purpose (precision, general, first-pass reconnaissance). The two remaining rows carry no number at all. **None of this is a specification.** **[INF]**

### 1e. The pedometer: present, documented, and never connected

The Rover UC spec table (2022-09, p.7) lists **[V]**:

```
Compass    Yes
Pedometer  Yes
```

and the manual devotes a whole subsection to it — §5.1 *Activity Screen* and §5.1.1 *Pedometer Reset*, pp.14–15 **[V]**:

> This screen shows your **steps taken (pedometer function)**, current heart rate and the current direction the detector is heading to (compass function).
> … You can reset the pedometer at any time by clicking the reset icon … After confirming the pedometer will start counting beginning at 0.

Also: *"If Smartwatch or Smartphone is not connected via Bluetooth and the detector is switched on, the Rover UC can be used as trekking pole with pedometer and compass."* **[V]**

**No OKM document I opened connects the pedometer to scan sampling.** It is documented purely as an operator-activity feature. A stride- or wheel-triggered impulse cadence is the natural mechanism for *"the distance between the impulses must be the same"*, and the hardware to do it is on the device — but **the link is nowhere in the documentation.** Record this as **[UNRES]**, not as a mechanism.

### Verdict on Gap 1

**A device-side sampling rule that could be applied to an arbitrary scan is unrecoverable from public OKM documentation.** Three reasons, in order of force:

1. OKM states a predefined automatic cadence exists and **publishes no value for it in any artifact reached** (§1b).
2. The one device that publishes a metric density publishes it for **its own model only** (§1c), and the newest flagship devices publish **no sampling spec of any kind** (§1a).
3. Everything else in the corpus is **recommendation**, in three mutually inconsistent numeric bands (§1d).

What **would** change this, concretely: (a) a firmware release note, which OKM does not publish in text form anywhere I could reach (see *Not reached* below); (b) a written reply from OKM support or a dealer to the question *"what is the impulse cadence of the Rover C4 in Automatic mode?"*; (c) a bench measurement — walk a known distance in Automatic mode with the count displayed, and divide. **(c) is cheap, decisive, and the only one of the three that does not depend on OKM's cooperation.**

---

## Gap 2 — the per-version sweep

This is where the sweep paid. **Three device generations declare three different things, and in the newest one the count is not declared at all.**

### Generation 1 (2009) — the operator declares a **count**

Rover C II (2009-09) and Rover Deluxe v4 (2009-10), §8.1.2 *Regulation of the number of impulses per scanning path*, **p.49 in both** **[V]**, verbatim and identical:

> It is possible to **select the number of impulses before starting the measurement** or selecting the automatic mode ("Auto") to adjust the number of measure points after finishing the first scanning path. When the number of measure points has been configured, **the device will stop automatically** when this number has been reached and waits for the start of the new scanning path.
>
> In the automatic mode you should stop the measurement of the first scanning path by yourself, by pressing the start button, as soon as you have reached the end of the first scanning path. **This effective amount of measure points will be used for all further scanning paths of this measurement.** Starting from the second scanning path, the device now stops automatically after the assumed number of impulses has been reached.

Factory defaults, stated as defaults, Rover C II p.57 and Rover Deluxe pp.57 & 62 **[V]**:

> Now you can see the selection menu of the impulse mode (Impulse Mode). **It is already set on "Automatic".** Confirm this selection by pressing the OK button.
> The next parameter is the number of impulses (Impulses). **The default setting is "20".** Press two times the arrow key, to select "Auto".

Rover Deluxe p.62 shows the arrow-key step explicitly: *"**The default setting is "20".** Press one time the arrow key [up], to select **"30"**."* **[V]** — so the parameter is a **discrete list in steps of 10**, and 30 is one ordinary step above the default.

Rover Deluxe p.60 also names the option's semantics **[V]**: *"**Impulses: "30" — Predefined fixed number of impulses**, which means that the number of impulses should be exactly 30 within the 1. scanning path and all following scanning paths."*

**The choice list is stated explicitly in generation 2**, 3D Ground Navigator 2 (2019-03) *Step 4 – Impulses*, p.42 **[V]**:

> Now you set the number of impulses (measure points), which will be recorded for each single scanning path. The following choices can be made:
> • **Automatic** — The number of total measure points of one scanning path will be defined during the measurement. … This number of measure points will than be used automatically for all following scanning paths. Beginning from the second scanning path the device will stop by itself, when the defined number of measure points has been sent out. **If you select "Automatic" you are not able to do a direct transfer to a computer. You can only store the measured values in the internal memory of the device, because the exact length of field is not yet selected.**
> • **10, 20, ..., 200** — Each scanning path consists of the selected number of measure points. At the end of each scanning path the device stops by itself, as soon as the number of measure points has been recorded.

Rover C4 (2021-08) §5.1.1 step 3, p.17, carries the **same `10, 20, ..., 200` list** and the same `Auto` semantics **[V]**:

> First, set the number of measure points (Impulses), which will be recorded for each single scan line.
> **Auto**: The number of measure points of one scan line will only be defined during the measurement. … **This number of measure points will then be used for all following scan lines. Beginning from the second scan line, the device will stop by itself, when the defined number of measure points has been sent.**
> In "Auto" mode you can not transfer data directly to a computer. You can only store the measured values in the internal memory, because **the exact length of field is not yet selected**.
> **10, 20, ..., 200**: Each scan line consists of the selected number of measure points.

Rover C4 §5.1.1, p.16, names it as one of the four things the operator sets **[V]**: *"Before starting the actual measurement, you have to adjust 4 essential parameters: • Impulses • Impulse Mode • Scan Mode • Transfer Mode."*

Rover C4 also carries a **transfer-summary screen** listing the parameter (p.29) **[V]**: `memory slot | Mineral Scan | 3D Ground Scan | Parallel | Impulses | per scan line`.

### Generation 2 (2014–2022) — the operator declares a **length**, and the count is derived

**eXp 4500 NT (2020-05 and 2021-07)** is the outlier that carries a density — see §1c. Its declared quantity is a length: `Field Length (Auto, 5 m, 10 m ..., 50 m)`.

Note also, eXp 4500 NT p.49 **[V]**: *"Modify the following parameters (**the underlined values correspond to the setting made by the factory**)"*. **I could not recover which values are underlined** — the underlining is a font attribute that does not survive text extraction, and I did not render the page as an image. So **the factory default for `Field Length` on the eXp 4500 is [UNRES]**. Do not assume `Auto`.

### Generation 3 (2022–2024) — the operator declares a **length only**; the count parameter is **gone**

**Rover UC (2022-09)** §5.2.1 *Preparing a 3D Ground Scan*, p.16, in full **[V]**:

> 2 Select **Default** to use the preset parameters that we recommend for fast scans:
> **Field Length: Auto** | **Impulse Mode: Automatic** | **Scan Mode: Parallel**
> 2 Select **Customized** to adjust the parameters individually.
> 3 Choose the **Field Length**.
> **Auto**: Determine the length by pressing the Trigger at the end of the first scan line. All succeeding lines will stop automatically.
> **10m, 20m, ...**: The length of the scan lines is defined before the scan. All lines will stop automatically.
> 4 Select the **Impulse Mode** to determine how the single impulses (scan values) will be released by the detector.
> **Automatic**: All scan values will be recorded continuously line by line without any break.
> **Manual**: Every single scan value will only be recorded by pressing the Trigger.

Three findings in one short section:

1. **There is no impulse-count parameter on the Rover UC.** The count is a *consequence* of the declared length and the operator's walking speed.
2. **There is a named factory preset**, and `Impulse Mode: Automatic` is **one of its three values**. ⇒ see Gap 3.
3. **Manual mode carries a hard constraint tied to the parameter's absence**: Rover UC §5.2.2, p.18 **[V]** — *"If you have selected the Impulse Mode **Manual** … This mode **requires Field Length Auto**."*

**eXp 5500 Pro (2024-11)** — the current flagship — §5.5.1 *Configure Measurement*, p.28 **[V]**:

> Open the operating mode 3D Ground Scan. **The recommended parameters for fast and easy scans are:**
> **Scan Mode: Parallel**
> **Impulse Mode : Automatic**
> **Sound: ON**
> **LED Orbit: ON**
> …
> **Impulse Mode Automatic** — The impulses (scan values) are recorded continuously without any break.

The scan setup asks only for **Field Length and Field Width**, entered *after* the walk (§5.5.2, p.30 **[V]**: *"**Enter the Field Length and Field Width** that you actually measured"*). No count, anywhere. And its technical-specification table (§9, pp.63–64) publishes **no sample rate and no measurement resolution** at all **[V]**.

### The sweep, as a table

| Generation | Models (manual date) | Operator declares | Count parameter | `Auto` meaning | Sample rate published |
| --- | --- | --- | --- | --- | --- |
| **1** | Rover C II (2009-09), Rover Deluxe v4 (2009-10) | **a count** | `10, 20, …, 200`, default **20** | count := whatever line 1 produced | **no** |
| **2a** | eXp 4500 NT (2020-05, 2021-07) | **a length** | **absent** (count = 6/m × length) | length := whatever line 1 measured | **no** |
| **2b** | 3D Ground Navigator 2 (2019-03), Rover C4 (2021-08, 2025-11) | **a count** | `10, 20, …, 200` | count := whatever line 1 produced | **yes** — 1024/s, 16 bit |
| **3** | **Rover UC (2022-09)**, **eXp 5500 Pro (2024-11)** | **a length only** | **absent — parameter does not exist** | length := whatever line 1 measured | UC **yes** (240/s, 15 bit); 5500 Pro **no** |

### Why this is a finding of the first order

#48's reasoning was that a per-version difference would matter because the export format carries no orientation information in any version, so a version that documented a counting rule would be the only place one could live. That is confirmed, with a twist:

- **A counting rule does exist, in the manuals** — it is just not in the file, and it is operator-facing rather than device-facing. Generations 1 and 2b publish the count as an explicit menu choice.
- **In generation 3 the count is not published anywhere in the entire workflow** — not on the device, not in the import wizard (§Gap 4). It is *only* observable after the fact, by opening the file and counting rows.
- **One generation published a density in absolute units** — 6 impulses/metre, eXp 4500 NT only — and **OKM then stopped publishing it**. The information was available once and was withdrawn.

**[INF], high confidence:** OKM's declared-parameter surface moved *away* from density as the devices moved to app-driven operation. For generation 3 hardware, a device-side sampling rule is not merely unpublished — by the vendor's own workflow design, **no count is ever asserted by anyone**, at any stage, in any artefact.

---

## Gap 3 — can the operator influence the count?

**Yes. Fully, and it is the primary documented control.** Five pieces of evidence, all **[V]**:

### 3a. The parameter exists, is first-class, and has a published choice list

Rover C4 §5.1.1, pp.16–17 and 3D Ground Navigator 2 p.42: `Impulses` is one of the four essential parameters; the choices are `Auto` or `10, 20, …, 200` (§Gap 2). Rover C II / Rover Deluxe pp.57, 62 establish the step size is 10 and the default is 20.

### 3b. The factory defaults are stated, and they explain the corpus

> It is already set on **"Automatic"**. … The default setting is **"20"**.
> — Rover C II (2009) p.57 **[V]**

> Now you entered into the selection menu Impulse Mode. **The default setting is "Automatic".** … As the next parameter you should select the number of impulses (Impulses). **The default setting is "20".**
> — Rover Deluxe v4 (2009) p.62 **[V]**

> Select **Default** to use the preset parameters that we recommend for fast scans: **Field Length: Auto | Impulse Mode: Automatic | Scan Mode: Parallel**
> — Rover UC (2022-09) p.16 **[V]**

> The recommended parameters for fast and easy scans are: **Scan Mode: Parallel | Impulse Mode : Automatic | Sound: ON | LED Orbit: ON**
> — eXp 5500 Pro (2024-11) p.28 **[V]**

**[INF], and this matters for #49:** the corpus's `Impulse Mode: Automatic` in 9 of 9 exports is **exactly what an untouched factory default produces**. Its presence is therefore **weak evidence of operator intent**, and its uniformity should not be read as a designed choice. It does not license any inference about the count.

### 3c. What `Manual` does to the **count** — the question #48 asked

Answer: **`Manual` does not change the expected count; it changes *when* each of the count's impulses is emitted, and OKM claims that makes the realised spacing more even.**

Evidence that the count is set **independently of** the impulse mode — they are two separate menu steps, and OKM's own tutorial pairs `Manual` with a specific count:

> **Impulse Mode: "Manual"** — Manual impulse mode, where the measure values (impulses) of a scanning path should be released manually. **The device waits after each measure point for the user to release the next impulse.**
> **Impulses: "30"** — Predefined fixed number of impulses, which means that the number of impulses should be exactly 30 within the 1. scanning path and all following scanning paths.
> — Rover Deluxe v4 (2009) p.60 **[V]**

Evidence that the density is unchanged and only the timing is operator-supplied — the eXp 4500 NT repeats its density figure in **both** modes (p.50, §1c) **[V]**, and the Rover UC documents a **constraint** rather than a change: `Manual` *"requires Field Length Auto"* (p.18) **[V]**.

And OKM's own account of what Manual buys you is about *evenness*, not *magnitude* (p.17 **[V]**): *"This gives you FULL CONTROL OVER WHEN SCAN VALUES ARE RECORDED and **helps you keep similar distances between impulses**, resulting in a more even scan grid."*

### 3d. There is **no special rule** — and OKM says so, in every manual that exposes the count

> **There is no special rule for selecting the right number of impulses.** But there are different aspects which has to be considered. These are for example
> • the length of your measured area and
> • the size of the objects you are searching for.
> — Rover C II (2009) §8.1.2, p.50; identical in 3D Ground Navigator 2 (2019) p.60 and eXp 4500 NT (2021) pp.74–75 **[V]**

This is a **direct, explicit vendor statement that the count is not derivable**. It is the single most quotable sentence in this note for the downstream ticket.

### 3e. The rover-c4 default is not stated in the Rover C4 manual

The Rover C4 (2021-08) manual documents the choice list `10, 20, …, 200` but **does not state which value is factory-default**; its worked example at p.20 says *"In total, there will be 20 measure points per scan line"*, consistent with the 2009 manuals' stated default of 20 **[INF]**, but that is inference from an example, not a specification. **[UNRES]** for the C4 default as such.

### Verdict on Gap 3

The preset **is** operator-visible, **is** a discrete menu choice, and its value **is** in the manuals. Chased down as the ticket asked:

- **What sets the "preset" in the Scan Analysis Guide's Missing Scan Data example:** the **operator, on the device**, before the scan. `preset` = *pre-set by the user*, not *defaulted by the software*. The guide's own next sentence names the actors: *"this issue only occurs with detectors requiring the number of impulses to be **entered manually during data transfer**"* (p.42 **[V]**).
- **What `Manual` does to the count:** nothing to the count itself; it removes the automatic trigger. OKM pairs it with a separately-chosen count (Rover Deluxe p.60) and, where a density is published, states the density in both modes (eXp 4500 NT p.50).
- **Whether the corpus's uniform `Automatic` is informative:** no. It is the documented factory default on three separate generations.

---

## Gap 4 — does `Missing Scan Data` imply a count the software expects?

**Yes. The expectation is documented, it is exact, and it is *not* a software constant — it is a number the operator reads off the device and types into the transfer dialog.**

### 4a. The current documentation names the fault and the remedy

*Scan Analysis Guide* §6.5.2 *Missing Scan Data*, p.42 **[V]**, in full for the parts that bear on the count:

> The empty corner in the upper left indicates a **DATA TRANSFER ERROR**. Such scan images are extremely rare, as this issue only occurs with detectors **requiring the number of impulses to be entered manually during data transfer**.
>
> In the example above, **the preset number of impulses per scan line is 30**, but the total number of impulses transfered is only 80 (see right image). These 80 impulses are automatically distributed across the three scan lines as 30, 30, 20 — leaving the final section of the third scan line empty (see left image). As a result, the measuring values are shifted within the scan field, making a reliable analysis impossible.
>
> Recommendations:
> • **Transfer the scan file again and enter the correct number of impulses per scan line.**
> • Repeat the measurement if the scan file is no longer available.

Three consequences, all **[V]** or **[INF]** from **[V]**:

1. **The redistribution algorithm is `chunk(flat_count, n)` with chunk size = the entered count**, filling from the start and leaving the tail of the last line empty. The example is `chunk(80, 3, 30) = 30, 30, 20`.
2. **"Preset" = device preset.** The guide's own attribution — *"detectors requiring the number of impulses to be entered"* — settles it.
3. **30 is not a constant.** It is the guide's example, and 30 is an ordinary reachable value: it is one arrow-key step above the factory default of 20, and it is the value OKM's own Rover Deluxe §9 tutorial uses (**p.62 [V]**).

### 4b. The transfer dialog, in the vendor's own words

*Visualizer 3D Software Manual* (2008) §4.4.1.1 *New*, **p.19** **[V]** — the `Ground Scan` data-transfer dialog, verbatim:

> **Impulses per scan line** — Here you have to enter the number of impulses per search line. **Beware that this number has to be exactly the same like the one selected on the measuring instrument.** If for example you used 20 impulses for the measurement with your device you have to enter here also 20 impulses.

**That is the software's input contract for the count, stated by the vendor, and it is a transcription obligation.** There is no default to fall back on and no expected value the software holds.

Corroborated on the device side, Rover C II (2009) p.57 **[V]**:

> **When leaving the operating mode "Ground Scan" you should keep in mind the number of impulses which you have used per scanning path! This value you should enter when transferring the data to the software!**

And the device displays the number for the operator to read off — 3D Ground Navigator 2 (2019) p.52, the transfer-summary screen **[V]**: *"This screen informs you about the settings that you have to adopt into the Visualizer 3D dialog. **It tells you how many impulses per scanning path were recorded.**"*

The on-device counter format, which also shows *why* the count must be transcribed rather than derived **[V]**:

> The display shows the message "**Press Start, L:1, I:0/?**". **The question mark "?" shows that the number of impulses per scanning path has not been defined yet.** … For example there can be the following message written in the display "Press Start, L:2, I:0/25". **Here 25 impulses has been defined.**
> — Rover C II (2009) p.57 **[V]**

So a scan taken in `Auto` has, at the moment of measurement, **no count at all** — the device shows `I:0/?`. The count only comes into existence when the operator ends line 1.

### 4c. The current generation does not document the field — and the fault class survives without it

The current V3DS import documentation describes the wizard's `Enter Project Information` step as **[V]**:

> This could be anything like GPS data, Description of environment, **Length and width of the scan field**, Device dependent information (e.g. probe)
> As seen in figure 3, you have to enter **at least a proper project title as well as the length and width of your scan area** before clicking Next.
> — *V3DS Documentation*, *Wireless Data Import via Bluetooth*

**No impulse-count field is documented in the current wizard.** Yet the fault class is still current — *AI Scan Analysis for 3D Ground Scans* (added in V3DS 3.4.0) **[V]**:

> This icon indicates potential data inconsistencies. These issues are usually the result of **faulty data transfer (e.g., selecting the wrong number of impulses)**.

**[INF]:** the count field survives in generation 1/2b devices and their transfer paths; in generation 3 the count is never asserted, so the corresponding fault cannot arise from a mis-typed field — it can only arise from a mis-declared **Field Length** or a genuinely short final line.

### 4d. What the software *does* expect, stated positively — and this is the finding #49 needs

The reproduction of the layout rule is not only implied by §6.5.2; OKM states it as a property of the software **[V]**:

> **KEEP EQUAL DISTANCE BETWEEN SCAN LINES** — Keep the distance between scan lines consistent throughout the scan. **Uniform spacing ensures an accurate scan image, as the software Visualizer 3D Studio displays the imported scan data at evenly spaced intervals.** Inconsistent spacing can therefore lead to distortions in the scan image.
> — *Scan Analysis Guide* p.11 (rules checklist), and *Scan Analysis Checklist-Log* p.3 — verbatim identical in both

**And the current software computes the spacing and gates it against a published threshold [V]:**

> Are the distances between the impulses within a scan line **no greater than 25 cm (0.85 ft)**?
> — *AI Scan Analysis for 3D Ground Scans*, the six pre-flight questions

> This icon indicates that **the distance between your impulses per scan line is too large. It should be not more than 25 cm (0.85 ft)**.
> This icon indicates that **the distance between your scan lines is too large. It should be not more than 50 cm (1.65 ft)**.
> — same page, the precheck indicator list

**[INF], high confidence, and directly actionable:** OKM's own software computes

```
realised_spacing = declared_field_length / impulses_per_line          (and  / (n-1) — see predecessor note)
```

and warns when it exceeds **0.25 m**. That is a **vendor-published, software-side rule with a vendor-published threshold**. It is reproducible from a file, it is checkable, and it is the same quantity the project needs.

### Verdict on Gap 4

**Yes — and the expected count is documented, operator-supplied, and absent from the file.** The `Missing Scan Data` section is not evidence of a hidden software constant; it is evidence of a **hand-transcription contract that can fail**. Nothing in the documentation gives a per-line count the software expects on its own, in any generation. The only quantities the software will assert for itself are the ones the operator typed into `Field Length` and `Field Width`.

---

## Artifacts actually opened

Everything below was downloaded and read in full text (PDFs extracted page-by-page; HTML pages fetched and de-tagged). **Nothing here is a secondary write-up.** Search terms applied to each PDF's full text: `impulse`, `number of impulses`, `impulses per`, `per scan line`, `per meter`, `Impulses:`, `default setting`, `Regulation of the number`, `sample rate`, `samples per second`, `values/second`, `values / second`, `measurement resolution`, `sampling rate`, `sampling interval`, `scanning speed`, `walking speed`, `pedometer`, `step counter`, `technical spec`, `\d+ bit`, `interval`, `preset`, `predefined`.

### PDFs — full text extracted

| # | Artifact | Version / date | Pages | Looked for |
| --- | --- | --- | --- | --- |
| 1 | **Scan Analysis Guide** (EN V1) — <https://www.okmdetectors.com/cdn/shop/files/OKM-Scan-Analysis-Guide-EN-V1-digital-komprimiert.pdf> | Version 1.0, **February 2026** | 28 | count, spacing, cadence, preset, redistribution, "Missing Scan Data", expected per-line count |
| 2 | **Scan Analysis Checklist-Log** (EN) — <https://www.okmdetectors.com/cdn/shop/files/OKM-Scan-Analysis-Checklist-Log-EN.pdf> | **no version or date printed in the artifact**; pocket companion to #1 | 8 | same; found the *"displays the imported scan data at evenly spaced intervals"* statement |
| 3 | **3D Ground Scan Guide** (EN) — <https://kuwait.okmdetectors.com/cdn/shop/files/OKM-3D-Ground-Scan-Guide-202108-EN.pdf> | 2021-08 | 18 | Impulse Mode, scanning speed, impulse spacing rules, Major Rules |
| 4 | **Rover C4 manual** (EN) — <https://southafrica.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-C4-202108-EN.pdf> | 2021-08 | 36 | `Impulses` parameter, choice list, defaults, transfer summary, spec table |
| 5 | **Rover C4 manual** (EN) — <https://euro-technologygroup.com/wp-content/uploads/2025/11/OKM-Manual-Rover-C4-EN.pdf> | 2025-11 — **SHA-256 identical to #4** | 36 | confirm no revision drift — none found |
| 6 | **Rover UC manual** (EN) — <https://www.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-UC-202209-EN.pdf> | 2022-09 | 36 | `Field Length` vs `Impulses`, `Default` preset, pedometer, compass, spec table |
| 7 | **3D Ground Navigator 2 manual** (EN) — <https://rojmd.okmdetectors.com/cdn/shop/files/OKM-Manual-3D-Ground-Navigator-2-201903-EN.pdf> | 2019-03 | 64 | `Impulses` choice list `10,20,…,200`, `Auto` semantics, transfer summary, spec table |
| 8 | **Rover C II manual** (EN, New Edition) — <https://kuwait.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-C-II-New-Edition-092009-EN.pdf> | 2009-09 | 62 | factory defaults, `I:0/?` counter, `Auto` semantics, spec table, walking-speed artefacts |
| 9 | **Rover Deluxe manual** (EN, New Edition v4) — <https://okm-usa.com/cdn/shop/files/OKM-Manual-Rover-Deluxe-New-Edition-v4-200910-EN.pdf> | 2009-10 | 62 | same, plus the `Impulses: "30"` Manual-mode tutorial |
| 10 | **Visualizer 3D Software manual** (EN) — <https://www.okmamericas.com/cdn/shop/files/OKM-Manual-Visualizer-3D-200810-EN.pdf> | 2008-10 | 51 | the transfer dialog's `Impulses per scan line` field |
| 11 | **eXp 4500 NT manual** (EN, v2) — <https://www.okmdetectors.com/cdn/shop/files/OKM-Manual-eXp-4500-NT-v2-202005-EN.pdf> | 2020-05 | 82 | **`6 impulses per meter`**, `Field Length`, factory defaults, spec table |
| 12 | **eXp 4500 NT manual** (EN) — <https://okm-usa.com/cdn/shop/files/OKM-Manual-eXp-4500-NT-202107-EN.pdf> | 2021-07 | 81 | same — `6 impulses per meter` confirmed in both revisions |
| 13 | **eXp 5500 Professional manual** (EN, X55-A01 V1) — <https://www.okmdetectors.com/cdn/shop/files/OKM-Manual-eXp-5500-Pro-X55-A01-V1-Digital-202411-EN.pdf> | **2024-11** | 66 (34 two-page spreads) | whether the count parameter still exists; spec table |

### Web pages — fetched and read

| # | Artifact | What was taken from it |
| --- | --- | --- |
| 14 | V3DS documentation index — <https://www.okmdetectors.com/blogs/v3ds-documentation> | the full 28-article list, used to enumerate the sweep |
| 15 | **all 28 V3DS documentation pages** — <https://www.okmdetectors.com/blogs/v3ds-documentation/> | swept as a set for `impulse / sample / trigger / preset / resolution / spacing / interval`. **The words "sample rate", "sampling", "trigger" and "preset interval" appear on none of them.** "Impulse" appears only as a UI label. Findings used: *AI Scan Analysis for 3D Ground Scans* <https://www.okmdetectors.com/blogs/v3ds-documentation/ai-scan-analysis-3d-ground-scans> (25 cm / 50 cm gates), *Analyzing and Editing 3D Scan Images* <https://www.okmdetectors.com/blogs/v3ds-documentation/analyzing-and-editing-3d-scan-images> (`e.g. 40 impulses, 20 scan lines`), *Wireless Data Import via Bluetooth* <https://www.okmdetectors.com/blogs/v3ds-documentation/wireless-data-import-via-bluetooth> (wizard fields), *Changelog* <https://www.okmdetectors.com/blogs/v3ds-documentation/changelog> (3.0.1 → 3.4.0, swept in full) |
| 16 | *How to Achieve Best 3D Scan Images* — <https://www.okmdetectors.com/blogs/videos-tutorials/how-to-create-best-scan-images> | 2020-10-07 — **"not collected in the predefined speed"** |
| 17 | *FAQ: Measuring Value vs Scan Value* — <https://www.okmdetectors.com/blogs/videos-tutorials/quick-scan-check-4-faq-3dgs-values> | 2025-11-25 — already carried in the predecessor note; re-read for the `7 lines × 115 impulses = 805` arithmetic |
| 18 | Product pages: <https://www.okmdetectors.com/products/rover-uc>, `/rover-c4`, `/exp-5500-professional`, `/exp-7000-professional-plus`, `/fusion-professional`, `/evolution-ntx`, `/fusion-light` | spec tables; `Samples: 240 per second @ 15 bit` (UC); `1024 values / second` + `16 bit` (C4, Fusion ×2, NTX); **neither** (5500 Pro, 7000 Pro Plus) |
| 19 | *OKM Download Center — Manuals* — <https://www.okmdetectors.com/pages/download-center-manuals> | inventory and language coverage; the per-manual PDF links are JS-driven, so the URLs above came from search |

---

## Not reached — and why that matters

These are **unreachable**, which is a different entry from **silent**. None of them is counted as evidence of absence.

| Artifact | Why not reached | Would it change the finding? |
| --- | --- | --- |
| **Firmware release notes / `.odu` update files** | The eXp 5500 manual §6.3 points to `www.okmdetectors.com/updates` for firmware updates distributed as **binary `.odu` files**. **OKM publishes no text changelog for detector firmware anywhere I could reach.** | **This is the single most likely place a device-side cadence would be disclosed, and it is not publicly readable.** Highest-value remaining target. |
| **Fusion, Evolution NTX, eXp 7000 Pro Plus manuals** | Not downloaded; only their product pages were read. Product pages publish sample rates but no impulse-density statement. | Low. Generation-2b pattern is well covered by C4 / 3D GN2. |
| **Which `Field Length` / `Impulse Mode` values are underlined (factory defaults) on the eXp 4500 NT** | Underlining is a font attribute that does not survive text extraction; I did not render the pages as images. | Low. Would firm up §3b for one model only. |
| **Non-English manuals** (eXp 4500 exists in EN/DE/FR/ES/TR/AR/ZH/FA; the download centre lists per-language files) | Not swept. | Low, but non-zero: a density figure could in principle differ by locale. |
| **German-language Scan Analysis Guide / 3D Ground Scan Guide** | Not opened; only the EN versions. | Low. The predecessor note already records EN/DE wording drift on soil-type parameters, so drift is real. |
| **The built-in soil-type tables and the `*.v3ds` internals** | Require a licensed V3DS install. Carried over from the predecessor note; not re-attempted. | None for this ticket. |
| **Anything from OKM support / a dealer / a forum** | Out of scope by instruction: primary sources only, and a support reply is the *next* action, not a source I can read. | **High** — see below. |

---

## What would change the verdict

The judgement below is specific enough to be falsified. Each of these is a concrete, bounded action.

1. **A bench measurement.** Walk a measured distance (tape, 10 m) in `Impulse Mode: Automatic` on a generation-1/2b device with `Impulses` set to a known value, and read the realised spacing. Repeat at two walking speeds. **If the spacing is invariant, a distance-triggered cadence exists and OKM simply does not publish it. If the spacing scales with speed, the cadence is temporal and the spacing is unrecoverable by construction.** This is the cheapest decisive test and it needs no vendor cooperation. It is the experiment to run.
2. **A written answer from OKM support or a dealer** to: *"In Impulse Mode Automatic, what determines the interval between impulses on the Rover C4 / eXp 5500 — time, distance, or steps?"* One sentence either confirms a temporal cadence (closing the question as unrecoverable-from-docs) or names a mechanism (opening it).
3. **A firmware changelog**, if one can be obtained from a dealer or an `.odu` release note. Would be the only place a numeric cadence could live.

If (1) shows the spacing is speed-invariant **and** (2) or (3) stays silent, then the device-side sampling rule is **not merely unpublished but absent as a concept** — the hardware would be free-running in time, and the metric spacing would be irreducibly a property of the operator, which is the strongest form of the answer this ticket can produce.

---

## One sentence to carry forward

**OKM documents the software's layout rule and gates it at 25 cm, documents the operator's count as a menu choice defaulting to 20, documents one model — and only one — as sampling at 6 impulses per metre, and states in as many words that "there is no special rule for selecting the right number of impulses"; the device-side cadence is asserted to exist ("the predefined speed") and is nowhere given a value, so for every device generation except the eXp 4500 NT the spacing inside a scan field is an unrecoverable property of the walk.**
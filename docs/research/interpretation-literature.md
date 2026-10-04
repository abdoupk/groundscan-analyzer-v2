# R2 — Published methods for interpreting OKM and shallow ground-scan responses

**Ticket:** abdoupk/groundscan-analyzer-v2 #21
**Purpose:** establish what the published record actually licenses a v2 analysis engine to *claim* about OKM Rover-series ground-scan data.
**Status of ground truth:** none. No independent field ground truth is available for this corpus. Everything below is about what published physics and published geophysics permit, not about what is in our corpus.
**Date of literature sweep:** 2026.

## How to read the evidence weights

| Tier | Meaning | Weight here |
| --- | --- | --- |
| **A — peer-reviewed primary** | Physics/modelling papers, field studies, standards documents | Load-bearing |
| **B — peer-reviewed adjacent** | Same physics, different application domain (UXO, glaciology, glaciology of radar, mineral exploration geochem) | Load-bearing by analogy; flag the analogy |
| **C — grey literature** | Agency/industry reports, practitioner tutorials, standards guidance notes, manufacturer-adjacent field tests | Corroborative only; useful for *what practitioners actually do* |
| **D — vendor** | OKM manuals, product pages, reseller pages | Evidence of *claims made*, not of *claims licensed*. Never used as support. |

**No Tier A or B source was found anywhere in the sweep that evaluates an OKM instrument, or any instrument in the "EMSR"-class consumer ground-scanner category, against ground truth.** Every quantitative statement below about OKM-family behaviour traces to OKM's own documents (Tier D) or to the much older "third-party field test" reports OKM publishes (Tier C/D — a commissioned test by a sworn expert whose device selection was random from the catalogue; the report itself is not in the peer-reviewed literature).

---

# Summary: what is established, contested, uncharacterised

## Established (Tier A/B, corroborated across independent literatures)

1. **FEM/EMI and GPR are different physical measurements that respond to different properties.** EMI in the induction regime is a diffusive measurement of bulk *electrical conductivity* (and, in the "magnetometer" mode, *magnetic susceptibility*); GPR is a wave measurement sensitive primarily to *permittivity*, with conductivity governing attenuation. Their sensitivities are near-complementary, not redundant. (Everett 2010; Pellerin 2002; Moghadas et al. 2010; CLU-IN/USACE.)
2. **A buried cavity is detectable in both modalities, but by different physics and with different failure modes.** In GPR it produces a strong paired top/bottom reflection ("bright spot") whose polarities are opposite, with reverberation when the void is large relative to wavelength. In EMI at high frequency (100 kHz–20 MHz) a void is a *conductivity contrast* with a relaxation signature of its own — it is not a "null". (Persico et al. 2024; Nobes 2018; Yu & Carin 2000; Barrowes et al. 2016, 2019.)
3. **A metal target produces an *induced* secondary field, and the induced moment is antiparallel to the inducing field.** This is the physical origin of the two-lobed (positive/negative) response. It is well modelled (equivalent dipole polarisability with negative diagonal terms; induced-polarisation formalism). (Wait 1960; Rai & Verma 1982; Noh et al. 2016; Pasion/Oldenburg-family dipole models; Baum's dipole polarisability work.)
4. **Two nearby targets below roughly one footprint/aperture width merge into a single anomaly.** Quantitatively anchored: targets must be separated by about the system footprint for anomalies to be resolved; resolution degrades as the sensor footprint grows. (Andersen & Auken 2005; Gupta, Kakirde & Negi 1988/1990; Duckworth & Clement 2001; Schamper et al. 2022; Ren et al. 2023.)
5. **A false-positive rate on ordinary geology is enormous, and is the dominant cost, not the exception.** Field demonstration on a magnetite-bearing volcanic island: 61,261 anomalies, of which 2.7% were ordnance, 27% geologic false positives, 70.3% buried metal. (Cargile et al. 2004, ESTCP.) The peer-reviewed summary position is blunt: detection capability exists, *discrimination capability does not*, *identification capability does not exist*. (Butler et al. 1998, ERDC TR-08-9.)
6. **A fixed multiple-sigma threshold on a spatially correlated lattice is not a significance level.** The statistics literature is unambiguous: on a correlated field you must control the *global* excursion rate, not per-cell p-values (look-elsewhere effect; Euler characteristic of Gaussian random fields; FDR under dependence). GPR-specific work exists that estimates false-alarm rate from a small target-free area precisely because per-pixel statistics are insufficient. (Gross & Vitells 2011; Gross & Schneider 2018; Lit & Shepherd; Bräu & Rial 2019; Perone Pacifico et al. 2004; Sun et al. 2014.)
7. **Depth estimates from these instruments carry large, structured, non-Gaussian errors.** For *GPR*, a well-tuned pipeline still yields ~7 cm depth error at the surface rising to ~22 cm by 80 ns two-way time, against a vertical resolution of ~5 cm — i.e. the *interpretation* error exceeds the *resolution* by >400% (Wunderlich et al. 2022). For EM cavity imaging, depth error is ±15% of depth only at the top PAS 128 quality level (dual-technique), ±40% at the single-technique level. (PAS 128:2022; Gowan et al. 2019.)
8. **Edge/boundary and direction-of-travel artefacts are real, named, and severe.** Herring-boning, ghost conductors, drooping trouser-leg responses, "off-end" ghosts, wrap-around FFT ringing, pimpling, bullseyes, string-of-beads. All documented with quantitative remedies. (Annetts et al. 2000; Ley-Cooper et al. 2010; Ellis 1998; Silic et al. 2018; Save et al. 2012; Geosoft; Minty; Breuer et al. 2024.)
9. **There is a standard, respected vocabulary for compatibility-versus-identification, and it is codified.** PAS 128:2022 is the clearest example: it grades every *segment* by survey type and confidence, requires a minimum of two independent techniques, and states explicitly that geophysical data alone does not identify. The petroleum-geoscience community has a parallel apparatus (DHI Index, "not all DHIs are DHIs"). (BSI 2022; AAPG/GeoExPro DHI Consortium.)

## Contested / genuinely ambiguous

- **How much material discrimination EMI alone can do.** Bruschini's foundational work finds *coarse, qualitative* classification by size and permeability is achievable at high S/N, and quantitative multi-feature discrimination possible for a limited set of large targets with stable signatures — but the same papers repeatedly find residual ambiguity, orientation dependence, and the requirement for a-priori knowledge of the target set. This is *not* settled; it is an active research area with real gains (MIS, HFEMI) but no general solution.
- **Whether EM can detect voids/cavities at all in low-frequency operation.** Yu & Carin (2000) establish it in the frequency domain with a lossy dielectric; Barrowes et al. (2016, 2019) establish it experimentally but need frequencies *above* the conventional EMI band (up to ~15–20 MHz). At the low frequencies typical of consumer instruments, the literature is much less encouraging.
- **Whether orthogonal-grid acquisition is required, recommended, or harmful.** Archaeology practice says perpendicular second acquisition improves localisation and shape definition, especially for depolarising bodies — but the same literature documents that *naive* combination of orthogonal traverses creates traverse-parallel linear artefacts and that GNSS-per-line errors can obliterate the target entirely. Both effects are real; the resolution is procedural, not algorithmic.
- **Whether a smooth, spatially correlated background bulge is separable from a compact target.** Robust background separation literature says it should be, *if* the filter width is chosen well (Wessel 1998/2015; Kim & Wessel 2008 directional median). But the same literature reports that the separated result *varies with filter width*, and that the variation is the dominant uncertainty. No published work validates a fixed physical scale for a consumer ground scanner where the scale (target size) is *not known in advance*.

## Uncharacterised (no relevant published evidence found)

- **Any quantified depth performance for the OKM Rover family.** OKM claims objects found "down to 25 m". No independent, peer-reviewed validation exists. The device manual's own depth figure is soil-dependent ("according to the chosen soil").
- **What a bl OKM "Ground Scan" number physically is.** OKM calls it "Electro-Magnetic Signature Reading (EMSR)" and publishes only sample rate (1024 values/s) and resolution (16 bit). Published specifications list the coil technology as VLF. No peer-reviewed characterisation of the transfer function, footprint, coil geometry, or frequency content was found. **This is the single largest gap.**
- **The false-positive rate of the classification taxonomy** (metallic-like / cavity-like / geological-like / dipolar-response) against any reference.
- **Whether a "dipolar response" class is separable from a "cavity" class at all** on a gridded lattice. Physics says both produce sign change across the target (see Q3). No published work evaluates this particular discrimination on this kind of instrument.
- **Any established practice for combining two 90°-offset acquisitions of a *hand-walked consumer scanner with no position log*.** The professional literature assumes GNSS or total station; the consumer literature (Tier C/D) assumes re-walking the grid and visual comparison.

## 🔴 Prominent red flags — legacy claims that the literature does NOT support

| Legacy claim | Status | Evidence |
| --- | --- | --- |
| Classify as "metallic-like" | **Not supported as an identification.** Supportable only as a compatibility statement: "the response is *consistent with* a metallic response." | Bruschini et al. call even their best result a "coarse"/"qualitative" classification; Butler et al. (ERDC) state there is **no** identification capability. |
| Classify as "cavity-like" | **Not supported.** | Persico et al. 2024 (Sensors 24:3238), verbatim: *"Currently, there is no mathematical method that can verify a detected target as a cavity."* Nobes 2018 documents voids routinely misidentified, and non-voids identified as voids. |
| Classify as "geological-like" | **Not a physical class.** It is a residual/catch-all ("neither metal nor cavity"). Naming it "geological" imports a claim about cause that no measurement supports. | PAS 128 wording: an anomalous feature is "an *unidentified* subsurface area … that differs in response to its surrounding area." |
| Report a device-reported depth as a depth | **Not supported without an explicit provenance and uncertainty statement.** Device depth is soil-keyed, single-technique, and single-point. PAS 128 puts single-technique depth at ±40% of depth at best. | PAS 128:2022 Table 1; Gowan et al. 2019; OKM manual ("according to the chosen soil"). |
| Treat 3σ as a detection threshold | **Not supported as a significance level.** It is a tunable heuristic. | Look-elsewhere / Euler-characteristic / FDR-under-dependence literature; Bräu & Rial 2019. |
| Distinguish dipole from cavity reliably | **Physics says the two share the observable.** A conductive body's induced moment is antiparallel to the inducing field, producing a +/− lobe pair; a cavity produces opposite-polarity top/bottom reflections. On a coarse lattice both are "a thing with two signs". | This is exactly why the legacy system needed a special case for "dipole misclassified as cavity" — the taxonomy is unstable, not the classifier. |

---

# Q1. Physical basis of the response

## 1.1 The two modalities are near-complementary, not variants of one measurement

**Frequency-domain electromagnetic induction (FEM/EMI).** A transmitter coil emits a time-varying magnetic field; eddy currents form in any conductor and re-radiate a secondary field picked up by a receiver coil, typically decomposed into in-phase and quadrature components. Everett (2010) states the position bluntly: *"the response recorded by the EM induction method is almost entirely due to the bulk subsurface electrical conductivity."* Depth of investigation is a function of **coil spacing** and **frequency** — larger spacing or lower frequency for depth, smaller for resolution (CLU-IN/USACE; EPA 1988/1993/1994). Apparent conductivity is an *integral* over depth, not a measurement of a layer. In the induction regime displacement currents are negligible, i.e. the physics is *diffusive* (Everett 2010; Giannino & Leucci 2022).

**GPR.** A transmitter emits a wideband EM pulse; reflections occur at interfaces where the **permittivity/velocity** changes; conductivity governs **attenuation**. The dielectric constant dominates shallow-soil GPR because permittivity of water overwhelms other constituents, which is why GPR-derived permittivity is used as a surrogate for soil water content (Moghadas et al. 2010; Huisman et al. 2003, doi:10.2136/vzj2003.4760). Vertical resolution is set by a fraction of wavelength (~λ/4); lateral resolution by the first Fresnel zone (Wunderlich et al. 2022; Leach 2021, GSSI).

**The complementary-sensitivity statement is directly evidenced, not just asserted:** Moghadas et al. (2010) perform joint inversion of synthetic GPR + EMI and find the benefit of combining the two information sources, while noting the fusion is *"not straightforward"* because the sensitivities differ in kind.

**Cramps/resolution limits:** GPR fails in conductive (clayey) cover — Pellerin (2002) documents the VETEM system existing precisely *"at the inductive limit … in the range between inductive EM and GPR for areas where GPR is problematic, such as in conductive terrain."* EMI loses resolution to depth. Moghadas et al. show that when the top layer is highly conductive or high-permittivity, **neither** method can fully retrieve hydrogeophysical parameters.

**Tier A/B citations:**
- Everett, M.E. (2010). "Theoretical Developments in Electromagnetic Induction Geophysics with Selected Applications in the Near Surface." *Geophysics* 75(5), F103–F122 (EGP Workshop review). https://mtnet.info/division/papers/EMWKSHP_ReviewVolumes/2010Giza/Everett_2010GizaReview.pdf
- Pellerin, L. (2002). "Applications of electrical and electromagnetic methods for environmental and geotechnical investigations." *Exploration Geophysics* 33(4), 190–204.
- Giannino, F. & Leucci, G. (2022). *Electromagnetic Methods in Geophysics: Applications in GeoRadar, FDEM, TDEM and AEM*. Wiley. ISBN 9781119770985.
- Moghadas, D., André, F., Slob, E., Vereecken, H., Lambot, S. (2010). "Joint full-waveform analysis of off-ground zero-offset GPR and EMI synthetic data for estimating soil electrical properties." *Geophysical Prospecting*.
- CLU-IN / USACE, "Electromagnetic Methods" technology page. https://cluin.org/characterization/technologies/default2.focus/sec/Geophysical%5FMethods/cat/Electromagnetic_Methods/ (Tier C, but a faithful summary of EPA/USACE primary documents.)

## 1.2 What a low-frequency conductor looks like

In the low-frequency (eddy-current) regime:

- Eddy currents are confined near the surface of a good conductor, confined "very closely to the object's surface", with skin depth δ ∝ 1/√(ωμσ) (Gans 1989, NIST IR 89-3915, Tier A/government).
- The response of the target is a **spectrum** with three named features: a low-frequency linear range, a quadrature peak, and the inductive limit — occurring *in that order* but at *different frequencies for different objects* (Barrowes et al. 2019).
- The target response is characterised by a **rank-2 magnetic polarisability tensor** (MPT), position-independent, whose coefficients encode size, shape, conductivity and permeability and vary with frequency (Ammari et al.; Ledger & Lionheart; Wilson et al. — see the 2025 arXiv paper "Characterising buried objects in metal detection", arXiv:2507.04450, and Ammari, Buffa & Nédélec 2013, *European Journal of Applied Mathematics* 295, doi:10.1017/S0956792523000207).
- **Ferrous vs non-ferrous is *in principle* a phase discrimination:** the induced-magnetisation contribution to the in-phase component is negative-signed with weak frequency dependence, which "is a direct indicator of a magnetic object" (Noh et al. 2016, *Geophys. J. Int.* 204(3), 1550–…, https://academic.oup.com/gji/article/204/3/1550/678228).

**Landmark result on discriminability limits:** Beran (2009 thesis, Tier B) shows via forward modelling that because conductivity and permeability are correlated in real materials, EM inversion *"can, at best, tell us whether a target is magnetic"*, and an accurate permeability estimate cannot be recovered — for spheres of realistic size over the EM-63 band. This is a hard, quantified ceiling on what a frequency-domain conductivity/permeability reading can say about composition.

## 1.3 What a cavity looks like in each modality

**In GPR.** An air-filled void in soil is a strong permittivity contrast (ε_r ≈ 1 vs soil ≈ 9). You get a reflection from the top (positive reflection coefficient ≈ +0.5 for soil→air) and a reflection from the bottom with **reversed polarity** (air→soil, coefficient ≈ −0.5), plus reverberation/multiples. When the void's time delay is ≲ half the pulsewidth the two wavelets **superimpose** and produce a single "bright spot" whose amplitude is ~50% larger than a single reflection — the *apparent* thickness then badly underestimates the true thickness (Nobes; "Ground penetrating radar response from voids: a demonstration using a simple model", *NDT&E International*, 2017). For voids much larger than the wavelength you get reverberation rather than hyperbolas (Kofman, Ronen & Frydman 2005, *J. Appl. Geophys.* 59(4), 284–299; Luo et al., PolyU thesis on GPR air-void pattern recognition). A cavity in GPR is *also* strongly compressed in the time/depth image because velocity jumps to 0.3 m/ns inside; Persico et al. (2024) measured an apparent cavity thickness of ~20 cm where the real value was about twice that, and needed a Combined Time–Depth Conversion to fix it.

**In EMI.** A void is not a null — it is a **conductivity contrast with its own relaxation signature**. Yu & Carin (2000) model a lossless dielectric body in a lossy dielectric medium as "a void in a conducting background" detectable by an EMI sensor at appropriate frequencies, using MoM and extended-Born. Barrowes et al. (2016) show experimentally that detecting "even voids embedded in conducting soils" requires frequencies **up to the low megahertz range** — above the <100 kHz band conventional EMI uses. Their 2019 work extends the band to 20 MHz as "HFEMI" and shows IED constituent parts including "conductivity voids" become visible. Bruschini (2004, *IEEE TGRS*) notes a related asymmetry: a permeable soil produces a plateau effect in the real part of the response and couples differently than a conductive soil.

**Where OKM sits.** Published reseller/specification listings give the OKM Rover C4 as: `Technology: GST / EMSR`, `Sensor technology / Coil technology: SCMI-15-D / VLF`, `Sample rate: 1024 values/second`, `Measurement resolution: 16 bit` (OKM product page and Rover C4 manual, Tier D). No peer-reviewed characterisation of what frequency or what physical quantity the channel actually measures was found. The vendor term "EMSR" is not a standard geophysical term. **Treat the transfer function as unknown.** The nearest published relative is a VLF-EMI instrument in the tens-of-kHz regime, i.e. squarely in the regime where Yu & Carin and Barrowes indicate voids *are* detectable but Barrowes indicate void detection is difficult below ~1 MHz and Barrowes' own 2016 conclusion is that low-frequency EMI is the wrong tool for it.

## 1.4 Interpreting a blended signal — the vendor claim

OKM markets the Rover series as combining GPR with metal detection. The device does **not** appear to be a GPR system: there is no waveform, no antenna, no time-zero, no velocity model; there is a single 1024 Hz scalar channel. **The published literature contains no support for the claim that OKM's Rover combines GPR with metal detection in any physically traceable way.** The Rover C II product page (Tier D) describes the combination differently and concretely: a 3D ground scan with a standard probe, a separate Super Sensor probe, a magnetometer mode, and a *geoelectrical* resistance measurement using four electrodes for voids — i.e. a **resistivity** method for cavities, not GPR. That reading is physically coherent (resistivity imaging does detect voids and is an established shallow method) and is *not* a blended-signal problem at all.

**The one genuinely relevant peer-reviewed precedent for a blended GPR + metal-detection signal is the dual-mode humanitarian demining detector.** Marsh et al. (2019, *IEEE Sensors Journal*, PMC6695582) integrate spectroscopic metal detection with GPR on one head and report: GPR verification of the MD reduces the false-alarm rate by ~50% (citing ALIS 2009), and that the *combination of features* — object-present confidence from each sensor **plus GPR-derived depth** — materially changes the detection threshold. Critically, they also report the limits: minimum-metal AP mines at 16 cm were not detected by the MD channel at all, and *"Some care must be taken when interpreting the GPR data for shallow targets, as this is where the signal-to-clutter ratio has been observed to be poorest."*

**Reading:** the literature supports **multi-channel fusion with depth-aware thresholds** as the right *shape* of solution, and equally supports the claim that a shallow fused response is the *worst* case for false alarms. It does not support a single scalar stream being "a blend of GPR and metal detection".

---

# Q2. Metallic vs cavity vs geological discrimination

## 2.1 Is "consistent with a metallic response" defensible?

**Yes — as a compatibility statement, and only as one.** The evidence base:

- **Discrimination by phase is real but coarse.** Bruschini (2002 thesis, EPFL) — the standard reference — concludes *"A 'qualitative' (coarse) target classification … seems indeed to be possible, at least for scenarios with a sufficient S/N ratio"*, by object size and permeability. Bruschini, van Kempen & Lochy (2003, *IEEE TGRS*, "Metal Target Discrimination with a Commercial Two Frequency Sensor – Part II") confirm only *"partial target discrimination"* from amplitude/real-ratio features alone, with residual ambiguity resolvable *"in a number of cases"* using phase.
- **The residual ambiguity is structural, not a tuning problem.** Bruschini's own limitations list is the key passage: discrimination depends on (C1) which/how many target types exist a priori, (C2) how stable their signatures are, (C3) how representative the available clutter is, (C4) **how many clutter items have sufficient S/N to be discriminated at all**. His conclusion: *"even if we could identify each mine but for example only 10% of the clutter had a sufficient S/N … in nearly 90% of the cases we would have to issue an 'unknown object type' response, the system would probably not be too useful."*
- **Coarse size-permeability classes, not material identification.** "Large metallic objects can be discriminated from *smaller clutter*." That is a statement about size and contrast, not about material.
- **Independent peer-reviewed summary of the state of the art:** Butler et al. (1998, ERDC TR-08-9): *"can detect UXO, within definable limits; cannot effectively discriminate UXO anomalies from 'false alarm' anomalies; cannot identify UXO."*
- **Material-property estimation is provably degenerate.** Beran (2009): EM inversion with physical parameters "can, at best, tell us whether a target is magnetic."

**Conclusion for the engine:** "consistent with a metallic response" is defensible if and only if the qualifier "consistent with" is load-bearing and the supporting evidence is *cited to the measurement* (channel polarity structure, phase behaviour if recorded) rather than to a ground truth that doesn't exist. It is **not** defensible as "identified as metallic", "classified as a metal target", or "metal detection confirmed".

## 2.2 False-positive behaviour on ordinary geology

This is the strongest, most uncomfortable part of the record.

| Source | Finding |
| --- | --- |
| Cargile et al. (2004), ESTCP project report, Kaho'olawe, Hawaii (Tier C, DoD) | Magnetite-bearing basaltic soils precluded magnetometers; EMI "subject to very high false alarm rates". As of 14 Nov 2001: **61,261 subsurface anomalies detected; 2.7% UXO; 27% false positives from geologic sources; 70.3% buried metal (UXO- and non-UXO-related).** Detection performance could not be evaluated from these figures. |
| Cargile et al. (2004) | ROC curves of Pd vs FAR were *"almost consistently flat, diagonal"* across three advanced EMI demonstrators — *"none of the systems demonstrated a capability to discriminate emplaced UXO from emplaced metallic clutter in this environment."* |
| Butler et al. (1998) | JPG Phase II: four demonstrators, detection rates >70%, **3.4 to 20.7 false alarms per ordnance item detected**. "Mag and flag" reaches ~100:1. |
| Beran (2009) | ~100:1 FAR is the baseline; "advanced" methods hoped to reach 10:1. |
| O'Neill et al. (2005), *IEEE TGRS* 44(1), 32–46, doi:10.1109/TGRS.2005.858437 | Even in *"artificially well-mixed, physically smoothed"* settings, local soil-permeability variation is a significant clutter source. With a single piece of clutter immediately above a much larger UXO, *"almost complete obscuration"* in both frequency and time domains. |
| O'Neill et al. (2005), "EMI obscuration of buried UXO…" | Two similar objects at comparable depths with SCR ≈ 20 *are* separable over a survey grid; **objects at significantly different depths relative to each other cannot be separated even at the same SCR.** |
| Das (2005, 2007) | Soil electrical conductivity and magnetic susceptibility both mask and distort the target response; in laterite, the total response of a buried sphere was the *sum* of soil and free-space sphere responses. |
| van Verre et al. (2020), *IEEE TGRS* | In mineralised soil, the soil response magnitude is **at least two orders of magnitude greater** than a minimum-metal AP landmine at moderate depth (5 cm), and varies **±20%** with local soil conditions and sensor lift-off as the sensor is swept. Soil-phase, however, *"remain broadly constant"* as the sensor moves — which is exactly the exploitable structure (see Q8b). |
| O'Neill et al. (2005) | Local soil permeability variation is a clutter source *even in smoothed settings* — i.e. smoothing does not fix geology. |

**Generalisation to our setting (flagged as an analogy, not an identity):** OKM is not a UXO instrument and our terrain is not laterite. But the structural claims transfer: (a) geological false positives are the *majority*, not the tail; (b) magnitude disparities (shallow clutter over deep target) are the dominant obscuration mechanism; (c) the one usable structure — *the soil component is stable in phase while the target component varies* — is available only if the instrument records in-phase and quadrature separately. **Whether OKM's single scalar channel preserves that structure is unknown and probably not.** That is a serious, engine-relevant gap.

## 2.3 Corroborating the legacy system's own synthetic findings

The legacy system found (i) smooth spatially-correlated noise is the known object-mimic, and (ii) a 3σ gate behaves as a heuristic rather than a significance level. Both are corroborated in *shape* by independent literatures — though we should be precise that no published work tests the specific legacy implementation.

**(i) Smooth spatially-correlated background mimics compact objects.** The robust regional–residual separation literature exists precisely because of this. Wessel (1998, *Mathematical Geology* 30(4), 391–408, doi:10.1023/A:1021744224009) introduced an *optimal robust separator* based on an iterative, data-adaptive median filter precisely because classical regional–residual separation is non-unique and provides no uncertainty estimate. Kim & Wessel (2008) then found the specific failure mode: standard median filtering *"chooses the biased medians near the features on a sloping regional trend, which is a serious artifact"* — i.e. **a smooth regional trend leaves biased residuals that look exactly like compact features.** Their Directional Median (DiM) filter fixes it by returning the *lowest* of N sector medians, and then reports the key honest caveat: *"the separated results vary with the choice of filter width. Such variations are spatially distributed"* and they propagate these into per-point MAD uncertainty bounds. **This is a direct, independent confirmation that a smooth, spatially-correlated background component is the canonical false-positive generator, and that removing it requires an explicitly chosen physical scale — with residual scale-dependent uncertainty.**

**(ii) A fixed multiple-sigma gate is not a significance level.** Multiple independent literatures converge:

- **Look-elsewhere / global significance.** Gross & Vitells (2011, *Phys. Rev. D* 83, 113008) and Gross & Schneider (2018, *NIM A* 924, 51–57) establish that in a scan over a parameter space, per-point p-values must be converted to a global p-value via the Euler characteristic of the excursion set of a Gaussian random field. **A local 3σ is not a 3σ discovery.** Lit & Shepherd (2023, *Eur. Phys. J. C* 83, 1086, doi:10.1140/epjc/s10052-023-12196-1) give a worked case where the trial factor needed to reach a *global* 3σ is 10¹⁴–10²², and conclude the thresholds customary in the field "need to be far higher".
- **Spatial FDR is not a local significance statement.** Sun, Reich, Cai, Guindani & Schwartzman (2014, *JASA* — PMC4310249) build FDR control for point-wise and cluster-wise spatial signals. A 2026 EGUsphere critique ("The Stippled Gridpoints are Statistically Significant", preprint, Tier C preprint) makes the point sharply: FDR is a *set-level* property, and reading an FDR-corrected map pointwise can be *more* permissive than uncorrected testing — "FDR-based significance should not be interpreted as a local measure of statistical significance."
- **GPR-specific, and directly on point.** Bräu & Rial (2019), "Estimation of False Alarms Rates for GPR Detection using the Euler characteristic of Gaussian Random Fields": *"Because of spatial correlations caused for example by the detection algorithm and heterogeneous soils it is not enough to use only statistics of individual pixels in the decision map."* They estimate the number of false alarms from the Euler-Poincaré characteristic of stationary Gaussian random fields, **with parameters estimated from only a small target-free area in the data.** That is the method the engine should adopt: estimate the null distribution empirically from background, then report a false-alarm *rate*, not a σ.

**Conclusion:** the legacy finding is corroborated in general shape and is, in fact, the *textbook* failure mode. A 3σ gate on a correlated lattice is a heuristic knob whose effective false-alarm rate is unknown and lattice-dependent.

---

# Q3. Dipole vs monopole, and the dipole/cavity confusion

## 3.1 Why metals give opposite-sign lobes

**The physics is unambiguous and is the standard treatment.** A conductor in a time-varying primary magnetic field develops eddy currents that, by Lenz's law, **oppose the change in flux** (Gans 1989; Barrowes et al. 2019). The resulting secondary field therefore:

- is **antiparallel to the inducing field** in the induction limit (i.e. it acts as a mirror of the primary, negative in-phase component);
- produces a **two-lobed** spatial signature: directly over the target, the secondary field cancels the primary (negative anomaly); on either side, it reinforces (positive anomaly).

In the magnetometry analogue this is textbook: for an induced-magnetised sphere, *"Above the sphere, the anomalous magnetic field, Fa, now points in the opposite direction as the Earth's main field … On either side of the sphere, the anomalous field points in the general direction of the main field and thus reinforces it"* (University of Nevada Las Vegas teaching notes, Tier C). In EM modelling this appears as **negative in-phase** for permeable bodies and **negative diagonal entries** in the fitted equivalent-dipole polarisability matrix — e.g. a synthetic case yielding mxx = −0.649 ± 0.009, myy = −0.648 ± 0.008, mzz = −0.635 ± 0.014, i.e. an induced moment of magnitude ≈ 1 in all three principal directions and antiparallel to the primary (OSTI report on estimating dipole polarisabilities and object centre location, <https://www.osti.gov/servlets/purl/917339>, Tier A/government; authors not captured in retrieval). Noh et al. (2016, *GJI* 204(3), 1550) state it as a *direct indicator*: *"a negative response with little frequency dependence is a direct indicator of a magnetic object."* Rai & Verma (1982, *Geophysics*, permeable-sphere interpretation of horizontal-loop EM) show that in-phase and quadrature anomaly amplitudes **and the anomaly half-width** jointly carry the target parameters — i.e. a dipolar profile's *shape* is informative but jointly constrained.

**Practical consequence:** the two lobes of a metal target are a *direct, expected consequence of it being a metal target.* They are not a separate anomaly class. Any taxonomy that promotes "dipolar-response" to a class alongside "metallic-like" is **double-counting**: dipole is a *shape* attribute of metal, not an alternative to it.

**Why a lobe pair can also appear from geometry/orientation rather than magnetism.** Butler et al. (1998) document, for a magnetometer, that a 155-mm projectile aligned ~45° to the Earth's field yields a **dipolar** total-field anomaly of ~240 nT, whereas the same object oriented ~90° to the field yields a **monopolar** anomaly of only ~110 nT. Same object, opposite-sign character, depending purely on orientation relative to the inducing field. For EM the analogue is the primary field's spatial gradient across the target, which flips the sign of the in-phase response depending on which side of the coil's field null the target sits.

## 3.2 What a genuine void looks like by comparison

In GPR, a void also shows **opposite signs** — but for an entirely different reason and with different structure:

- Top boundary: soil (ε≈9) → air (ε=1), reflection coefficient ≈ **+0.5**.
- Bottom boundary: air → soil, reflection coefficient ≈ **−0.5**.
- So a cavity gives a **positive-then-negative** pair of reflections with a time separation equal to twice the void's traversal delay at air velocity.
- Small voids (< ~½ pulsewidth of delay) have their two reflections **superimpose** into a single enhanced pulse — the "bright spot" — with **no visible two-lobe structure and no recoverable thickness** (Nobes 2017, *NDT&E International*; Kofman et al. 2005).

**Therefore the dipole/cavity confusion is physically real and severe:**

| | Metal target (EMI) | Air void (GPR) |
| --- | --- | --- |
| Mechanism of sign change | Induced moment antiparallel to primary | Reflection coefficient sign flip at two interfaces |
| Structure | +/− lobes flanking a central negative, with a null roughly over the target | + top reflection, − bottom reflection, time-separated by 2×traversal |
| On a coarse lattice | Two adjacent sign regions | Two adjacent sign regions |
| Recoverable quantitative handle | Half-width and quadrature/in-phase ratio (Rai & Verma 1982) | Two-way time separation — **only if the void is thick enough relative to pulsewidth** |

**They are the same observable at the resolution a consumer gridded scan provides.** Nobes (2018, "Interpretation pitfalls to avoid in void interpretation from ground-penetrating radar imaging") documents that voids are *routinely* misidentified, that non-voids are misinterpreted as voids, that voids *do* have strong top/bottom reflections, and — critically for our ticket — that features "identified as a void based on **incomplete data**" are a documented failure mode. Persico et al. (2024) close it off: *"there is no mathematical method that can verify a detected target as a cavity."*

**On OKM's own account of the same confusion.** The Rover C4 / Rover UC manuals (Tier D) instruct the operator to distinguish exactly these cases by the number of lobes: *"The signature consists of both a positive signal (red) as well as a negative signature (blue) right next to each other"* (ferromagnetic); *"only a negative (blue) signal"* (non-metallic / void); *"only a positive (red) signal"* (non-ferrous). **The vendor's own taxonomy makes "dipolar" a sub-case of "ferromagnetic", not a peer class.** That is a strong, independent argument that the legacy system's four-way taxonomy is mis-specified.

---

# Q4. Depth estimation reliability

## 4.1 The fundamental resolution limit

- **GPR vertical resolution is ~λ/4** and degrades with depth via wavefront spreading (Wunderlich et al. 2022; Leach 2021). Leach's practical rule of thumb for 400/350 MHz: **for every 30 cm of depth, an object must increase in size by 2.5 cm to remain visible.**
- **EMI depth of investigation is set by coil spacing and frequency, and gives an *integrated* apparent value, not a depth.** Rasmussen (2024, *EGUsphere* preprint) notes FDEM "can hardly achieve a resolution finer than the meter scale" with a typical 1 m² footprint, and that in conductive soil *"most of the signal at higher frequencies is conveyed … into the topmost layer … decreasing the depth of investigation."*
- **Signal falls as ~1/r⁶ for induction-balance locators** (Lancaster, *The Electronics of Search*, Tier C), meaning amplitude, not just resolution, degrades catastrophically with depth. A 4× diameter target has 64× the signal of a 1× target.

## 4.2 The "bifurcation" / target-merging phenomenon

This is well established in the EM/GPR literature and has a standard name: **anomaly coalescence / spatial resolution limit**.

- **Footprint-anchored rule.** Andersen & Auken (2005), "Airborne electromagnetic footprints in 1D earths": 3-D model results *"suggest that resistive targets must be separated by roughly the footprint size if their anomalies are to be resolved completely."* They also show FDEM footprints are several times larger than the traditionally quoted inductive-limit values — for an HCP system the in-phase footprint exceeds **10× the flight height** at low induction number. **So the merging threshold scales with the system footprint, which for a handheld scanner is metres.**
- **Coil-spacing-anchored rule, inductive configuration.** Gupta, Kakirde & Negi (1988, *IEEE TGRS* 26(2), 187–194, doi:10.1109/36.3020): *"the inline configuration can electromagnetically resolve the individual conductor only when the separation between them is greater than or equal to transmitter-receiver separation. … broadside configuration can relax such a limit and resolve the two conductors even when the separation between them is half of the transmitter-receiver separation."* **This is the cleanest published statement of the "2σ"-shaped rule we need**: resolution requires separation ≥ 1 sensor dimension (inline) or ≥ ½ (broadside).
- **Interaction is not just blurring — it biases depth.** Duckworth & Clement (2001, *Geophysics*): as conductors approach, horizontal-coplanar per-conductor responses progressively *weaken*; vertical-coincident responses first *increase* then *decline* as the anomalies merge; after merging *"both coil systems record an expected strong increase of response which exceeds the response when the conductors are in contact."* And decisively: *"mutual inductive interactions cause **significant variations in the depth estimates** provided by horizontal coplanar coils. Depth estimates provided by vertical coincident coils are always **smaller** than the true target depths."* **So two targets closer than one footprint do not merely blur into one — they produce an amplitude that exceeds a single target's, and a biased depth.** That is precisely a bifurcation-like behaviour in the response amplitude.
- **Direct coalescence observation.** Schamper et al. (2022) modelling: *"the individual EM responses of the two bodies merged into a single EM anomaly when the spacing became very small (**coalescence phenomenon**)."* At 30 m spacing the VCP residuals no longer showed two maxima.
- **Signal-level definition of resolution.** Ren et al. (2023, *Front. Mater.* 10:1110834, doi:10.3389/fmats.2023.1110834) formalise it: two particles are indistinguishable when their peaks merge and amplitude deviates by more than 10% of the single-particle amplitude, i.e. **"the minimum distance between two distinguishable particles."** They show the limit worsens with coil radius. A general-purpose, dimensionally explicit definition of exactly the legacy system's "bifurcation" observation.
- **Blind source separation is needed to unmerge — and it is imperfect.** Hu & Collins (2004) pose multiple close objects as a blind source separation problem and compare 2nd- vs 4th-order statistics, "analys[ing] the strengths and weaknesses of each approach". Collins, Gao & Tantum (2002): on heavily cluttered sites *"the measured EMI signal consists of a weighted sum of responses from each anomaly."* Schofield, Hu & Collins (2003) show weighted combinations reproduce the merged response and propose algorithms to detect overlapping objects.
- **In GPR the same phenomenon appears as "interfering hyperbolas"** from closely spaced vertical structures at different depths, and requires numerical modelling to disambiguate (Hill & Nunn, *Int. J. Min. Sci.*, 2025, doi:10.1007/s40808-025-02676-6).

**Interpretation for the ticket.** The "2σ of separation" rule is a real and published phenomenon; the published *anchors* are sensor-footprint and coil-spacing multiples, not σ. A σ-based separation rule is a **device-calibrated proxy** for footprint and will be wrong if the walk speed, sample rate, or probe height changes. If the engine keeps a σ-based rule it should document it as calibrated-to-footprint and state the footprint it was calibrated for.

## 4.3 Honest error bars on depth

**For GPR (the best-understood case):**

- Wunderlich et al. (2022, *Remote Sensing* 14(15), 3665) — best automatic method: RMS velocity error 0.021 m/ns vs manual; manual-vs-manual mean error 0.004 m/ns, max 0.019 m/ns; **derived depth error ≈ 7 cm at the surface rising to ≈ 22 cm by 80 ns two-way time, which is *">400% larger than the vertical resolution of approximately 5 cm"* provided by λ/4.** Phase-pick error alone contributes 0.01–0.02 m.
- Wunderlich et al. (2024, *Remote Sensing* 16(21), 4080) — depth errors are dominated by the **velocity model, not the picking**. Assuming a 1-D or constant-velocity model instead of a 3-D velocity model produces *"about 0.5 m at 20 ns and up to 2 m at 80 ns"* of depth error; even a modest ±0.05 m/ns velocity-model error is *"comparable to the maximum variation in the 3D model."*
- Al Hagrey (*Archaeometry*, doi:10.1111/arcm.12214): hyperbola fitting *"produced some unexpectedly high subsurface signal velocity estimates"*; CMP gathers gave better results. **Hyperbola fitting for velocity is not trustworthy.**
- Patsia & Giannopoulos (2023, doi:10.3997/2214-4609.202320161): hyperbola fitting is *"an ill-posed problem, where many different combinations of medium velocity, target depth and radius can lead to similar hyperbolic signatures"*; even **with known velocity, radius cannot be estimated reliably**.
- PAS 128:2022 (see below) sets the *industry* vertical tolerance.

**For cavities specifically:** Persico et al. (2024) found apparent cavity thickness ≈ 20 cm vs a true value ≈ 2× that. Cave thicknesses are systematically **under**estimated without a velocity-aware time–depth conversion.

**The industry standard for depth error — PAS 128:2022 (BSI), Table 1:**

| Level | Meaning | Horizontal | Vertical |
| --- | --- | --- | --- |
| QL-A | Verified by inspection (trial pit / chamber) | ±50 mm | ±25 mm |
| QL-B1(P) | Position **and depth** detected by **multiple** techniques (GPR + EML) | ±150 mm or ±15% of depth, whichever is greater | **±15% of detected depth** |
| QL-B2(P) | Position **and depth** detected by **one** technique | ±250 mm or ±40% of depth | **±40% of detected depth** |
| QL-B3(P) | Horizontal position only, one technique, **no confidence in depth** | ±500 mm | **Undefined** |
| QL-B4 | Assumed route; surveyed but **nothing detected** | Undefined | Undefined |

Source: BSI (2022), *PAS 128:2022 Underground utility detection, verification and location. Specification*, Table 1 and Annex B (Table B.1). Corroborated in Gowan et al. (2019), *Proc. ICE Municipal Engineer* 173(4), 218–…, doi:10.1680/jmuen.18.00055.

**An important and humbling meta-finding from Gowan et al. (2019):** they audited ~50 trial pits and found that **the vertical accuracy promised at QL-B1 (±15%) was rarely achieved**, while QL-B2 tolerances were usually met; and they recommend *"a differentiation … be made between accuracy and confidence"*, because two techniques agreeing raises **confidence that something is there**, not **accuracy of its position**. This is directly on point for an engine that wants to cross-validate acquisitions: **agreement between two acquisitions is not a depth measurement.**

## 4.4 Verdict on "carry device-reported depth verbatim and never derive depth"

**The literature strongly supports this decision — with one essential qualification.**

Supported:
- A single-technique, non-migrated, non-velocity-calibrated depth reading is at best a QL-B2 quantity at ±40% of depth, and at worst (device soil-keyed, no velocity model) has no defensible accuracy class at all.
- Every error source in GPR depth estimation (velocity model, phase pick, time-zero, target radius) is present *and larger* in a device with no velocity model and no waveform.
- OKM's own documentation makes depth a function of the operator-selected soil setting, i.e. a **prior, not a measurement**. Carrying it verbatim without labelling is the main hazard.

The qualification the literature demands:
- **"Verbatim" must mean "verbatim *and explicitly attributed*".** PAS 128's own drawings label depths as "0.15 m **Assumed**" — the word "assumed" is load-bearing, and the drawing also carries an explicit note that *"100% detection and accuracy cannot be guaranteed."* The engine must carry a provenance field distinguishing **measured** from **device-estimated** from **operator-asserted**, and must not render a device-estimated depth in the same visual weight as a measured one.
- **Deriving our own depth is worse than carrying a bad one** *unless* we have a calibrated velocity model and a time-zero, which a scalar-channel device does not provide. So: correct call, and the reason is stronger than "we can't be sure" — it is that we would be inverting a measurement whose physical quantity we have not established.

---

# Q5. Boundary effects

Our corpus has a target in the last scan line, incompletely captured. The literature is unambiguous that edge-of-coverage behaviour is systematically wrong, in a *known direction*, and that the practitioner protocols exist to prevent it.

## 5.1 Targets near the edge of coverage

- **The far field extends beyond the survey.** Oldenburg et al. (2019) showed a 1-D inversion of a vertical conductor produces a **"drooping trouser leg"** anomaly at both ends, *"because the detection system can sense the presence of a large conductive anomaly even when it is not directly above it."* This is precisely the mechanism that pollutes the edges of a finite grid: the response at the last line is contaminated by whatever is outside it.
- **Off-end ghosting.** Ellis (1998) found 1-D inversion recovers local features of a real anomaly layer but *"distortions would occur near the edges of the anomaly"* and that data misfit cannot signal the presence of 3-D effects. Silic et al. (2018) simulated an "off-end effect" where the system approaches a large conductor without reaching it, and **1-D inversion generates an independent 'ghost' conductor**.
- **Edge artefacts imaged as deep conductors with inverted horseshoe shapes.** Ley-Cooper, Macnae & Viezzoli (2010), "Breaks in lithology: interpretation problems when handling 2D structures with a 1D approximation": *"Near abrupt edges of an extensive conductive layer, the lateral falloff in AEM amplitudes tends to produce a drooping tail in a conductivity section … edge-effect responses often are imaged as deep conductors with an inverted horseshoe shape."*
- **Direction-of-travel dependence — "herring-boning".** Annetts et al. (2000), "Modelling the airborne electromagnetic response of a vertical contact", *Exploration Geophysics* 31(1–2): flying from resistive onto conductive ground produces an **overshoot** up to 250 m either side of the true boundary at 0.01 ms and 350 m at 10 ms; flying the reverse way produces a **false resistor** of lower spatial extent. Crucially, *"a genuine conductor does not change polarity when the flight direction is reversed"* — so **polarity flips between out-and-back passes are a boundary/direction artefact, not a target property.** Their conclusion: *"the worst-case AEM surveys are single-line and 'racetrack-mode' inline component surveys"*, and *"closely spaced lines flown in opposite directions may be needed for accurate interpretation."*
- **Terrain/relief effects.** Liu & Becker (1990): modest relief doesn't affect phase but amplitude anomalies *"can lead to erroneous estimates of the subsurface depth."*
- **The 2-D assumption violation is formally equivalent.** Hung, Lin, Lee & Weng (2019), "3D and Boundary Effects on 2D Electrical Resistivity Tomography": offline features project onto the 2-D section depending on resistivity ratio, electrode spacing, and distance from the feature to the boundary.

## 5.2 Grid-edge and processing-edge artefacts

- **FFT wrap-around / Gibbs ringing.** Save, Uieda, Barbosa & Chandler (2012), *Nonlinear Processes in Geophysics* 19(2), 291–299, "Grid preparation for magnetic and gravity data using fractal fields": because FFT processing assumes periodicity, edge discontinuities cause ringing *"which will often 'bleed' from one edge of the grid to the opposite edge (wrap-around)"* — so a target near one edge can generate a spurious anomaly near the **opposite** edge. Mitigation is standard: taper, mirror, pad with an extrapolated field, remove a low-order trend first.
- **Edge trimming is standard practice.** Every mature gridding workflow (Geosoft, Minty GridMerge) trims a margin of cells before levelling, specifically because edge cells are unreliable.
- **A more sophisticated method today says explicitly that the classic approach fails at edges.** Breuer et al. (2024–2026, *Geophys. J. Int.* 247(1), ggag305): more challenging separations arise *"where the anomaly is close to the edge of a survey where some of the data required to define the regional field are unavailable"*, and **"a low data misfit from 1-D inversion does not guarantee that the 1-D approximation is valid."**

**Practical recommendations for our incomplete-last-line case, all literature-derived:**
1. **Flag it, do not classify it.** An anomaly whose support is clipped by the survey boundary is a censored observation. Emit a boundary-incompleteness marker and exclude it from the classification vocabulary entirely.
2. **Do not extrapolate into it.** Every method that does (min curvature, IDW, mirror, FFT padding) manufactures values there; kriging's near-zero weights in unsampled regions mean it manufactures nothing but also asserts nothing.
3. **Watch for the mirror artefact.** If any spectral/FFT processing is applied, the last line can produce a false anomaly at the first line. Check the opposite edge.
4. **Require directional consistency.** A genuine compact target's polarity structure should be stable between passes; a boundary artefact's will not (Annetts et al. 2000).

---

# Q6. Characteristic failure modes and confounds

| Confound | Published characterisation | Citation |
| --- | --- | --- |
| **Soil moisture / heterogeneity** | The single largest driver of FDEM variance in the top metre. ECa correlates with soil moisture (rs = 0.78 areal). Moisture **increases EC**, confounds compaction signals, and *"in the presence of conductive soil, most of the signal at higher frequencies is conveyed … into the topmost layer and does not diffuse into the subsoil, thus decreasing the depth of investigation."* | Rasmussen (2024, *EGUsphere* preprint); Pathirana et al. (2023, *Remote Sensing* 15(11), 2932, doi:10.3390/rs15112932) |
| **Compaction / agricultural structure** | FDEM shows high-EC anomalies over tramline compaction from surface saturation — i.e. **tillage furrows read as anomalies**. | Rasmussen (2024) |
| **Mineralisation (ferrous minerals in soil)** | Soil conductivity **and** permeability both affect the response. Laterite/Cambodian soil has dispersive magnetic susceptibility. Soil response magnitude ≥ 100× a minimum-metal mine at 5 cm; ±20% variation from local conditions and sensor lift-off. Permeability values: ordinary soil 1.0006, volcanic rock/soil 1.021, granite 1.076, iron-mining-area rock 1.1. | Das (2005, *IEEE TGRS*; 2007, SPIE 6553); van Verre et al. (2020, *IEEE TGRS*); arXiv:2507.04450 |
| **Ferrous contamination / near-surface metal litter** | Dominant false-positive class. 70.3% of Kaho'olawe anomalies were buried metal, non-UXO. Magnetometer "may detect small ferrous objects at or near the surface better than electromagnetic sensors with large sensor coils." OKM's own manual warns the magnetometer mode *"can also react on metallic trash or contamination laying on the surface or near to the surface."* | Cargile et al. (2004); ITRC UXO-3; OKM Rover C4 manual (Tier D) |
| **Ferrous contamination obscuring deeper targets** | *"For a single piece of clutter and a much more massive UXO immediately below, simulations show almost complete obscuration of the UXO, in both frequency and time domains."* And with two objects at *different depths*, the deeper one cannot be distinguished even at SCR ≈ 20. | O'Neill et al. (2005), "EMI obscuration of buried UXO…" |
| **Utility lines / infrastructure** | "Infrastructure in survey areas is unavoidable and can cause characteristic distortion of semi-airborne EM data leading to artefacts in inversion models." Conductive infrastructure can produce spurious **deep** anomalies reaching >400 m, or a spurious resistive body directly beneath — depending on how the infrastructure is modelled. | Treppke, Becken & Rochlitz (2024) |
| **Instrument / electronics artefacts (operator-sourced, vendor-acknowledged)** | OKM's own list: proximity to a radio station, lightning, high-powered electrical conduits, airport ground radar, high-powered speakers, magnets; and *"these errors … can be quickly identified by a single strong spike within the scan often turning the entire scan a dark orange or red color."* OKM also warns the probe **self-rebalances and can make an object disappear** if left within it. | OKM Rover UC / Rover C4 manuals (Tier D) — note: Tier D, but it is the vendor documenting its own failure modes, which is admissible as evidence of failure modes and inadmissible as evidence of performance |
| **Probe height / liftoff** | Explicitly identified as a soil-response modulator of ±20%; also a detector-height sensitivity in EMI | van Verre et al. (2020); Bruschini (2004) |
| **Instrument drift** | Named as a required check in FDEM practice | Rasmussen (2024), citing De Smedt et al. (2016) |
| **Walk speed / probe orientation** | OKM: *"Walk all scan lines at the same speed. Keep the probe vertical and avoid pivoting and swinging."* Archaeological GPR: higher speeds *"could certainly introduce noise due to the inevitable increase in antenna tilting."* Directional dependence of sensors also causes heading error producing banding (below). | OKM manuals (Tier D); MDPI *CIMNiL* 6(3), 154 (2023) |
| **Cell/terrain / relief** | Amplitude anomalies from modest relief give *"erroneous estimates of the subsurface depth"* | Liu & Becker (1990) |
| **Biogenic / ploughing effects** | *"A similar banding pattern is often encountered in archaeological fields when the soil is used for agriculture; in such cases, directional filters are able to remove the ploughing effect."* | *CIMNiL* 6(3), 154 (2023) |

**The provider-side confound the engine cannot see at all:** OKM's own manuals state that whether a find is made *"depends on a huge number of factors … Variable soil properties can and will hamper and alter ultimate scan measurements. Areas with an extreme amount of ground water, varying clays, sands and wet soils make scanning more difficult and may reduce the maximum depth capabilities of the detection equipment, regardless of make or model."* **There is no soil-condition metadata in the data stream.** Every depth figure and every amplitude threshold is therefore conditioned on unrecorded, unrecoverable state.

---

# Q7. "Consistent with" vs "identified as"

## 7.1 There is a standard formulation, and it is codified

**PAS 128:2022 (BSI) is the clearest, and it is the right model to copy.** Its vocabulary:

- Survey types: **D** (desktop records search) → **C** (site reconnaissance) → **B** (detection) → **A** (verification/exposure). A hierarchy where *finding a record* is a strictly weaker claim than *seeing the thing*.
- Every **segment** of a feature is graded individually by quality level (QL-A/B1/B2/B3/B4/C/D), reflecting method used, accuracy achieved, post-processing, and supporting data.
- **Depth is graded separately from position.** QL-B3 explicitly has horizontal position but *"Undefined"* vertical accuracy. QL-B4 is *"Positional location has been **assumed**."*
- On drawings, depths carry an explicit qualifier: "0.15 m **Assumed**", and features are labelled "Metallic Target" / "Radar Target" / "Possible Target" — never with a material name the instrument could not determine.
- The definition of a non-utility anomaly is the key sentence: *"An **anomalous feature** is an **unidentified subsurface area** evident within the radar data that **differs in response to its surrounding area**. Examples of anomalous features include voiding, heavily saturated ground, buried tanks and demolished building foundations."* Note: (a) *unidentified*; (b) defined by *response contrast*, not cause; (c) the examples are dominated by **geology and man-made intrusions**, not by metals.
- And the explicit statement practitioners must honour: *"Geophysical data by itself does not allow identification of the utility detected. The identification of the utility is achieved through a combination of on-site interpretation from both GPR and EML surveys together with on-site reconnaissance and correlation with utility records."*
- Mandatory deliverable content includes: *"a description of how successful each detection methodology proved to be and a plan showing any areas where these detection methodologies were not successful"* and *"a list of buried features and obstructions other than utilities detected."* **Non-detection and non-targets are first-class reportable outputs.**

## 7.2 The peer-reviewed uncertainty-rating vocabulary

- **Ormerod et al. (2017), "Teaching Uncertainty: a new framework for communicating unknowns in traditional and virtual field experiences", *Scientific Contributions*:** a six-category ranking for both observations and models — **No evidence · Permissive · Suggestive · Presumptive · Compelling · Certain** — with models barred from "no evidence" and "certain". Definitions are exactly the distinctions we need: *Permissive* = "cannot be ruled out, but it is also not the only available solution"; *Suggestive* = "positive evidence … but the evidence also allows the possibility for other inferences"; *Presumptive* = "presumed in the absence of further information … more likely right than wrong"; *Compelling* = "necessarily based on a preponderance of positive evidence."
- **Erharter, Lacasse & Tschuchnigg (2024), "A consistent terminology to communicate ground-related uncertainty", *Canadian Geotechnical Journal*:** a three-step reporting discipline — (1) if it is a fact, say so with no hedging; (2) otherwise assess and **state the level of confidence**, and if confidence is low–medium, say so *and state how higher confidence could be obtained*; (3) only at high confidence, use calibrated likelihood/quantity terms. They also document the "directionality of verbal uncertainty expressions" phenomenon (after Honda & Yamagishi 2006; Teigen & Brun 1999): **negatively-framed hedges ("it is unlikely that X") pull attention to the complement.** For a detector that reports many anomalies, this matters — always report the positive-likelihood form for the candidate and reserve negation for the background.
- **Petroleum geoscience: the DHI Index.** The DHI Consortium's apparatus (GeoExPro 2012) exists precisely because *"not all anomalous amplitude events are DHIs"*; they build a weighted index of positive characteristics and require a *preponderance* before accepting a feature as a DHI, and they note that "care should be taken that not all amplitudes are DHIs and not all geologic settings exhibit DHIs equally." That is the same epistemic structure as our problem, solved with an explicit evidence-weighting device.

## 7.3 Recommended vocabulary mapping

| Our intent | Defensible phrasing | Not defensible |
| --- | --- | --- |
| Anomalous region detected | "Anomalous response, exceeding the local background estimate" | "Object detected", "Target detected" |
| Looks metallic | "Response **consistent with** a metallic target", with the supporting feature named | "Metallic object identified", "Metal confirmed", "Class: metallic" |
| Looks like a cavity | "Response **consistent with** a void or cavity; cavity not confirmed" | "Cavity identified", "Void confirmed" |
| Residual catch-all | "Unclassified response" / "response not consistent with the metallic or void templates" | "Geological-like" (asserts cause) |
| Depth | "Device-estimated depth (operator soil setting: X). Not independently verified." | A bare number in a table, rendered identically to a measured value |
| Overall | "Candidate" / "**Candidate** anomaly" | "Find", "Discovery", "Treasure" |
| Confidence language | "presumptive" / "suggestive" per Ormerod et al. | "certain", "confirmed", "no doubt" |

**The one structural recommendation with the strongest literature backing:** adopt PAS 128's *per-segment graded confidence* idea, and grade on **axes that are actually independent** — Gowan et al. (2019) showed empirically that blending two techniques raises confidence-in-existence without raising positional accuracy, and therefore recommends separating the two. Our engine should never let evidence about *what* an anomaly is raise its confidence in *where* or *how deep*, and should say so in the output.

---

# Q8. Prior art in three algorithmic areas

## 8.1 Multi-acquisition registration, including the 90° case

### Is there a standard for the perpendicular case? Yes — and it is not optional.

**Physics/method statement.** *"It is useful, in the absence of precise information on buried structures, to acquire the profiles in two perpendicular directions; this allows for correct localization and better geometrical definition of anomalies, **especially in the presence of depolarizing objects**."* And on geometry: *"the parallel line arrangement is effective in identifying the approximate location of the anomalous body, while the **orthogonal line arrangement is optimal for identifying a target body near the line intersection**."* — *CIMNiL* 6(3), 154 (2023), peer-reviewed review of archaeological geophysical techniques.

**The EM-specific reason, stated as a design rule.** GeoSci.xyz UXO survey-design guidance (Tier C): *"The excitation of a buried target occurs parallel to the inducing field. Thus in order to accurately recover polarizations … we must excite the target significantly from **multiple angles**. Ideally, the target would be excited from **3 orthogonal directions** … For single loop transmitters … **perpendicular survey lines have historically been added** to excite targets from multiple sides."* Two directions is the practical minimum; three is the ideal.

**The direction-dependence result that makes single-direction data unsafe.** Annetts et al. (2000): genuine conductors do not change polarity with flight direction, but boundary/step responses do — flying toward a conductive region creates a false conductor, away creates a false resistor, of large enough amplitude to *"mask the response of a genuine conductor (1.0 Ω·m) at a depth of 50 m."*

### The professional standard for levelling and merging overlapping grids

- **Tie lines + micro-levelling.** Minty: micro-levelling uses directional + wavenumber filtering to attenuate line-parallel variations, *"has low discrimination and reduces the amplitude of many true field variations"* — so micro-levelled grids are unsuitable for quantitative work; prefer tie-line-levelled channels for inversion.
- **Shift/scale/tilt as a joint inverse problem.** Minty GridMerge: magnetic data generally need a level shift, radiometric need shift *and* scale; tilt may be needed. Three preconditions: grids must be interconnected by overlap; a baseline must be specified; there must be sufficient overlap and dynamic range. And the honest warning: *"it is possible to have an almost perfect fit between individual grid pairs, yet a poor fit to the merge"* when one grid is tilted — the inconsistency is distributed across all overlaps and it is not obvious which grid is at fault.
- **Merge strategies.** Priority-ordered re-sampling (fast, QC-only) vs **feathered merge** (residual differences propagated into overlaps by distances proportional to wavelength — "produces a seamless join", but compute-intensive).
- **Standard edge handling.** Trim grid edges (Minty trims 5 cells) before levelling; Geosoft's `Merge Sorties` DC-shifts the second segment by the mean difference over the overlap and tapers the overlap before merging — and explicitly does **not** cross-level flight and tie lines, reporting repeats and dummies instead.
- **Pas 128's requirement**: positioning of a GPR transect *"shall be recorded using either GNSS or total station so that the survey transect can be georeferenced at an absolute accuracy of ≤100 mm"*, and infill areas that could not be covered *"shall be clearly marked on the deliverable drawing."*

### The failure modes of registration — the reason the 90° case is hard

- **Per-traverse GNSS offset errors are catastrophic and are the *actual* source of linear artefacts.** Petković, Cvetkov & Sretenović (2014): with GPS-acquired positions, *"when starting each new traverse, the GPS re-started its communication with the satellites"*, giving a common error of ~2 m per traverse. With 1 m traverse spacing, *"this error can result in the **complete flecking of the anomalies**."* Corrective processing: zero-mean/zero-median traverse levelling (**unsuccessful** in their test), "decorrugation" (low-pass moving average along and across traverse, **successful**), or nonlinear interpolation (local polynomial, **best**). Their recommendation: use a total station for the polygon corners because *"current commercial navigation systems do not satisfy the accuracy required"*; and *"if large areas are to be explored, it is desirable to divide them into a series of smaller exploration polygons with margin lengths not exceeding 25 m."*
- **Heading error / banding.** *"The bidirectional acquisition mode causes typical noise, resulting in a striped pattern as the data are shifted along the progress direction. This effect is often referred to as the 'heading error'."* Quick correction: averaging along each line. This is precisely the artifact a naive orthogonal merge will amplify, because each orientation has its own heading-error signature.
- **Parallel beats zigzag.** Petković et al.: *"The best results … those with the absence of linear anomalies were observed when using the **parallel** method of acquisition, regardless of how the traverses were oriented"*; zigzag *"requires additional data processing such as: adjusting the traverses of the mean or median to a common value, decorrugation or the use of non-linear interpolation."* **For a consumer scanner this is directly actionable: prefer separate parallel out-and-back passes over a single zig-zag, precisely because the latter requires levelling that we cannot verify.**
- **Georeferencing accuracy for multi-channel GPR** (Sensors-adjacent, 2020, doi:10.3390/rs12292945): GNSS-RTK with 1-PPS gave vectorised network localisation errors of ±0.052 m; GPS-only produced *"characteristic faults along the linear objects"* from poorly adjusted adjacent trajectories. **This confirms that registration quality, not survey design, sets positional accuracy** — and it is the part a consumer scanner has least of.
- **PUMA (TSA PAS 128 accreditation) requires** that the method statement declare survey types and *the expected achievable quality level*, and that deliverables contain *"a polygon representing where any search sweep has been undertaken."*

### What this means for the engine

There **is** a standard (tie lines, baseline, shift/scale/tilt by overlap, priority + feathering, edge trimming, absolute georeference at ≤100 mm) — but it presupposes (a) positional logging and (b) *overlapping* areas. A re-walked orthogonal grid has **no overlap** and **no position log**, so none of the standard machinery applies. The honest fallback that the literature does support for that situation is the one OKM's own manual prescribes: **repeat the scan and check that the anomaly does not move and its shape does not radically change.** That is a *reproducibility* test, not a registration method, and it is a much weaker claim than "registered." The engine should not call a 90° combination "registered"; it should call it "cross-checked", and record whether the two passes agreed in position within a stated tolerance.

## 8.2 Robust anomaly detection on a gridded lattice

### Separating signal from a sloping/curved geological background — the established canon

| Method | Reference | What it does | Known weakness |
| --- | --- | --- | --- |
| **Optimal Robust Separator (ORS)** | Wessel (1998), *Math. Geol.* 30(4), 391–408, doi:10.1023/A:1021744224009; refined in Wessel (2015) | Iteratively estimates a regional field as the median of the raw data, so the *residual* excludes the median level; runs over a range of filter widths and returns a median residual plus **MAD-based uncertainty bounds** | Result varies with filter width; "most regional–residual techniques give non-unique results and provide no estimates of the uncertainty" — this one's virtue is that it *does* |
| **Directional Median (DiM)** | Kim & Wessel (2008) | Divides the filter circle into N bow-tie sectors, takes the median of each, returns the **lowest** — *"prevents DiM filtering from choosing the biased medians near the features on a sloping regional trend, which is a serious artifact of standard median filtering"* | None stated for our case; the sector count and width are free parameters |
| **Robust polynomial trend removal** | Beltrão, Silva & Costa (1991), *Geophysics* 56(1), 80–89, doi:10.1190/1.1442960 | Fits the trend only to points selected as a human interpreter would (low horizontal gradient, low 2nd vertical derivative) | Depends on selection heuristics |
| **U-spatial statistic** | Cheng (1999) / Cheng, Agterberg & Bonham-Carter (1996), *J. Geochem. Explor.* 56(3), 183–195, doi:10.1016/0375-6742(96)00035-0 | Multiplicative cumulant power (U-value) over a search circle; takes the **maximum** U over radii | Sensitivity to irregular sampling; often returned zero max-U |
| **C–A fractal** | Cheng, Agterberg & Ballantyne (1994), *J. Geochem. Explor.* 51(2), 109–130, doi:10.1016/0375-6742(94)90013-2 | log–log break in concentration–area curve gives multi-level anomaly thresholds | Needs gridded data; thresholds are fit-dependent |
| **Local neighbourhood median/MAD** | Zhang et al. (2013), *J. Geochem. Explor.* — "Identification of weak geochemical anomalies using robust neighborhood statistics coupled with GIS" | local MEDIAN/MAD discriminate backgrounds; **"the resulting neighborhood statistics is influenced by the size of neighborhood"** | Same scale-dependence problem |
| **Median + 2·MAD (EDA)** | Tukey (1977); Carranza (2010); Reimann & Garrett (2005) | Classic robust thresholding | **Fails on weak anomalies** — Reiman-type studies find median+2MAD maps only strong anomalies, missing the buried/covered cases where the interesting targets are |
| **Local polynomial regression** | Petković et al. (2014) | Best of the tested methods for removing traverse-parallel linear artefacts | Loses real high-frequency content |

### Choosing a physical scale to threshold at

The literature's honest position, across every source, is that **the separation scale is the dominant free parameter and there is no automatic way to choose it.**

- Wessel: *"the separated results vary with the choice of filter width. Such variations are spatially distributed"* — and his remedy is to *report* the spread as per-point uncertainty, not to resolve it.
- Exploration geochemistry has spent four decades on this and the comparative reviews conclude bluntly: *"this implies that there is **no universally accepted 'rule of thumb'** for choosing the most suitable spatial interpolation techniques for specific scenarios"* (spatial interpolation analogue, PMC11226832), and *"there is no universally perfect interpolation method, testing their accuracy on the specific data is crucial."*
- For **thresholding** specifically: Reimann, Filzmoser & Garrett (2005), "Background and threshold: critical comparison of methods of determination", *J. Geochem. Explor.* (PMID 15993678) is the reference for the fact that threshold choice is method-dependent and that reported thresholds are not comparable across methods.

**However**, there is one *physical* handle that is not available to potential-field/geochemical work but **is** available here, and it is the strongest methodological recommendation in this whole document:

**The target is a metal conductor; its response is compact and has a known spatial scale set by the sensor footprint.** So the scale is not free — it is set by geometry we can measure (probe length is published: OKM Rover C4 standard probe 445 mm, shaft 35 mm, LED orbit 65 mm; Super Sensor 960 mm × 50/65 mm, per the Rover C4 manual, Tier D). Two survey lines a few tens of cm apart carrying a real anomaly should correlate; a geological or instrumental artefact should not. **This gives an empirical scale-selection procedure that does not require a-priori target size: scan a range of filter/separation scales and select by which scale maximises out-of-sample reproducibility across independent acquisitions.** That is testable, it is cheap, and it directly attacks the Wessel/Cheng scale-dependence problem by making the data choose the scale rather than the analyst.

### Thresholding: use an empirical null, not a σ

The canon for "what threshold" is now well settled in the statistically-uncertain-signal literature and it is not a σ:

1. **Bräu & Rial (2019)** — estimate false-alarm rate on GPR detection maps using the Euler-Poincaré characteristic of stationary Gaussian random fields, *"with the necessary parameters estimated from only a small target free area in the data."* Directly on point, directly applicable.
2. **Look-elsewhere / Euler characteristic** — Gross & Vitells (2011), *Phys. Rev. D* 83, 113008; Gross & Schneider (2018), *NIM A* 924, 51–57; Lit & Shepherd (2023), *EPJC* 83, 1086 (trial factors of 10¹⁴–10²² for global 3σ in a realistic search). The excursion-set approach gives a **global** false-alarm probability for a lattice of tests under spatial correlation.
3. **FDR under spatial dependence** — Sun, Reich, Cai, Guindani & Schwartzman (2014), *JASA*, PMC4310249, point-wise and cluster-wise FDR control for spatial signals. **Cluster-wise** FDR is the right granularity here because anomalies are clusters.
4. **Self-calibration** (arXiv:2108.06333) — the cheapest practical approach when you have one dataset: estimate the look-elsewhere-corrected p-value from the *peak height distribution of the data itself*, needing no simulation. **This is the recommended v2 method:** it is data-driven, cheap, and exactly suited to "I have one grid and want an honest number of false alarms per grid."

**The 3σ gate should be retired as a *significance level* and retained, if at all, as a documented *display threshold* with an accompanying, measured false-alarm-per-grid figure.**

## 8.3 Gridding irregularly sampled points

### The standard approaches

| Method | Characteristic | Failure mode |
| --- | --- | --- |
| **Minimum curvature** (Briggs 1974; Swain 1976; Webring 1981) — Geosoft `RANGRID` | Smoothest surface through the data; iterative coarse→fine | *"quickly degrades over areas with **sparse data control** where the grid spacing is smaller than the actual spacing between data points"*; produces **"pimpling"** that shows up in high-frequency-filter products; **"bulls-eye" / "string-of-beads"** for narrow features relative to line direction; clustered data produces "undesirable highs or lows in the more poorly sampled parts"; slow for large datasets |
| **Kriging** — Geosoft `KRIGRID` | Statistical; gives an **error grid**; reduces bullseyes | *"rarely used with geophysical data, which tends to follow a natural smooth surface"*; "statistically under-sampled" geophysical data → careful variogram modelling rarely worth it; slow; **"can lead to edge effects at the limits of the smaller matrix window"** when >500 points; produces **negative values** (hence the "grid the log of the data" option) |
| **Bi-directional gridding** — Geosoft `BIGRID` | Honours features parallel to survey lines | Produces **ellipsoids / ellipsoidal "beads"** for short-wavelength features not aligned with the trend; **cannot work with tie-lines** |
| **Natural neighbour** (Sibson 1981; Sambridge et al. 1995) | Delaunay-based, local, exact at nodes, handles highly irregular distributions, C¹ derivatives | *"produces aliased artefacts around areas of sparse data control when a grid spacing smaller than the actual grid spacing is used"* |
| **IDW / Shepard** | Simple, fast, no variogram | **Bullseyes** — see below; *"cannot interpolate above or below the surrounding data which tends to generate flat areas"*; *"will average out trends and emphasize anomalies (outliers)"* |
| **Triangulation (TIN)** | Exact at nodes, honours breaklines and slope features; represents a surface with fewer points | *"generated surfaces are not smooth and may have a jagged appearance"*; facets sample-dependent; "irregularly shaped polygons, especially on the edges" |
| **Inverse interpolation / regularised** | Tikhonov data-fitting + Laplacian smoothing, Gaussian-weighted operator; **"produced smooth and accurate results without obvious aliasing artefacts"** even when grid spacing ≪ flight-line spacing (501×107 grid at 500 m) | Time-consuming; authors note *"none of established gridding methods are suited to all geophysical data"* |
| **Iterative gridding** (ExploreGeo Technical Note 7) | Exclusion Method (better for closely-spaced stations on isolated or widely spaced lines) or Insert Method (faster, less complicated) | *"This method is more prone to gridding artefacts in areas where data are acquired on relatively close stations but wide line spacing"* |

### The bullseye failure mode, precisely

This is the failure mode most likely to bite a hand-walked scan, and it is worth stating exactly because it is **mathematically unavoidable in the exact interpolators**:

- IDW is an **exact** interpolator: at a sample, weight 1/d^p → ∞, so the surface *must* pass exactly through the sample and fall away from it. **Every isolated sample therefore becomes a local extremum.** The probability of a sample being a local extremum is close to 1; in one measurement it was 83.1%. Because the weight depends only on distance, the field around an isolated sample has *circular symmetry*, and contouring it produces **concentric rings**. Power 4 gives dramatic bullseyes, power 1.5 soft ones; fewer neighbours makes them worse.
- **The cure is to make the interpolator inexact:** add a smoothing distance so the weight at zero distance is finite (`1/(d² + s²)^(p/2)`, with s ≈ 1/10 of mean sample spacing), or equivalently use kriging with a non-zero nugget. **"The trade is exactness for smoothness… If your samples have measurement error, you want an inexact interpolator, because honouring a noisy measurement exactly is honouring the noise."**
- Kriging with a zero nugget is exact and *also* rings, but more weakly. Linear TIN is exact and shows **faceting** instead of rings. Splines are exact and swap rings for **overshoot** near steep changes.
- **Diagnostic, and this is the important bit: "rings around a single sample with none elsewhere usually means that sample is an outlier — check it before smoothing it away."** Bullseyes are worst exactly in the sparsely sampled parts of the map.
- **Independent confirmation:** Engebretson et al. / *GJI* 189(3), 1353 (2012) show "aliasing artefacts (represented by a string of beads) are obvious along the narrow and sharp anomalies in the vertical gradient from the minimum curvature grid", while inverse interpolation does not produce them. The same string-of-beads artefact is documented in Minty: *"enhancement of older, more widely spaced line data has significant artefacts in the form of 'bicycle-chain' or 'string-of-pearls' patterns where the minimum curvature gridded data cannot interpolate sharp gradients from one profile intersection to the next."*

### The rule this implies for OKM scan grids

A hand-walked zig-zag grid is, from the gridding algorithm's point of view, **a clustered dataset with dense sampling along lines and sparse sampling across them** — the exact configuration every method above documents as pathological. Three defensible choices:

1. **Do not grid at all.** Keep the data as a set of 1-D lines, and compute neighbourhood statistics *along* each line using the physical probe footprint as the neighbourhood, never across lines. This is what Petković et al. found worked (decorrugation along and across traverse, then local-polynomial interpolation). It avoids fabricating values in the gaps.
2. **If gridding is required, use an inexact interpolator** (kriging with a non-zero nugget, or IDW with a smoothing distance of ~1/10 mean spacing) and **emit a per-cell support/uncertainty field** so that no anomaly is ever reported without its interpolation uncertainty attached.
3. **Never grid with an exact interpolator** across a sparse direction. Minimum curvature, zero-nugget kriging, and plain IDW are all *exact* and all manufacture local extrema in the gaps — i.e. **they manufacture anomalies that were never measured.**

---

# What this means for the engine's claim vocabulary

## The single decision the literature forces

**Classify the anomaly, never the object.** The strongest published statement available is Persico et al. (2024): *"Currently, there is no mathematical method that can verify a detected target as a cavity."* Every classification in the legacy taxonomy was of the object. That is the category error, and it is not fixable by better features.

## Concrete, literature-backed rules

1. **Every output is a *candidate anomaly*, never a *detection*.** PAS 128 grades by survey type; detection is the *weakest* thing you can claim about something not seen.
2. **Material names require a specific, named measurement.** No published work supports inferring "metal", "void", "gold", "chest", or "tomb" from an uncalibrated scalar channel. Where OKM's own manual says the software *"cannot identify element specific materials, minerals or items that occur naturally in the ground"* (Tier D, but it is the vendor *conceding* the limit), we must concede it too. Use **response-shape descriptors** with the physical feature named: `bipolar-lobed`, `compact-single-sign`, `extended-low-contrast`, `boundary-censored`, `unclassified`.
3. **The dipole class must be dissolved, not kept.** Published physics (Lenz; negative equivalent-dipole polarisability entries; Noh et al. 2016's "negative response with little frequency dependence is a direct indicator of a magnetic object") makes dipole-ness a *consequence* of being metallic — which OKM's own manual already encodes by making the lobe-pair a *sub-case of the ferromagnetic signature*. A cavity also produces opposite signs (opposite-polarity top/bottom reflections). **Therefore "dipolar-response" and "metallic-like" are not orthogonal, and "dipolar-response" and "cavity-like" are not distinguishable at lattice resolution.** Keeping the legacy special case ("dipole misclassified as cavity") is treating a symptom of an ill-posed taxonomy.
4. **Rename "geological-like".** It is the residual class. Calling it "geological" asserts a cause. PAS 128's own examples of anomalous features are *"voiding, heavily saturated ground, buried tanks and demolished building foundations"* — i.e. the residual class in a real professional workflow contains voids, hydrology, and man-made intrusions. Our residual class almost certainly contains voids, hydrology, tillage, mineralisation, ferrous litter, and instrument artefacts. It must be named `unclassified` (or `residual`) and must never be presented as an identification of geology.
5. **Replace the 3σ gate with a measured false-alarm rate.** Per §8.2. Report `n_candidates`, `estimated_false_alarms_per_grid` (from self-calibration or an Euler-characteristic estimate on an empirical null from a background region), and the scale-selection method. A σ in the output is a display threshold, and should be labelled as such.
6. **Never derive depth. Carry device depth only as an explicitly attributed, soil-keyed estimate.** PAS 128's tolerances (§4.3) are the honest frame: a single-technique depth is a ±40%-of-depth quantity at best. Store `depth_source ∈ {device_estimated_operator_soil_setting}` and `depth_verified = false` unconditionally. Render it visually distinct from anything measured. Note in the deliverable, per PAS 128 practice, that *"100% detection and accuracy cannot be guaranteed."*
7. **Carry provenance on every candidate.** PAS 128 requires recording instrument model and serial, operator, calibration method and data, weather, on-site limitations, and available records. It also requires reporting *"a plan showing any areas where these detection methodologies were not successful"* and *"a list of buried features and obstructions other than utilities detected."* **Non-detections and non-candidates are required outputs, not omissions.**
8. **Add an explicit confidence axis, using Ormerod et al.'s scale.** "Presumptive" is the honest ceiling for anything derived from this corpus with no ground truth and no calibrated velocity model. Note also that having two acquisitions agree raises **confidence in existence** without raising **positional accuracy** (Gowan et al. 2019) — so confidence-in-existence and confidence-in-position should be separate fields.
9. **Flag boundary-censored anomalies into a separate bucket, not into the taxonomy.** A candidate clipped by the last scan line is a censored observation (§5). It should carry a `boundary_censored` flag and be excluded from material- or shape-classification, because its lobe count is truncated by construction — which is exactly how a dipole could be manufactured or destroyed at the edge.
10. **Register vs cross-check.** Because a re-walked orthogonal grid has no overlap and no position log, none of the standard levelling machinery (§8.1) applies. Call the operation **cross-checked**, not registered, and report the observed positional agreement between passes as a number.

## Three findings worth escalating to the ticket itself

- **The device's transfer function is undocumented in the peer-reviewed literature.** No characterisation of what an OKM Rover channel physically measures exists outside OKM's own "EMSR" label and a VLF coil-technology string. Every downstream decision — depth handling, threshold scaling, the meaning of "metallic", even whether sign has any physical content — is conditioned on a quantity we have not established. **This is the highest-value follow-up:** if a physical characterisation of one unit exists (even unpublished, even from a dealer technical exchange), it changes more of the engine's design than anything in this literature review.
- **The literature supports a stronger claim than "consistent with": it supports a graded, two-axis claim.** Ormerod et al. plus PAS 128 together give "presumptive/suggestive" on *existence* and a separate accuracy grade on *position/depth*. That is strictly more useful to a user than a single hedge word, and it is standard practice in both a peer-reviewed education framework and a national standard. Adopting it would be a genuine improvement over the legacy system's flat classification.
- **"Consistent with a metallic response" is defensible; nothing stronger is.** If the engine must carry one material-flavoured label, that phrase, with the supporting feature cited, is the ceiling. Given Bruschini's own verdict that even *coarse* classification requires high S/N and a known target set, and Butler et al.'s flat "cannot identify", the honest default should be the **unclassified residual class**, with metallic-consistency offered only where a specific measured feature (e.g. compact bipolar structure with a central sign reversal, stable across passes) is present and even then phrased as compatibility.

---

## Reference list

Peer-reviewed (Tier A/B), with DOIs where verified:

1. Andersen, A. & Auken, E. (2005). Airborne electromagnetic footprints in 1D earths. *Geophysics*. https://epic.awi.de/id/eprint/13669/1/Rei2005k.pdf
2. Ammari, H., Buffa, E. & Nédélec, I. (2013). Characterising small objects in the regime between the eddy current model and wave propagation. *European Journal of Applied Mathematics* 295. doi:10.1017/S0956792523000207
3. Annetts, B., et al. (2000). Modelling the airborne electromagnetic response of a vertical contact. *Exploration Geophysics* 31(1–2). https://aegisgeophysics.com.au/gallery/2000%20Annetts%20et%20al.pdf
4. Barrowes, B.E., Sigman, J.B., Wang, Y., O'Neill, K., Shubitidze, F., et al. (2016). Detection of conductivity voids and landmines using high frequency electromagnetic induction. *IEEE TGRS*. Companion: Barrowes et al. (2016), Carbon fiber and void detection using high-frequency EMI, *Proc. SPIE* 9823, 98230D. doi:10.1117/12.2224584
5. Barrowes, B.E., Prishvin, M., Jutras, G., Shubitidze, F. (2019). High-frequency electromagnetic induction (HFEMI) sensor results from IED constituent parts.
6. Beltrão, J.F., Silva, C.B., Costa, J.C. (1991). Robust polynomial fitting method for regional gravity estimation. *Geophysics* 56(1), 80–89. doi:10.1190/1.1442960
7. Beran, L. (2009). *Classification of unexploded ordnance*. MSc thesis.
8. Bräu, C. & Rial, F.I. (2019). Estimation of false alarms rates for GPR detection using the Euler characteristic of Gaussian random fields.
9. Breuer, et al. (2026). Array effects in electromagnetic surveying: misplacement of anomaly locations in one-dimensional inversion. *Geophys. J. Int.* 247(1), ggag305. https://academic.oup.com/gji/article/247/1/ggag305/8748417
10. Briggs, W. (1974). *Minimum curvature simple cubic with tension*. (Cited in #12.)
11. Bruschini, C. (2002). *A Multidisciplinary Analysis of Frequency Domain Metal Detectors for Humanitarian Demining*. PhD thesis, EPFL.
12. Bruschini, C. (2004). On the low-frequency EMI response of coincident loops over a conductive and permeable soil and corresponding background reduction schemes. *IEEE Trans. Geosci. Remote Sens.*
13. Bruschini, C., van Kempen, L.M., Lochy, J. (2003). Metal target discrimination with a commercial two frequency sensor – Part II: quantitative aspects. *IEEE Trans. Geosci. Remote Sens.*
14. Cheng, Q., Agterberg, F.P., Ballantyne, S.B. (1994). The separation of geochemical anomalies from background by fractal methods. *J. Geochem. Explor.* 51(2), 109–130. doi:10.1016/0375-6742(94)90013-2
15. Cheng, Q., Agterberg, F.P., Bonham-Carter, G. (1996). A spatial analysis method for geochemical anomaly separation. *J. Geochem. Explor.* 56(3), 183–195. doi:10.1016/0375-6742(96)00035-0
16. Collins, L.M., Gao, P., Tantum, S.L. (2002). Model-based statistical signal processing using electromagnetic induction data for landmine detection and classification.
17. Das, Y. (2005). Electromagnetic induction response of a target buried in conductive and magnetic soil. *IEEE Trans. Geosci. Remote Sens.*
18. Das, Y. (2007). Effects of magnetic soil on metal detectors: preliminary experiments. *Proc. SPIE* 6553, 65530E.
19. Duckworth, K., Clement, B.R. (2001). Inductive interaction between closely spaced steeply dipping tabular conductors located in a resistive host. *Geophysics*.
20. Ellis, R.G. (1998). [1-D inversion applicability in multidimensional environments.] *Geophysics*.
21. Engebretson / [author list not captured]. (2012). Gridding aeromagnetic data using inverse interpolation. *Geophys. J. Int.* 189(3), 1353–1366. https://academic.oup.com/gji/article/189/3/1353/609555
22. Everett, M.E. (2010). Theoretical developments in electromagnetic induction geophysics with selected applications in the near surface. *Geophysics* 75(5). https://mtnet.info/division/papers/EMWKSHP_ReviewVolumes/2010Giza/Everett_2010GizaReview.pdf
23. Gans, W.L. (1989). Suggested methods and standards for testing and verification of electromagnetic buried object detectors. NIST IR 89-3915. https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir89-3915.pdf
24. Giannino, F. & Leucci, G. (2022). *Electromagnetic Methods in Geophysics*. Wiley. ISBN 9781119770985.
25. Gowan, et al. (2019). Improved underground utilities asset management – assessing the impact of the UK utility survey standard (PAS128). *Proc. ICE Municipal Engineer* 173(4), 218. doi:10.1680/jmuen.18.00055
26. Gross, N. & Vitells, N. (2011). Search for oscillations in the cosmic-ray electron-positron annihilation rate. *Phys. Rev. D* 83, 113008.
27. Gross, N. & Schneider, U. (2018). Incorporating the look-elsewhere effect into global significance in searches for new physics. *NIM A* 924, 51–57.
28. Gupta, O.P., Kakirde, S.T., Negi, J.G. (1988). Scale model experiments to study low-frequency electromagnetic resolution of multiple conductors. *IEEE Trans. Geosci. Remote Sens.* 26(2), 187–194. doi:10.1109/36.3020
29. Hu, W.G. & Collins, L.M. (2004). Classification of closely spaced subsurface objects using electromagnetic induction data and blind source separation algorithms. *IEEE TGRS*.
30. Hung, Y.-C., Lin, C.-P., Lee, C.-T., Weng, K.-W. (2019). 3D and boundary effects on 2D electrical resistivity tomography. *Applied Sciences*.
31. Huisman, J.A., Hubbard, S.S., Redman, J.D., Annan, A.P. (2003). Measuring soil water content with ground penetrating radar: a review. *Vadose Zone J.* 2(4), 476–491. doi:10.2136/vzj2003.4760
32. Kim, S.-S. & Wessel, P. (2008). Directional median filtering for regional–residual separation of bathymetry.
33. Kofman, L.A., Ronen, A., Frydman, S. (2005). Detection of model voids by identifying reverberation phenomena in GPR records. *J. Appl. Geophys.* 59(4), 284–299.
34. Leach, P. (2021). *GSSI — Theory primer and field guide for archaeology*. https://www.geophysical.com/wp-content/uploads/2021/02/MN10-376-Rev-A-GPR-Theory-Primer-and-Field-Guide-for-Archaeology.pdf
35. Ley-Cooper, A.Y., Macnae, J.C., Viezzoli, A. (2010). Breaks in lithology: interpretation problems when handling 2D structures with a 1D approximation. *Exploration Geophysics*.
36. Lit, S.V. & Shepherd, W.A. (2023). Fast estimation of the look-elsewhere effect using Gaussian random fields. *Eur. Phys. J. C* 83. doi:10.1140/epjc/s10052-023-12196-1
37. Liu, G. & Becker, A. (1990). Evaluation of terrain effects in airborne electromagnetic surveys. *Geophysics*.
38. Luo, [author list not captured]. GPR pattern recognition of shallow subsurface air voids. Thesis, Hong Kong Polytechnic University. https://ira.lib.polyu.edu.hk/bitstream/10397/93544/1/Luo_GPR_Pattern_Recognition.pdf
39. Marsh, L.A., van Verre, W., Davidson, J.L., Gao, X., Podd, F.J.W., Daniels, D.J., et al. (2019). Combining electromagnetic spectroscopy and ground-penetrating radar in a dual-mode landmine detection system. *IEEE Sensors J.* https://pmc.ncbi.nlm.nih.gov/articles/PMC6695582/
40. Moghadas, D., André, F., Slob, E., Vereecken, H., Lambot, S. (2010). Joint full-waveform analysis of off-ground zero-offset GPR and EMI synthetic data for estimating soil electrical properties. *Geophys. Prospect.*
41. Noh, K., Oh, S., Seol, S.J., Lee, K.H., Byun, J. (2016). Analysis of anomalous electrical conductivity and magnetic permeability effects using a frequency domain controlled-source electromagnetic method. *Geophys. J. Int.* 204(3), 1550. https://academic.oup.com/gji/article/204/3/1550/678228
42. Nobes, D.C. (2017/2018). Ground penetrating radar response from voids: a demonstration using a simple model. *NDT&E International*. / Nobes, D.C. (2018). Interpretation pitfalls to avoid in void interpretation from ground-penetrating radar imaging. *Near Surface Geophys.*
43. O'Neill, K., Sun, K., Shubitidze, F., Shamatava, I., Paulsen, K.D. (2005). Accounting for the effects of widespread discrete clutter in subsurface EMI remote sensing of metallic objects. *IEEE TGRS* 44(1), 32–46. doi:10.1109/TGRS.2005.858437
44. O'Neill, K., Shubitidze, F., Sun, K., Shamatava, I., Paulsen, K.D. (2005). EMI obscuration of buried UXO by geophysical magnetic permeability, anthropogenic clutter, and by magnitude disparities.
45. Oldenburg, D.W., et al. (2019). [1-D inversion of 2-D vertical conductor response.] Cited in #7.
46. Ormerod, et al. (2017). Teaching uncertainty: a new framework for communicating unknowns in traditional and virtual field experiences. *Scientific Contributions*. https://se.copernicus.org/preprints/se-2021-69/se-2021-69.pdf
47. Pathirana, S., Lambot, S., Krishnapillai, M., Smeaton, C.M., Cheema, M.A., Galagedara, L. (2023). Ground-penetrating radar and electromagnetic induction: challenges and opportunities in agriculture. *Remote Sensing* 15(11), 2932. doi:10.3390/rs15112932
48. Pellerin, L. (2002). Applications of electrical and electromagnetic methods for environmental and geotechnical investigations. *Exploration Geophysics* 33(4), 190–204.
49. Persico, R., et al. (2024). GPR mapping of cavities in complex scenarios with a combined time–depth conversion. *Sensors* 24(10), 3238. doi:10.3390/s24103238
50. Petković, M., Cvetkov, V., Sretenović, B. (2014). Advantages and disadvantages of a parallel and zigzag method of acquisition in walking mode in magnetometric archeological research.
51. Rai, S.S. & Verma, S.K. (1982). Quantitative interpretation of horizontal-loop EM measurements using a permeable sphere model. *Geophysics*.
52. Ren, Y., Wen, X., Gao, S., Liu, Y., Ju, B. (2023). Theoretical and simulation analysis on the spatial resolution of magnetic metal debris sensors. *Front. Mater.* 10, 1110834. doi:10.3389/fmats.2023.1110834
53. Save, M.C., Uieda, L., Barbosa, L., Chandler, C. (2012). Grid preparation for magnetic and gravity data using fractal fields. *Nonlinear Processes in Geophysics* 19(2), 291–299. https://npg.copernicus.org/articles/19/291/2012/
54. Schamper, C., Sab, G.A., Réjiba, F., Flipo, N. (2022). Performance of light fixed-wing airborne time-domain electromagnetic system for mapping the near-surface cover layer in an alluvial plain context: a numerical study.
55. Schofield, D., Hu, W., Collins, L.M. (2003). Separation of overlapping signatures in EMI data.
56. Silic, J., et al. (2018). [1-D vs 2.5-D inversion; off-end ghosting.] Cited in #7.
57. Sun, W., Reich, B.J., Cai, T., Guindani, M., Schwartzman, A. (2014). False discovery control in large-scale spatial multiple testing. *JASA*. https://pmc.ncbi.nlm.nih.gov/articles/PMC4310249/
58. Treppke, H., Becken, M., Rochlitz, R. (2024). Modelling of infrastructure effects in semi-airborne EM data.
59. van Verre, W., Marsh, L.A., Davidson, J.L., Cheadle, E., Podd, F.J.W., Peyton, A.J. (2020). Detection of metallic objects in mineralized soil using magnetic induction spectroscopy. *IEEE TGRS*.
60. Wessel, P. (1998). An empirical method for optimal robust regional-residual separation of geophysical data. *Mathematical Geology* 30(4), 391–408. doi:10.1023/A:1021744224009
61. Wessel, P. (2015). Regional–residual separation of bathymetry and revised estimates of Hawaii plume flux.
62. Wunderlich, T., Wilken, D., Majchczack, B.S., Segschneider, M., Rabbel, W. (2022). Hyperbola detection with RetinaNet and comparison of hyperbola fitting methods in GPR data from an archaeological site. *Remote Sensing* 14(15), 3665. doi:10.3390/rs14153665
63. Wunderlich, T., et al. (2024). What is beyond hyperbola detection and characterization in ground-penetrating radar data? *Remote Sensing* 16(21), 4080. doi:10.3390/rs16214080
64. Yu, T.-J. & Carin, L. (2000). Analysis of the electromagnetic inductive response of a void in a conducting-soil background. *IEEE TGRS* 38(3), 1320–1327. doi:10.1109/36.843025
65. Al Hagrey, S.A. (*Archaeometry*). Ground-penetrating radar velocity determination and precision estimates using common-midpoint collection. doi:10.1111/arcm.12214
66. Patsia, O. & Giannopoulos, A. (2023). Hyperbola fitting for characterising cylindrical targets in GPR data using deep learning permittivity predictions. *Proc. 12th Int. Conf. on GPR*. doi:10.3997/2214-4609.202320161
67. Hill, R. & Nunn, S. (2025). Applying different features of GPR hyperbolic reflections to cavity identification. *Int. J. Min. Sci. Constr. Mater.* doi:10.1007/s40808-025-02676-6
68. Reimann, C., Filzmoser, P., Garrett, R.G. (2005). Background and threshold: critical comparison of methods of determination. *J. Geochem. Explor.* PMID 15993678.
69. Erharter, G.H., Lacasse, S., Tschuchnigg, F. (2024). A consistent terminology to communicate ground-related uncertainty. *Can. Geotech. J.*
70. *CIMNiL* 6(3), 154 (2023). An overview of geophysical techniques and their potential suitability for archaeological studies. doi:10.3390/cimni6030154
71. Georeferencing of multi-channel GPR — accuracy and efficiency of mapping of underground utility networks. *Remote Sensing* 12(18), 2945 (2020). doi:10.3390/rs12182945
72. Geosoft/Seequent (2024). *Merge Sorties into Survey Database* (GX documentation). https://help.seequent.com/Oasismontaj/2024.1/Content/gxhelp/u/geosoft_gx_uavsurvey_mergesortieintosurvey.htm
73. Babish, G. (2006). *Geostatistics without tears*. Saskatchewan Geological Survey. https://www.geokniga.org/bookfiles/geokniga-babishg2006-geostatisticswithouttears.pdf
74. Zhang, et al. (2013). Identification of weak geochemical anomalies using robust neighborhood statistics coupled with GIS in covered areas. *J. Geochem. Explor.*
75. Chork, M.A. & Mazzucchelli, C. (1989). Spatial filtering of exploration geochemical data using EDA and robust statistics. *J. Geochem. Explor.*
76. Spatial interpolation techniques comparison and evaluation. PMC11226832 (2024).
77. Lit & Shepherd — see #36.
78. "The Stippled Gridpoints are Statistically Significant: (Mis)uses of False Discovery Rate Correction for Geospatial Data." *EGUsphere* preprint 2026. https://egusphere.copernicus.org/preprints/2026/egusphere-2026-2203/
79. Self-calibrating the look-elsewhere effect. arXiv:2108.06333. https://ar5iv.labs.arxiv.org/html/2108.06333
80. Characterising buried objects in metal detection. arXiv:2507.04450 (2025).
81. Surface modes and multi-power law structure in the early-time electromagnetic response of magnetic targets. arXiv:math-ph/0401036.

Standards and grey literature (Tier C):

82. **BSI (2022). *PAS 128:2022 Underground utility detection, verification and location. Specification*.** British Standards Institution. https://www.civilenghub.com/NewSamples/BSI/172454453/PAS-128-2022-1.pdf
83. Survey Association. *PAS128 Utility Mapping Accreditation (PUMA) Scheme Guide* (2024). https://assets.lrqa.com/m/663f041c77c49639/original/TSA-PUMA-Guide-GB-2024.pdf
84. Cargile, D.M., Bennett, H.H., Goodson, R.A., DeMoss, T.A., Cespedes, E.R., et al. (2004). *Advanced UXO detection/discrimination technology demonstration — Kaho'olawe, Hawaii.* ESTCP project report.
85. Butler, D.K., Cespedes, E.R., Cox, C.B., Wolfe, P.J. (1998). *Multisensor methods for buried unexploded ordnance detection, discrimination, and identification.* ERDC TR-08-9.
86. ITRC (2024). *Geophysical prove-outs for munitions response projects* (UXO-3). https://itrcweb.org/wp-content/uploads/2024/09/UXO-3.pdf
87. Minty Geophysics. *GridMerge Help — Grid Merging Fundamentals*. https://www.mintygeophysics.com/GridMerge_Help/GridMergingFundamentals.html
88. Geosoft/Seequent. *Topics in Gridding Workshop* (Matarozzo, C.). https://files.seequent.com/MySeequent/technical-papers/topicsingriddingworkshop.pdf
89. ExploreGeo. *Technical Note 7 — Iterative Gridding of Irregularly Spaced Data*. https://www.exploregeo.com.au/download_docs/Technical_Note_7_iterative_gridding.pdf
90. GeoSci.xyz. *Survey design — electromagnetic geophysics (UXO).* https://em.geosci.xyz/content/geophysical_surveys/uxo/survey_design.html
91. GeoExPro (2012). *Relating seismic interpretation to reserve/resource calculations* (DHI Consortium). https://www.geoinsights.com/relating-seismic-interpretation-to-reserve-resource-calculations/
92. Zetica (2023). *Improved methodology for assessing the risk of unexploded bombs during site investigations and foundation piling.* https://zeticauxo.com/wp-content/uploads/2023/02/zetica-understanding-the-limits-of-detectability-of-uxo.pdf
93. Lancaster, M. *The Electronics of Search*. http://www.geotech1.com/pages/metdet/info/lancaster/lancaster_150.pdf
94. University of Nevada Las Vegas, geology teaching notes — magnetic anomaly of a magnetized sphere. https://pburnley.faculty.unlv.edu/GEOL452_652/magnetism/notes/MagNotes32aexample2.html
95. Roberts, et al. *Geophysical survey methodology* (Internet Archaeology 47, Appendix 6). https://intarch.ac.uk/journal/issue47/7/app6.html
96. Historic England. *Traversing the Past* (total station / RTK practice). https://arf.berkeley.edu/files/attachments/equipment/HEAG_Traversing_the_Past_compressed.pdf
97. CLU-IN / USACE. *Electromagnetic Methods.* https://cluin.org/characterization/technologies/default2.focus/sec/Geophysical%5FMethods/cat/Electromagnetic_Methods/
98. Estimating dipole polarizabilities and object center location. https://www.osti.gov/servlets/purl/917339
99. Rasmussen, M. (2024). *Uncovering soil compaction: performance of electrical and electromagnetic geophysical methods.* *EGUsphere* preprint. https://egusphere.copernicus.org/preprints/2024/egusphere-2024-1587/
100. Landscape & Architectural Geophysics (LAG), *Persico, R. et al.* 2024 — see #49.

Vendor material (Tier D — cited **only** as evidence of claims made, never as support):

101. OKM GmbH. *OKM Rover C4 User Manual* (2017; rev. 2021). https://euro-technologygroup.com/wp-content/uploads/2025/11/OKM-Manual-Rover-C4-EN.pdf
102. OKM GmbH. *OKM Rover UC User Manual* (v3, 2019). https://okmpersia.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-UC-v3-201903-EN.pdf
103. OKM GmbH. *OKM Rover Gold User Manual* (2013). https://okmpersia.okmdetectors.com/cdn/shop/files/OKM-Manual-Rover-Gold-201307-EN.pdf
104. OKM GmbH. Rover C II product page. https://www.okmdetectors.com/blogs/previous-products/rover-c-ii-new-edition
105. OKM GmbH. Rover C4 product page (specification: GST/EMSR, SCMI-15-D, VLF, 1024 values/s, 16 bit). https://www.okmdetectors.com/products/rover-c4
106. OKM GmbH. *Field test reviews of OKM metal detectors* (Dr K.-H. Walker, 2006 tests, published 2017). https://www.okmdetectors.com/blogs/news/metal-detector-field-test

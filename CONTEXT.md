# GroundScan

The scientific analysis engine for OKM ground-scan data. It reads a survey of operator-acquired scan exports and emits located, characterised, bounded **detections** — records that state not only what was found but how much is known about it and what limits the claim.

The engine makes no reporting, plotting, or viewing decisions of its own. A later tool may present these records; the engine's obligation is that they cannot be misread.

## Language

### The survey

**Scan**:
One operator acquisition, one exported file. A scan has a start point the operator chose and an extent the operator declared.
_Avoid_: acquisition, measurement, file

**Survey**:
A set of scans intended to cover one area, analysed together into one result.
_Avoid_: site, project, session

**Lattice**:
The array of sampled positions within one scan, addressed by impulse index. **Exactly the set of indices the file contains**: the export **declares no count** of impulses or lines, so the lattice's dimensions are observed and never inferred from a declared extent, and nothing in the file states how many were intended.

Two facts about the same axis are recorded, and neither determines the other. The **span** is the operator's — the vendor's echo covers exactly the extent they declared — while the **spacing** between indices is **stated nowhere in the export** and is recoverable only as `span / (count − 1)`, from the declared span and the observed count together. So a lattice's size says how a survey was sampled, not how much ground it covered: three exports declaring the same 3.00 m carry 10, 19 and 26 impulses per line, and a declared 15.00 m carries more per line than a declared 20.00 m does.

**Spacing is not a density.** The **impulse density** — intervals per unit of declared length, `span / count` — is a different quantity one interval shorter, and OKM has published one: its eXp 4500 NT manual states *six impulses per metre*, in a manual, for one model, on a sensor the other lines do not use. Read the other way it is **not** the spacing: a declared 5 m at six per metre is 30 impulses spanning **4.833 m**. The two differ by up to a fifth on real exports, so the words are not interchangeable and the density is never a substitute.

With no declared span there is **no spacing at all**, which is the normal case and the reason every descriptor is pitch-free.
_Avoid_: grid, raster, mesh

**Impulse index**:
An ordinal along or across one scan line, as the device reports it — where one impulse fell in that line's sequence, not how many there were. It is the only spatial fact in an export that is **neither asserted by an operator nor computed by the vendor's software from what they asserted**, which is a statement about its origin and not about its truth: where a line begins is recorded nowhere and unverifiable.
_Avoid_: coordinate, position, index — an index is not a position; impulse count, which is the lattice's size

**Line order**:
Whether a scan line's impulse index counts from where the operator began walking, or in one fixed field direction — that is, whether successive lines were written in **alternating travel directions** or all alike. It is **absent from the export**: `Scan Mode` is `context-only` and provably inert, a filename is not evidence, and no OKM version records it.

Measured, the engine **preserves the exported order** and never infers or repairs it. Reversal is **not globally semantics-preserving**: it changes which cells are adjacent, and therefore everything derived from a changed component — its cell set, solidity, compactness, cell count, polarity, dominance, depth interval — along with any background or residual computation whose kernel crosses scan lines. It is harmless **only for quantities whose inputs are unchanged under it**: whole-scan response spread, counts over a fixed cell set, and pointwise facts such as one fixed cell's polarity.
_Avoid_: zigzag correction, row direction, scan direction, mirroring

### The export

**Column registry**:
The closed set of column names the input contract recognises, each with a **role** and a **field provenance**. A name is matched after trimming surrounding whitespace and comparing case-insensitively, and by nothing else — not underscores, not punctuation, not units, not wording. So **the unit is part of the name**: `Impulse X [ft]` is an unknown column, never a convertible variant of `Impulse X [m]`. Reordering is not a variation at all, because a file cannot carry it as information. An alias table earns its place only if OKM is shown to publish a real alias; until then a second spelling is a violation, not an accommodation.
_Avoid_: schema, header map, column aliases

**Role**:
What the engine *does* with a column, as distinct from what the file calls it. `impulse` and `scan-line` are the two lattice indices, `response` is the signal, `impulse-metric` and `scan-line-metric` are the vendor's own coordinate echo and are **cross-check only, never an input**, and `context-only` marks a field the engine records and never lets any claim depend on. Reading a file means mapping names onto roles, never onto positions in a line.
_Avoid_: field type, column purpose

**Optional / Reserved**:
Two distinct permissions for a registered column. **Optional** means a supported export may omit it. **Reserved** means the current vendor export does not produce it, and the name is registered anyway so a future version needs no vocabulary change. Neither is ever load-bearing: an optional or reserved column can never feed a registered evidence computation or a warrant. A reserved name and an optional name are different states, and the contract must tell them apart.
_Avoid_: tolerated, allowed, future-proof

**Dialect**:
How the file is written: the field delimiter, the decimal separator, and the declared decimal precision. The delimiter is read from the header, which contains no numbers. The decimal separator cannot be, and is read from a numeric declaration in the metadata — so a file with no numeric declaration leaves it **assumed**, never guessed per row. Once established, every row parses under that one dialect; a row that does not is a named violation. Precision is **formatting**: numbers are never rounded, padded, or rewritten to the places the operator chose.
_Avoid_: encoding, format, parser settings

**Unframed value**:
A number an export supplies with **no declared frame**. Not a position — a position without its frame is a number — and therefore never carried, never interpreted, never a candidate for identity. It may be retained as a **presence state** alone, and its absence is a fact worth keeping while the value itself is discarded: the coordinates in an OKM export arrive with the same unverified, software-written status as every other column, differ from the coordinate columns only in having no frame at all, and are documented as *relocation* rather than orientation or registration. A human needing the number reads the source export; retaining it in the engine would only launder a bare figure into a field that reads like a position.
_Avoid_: metadata, geotag, waypoint, coordinates

**Value integrality**:
The **lattice** the exported responses lie on — the largest value every response is an exact multiple of, computed on the printed decimals — and whether that lattice is `1`. A defensible fact about the input, computable with no declaration and **recorded nowhere in the file** — the export's decimal-place setting is a display choice and proves nothing, since all nine real exports are written at four places while six of them carry no fractional part at all.

The lattice is the general fact and integrality is its special case, so one recorded value carries both, and **one value per scan serves everything**: a median of lattice points is a lattice point, so a scan's residual lies on the same lattice as its responses. It is **never the declared precision** — a lattice coarser than the formatting grid is a property of the measurement, one equal to it is a property of the printing, and where the responses have no lattice of their own any exact tie they carry is an artefact of printing and nothing follows from it about the ground.

Two consequences follow, and both are why it is carried. **On an integral scan, exact ties are structural rather than coincidental**, so an exact-equality guard built for near-ties is the wrong instrument. And **on an integral scan, summation is exact**, so float non-associativity cannot arise there — a hazard measured on one export may simply not exist on another. Reported with its sample count and named for what was observed, never for a cause: `rounded`, `processed` and `quantised` each assert a mechanism the file does not state, and the direction is genuinely unknown.

**It is not a grade.** No stated property's grade depends on it. Where it matters it decides whether an exact tie is structural or coincidental, and it may collapse a numerical bound to zero — but a promise the engine makes about itself is argued from its construction, never from the input it happens to be reading.
_Avoid_: rounding, resolution, precision, quantisation, raw signal

**Convention**:
A modelling commitment the engine makes in place of a fact it does not have — the metric coordinate series, the default decimal separator, the quantile definition, the background model. Named, versioned, and **recorded where it is determined** — a per-scan convention in **scan context**, a per-measurement one on the result that depends on it — so a reader can tell which parts of a result rest on a convention rather than on the data. A convention is **not an assertion**: nobody stated it. (It is deliberately not called an assumption, which is a near-synonym here and would blur exactly this line.)

Each is pinned by its **stated mathematical property**, never by a library's default: the quantile convention by exact reflection symmetry, which admits four interpolation types and is then separated from them by the property that its plotting position stays inside the sample's range, so the extreme order statistics are reached without clamping. Where a convention admits several readings, the choice is **recorded as a property with what it costs** — a quantile may return a value the sample does not contain, which is stated rather than designed away.
_Avoid_: assumption, default, fallback, heuristic

**Contract violation**:
A named, closed reason the input declines a file. Run-level violations — only those preventing the input from being read as a serialisation at all — stop the run. Every other violation is **per scan**: one bad file among six never denies the other five, and the survey records which scans were refused and why. A scan refused for its own reasons never causes a related scan to be refused, so a missing relationship across a refused scan is connective state rather than a fault of its own. Each failing row receives **exactly one** reason: an unparseable row is never also reported as an invalid index, and a duplicate coordinate is only counted among rows whose indices are valid.
_Avoid_: parse error, invalid file, bad input

**Refused scan**:
A scan the input contract declines, carrying its reason. Not a **result state** — the engine declines to produce one rather than producing one that says nothing. Its lattice and measurements stay inside the file, unreachable; what survives is the refusal and its reason.
_Avoid_: failed scan, rejected scan, bad scan

**Vendor corpus**:
The nine real exports OKM publishes as educational examples, and the **only operator-shaped input that exists** for this format. Nine separate vendor *demo* scans of nine different places — not a survey of one area — and **structurally identical**: the same four sections, the same eight columns, the same dialect. Exactly one genuine repeat pair exists; nothing else pairs, and only under a 0°/180° relation.

A **provenance set, never a reference**: no independent ground truth stands behind any of them, their notes are the vendor's own, and every pattern name they use is consumer vocabulary the engine may not emit. Complete for this format's **variation** and empty of it — variation in content, none in structure — so what they can establish is **compatibility**, never correctness about the ground. Its *condition* is a separate fact: missing files and files whose content is not the expected one are different states, and neither is ever covered by synthetic or derived material.
_Avoid_: reference, ground truth, training data, benchmark, expectations, sample set

**Measurement standing**:
What may be done with a **corpus-derived number** quoted in support of a decision. Exactly four values, in closed vocabulary:

- `recorded` — every applicable setting is carried, so it may be quoted as a **point value**.
- `swept` — a declared sweep, with its axes **and extent**, plus the measured spread across it, so it may be quoted as that sweep's **interval** and **never as a point**.
- `unpinned` — settings were not carried and no sweep exists. **Not evidence.** History only.
- `unrecoverable` — a declared sweep exists and the figure is **not reachable** in it. **Retired**; supports nothing.

`legacy-sweep` is the **provenance label** rather than a standing: it marks a figure whose settings were not carried, and it becomes `swept` or `unrecoverable` once a sweep settles the question.

The **spread never decides anything** — it *is* the figure's interval — so no number in this vocabulary turns on a judgement about acceptability, and there is no threshold anywhere in it. The rule **binds the document that declares staleness** as well: a ticket that marks a figure stale may not reuse it unmarked in the same breath.

This is a vocabulary about **measurements taken while designing the engine**, and it is **pairwise disjoint from every result state** — a design-time figure is never `emitted`, `not-emitted` or `indeterminate`, and the engine never produces a standing. Its subject is not the ground and not the engine's output but **a number someone wrote down**, which is why a fourth category is needed that the engine's own three do not cover.
_Avoid_: confidence, evidence grade, measurement quality

**Measurement register**:
The single home for every corpus-derived number this project quotes, and for its **standing** — `docs/measurements.md`, versioned, one entry per figure. The specification **cites register entries** rather than restating figures, so a figure's standing is written down once, in a file a later correction can reach.

It exists because of a structural fact rather than a preference: a correction recorded in an issue **comment** cannot reach the text it corrects, since GitHub comments are immutable. Every withdrawal this project made before the register existed landed as a later comment the withdrawn text could not see, so the withdrawn figures were still unmarked in the very resolutions that cited them.

Exempt from the rule, and recorded as exempt so the exemption is visible rather than assumed: **definitional** results proved from a definition, **synthetic** results over constructed fields, **exact-oracle** derivations independent of any corpus, and **raw-column** statistics needing no processing convention.

Enforcement is **procedural, not mechanical**. A lint cannot work — a literal search for one withdrawn figure misses another entirely because the two are written with different glyphs, and that class of miss is not fixable by trying harder. A gate that can be evaded by typing an en-dash reads as enforcement while enforcing nothing, which is worse than an honest rule.
_Avoid_: evidence database, measurement log, results table

**Synthetic scenario**:
A manufactured survey, used where no real one exists — chiefly to exercise the perpendicular case, which no real data ever will. It has no vendor provenance and no operator, every assertion in it is **`fixture-asserted`**, and it is **`synthetic-only`** evidence: not real data, and never a substitute for it.

What it asserts is **mechanics, never ground**. Its manufactured responses exist so that detections exist, and it says nothing about what the engine finds in them — count, location, size and polarity are out of scope, and **a change in how many it yields is not a scenario failure**. A carefully designed ground is an invitation to read the scenario as validation, and should be treated with suspicion.

Two consequences follow. It is built in **exact integers and rationals with explicit bytes**, so its bytes are reproducible by construction rather than by luck — and that guarantee is about the *generator*, never about the engine. And it **cannot check itself**: where the thing under test is an operator's declaration, the scenario supplies that declaration and then asserts the engine honoured it, so it proves the engine composes and preserves and never repairs, and proves nothing about whether anyone declared a real walk correctly.
_Avoid_: ground truth, expected results, test data, mock survey, simulated site, fixture suite

### Position

**Frame**:
The space a position is measured within, named for whoever established it. A frame is part of the position's identity: a position without its frame is not a position but a number.
_Avoid_: datum, CRS, coordinate system

**Scan-local position**:
A position as exact integer impulse indices within the contributing scan's own lattice and frame. The engine's **canonical position**, and the only one always available — a shared-frame or physical expression is derived from it and never replaces it.
_Avoid_: primary position, raw position, index position

**Field position**:
A position within the extent an operator declared for a scan, in units that operator supplied. True only to the extent the declaration was true. Its axes are **along-line** — the impulse axis, the vendor's `Field Length` — and **across-lines** — the scan-line axis, the vendor's `Field Width`: names that describe the lattice and say **nothing about direction**. No east or north, no `x` and `y` read as directions, no red and green.

Each axis carries its own **scale**, computed from the scan's own extreme indices, and the scale **travels inside the position and nowhere else**. It is never a field of its own: a bare figure in metres with no frame attached is an **unframed value**, and a record carrying one launders a number into a field that reads like a position. So the position names the scale's **two inputs with their own provenances** — the declared span as an assertion, the observed count as a device index — and the scale is their quotient, which is what tells a reader which input to distrust. Neither is sufficient alone: labelling the scale by the span alone would imply the *count* is suspect and the span sound, which inverts the truth. **OKM publishes a recommended spacing band and the engine adopts none of it** — that is advice to an operator about how to walk, not a property of a file, and a number the engine cannot derive has no business in the record.

Its **origin** is wherever the file places index 1, which is the operator's **marked starting point** — physically real, recorded in no OKM version in no column, and not locatable by the engine. So every position is measured from a mark that cannot be verified, and is **ambiguous along one axis** to exactly the degree that **line order** is. One fact, one limitation, two consequences.
_Avoid_: metric coordinate, world coordinate, real coordinate

**Survey position**:
A position in a frame the engine constructed by registering scans against a chosen reference scan. Supported by no input file. A survey position is a **shared-frame position**, so it carries its scan-local origin with it.
_Avoid_: absolute position, geo position, absolute coordinate

**Shared-frame position**:
A position re-expressed in a shared frame. **Derived**, never canonical: it always retains the scan-local position it came from, and each axis records the declaration that supplied its scale. Because those scales may come from *different* scans' declarations, it may be **fractional**, and when they do it is **not a homogeneous unit pair** — no metric distance is stated across such axes. Re-rooting preserves every pairwise frame relation and re-expresses only the coordinates.
_Avoid_: shared coordinate, fused position, merged position, world position

**Provenance**:
Where a value came from, recorded per axis. Exactly four values exist **for a position**:

- `device-index` — a count the device reported. Invariant.
- `operator-asserted` — a position in a rectangle the operator declared. True only if the declaration was.
- `derived-by-vendor-software-from-operator-assertion` — a value the vendor's export software computed from an assertion the operator made. The operator never stated this number; they stated something else, and software did the rest.
- `engine-constructed` — a position in a frame the engine built. True only within the assumptions of the registration that built it.

A **field** provenance is a superset, carrying every registry row, and adds one value:

- `instrument-produced-and-software-transformed` — the instrument produced it and operator-controlled software passed it through. No assertion stands behind it, and **no unit is promised**: OKM's own worked examples for the signal span three orders of magnitude, and an unrecoverable modifier state may have transformed it before export. **Illegal for any positional role** — a position carries one of the four above, or the contract is broken.

The word **measured** is not a provenance value. Nothing in an OKM export is measured; every column but the signal itself is computed by export software from operator-typed metadata.
_Avoid_: measured, derived, computed, estimated, quality

**Assertion**:
Something stated that the engine carries but cannot verify — an extent, a soil type, a start point, a scan's relation to another scan. Carried always, labelled always, never silently repaired. Note that a value *computed from* an assertion is not itself an assertion: see the third provenance value.

Every assertion carries a **source**, and there are exactly two. **`operator-asserted`** — a person said it. **`fixture-asserted`** — a test harness said it, which is **not the same as nobody saying it**: it is a stated fact, and the reader is entitled to know no operator stands behind it. The source is fixed at the **entry point** and **the engine never assigns it**, so a file cannot claim either. Sources may coexist in one survey, and **any claim whose warrant rests on a `fixture-asserted` assertion carries a limitation naming it** — the caveat travels with the claim rather than sitting in a report, and it is why a detection derived from one cannot read as an operator's finding. That mechanism is one-directional: nothing strips the labelling from a record.
_Avoid_: metadata, hint, assumption

**Relative orientation**:
A scan's relation to another scan, declared by the operator as exactly one of **Same**, **Opposite**, **90° clockwise**, or **90° counter-clockwise**. Never an absolute direction, a compass bearing, or a geodetic angle. Direction is part of the value because clockwise and counter-clockwise are mirror images of each other and the data cannot tell them apart. **Optional, never inferred**, and preserved exactly as declared: a declaration is never repaired into its own mirror, never into a neighbouring value, and never inferred from a filename, from data, or from neighbouring scans.

**"Clockwise" is the operator's, not the engine's.** The axes are `along-line` and `across-lines` and carry no direction at all, so there is no frame in which the engine could be clockwise in — the words name which of the two 90° values this is, and nothing more. That makes the mapping a **named convention**, `relative-turn-v1`, whose content is an asymmetric **mapping table** held as versioned contract data: a square lattice with a centred detection maps identically under both directions, so the table also states the **coincidence set** where they agree. It is recorded on every shared-frame position, and any implementation of it reads the table rather than the prose, so a misreading of the word fails loudly instead of agreeing quietly.
_Avoid_: orientation, bearing, heading, direction, angle, degrees

**Frame relation**:
The relation between two scans within a shared frame, carried as the composed class in **ℤ/4** — Same = 0, 90° clockwise = 1, Opposite = 2, 90° counter-clockwise = 3. Every scan holds the class from the canonical reference, derived by composing declared relations; the classes of two scans **difference** to their pairwise relation, which is what makes composition decide consistency exactly. So a cycle is either closed or contradictory, never merely implausible. The declared word is the assertion; the composed class is engine-constructed. **No rotation is applied at the last moment**, and no transform matrix is ever an assertion — the perpendicular case establishes a *relation between lattices*, never a merged grid.
_Avoid_: transform, rotation, transform matrix, alignment, registration transform

**Aspect consistency**:
The structural check of a declared relation against the two lattices' **long/short axis roles**: an odd relation (90°, 270°) expects those roles to exchange, an even relation (Same, Opposite) expects them unchanged. It reports exactly `consistent`, `contradictory`, or `not-informative` — the last whenever **either** endpoint lattice is structurally square, decided by structural equality rather than tolerance. Computed from the lattice alone, so it needs no declaration; it **never gates and never repairs**, and it cannot distinguish clockwise from counter-clockwise. It corroborates a declaration cheaply and cannot confirm a plausible one, so it is never evidence that a declaration is right.
_Avoid_: aspect validation, shape check, orientation verification

**Shared frame**:
The frame a group of scans is placed into, which exists only when a **complete path of declared relationships** connects them. A survey may hold several independent frames at once — one per connected component — and a detection is placed in a frame only through the **frame relations** its own scan holds. Without a path there is no shared-frame position, and a missing link blocks only the component it breaks, never the others. A component holds **no merged lattice**: each scan's measurements stay in its own, and the frame relates them without combining a single cell.
_Avoid_: site frame, world frame, datum, georeference

**Missing orientation path**:
The condition of two scans that no complete path of declared relations connects. The shared-frame position is `not-emitted: missing-orientation-path`, which **withdraws nothing**: per-scan analysis, scan-local detections and the remaining components are untouched. Distinct from a **Contradiction**, which withdraws its component — a consumer debugging a survey needs to tell "nobody said" apart from "they disagreed".
_Avoid_: missing orientation, no orientation, disconnected

**Withdrawn component**:
A connected component whose shared frame is unavailable because a **contradictory cycle** makes its classes path-dependent. Every scan in it **falls back to its implicit local frame**, so each detection retains exactly one valid frame, and per-scan analysis and scan-local detections are unaffected. Reported contradictions are ordered by **canonical edge order**, and order-invariance is proved by permutation test rather than assumed.
_Avoid_: invalid frame, broken frame, failed component

**Canonical reference**:
The scan whose own lattice anchors a shared frame. A **convention, not an assertion**: chosen by a total order over a hash of the canonicalised measurement payload, and reading nothing about what any operator declared. Never the most central scan, never the most consistent one, never a name a human chose.
_Avoid_: master scan, base scan, primary scan, anchor scan

**Canonical payload**:
The measurement content of a scan, reduced to what the engine measures — excluding metadata, filenames, and anything an operator typed. **Absolute coordinate labels are excluded too**: relabelling every index by the same integer changes no measurement, so it must change no hash — otherwise the shared frame would depend on an index-base convention, which is the data-dependence the canonical reference exists to prevent. Two exports of the same measurement are therefore the **same scan**, whatever their indices say.

Two exports of the same measurement produce the same canonical payload, so a cosmetic edit cannot silently change which scan anchors a frame. **Indistinguishability is the deliberate cost**: two exports differing only in metadata are the same scan as far as identity is concerned, which is why no discarded **unframed value** can be smuggled back in through identity or canonicalisation.
_Avoid_: raw bytes, file content, payload

**Reflection orbit**:
The set of lattices one lattice is identical to under the reflections the engine admits, and it exists so that **identity cannot depend on which way an operator walked** — the same reason absolute coordinate labels are excluded, for the same reason neither is a fact the file states. It is exactly **{identity, along-line, across-lines, their composition}**, declared once and reused as the transform vocabulary's reflection subset, so refusing a reflection as a transform and excluding it from the orbit are one decision rather than two.

**The canonical payload is the lexicographically smallest representative of that orbit**, positions held relative to the **minimum measured-cell position** rather than to the lattice's own minimum — which is what lets padding at an edge leave the payload untouched instead of shifting every position it holds — and it is **not** a multiset of responses: lattice dimensions, connectivity, spatial relationships and response values are all preserved. Reflections inside the orbit are a fact about the file's internal layout and carry **no physical meaning** — which reflection a scan is taken to be says nothing about the operator's walk direction.

**Identity covers measured content only.** The representative is chosen by comparing index-and-value triples as **numbers**, never as encoded bytes, so integer endianness and float byte order cannot decide which lattice a scan is. The hash is then taken over the chosen representative's encoding, and it is blind to declared lattice dimensions, to padding, and to every operator-typed value — which means two exports differing only in what the operator wrote are the same scan, and padding is the same scan as an absent row. That indistinguishability is the price of an identity reading nothing but measurements, and it is exactly why the record keeps the distinctions the hash drops. The hash never covers the record's own text either, so no formatting change can re-root a frame in every stored result. Its encoding version is carried in the hash's preimage **and** declared at the document root, since a version that is only invisible makes two records' hashes silently incomparable rather than detectably so.
_Avoid_: reflection group, symmetry group, canonical orientation, handedness

**Re-rooting**:
Expressing a frame from a different canonical reference. It changes the *expression* of coordinates and nothing else: the same detections, the same per-scan results, the same declared relationships, the same conclusion. Every **pairwise frame relation** is preserved — the classes difference to the same value mod 4 — while the coordinates re-express. Across a 90° relation the coordinate tuple is legitimately re-expressed, so invariance is of the physical relationship, never of the numbers.
_Avoid_: realignment, re-registration, re-anchoring

**Contradiction**:
Two operator assertions in a survey that cannot both hold. Reported as a limitation, and it blocks the affected fused position — the engine never picks a winner, because it has no independent authority to. As a **cycle** it is decidable rather than suspected: a cycle whose classes do not close is contradictory, and the component holding it becomes a **withdrawn component**.
_Avoid_: conflict, inconsistency, error, repair

**Depth**:
A measurement property of a detection, never part of its position and **never an engine claim**. Present as an **interval** spanning the covered samples, because the vendor's per-sample estimates disagree — typically by a large fraction of their own spread between adjacent samples. Never a point value: aggregating would invent a number the file does not contain. Absent means absent, never zero. The interval is **evidence with a provenance**, not a statement that anything is at that depth: PAS 128 labels such depths *"Assumed"*, and any claim that something is actually there belongs to the consumer.
_Avoid_: z, level, burial depth, target depth, measured depth

### Measurements

**Response**:
The raw measured signed value at one sample, before any grouping. A response is a number, not yet a thing. Unitless and signed; not comparable across scans, sessions, or devices — only within one. It is what the **canonical payload** is made of: the payload hash covers responses, never residuals, because the residual depends on conventions the hash must not read.
_Avoid_: reading, value, sample

**Residual**:
A response **minus the background model**, in **original measurement units**. The raw form, always available, and the basis for every derived quantity. A residual over a measured cell is **finite by construction** — a response is finite and a median background is finite — which is why no non-finite value is representable anywhere in the record, arrays included, and why padding is carried as the absence of a measurement rather than as a numeric stand-in.
_Avoid_: corrected value, cleaned signal, normalised value

**Background model**:
The multiscale median model subtracted to produce residuals, fixed as the convention **`background-model-v1`**. Its windows, support rule, scale combination and quantile conventions are **processing metadata** — they describe the computation, not the ground. No estimator is assumption-free, so the assumption is recorded. **No trend term is removed**: an explicit one would be a geometric claim about the ground, and the largest window already is the low-frequency removal.

Every window is **centred and clipped to the lattice**, and every median is taken over **measured cells only** — padding is never filled, so a window's **support** is the count of measured cells it contains, **derived per scale and never stored**. Scales combine by **median**, which is why no tie rule governs the combination at all, and why the ladder is an **odd** count: an even ladder's median is an average of order statistics rather than one, and would forfeit the median-atom result below.

The convention is **pinned by polarity symmetry** — the combination must not bias the polarity partition, since polarity is defined against the background — recorded with its coverage (8 of 9 vendor exports; the sole exception is the one whose robust scale is unusable), and deliberately **not** as a stated property, because near-balanced is not exact.
_Avoid_: baseline, trend removal, detrending

**Component hierarchy**:
The deterministic tree the engine emits, and **every node of it is a detection**. One structure read two ways, not two structures: the hierarchy *is* the detection record. It is built **per polarity** over the cells whose residual is non-zero, with **one level per distinct residual magnitude, per polarity** — a magnitude occurring on both sides of the background is **two** levels and not one, so the level grid is a partition of the polarity and never a count of magnitudes over the field — so the engine holds no threshold, because it emits the whole tree rather than a cut of it, and thresholds are policy.

**Simultaneous entry is unordered.** Every cell sharing a magnitude enters as a sibling at once, which needs **no tie rule**: the components at a level are determined by the thresholded set, not by entry order. An ordering rule would impose an arbitrary sequence on cells the data does not distinguish, and would create intermediate nodes matching no thresholded set at all. This is not a corner case — one measured level carries **480 cells** — and it is what keeps the tree equivariant under **reflection**, since a reflection permutes cells within a simultaneous group.

Levels are **raw residuals, never z-scores**: the scale-normalised view does not exist when the robust scale is in disagreement, so a level in σ units would be undefined exactly then. Stable in its upper structure under noise; **not** stable in how many nodes it has.
_Avoid_: cluster tree, dendrogram, segmentation, mask

**Detection count**:
How many nodes the hierarchy holds, **over one polarity**, and **no cross-polarity total is emitted** — the structure ships and the tally is the consumer's, as with the component count. A **distinct quantity** from the **component count** — it is a property of the whole tree rather than of a cut of it — and it is the quantity that replaces "how many findings" now that a finding is not something the engine reports.

**One node per birth.** A component born at a level and unchanged at the next is one node with a lifespan; a cell set that vanishes and later returns is a **second** node, so a node's identity is its birth and never its cell set. Summing the component count over levels is therefore **not** this quantity: it counts a surviving component once per level it outlives, which is a tally over cuts rather than a property of the tree.

Its definitional bound is **the cells entering the hierarchy**: the count never exceeds them and never falls below the number of components they form, so **both ends are attainable** and the sharp end is the cell count. It is **not** #32's per-level bound, which is over a level rather than a tree.
_Avoid_: component count, node count, anomaly count, finding count

**Component count**:
How many components the hierarchy holds **at one level and one polarity**. Since **every node is a detection**, this is a **derivation over what the record already carries** rather than a separate stored output — the structure ships, the tally is the consumer's, and derivable state is not duplicated.

It is a fact about **the engine's output**, not about the ground, and a derivation of it carries three things: the **level**, the **connectivity convention** without which neither its bound nor its reproduction holds, and a **reference to the scan's stability record**. That stability record **is** engine output, and the asymmetry is exact: per-trial counts require *running* the declared perturbation protocol, so they cannot be re-derived from one run. The record's own sensitivity output carries the **multiset of per-trial counts** and the trial count rather than any reduced drift figure — a relative deviation would be a chosen magnitude, and a count's instability is a jump rather than a drift. Its population is a numerator over the **scan's measured cells**, padding excluded: the one candidate denominator that is exactly invariant, since a polarity-restricted cell count provably flips sign under any perturbation. **No cross-polarity total is shipped**, and no derived ratio — the numerator and the denominator are stated and the quotient is the consumer's.

It carries the one thing about a count that *is* exact, a **definitional bound** that is a **theorem** — the independence number of the connectivity graph, so `ceil(L·W/2)` under 4-connectivity and `ceil(L/2)·ceil(W/2)` under 8-connectivity — which means **the ceiling survives the perturbation the count does not**. Witness attainment is claimed only for a fully measured rectangular lattice.

**No monotonicity guarantee exists**, and that is recorded as an **existential** fact — no guarantee, with a witness — not as a claim that any scan behaves non-monotonically. A degenerate scan whose counts are constant does not contradict it, and the entry is **not** qualified to "where the levels are distinguishable", which would assert the opposite and promise non-monotonicity the engine cannot support.
_Avoid_: detection count, finding count, cluster count, node count, anomaly count, candidate count

**Parent map**:
The relation between two **levels** of one polarity under one connectivity: **every component at a higher level lies inside exactly one component at a lower level**. It is **total** and it **composes across any two levels**, which is what makes it traversable and what replaces the reading of a level as a filter over a fixed set.

The two families are **not nested** in the other direction, and that asymmetry is the whole point: a lower-level component may have **no** higher-level descendant, or **several**. So a level is a **cut through a fixed tree**, never a subset of another level's result, and a count is **the number of tree nodes alive at that cut** — it **rises on splitting** and **falls on vanishing**.

This is what a consumer can actually do with a level: traverse *down* from any detection and see which lower-level regions it came from. The branching along that traversal is where non-monotonicity lives. What is unavailable is reading the level as a nested filter, and **counting across levels is not a sensitivity analysis** — the curve is not monotone and every point on it is itself unstable.
_Avoid_: nesting, hierarchy of levels, containment chain, level filter

**Mask-invariance**:
Whether a declared **bounded** perturbation of the residual field could change **any** thresholded cell set, decided rather than measured. If every finite measured cell's distance to every threshold of every compared level **exceeds the declared amplitude**, no cell can cross a threshold, so the thresholded sets are identical — and therefore **every** derived quantity is identical: counts, parent map, hierarchy.

Two states, **`mask-invariant`** and **`not-guaranteed`**. It is **sufficient and not necessary**, and **`not-guaranteed` does not mean unstable** — a large share of genuinely invariant fields read `not-guaranteed`, because the criterion is conservative. It belongs to the **exact-tie-tolerance** family: derived from the computation, catching the case it names and nothing else, and **never a threshold**.

**Ordering invariance is a corollary of this, not its content** — and so is magnitude invariance, since a count that cannot change cannot reorder. Valid only for a **bounded** protocol; an unbounded one leaves every field unguaranteed. Where a protocol perturbs the payload instead of the residual, the residual bound is **derived through the background model** rather than assumed: a median is **monotone and shift-equivariant**, hence **1-Lipschitz in the sup norm** — if every input moves by at most `a` the median moves by at most `a`, which is the property that matters because a draw perturbs *every* cell at once — so a payload amplitude of `a` moves the background by at most `a` and the residual by at most **`2a`**, and no tighter bound follows from the model **for the pinned median-ladder background**. That last clause is load-bearing: the constant is **`(1 + Λ)`**, where `Λ` is the background operator's sup-norm Lipschitz constant, so it is a property of the **background model** and not of the draw. The consequence is worth stating plainly — payload-perturbation invariance is **strictly rarer** than residual-perturbation invariance, because every threshold distance must clear twice the amplitude. The amplitude is compared by **strict inequality** with the floating-point error bound subtracted.
_Avoid_: stability, robustness, noise tolerance, sensitivity, order stability

**Level**:
A **residual magnitude at which the tree is read** — and therefore a cut the consumer makes over data it already holds, not a parameter the engine is given. Every level is already present in the record, because every node is a detection carrying its birth level. **A cut moves no engine output at all**, which is the consumer-facing guarantee in one line: *you may cut anywhere and lose nothing the engine computed.*

Chosen per survey by the consumer, and **never transferable between surveys**. The corpus figure that once carried this — top-lifespans as a fraction of residual spread — is **withdrawn** and stands `unrecoverable` in the register: under the pinned background it is not merely unmatched but **unreachable**, since on three of the nine exports the smallest gap the level grid admits already exceeds the band's upper edge. The non-transferability never rested on that figure in any case — it rests on the tree and the residual scale being per scan — and the withdrawal leaves it standing. **No transferable default exists.**

A level is a raw residual and so is **not** withheld when the robust scale is in disagreement — the cut needs no scale at all. What the disagreement withholds is the **scale-normalised view**, and only that; see **Scale status**. An earlier ruling that a level-based reading is rejected on scale disagreement survives against the normalised view alone.

A level is **not a filter over a fixed set**: raising it does not necessarily lower the **component count**, because a count is a discontinuous functional of a thresholded set. Raising it can **split** a component, **delete** one entirely, or **merge** survivors; lowering it can merge components or create new ones. The cells responsible **cannot be named** — the number that must cross together is **unbounded** — so **a level is never a nested filter and no marginality diagnostic exists**.

Whether a given comparison of levels survives a perturbation is **mask-invariance**, and it is decided rather than measured.
_Avoid_: threshold, cutoff, sensitivity

**Solidity**:
`A / (convex-hull area)`, where `A` is occupied cell count and the hull is of **cell corners**. Exactly `1.0` for any convex cell set. A ratio, so **pitch-invariant**: it describes index space, not the shape of anything on the ground.
_Avoid_: convexity, fill, density

**Compactness**:
`4πA / P²`, where `P` is **exposed lattice-edge perimeter, counting hole boundaries**. Penalises elongation and boundary irregularity, with discretisation effects at small sizes — a 50-cell line scores 0.06 where a 5×5 block scores 0.79, though both are perfectly convex. So equal solidity does not imply equal compactness. Also pitch-invariant, also index space.
_Avoid_: roundness, circularity, isoperimetric score

**Index space**:
The lattice of impulses, counted and shaped without reference to any physical extent. Everything in index space is computable even when the operator declared no extent — which is the normal case. A descriptor that needs a pitch cannot be computed here, which is why physical dimensions are added only when an extent exists.
_Avoid_: grid space, cell space, lattice units

**Anomaly**:
A spatially connected set of **residuals** sharing a polarity — residuals, not responses, since polarity is defined against the background and a response carries no side. Each one is exactly one **detection**.
_Avoid_: blob, region, cluster, object

**Detection**:
**One node of the component hierarchy.** That is the whole of it: a detection is not chosen from the tree, it *is* a node, and it carries its **birth level** as a recorded fact.

So **no level ever enters the engine as an input**, and a detection is "a component at a selected level" with the selection made by the tree rather than by the caller. What the consumer selects is *which detections to read*. A detection is a bundle of claims with their warrants, not a finding. It belongs to a **frame** rather than to a scan, but its identity and numbering are **scan-local and permanently so**: it never contains measurement cells from more than one scan, and it retains the contributing scan's canonical payload hash even when that scan shares a frame with others.

Two measured facts a reader should have before assuming a detection is an interesting thing. **The majority are single cells**, because every node qualifies and a leaf is a node — so most carry solidity exactly 1.0 and maximal compactness, and filtering them is the consumer's worth judgement, never the engine's. And **a large fraction of a scan's cells produce no detection at any level**, because a cell whose residual is exactly zero is in neither polarity; measured, 1,150 of 2,400 cells on one export and 1,204 of 1,600 on another. The record states both populations rather than leaving them to be inferred from a count.
_Avoid_: finding, candidate, target, object

### The record

**Result state**:
One of `emitted`, `not-emitted`, or `indeterminate`, carried by **both evidence outputs and interpretive claims** — one mechanism, not two. `not-emitted` applies **only** where a quantity is mathematically undefined or its computation cannot be performed, and it names which. It does **not** apply because a value is small: a quantity computed from a thin sample is emitted, with the **sample size carried as an explicit fact**, and sufficiency is the consumer's judgement. A magic minimum reintroduced under another name is the same defect as the threshold it replaced. Nothing is ever silently omitted, and an absent value always differs from an unrecorded one.

A **refused scan** is not one of these: it is the input declining to produce a result at all, so its reason vocabulary is closed separately from the `not-emitted` reasons. Refusal is **exclusively a contract matter** — a contract-valid scan is always read, however underdetermined the physics.

Other surfaces carry **their own closed vocabularies** — a gate's report states, a scenario's, a **measurement standing**'s — and none of them may be used here. The relationship runs **one way only**: a gate or scenario condition may name an engine result state as the outcome it expected, and engine data never adopts a condition from outside the record. Every such vocabulary is **pairwise disjoint** from every other, because the value that appears on two surfaces is the one a reader cannot interpret.
_Avoid_: missing, null, absent, unknown, null-with-reason

**Evidence output**:
A measured quantity carrying its method and provenance, needing **no licence**: residual, polarity, solidity, compactness, dominance, component size in cells, physical area, the depth interval. Distinct from an interpretive claim, which needs a warrant — and an evidence output is **not** a weaker claim, it is a different kind of statement. Each declares its **exact inputs** and its **population**: a coverage or validity figure is a numerator and a **named denominator**, never a bare fraction whose population is implicit, so a reader can see what was counted over what. Heterogeneous evidence is **never aggregated into a scalar** — such a field is unrepresentable rather than merely discouraged, since a lint can be suppressed with a reason and an absent field cannot be.
_Avoid_: measurement alone, metric, raw value

**Boundary contact**:
Two facts about a detection's position in its lattice, kept **distinct** and never collapsed into one score: the cells lying on the measured lattice's own boundary, and the cells **adjacent to padding or a missing region**. They are different confounds — an anomaly at the edge of coverage is clipped by the instrument's field, while one beside an absent region is flanked by nothing measured — and a single "boundary" number hides which happened. Both are measurement evidence with a method, carrying no threshold: the consumer decides whether proximity matters.
_Avoid_: boundary score, edge quality, clipping penalty

**Run context**:
What the engine knows about one execution: the environment fingerprint and execution metadata. Separate from scan context because it describes the run, not any input.
_Avoid_: session, job info, invocation

**Scan context**:
What the engine knows about one scan before any claim: canonical payload hash, background model and its conventions, robust-scale status including any disagreement, and the scan-level stability record. It belongs to the scan because it describes that scan's own measurements, not the ground.
_Avoid_: scan metadata, header info, scan profile

**Frame context**:
What the engine knows about a shared frame: its canonical reference, the declared relative orientations connecting members, component membership, and any contradiction. A frame may span several scans, and detections belong to a **frame** rather than to a scan — a single scan simply uses an implicit, engine-constructed local frame.
_Avoid_: site context, registration info, alignment result

**Quantity registry**:
The shipped, versioned record of every quantity the engine computes: its **definition**, its **derivation**, its **unit**, its **population**, and its **definitional bounds** with a tightness witness for each. It exists because the column registry cannot hold a fact about a *number* rather than a column, and without it a name like *coverage* would be claimed by two decisions at once.

It is the **only home of a definitional bound**, so the engine, the validation tests and the compatibility gate all read one definition rather than each restating it — which is the only way **no bound is unowned** survives someone adding a fifth quantity. Its version travels **once at the document root**, beside the contract version, and its derivations sit **inside the vocabulary lint** with per-line suppressions only, because a bound's rationale is prose in shipped code and prose is where a drifted label reappears.
_Avoid_: metrics catalogue, descriptor table, schema

**Contract version**:
A **monotonic integer** at the document root declaring what shape the record is, read before any version-dependent parsing. It is not a version string, because the reader accepts only the current version and a compatibility semantic would promise exactly the compatibility this project refuses. **Registry versions** — columns, quantities, properties — travel beside it, once each; **conventions** travel **where they are determined** instead — a per-scan convention in **scan context**, a per-measurement one on the result that depends on it — because a result depends on its own and two results in one document need not depend on the same ones. An older record is read by its own historical specification, never by a branch in the current reader.
_Avoid_: schema version, format version, semver, api version

### Claims

**Characterisation**:
A compatibility statement about a detection's *response* — the response families it is consistent with, never a physical object or material. Permitted **only** when it cites a **licensed source**: one stating its method, its independence from the instrument vendor, and the conditions under which it is known to fail. A physical model with explicit assumptions and validity bounds qualifies as a substitute. A hedged noun is still a noun: `metallic-like` in a machine contract is indistinguishable from `metallic`.
_Avoid_: classification, identification, label, type, metallic-like, cavity-like

**Licensed source**:
The evidence a characterisation must cite to exist at all. A source qualifies by stating its **method**, its **independence from the instrument vendor**, and the **conditions under which it is known to fail** — or by being a physical model with explicit assumptions and validity bounds. No source currently qualifies, so characterisation is **deferred**, not refused.
_Avoid_: reference, corpus, ground truth, training data

**Measurement evidence**:
A statement about what was measured, not about what is out there. Recurrence across acquisitions, stability under a declared perturbation, dominance at a stated level, polarity. Needs no licence, because it makes no cross-boundary leap — and it is **not** a weaker characterisation, it is a different kind of claim. Distinct from determinism: repeatability across acquisitions and deterministic computation are separate properties.
_Avoid_: characterisation, confidence, evidence score, repeatability

**Dominance**:
The peak residual magnitude of the strongest component over that of the second strongest, at a selected level. **A ratio, and structurally stable** — which is an argument from being a ratio over a thresholded set, not a corpus result. The corpus measurement once offered for it is **withdrawn** and stands `unrecoverable` in the register, on two independent grounds: its classification half named **three bands**, and a band is a threshold, which the engine holds none of; and its magnitude half was a **worst case** that the declared protocol does not reach. What replaces it is measured per polarity at a declared level and carries the component count beside it. Its *existence* is count-dependent (needs ≥2 components) while its *value* is not.
_Avoid_: uniqueness, dominance score, strength ratio, prominence

**Polarity**:
Whether a component's responses are greater or less than the estimated background. **A partition, not a measurement** — positive and negative components are disjoint by construction, so polarity is structurally exact. Says which side of background a response fell on, and nothing about what is there. Carries no implication about material, object class, cavity, or ground condition.
_Avoid_: sign, direction, up/down, above/below ground, anomaly type

**Stability**:
How far a measurement moves under a declared perturbation, recorded as an **attribute of the scan** — kind, magnitude, reference quantity, method, seed, trial count — and referenced by each claim evaluated under it. Deterministic for a given seed. **Stability is not validity.**
_Avoid_: robustness, confidence, reliability, repeatability

**Reserved**:
Contract space kept for a capability that has no producer in this implementation. The characterisation field is reserved, empty, and always so — meaning future-compatible contract space, **not** something to delete. A reserved field and a produced one are different states, and the record must distinguish them. In an input contract the same word means a **registered column the supported export does not currently produce**, which is not the same as an optional one.
_Avoid_: absent, missing, unsupported, future

**Context-only**:
A field the engine records and no claim may depend on. `Scan Mode`, the soil block, and every other export declaration whose semantics are not sufficient to be load-bearing are context-only, and the contract enforces it mechanically rather than by care: a warrant may not reference a context-only, optional, or reserved field, because a claim resting on one is a claim resting on nothing. Note what this does **not** say — a recorded licence does not make the signal clean. An unrecorded modifier state cannot be recovered, reconstructed, or silently used; it is named as a limitation that the claims downstream **reference**.

A context-only field may still contribute a **presence state** — absent, present-but-empty, present-with-value — while its value is discarded. Keeping the state and dropping the value are separate decisions, and the state is often the defensible fact: that an export *claims* a position is worth recording; what the number is, is not.
_Avoid_: metadata, informational, unused, ignored

**Closed vocabulary**:
The set of names the contract surface may use, checked mechanically over fields, enum values, limitation and error strings, and other shipped labels. New vocabulary is added **deliberately**, so drift is a review event rather than an oversight. It gates vocabulary drift — it does **not** certify meaning, since an innocuous name can still encode a forbidden claim.
_Avoid_: allowlist alone, ban list, schema alone

**Warrant**:
What a claim is grounded in, carried inline with the claim itself. A claim without a warrant is not permitted to exist. Warrants never combine: confidence that an anomaly exists and confidence in where it is are different claims and are never aggregated into one.
_Avoid_: confidence, score, certainty, probability

**Limitation**:
A first-class, claim-specific, machine-readable caveat qualifying the claim it travels with. Present even when empty — "no limitations" is a stated fact, distinct from "limitations unrecorded". A limitation that is no longer true must fail a test.
_Avoid_: caveat, warning, note, disclaimer

### Determinism

**Determinism**:
Two guarantees, and they differ in kind. **Repeatability**: the same **environment fingerprint** and the same **input export** yield the same bytes — a guarantee of **construction** rather than of observation, because numerical execution is constrained to be non-varying within one fingerprint rather than merely observed to be. **Order-invariance**: the same set of scans, presented in any order, yields the same survey result. Platform invariance is **declined** — float conventions in filtering, linear algebra and the convex hull bound it, and it cannot be demonstrated. A cross-platform figure may be reported informationally, but it is not a guarantee.
_Avoid_: reproducibility, consistency, repeatability alone

**Environment fingerprint**:
The recorded provenance of a result, and the scope a repeatability claim is stated against: interpreter and library builds, platform, and the **numerical execution characteristics** able to bear on a result — the CPU features and array dispatch actually used, the numerical backend configuration, and the thread counts in force. It **reports** what was used rather than accepting it: a pinned engine constant such as single-threaded numerical execution is stated here and is not a value a caller may vary, because a declared one would be a judgement the engine cannot defend wearing a provenance stamp. The **contract version** and the **registry versions** are *not* in it; they travel at the document root, so a registry change is never mistakable for a change of record shape.
_Avoid_: build info, environment, provenance stamp

**Canonical order**:
The total order imposed by the canonical payload hash, applied to **every unordered collection and every intermediate stage whose result can depend on iteration order**. It makes order-invariance true by construction rather than by luck, and it is the same mechanism that makes the canonical reference order-free.
_Avoid_: sorting, stable ordering, tiebreak

### The properties

**Transform**:
A change to an input's form that leaves its measurements the same — a relabelling, a reordering, a reflection, a rewrite under another dialect. Exactly three things make one admissible: it **preserves the measured cells and the lattice topology**, it **adds no measurement and no interpolated value**, and it **makes no new operator assertion**. Coordinate relabelling is admissible; a 90° turn is not, because it does not map the lattice to itself; resampling is not, because it manufactures values the source contract never contained; and the displaced-copy chance baseline is not, because it deliberately changes the measurement.

The criteria are stated over **inputs**, not over files, so an **analysis parameter** qualifies: **a change of level** modifies no measured data, preserves the cells and the topology, adds nothing and asserts nothing, and is therefore a transform. It earns its place because it is the only way the registry can state what a level does — the **nested thresholded sets** and the **parent map** as `exact` properties, and the absence of any monotonicity guarantee as a witness-backed non-property. **A transform need not preserve every output**: an entry says which outputs it governs and which it excludes, so a transform that legitimately changes some outputs is already representable.

**Padding extension is admissible, and padding substitution is not.** Adding empty cells adds no measurement and asserts nothing; because every background window is taken over measured cells only, no window's content changes, so the **background, residual, support and hierarchy are exactly preserved** — the invariance holds from the construction, not from measurement. The one output it moves is **Boundary contact**, since a measured cell can become adjacent to padding, and the entry excludes it with that reason. Turning a measured cell into padding is the opposite case: it **removes measurement content**, so it is not a transform at all, and is registered as a **named non-property** carrying its reason — so that whoever wants it back must argue against the reason rather than notice an absence.
**A convention bump is a transform, and it declares its scope.** Re-deriving a named, versioned modelling commitment — the quantile definition, the background model, the scale agreement — is admissible on the same terms as any other, and is registered as `convention-bump`. It is **never silent and never retroactive**: a bump records the old and new versions beside each other.

A bump's **scope is the commitments that moved**, and a convention is a **bundle**, so the parts are named in the convention's declaration and the bump names which of them it carries. **`scale-agreement-v1` is the worked case** — the estimator pair, the calibration constant, the **disagreement normalisation**, and the tolerance's derived form — and its parts have **three different footprints**: the calibration constant moves both estimates, while the **disagreement magnitude is provably independent of it** — the constant cancels — so a constant-only bump is a **constrained** move, not an independent one. The constraint is recorded as a fact about the convention rather than encoded as per-part versions, because a version per part advertises an independence the algebra denies.

_Avoid_: relation, transform family, perturbation, corruption

**Stated property**:
A promise the engine makes about itself, that some transform leaves some named class of output unchanged. Stated by the **property registry** and proved by the test suite, **never at runtime**: a violation is a test failure and nothing else, so the result states stay at exactly `emitted`, `not-emitted` and `indeterminate` and no property is ever a gate. Stating one says nothing about which way an operator walked — computational symmetry is not a claim about the ground — and that exclusion is standing for the whole registry rather than written into each entry, because repetition invites drift into treating one entry as the exception.
_Avoid_: invariant, guarantee, symmetry check, metamorphic test

**Grade**:
How strongly a stated property holds: **`exact`**, meaning identically and provable from the construction, or **`bounded`**, meaning to a bound derived from the accumulation the property names. A **refusal is not a grade** — it is a named non-property carrying its reason, so that whoever wants it back must argue against the reason rather than notice an absence. There is no third grade and no number, because a property score is a threshold wearing a grade's clothes. **Grades are argued from the construction, never from measured agreement**: a corpus result may support a property's evidence coverage and may never justify, strengthen or weaken its grade.
_Avoid_: strength, tolerance, exactness, score, confidence

**Numbering is a presentation**:
Component numbers order results; they do not identify them. **A detection's identity is its canonical payload identity plus its scan-local cell set.** Numbering survives translation, padding, row permutation, survey reordering and re-rooting, and **may permute under reflection**, because it follows lattice order and a reflection reverses lexicographic lattice order. So the two halves of canonical order disagree on purpose — identity is blind to what happened to position, numbering is blind to what happened to content — and a reflection property therefore governs component **sets** and their per-component quantities while **explicitly excluding numbers**. A reader who assumes otherwise will write a test that fails on the first asymmetric input.
_Avoid_: stable ids, stable numbering, ordering invariance

**Property registry**:
The shipped, versioned list of stated properties, held as a typed module inside the package and imported by the property suite as its **single source of truth**, so no test hard-codes a property the registry does not hold. One entry per `(transform, output class)`; each entry carries the transform, the output class, the grade, its **preconditions** — an `exact` grade is a theorem, and a theorem states its hypotheses — the bound's derivation, its governed and excluded outputs, and its evidence coverage **recorded apart from the grade**. The governed-output classes are a **closed partition**, which is what lets an output always be named in order to be excluded; and an output is excluded **only where the transform demonstrably moves it**, with the reason recorded, because an over-broad exclusion list hands a later contributor something to reclaim on a technicality.

**An exclusion covers moving a result *state*, not only moving a value.** A transform that flips an output from `emitted` to `indeterminate` has changed what the engine will and will not say, which no comparison of values detects; an entry that listed only value-bearing outputs would pass such a bump and ship a changed contract.

**An entry states its survivors as well as its exclusions.** The exclusion rule is negative, which leaves *unlisted* and *provably unmoved* looking alike — and the strongest thing an entry can say is usually the thing nobody wrote down. So where a transform's footprint is a strict **subset** of a class, the entry enumerates **members** and says so, rather than naming the class; that is finer than the `(transform, output class)` key and is recorded as deliberate, so the next contributor does not "fix" it back to class granularity.

The registry version travels once at the **document root**, beside the contract version and the other registry versions, so a property-registry change is never mistakable for a change of record shape.
_Avoid_: property list, test manifest, contract of invariants

**Indeterminate**:
A result the engine will not commit to, because a required check failed or a required warrant could not be established. On the check side: a non-unique argmax, candidates tied within the recorded floating-point bound, or instability under the recorded perturbation protocol. Each is a **separate check**, and each references a *recorded* protocol rather than a fixed constant, so changing the protocol changes the outcome consistently.

On the warrant side, two cases, and neither is about signal quality. **`export-processing-state`** — a claim depends on a fact the export cannot supply; the engine knows it cannot be recovered and does **not** know the exported values are bad. **`scale-not-warranted`** — the required warrant is a single robust scale, and the engine holds **two disagreeing estimates of the same quantity** and will not choose. It is named for the missing warrant and not for the condition, so that it never restates `scale_status`'s value on a second surface.

It means **"the required warrant is not established"**, never "the signal is probably poor". So it is **not** a quality score, a penalty, a ranking, or a proxy for signal quality, and a claim's being indeterminate says nothing about the values behind it. A passing check means only that the candidate is **well-defined and stable under that protocol** — never that the alignment is physically real.
_Avoid_: unresolved, ambiguous, unknown, tie

**Exact-tie tolerance**:
A numeric determinism guard on candidate scores, derived from the actual scoring computation and its accumulation length — not from a generic epsilon. Measured at ~1e-12 for an accumulation of 5,000 terms, while real margins are of order 1e-1: **it catches exact ties and nothing else**, and is not a doubt threshold.
_Avoid_: epsilon, float tolerance, tie threshold

**Scale status**:
What the robust-scale estimation produced for **one scan's residual field** — never per detection, because a detection-level scale would make the level depend on the detection. **Five** mutually exclusive states in a **fixed order of precedence**: no finite residual values, a field whose finite values are all equal, a **median atom** outvoting the median, and otherwise a tie or a disagreement — plus **tie-tolerance-saturated**, the case where a disagreement exists that the derived tolerance cannot discriminate.

A disagreement carries its **relative** magnitude, `|σ(MAD) − σ(IQR)| / max(σ(MAD), σ(IQR))` — **dimensionless**, and in `[0,1]` identically. That bound is not a convenience: it is what makes **`tie-tolerance-saturated` decidable at all**, since the state is the derivation that a tolerance of `1` or more is exceeded by every possible pair. The magnitude is therefore **symmetric** — neither estimate is the reference — and it is **exactly invariant** to the calibration constant, since numerator and denominator share it. It is **not** a difference in residual units: a **Response** is not comparable across scans, so such a figure is not comparable across scans either, and it can never be compared against a dimensionless tolerance. The whole construction is the named convention **`scale-agreement-v1`**. Every state records **both estimates**; a tie is **neither agreement nor disagreement**, so it never silently triggers a fallback, and it is a condition of `scale_status` rather than a generic result state.

What each state does to the one output that depends on the scale. The **scale-normalised view** is `not-emitted` with reason **`scale-not-positive-finite`** when the scale is zero or undefined — the three states up to and including the atom — and `indeterminate` with reason **`scale-not-warranted`** when it is positive but the two estimates disagree, which includes the saturated state. The two names are **disjoint from `scale_status`'s values and from each other**: the state says *what condition obtained*, the reason says *what could not be performed* or *what could not be warranted*. Nothing else the engine emits depends on the scale, so **the robust scale is reported but load-bearing for no output** — which is what lets it be evidence without being a gate.

**Measured on the vendor corpus: 1 `median-atom`, 2 `exact-agreement`, 6 `disagreement`, and 0 of the two remaining states.** Both agreements are an **exact float identity** — `IQR == 2 × MAD` on an integral export — so they are a lattice artefact rather than a fact about the estimators, and the 50% disagreement on one export is the same mechanism inverted. **Tie-tolerance-saturated never fires**: the smallest real disagreement is `0.0157` — the relative magnitude, on `Tunnel - Control Scan` — against a derived tolerance of `7.95e-16`, **thirteen orders of magnitude clear**.

The two estimates are **the same quantity measured twice** — a Gaussian-equivalent σ under one named calibration convention, both factors derived from the same `Φ⁻¹(0.75)` so they cannot drift apart — because two estimators of *different* quantities would report disagreement on every clean input, which is a units error wearing a detector's clothes. **Agreement is an asymptotic property, not a definitional one**: they are calibrated to σ rather than to each other, so their finite-sample divergence is a fact about the field rather than a defect, and it is exactly what the disagreement state reports. **Agreement is therefore not evidence of convergence**, it does not certify that the sample was symmetric, and on an integral export it is a lattice artefact rather than a fact about the estimators.

Disagreement is decided by a **tolerance derived from the computation** and from that field's own offset-to-spread ratio `L/s` — the largest absolute value among the centring median and the two quartiles, over the larger of the two estimates — never a chosen number, and never a fixed fraction. `L/s` is what the tolerance is **divided by**, which is why the tolerance is a ratio rather than an absolute error bound and is commensurable with the relative magnitude alone. It is a determinism guard of the same kind as **exact-tie tolerance**, and it inherits that entry's standing: it catches exact coincidence and nothing else.

The field's **construction is part of this provenance**, so every state is a property of *that* residual field rather than of the scan in the abstract.
_Avoid_: scale score, dispersion tier, confidence, scale flag, quality tier

**Median atom**:
A run of values **exactly equal** to the sample's median, heavy enough to outvote it. **Measured on the corpus under `background-model-v1`**: one vendor export's residual field carries an atom of **0.7525** of its cells, past the halfway point and so producing a robust scale of exactly zero, while a second sits at **0.4792** and is **not** an atom at all. (Earlier figures — fractions of 0.57 to 0.81 across two exports — were measured under the superseded background and are **withdrawn**; the "points" they were quoted at have no counterpart under a pinned ladder of three scales.)

Its consequence is exact and it is not a matter of tuning: **the median absolute deviation is zero if and only if the atom holds more than half the sample**, and every median-of-medians scale estimator inherits that, so on such a field the whole family returns **exactly zero together** — while the interquartile range, blind to the atom, can be non-zero on the same sample. So **two estimators from one family cannot witness each other's blind spot**, and a detector built from two of them reports *agreement* on a value that is not the dispersion.

**The cause of a median atom is not assumed.** Exact ties arise wherever **local** variation falls below the value lattice's step, and whether the field's spread as a whole is large or small does not follow from that. One cause, two scales: **tie-proneness is governed by local variation relative to the lattice step, and whether a perturbation applies at all is governed by the field's spread relative to it** — so the two point in opposite directions only while the spread is not inflated above the bulk by a heavy tail. A field with a wide tail over an exactly tied background is tied and applicable at once, which is why the corpus's one large atom being unperturbed is an observation and not a theorem.

That is why the atom is carried as **evidence in its own right** — an exact count over an exact denominator, with **no threshold** — rather than being left to be inferred from two estimates that share the failure.
_Avoid_: outlier pile, spike, degenerate sample, atom, tie cluster

**Padding**:
A lattice cell carrying no measurement. **Padding never participates in component identity or numbering** — a component's number depends only on measured cells and their lattice coordinates, so moving or adding padding must not renumber anything. An **interpolated or resampled value is padding by definition**: it is not a measurement, so it can never enter a measurement lattice, and it is this rule — not caution — that forbids resampling one scan onto another.

In the export, padding is exactly **an empty response at a valid lattice coordinate**, and three neighbouring states are *not* padding and are never quietly folded into it: an **empty index cell**, which leaves the coordinate unreconstructable and is a violation; an **absent row**, where the coordinate was never written; and a **short line**, where the vendor exported fewer rows for a line than declared — a documented vendor artefact, recorded as **declared against observed counts** and preserved as a discrepancy, never as a parse failure and never filled with zero. Absent means absent, never zero.

Padding is likewise **invisible to identity**: the canonical payload covers measured content only, so padding and an absent row are the same scan to the hash. The record still keeps them apart, because identity and record are different questions and only one of them is allowed to be lossy.
_Avoid_: missing cells, gaps, absent data

**Hazard class**:
One of the current four — **order**, **tie**, **magnitude-instability**, **non-monotone-level** — sorted into two **rule kinds**. A **determinism** hazard means the same input yields a different answer; it is closed by construction or by decidable checks, and both its members are order and tie. An **inference** hazard means the engine's answer is perfectly determined and the *consumer's reasoning* is what fails; it is closed by **annotation**, the record stating the licensing condition, and **nothing gates**. Its two members are magnitude-instability and non-monotone-level, and they **share one named mechanism**: *a count is a discontinuous functional of a thresholded set*.

The taxonomy is fixed for this phase and **remains reopenable**: a new hazard is either mapped onto an existing class or explicitly reopens the taxonomy, because v2 is not yet built and a classification that cannot represent a real hazard is wrong.
_Avoid_: hazard type, risk category, taxonomy
**Chance baseline**:
A scan displaced by a fixed vector larger than the match tolerance, used to measure **chance correspondence** — explicitly *not* real-world unrelated-scan behaviour, which this corpus cannot supply because its only same-shape pair genuinely matches. The same artefact serves the recurrence contract, so one construction serves both.
_Avoid_: null baseline, random baseline, control

**Self-alignment stability**:
Argmax invariance measured by comparing a source against a **perturbed copy of itself**. Measured: the winning shift is invariant across 6 perturbations on all 7 tested sources. This does **not** establish stability for aligning two independent acquisitions of one area, and that limitation travels with every result.
_Avoid_: registration stability, alignment stability, robustness

**Deterministic order is not selection**:
A canonical order fixes the *order* results are reported in. It never chooses which candidate is physically correct — that takes separation and stability evidence, and the two criteria are held distinct on purpose.
_Avoid_: ranking, preference, priority

### Judgement

**Defensible**:
A fact the engine can establish from the data in front of it — coverage, finiteness, whether a lattice is well-formed. Only defensible facts may gate output. **An unrecoverable fact is defensible**: the engine can establish that a thing *cannot be recovered from this export*, and establishing that is enough to withhold a claim whose warrant requires it, while saying nothing whatever about the quality of what was exported. This is the difference between *the warrant is missing* and *the thing is poor*, and collapsing them is how an honest limitation turns into a silent quality score.
_Avoid_: valid, trustworthy, quality score

**Policy**:
A judgement the engine cannot establish from data, made once and frozen. Never a gate; at most an annotation. Thresholds are policy, so a quality bar lives outside the engine entirely.

**Definitional bound**:
A bound on a named quantity that its **definition or computability requires** — compactness at most `π/4`, because `P ≥ 4√A` over any cell set; solidity at most `1`, because it is occupied cells over a hull that contains them. Not the opposite of a threshold but **the same retention rule reaching the one number that survives it**, so a definitional bound is kept while a policy number is deleted, and neither is a matter of taste.

A bound that is true but not **sharp** is a weaker statement than one that is, so each carries a **tightness witness**: a constructed case attaining it exactly. Three checks, kept separate — the bound's validity, the witness's attainment, and production's agreement — and the oracle proving them is **independent of the implementation it checks**, since an oracle sharing production's code verifies nothing. A bound stated without its derivation is an assertion; a bound whose derivation is not linted is worse.
_Avoid_: threshold, limit, sanity check, range check, epsilon check

**Field ready**:
**Not a domain term, and deliberately recorded as such.** No such state exists in this engine, and readiness is not a spectrum it can report. Legacy computed one — a `ready_score` in [0, 1] with tiered block/caution thresholds over a dozen heterogeneous signals — and the concept is deleted rather than softened, because softening it would leave a number whose only remaining function is to be quoted as though the engine had endorsed it. An operator asking *is this fit to dig?* is asking the engine to make a judgement it has no warrant for; what the engine owes instead is the facts, each with its population, and the limitations attached. A consumer may compute readiness. The engine's record must never be read as asserting one.
_Avoid_: readiness, fitness, quality level, grade, confidence

## The claim boundary

The engine describes **anomalies**, never objects. It measures responses, and may state compatibility with response families **only when it names the source that licenses that connection**.

The strongest sentence the engine can produce about the ground is:

> an anomaly at impulse 34, line 12, extent 3 by 5 impulses, bipolar response, consistent with a family previously associated with metallic targets

It cannot say *metal*, *target*, *tunnel*, *buried object*, *at 4 m*, or *validated* — and offers no route by which any of those could be inferred. Interpretation of a measurement into a physical conclusion is the consumer's work, done with information the engine does not have.

Two consequences that are easy to forget:

- **Weak is not the same as undefendable.** A faint detection is emitted with its limitations attached. Suppression happens only where a claim could not be defended at all.
- **`metallic-like` and its siblings are consumer vocabulary.** They may reappear downstream, reading a compatibility statement the engine emitted. They may never appear in the engine's own contract — nor under a renamed label in its tests, which would smuggle the same claim back through the test boundary. **Reserved is not absent:** the characterisation field is kept and always empty, and deleting it would be a contract regression, not a cleanup.

## Notes on the vocabulary

Two distinctions this codebase cannot afford to blur, because legacy blurred both:

- **Scan orientation is not candidate orientation.** Relative orientation is how the operator walked between scans — and it is absent from the export entirely, present in no OKM version, so the operator is the only source. A detection's orientation is an axis of its own shape, computed in whatever frame its positions live. They are different quantities with different names, and neither may be labelled with the other's.
- **Absence is a stated fact.** When an operator declared no extent, the detection has no field position — and that absence is reported, not filled in with a guess. A plausible number with no basis behind it is worse than no number.

A third, learned the hard way: **a relative orientation is a four-value relationship, not an angle.** An operator does not know or care that they turned 90° anticlockwise; they know they turned around, or they turned a corner in a particular direction. Modelling it as degrees invites geodetic reasoning the engine cannot support, and "90°" without a direction silently discards the mirror ambiguity that makes the declaration load-bearing.

A fourth, and the one most easily undone by a later contributor: **the canonical reference is a convention, and conventions are chosen by rules that read nothing of substance.** Choosing the most central scan, the best-correlated one, the first in the input list, or the one whose name reads first are all the same mistake — they make the frame depend on the data, the order, or the operator, and every one of those is either a claim the engine cannot warrant or a judgement it is forbidden to make. The reference is chosen by hashing the measurement and taking the smallest. The resulting name is meaningless to a human, and that is the point.

A fifth, about the *shape* the engine reports. **Everything preserved is in index space**, meaning ratios and counts over a cell set rather than descriptions of a thing on the ground. That is not a simplification — it is what makes a detection computable at all when the operator declared no extent, which is the normal case. The corollary is that a descriptor needing a physical pitch is a different kind of quantity and cannot be substituted silently for one that does not.

A sixth, about what a perpendicular pair of scans actually buys. **Two scans walked across each other establish a relation, not a merge.** The tempting prize is one grid with the anomalies in it, and taking it requires resampling one lattice onto the other — which manufactures values that are not measurements, so the merged grid is not a measurement grid and every count over it would be a count of inventions. So the engine keeps both lattices whole, relates them, and stops there. The consequences are worth stating plainly because each reads like a missing feature: there is **no cross-scan count and no cross-scan density**, even over an overlap; a shared-frame position may be **fractional**, because its axes take their scale from different declarations and so are not one unit; and the position is **not tape-able** in the sense of a place on Earth. What the operator gets is what their own assertions support — a position inside the grid they declared — plus the chain that made it true. More detections, not fewer, and none of them invented.

A seventh, and the one most easily undone by a later contributor. **A corrected value sitting beside the shipped one is not evidence.** It reads as care — someone went further — and it is the shape of a claim with no warrant attached: an alternate number with no decision behind it, which a consumer cannot evaluate and therefore either trusts or ignores. The engine emits the value it has, and where the data is wrong the honest response is a **limitation**, not a correction nobody asked for. This is why the legacy dipole diagnostic and shadow ledger, nine hundred lines in total, computed corrected values beside the shipped ones and decided nothing. If a correction is ever justified it arrives as a claim with a warrant and a limitation — or it does not arrive.

An eighth, about the one thing in this domain that is neither in the file nor in the engine. **The operator's starting mark.** It is physically real — OKM tells them to *place a little marking on the ground* and to *remember the exact location of your starting point* — and it appears in no version of any OKM software, in no column, and in no firmware. Everything the engine says about position is measured from it, so the engine carries it as an **assertion** and can verify none of it, and the record says so rather than implying an anchor that does not exist. Its corollary is the naming rule that follows: **the axes are `along-line` and `across-lines`, and nothing else.** `x-axis` is the real hazard, not `east` — in a numerical codebase an `x` reads as a direction long before anybody opens a document. And the operator's own `Notes` field, which in the real exports contains sentences as varied as *"the user has performed a control scan"* and *"It is located in a depth of approx. 4 m"*, is prose: never parsed, never a spatial input, and a metamorphic property in its own right that replacing it with arbitrary text changes nothing.

A ninth, about the number most likely to be misread. **A component count is a measurement, and it is of the engine's output rather than of the ground.** The instinct is to treat it as a fact about the field and either trust it too much or withhold it entirely; both are wrong, and in opposite directions. Trusting it too much reads a count as a statement about how many things are buried, which nothing licenses. Withholding it treats instability as a reason not to report, which is a judgement about worth — and the engine's regime has no such judgement, which is the same reason *field ready* was deleted. So the count is emitted, carrying its level and its conditions, and a **consumer** decides what a number of components is worth. The companion fact is that instability is not uniform across quantities: a **ratio** over a cell set is structurally stable, a **partition** is exact by construction, and a **count** is a jump. Treating all three as one kind of number is how a stable engine ships an unstable claim.

A tenth, about evidence rather than output, and the one that should have stopped a number this project has been quoting. **A measured number is not evidence without the settings that produced it.** The load-bearing measurement behind the non-monotone-in-the-level hazard — `51 / 4 / 11 / 6` components at four levels — turned out to be unrecoverable: across 2,260 settings of the unpinned axes, **none** reproduces it. Not because anyone erred, but because the **background window and the detrending mode were never fixed**, so whatever produced the number used a setting nobody recorded. A number that depends on an unpinned convention is unreproducible *by construction*, and no amount of care at the moment of measurement prevents it. So every corpus-derived number carries the conventions, the connectivity, and the perturbation protocol that produced it, or is labelled `legacy-sweep` or `unrecoverable` and is **not** used as evidence. The corollary is the one to watch: **"we measured it" is not a warrant**, and neither is precision, agreement across reruns, or the number looking reasonable. A setting nobody wrote down is indistinguishable, later, from a number nobody can check. The background's window and trend mode were the two unpinned settings behind that figure; they are now fixed together as `background-model-v1`, which is the shape of the fix — **the convention is pinned, versioned and recorded, so the next number is reproducible.**

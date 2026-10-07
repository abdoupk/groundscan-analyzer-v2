"""Phase K -- the calibration decision table, as data.

Every candidate parameter lands in exactly one status, and the register is the
artefact that makes that auditable. Two properties matter more than the list
itself.

**One status per parameter, not per value.** A parameter whose production value
is unjustified and whose replacement is unjustified is ``INSUFFICIENT
EVIDENCE``; it does not become ``PROVISIONAL`` because a value happens to sit in
the code, and it does not become ``CALIBRATED`` because a sweep produced a
number. The status describes the *evidence*, not the current setting.

**A number is never calibrated by working.** ``CALIBRATED`` requires an
independent expectation and a population the parameter was not fitted to. Every
record therefore carries its dataset, its sample count, its derivation and its
applicability, so a reader can check that claim rather than take it.

The status vocabulary is closed. Adding a status to describe one awkward
parameter is how a decision table stops being a decision table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# The closed status vocabulary
# ---------------------------------------------------------------------------

#: A value determined by mathematics from the construction, with no free choice
#: and no fitting. Derivable by hand; checkable by an independent implementation.
STATUS_CALIBRATED = "CALIBRATED"

#: A value that is currently in service and is not known to be wrong, but for
#: which the evidence is insufficient to call it right. The default for a
#: number that predates the work that would justify it.
STATUS_PROVISIONAL = "PROVISIONAL"

#: A free modelling choice. The code could have used any value in a range; this
#: one was selected for a stated reason, and no evidence available here
#: discriminates between the alternatives. Calling such a value wrong is as
#: unjustified as calling it right.
STATUS_MODEL_CHOICE = "MODEL CHOICE"

#: A value that *can* be determined, by a measurement identified and feasible,
#: but which needs a category of evidence this repository does not contain.
STATUS_EMPIRICAL_VALIDATION_REQUIRED = "EMPIRICAL VALIDATION REQUIRED"

#: No evidence base exists for this parameter here, and the brief does not
#: identify a measurement that would create one.
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"

#: The question does not arise for this parameter, because the quantity it would
#: calibrate does not reach the stage the parameter sits at.
STATUS_NOT_APPLICABLE = "NOT APPLICABLE"

PARAMETER_STATUSES: tuple[str, ...] = (
    STATUS_CALIBRATED,
    STATUS_PROVISIONAL,
    STATUS_MODEL_CHOICE,
    STATUS_EMPIRICAL_VALIDATION_REQUIRED,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NOT_APPLICABLE,
)

# ---------------------------------------------------------------------------
# Activation vocabulary
# ---------------------------------------------------------------------------

ACTIVATION_ACTIVATED = "ACTIVATED"
ACTIVATION_NOT_ACTIVATED = "NOT ACTIVATED"
ACTIVATION_PROVISIONAL = "PROVISIONAL"
ACTIVATION_REQUIRES_FIELD_VALIDATION = "REQUIRES FIELD VALIDATION"

ACTIVATION_DECISIONS: tuple[str, ...] = (
    ACTIVATION_ACTIVATED,
    ACTIVATION_NOT_ACTIVATED,
    ACTIVATION_PROVISIONAL,
    ACTIVATION_REQUIRES_FIELD_VALIDATION,
)


@dataclass(frozen=True)
class ParameterRecord:
    """One parameter, one status, and everything a reader needs to disagree.

    ``value`` is ``None`` where the parameter has no value in service -- an
    unset ``d_res`` is ``None``, not 0.0 and not "unset as a string", because a
    consumer that wants to branch on it should not have to parse prose.
    """

    parameter_id: str
    question: str
    current_value: Any
    unit: str
    production_sites: tuple[str, ...]
    status: str
    dataset: str
    sample_count: int
    derivation: str
    uncertainty: str
    applicability: str
    rationale: str
    recommended_action: str
    activation: str
    measured_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in PARAMETER_STATUSES:
            raise ValueError(
                f"{self.parameter_id}: status {self.status!r} is not one of {PARAMETER_STATUSES}"
            )
        if self.activation not in ACTIVATION_DECISIONS:
            raise ValueError(
                f"{self.parameter_id}: activation {self.activation!r} is not one of "
                f"{ACTIVATION_DECISIONS}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "question": self.question,
            "current_value": self.current_value,
            "unit": self.unit,
            "production_sites": list(self.production_sites),
            "status": self.status,
            "dataset": self.dataset,
            "sample_count": self.sample_count,
            "derivation": self.derivation,
            "uncertainty": self.uncertainty,
            "applicability": self.applicability,
            "rationale": self.rationale,
            "recommended_action": self.activation,
            "activation": self.activation,
            "measured_evidence": self.measured_evidence,
        }


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------


def parameter_register() -> tuple[ParameterRecord, ...]:
    """Every parameter the brief asks about, with its status and its evidence.

    Written as a single literal so that the whole table is reviewable in one
    place and any change to it shows as a change to a status rather than as an
    edit buried in a measurement function. The ``measured_evidence`` blocks quote
    the characterization functions that produced each number, so a reader can
    re-run them; they are summaries of runs, not new claims.
    """
    from .geometry import COMPACTNESS_CONSUMERS, GEOMETRY_QUALITY_SOLIDITY_WEIGHT

    compactness_sites = tuple(c["production_site"] for c in COMPACTNESS_CONSUMERS)
    return (
        ParameterRecord(
            parameter_id="d_res",
            question="Is there a defensible single spatial distinguishability scale?",
            current_value=None,
            unit="m",
            production_sites=(
                "groundscan/validation/decomposition_reference.py:204 (ResolvableSeparation.value_m)",
                "groundscan/validation/decomposition_reference.py:255 (UNRESOLVED_SEPARATION)",
            ),
            status=STATUS_MODEL_CHOICE,
            dataset="analytical (continuous field) + perturbation (sampled detection)",
            sample_count=42,
            derivation=(
                "The analytic bifurcation scale of two equal Gaussians is exactly 2*sigma, "
                "derived in closed form from the construction. The delivered limit was "
                "measured as a separation sweep per (sigma, pitch, noise, anisotropy) cell, "
                "with the ground truth coming from the number of local maxima of the "
                "continuous field rather than from the detector."
            ),
            uncertainty=(
                "The measured d_res/d_analytic operating factor moved between 1.5 and 3.0 "
                "across the swept surface, and one cell was non-monotone (a coarse lattice "
                "at sigma = pitch, where the response is barely sampled). The crossing is "
                "bracketed, not located: each summary reports the last failing and the "
                "first passing separation."
            ),
            applicability=(
                "Valid only for the swept regime: equal-amplitude equal-width Gaussians, "
                "the production multiscale detector at threshold 3.0 and min_size 3, the "
                "production scales (3,5,9,15). Not valid for a different response family, "
                "a different detector configuration, or a real instrument whose noise is "
                "not Gaussian."
            ),
            rationale=(
                "A single d_res is not available: the quantity is a property of response "
                "width, sampling pitch, noise level and detection threshold jointly, and "
                "every one of those appears in the measurement. Declaring the parameter a "
                "model choice with a measured operating envelope is the honest outcome; "
                "declaring a number would silently assume an operating point the number "
                "does not state. The value stays None and the conservative-nest policy "
                "stays the only evaluable one."
            ),
            recommended_action=(
                "Keep unset. Publish the operating-factor surface as the envelope rule "
                "instead of a threshold, and require a field line-spacing and contrast "
                "record before any value is proposed."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "analytic_rule": "d_res_analytic(sigma) = 2*sigma exactly",
                "probe": "calibration.resolution.d_res_operating_envelope",
                "operating_factor_range_observed": [1.5, 3.0],
            },
        ),
        ParameterRecord(
            parameter_id="d_res.response_width_dependence",
            question="Does the analytic resolution scale with the response width?",
            current_value=2.0,
            unit="multiples of sigma",
            production_sites=("groundscan/validation/decomposition_reference.py:175",),
            status=STATUS_CALIBRATED,
            dataset="analytical (closed form, verified against a continuous-field oracle)",
            sample_count=42,
            derivation=(
                "A closed form, derived from the construction alone. For "
                "f(x) = A[exp(-(x-s/2)^2/2s^2) + exp(-(x+s/2)^2/2s^2)] the midpoint is a "
                "local maximum while s < 2*sigma and a local minimum while s > 2*sigma. "
                "The crossing s = 2*sigma is where f'' vanishes at the midpoint, exactly, "
                "independent of amplitude and of sampling."
            ),
            uncertainty=(
                "None in the derivation. The constant was confirmed numerically at 14 swept "
                "separations: the independent local-maxima oracle reported 1 mode at and "
                "below 1.0*2*sigma and 2 modes above it, with no exceptions."
            ),
            applicability=(
                "Equal-amplitude, equal-width, isotropic Gaussians only. Unequal amplitudes "
                "or widths move the bifurcation, and no closed form is offered for them."
            ),
            rationale=(
                "This is the one number in Stage 4 that is determined rather than chosen, "
                "and it is calibrated in the strict sense: a closed form, an independent "
                "numerical check, and a stated domain of validity."
            ),
            recommended_action="No action. Cite it as the analytic floor when reporting d_res.",
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.resolution.analytic_bifurcation_separation_m",
                "verification": "continuous_modes matched analytic_modes at every separation",
            },
        ),
        ParameterRecord(
            parameter_id="min_size",
            question="Should min_size be cells, physical area, or a response width?",
            current_value=3,
            unit="cells",
            production_sites=(
                "groundscan/services/config.py:22 (AnalysisConfig.min_size)",
                "groundscan/core/anomaly.py:238 (detect_anomalies default)",
                "groundscan/cli/__init__.py:23 (--min-size default)",
                "groundscan/site/analyze_site.py:565",
                "groundscan/core/rescue.py:31 (ExtractionRescuePolicy.min_size)",
            ),
            status=STATUS_PROVISIONAL,
            dataset="perturbation (single constructed response, swept over pitch)",
            sample_count=35,
            derivation=(
                "For each (response sigma, pitch) the smallest min_size that keeps the "
                "response was found by bisection over the production filter, and reported "
                "in three units: cells, square metres, and multiples of the response's own "
                "FWHM. The cell count tracked pitch with a fitted log-log exponent; the "
                "area and width forms were scored by their relative spread across pitch."
            ),
            uncertainty=(
                "min_size = 3 is a cell count, so as a physical floor it is 3*dx*dy: "
                "0.1875 m^2 at a 0.25 m pitch and 3 m^2 at 1.0 m. The same number therefore "
                "describes two different instruments, and a pitch-free replacement cannot be "
                "chosen from this evidence because no candidate unit is stable across the "
                "whole swept range."
            ),
            applicability=(
                "Applies to the local detector's component filter. The rescue policy carries a "
                "second, independent min_size and the separation config carries its own "
                "min_fragment_cells; none of the three is covered by this characterization."
            ),
            rationale=(
                "A cell count is a resolution-relative constraint, not a physical size, and "
                "that is a property of the parameterization rather than of its current value. "
                "Because the evidence does not identify an invariant unit, the value stays as "
                "it is and is recorded as provisional rather than replaced by a differently "
                "arbitrary unit."
            ),
            recommended_action=(
                "Keep 3. Document it as resolution-relative. Any move to a physical area or a "
                "response width requires a pitch/response joint sweep that identifies an "
                "invariant, and then a deliberate activation with a golden diff."
            ),
            activation=ACTIVATION_PROVISIONAL,
            measured_evidence={
                "probe": "calibration.resolution.min_size_resolution_sweep",
                "physical_floor_formula": "min_size * dx * dy",
            },
        ),
        ParameterRecord(
            parameter_id="min_margin",
            question="Does min_margin = 0.02 have a defensible meaning?",
            current_value=0.02,
            unit="evidence support (dimensionless, rounded to 3 dp)",
            production_sites=("groundscan/core/evidence.py:36 (EvidenceModelConfig.min_margin)",),
            status=STATUS_MODEL_CHOICE,
            dataset="perturbation + vendor (candidate population), one factor at a time",
            sample_count=95,
            derivation=(
                "The margin is best minus runner-up. The evidence model's `unknown` "
                "hypothesis is a declared affine function of the best specific support, "
                "(0.58 - 0.45*S), and the floor 0.05 is unreachable over the whole range, "
                "so the map is unconditionally affine. Wherever `unknown` is the runner-up, "
                "the margin is 1.45*S - 0.58 and min_margin is exactly equivalent to a floor "
                "on the winner's support at S = (min_margin + 0.58)/1.45 = 0.4138."
            ),
            uncertainty=(
                "On the measured population the runner-up was `unknown` in 0 of 95 cases, so "
                "the equivalence was never exercised; the closed form was still verified to "
                "zero prediction error. The joint (support, margin) grid shows the gate is "
                "not a restatement of min_support: at production min_support it removes 3 "
                "candidates at 0.02, 7 at 0.04, 8 at 0.08 and 53 at 0.16. The converse is "
                "nearer true but still false: min_support removes nothing anywhere in "
                "0.40-0.60 and 4 candidates at 0.70, so over most of its swept range the "
                "margin gate dominates it."
            ),
            applicability=(
                "Applies to core.evidence.classify_from_evidence only. classify.py carries a "
                "second, different margin (hypothesis_min_margin = 0.04) on the cavity/tunnel "
                "score pair; the two were never combined in this work and the 0.04 constant is "
                "recorded separately."
            ),
            rationale=(
                "The constant's meaning is now stated rather than assumed. The structural "
                "identity is exact and conditional on a runner-up branch this population never "
                "reaches; the measured behaviour is that the gate is load-bearing here, with a "
                "sharp knee between 0.08 and 0.16. No evidence available here discriminates "
                "between 0.01, 0.02 and 0.03 -- the population has one candidate between them "
                "-- while the knee it can see sits far above the production setting. The "
                "neighbours are therefore named and left as they are, rather than one of them "
                "being chosen on absent evidence."
            ),
            recommended_action=(
                "Keep 0.02. Record the closed-form identity in docs/thresholds.md so the "
                "constant is not later 'calibrated' as if it were an independent criterion."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.margin_structure / margin_sensitivity_sweep; "
                "calibration.interactions.evidence_x_min_margin",
                "equivalent_support_floor": 0.413793,
                "closed_form_max_error": 0.0,
                "n_rejected_at_production_min_margin": 3,
                "min_margin_redundant_given_min_support": False,
            },
        ),
        ParameterRecord(
            parameter_id="min_margin.instability_zone",
            question="Is a small margin actually an unstable decision?",
            current_value=None,
            unit="margin (dimensionless)",
            production_sites=(),
            status=STATUS_INSUFFICIENT_EVIDENCE,
            dataset="perturbation (one constructed response, controlled factors)",
            sample_count=0,
            derivation=(
                "Intended as an empirical instability zone: the flip rate under controlled "
                "perturbation, binned by margin. Not populated, because the flip rate is a "
                "property of the perturbation set and no perturbation set here is "
                "representative of a real survey's re-walk error."
            ),
            uncertainty=(
                "The perturbations available are noise, translation, amplitude, anisotropy, "
                "raster density, contamination and polarity. A real re-survey adds GPS "
                "re-walk error, a different operator, a different day and a different line "
                "spacing, and the flip rate under those is not bounded by the set above. The "
                "harness reports the per-margin-bin flip rates with empty bins left visible, "
                "so a future run with a better perturbation set has somewhere to land."
            ),
            applicability="Not established.",
            rationale=(
                "Without an instability zone measured on a representative perturbation set, "
                "there is nothing for min_margin to be a threshold *against*. The 0.02 value "
                "therefore has no measured support in either direction, and reporting a zone "
                "from these perturbations would be a claim about the perturbations."
            ),
            recommended_action=(
                "Leave the zone undefined. The measurement harness is in place; the missing "
                "input is a documented re-survey perturbation set."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
        ),
        ParameterRecord(
            parameter_id="solidity.band.shape_irregular",
            question="Does 0.48 still mean 'irregular' after S02?",
            current_value=0.48,
            unit="solidity (dimensionless, S02-corrected)",
            production_sites=("groundscan/core/shape.py:223",),
            status=STATUS_MODEL_CHOICE,
            dataset="analytical (88 exact cell sets)",
            sample_count=88,
            derivation=(
                "The band pre-dates S02 and was selected against a formula whose dimension "
                "was 1/area. Re-characterized against the corrected metric on 88 exact cell "
                "sets, scored with the independent exact rational oracle."
            ),
            uncertainty=(
                "The band crosses 11 of 88 analytic shapes and 5 sit within 0.05 of it, so a "
                "5% move changes up to 5 shapes. The band separates crosses from L-shapes on "
                "this catalogue rather than irregular from compact: a 3-cell-arm L measures "
                "0.545 and a 2-cell-arm cross 0.345."
            ),
            applicability=(
                "Applies to the 'irregular' shape branch, which is only reached when the "
                "boundary, linear, elongated and broad branches have all been excluded -- so "
                "the band's population is the residual, not the catalogue."
            ),
            rationale=(
                "The corrected metric is exact and pitch-free, so the band is at least applied "
                "to a well-defined quantity now. Nothing available here says which shapes "
                "should be called irregular; that is a descriptive-category question about "
                "morphology, and the brief supplies no independent labelling for it."
            ),
            recommended_action=(
                "Keep 0.48. Any change requires an independently labelled shape corpus, which "
                "is category D and unavailable."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.geometry.solidity_census_summary",
                "n_crossed": 11,
                "n_total": 88,
                "n_fragile_within_0.05": 5,
            },
        ),
        ParameterRecord(
            parameter_id="solidity.band.geology",
            question="Does 0.75 still gate the geological-like hypothesis?",
            current_value=0.75,
            unit="solidity (dimensionless, S02-corrected)",
            production_sites=("groundscan/core/classify.py:309",),
            status=STATUS_MODEL_CHOICE,
            dataset="analytical + perturbation + vendor (candidate population)",
            sample_count=88,
            derivation=(
                "Re-characterized on the analytic catalogue, then its sensitivity measured on "
                "the pipeline's own candidates by perturbing the solidity value and counting "
                "band crossings."
            ),
            uncertainty=(
                "The most active of the three bands: 32 of 88 analytic shapes and, on the "
                "candidate population, a +/-0.10 solidity shift moved 28 to 52 candidates "
                "across it. It is the band a calibration would most change and the one with "
                "the least independent support."
            ),
            applicability="The gate is one conjunct of the geological-like hypothesis.",
            rationale=(
                "Same reasoning as the irregular band, with more leverage: this band is the "
                "most load-bearing of the three and the least independently constrained -- "
                "no evidence here discriminates between 0.70, 0.75 and 0.80, and the "
                "neighbours are named rather than one of them being chosen. That combination "
                "argues for leaving it alone and flagging it, not for tuning it."
            ),
            recommended_action=(
                "Keep 0.75. Record it as the highest-leverage unvalidated band; a future "
                "calibration should start here."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.interactions.solidity_x_geometry_quality",
                "n_crossed": 32,
                "n_total": 88,
            },
        ),
        ParameterRecord(
            parameter_id="solidity.band.recovery_note",
            question="Does 0.50 still mark an irregular/concave note?",
            current_value=0.50,
            unit="solidity (dimensionless, S02-corrected)",
            production_sites=("groundscan/core/classify.py:653",),
            status=STATUS_MODEL_CHOICE,
            dataset="analytical (88 exact cell sets)",
            sample_count=88,
            derivation="Re-characterized on the analytic catalogue with the exact oracle.",
            uncertainty=(
                "12 of 88 shapes cross it and 11 sit within 0.05 -- the most fragile of the "
                "three bands by the fragility criterion, and the two bands 0.48 and 0.50 are "
                "close enough that a shape can cross one and not the other for no principled "
                "reason."
            ),
            applicability="Appends a note to the candidate; it does not gate a hypothesis.",
            rationale=(
                "Two bands within 0.02 of each other, neither independently justified, on a "
                "quantity whose population is raster-dependent. That is enough to say the "
                "pair is unexplained; it is not enough to change either, because there is no "
                "evidence pointing at a replacement."
            ),
            recommended_action=(
                "Keep 0.50. Note the 0.48/0.50 proximity as the concrete reason a joint "
                "recalibration is needed rather than a per-band tweak."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.geometry.solidity_census_summary",
                "n_crossed": 12,
                "n_fragile_within_0.05": 11,
            },
        ),
        ParameterRecord(
            parameter_id="geometry_quality.solidity_weight",
            question="Is 0.25 the right weight for solidity in geometry_quality?",
            current_value=GEOMETRY_QUALITY_SOLIDITY_WEIGHT,
            unit="weight (dimensionless; one of four terms summing to 1.0)",
            production_sites=(
                "groundscan/core/shape.py:381",
                "groundscan/site/separation_fragments.py:159",
            ),
            status=STATUS_MODEL_CHOICE,
            dataset="analytical (weight sweep) + perturbation + vendor (mediator probe)",
            sample_count=88,
            derivation=(
                "The other three terms (0.30 cell count, 0.25 mask fill, 0.20 boundary) were "
                "recovered exactly and verified against production geometry_quality to zero "
                "difference, then the solidity weight was swept alone."
            ),
            uncertainty=(
                "Removing the term entirely (0.25 -> 0.0) changes the evidence selection for "
                "1 of 90 candidates, and moving it over 0.0-0.4 changes none. The 0.40 "
                "weak-geometry band is not crossed by any solidity shift up to +/-0.10; the "
                "closest approach measured was 0.023. The weight is therefore neither "
                "calibrated nor inert -- it is a free parameter in a regime the population "
                "does not exercise."
            ),
            applicability=(
                "Two of the three production sites are covered (core.shape and the separation "
                "fragment path). The third, diagnostics.dipole's merged-lobe geometry quality, "
                "is a function of two lobes and is outside this measurement."
            ),
            rationale=(
                "There is no evidence that discriminates 0.25 from 0.10 or 0.40, and the "
                "population is too far from the only band that reads it for a change to have a "
                "measurable effect. Both facts point the same way: leave it."
            ),
            recommended_action=(
                "Keep 0.25. Do not attempt to compensate for a solidity-band change with this "
                "weight -- the mediator probe shows the two routes are independent, with zero "
                "overlap in the candidates they touch."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.geometry.geometry_quality_weight_sweep + "
                "calibration.interactions.geometry_quality_x_evidence",
                "n_evidence_changed_at_weight_zero": 1,
                "min_distance_to_geometry_band": 0.023338,
            },
        ),
        ParameterRecord(
            parameter_id="threshold.3sigma",
            question="Is threshold = 3.0 a significance level?",
            current_value=3.0,
            unit="robust z-score (dimensionless)",
            production_sites=(
                "groundscan/services/config.py:21 (AnalysisConfig.threshold)",
                "groundscan/core/anomaly.py:237 (detect_anomalies default)",
                "groundscan/cli/__init__.py:22",
                "groundscan/site/analyze_site.py:564",
            ),
            status=STATUS_MODEL_CHOICE,
            dataset="perturbation (noise-only fields, target-free by construction)",
            sample_count=168,
            derivation=(
                "The nominal per-cell rate 2*Phi(-t) = 0.27% at t = 3 assumes independent "
                "standard-normal z. Each named source of departure was measured separately: the "
                "max over four scale fields, the per-scale non-Gaussianity of a median-filter "
                "residual, the lag-1 spatial autocorrelation, and the contamination fraction."
            ),
            uncertainty=(
                "The measured per-cell exceedance rate on a target-free field was 1.32% against "
                "a nominal 0.27% -- a multiplicity factor of 4.88, dominated by the smallest "
                "scale (4.34x alone). The spatial correlation ran the other way: lag-1 Moran's I "
                "was negative, so the effective sample size exceeded the cell count and the "
                "independence assumption was conservative, not optimistic."
            ),
            applicability=(
                "The measured rates are for additive Gaussian noise. A real instrument's noise "
                "is not Gaussian and no field evidence is available, so the measured factor is "
                "a property of the noise model chosen here rather than of any survey."
            ),
            rationale=(
                "3.0 is a conventional robust-z multiple and the characterization says exactly "
                "how far its nominal reading is from what the detector does. That is enough to "
                "keep the number and to forbid the interpretation; it is not enough to replace "
                "it with a calibrated rate, which would need a measured instrument noise model."
            ),
            recommended_action=(
                "Keep 3.0. Add the interpretation warning to the contract that already exists "
                "for it: `threshold` is a robust-z multiple, not a false-positive rate."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.three_sigma_characterization",
                "nominal_cell_rate": 0.0027,
                "measured_cell_rate": 0.01318,
                "multiplicity_factor": 4.8832,
                "morans_i_lag1": -0.204079,
            },
        ),
        ParameterRecord(
            parameter_id="threshold.sigma_claim",
            question="Should the 3-sigma gate be restated as a statistical significance?",
            current_value=False,
            unit="boolean policy",
            production_sites=(),
            status=STATUS_INSUFFICIENT_EVIDENCE,
            dataset="not applicable -- the question is about warrant, not measurement",
            sample_count=0,
            derivation=(
                "A significance claim needs an error model, a multiplicity correction over the "
                "candidate z-fields and maxima selection, and a test of that model against a "
                "real instrument. The first two can be written down; the third cannot, because "
                "category D is unavailable."
            ),
            uncertainty=(
                "Even on the Gaussian noise model the naive reading is wrong by 4.9x, and the "
                "measurement showed the sign of the spatial-correlation correction is opposite "
                "to the usual intuition. A partial correction that fixed the multiplicity and "
                "ignored the rest would look more authoritative while being less defensible."
            ),
            applicability="Not applicable.",
            rationale=(
                "Retaining 3.0 as a documented heuristic is more honest than replacing it with a "
                "significance level computed under an assumed noise model that no measurement "
                "supports."
            ),
            recommended_action=(
                "Retain as heuristic and state the warning. Revisit only with a measured noise "
                "model from field data."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
        ),
        ParameterRecord(
            parameter_id="evidence.min_support",
            question="Does min_support = 0.50 have a defensible meaning?",
            current_value=0.50,
            unit="evidence support (dimensionless)",
            production_sites=("groundscan/core/evidence.py:35",),
            status=STATUS_MODEL_CHOICE,
            dataset="perturbation + vendor (candidate population)",
            sample_count=95,
            derivation=(
                "Swept jointly with min_margin on the measured joint (support, margin) "
                "distribution, because the two act on the same decision and neither's "
                "redundancy is meaningful alone."
            ),
            uncertainty=(
                "min_support removes nothing anywhere in 0.40-0.60 on this population -- the "
                "margin gate already excludes every candidate those levels would -- and only "
                "starts removing candidates at 0.70, where it excludes 4 of 95. So over most "
                "of its own plausible range the constant is dominated by the margin gate, and "
                "it is a second, weaker filter rather than the primary one."
            ),
            applicability="Applies to core.evidence only.",
            rationale=(
                "It is dominated rather than inert: it is not redundant at 0.70, so it is not "
                "dead, but at its own production value it excludes nothing the margin gate "
                "has not already excluded. That is a reason to record it, not to move it -- "
                "a gate that rarely fires is a gate that rarely needs justifying, and any "
                "replacement value would be chosen on the same absent evidence."
            ),
            recommended_action=(
                "Keep 0.50. Note that it is the weaker of the pair, and that a future "
                "calibration of this decision should start from min_margin."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.interactions.evidence_x_min_margin",
                "min_support_redundant_given_min_margin": False,
                "min_support_adds_nothing_in_0.40_to_0.60": True,
                "n_rejected_at_support_0.70": 4,
            },
        ),
        ParameterRecord(
            parameter_id="evidence.unknown_floor",
            question="Is the declared `unknown_floor` the floor that is applied?",
            current_value=0.18,
            unit="evidence support (dimensionless)",
            production_sites=(
                "groundscan/core/evidence.py:37 (EvidenceModelConfig.unknown_floor)",
            ),
            status=STATUS_NOT_APPLICABLE,
            dataset="static reading of the production source, confirmed by execution",
            sample_count=0,
            derivation=(
                "EvidenceModelConfig.unknown_floor = 0.18 is declared and never read. The floor "
                "actually applied inside score_hypotheses is the literal 0.05 in "
                "max(0.05, 0.58 - 0.45 * specific_best). A grep over the package finds no other "
                "reader of the field."
            ),
            uncertainty="None: the field has no reader, so it cannot affect any output.",
            applicability=(
                "Not applicable as a calibration target. It is a dead configuration field, and "
                "changing it would change nothing while appearing to be a calibration."
            ),
            rationale=(
                "The parameter does not reach the decision chain, so it has no behaviour to "
                "characterize. Reporting it as a calibration target would invite a future "
                "reader to 'fix' it by moving 0.18, which is the wrong fix in the wrong place."
            ),
            recommended_action=(
                "Do not calibrate. Record the discrepancy in docs/thresholds.md. The real fix is "
                "to make score_hypotheses read the config field or delete it, which is a code "
                "cleanup outside this task's protected scope."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.unknown_closed_form",
                "declared_floor": 0.18,
                "applied_floor": 0.05,
            },
        ),
        ParameterRecord(
            parameter_id="compactness.metal_min_compactness",
            question="What does a compactness band mean, given the estimator?",
            current_value=0.55,
            unit="isoperimetric quotient (dimensionless, clipped to [0,1])",
            production_sites=compactness_sites,
            status=STATUS_MODEL_CHOICE,
            dataset="analytical (88 exact cell sets) with an exact exposed-edge perimeter oracle",
            sample_count=88,
            derivation=(
                "The production estimator approximates the perimeter by the count of cells "
                "surviving a morphological erosion -- a boundary-cell ring, not a length. It "
                "was measured against the exact exposed-edge perimeter for the same cell sets: "
                "median error +0.48, and it saturates at exactly 1.0 for 50 of 88 shapes."
            ),
            uncertainty=(
                "The metric is not scale-invariant: a k x k block's exact quotient is pi/4 for "
                "every k, while the proxy runs 1.0 up to k = 8 and only approaches pi/4 as k "
                "grows. For a one-cell-thick run the ring IS the component, so the proxy "
                "saturates at 1.0 up to length 12 while the true quotient keeps falling. 47 of "
                "the 55 shapes whose true compactness is below 0.50 pass all remaining gates."
            ),
            applicability=(
                "Applies wherever Candidate.compactness is read: site.separation (one band) "
                "and diagnostics.dipole (one). The two classify.py bands (0.55, 0.30) were "
                "dropped from this record when the dead rule cascade was removed from "
                "core/classify.py: they gated branches that were overwritten before a "
                "candidate left classify_candidate, so they compared compactness against "
                "nothing."
            ),
            rationale=(
                "There are two different compactness thresholds and no single compactness "
                "policy, and the underlying estimator cannot reject thin shapes at all. Any "
                "band on it is a band on a size-dependent, size-confounded proxy. That is a "
                "defensible reason to keep the values; it is not a reason to move them, and "
                "replacing the estimator would invalidate both thresholds at once, which is "
                "the opposite of a narrow activation."
            ),
            recommended_action=(
                "Keep both values. Record the boundary-cell-ring limitation in "
                "docs/adr/001 (it is partly documented there) and add the measured scale bias. "
                "An estimator change is a separate, larger piece of work requiring a "
                "per-gate recalibration."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.geometry.compactness_matrix_summary",
                "median_abs_error": 0.480229,
                "n_proxy_saturated_at_one": 50,
                "n_low_oracle_shapes_passing_every_gate": 47,
            },
        ),
        ParameterRecord(
            parameter_id="compactness.estimator",
            question="Should the estimator be a physical exposed perimeter?",
            current_value="digital_compactness: 4*pi*A / (erosion-boundary cell count)^2",
            unit="estimator identity",
            production_sites=("groundscan/_util.py:448",),
            status=STATUS_EMPIRICAL_VALIDATION_REQUIRED,
            dataset="analytical (the exact exposed-edge perimeter is available here)",
            sample_count=88,
            derivation=(
                "An exact exposed-edge perimeter is computable for any cell set as "
                "4N - 2*(face-adjacent pairs), and the resulting quotient is scale-invariant "
                "and equals pi/4 for every k x k block. The measurement of the gap against the "
                "production proxy is what makes this a *specified* candidate rather than a "
                "vague improvement."
            ),
            uncertainty=(
                "Everything downstream of the metric would move at once: the two gate "
                "thresholds, two evidence weights, the morphology tables and the frozen "
                "goldens. No independent evidence indicates that a change would improve "
                "any decision, only that the current proxy is biased."
            ),
            applicability=(
                "Every consumer of Candidate.compactness, plus the shadow ledger's legacy "
                "column and the dipole merge average."
            ),
            rationale=(
                "The defect is established; the fix is not scoped, and the brief's rule against "
                "changing production on insufficient justification applies to a replacement as "
                "much as to a retune. 'Do not fix compactness because an intuitive shape "
                "received an unexpected score' cuts both ways: the score here is wrong for a "
                "measured reason, but replacing it needs both compactness gates recalibrated "
                "together."
            ),
            recommended_action=(
                "Do not replace in this stage. The estimator candidate and its measured error "
                "are recorded so a later activation can be scoped rather than rediscovered."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.geometry.compactness_scale_bias / compactness_thin_diagnostic",
                "square_true_value": 0.785398,
                "proxy_saturates_for_thin_runs_up_to_length": 12,
            },
        ),
        ParameterRecord(
            parameter_id="review_status_bands",
            question="Are the review-status bands calibratable at all?",
            current_value="0.30 / 0.40 / 0.65, plus penalty triggers at 0.34-0.70",
            unit="quality and evidence scores (dimensionless)",
            production_sites=(
                "groundscan/gates/quality.py:300-311 (assess_candidate_quality)",
                "groundscan/gates/quality.py:238-276 (penalty triggers)",
            ),
            status=STATUS_NOT_APPLICABLE,
            dataset="not reached -- the scalars are inline literals, not parameters",
            sample_count=0,
            derivation=(
                "Ten of the seventeen scalars in the gate chain are written as inline "
                "literals at their comparison site inside assess_candidate_quality, not as "
                "fields of a config object. A one-factor sweep cannot reach them, so their "
                "sensitivity is not measured here and no status of 'inert' is claimed for "
                "them: unreachability is a different finding from insensitivity, and its "
                "remedy is concrete."
            ),
            uncertainty=(
                "The bands' original derivation is a v0.2 synthetic benchmark, and the "
                "disclosure that evidence enters the quality score twice (effective weight "
                "about 0.68) is already in the source. Neither fact is a measurement, and "
                "nothing here can turn either into one."
            ),
            applicability=(
                "The whole review_status band set. The evidence and screening scalars in the "
                "same chain are reachable and are characterized separately."
            ),
            rationale=(
                "The question does not arise as a calibration question, because these "
                "constants are not reachable as parameters: they are literals at their "
                "comparison sites. Naming these ten in one config object would make them "
                "characterizable, auditable and reportable as a set; today they are spread "
                "across eleven comparison sites in one function. That is a structural "
                "observation about the code, and it is the actionable part of this row."
            ),
            recommended_action=(
                "Do not attempt to calibrate what cannot be swept. Promote the ten "
                "literals to a named config object first -- a pure refactor with no "
                "behaviour change -- then characterize them with the harness that already "
                "exists. Do not adjust any of them in the meantime."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.evidence_quality_sensitivity_matrix",
                "n_sweepable_specs": 7,
                "n_unsweepable_specs": 10,
            },
        ),
        ParameterRecord(
            parameter_id="classify.hypothesis_min_margin",
            question="Is the second evidence margin load-bearing?",
            current_value=0.04,
            unit="final cavity/tunnel margin (dimensionless, rounded to 3 dp)",
            production_sites=("groundscan/core/classify.py:54 (ClassificationConfig)",),
            status=STATUS_MODEL_CHOICE,
            dataset="perturbation + vendor (candidate population), one factor at a time",
            sample_count=111,
            derivation=(
                "Swept on its own through the classifier rather than through the evidence "
                "model, because it is read by a different function on a different score "
                "pair. It is the *second* margin in the system and acts only on the "
                "cavity-like vs tunnel-like arbitration, where the two are a constrained "
                "pair rather than eight competing hypotheses."
            ),
            uncertainty=(
                "Swept over 0.00-0.20 in both directions and it changed **no** decision on "
                "this population: 0 classification changes at every value. That is an "
                "inertness finding, not a validation -- the population's cavity/tunnel pairs "
                "are few and their margins sit well clear of the gate, so the sweep has "
                "little to act on."
            ),
            applicability=(
                "The cavity-like vs tunnel-like arbitration only. It is a different "
                "quantity from evidence.min_margin and the two were never combined in this "
                "work."
            ),
            rationale=(
                "Inert on this corpus and unjustified anywhere else. Those are two different "
                "statements, and the register records the first while refusing to promote "
                "it to the second. No evidence here discriminates between the swept "
                "neighbours 0.00, 0.02, 0.04, 0.08 and 0.16 -- the population has few "
                "cavity/tunnel pairs and none with a margin near the gate, so every one of "
                "those values produces the same decisions. The neighbours are therefore "
                "named and left as they are, and the constant is neither moved nor removed: "
                "removing it would be a behaviour change justified by a corpus that cannot "
                "distinguish it from any other value in its range."
            ),
            recommended_action=(
                "Keep 0.04. Do not read the inertness as validation, and do not remove the "
                "constant. A population with tight cavity/tunnel pairs would exercise the "
                "gate, and none is available here."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.evidence_quality_sensitivity_matrix",
                "sweepable": True,
                "max_n_any_changed": 0,
                "n_swept_values": 10,
            },
        ),
        ParameterRecord(
            parameter_id="screening.primary_threshold",
            question="Is the 0.70 screening band meaningful or inert?",
            current_value=0.70,
            unit="screening score (dimensionless heuristic, not a probability)",
            production_sites=("groundscan/gates/screening.py:27",),
            status=STATUS_PROVISIONAL,
            dataset="perturbation + vendor (candidate population)",
            sample_count=95,
            derivation=(
                "Swept alone on a fixed population, with the evidence selection and the "
                "review_status recomputed under each value so the whole chain was observed "
                "rather than just the retention decision."
            ),
            uncertainty=(
                "The band was selected on the calibration half of a deterministic synthetic "
                "benchmark and evaluated on the holdout half, which makes it a software-"
                "validation parameter by its own documentation. The measured population cannot "
                "say whether 0.70 is the right retention point, because no ground truth exists "
                "for what should be retained."
            ),
            applicability=(
                "Applies to the single-scan and site screening stages. The rescue band, the "
                "rescue conjuncts and the review-status bands are separate scalars and are "
                "recorded separately in the sensitivity matrix."
            ),
            rationale=(
                "The band's own documentation already disclaims field calibration. The "
                "characterization adds the measured sensitivity and confirms the band is not "
                "inert, which is as far as this evidence can go."
            ),
            recommended_action=(
                "Keep 0.70. Keep the existing software-validation disclaimer; it is accurate."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.decision.evidence_quality_sensitivity_matrix",
            },
        ),
        ParameterRecord(
            parameter_id="field_evidence",
            question="Can any physical threshold be calibrated against field truth?",
            current_value=None,
            unit="not applicable",
            production_sites=(),
            status=STATUS_INSUFFICIENT_EVIDENCE,
            dataset="category D: empty",
            sample_count=0,
            derivation=(
                "The enumerated gaps are recorded in calibration.datasets."
                "field_evidence_availability(): no verified ground truth, no instrument "
                "response calibration record, no repeat-survey set, no known-buried-content "
                "survey. None of them exists in this repository."
            ),
            uncertainty="Not applicable -- the category is empty, not uncertain.",
            applicability=(
                "Blocks every parameter whose calibration requires knowing what is in the "
                "ground. Does not block the analytic results, which need no field data."
            ),
            rationale=(
                "Recording the absence as a first-class, queryable fact is the only defensible "
                "handling. Treating vendor annotations as the substitute would convert a claim "
                "about a scan into a measurement of the ground, which is the error this whole "
                "task is structured to prevent."
            ),
            recommended_action=(
                "Report category D as unavailable in every deliverable. Do not substitute "
                "vendor annotations."
            ),
            activation=ACTIVATION_REQUIRES_FIELD_VALIDATION,
        ),
        ParameterRecord(
            parameter_id="scale_status_x_anomaly_zscore",
            question="Does a degraded scale read differently in the z-score?",
            current_value=None,
            unit="not applicable -- the status never reaches the candidate",
            production_sites=(
                "groundscan/diagnostics/shadow.py (S03 shadow)",
                "groundscan/diagnostics/shadow.py (ScaleShadow)",
            ),
            status=STATUS_NOT_APPLICABLE,
            dataset="perturbation + vendor (candidate population)",
            sample_count=90,
            derivation=(
                "Measured by reading the scale status off every candidate in the population. "
                "All 90 report an empty status, because the field does not exist on Candidate: "
                "the S03 status is carried by the shadow ledger and the technical diagnostics "
                "block, both of which are off by default and decide nothing."
            ),
            uncertainty="Not applicable: there is no status on the candidate path to condition on.",
            applicability=(
                "Applies to the shadow/diagnostics channel only. The interaction the brief "
                "asks about cannot arise there, because the diagnostics channel does not feed "
                "a threshold."
            ),
            rationale=(
                "Answering this as NOT APPLICABLE with the measurement attached is more useful "
                "than reporting a correlation of zero: it says the coupling is absent *by "
                "construction*, which is a stronger and more actionable statement than a "
                "measured absence."
            ),
            recommended_action=(
                "No action. If S03 is ever activated on the candidate path, this interaction "
                "becomes real and must be re-measured before any z-score threshold is trusted."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
            measured_evidence={
                "probe": "calibration.interactions.scale_status_x_anomaly_zscore",
                "n_candidates_carrying_a_status_field": 0,
            },
        ),
        ParameterRecord(
            parameter_id="s01_decomposition.d_res",
            question="Should the S01 decomposition be activated now?",
            current_value="conservative-nest",
            unit="policy identity",
            production_sites=("groundscan/site/separation.py:34 (SeparationConfig)",),
            status=STATUS_NOT_APPLICABLE,
            dataset="not reached -- the policy takes the conservative branch at every separation",
            sample_count=21,
            derivation=(
                "Measured by sweeping the separation of a constructed pair and observing that "
                "the decomposition policy has no crossing: it nests at every separation, so "
                "there is no d_res value it would disagree with. Activating d_res would "
                "introduce a new decision, not adjust an existing one."
            ),
            uncertainty="Not applicable -- the measured crossing is the only evidence available.",
            applicability="The S01 production decomposition is unchanged and stays unchanged.",
            rationale=(
                "The question does not arise for the policy as it stands, because the "
                "conservative-nest branch has no threshold to calibrate: it nests at every "
                "separation, so there is no d_res value for it to be wrong about. Activating "
                "d_res would introduce a new decision rather than adjust an existing one, and "
                "Stage 3 already left S01 characterized and not activated. Nothing measured "
                "here supplies the missing evidence; it supplies a curve."
            ),
            recommended_action=(
                "No activation. The separation curve is available as evidence for a future "
                "activation review."
            ),
            activation=ACTIVATION_NOT_ACTIVATED,
        ),
    )


def status_counts(records: Sequence[ParameterRecord] | None = None) -> dict[str, int]:
    """How many parameters landed in each status. The roll-up a reviewer wants first."""
    table = tuple(records) if records is not None else parameter_register()
    counts = {status: 0 for status in PARAMETER_STATUSES}
    for record in table:
        counts[record.status] += 1
    return counts


def activation_decisions(records: Sequence[ParameterRecord] | None = None) -> dict[str, str]:
    """The activation decision per parameter, as a flat mapping.

    Nothing in this stage is ``ACTIVATED``. That is the expected outcome of a
    characterization pass whose evidence base contains no field data, and it is
    reported as a result rather than as a failure to complete.
    """
    table = tuple(records) if records is not None else parameter_register()
    return {record.parameter_id: record.activation for record in table}


def register_report() -> dict[str, Any]:
    """The whole table as JSON, with the status and activation roll-ups."""
    table = parameter_register()
    activations = activation_decisions(table)
    return {
        "statuses": list(PARAMETER_STATUSES),
        "activations": list(ACTIVATION_DECISIONS),
        "n_parameters": len(table),
        "status_counts": status_counts(table),
        "activation_counts": {
            key: sum(1 for v in activations.values() if v == key) for key in ACTIVATION_DECISIONS
        },
        "n_activated": sum(1 for v in activations.values() if v == ACTIVATION_ACTIVATED),
        "records": [record.to_dict() for record in table],
    }

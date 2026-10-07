"""Phase J -- the operating envelope, with its three confidence tiers.

An operating envelope is only useful if a reader can tell, for every statement in
it, *how much* it rests on. So every row carries exactly one tier, drawn from a
closed set:

``validated operating range``
    A range the characterization actually exercised, with a measured outcome at
    every point in it. Says what was tested, not what is true in general.

``engineering assumption``
    A range the code was exercised over because it had to be exercised over
    something, with no evidence that it is the right range. These are the rows a
    reader is most likely to mistake for validated, so they are named as
    assumptions in the row itself.

``unknown``
    A quantity the product needs and this work could not determine. Present in
    the table with its value absent, so its absence is visible rather than
    inferred from a silence.

The tiers are not decoration. ``docs/thresholds.md`` and the generated
machine contract both read threshold-looking numbers, and a validated range and an
assumption rendered identically are indistinguishable once they leave this file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

TIER_VALIDATED = "validated operating range"
TIER_ASSUMPTION = "engineering assumption"
TIER_UNKNOWN = "unknown"

ENVELOPE_TIERS: tuple[str, ...] = (TIER_VALIDATED, TIER_ASSUMPTION, TIER_UNKNOWN)


@dataclass(frozen=True)
class EnvelopeRow:
    """One envelope statement, with its tier and the evidence that set it."""

    row_id: str
    quantity: str
    value: Any
    unit: str
    tier: str
    evidence: str
    limitation: str

    def __post_init__(self) -> None:
        if self.tier not in ENVELOPE_TIERS:
            raise ValueError(f"{self.row_id}: tier {self.tier!r} is not one of {ENVELOPE_TIERS}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "quantity": self.quantity,
            "value": self.value,
            "unit": self.unit,
            "tier": self.tier,
            "evidence": self.evidence,
            "limitation": self.limitation,
        }


def operating_envelope(
    *,
    swept_pitches_m: Sequence[float] = (0.25, 0.5, 1.0),
    swept_dy_ratios: Sequence[float] = (1.0, 2.0),
    swept_sigmas_m: Sequence[float] = (0.5, 1.0, 1.5, 2.0),
    swept_noise_sigmas: Sequence[float] = (0.5, 1.0, 2.0),
    swept_response_amplitudes: Sequence[float] = (3.0, 5.0, 7.0, 10.0, 14.0, 20.0),
) -> dict[str, Any]:
    """The envelope, as rows, with the swept range and the tier of each claim.

    Every numeric range below is a *swept* range: the span the characterization
    actually ran. Reading one as a supported range would be reading a test design
    as a specification, which is why the tier column is load-bearing and why the
    ``unknown`` rows are present at all.
    """
    rows: list[EnvelopeRow] = [
        EnvelopeRow(
            row_id="lattice.dx",
            quantity="sampling pitch, x",
            value={"from": min(swept_pitches_m), "to": max(swept_pitches_m)},
            unit="m",
            tier=TIER_VALIDATED,
            evidence=(
                "the separation sweep, the min_size boundary walk and the cross-resolution "
                "comparison were all run at 0.25, 0.5 and 1.0 m, and a measured outcome was "
                "recorded at each"
            ),
            limitation=(
                "the product has been used outside this range in practice; nothing here "
                "was measured there, so 'validated' means exercised, not endorsed"
            ),
        ),
        EnvelopeRow(
            row_id="lattice.dy_over_dx",
            quantity="lattice anisotropy",
            value={"from": min(swept_dy_ratios), "to": max(swept_dy_ratios)},
            unit="ratio",
            tier=TIER_VALIDATED,
            evidence=(
                "every d_res cell was run at both an isotropic and a 2:1 lattice; solidity "
                "was additionally proven invariant to any ratio, and compactness was "
                "measured on anisotropic cells"
            ),
            limitation=(
                "no ratio above 2:1 was exercised, and highly anisotropic surveys are a "
                "common real acquisition pattern, so this range is narrower than practice"
            ),
        ),
        EnvelopeRow(
            row_id="response.width",
            quantity="constructed response width (1 sigma)",
            value={"from": min(swept_sigmas_m), "to": max(swept_sigmas_m)},
            unit="m",
            tier=TIER_VALIDATED,
            evidence=(
                "one d_res surface was swept per sigma, and the analytic bifurcation scale "
                "2*sigma was measured and confirmed at each"
            ),
            limitation=(
                "a Gaussian width is a modelling choice; a real instrument's response width "
                "is not measured anywhere in this repository"
            ),
        ),
        EnvelopeRow(
            row_id="response.width_in_pitch",
            quantity="response width expressed in pitch units",
            value={"from": 0.5, "to": 4.0},
            unit="sigma / pitch",
            tier=TIER_VALIDATED,
            evidence=(
                "the swept surface spans sigma 0.5-2.0 m against pitch 0.25-1.0 m, i.e. "
                "0.5 to 8 sigma per pitch, and a crossing exists in every combination"
            ),
            limitation=(
                "at sigma/pitch below about 1 the response is barely sampled and one d_res "
                "cell was non-monotone, so the low end is characterised as unreliable rather "
                "than as supported"
            ),
        ),
        EnvelopeRow(
            row_id="signal.amplitude",
            quantity="constructed peak amplitude over the noise sigma",
            value={"from": 1.0, "to": 40.0},
            unit="peak SNR",
            tier=TIER_VALIDATED,
            evidence=(
                "the amplitude ladder (3-20) and the noise ladder (0.25-3.0) were swept and "
                "cross to give SNR 1.0-40.0; the 3-sigma false-positive characterization was "
                "run at SNR 0 (noise-only) and at the ladder's top"
            ),
            limitation=(
                "SNR here is amplitude over the *assumed* Gaussian sigma. A real "
                "instrument's noise floor, drift and gain stability are not measured, so "
                "this row describes the forward model and not any device"
            ),
        ),
        EnvelopeRow(
            row_id="residual.scale",
            quantity="smallest residual scale the estimator will report as a measurement",
            value=1e-9,
            unit="residual units (relative to the residual's own extent)",
            tier=TIER_ASSUMPTION,
            evidence=(
                "groundscan._util.SCALE_DEGENERACY_TOLERANCE; Stage 3 characterized it and "
                "measured zero output changes from it over the corpus"
            ),
            limitation=(
                "it is an arithmetic floor, chosen to sit clear of round-off, and it is "
                "NOT a physical resolution. Treating it as one would claim the product can "
                "resolve features at the double-precision limit of the subtraction that "
                "produced the residual. Whether any real acquisition reaches it is unknown"
            ),
        ),
        EnvelopeRow(
            row_id="resolution.d_res",
            quantity="spatial distinguishability of two equal responses",
            value=None,
            unit="m",
            tier=TIER_UNKNOWN,
            evidence=(
                "the analytic floor is exactly 2*sigma; the delivered limit was measured as "
                "a factor of that floor between 1.5 and 3.0 across the swept surface, and no "
                "single value is defensible without naming sigma, pitch, noise and anisotropy"
            ),
            limitation=(
                "a single d_res cannot be reported. The operating-factor surface is the "
                "envelope rule; see the separation-curve rows in the calibration report"
            ),
        ),
        EnvelopeRow(
            row_id="resolution.unresolved_band",
            quantity="separations whose outcome is draw-dependent",
            value="1.1x to 2.0x of 2*sigma, at pitch 0.5 m, sigma 1.0 m, noise 1.0",
            unit="multiples of 2*sigma",
            tier=TIER_VALIDATED,
            evidence=(
                "measured directly: across three independent noise draws, the 1.1x-2.0x band "
                "contains every multiplier at which the draws disagreed, and 0 of the "
                "multipliers above 2.0x"
            ),
            limitation=(
                "a band stated as a multiplier, not as metres, because the metre value "
                "moves with the response width; quoting a metre band without the width would "
                "be the same error d_res would make"
            ),
        ),
        EnvelopeRow(
            row_id="size.min_size_physical_floor",
            quantity="smallest component area that survives the size filter",
            value=None,
            unit="m^2",
            tier=TIER_UNKNOWN,
            evidence=(
                "min_size = 3 cells implies 3*dx*dy, which is 0.1875 m^2 at a 0.25 m pitch "
                "and 3.0 m^2 at a 1.0 m pitch; the sweep found no candidate unit (cells, "
                "area, response width) that is invariant across the swept pitches"
            ),
            limitation=(
                "reported as unknown rather than as a pitch-dependent number, because a "
                "number that changes with the survey's own sampling cannot be quoted without "
                "quoting the sampling"
            ),
        ),
        EnvelopeRow(
            row_id="sample.minimum_cells",
            quantity="smallest grid the detector was exercised on",
            value={"from": 32, "to": 128},
            unit="cells per axis",
            tier=TIER_VALIDATED,
            evidence=(
                "the false-positive characterization was measured on 64x64 and 128x128 "
                "noise-only fields, and 32x96 for the single-response boundary walk; 128 is "
                "the smallest measured size at which any excursion survived both downstream "
                "filters"
            ),
            limitation=(
                "below roughly 4x4 cells fewer than two detector scales are viable and the "
                "multiscale persistence guard is skipped by design; nothing in this work "
                "characterizes a grid that small. The measured surviving-region count is zero "
                "on every field below 128x128, which is a fact about the filters and not a "
                "guarantee for a grid of a different aspect"
            ),
        ),
        EnvelopeRow(
            row_id="raster.sensitivity_solidity",
            quantity="sensitivity of a candidate's solidity to the sampling pitch",
            value={"metric": 0.0, "population": "up to 0.278 measured"},
            unit="absolute solidity",
            tier=TIER_VALIDATED,
            evidence=(
                "the metric is exactly pitch-invariant (max deviation 2e-15 over three orders "
                "of magnitude of pitch, 1/25 and 25/1 anisotropy, and a survey-magnitude "
                "origin); the *population* shifts by up to 0.278 between 0.25 m and 1.0 m "
                "because the raster produces different cell sets"
            ),
            limitation=(
                "the two movements must not be added. The metric cannot move; the shape the "
                "detector finds can. This is why a solidity band is pitch-free as a "
                "comparison and still regime-dependent as a population"
            ),
        ),
        EnvelopeRow(
            row_id="raster.sensitivity_compactness",
            quantity="sensitivity of a candidate's compactness to component size",
            value={"max_abs_delta_across_pitch": 0.728504, "corr_with_cell_count": 0.5994},
            unit="compactness",
            tier=TIER_VALIDATED,
            evidence=(
                "the exact exposed-edge quotient is pi/4 for every k x k block while the "
                "production proxy runs 1.0 up to k = 8; a one-cell run saturates at 1.0 up to "
                "length 12; 47 of 55 shapes with a true compactness below 0.50 pass all "
                "gates"
            ),
            limitation=(
                "this is an estimator property, not a raster artifact, and no pitch or "
                "anisotropy choice removes it"
            ),
        ),
        EnvelopeRow(
            row_id="field.ground_truth",
            quantity="independent ground truth for any physical threshold",
            value=None,
            unit="not applicable",
            tier=TIER_UNKNOWN,
            evidence="calibration.datasets.field_evidence_availability() enumerates the gaps",
            limitation=(
                "no excavated, bored or installation-verified truth; no instrument response "
                "calibration record; no repeat-survey set; no known-buried-content survey. "
                "Vendor annotations are a claim about a scan, not a measurement of the ground"
            ),
        ),
        EnvelopeRow(
            row_id="instrument.noise_model",
            quantity="the acquisition's noise distribution",
            value=None,
            unit="not applicable",
            tier=TIER_UNKNOWN,
            evidence=(
                "the 3-sigma characterization used additive Gaussian noise by choice, and "
                "measured a 4.88x departure from the nominal per-cell rate on it"
            ),
            limitation=(
                "every false-positive figure in this work is a property of an assumed noise "
                "model. None of it is a field-performance estimate and none may be quoted as "
                "one"
            ),
        ),
        EnvelopeRow(
            row_id="survey.line_spacing",
            quantity="the line spacing the product's thresholds were derived for",
            value=None,
            unit="m",
            tier=TIER_UNKNOWN,
            evidence=(
                "the calibration register's deferred row for an operating line-spacing range "
                "remains deferred: this work produced a pitch-swept measurement surface, not "
                "a spacing the thresholds are valid for"
            ),
            limitation=(
                "recording a swept range as a supported spacing would present a test design "
                "as a specification"
            ),
        ),
    ]
    return {
        "tiers": list(ENVELOPE_TIERS),
        "tier_definitions": {
            TIER_VALIDATED: (
                "a range the characterization exercised, with a measured outcome at every "
                "point in it. Says what was tested, not what is true in general."
            ),
            TIER_ASSUMPTION: (
                "a range or value the code had to be exercised over, with no evidence that "
                "it is the right one. The row names itself an assumption so it cannot be "
                "read as validated after it leaves this file."
            ),
            TIER_UNKNOWN: (
                "a quantity the product needs and this work could not determine. Present "
                "with its value absent, so the absence is visible rather than inferred."
            ),
        },
        "swept_ranges": {
            "pitches_m": list(swept_pitches_m),
            "dy_ratios": list(swept_dy_ratios),
            "response_sigmas_m": list(swept_sigmas_m),
            "noise_sigmas": list(swept_noise_sigmas),
            "response_amplitudes": list(swept_response_amplitudes),
        },
        "tier_counts": {tier: sum(1 for r in rows if r.tier == tier) for tier in ENVELOPE_TIERS},
        "n_unknown": sum(1 for r in rows if r.tier == TIER_UNKNOWN),
        "rows": [row.to_dict() for row in rows],
        "reading_rule": (
            "A row in the validated tier is a statement about what was tested. A row in the "
            "assumption tier is a statement about what had to be chosen. A row in the unknown "
            "tier is a statement about what is missing. The tiers are not severities and must "
            "not be summed or ranked."
        ),
    }

"""Shadow measurement for S01: decomposition multiplicity against the independent oracle.

:mod:`groundscan.validation.decomposition_reference` proves what the constructed
fields *are*. This module answers the second question -- what the pipeline
actually does with them, and what it does on real inputs -- by running every
controlled case over its resolution ladder and aspect sweep, and every available
fixture through the same public entry point the product uses.

## What is measured, per run

Every run records the whole causal chain, and keeps the levels separate so a
reader can see which stage moved:

===================================  ==========================================
``anomaly_region_count``             level 2, from the detector's own labelling
``continuous_maxima``                level 3 oracle, analytic, from the forward
                                     model
``sampled_maxima``                   local maxima of the noiseless field on
                                     *this* lattice
``production_seed_maxima``           local maxima of the **replica** production
                                     seed field, at the 90 %-of-peak basin cut
``candidate_count``                  level 4 records emitted
``top_level_count``                  level 4 records with a top-level role
``decomposition_count``              level 5 records
``within_response_separations_m``    the ``d_res`` input (v2 §11.4)
===================================  ==========================================

``production_seed_maxima`` comes from the replica, not from production itself,
and is recorded so the *stage* that moved can be named. It is labelled
``production_seed_field_basins`` in the JSON for exactly that reason.

## What is deliberately not done

* **No threshold is proposed.** :func:`separation_summary` reports the measured
  range of within-response separations and leaves ``proposed_d_res_m`` at
  ``None``, because a ``d_res`` value needs a line-spacing / contrast sweep on
  field or bench data (v2 §15.1, §15.3).
* **No policy is activated.** Nothing here changes a candidate, a score, a
  report or a baseline. It is a census.
* **No count is a count of objects.** Every payload passes
  :func:`~.decomposition_reference.assert_no_object_count_claim`.
"""

from __future__ import annotations

import math
import tempfile
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .decomposition_reference import (
    ASPECT_RATIOS,
    LEVEL_ANOMALY_REGION,
    LEVEL_CANDIDATE_HYPOTHESIS,
    LEVEL_DECOMPOSITION,
    LEVEL_RESPONSE_REGION,
    UNKNOWN_MECHANISM,
    UNRESOLVED_SEPARATION,
    MultiplicityFinding,
    PerturbedRun,
    ResolvableSeparation,
    StabilityVerdict,
    aspect_ladder,
    assert_no_object_count_claim,
    classify_multiplicity,
    compare_runs,
    continuous_maxima_count,
    group_into_responses,
    local_maxima_count,
    multiplicity_excess,
    production_seed_field,
    resolution_ladder,
    separation_distribution,
    superlevel_basin_count,
)
from .synthetic_core.cross_resolution import (
    PhysicalResponse,
    PhysicalScene,
    Resolution,
    sample_scene,
)

#: Roles that are presented as top-level findings by default. Mirrors
#: :data:`groundscan.diagnostics.shadow.TOP_LEVEL_ROLES`, re-declared so this
#: module does not need the shadow flag enabled to read the same vocabulary.
TOP_LEVEL_ROLE_NAMES: frozenset[str] = frozenset({"response", "conflict"})

#: Independent noise draws per rung. One draw is not a characterisation: a count
#: that flickers with the noise seed is a different finding from one that moves
#: with pitch, and the two must not be conflated.
ENSEMBLE_DRAWS: int = 6
DRAW_STRIDE = 7919


def draw_seeds(case: str, resolution: Resolution) -> tuple[int, ...]:
    """Independent noise seeds for one rung of one case.

    Two lattices cannot share a noise sample, so independence is the only honest
    option -- and it is precisely why no cross-resolution comparison here may be
    exact.

    The per-case offset is a **stable** digest, not :func:`hash`: CPython
    randomises string hashing per process, so a ``hash``-derived seed would give a
    different measurement on every run and no result here would be reproducible.
    """
    offset = zlib.crc32(case.encode("utf-8")) % 90_000
    base = 410_000 + offset * 10 + int(round(resolution.dx * 1000)) % 9973
    return tuple(base + DRAW_STRIDE * k for k in range(ENSEMBLE_DRAWS))


# ---------------------------------------------------------------------------
# One measured run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunObservation:
    """Everything measured for one scene at one resolution, levels kept apart."""

    label: str
    case_family: str
    pitch_m: float
    dy_ratio: float
    anomaly_region_count: int
    response_region_count: int
    continuous_maxima: int
    sampled_maxima: int
    production_seed_field_basins: int
    candidate_count: int
    top_level_count: int
    decomposition_count: int
    positions_m: tuple[tuple[float, float], ...]
    patterns: tuple[str, ...]
    roles: tuple[str, ...]
    evidence: tuple[float, ...]
    separation_statuses: tuple[str, ...]
    within_response_separations_m: tuple[float, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "label": self.label,
            "case_family": self.case_family,
            "pitch_m": self.pitch_m,
            "dy_ratio": self.dy_ratio,
            "levels": {
                "anomaly_region": self.anomaly_region_count,
                "response_region": self.response_region_count,
                "candidate_hypothesis": self.candidate_count,
                "decomposition": self.decomposition_count,
            },
            "continuous_maxima": self.continuous_maxima,
            "sampled_maxima": self.sampled_maxima,
            "production_seed_field_basins": self.production_seed_field_basins,
            "top_level_count": self.top_level_count,
            "positions_m": [list(p) for p in self.positions_m],
            "patterns": list(self.patterns),
            "roles": list(self.roles),
            "evidence": [round(float(e), 6) for e in self.evidence],
            "separation_statuses": list(self.separation_statuses),
            "within_response_separations_m": [
                round(float(s), 6) for s in self.within_response_separations_m
            ],
            **self.extra,
        }
        assert_no_object_count_claim(payload)
        return payload


def _roles(candidates: Sequence[Any]) -> tuple[str, ...]:
    from ..diagnostics.shadow import assign_role

    return tuple(assign_role(c) for c in candidates)


def _within_response_separations(candidates: Sequence[Any]) -> tuple[float, ...]:
    from ..diagnostics.shadow import measure_roles

    separations: list[float] = []
    for record in measure_roles(list(candidates)):
        for value in getattr(record, "within_response_separations", ()) or ():
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                separations.append(number)
    return tuple(sorted(separations))


def _record_view(candidate: Any) -> dict[str, Any]:
    """The four fields response grouping needs, nothing else.

    Read from the candidate rather than re-derived, so the grouping is a view of
    the production graph and not a second opinion about it.
    """
    return {
        "separation_status": str(candidate.separation_status),
        "separation_parent_id": candidate.separation_parent_id,
        "id": int(candidate.id),
        "x": float(candidate.x_center),
        "y": float(candidate.y_center),
        "pattern": str(candidate.pattern_hypothesis),
    }


def observe_run(
    scene: PhysicalScene,
    resolution: Resolution,
    *,
    seed: int,
    config: Any | None = None,
) -> RunObservation:
    """Run the public single-scan path once and record one observation.

    ``analyze_scan`` is called rather than any internal stage, so what is
    measured is the reachable behaviour, not a stage's intermediate state.
    """
    from ..core.anomaly import detect_anomalies
    from ..core.grid import reconstruct_grid
    from ..services.config import AnalysisConfig
    from ..services.single_scan import analyze_scan

    cfg = config or AnalysisConfig()
    scan = sample_scene(scene, resolution, seed=seed)
    with tempfile.TemporaryDirectory(prefix="s01_") as tmp:
        _grid, anomaly, candidates = analyze_scan(
            scan,
            tmp,
            label=f"{scene.name}-{resolution.name}",
            config=cfg,
            write_outputs=False,
        )

    # Rebuild the replica seed field from the detector's own z-map, on its own
    # grid, so the basin count is measured rather than modelled.
    rebuilt = reconstruct_grid(scan)
    rebuilt_anomaly = detect_anomalies(
        rebuilt,
        threshold=float(cfg.threshold),
        min_size=int(cfg.min_size),
        background_method=str(cfg.background_method),
        scales=tuple(cfg.scales),
        connectivity=int(cfg.connectivity),
    )
    seed_field, seed_mask = production_seed_field(rebuilt_anomaly.zscore, support_threshold=0.28)
    basins = superlevel_basin_count(seed_field, seed_mask)

    xs, ys = scene.x_samples(resolution), scene.y_samples(resolution)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    sampled = local_maxima_count(scene.value_at(xx, yy))

    roles = _roles(candidates)
    # Level 3 is read from the graph production already records, never from
    # `response_component_ids`: the single-scan stage back-fills that field with
    # `[own id]` for every candidate, so it reports one response region per
    # fragment and would report zero multiplicity for the defect it is meant to
    # measure.
    groups = group_into_responses([_record_view(c) for c in candidates])
    del anomaly  # the rebuilt map is the one the replica is measured on
    return RunObservation(
        label=f"{scene.name}@{resolution.name}",
        case_family=scene.case_family,
        pitch_m=float(resolution.dx),
        dy_ratio=float(resolution.dy_ratio),
        anomaly_region_count=int(rebuilt_anomaly.n_components),
        response_region_count=len(groups),
        continuous_maxima=continuous_maxima_count(scene),
        sampled_maxima=sampled,
        production_seed_field_basins=basins,
        candidate_count=len(candidates),
        top_level_count=sum(1 for r in roles if r in TOP_LEVEL_ROLE_NAMES),
        decomposition_count=sum(1 for r in roles if r not in TOP_LEVEL_ROLE_NAMES),
        positions_m=tuple(
            (round(float(c.centroid_weighted_x), 6), round(float(c.centroid_weighted_y), 6))
            for c in candidates
        ),
        patterns=tuple(str(c.pattern_hypothesis) for c in candidates),
        roles=roles,
        evidence=tuple(float(c.evidence_score) for c in candidates),
        separation_statuses=tuple(str(c.separation_status) for c in candidates),
        within_response_separations_m=_within_response_separations(candidates),
        extra={
            "constructed_response_count": scene.response_count,
            "multiplicity_excess": multiplicity_excess(groups),
            "response_groups": [g.to_dict() for g in groups],
        },
    )


# ---------------------------------------------------------------------------
# Per-case characterization
# ---------------------------------------------------------------------------


def characterize_case(
    scene: PhysicalScene,
    *,
    config: Any | None = None,
    pitches: tuple[float, ...] | None = None,
) -> tuple[tuple[RunObservation, ...], tuple[StabilityVerdict, ...], MultiplicityFinding]:
    """Measure one controlled case over its resolution ladder.

    Returns the per-rung observations, the stability verdicts over independent
    noise draws, and one :class:`MultiplicityFinding` carrying the mechanism
    assignment for the case's largest observed multiplicity difference.
    """
    ladder = resolution_ladder(scene.width_m, scene.height_m, pitches or (1.0, 0.5, 0.25, 0.125))
    single = tuple(
        observe_run(scene, resolution, seed=draw_seeds(scene.name, resolution)[0], config=config)
        for resolution in ladder
    )

    verdicts: list[StabilityVerdict] = []
    for resolution in ladder:
        runs = tuple(
            observe_run(scene, resolution, seed=seed, config=config)
            for seed in draw_seeds(scene.name, resolution)
        )
        verdicts.append(
            compare_runs(
                f"{scene.name}@{resolution.name}",
                tuple(
                    PerturbedRun(
                        label=f"draw{i}",
                        candidate_count=o.candidate_count,
                        top_level_count=o.top_level_count,
                        positions_m=o.positions_m,
                        roles=o.roles,
                        patterns=o.patterns,
                        evidence=o.evidence,
                        pitch_m=o.pitch_m,
                    )
                    for i, o in enumerate(runs)
                ),
            )
        )

    # The multiplicity claim only concerns records that share a response region.
    # A rung whose records are all separate components is level-2 behaviour, and
    # when there are more components than the field has maxima that is noise
    # fragmentation -- a different finding, reported separately rather than
    # folded into the mechanism below.
    excess_rungs = [o for o in single if int(o.extra.get("multiplicity_excess", 0)) > 0]
    worst = max(
        excess_rungs,
        key=lambda o: int(o.extra.get("multiplicity_excess", 0)),
        default=None,
    )
    if worst is None:
        finding = MultiplicityFinding(
            label=f"{scene.name}/ladder",
            mechanism=UNKNOWN_MECHANISM,
            continuous_maxima=single[0].continuous_maxima if single else 0,
            sampled_maxima=single[0].sampled_maxima if single else 0,
            production_seed_maxima=single[0].production_seed_field_basins if single else 0,
            anomaly_region_count=sum(o.anomaly_region_count for o in single),
            top_level_count=sum(o.top_level_count for o in single),
            decomposition_count=sum(o.decomposition_count for o in single),
            excess_records=0,
            notes=(
                "no rung emitted more than one record per response region; there is no "
                "multiplicity difference to classify, so no mechanism is claimed"
            ),
            evidence={
                "ladder_rungs": [o.label for o in single],
                "multiplicity_excess_per_rung": [
                    int(o.extra.get("multiplicity_excess", 0)) for o in single
                ],
                "top_level_counts": [o.top_level_count for o in single],
                "continuous_maxima_counts": [o.continuous_maxima for o in single],
                "anomaly_region_counts": [o.anomaly_region_count for o in single],
                "draw_to_draw_candidate_counts": [
                    list(v.metrics["candidate_counts"]) for v in verdicts
                ],
            },
        )
        return single, tuple(verdicts), finding

    independent = sum(1 for o in single for s in o.separation_statuses if s == "none")
    finding = MultiplicityFinding(
        label=f"{scene.name}/ladder",
        mechanism=classify_multiplicity(
            continuous_maxima=worst.continuous_maxima,
            sampled_maxima=worst.sampled_maxima,
            production_seed_maxima=worst.production_seed_field_basins,
            record_count=worst.candidate_count,
            anomaly_region_count=worst.anomaly_region_count,
            independent_components=independent,
            separation_median_m=_median(worst.within_response_separations_m),
            pitch_m=worst.pitch_m,
            dy_ratio=worst.dy_ratio,
        ),
        continuous_maxima=worst.continuous_maxima,
        sampled_maxima=worst.sampled_maxima,
        production_seed_maxima=worst.production_seed_field_basins,
        anomaly_region_count=worst.anomaly_region_count,
        top_level_count=worst.top_level_count,
        decomposition_count=worst.decomposition_count,
        excess_records=int(worst.extra.get("multiplicity_excess", 0)),
        within_response_separations_m=worst.within_response_separations_m,
        notes=(
            f"worst ladder rung {worst.label}: "
            f"{int(worst.extra.get('multiplicity_excess', 0))} record(s) beyond one per "
            f"response region, from {worst.continuous_maxima} continuous maximum"
        ),
        evidence={
            "ladder_rungs": [o.label for o in single],
            "multiplicity_excess_per_rung": [
                int(o.extra.get("multiplicity_excess", 0)) for o in single
            ],
            "top_level_counts": [o.top_level_count for o in single],
            "continuous_maxima_counts": [o.continuous_maxima for o in single],
            "anomaly_region_counts": [o.anomaly_region_count for o in single],
            "production_seed_field_basins": [o.production_seed_field_basins for o in single],
            "independent_record_counts": [independent],
            "draw_to_draw_candidate_counts": [
                list(v.metrics["candidate_counts"]) for v in verdicts
            ],
        },
    )
    return single, tuple(verdicts), finding


def _median(values: Sequence[float]) -> float | None:
    finite = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not finite:
        return None
    middle = len(finite) // 2
    return finite[middle] if len(finite) % 2 else 0.5 * (finite[middle - 1] + finite[middle])


# ---------------------------------------------------------------------------
# Anisotropy (Phase F)
# ---------------------------------------------------------------------------


def anisotropy_sweep(
    scene: PhysicalScene, *, dx: float = 0.5, config: Any | None = None
) -> tuple[RunObservation, ...]:
    """The same physical field, the same ``dx``, only ``dy/dx`` varying.

    This is the experiment that separates *resolution* from *lattice geometry*.
    Holding the field and the x pitch fixed makes the aspect ratio the only
    moving variable, so any count that changes is attributable to anisotropy
    rather than to sampling density.
    """
    return tuple(
        observe_run(scene, resolution, seed=7_000 + index, config=config)
        for index, resolution in enumerate(
            aspect_ladder(scene.width_m, scene.height_m, dx, ASPECT_RATIOS)
        )
    )


# ---------------------------------------------------------------------------
# Perturbation families (Phase G)
# ---------------------------------------------------------------------------


def _run(scene: PhysicalScene, resolution: Resolution, seed: int, config: Any) -> PerturbedRun:
    o = observe_run(scene, resolution, seed=seed, config=config)
    return PerturbedRun(
        label=scene.name,
        candidate_count=o.candidate_count,
        top_level_count=o.top_level_count,
        positions_m=o.positions_m,
        roles=o.roles,
        patterns=o.patterns,
        evidence=o.evidence,
        pitch_m=o.pitch_m,
    )


def perturbation_families(
    scene: PhysicalScene, *, config: Any | None = None
) -> dict[str, StabilityVerdict]:
    """Every controlled perturbation family required by Phase G.

    The families are:

    ``noise``
        independent draws on the *same* lattice, so nothing but the noise moves;
    ``translation``
        the response walked across the field in 0.5 m steps;
    ``amplitude`` / ``width`` / ``rotation``
        the response's own parameters perturbed about the construction.

    Each is reduced by :func:`compare_runs` under the tolerances declared in
    :mod:`.decomposition_reference`, so an instability is a measurement against
    a stated threshold rather than an impression. The declared vocabulary
    separates count, location, role, classification and evidence instability,
    because a family can hold its count and still flip its label -- which is a
    finding, not a stable result.
    """
    from .synthetic_core.cross_resolution import PhysicalResponse as _Resp

    cfg = config or default_config()
    mid = resolution_ladder(scene.width_m, scene.height_m, (0.5,))[0]
    base = scene.responses[0]
    centre_x, centre_y = base.cx, base.cy
    families: dict[str, StabilityVerdict] = {}

    def variant(
        name: str,
        *,
        cx: float = centre_x,
        cy: float = centre_y,
        sigma_x: float = base.sigma_x,
        sigma_y: float = base.sigma_y,
        amplitude: float = base.amplitude,
        orientation_deg: float = base.orientation_deg,
    ) -> PhysicalScene:
        """The scene with its first response's parameters overridden.

        Spelled out rather than ``**overrides`` so the parameter set is checked
        against :class:`PhysicalResponse` at the call site, and a renamed field
        becomes a mypy error instead of a runtime surprise.
        """
        return _single(
            scene,
            _Resp(
                label=base.label,
                cx=float(cx),
                cy=float(cy),
                sigma_x=float(sigma_x),
                sigma_y=float(sigma_y),
                amplitude=float(amplitude),
                orientation_deg=float(orientation_deg),
            ),
            name,
        )

    # -- noise: the same construction and lattice, six independent draws ----
    families["noise"] = compare_runs(
        "noise",
        tuple(_run(scene, mid, 30_000 + 101 * k, cfg) for k in range(ENSEMBLE_DRAWS)),
    )

    # -- translation: the response walked across the field -------------------
    translations = []
    for step in (0.0, 0.5, 1.0, 1.5, 2.0):
        moved = variant(f"{scene.name}_tx{step:g}", cx=centre_x + step)
        translations.append(_run(moved, mid, 31_000, cfg))
    families["translation"] = compare_runs("translation", tuple(translations))

    # -- amplitude -----------------------------------------------------------
    amplitudes = []
    for factor in (0.4, 0.6, 0.8, 1.0, 1.5, 2.0):
        scaled = variant(f"{scene.name}_amp{factor:g}", amplitude=base.amplitude * factor)
        amplitudes.append(_run(scaled, mid, 32_000, cfg))
    families["amplitude"] = compare_runs("amplitude", tuple(amplitudes))

    # -- width: isotropic, so both sigmas scale together ----------------------
    widths = []
    for factor in (0.5, 0.75, 1.0, 1.5, 2.0):
        scaled = variant(
            f"{scene.name}_w{factor:g}",
            sigma_x=base.sigma_x * factor,
            sigma_y=base.sigma_y * factor,
        )
        widths.append(_run(scaled, mid, 33_000, cfg))
    families["width"] = compare_runs("width", tuple(widths))

    # -- rotation ------------------------------------------------------------
    rotations = []
    for angle in (0.0, 10.0, 20.0, 30.0, 45.0, 60.0):
        turned = variant(f"{scene.name}_rot{angle:g}", orientation_deg=angle)
        rotations.append(_run(turned, mid, 34_000, cfg))
    families["rotation"] = compare_runs("rotation", tuple(rotations))

    return families


def _single(scene: PhysicalScene, response: PhysicalResponse, name: str) -> PhysicalScene:
    """The same extent and noise model, carrying exactly one response."""
    return PhysicalScene(
        name=name,
        width_m=scene.width_m,
        height_m=scene.height_m,
        case_family=scene.case_family,
        noise_sigma=scene.noise_sigma,
        responses=(response,),
    )


def default_config() -> Any:
    """The public analysis configuration the measurement runs under."""
    from ..services.config import AnalysisConfig

    return AnalysisConfig()


# ---------------------------------------------------------------------------
# Real-input census
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputCensus:
    """Multiplicity census for one real input."""

    source: str
    candidate_count: int
    top_level_count: int
    decomposition_count: int
    roles: tuple[str, ...]
    separation_statuses: tuple[str, ...]
    positions_m: tuple[tuple[float, float], ...]
    patterns: tuple[str, ...]
    within_response_separations_m: tuple[float, ...]
    parent_ids: tuple[int | None, ...]
    response_component_ids: tuple[tuple[int, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "candidate_count": self.candidate_count,
            "top_level_count": self.top_level_count,
            "decomposition_count": self.decomposition_count,
            "roles": list(self.roles),
            "separation_statuses": list(self.separation_statuses),
            "positions_m": [list(p) for p in self.positions_m],
            "patterns": list(self.patterns),
            "within_response_separations_m": [
                round(float(s), 6) for s in self.within_response_separations_m
            ],
            "separation_parent_ids": list(self.parent_ids),
            "response_component_ids": [list(v) for v in self.response_component_ids],
        }
        assert_no_object_count_claim(payload)
        return payload


def census_scan(scan: Any, *, source: str, config: Any | None = None) -> InputCensus:
    """Run the public single-scan path on a real scan and census the multiplicity."""
    from ..services.single_scan import analyze_scan

    cfg = config or default_config()
    with tempfile.TemporaryDirectory(prefix="s01c_") as tmp:
        _grid, _anomaly, candidates = analyze_scan(
            scan,
            tmp,
            label=source.replace(":", "_").replace("/", "_"),
            config=cfg,
            write_outputs=False,
        )
    return census_candidates(candidates, source=source)


def census_candidates(candidates: Sequence[Any], *, source: str) -> InputCensus:
    roles = _roles(candidates)
    return InputCensus(
        source=source,
        candidate_count=len(candidates),
        top_level_count=sum(1 for r in roles if r in TOP_LEVEL_ROLE_NAMES),
        decomposition_count=sum(1 for r in roles if r not in TOP_LEVEL_ROLE_NAMES),
        roles=roles,
        separation_statuses=tuple(str(c.separation_status) for c in candidates),
        positions_m=tuple(
            (round(float(c.x_center), 6), round(float(c.y_center), 6)) for c in candidates
        ),
        patterns=tuple(str(c.pattern_hypothesis) for c in candidates),
        within_response_separations_m=_within_response_separations(candidates),
        parent_ids=tuple(
            (int(v) if v is not None else None)
            for v in (getattr(c, "separation_parent_id", None) for c in candidates)
        ),
        response_component_ids=tuple(
            tuple(int(v) for v in (getattr(c, "response_component_ids", None) or []))
            for c in candidates
        ),
    )


def synthetic_census() -> Iterator[InputCensus]:
    from .synthetic_core.core import generate_scan, scenario_catalog

    for scenario in scenario_catalog():
        scan, _truth = generate_scan(scenario)
        yield census_scan(scan, source=f"synthetic:{scenario.name}")


def vendor_census() -> Iterator[InputCensus]:
    from ..services.single_scan import load_scan
    from .fixtures import VENDOR_ROOT

    for group in ("train", "validation"):
        for path in sorted((VENDOR_ROOT / group).glob("*.csv")):
            yield census_scan(load_scan(path), source=f"vendor:{group}/{path.stem}")


def golden_census() -> Iterator[InputCensus]:
    """The seven golden cases, through the same harness the golden gate uses."""
    from ..services.single_scan import load_scan
    from .fixtures import VENDOR_ROOT
    from .golden import GOLDEN_SYNTHETIC_SINGLE, GOLDEN_VENDOR_CASES
    from .synthetic_core.core import SyntheticScenario, SyntheticTarget, generate_scan

    for kind, seed in GOLDEN_SYNTHETIC_SINGLE:
        target = SyntheticTarget(kind=kind, x=10.0, y=10.0, depth=2.0, amplitude=12.0)
        scenario = SyntheticScenario(
            name=f"golden_{kind}",
            width_m=20.0,
            height_m=20.0,
            nx=40,
            ny=40,
            targets=(target,),
            noise_sigma=0.5,
            seed=seed,
        )
        scan, _ = generate_scan(scenario)
        yield census_scan(scan, source=f"golden:synth_{kind}")
    for case_id, (subdir, fname) in GOLDEN_VENDOR_CASES.items():
        path = VENDOR_ROOT / subdir / fname
        if path.exists():
            yield census_scan(load_scan(path), source=f"golden:{case_id}")


def site_census(tmp: str | Path | None = None) -> list[InputCensus]:
    """The multiscan path, where ``separate_fused_candidates`` runs on consensus.

    The site call site passes ``allow_single_scan=False`` and the default
    ``support_threshold=0.30``, so it is a genuinely different configuration from
    the single-scan one and is measured separately rather than assumed to match.
    """
    from ..site.analyze_site import analyze_site
    from .synthetic_core.core import SyntheticScenario, SyntheticTarget, generate_scan

    work = Path(tmp) if tmp is not None else Path(tempfile.mkdtemp(prefix="s01site_"))
    scenes = {
        "site_one_response": [("positive_compact", 12.0, 12.0)],
        "site_two_separated": [("positive_compact", 6.0, 12.0), ("positive_compact", 18.0, 12.0)],
        "site_two_close": [("positive_compact", 11.0, 12.0), ("positive_compact", 13.0, 12.0)],
        "site_three_multimodal": [
            ("positive_compact", 4.0, 12.0),
            ("positive_compact", 7.0, 12.0),
            ("positive_compact", 10.0, 12.0),
        ],
    }
    out: list[InputCensus] = []
    for name, targets in scenes.items():
        scans = []
        for index, seed in enumerate((101, 202, 303)):
            scenario = SyntheticScenario(
                name=f"{name}_{index}",
                width_m=24.0,
                height_m=24.0,
                nx=48,
                ny=48,
                targets=tuple(
                    SyntheticTarget(kind=k, x=x, y=y, depth=2.0, amplitude=12.0)
                    for k, x, y in targets
                ),
                noise_sigma=0.5,
                seed=seed,
            )
            scan, _ = generate_scan(scenario)
            scans.append((f"{name}_{index}", scan))
        result = analyze_site(scans, work / name)
        out.append(census_candidates(list(result.fused_candidates), source=f"site:{name}"))
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def separation_summary(censuses: Sequence[InputCensus]) -> dict[str, Any]:
    """Pool the measured within-response separations -- the ``d_res`` input.

    Reports range and shape. Proposes no value, and says why in the payload.
    """
    pooled: list[float] = []
    for census in censuses:
        pooled.extend(census.within_response_separations_m)
    summary = separation_distribution(tuple(pooled))
    assert_no_object_count_claim(summary)
    return summary


def aggregate(censuses: Sequence[InputCensus]) -> dict[str, Any]:
    """Census roll-up: how much multiplicity the real inputs actually carry."""
    payload = {
        "inputs": len(censuses),
        "candidates": sum(c.candidate_count for c in censuses),
        "top_level": sum(c.top_level_count for c in censuses),
        "decomposition": sum(c.decomposition_count for c in censuses),
        "inputs_with_decomposition": sum(1 for c in censuses if c.decomposition_count),
        "inputs_with_multi_record_parent": sum(1 for c in censuses if _has_multi_record_parent(c)),
        "separation_distribution": separation_summary(censuses),
    }
    assert_no_object_count_claim(payload)
    return payload


def _has_multi_record_parent(census: InputCensus) -> bool:
    """Whether one parent id accounts for more than one emitted record.

    The structural form of the S01 defect: several emitted records that the
    pipeline itself attributes to a single parent. This is measured from the
    production ``separation_parent_id`` the pipeline already records, so it does
    not depend on any new inference.
    """
    counts: dict[int, int] = {}
    for status, parent in zip(census.separation_statuses, census.parent_ids, strict=True):
        if status.startswith("decomposed") and parent is not None:
            counts[parent] = counts.get(parent, 0) + 1
    return any(count > 1 for count in counts.values())


def public_path_reachability(tmp: str | Path | None = None) -> dict[str, Any]:
    """Does the multiplicity reach the written machine contract, and how.

    Measured by writing a real analysis and reading it back, not by reading the
    writer. Answers the "final-output impact" question with the artifact itself.
    """
    import csv as _csv
    import json as _json
    import os

    from ..api import analyze
    from .decomposition_reference import RESPONSE_SIGMAS
    from .decomposition_reference import UNRESOLVED_SEPARATION as _sep
    from .synthetic_core.cross_resolution import (
        PhysicalResponse,
        sample_scene,
    )

    del _sep
    scene = PhysicalScene(
        name="reachability_ridge",
        width_m=12.0,
        height_m=12.0,
        case_family="smooth-ridge",
        noise_sigma=1.0,
        responses=(
            PhysicalResponse(
                label="r0", cx=6.0, cy=6.0, sigma_x=3.0, sigma_y=0.5, amplitude=RESPONSE_SIGMAS
            ),
        ),
    )
    resolution = Resolution(name="p0.25", dx=0.25, width_m=12.0, height_m=12.0)
    scan = sample_scene(scene, resolution, seed=11)
    with tempfile.TemporaryDirectory(prefix="s01r_", dir=None) as work:
        result = analyze(scan, out_dir=work, label="reach", write_outputs=True)
        names = sorted(os.listdir(work))
        analysis = _json.loads((Path(work) / "reach_analysis.json").read_text(encoding="utf-8"))
        rows = list(
            _csv.DictReader(
                (Path(work) / "reach_candidates.csv").open(encoding="utf-8", newline="")
            )
        )
    candidates = analysis.get("candidates", [])
    payload = {
        "artifacts": names,
        "candidate_count": len(result.candidates),
        "contract_candidate_count": len(candidates),
        "csv_rows": len(rows),
        "csv_separation_statuses": [r.get("separation_status") for r in rows],
        "csv_parent_ids": [r.get("separation_parent_id") for r in rows],
        "csv_fragment_counts": [r.get("separation_fragment_count") for r in rows],
        "csv_response_component_ids": [r.get("response_component_ids") for r in rows],
    }
    del tmp
    assert_no_object_count_claim(payload)
    return payload


def d_res_state(parameter: ResolvableSeparation = UNRESOLVED_SEPARATION) -> dict[str, Any]:
    """The parameter's own state, carried into the payload so it cannot be read
    as a number that does not exist."""
    payload = dict(parameter.to_dict())
    assert_no_object_count_claim(payload)
    return payload


__all__ = [
    "ENSEMBLE_DRAWS",
    "InputCensus",
    "LEVEL_ANOMALY_REGION",
    "LEVEL_CANDIDATE_HYPOTHESIS",
    "LEVEL_DECOMPOSITION",
    "LEVEL_RESPONSE_REGION",
    "RunObservation",
    "TOP_LEVEL_ROLE_NAMES",
    "aggregate",
    "anisotropy_sweep",
    "census_candidates",
    "census_scan",
    "characterize_case",
    "d_res_state",
    "draw_seeds",
    "golden_census",
    "observe_run",
    "perturbation_families",
    "public_path_reachability",
    "separation_summary",
    "site_census",
    "synthetic_census",
    "vendor_census",
]

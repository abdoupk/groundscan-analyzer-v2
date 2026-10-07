"""Consensus-map target separation for close and overlapping anomaly responses.

Orchestrator (v0.5.2 split): helpers live in separation_seeds /
separation_fragments / separation_diagnostics / separation_dipole.
This module keeps SeparationConfig + separate_fused_candidates and
re-exports moved helpers for backward compatibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from ..models import Candidate
from .separation_diagnostics import (
    _attach_undersegmentation_diagnostic,
    _clone_with_diagnostics,
    diagnose_undersegmentation,
)
from .separation_dipole import resolve_dipole_pairs
from .separation_fragments import _fragment_full_descriptors, _fragment_stats
from .separation_seeds import (
    _depth_layer_seed_pair,
    _find_seeds,
    _finite_peak,
    _parent_is_bipolar,
    _patch_for_candidate,
)


@dataclass(frozen=True)
class SeparationConfig:
    min_distance_px: int = 3
    seed_rel_height: float = 0.35
    seed_min_ratio: float = 0.38
    seed_floor: float = 2.0
    center_clamp_ratio: float = 0.25
    mixed_sign_ratio: float = 0.80
    parent_evidence_min: float = 0.55
    # v0.4.2 (audit F-01 fallout): bipolar-rescue gate. Deliberately mirrors
    # DipoleMergeConfig.min_peak / min_peak_balance: the rescue only lets a
    # low-evidence parent reach the split stage, while the merge gates still
    # decide whether the lobes reunite. Keep the two in sync on purpose.
    bipolar_rescue_min_peak: float = 4.0
    bipolar_rescue_min_balance: float = 0.40
    single_scan_min_anomaly_score: float = 8.0
    single_scan_exempt_patterns: tuple[str, ...] = ("geological-like",)
    artifact_max: float = 0.55
    support_threshold: float = 0.30
    max_seeds_per_parent: int = 4
    # v0.2.65: a very compact, high-strength consensus fragment can occupy
    # only two support cells at coarse fusion resolution. Keep the ordinary
    # minimum at three cells and allow a two-cell fragment only when the
    # multi-scan parent is strongly supported.
    min_fragment_cells: int = 3
    strong_multiscan_min_fragment_cells: int = 2
    strong_multiscan_fragment_peak_ratio: float = 1.15
    # v0.2.46 experimental: depth-layer deblending is opt-in because the
    # available synthetic benchmark does not justify enabling it by default.
    enable_depth_layer_deblending: bool = False


DEFAULT_SEPARATION_CONFIG = SeparationConfig()


# Backward-compat re-exports (moved helpers; import path unchanged for callers).
__all__ = [
    "SeparationConfig",
    "DEFAULT_SEPARATION_CONFIG",
    "separate_fused_candidates",
    "resolve_dipole_pairs",
    "diagnose_undersegmentation",
    "_find_seeds",
    "_patch_for_candidate",
    "_parent_is_bipolar",
    "_depth_layer_seed_pair",
    "_finite_peak",
    "_fragment_stats",
    "_fragment_full_descriptors",
    "_clone_with_diagnostics",
    "_attach_undersegmentation_diagnostic",
]


def separate_fused_candidates(
    candidates: list[Candidate],
    consensus_support: np.ndarray[Any, Any] | None,
    consensus_signed: np.ndarray[Any, Any] | None,
    reference_x: np.ndarray[Any, Any],
    reference_y: np.ndarray[Any, Any],
    *,
    positive_channel: np.ndarray[Any, Any] | None = None,
    negative_channel: np.ndarray[Any, Any] | None = None,
    min_distance_px: int = 3,
    support_threshold: float = 0.30,
    max_seeds_per_parent: int = 4,
    allow_single_scan: bool = False,
    config: SeparationConfig | None = None,
    depth_grid: np.ndarray[Any, Any] | None = None,
    persistence_map: np.ndarray[Any, Any] | None = None,
    artifact_map: np.ndarray[Any, Any] | None = None,
    signal_grid: np.ndarray[Any, Any] | None = None,
    anomaly_threshold: float = 2.0,
    fragment_cells: dict[int, tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]] | None = None,
) -> tuple[list[Candidate], dict[int, int]]:
    """Split fused candidates when consensus evidence contains multiple peaks.

    Returns new candidates plus a mapping ``parent_id -> fragment_count``.  Parents
    with no convincing multi-peak structure are returned unchanged.

    Optional ``depth_grid`` / ``persistence_map`` / ``artifact_map`` /
    ``signal_grid`` must share the support field's grid so each fragment's
    depth, persistence, artifact and signal descriptors are recomputed from its
    own cells instead of inheriting the parent's whole-object statistics.
    Channels with a mismatched shape are ignored.

    ``fragment_cells`` is an optional out-parameter, not part of the return
    contract: when a dict is supplied it is filled with ``fragment_id ->
    (rows, cols)`` in field coordinates. It exists because a fragment's cells are
    discarded here, and a later stage that must reason about the *union* of two
    fragments (the dipole merge) has no other way to get them. It is a side
    channel deliberately rather than a third return value, so that the four
    existing call sites keep working unchanged and a caller that does not need the
    cells pays nothing for them.
    """
    config = config or DEFAULT_SEPARATION_CONFIG
    if min_distance_px == 3:
        min_distance_px = config.min_distance_px
    if support_threshold == 0.30:
        support_threshold = config.support_threshold
    if max_seeds_per_parent == 4:
        max_seeds_per_parent = config.max_seeds_per_parent
    if not candidates or consensus_support is None:
        return candidates, {c.id: 1 for c in candidates}
    support = np.nan_to_num(consensus_support, nan=0.0)
    signed = np.nan_to_num(
        consensus_signed if consensus_signed is not None else np.zeros_like(support), nan=0.0
    )
    pos = np.nan_to_num(
        positive_channel if positive_channel is not None else np.maximum(signed, 0.0), nan=0.0
    )
    neg = np.nan_to_num(
        negative_channel if negative_channel is not None else np.maximum(-signed, 0.0), nan=0.0
    )
    resolution = support.shape[0]
    site_width = float(np.nanmax(reference_x) - np.nanmin(reference_x)) if reference_x.size else 1.0
    site_height = (
        float(np.nanmax(reference_y) - np.nanmin(reference_y)) if reference_y.size else 1.0
    )
    x0 = float(np.nanmin(reference_x)) if reference_x.size else 0.0
    y0 = float(np.nanmin(reference_y)) if reference_y.size else 0.0
    y_axis = np.linspace(y0, y0 + site_height, support.shape[0])
    x_axis = np.linspace(x0, x0 + site_width, support.shape[1])

    out: list[Candidate] = []
    fragment_counts: dict[int, int] = {}
    next_id = 1
    for parent in candidates:
        rs, cs = _patch_for_candidate(
            parent,
            # support is always a 2D consensus field: spell out the pair so
            # the tuple[int, int] contract is statically exact.
            field_shape=(support.shape[0], support.shape[1]),
            x0=x0,
            y0=y0,
            site_width=site_width,
            site_height=site_height,
        )
        s = support[rs, cs]
        p = pos[rs, cs]
        n = neg[rs, cs]

        # Bind the loop-varying slice at definition time (B023): the helper
        # is only ever called synchronously below, but default-arg binding
        # keeps it correct if a call is ever deferred past the iteration.
        def _patch_of(
            field: np.ndarray[Any, Any] | None,
            _rs: slice = rs,
            _cs: slice = cs,
        ) -> np.ndarray[Any, Any] | None:
            if field is None:
                return None
            arr = np.asarray(field)
            if arr.shape != support.shape:
                return None
            return arr[_rs, _cs]

        signed_patch = np.asarray(signed[rs, cs])
        depth_patch = _patch_of(depth_grid)
        persist_patch = _patch_of(persistence_map)
        artifact_patch = _patch_of(artifact_map)
        signal_patch = _patch_of(signal_grid)
        local_mask = s >= support_threshold
        # Build signed response strength before any early exit so overlap diagnostics
        # can also explain parents rejected by safety gates.
        pos_strength = p * np.clip(s, 0.0, 1.0)
        neg_strength = n * np.clip(s, 0.0, 1.0)
        # v0.4.2 (audit F-01 fallout): a fused bipolar parent has muddled
        # morphology BY CONSTRUCTION (both lobes in one object), so its fused
        # evidence score can sit below parent_evidence_min even for very
        # strong responses (Iron Box parent: |z|=38.7 yet margin 0.016 ->
        # unknown, ev 0.26). The old saturated strength curve inflated such
        # parents above this gate; with the desaturated curve the gate would
        # block exactly the resolver built for this case. Strong raw signal
        # plus strong opposite-sign structure -- both pre-evidence-model
        # measurements -- therefore bypass the evidence minimum only.
        # Artifact/broad/scan-count gates still apply, and the downstream
        # pair-score/merge gates still decide the outcome.
        strong_opposite_sign = (
            parent.polarity == "negative"
            and parent.positive_peak
            > config.mixed_sign_ratio * max(abs(parent.negative_peak), 1e-9)
        ) or (
            parent.polarity == "positive"
            and abs(parent.negative_peak)
            > config.mixed_sign_ratio * max(abs(parent.positive_peak), 1e-9)
        )
        # Bipolar rescue uses the merge's notion of bipolarity (peak balance),
        # not the stricter tunnel-protection ratio above: e.g. the Iron Box
        # parent carries +23.6/-38.7 (balance 0.61) -- bipolar by merge
        # standards (>= 0.40) but below the 0.80 tunnel ratio.
        pos_peak = max(float(parent.positive_peak), 0.0)
        neg_peak = max(abs(float(parent.negative_peak)), 0.0)
        bipolar_balance = (
            min(pos_peak, neg_peak) / max(pos_peak, neg_peak)
            if max(pos_peak, neg_peak) > 0
            else 0.0
        )
        strong_bipolar_signal = (
            abs(parent.anomaly_score) >= config.single_scan_min_anomaly_score
            and pos_peak >= config.bipolar_rescue_min_peak
            and neg_peak >= config.bipolar_rescue_min_peak
            and bipolar_balance >= config.bipolar_rescue_min_balance
        )
        if (
            (parent.evidence_score < config.parent_evidence_min and not strong_bipolar_signal)
            or ((not allow_single_scan) and parent.scan_count < 2)
            or parent.artifact_score >= config.artifact_max
            or parent.scale_class == "broad"
        ):
            fragment_counts[parent.id] = 1
            out.append(
                _clone_with_diagnostics(
                    parent,
                    next_id,
                    pos_field=pos_strength,
                    neg_field=neg_strength,
                    local_mask=local_mask,
                    min_distance=max(int(min_distance_px), 3),
                    depth_patch=depth_patch,
                )
            )
            next_id += 1
            continue
        if (
            allow_single_scan
            and parent.scan_count < 2
            and (
                abs(parent.anomaly_score) < config.single_scan_min_anomaly_score
                or parent.pattern_hypothesis in config.single_scan_exempt_patterns
            )
        ):
            fragment_counts[parent.id] = 1
            out.append(
                _clone_with_diagnostics(
                    parent,
                    next_id,
                    pos_field=pos_strength,
                    neg_field=neg_strength,
                    local_mask=local_mask,
                    min_distance=max(int(min_distance_px), 3),
                    depth_patch=depth_patch,
                )
            )
            next_id += 1
            continue
        # strong_opposite_sign was computed above (before the evidence gate);
        # reuse it here for the tunnel-protection checks.
        protect_strong_tunnel = (
            parent.pattern_hypothesis == "tunnel-like"
            and parent.line_support_score >= 0.80
            and parent.axial_signal_continuity_score >= 0.90
        )
        if (
            parent.scan_count >= 2
            and parent.pattern_hypothesis == "tunnel-like"
            and not strong_opposite_sign
        ):
            fragment_counts[parent.id] = 1
            out.append(
                _clone_with_diagnostics(
                    parent,
                    next_id,
                    pos_field=pos_strength,
                    neg_field=neg_strength,
                    local_mask=local_mask,
                    min_distance=max(int(min_distance_px), 3),
                    depth_patch=depth_patch,
                )
            )
            next_id += 1
            continue
        if (
            allow_single_scan
            and parent.scan_count < 2
            and (
                (protect_strong_tunnel and not strong_opposite_sign)
                or (
                    parent.polarity == "negative"
                    and parent.line_support_score >= 0.68
                    and parent.linearity_score >= 0.45
                    and protect_strong_tunnel
                    and not strong_opposite_sign
                )
            )
        ):
            fragment_counts[parent.id] = 1
            out.append(
                _clone_with_diagnostics(
                    parent,
                    next_id,
                    pos_field=pos_strength,
                    neg_field=neg_strength,
                    local_mask=local_mask,
                    min_distance=max(int(min_distance_px), 3),
                    depth_patch=depth_patch,
                )
            )
            next_id += 1
            continue
        # Only split on response channels that have substantial support.  This keeps
        # broad background variation from manufacturing seeds in a weak region.
        local_extent = max(
            parent.major_extent, parent.minor_extent, parent.width, parent.height, 1.0
        )
        if allow_single_scan and parent.scan_count < 2:
            # In one scan, scale the seed distance from raster resolution rather
            # than the full parent size. Otherwise a large fused blob can reject
            # legitimate close peaks before decomposition even starts.
            min_sep = max(int(min_distance_px), 3)
        else:
            min_sep = max(
                min_distance_px,
                int(round(local_extent / max(site_width, site_height, 1e-9) * resolution * 0.22)),
            )
        # v0.2.38: the lower seed-height threshold is intended for genuinely
        # fused multi-target responses. Preserve the v0.2.37 threshold for a
        # clearly bipolar parent so one metal/dipole response is not split more
        # aggressively and then mislocalized during fragment recombination.
        parent_bipolar_for_seeds = _parent_is_bipolar(parent)
        parent_bipolar = parent_bipolar_for_seeds
        seed_rel_height = 0.48 if parent_bipolar_for_seeds else config.seed_rel_height
        # v0.2.49 experimental: close multi-target bipolar responses can place
        # their two signed lobes closer than the generic 3 px separation. For
        # multi-scan parents, allow a 2 px signed-lobe seed distance. The final
        # dipole merge guard decides whether those lobes remain a dipole.
        seed_min_distance = 2 if (parent_bipolar_for_seeds and parent.scan_count >= 2) else min_sep
        seed_pos_field = (
            p if (parent_bipolar_for_seeds and parent.scan_count >= 2) else pos_strength
        )
        seed_neg_field = (
            n if (parent_bipolar_for_seeds and parent.scan_count >= 2) else neg_strength
        )
        seeds_pos = _find_seeds(
            seed_pos_field,
            local_mask & (seed_pos_field > 0),
            min_distance=seed_min_distance,
            rel_height=seed_rel_height,
        )
        seeds_neg = _find_seeds(
            seed_neg_field,
            local_mask & (seed_neg_field > 0),
            min_distance=seed_min_distance,
            rel_height=seed_rel_height,
        )
        seeds = [(r, c, v, "positive") for r, c, v in seeds_pos] + [
            (r, c, v, "negative") for r, c, v in seeds_neg
        ]
        seeds.sort(key=lambda t: t[2], reverse=True)
        chosen: list[tuple[int, int, float, str]] = []
        patch_center = (s.shape[0] / 2.0, s.shape[1] / 2.0)
        peak_by_channel = {
            "positive": _finite_peak(pos_strength),
            "negative": _finite_peak(neg_strength),
        }
        for seed in seeds:
            # Seeds must remain reasonably close to the parent's registered center.
            if math.hypot(seed[0] - patch_center[0], seed[1] - patch_center[1]) > max(
                4.0, 0.95 * max(s.shape)
            ):
                continue
            if seed[2] < max(
                config.seed_floor, config.seed_min_ratio * peak_by_channel.get(seed[3], seed[2])
            ):
                continue
            if all(
                math.hypot(seed[0] - a, seed[1] - b) >= seed_min_distance for a, b, *_ in chosen
            ):
                chosen.append(seed)
            if len(chosen) >= max_seeds_per_parent:
                break

        # v0.2.46: depth-layer second pass. Run only when generic spatial seed
        # detection found fewer than two seeds. The dominant signed response must
        # have two balanced, spatially separated depth layers; bipolar/broad/
        # geology/tunnel responses remain excluded.
        parent_depth_assisted = False
        if (
            config.enable_depth_layer_deblending
            and len(chosen) < 2
            and depth_patch is not None
            and parent.polarity in ("positive", "negative")
            and not _parent_is_bipolar(parent)
            and parent.pattern_hypothesis not in ("geological-like", "tunnel-like")
            and parent.response_family not in ("broad-response", "dipolar-response")
            and parent.artifact_score < config.artifact_max
        ):
            dominant = pos_strength if parent.polarity == "positive" else neg_strength
            depth_seeds = _depth_layer_seed_pair(
                dominant,
                local_mask & (dominant > 0),
                depth_patch,
                min_depth_gap_m=0.75,
                min_cluster_weight=0.22,
                min_spatial_separation_px=max(3.0, 0.75 * max(int(min_sep), 3)),
            )
            if len(depth_seeds) == 2:
                chosen = [(int(r), int(c), float(v), parent.polarity) for r, c, v, _ in depth_seeds]
                parent_depth_assisted = True

        # A single broad/tiny peak is not a split candidate.
        if len(chosen) < 2:
            fragment_counts[parent.id] = 1
            cloned = replace(parent, id=next_id)
            cloned = _attach_undersegmentation_diagnostic(
                cloned,
                pos_field=pos_strength,
                neg_field=neg_strength,
                local_mask=local_mask,
                min_distance=max(int(min_sep), 3),
                depth_field=depth_patch,
            )
            next_id += 1
            out.append(cloned)
            continue

        # Assign supported response pixels to the nearest seed.  Distances are
        # weighted slightly toward the stronger local response to avoid razor-thin
        # splits in noisy overlap zones.
        coords = np.argwhere(local_mask)
        if len(coords) < 6:
            fragment_counts[parent.id] = 1
            cloned = replace(parent, id=next_id)
            cloned = _attach_undersegmentation_diagnostic(
                cloned,
                pos_field=pos_strength,
                neg_field=neg_strength,
                local_mask=local_mask,
                min_distance=max(int(min_sep), 3),
                depth_field=depth_patch,
            )
            next_id += 1
            out.append(cloned)
            continue
        seed_xy = np.array([[r, c] for r, c, _, _ in chosen], dtype=float)
        point_xy = coords.astype(float)
        dist2 = ((point_xy[:, None, :] - seed_xy[None, :, :]) ** 2).sum(axis=2)
        assignments = np.argmin(dist2, axis=1)
        survivors_before = len(out)
        for frag_i, (sr, sc, peak, polarity) in enumerate(chosen, 1):
            frag_coords = coords[assignments == (frag_i - 1)]
            # v0.2.65: preserve a two-cell fragment only when it has
            # cross-scan support and a strong consensus peak. One-cell
            # fragments and weak two-cell noise remain rejected.
            min_cells = int(config.min_fragment_cells)
            if (
                int(parent.scan_count) >= 2
                and len(frag_coords) == int(config.strong_multiscan_min_fragment_cells)
                and peak
                >= max(
                    3.0,
                    float(anomaly_threshold) * float(config.strong_multiscan_fragment_peak_ratio),
                )
            ):
                min_cells = int(config.strong_multiscan_min_fragment_cells)
            if len(frag_coords) < min_cells:
                continue
            mask = np.zeros_like(local_mask, dtype=bool)
            mask[frag_coords[:, 0], frag_coords[:, 1]] = True
            local_x_axis = x_axis[cs.start : cs.stop]
            local_y_axis = y_axis[rs.start : rs.stop]
            stats = _fragment_stats(
                mask, local_x_axis, local_y_axis, frag_coords[:, 0], frag_coords[:, 1]
            )
            # Use the selected polarity channel to localize a fragment. Voronoi
            # assignment by total support can pull an opposite-sign component
            # toward the shoulder of an overlapping response.
            channel_field = (
                (p if polarity == "positive" else n)
                if (parent_bipolar and parent.scan_count >= 2)
                else (pos_strength if polarity == "positive" else neg_strength)
            )
            channel_weights = channel_field[frag_coords[:, 0], frag_coords[:, 1]]
            if float(np.sum(channel_weights)) > 1e-9:
                center_row, center_col = np.average(frag_coords, axis=0, weights=channel_weights)
            else:
                center_row, center_col = np.average(
                    frag_coords,
                    axis=0,
                    weights=np.maximum(local_mask[frag_coords[:, 0], frag_coords[:, 1]], 1),
                )
            fx = float(local_x_axis[int(np.clip(round(center_col), 0, len(local_x_axis) - 1))])
            fy = float(local_y_axis[int(np.clip(round(center_row), 0, len(local_y_axis) - 1))])
            # A decomposition should not relocate a response component far outside
            # the parent response footprint. Clamp the fragment center around the
            # parent's center to reduce shoulder-driven localization drift.
            clamp_x = config.center_clamp_ratio * max(
                float(parent.width), float(parent.major_extent), 1.0
            )
            clamp_y = config.center_clamp_ratio * max(
                float(parent.height), float(parent.minor_extent), 1.0
            )
            fx = float(np.clip(fx, parent.x_center - clamp_x, parent.x_center + clamp_x))
            fy = float(np.clip(fy, parent.y_center - clamp_y, parent.y_center + clamp_y))
            # Fragment descriptors are recomputed from this fragment's own cells
            # (same formulas as analysis.shape). Inheriting the parent's whole-
            # object statistics here is what used to turn one iron dipole into
            # "metal + independent cavity".
            frag_desc = _fragment_full_descriptors(
                mask=mask,
                frag_rr=frag_coords[:, 0],
                frag_cc=frag_coords[:, 1],
                local_x_axis=local_x_axis,
                local_y_axis=local_y_axis,
                field_shape=(support.shape[0], support.shape[1]),
                signed_patch=signed_patch,
                stats=stats,
                total_cells=int(np.count_nonzero(np.isfinite(support))),
                row_offset=int(rs.start),
                col_offset=int(cs.start),
                depth_patch=depth_patch,
                persist_patch=persist_patch,
                artifact_patch=artifact_patch,
                signal_patch=signal_patch,
                anomaly_threshold=float(anomaly_threshold),
            )
            frag_artifact = float(frag_desc.get("artifact_score", parent.artifact_score))
            # Fragment evidence is inherited, then slightly discounted for the fact
            # that this is a decomposition hypothesis rather than an independently
            # detected connected component.
            evidence = float(
                np.clip(parent.evidence_score * (0.92 if len(chosen) > 2 else 0.96), 0.0, 1.0)
            )
            fragment = replace(
                parent,
                id=next_id,
                x_center=fx,
                y_center=fy,
                n_points=int(stats["n_points"]),
                area_cells=int(stats["area_cells"]),
                width=max(stats["width"], parent.width / max(len(chosen), 1) * 0.55),
                height=max(stats["height"], parent.height / max(len(chosen), 1) * 0.55),
                aspect_ratio=float(stats["aspect_ratio"]),
                orientation_deg=(
                    float(frag_desc["orientation_deg"])
                    if math.isfinite(float(frag_desc["orientation_deg"]))
                    else float(parent.orientation_deg)
                ),
                shape_class=str(frag_desc["shape_class"]),
                polarity=polarity,
                peak_signal=float(frag_desc.get("peak_signal", parent.peak_signal)),
                mean_signal=float(frag_desc.get("mean_signal", parent.mean_signal)),
                anomaly_score=float(frag_desc["anomaly_score"]),
                positive_peak=float(frag_desc["positive_peak"]),
                negative_peak=float(frag_desc["negative_peak"]),
                signed_anomaly_mean=float(frag_desc["signed_anomaly_mean"]),
                anomaly_density=float(frag_desc["anomaly_density"]),
                compactness=float(stats["compactness"]),
                continuity_score=float(frag_desc["continuity_score"]),
                artifact_score=frag_artifact,
                multiscale_persistence=float(
                    frag_desc.get("multiscale_persistence", parent.multiscale_persistence)
                ),
                broadness_score=float(frag_desc["broadness_score"]),
                regional_support_score=(
                    float(frag_desc["broadness_score"]) if parent.scale_class == "broad" else 0.0
                ),
                boundary_contact_ratio=float(frag_desc["boundary_contact_ratio"]),
                solidity=float(frag_desc["solidity"]),
                geometry_quality=float(frag_desc["geometry_quality"]),
                line_support_score=float(frag_desc["line_support_score"]),
                line_support_orientation_deg=float(frag_desc["line_support_orientation_deg"]),
                axial_signal_continuity_score=float(frag_desc["axial_signal_continuity_score"]),
                centroid_weighted_x=float(fx),
                centroid_weighted_y=float(fy),
                depth_mean=float(frag_desc.get("depth_mean", parent.depth_mean)),
                depth_std=float(frag_desc.get("depth_std", parent.depth_std)),
                depth_min=float(frag_desc.get("depth_min", parent.depth_min)),
                depth_max=float(frag_desc.get("depth_max", parent.depth_max)),
                depth_range=float(frag_desc.get("depth_range", parent.depth_range)),
                depth_estimate=float(frag_desc.get("depth_estimate", parent.depth_estimate)),
                depth_estimate_std=float(
                    frag_desc.get("depth_estimate_std", parent.depth_estimate_std)
                ),
                depth_relative_dispersion=float(
                    frag_desc.get("depth_relative_dispersion", parent.depth_relative_dispersion)
                ),
                depth_stability_score=float(
                    frag_desc.get("depth_stability_score", parent.depth_stability_score)
                ),
                depth_valid_fraction=float(
                    frag_desc.get("depth_valid_fraction", parent.depth_valid_fraction)
                ),
                major_extent=max(
                    stats["major_extent"], parent.major_extent / max(len(chosen), 1) * 0.55
                ),
                minor_extent=max(
                    stats["minor_extent"], parent.minor_extent / max(len(chosen), 1) * 0.55
                ),
                elongation_ratio=float(stats["elongation_ratio"]),
                linearity_score=float(
                    np.clip(
                        1.0 - stats["minor_extent"] / max(stats["major_extent"], 1e-9), 0.0, 1.0
                    )
                ),
                evidence_score=round(evidence, 3),
                confidence=round(min(max(evidence, 0.1), 0.95), 2),
                notes=(parent.notes + "; " if parent.notes else "")
                + f"separated from parent candidate {parent.id} via {('depth-layer ' if parent_depth_assisted else '')}multiscan consensus peak {frag_i}/{len(chosen)}; decomposition hypothesis, not an independently validated object.",
                separation_status=(
                    "decomposed-depth-layer" if parent_depth_assisted else "decomposed-consensus"
                ),
                separation_parent_id=parent.id,
                separation_quality=float(
                    np.clip(
                        0.5
                        * peak
                        / max(
                            _finite_peak(pos_strength if polarity == "positive" else neg_strength),
                            1e-9,
                        )
                        + 0.5
                        * min(
                            1.0,
                            (math.hypot(sr - chosen[0][0], sc - chosen[0][1]) / max(min_sep, 1)),
                        ),
                        0.0,
                        1.0,
                    )
                ),
                separation_fragment_count=len(chosen),
                multi_scan_status="decomposed-consensus",
                scan_count=parent.scan_count,
                detection_rate=parent.detection_rate,
                contributing_scans=list(parent.contributing_scans),
            )
            # Reinterpret the fragment only at the pattern-vocabulary level.
            # Cross-scan evidence remains inherited; this avoids pretending the
            # decomposition itself is an independently validated detection.
            # Dipole guard: a negative lobe split from a bipolar (pos+neg) parent
            # belongs to one signed response; the final merge labels the response
            # morphology explicitly without inferring material identity.
            parent_bipolar = _parent_is_bipolar(parent)
            if (
                polarity == "positive"
                and stats["aspect_ratio"] < 2.8
                and stats["compactness"] >= 0.45
                and frag_artifact < 0.55
            ):
                fragment.pattern_hypothesis = "metallic-like"
            elif (
                polarity == "negative"
                and parent.pattern_hypothesis == "tunnel-like"
                and not parent_bipolar
            ):
                fragment.pattern_hypothesis = "tunnel-like"
            elif polarity == "negative" and parent_bipolar:
                fragment.pattern_hypothesis = "metallic-like"
                fragment.notes += "; bipolar-dipole parent: negative lobe kept as a dipole companion, not an independent cavity/void."
            elif polarity == "negative":
                fragment.pattern_hypothesis = "cavity-like"
            else:
                fragment.pattern_hypothesis = parent.pattern_hypothesis
            if fragment_cells is not None:
                # Record this fragment's cells in *field* coordinates so a later
                # stage can reason about a set that spans several fragments. The
                # fragment's own compactness/solidity were computed from the local
                # window above and are unaffected by this; the cells are recorded
                # because they are destroyed here and are the only way to compute
                # a union over a merged pair (see diagnostics.dipole).
                fragment_cells[next_id] = (
                    np.asarray(frag_coords[:, 0], dtype=int) + int(rs.start),
                    np.asarray(frag_coords[:, 1], dtype=int) + int(cs.start),
                )
            out.append(fragment)
            next_id += 1
        if len(out) == survivors_before:
            # Every fragment failed the minimum-size gate: retain the parent
            # rather than silently dropping the candidate from the site
            # result set. Mark it explicitly as unresolved.
            fragment_counts[parent.id] = 1
            retained = replace(
                parent,
                id=next_id,
                separation_status="unresolved-undersegmented",
                separation_fragment_count=len(chosen),
                notes=(parent.notes + "; " if parent.notes else "")
                + f"separation unresolved: {len(chosen)} fragments rejected by minimum-size gate; parent retained",
            )
            retained = _attach_undersegmentation_diagnostic(
                retained,
                pos_field=pos_strength,
                neg_field=neg_strength,
                local_mask=local_mask,
                min_distance=max(int(min_sep), 3),
                depth_field=depth_patch,
            )
            next_id += 1
            out.append(retained)
        else:
            fragment_counts[parent.id] = len(out) - survivors_before
    return out, fragment_counts

"""Reproduction fixture for the out-of-bounds edge clipping in site/verdicts.py.

STATUS: fixture only. The defect is confirmed reachable but NOT fixed yet (see
the audit follow-up). This module deliberately does **not** pin the current
clipped output, because that is the behaviour under dispute. It pins the
*precondition* instead -- that the aligned branch can map a candidate outside
the reference field -- using the alignment primitives directly, so it stays
green whether or not the clipping is later changed.

Why the clipping exists
-----------------------
``_candidate_observation_point`` has two branches:

* **branch A** (``alignment is None``, the reference scan itself) normalizes by
  the *observation's own* extent. A candidate's ``x_center`` comes from that same
  grid, so ``u`` is in [0, 1] by construction and ``np.clip`` can never bite.
* **branch B** (``alignment`` exists, i.e. a non-reference scan) maps the point
  into the reference frame and then normalizes by the *reference* extent. The
  shift is capped at ``max_shift`` cells on a ``resolution``-cell fusion grid
  (6/40 = 15% of the field), so a candidate sitting near an edge of its own
  field plus an outward shift can land outside the reference field, where
  ``np.clip(u, 0, 1)`` silently pins it to the edge.

Measured reachability (deterministic, seed-fixed):

===================================  =========  =======  =======  ==========
non-reference x offset (cells)        raw_u max  clipped  fused    candidates
===================================  =========  =======  =======  ==========
-3.0, -1.0, +1.0                     0.99        no       1-3     1-3
+3.0                                 1.0061      yes      1-6     1-6
+6.0                                 1.0574      yes      1-2     1-2
===================================  =========  =======  =======  ==========

So a small forward offset between scans is enough. Distinct candidates pinned
to ``u == 1.0`` then share an edge coordinate, which is the mechanism behind
the audit's "phantom edge clusters" claim.

Outcome: reachable, but the clipping has **no effect on the output**, so the
defect is closed unfixed
--------------------------------------------------------
The audit recommended excluding out-of-bounds candidates instead of clipping
them. Measured, that recommendation is backwards, so this fixture is kept as a
reachability record and the code is left alone.

Two independent measurements:

1. Clipping is a no-op on the result. Re-running the site pipeline with the
   clip bypassed (raw fractions passed through) produced **byte-identical**
   fused output in every configuration tested -- offsets +3.0, +4.0, +5.0 and
   +6.0, against six target placements including both field edges::

       off=+4 tx= 2  fused clip=2 noclip=2  SAME
       off=+5 tx=30  fused clip=4 noclip=4  SAME
       off=+6 tx=30  fused clip=2 noclip=2  SAME   (and 15 more)

2. The displacement is bounded below the cluster threshold. The site pipeline
   calls ``align_grids`` with the default ``max_shift=6`` on a 40-cell fusion
   grid (``fusion_resolution=40``), so the worst case is ``6/40 = 0.15`` in
   normalized units; measured worst overshoot was **0.0574**. Clustering uses
   ``distance_threshold=0.06``. Clipping therefore moves a point by strictly
   less than the distance at which two candidates would be merged, so it cannot
   merge distinct clusters.

Excluding instead of clipping would discard a candidate whose scan genuinely
does overlap the reference field -- converting a sub-threshold coordinate shift
into a lost detection. If this is ever revisited, the right guard is a
diagnostic warning when the raw fraction leaves [0, 1], not a silent pin and not
a drop.

Run ``python -m pytest tests/unit/test_verdicts_edge_clipping_fixture.py -q``.
"""

from __future__ import annotations

# The site package re-exports a function named ``analyze_site``, which shadows
# the submodule of the same name. ``import groundscan.site.analyze_site as X``
# therefore binds the *function*; the module must come from sys.modules.
import sys as _sys
import tempfile

import numpy as np

import groundscan.site.verdicts as V
from groundscan import ScanData, ScanMetadata
from groundscan.api import analyze_site

_SITE_MODULE = _sys.modules["groundscan.site.analyze_site"]

_OFFSET_TRIGGER = 3.0  # smallest forward offset that pushes a point out of bounds


def _scan(label: str, seed: int, *, offset: float = 0.0, n: int = 60) -> tuple[str, ScanData]:
    """A 60x60 scan with one target, optionally offset along x by whole cells."""
    rng = np.random.default_rng(seed)
    x = np.repeat(np.arange(n, dtype=float), n) + offset
    y = np.tile(np.arange(n, dtype=float), n)
    signal = rng.normal(0.0, 1.0, n * n)
    cy = n // 2
    signal[(y >= cy - 3) & (y <= cy + 3) & (x >= cy - 3) & (x <= cy + 3)] += 8.0
    return (
        label,
        ScanData(
            x=x,
            y=y,
            z=np.ones(n * n),
            signal=signal,
            metadata=ScanMetadata(field_length_m=float(n - 1), field_width_m=float(n - 1)),
        ),
    )


def _raw_reference_fractions(scans, reference_label: str) -> list[tuple[float, float, str]]:
    """Pre-clip (u, v, label) for every aligned observation point.

    Computed from the alignment primitives, deliberately bypassing the helper
    that clips, so the result does not change when the clipping is fixed.
    """
    captured: list[tuple[float, float, str]] = []
    real = V._candidate_observation_point

    def spy(candidate, obs, reference, alignment, resolution):
        if alignment is not None:
            row, col = V.map_point_to_aligned(
                candidate.x_center,
                candidate.y_center,
                obs.grid.x_centers,
                obs.grid.y_centers,
                alignment,
            )
            x, y = V._reference_xy_from_aligned_point(row, col, reference.grid, resolution)
            rx0, rx1, ry0, ry1 = V._scan_extent(reference.grid)
            captured.append((
                (x - rx0) / max(rx1 - rx0, 1e-9),
                (y - ry0) / max(ry1 - ry0, 1e-9),
                obs.label,
            ))
        return real(candidate, obs, reference, alignment, resolution)

    _SITE_MODULE._candidate_observation_point = spy
    try:
        with tempfile.TemporaryDirectory(prefix="gs-edge-") as tmp:
            analyze_site(scans, out_dir=tmp, reference_label=reference_label)
    finally:
        _SITE_MODULE._candidate_observation_point = real
    return captured


def test_offset_scans_can_map_outside_the_reference_field():
    """The aligned branch can produce a point outside [0, 1] -- the precondition.

    Asserted from the raw mapping, not from the clipped helper, so this stays
    true after the clipping is changed. The offsets that trigger it are
    recorded in the module docstring.
    """
    scans = [
        _scan("a", 1, offset=0.0),
        _scan("b", 2, offset=_OFFSET_TRIGGER),
        _scan("c", 3, offset=_OFFSET_TRIGGER),
    ]
    fractions = _raw_reference_fractions(scans, "a")

    assert fractions, "no aligned observation points were produced"
    outside = [
        (u, v, label) for u, v, label in fractions if not (0.0 <= u <= 1.0) or not (0.0 <= v <= 1.0)
    ]
    assert outside, (
        f"expected at least one point outside the reference field at offset "
        f"{_OFFSET_TRIGGER}, got {[(round(u, 4), round(v, 4)) for u, v, _ in fractions]}"
    )


def test_coincident_scans_stay_inside_the_reference_field():
    """The control: no offset, nothing escapes. Guards against a false fixture."""
    scans = [_scan("a", 1), _scan("b", 2), _scan("c", 3)]
    fractions = _raw_reference_fractions(scans, "a")

    assert fractions
    for u, v, label in fractions:
        assert -1e-9 <= u <= 1.0 + 1e-9, f"{label} escaped at u={u}"
        assert -1e-9 <= v <= 1.0 + 1e-9, f"{label} escaped at v={v}"


def test_branch_a_cannot_escape_by_construction():
    """The reference scan's own points are normalized by its own extent.

    This is why the defect is only reachable through the *aligned* branch, and
    it documents why the fixture has to use a non-reference scan.
    """
    scans = [_scan("a", 1, offset=_OFFSET_TRIGGER)]
    reference = scans[0][1]
    from groundscan.core.grid import reconstruct_grid

    grid = reconstruct_grid(reference)
    x0, x1, y0, y1 = V._scan_extent(grid)
    for candidate_x in (x0, x1, (x0 + x1) / 2.0):
        u = (candidate_x - x0) / max(x1 - x0, 1e-9)
        assert 0.0 <= u <= 1.0


def test_clipping_does_not_change_the_fused_result():
    """Why the defect is closed unfixed: clipping is a no-op on the output.

    Bypasses the clip and passes the raw fractions through.     If this ever
    fails, that is the signal to revisit the decision -- for reference, the
    no-op property still held at offsets up to +20 cells in ad-hoc probing and
    first broke at +30, where the aligner can no longer recover the shift and
    the residual displacement exceeds ``distance_threshold``.
    """
    real = V._candidate_observation_point
    bypass: dict[str, bool] = {"on": False}

    def unclipped(candidate, obs, reference, alignment, resolution):
        if alignment is not None and bypass["on"]:
            row, col = V.map_point_to_aligned(
                candidate.x_center,
                candidate.y_center,
                obs.grid.x_centers,
                obs.grid.y_centers,
                alignment,
            )
            x, y = V._reference_xy_from_aligned_point(row, col, reference.grid, resolution)
            rx0, rx1, ry0, ry1 = V._scan_extent(reference.grid)
            return (
                (x - rx0) / max(rx1 - rx0, 1e-9),
                (y - ry0) / max(ry1 - ry0, 1e-9),
                max(*V._normalized_dims(candidate, obs.grid)),
            )
        return real(candidate, obs, reference, alignment, resolution)

    def fused_signature() -> tuple:
        with tempfile.TemporaryDirectory(prefix="gs-edge-cmp-") as tmp:
            result = analyze_site(scans, out_dir=tmp, reference_label="a")
        return tuple(
            sorted(
                (
                    round(float(c.x_center), 3),
                    round(float(c.y_center), 3),
                    round(float(c.evidence_score), 3),
                    int(c.scan_count),
                )
                for c in result.fused_candidates
            )
        )

    scans = [
        _scan("a", 1, offset=0.0),
        _scan("b", 2, offset=6.0),
        _scan("c", 3, offset=6.0),
    ]

    _SITE_MODULE._candidate_observation_point = unclipped
    try:
        bypass["on"] = False
        clipped = fused_signature()
        bypass["on"] = True
        unclipped_result = fused_signature()
    finally:
        bypass["on"] = False
        _SITE_MODULE._candidate_observation_point = real

    assert clipped, "the fixture produced no fused candidates, so it proves nothing"
    assert unclipped_result == clipped, (
        "clipping now changes the fused result; the no-op argument for closing "
        "this unfixed no longer holds and the decision must be revisited:\n"
        f"  clipped  = {clipped}\n"
        f"  unclipped= {unclipped_result}"
    )

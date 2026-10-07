"""Controlled cross-resolution cases: known physical geometry, five families.

Each case is a *construction* whose mathematical structure is known before any
detector runs, so the expectation can be derived independently:

===== ==========================  ==============================================
Case  Family                      Construction and its known structure
===== ==========================  ==============================================
A     ``unimodal``                One isotropic Gaussian. The superlevel set
                                  at any threshold below the peak is
                                  contractible, so there is exactly one
                                  connected anomaly region *in principle*.
B     ``separated``               Two Gaussians separated by many sigma. The
                                  superlevel set is disconnected, and the gap
                                  exceeds any plausible d_res, so two response
                                  regions are the construction's own statement.
C     ``close_unresolved``        Two Gaussians separated by LESS than
                                  ``2 * sigma``. Equal Gaussians bifurcate at
                                  ``2 * sigma``; below it the field is
                                  strictly unimodal, so the sub-structure is
                                  unrecoverable at any sampling density.
D     ``multi_seed``              One elongated response. The *continuous*
                                  field is unimodal, but a long thin profile
                                  sampled on a lattice has many discrete
                                  local maxima. Seed count is therefore a
                                  property of the sampling, and the design
                                  forbids asserting it stable.
E     ``anisotropic``             As Case A, sampled with ``dy != dx`` at
                                  every rung, to test whether a metric that
                                  should be dimensionless depends on the
                                  sampling aspect ratio.
===== ==========================  ==============================================

Every case is a physical *scene*. ``scene.response_count`` counts constructed
responses in the forward model -- it is not, and may never be presented as, a
count of buried objects (contract K3).
"""

from __future__ import annotations

from .cross_resolution import (
    PhysicalResponse,
    PhysicalScene,
    Resolution,
    anisotropic_ladder,
    isotropic_ladder,
)

#: Shared extent so the five cases differ only in response placement.
EXTENT_W = 24.0
EXTENT_H = 24.0

#: Coarse -> fine. A factor of two per step, the customary survey progression.
PITCHES: tuple[float, ...] = (1.0, 0.5, 0.25)

#: Per-case noise seed base. Distinct so no two cases share a noise draw.
SEED_BASE: dict[str, int] = {
    "case_a_unimodal": 410_001,
    "case_b_separated": 420_001,
    "case_c_close_unresolved": 430_001,
    "case_d_multi_seed": 440_001,
    "case_e_anisotropic": 450_001,
}


def case_a_unimodal() -> PhysicalScene:
    """One clearly unimodal response (design §12.2 Case A).

    sigma = 1.2 m against a 1.0/0.5/0.25 m ladder, so the peak is sampled by
    1.2 / 0.25 = 4.8 sigma-cells even at the finest rung: the response is
    resolved at every rung, and this is the case a too-aggressive fix breaks.
    """
    return PhysicalScene(
        name="case_a_unimodal",
        width_m=EXTENT_W,
        height_m=EXTENT_H,
        case_family="unimodal",
        noise_sigma=0.5,
        responses=(
            PhysicalResponse(
                label="r0", cx=12.0, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=18.0
            ),
        ),
    )


def case_b_separated() -> PhysicalScene:
    """Two clearly separated responses (design §12.2 Case B).

    8 m apart at sigma = 1.2 m, i.e. 6.7 sigma. The 50 % contours (radius
    1.66 m) are non-overlapping by ~4.7 m, so the anti-test for "one response ->
    one finding" over-correction is genuinely separated.
    """
    return PhysicalScene(
        name="case_b_separated",
        width_m=EXTENT_W,
        height_m=EXTENT_H,
        case_family="separated",
        noise_sigma=0.5,
        responses=(
            PhysicalResponse(label="r0", cx=8.0, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=18.0),
            PhysicalResponse(
                label="r1", cx=16.0, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=16.0
            ),
        ),
    )


def case_c_close_unresolved() -> PhysicalScene:
    """Two responses unresolved at the given sampling (design §12.2 Case C).

    Separation 1.5 m against sigma = 1.2 m. Since 1.5 < 2 * 1.2 = 2.4, the
    superposed continuous field is strictly unimodal: there is one maximum, and
    the second response is not recoverable at *any* pitch. The oracle for this
    case comes from the forward model, not from the detector.
    """
    return PhysicalScene(
        name="case_c_close_unresolved",
        width_m=EXTENT_W,
        height_m=EXTENT_H,
        case_family="close_unresolved",
        noise_sigma=0.5,
        responses=(
            PhysicalResponse(
                label="r0", cx=11.25, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=18.0
            ),
            PhysicalResponse(
                label="r1", cx=12.75, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=16.0
            ),
        ),
    )


def case_d_multi_seed() -> PhysicalScene:
    """One response producing many decomposition seeds (design §12.2 Case D).

    An elongated response rotated 30 degrees. The *continuous* field is
    unimodal (independent probe: 1 maximum), but the field's own aspect ratio
    against an axis-aligned lattice is what produces the discretisation
    staircase, and that staircase carries several discrete local maxima.

    This is the case that must never assert a stable seed count. What the
    measurement actually shows -- see :func:`aspect_sweep` -- is more precise
    than "seeds vary with resolution": for this fixed field the count is
    *invariant* under isotropic re-sampling and varies with lattice aspect ratio.
    The count is a property of the sampling geometry, not of the field and not
    of pitch alone.
    """
    return PhysicalScene(
        name="case_d_multi_seed",
        width_m=EXTENT_W,
        height_m=EXTENT_H,
        case_family="multi_seed",
        noise_sigma=0.5,
        responses=(
            PhysicalResponse(
                label="r0",
                cx=12.0,
                cy=12.0,
                sigma_x=2.4,
                sigma_y=0.45,
                amplitude=18.0,
                orientation_deg=30.0,
            ),
        ),
    )


#: Lattice aspect ratios swept for Case D at fixed dx (see ``aspect_sweep``).
ASPECT_RATIOS: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)

#: dx held fixed while ASPECT_RATIOS varies, so the sweep isolates anisotropy.
ASPECT_SWEEP_DX = 0.5


def case_e_anisotropic() -> PhysicalScene:
    """Anisotropic sampling, dx != dy (design §12.3).

    Same physical scene as Case A, but the ladder is sampled with dy = 2 dx at
    every rung, so a metric that ought to be dimensionless can be checked for a
    dependence on the sampling aspect ratio.
    """
    return PhysicalScene(
        name="case_e_anisotropic",
        width_m=EXTENT_W,
        height_m=EXTENT_H,
        case_family="anisotropic",
        noise_sigma=0.5,
        responses=(
            PhysicalResponse(
                label="r0", cx=12.0, cy=12.0, sigma_x=1.2, sigma_y=1.2, amplitude=18.0
            ),
        ),
    )


CASE_BUILDERS = (
    case_a_unimodal,
    case_b_separated,
    case_c_close_unresolved,
    case_d_multi_seed,
    case_e_anisotropic,
)


def cross_resolution_cases() -> list[PhysicalScene]:
    """The five controlled families, in case order."""
    return [builder() for builder in CASE_BUILDERS]


def ladder_for(scene: PhysicalScene) -> tuple[Resolution, ...]:
    """coarse -> medium -> fine ladder appropriate to *scene*'s family."""
    if scene.case_family == "anisotropic":
        return anisotropic_ladder(scene.width_m, scene.height_m, PITCHES, dy_ratio=2.0)
    return isotropic_ladder(scene.width_m, scene.height_m, PITCHES)


def seed_for(scene: PhysicalScene, resolution: Resolution, rung: int) -> int:
    """Independent noise seed per (case, rung).

    Two lattices cannot share a noise sample, so independence is the only honest
    option -- and it is precisely why no relation downstream may be exact.
    """
    return SEED_BASE[scene.name] + 1000 * rung


#: Independent noise draws per rung for the seed-ensemble characterisation.
#: Six is the smallest number that can expose a draw-to-draw swing at all; a
#: single draw is not a characterisation.
ENSEMBLE_DRAWS: int = 6


def ensemble_seeds(scene: PhysicalScene, resolution: Resolution) -> tuple[int, ...]:
    """Independent noise seeds for one rung of one case."""
    base = SEED_BASE[scene.name] * 10 + int(round(resolution.dx * 1000)) % 9973
    return tuple(base + 7919 * k for k in range(ENSEMBLE_DRAWS))


__all__ = [
    "ASPECT_RATIOS",
    "ASPECT_SWEEP_DX",
    "CASE_BUILDERS",
    "ENSEMBLE_DRAWS",
    "EXTENT_H",
    "EXTENT_W",
    "PITCHES",
    "SEED_BASE",
    "case_a_unimodal",
    "case_b_separated",
    "case_c_close_unresolved",
    "case_d_multi_seed",
    "case_e_anisotropic",
    "cross_resolution_cases",
    "ensemble_seeds",
    "ladder_for",
    "seed_for",
]

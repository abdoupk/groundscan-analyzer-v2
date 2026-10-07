"""Phase A -- the calibration datasets, and the independent oracles they need.

Four categories, kept strictly apart because they license different kinds of
conclusion:

``analytical``
    A lattice cell set, or a continuous field, whose truth is a closed form or
    an exact rational. Shapes here are defined by their *cells*, not by an
    image, so "which cells are occupied" is a fact and not a rendering choice.

``perturbation``
    A known base response plus a controlled, single-factor change: additive
    noise, amplitude, translation, anisotropy, raster density, contamination or
    polarity. One factor per sample, so any measured difference is attributable.

``vendor``
    The nine ``scans/vendor_demo`` CSVs. Behavioural and regression reference
    only. A vendor annotation records what a vendor *said*; it is not a physical
    measurement and is never used to select a number.

``field``
    **Unavailable.** See :func:`field_evidence_availability`. The category exists
    so the absence is a recorded, queryable fact rather than a silence that
    reads as "not applicable".

Provenance is attached to every sample, not to a dataset as a whole, because the
provenance question that matters is per-sample: a shape perturbed ten times is
ten samples, and if one perturbation introduced a bug the other nine are still
valid evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from ...core.grid import Grid2D
from ...core.shape import _classify_shape, _shape_metrics

CATEGORY_ANALYTICAL = "analytical"
CATEGORY_PERTURBATION = "perturbation"
CATEGORY_VENDOR = "vendor"
CATEGORY_FIELD = "field"

CATEGORIES: tuple[str, ...] = (
    CATEGORY_ANALYTICAL,
    CATEGORY_PERTURBATION,
    CATEGORY_VENDOR,
    CATEGORY_FIELD,
)

#: A cell is an ``(row, col)`` lattice index pair. Row/col rather than x/y
#: because the raster's two axes are not interchangeable: ``local_mask`` is
#: indexed ``[row, col]`` and a transposed shape set is a different component.
Cell = tuple[int, int]


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """Where one calibration sample came from, and what may be concluded from it.

    ``independent_of_pipeline`` is the load-bearing field. A sample whose truth
    came out of the production code cannot be used to justify a production
    value; it can only describe behaviour. ``ground_truth`` states the *kind* of
    truth available, which is a strict ordering:

    ``exact``
        a closed form or exact rational arithmetic
    ``analytic``
        derived from the construction by a formula written out here
    ``behavioural``
        whatever the code under test does, with no external truth
    ``unavailable``
        nothing independent exists
    """

    category: str
    construction: str
    truth_kind: str
    independent_of_pipeline: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "construction": self.construction,
            "truth_kind": self.truth_kind,
            "independent_of_pipeline": self.independent_of_pipeline,
            "detail": self.detail,
        }


TRUTH_EXACT = "exact"
TRUTH_ANALYTIC = "analytic"
TRUTH_BEHAVIOURAL = "behavioural"
TRUTH_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ShapeSample:
    """One analytic cell set and the exact quantities known about it.

    ``cells`` is the *shape truth*: which cells are occupied. ``perimeter_edges``
    and ``solidity_exact`` are computed from it by the independent oracles below,
    never by production code.
    """

    sample_id: str
    shape_family: str
    cells: tuple[Cell, ...]
    provenance: Provenance
    description: str = ""

    @property
    def n_cells(self) -> int:
        return len(self.cells)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "shape_family": self.shape_family,
            "n_cells": self.n_cells,
            "perimeter_edges": exposed_edge_perimeter(self.cells),
            "compactness_exact": exact_compactness(self.cells),
            "solidity_exact": float(exact_solidity_fraction(self.cells)),
            "provenance": self.provenance.to_dict(),
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Independent oracles (no production code is involved)
# ---------------------------------------------------------------------------


def cellset(cells: Iterable[Cell]) -> tuple[Cell, ...]:
    """Canonical form: a de-duplicated tuple in ``(row, col)`` order."""
    return tuple(sorted({(int(r), int(c)) for r, c in cells}))


def face_adjacency_count(cells: Sequence[Cell]) -> int:
    """Number of unordered cell pairs sharing an edge. Pure lattice counting.

    This is 4-adjacency and only 4-adjacency. Two cells that touch at a corner
    share no edge, so a diagonal run has *no* face adjacency at all -- which is
    the correct physical statement and the reason the exposed-edge perimeter
    below is a genuine boundary length rather than a pixel-count heuristic.
    """
    occupied = set(cells)
    count = 0
    for row, col in occupied:
        if (row + 1, col) in occupied:
            count += 1
        if (row, col + 1) in occupied:
            count += 1
    return count


def exposed_edge_perimeter(cells: Sequence[Cell]) -> int:
    """Length of the exposed cell-edge boundary, in cell-edge units.

    ``P = 4N - 2 * A4``: every cell contributes four edges, and every shared
    edge removes two of them. This is exact for a union of unit squares, counts
    hole boundaries as exposed (they are -- a hole is exposed boundary), and
    ignores corner-touching contacts entirely.

    It is the *physical* perimeter in the sense the isoperimetric quotient needs:
    it is a length, it scales with the shape, and for a ``k x k`` block it is
    exactly ``4k`` for every ``k``.
    """
    n = len(cells)
    if n == 0:
        return 0
    return int(4 * n - 2 * face_adjacency_count(cells))


def exact_compactness(cells: Sequence[Cell]) -> float:
    """Isoperimetric quotient ``4*pi*A / P^2`` on the exposed-edge perimeter.

    Independent of the production estimator in ``_util.digital_compactness``,
    which approximates the perimeter by an erosion-boundary *cell count*. The
    two agree in the large-N limit and part company below it; the shape matrix in
    :mod:`.geometry` measures exactly how far, because that gap is the whole
    question for a compactness band.
    """
    n = len(cells)
    perimeter = exposed_edge_perimeter(cells)
    if n == 0 or perimeter == 0:
        return 0.0
    return float(4.0 * math.pi * n / (perimeter * perimeter))


def exact_solidity_fraction(cells: Sequence[Cell]):
    """Exact rational solidity, via the Stage-2 oracle.

    Delegates to ``validation.solidity_reference``, which traces the cell-union
    boundary in exact integer half-cell coordinates and evaluates the shoelace
    as a ``Fraction``. It shares no code with ``core.shape._convex_hull_solidity``
    (which is a centre hull plus a Minkowski identity) and no code with the
    retired formula, so agreement between the two is real evidence.
    """
    from ..solidity_reference import exact_solidity

    return exact_solidity(cells)


# ---------------------------------------------------------------------------
# Analytic shape catalogue
# ---------------------------------------------------------------------------


def rect(width: int, height: int, *, origin: tuple[int, int] = (0, 0)) -> tuple[Cell, ...]:
    r0, c0 = origin
    return cellset((r0 + r, c0 + c) for r in range(height) for c in range(width))


def square(side: int) -> tuple[Cell, ...]:
    return rect(side, side)


def line(length: int) -> tuple[Cell, ...]:
    return rect(length, 1)


def cross(arm: int, thickness: int = 1) -> tuple[Cell, ...]:
    """A plus sign: two bars of *arm* cells each side of the centre."""
    total = 2 * arm + thickness
    offset = (total - thickness) // 2
    return cellset(
        [cell for cell in rect(total, thickness, origin=(0, offset))]
        + [cell for cell in rect(thickness, total, origin=(offset, 0))]
    )


def l_shape(arm: int, thickness: int = 1) -> tuple[Cell, ...]:
    return cellset(
        [cell for cell in rect(arm, thickness, origin=(0, 0))]
        + [cell for cell in rect(thickness, arm, origin=(arm - thickness, 0))]
    )


def t_shape(arm: int, thickness: int = 1) -> tuple[Cell, ...]:
    stem = rect(thickness, arm, origin=(0, arm // 2))
    top = rect(2 * arm + thickness, thickness, origin=(0, 0))
    return cellset(list(stem) + list(top))


def u_shape(arm: int, thickness: int = 1) -> tuple[Cell, ...]:
    left = rect(arm, thickness, origin=(0, 0))
    right = rect(arm, thickness, origin=(0, 2 * arm - thickness))
    base = rect(2 * arm, thickness, origin=(arm - thickness, 0))
    return cellset(list(left) + list(right) + list(base))


def hollow_square(side: int, thickness: int = 1) -> tuple[Cell, ...]:
    """A ring. The hole's edges are exposed, and the oracle counts them."""
    return cellset(
        cell
        for cell in square(side)
        if min(cell[0], cell[1], side - 1 - cell[0], side - 1 - cell[1]) < thickness
    )


def disc(radius: int) -> tuple[Cell, ...]:
    cells = []
    r = int(radius)
    for row in range(-r, r + 1):
        for col in range(-r, r + 1):
            if row * row + col * col <= r * r:
                cells.append((row + r, col + r))
    return cellset(cells)


def ellipse(radius_a: int, radius_b: int) -> tuple[Cell, ...]:
    cells = []
    a, b = max(int(radius_a), 1), max(int(radius_b), 1)
    for row in range(-b, b + 1):
        for col in range(-a, a + 1):
            if (col / a) ** 2 + (row / b) ** 2 <= 1.0:
                cells.append((row + b, col + a))
    return cellset(cells)


def triangle(leg: int) -> tuple[Cell, ...]:
    return cellset((row, col) for row in range(leg) for col in range(leg - row))


def staircase(length: int) -> tuple[Cell, ...]:
    """A 45-degree diagonal run.

    One component under the pipeline's default 8-connectivity, and *no* face
    adjacency at all. It is the sharpest available test of whether a shape
    metric is being computed on cells or on physical extent.
    """
    return cellset((i, i) for i in range(length))


def notched_square(side: int, notch: int = 2) -> tuple[Cell, ...]:
    """A square with a corner bitten out -- concave without being thin."""
    cells = list(square(side))
    for row in range(notch):
        for col in range(notch):
            cells.remove((row, col))
    return cellset(cells)


def spiky_square(side: int, arm: int = 2) -> tuple[Cell, ...]:
    """A square with arms -- a plus on top of a block."""
    return cellset(list(square(side)) + list(cross(arm + side // 2)))


def _analytic_samples() -> list[ShapeSample]:
    """The analytic catalogue.

    Chosen so that each family stresses a *different* part of the geometry
    contract, and so that the family a human would call a particular shape is
    not also the family that happens to score well:

    * ``block`` -- solidity must be exactly 1.0 (theorem)
    * ``concave`` -- L, T, U, notch: the class the ``0.48`` band is *for*
    * ``ring`` -- a hole, which the exposed-edge oracle counts and a
      convex-hull denominator is blind to
    * ``diagonal`` -- corner contact only; no face adjacency
    * ``thin`` -- one-cell-thick structures, where a boundary-*cell* perimeter
      degenerates
    * ``disc`` -- curved boundary, where perimeter is not a lattice count at all
    * ``tiny`` -- the 1- and 2-cell regimes where no shape is measurable
    """

    def _sample(
        sample_id: str, family: str, cells: Sequence[Cell], description: str
    ) -> ShapeSample:
        return ShapeSample(
            sample_id=sample_id,
            shape_family=family,
            cells=cellset(cells),
            provenance=Provenance(
                category=CATEGORY_ANALYTICAL,
                construction=f"closed-form cell set: {sample_id}",
                truth_kind=TRUTH_EXACT,
                independent_of_pipeline=True,
                detail=(
                    "occupied cells defined by construction; perimeter and solidity "
                    "computed by independent exact oracles"
                ),
            ),
            description=description,
        )

    out: list[ShapeSample] = []
    for side in (1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50):
        out.append(
            _sample(
                f"block_{side}x{side}",
                "block",
                square(side),
                f"solid {side}x{side} block; solidity is a theorem at 1.0",
            )
        )
    for width, height in (
        (2, 1),
        (3, 1),
        (5, 1),
        (9, 1),
        (17, 1),
        (33, 1),
        (2, 3),
        (4, 6),
        (6, 2),
        (12, 5),
    ):
        out.append(
            _sample(
                f"rect_{width}x{height}",
                "block" if min(width, height) > 1 else "thin",
                rect(width, height),
                f"solid {width}x{height} rectangle",
            )
        )
    for arm, thickness in ((1, 1), (2, 1), (3, 1), (5, 1), (2, 2), (4, 1)):
        out.append(
            _sample(
                f"cross_a{arm}_t{thickness}",
                "concave",
                cross(arm, thickness),
                f"plus sign, arm {arm}, thickness {thickness}",
            )
        )
    for arm in (1, 2, 3, 5, 8):
        out.append(_sample(f"l_a{arm}", "concave", l_shape(arm), f"L shape, arm {arm}"))
    for arm in (2, 3, 5, 8):
        out.append(_sample(f"t_a{arm}", "concave", t_shape(arm), f"T shape, arm {arm}"))
    for arm in (2, 3, 5, 8):
        out.append(_sample(f"u_a{arm}", "concave", u_shape(arm), f"U shape, arm {arm}"))
    for side, thickness in ((3, 1), (5, 1), (7, 1), (9, 2)):
        out.append(
            _sample(
                f"ring_{side}_t{thickness}",
                "ring",
                hollow_square(side, thickness),
                f"hollow {side}x{side} ring, wall {thickness}",
            )
        )
    for radius in (1, 2, 3, 4, 6, 8, 12):
        out.append(
            _sample(f"disc_r{radius}", "disc", disc(radius), f"rasterised disc, radius {radius}")
        )
    for a, b in ((3, 1), (5, 2), (8, 3), (10, 2)):
        out.append(
            _sample(
                f"ellipse_{a}x{b}", "disc", ellipse(a, b), f"rasterised ellipse, semi-axes {a},{b}"
            )
        )
    for leg in (2, 3, 4, 6, 9):
        out.append(
            _sample(f"triangle_{leg}", "concave", triangle(leg), f"staircase triangle, leg {leg}")
        )
    for length in (2, 3, 4, 5, 6, 8, 12, 20, 30):
        out.append(
            _sample(
                f"diagonal_{length}",
                "diagonal",
                staircase(length),
                f"45-degree diagonal run, {length} cells, 8-connected only",
            )
        )
    for length in (2, 3, 4, 5, 6, 7, 8, 10, 14, 20, 30, 45):
        out.append(
            _sample(
                f"thin_{length}",
                "thin",
                line(length),
                f"one-cell-thick run, {length} cells",
            )
        )
    for side, notch in ((5, 1), (5, 2), (8, 2), (10, 3), (6, 3)):
        out.append(
            _sample(
                f"notch_{side}_n{notch}",
                "concave",
                notched_square(side, notch),
                f"{side}x{side} block with a {notch}x{notch} corner removed",
            )
        )
    out.append(
        _sample("spiky_10_a2", "concave", spiky_square(10, 2), "10x10 block plus a 2-cell cross")
    )
    return out


def analytic_shape_catalogue() -> tuple[ShapeSample, ...]:
    """The analytic dataset. Every sample carries its own provenance."""
    return tuple(_analytic_samples())


# ---------------------------------------------------------------------------
# Perturbation families (category B)
# ---------------------------------------------------------------------------


PERTURBATION_FACTORS: tuple[str, ...] = (
    "noise",
    "amplitude",
    "translation",
    "anisotropy",
    "raster_density",
    "contamination",
    "polarity",
)


@dataclass(frozen=True)
class PerturbationCase:
    """One known base response plus one controlled change.

    Exactly one factor varies. That is the whole point: a two-factor case cannot
    attribute its own difference, and an unattributable difference is not
    evidence about either factor.
    """

    case_id: str
    factor: str
    level: float
    base_label: str
    responses: tuple[Any, ...]
    width_m: float
    height_m: float
    noise_sigma: float
    dy_ratio: float
    base_pitch_m: float
    detail: str = ""

    def provenance(self) -> Provenance:
        return Provenance(
            category=CATEGORY_PERTURBATION,
            construction=(
                f"continuous forward model (sum of rotated Gaussians) + single "
                f"controlled factor '{self.factor}' at level {self.level:g}"
            ),
            truth_kind=TRUTH_ANALYTIC,
            independent_of_pipeline=True,
            detail=(
                f"base={self.base_label}, {len(self.responses)} constructed response(s); "
                f"only the named factor differs from the base. {self.detail}"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "factor": self.factor,
            "level": self.level,
            "base_label": self.base_label,
            "n_responses": len(self.responses),
            "width_m": self.width_m,
            "height_m": self.height_m,
            "noise_sigma": self.noise_sigma,
            "dy_ratio": self.dy_ratio,
            "base_pitch_m": self.base_pitch_m,
            "provenance": self.provenance().to_dict(),
        }


#: The base response every perturbation family departs from. One positive
#: compact response, amplitude 10, sigma 1.0 m, at the centre of a 24 x 18 m
#: field. Its amplitude-to-noise ratio at noise sigma 1.0 is 10, which sits
#: above the production detection threshold with room to spare; the amplitude
#: and noise families walk it down towards and past that boundary.
BASE_SCENE_WIDTH_M = 24.0
BASE_SCENE_HEIGHT_M = 18.0
BASE_AMPLITUDE = 10.0
BASE_SIGMA_M = 1.0
BASE_PITCH_M = 0.5


def _base_response() -> Any:
    from ..synthetic_core.cross_resolution import PhysicalResponse

    return PhysicalResponse(
        label="base",
        cx=BASE_SCENE_WIDTH_M / 2.0,
        cy=BASE_SCENE_HEIGHT_M / 2.0,
        sigma_x=BASE_SIGMA_M,
        sigma_y=BASE_SIGMA_M,
        amplitude=BASE_AMPLITUDE,
    )


def _make_response(
    label: str,
    *,
    cx: float | None = None,
    cy: float | None = None,
    sigma_x: float = BASE_SIGMA_M,
    sigma_y: float = BASE_SIGMA_M,
    amplitude: float = BASE_AMPLITUDE,
    orientation_deg: float = 0.0,
) -> Any:
    from ..synthetic_core.cross_resolution import PhysicalResponse

    return PhysicalResponse(
        label=label,
        cx=BASE_SCENE_WIDTH_M / 2.0 if cx is None else cx,
        cy=BASE_SCENE_HEIGHT_M / 2.0 if cy is None else cy,
        sigma_x=sigma_x,
        sigma_y=sigma_y,
        amplitude=amplitude,
        orientation_deg=orientation_deg,
    )


def perturbation_catalogue() -> tuple[PerturbationCase, ...]:
    """Category B: seven factors, one at a time, each with several levels.

    The levels are chosen to bracket the production operating point rather than
    to sample uniformly:

    * ``noise`` 0.25 .. 3.0, spanning peak-SNR 40 down to 3.3
    * ``amplitude`` 3 .. 20, spanning peak-SNR 3 to 20
    * ``translation`` 0 .. 0.9 m, up to within one base pitch of a cell centre
    * ``anisotropy`` sigma_y/sigma_x 1.0 .. 3.0
    * ``raster_density`` pitch 1.5 down to 0.2 m
    * ``contamination`` 0 .. 20 injected one-cell spikes
    * ``polarity`` amplitude sign
    """
    cases: list[PerturbationCase] = []

    def _add(
        case_id: str,
        factor: str,
        level: float,
        responses: tuple[Any, ...],
        *,
        noise_sigma: float = 1.0,
        dy_ratio: float = 1.0,
        base_pitch_m: float = BASE_PITCH_M,
        detail: str = "",
    ) -> None:
        cases.append(
            PerturbationCase(
                case_id=case_id,
                factor=factor,
                level=level,
                base_label="base",
                responses=responses,
                width_m=BASE_SCENE_WIDTH_M,
                height_m=BASE_SCENE_HEIGHT_M,
                noise_sigma=noise_sigma,
                dy_ratio=dy_ratio,
                base_pitch_m=base_pitch_m,
                detail=detail,
            )
        )

    _add("base", "reference", 0.0, (_base_response(),), detail="unperturbed reference")
    for sigma in (0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        _add(
            f"noise_{sigma:g}",
            "noise",
            sigma,
            (_base_response(),),
            noise_sigma=sigma,
            detail=f"peak-SNR {BASE_AMPLITUDE / sigma:.1f}",
        )
    for amplitude in (3.0, 5.0, 7.0, 10.0, 14.0, 20.0):
        _add(
            f"amp_{amplitude:g}",
            "amplitude",
            amplitude,
            (_make_response("amp", amplitude=amplitude),),
            detail=f"peak-SNR {amplitude / 1.0:.1f} at noise sigma 1.0",
        )
    for shift in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9):
        _add(
            f"translate_{shift:g}",
            "translation",
            shift,
            (
                _make_response(
                    "shift",
                    cx=BASE_SCENE_WIDTH_M / 2.0 + shift,
                ),
            ),
            detail=f"offset {shift:g} m = {shift / BASE_PITCH_M:g} base pitches",
        )
    for ratio in (1.0, 1.25, 1.5, 2.0, 3.0):
        _add(
            f"aniso_{ratio:g}",
            "anisotropy",
            ratio,
            (_make_response("aniso", sigma_x=BASE_SIGMA_M, sigma_y=BASE_SIGMA_M * ratio),),
            detail=f"sigma_y/sigma_x = {ratio:g}",
        )
    for pitch in (1.5, 1.0, 0.75, 0.5, 0.35, 0.25, 0.2):
        _add(
            f"raster_{pitch:g}",
            "raster_density",
            pitch,
            (_base_response(),),
            base_pitch_m=pitch,
            detail=f"lattice pitch {pitch:g} m",
        )
    for spikes in (0, 2, 5, 10, 20):
        _add(
            f"contam_{spikes}",
            "contamination",
            float(spikes),
            (_base_response(),),
            detail=f"{spikes} injected one-cell spikes at amplitude 40",
        )
    for amplitude in (10.0, -10.0):
        _add(
            f"polarity_{'neg' if amplitude < 0 else 'pos'}",
            "polarity",
            amplitude,
            (_make_response("pol", amplitude=amplitude),),
            detail="sign of the constructed response",
        )
    for dy_ratio in (1.0, 1.5, 2.0, 3.0):
        _add(
            f"lattice_dy{dy_ratio:g}",
            "raster_density",
            dy_ratio,
            (_base_response(),),
            dy_ratio=dy_ratio,
            base_pitch_m=0.5,
            detail=f"lattice anisotropy dy/dx = {dy_ratio:g}",
        )
    return tuple(cases)


def contamination_field(
    shape: tuple[int, int], *, n_spikes: int, amplitude: float, seed: int
) -> np.ndarray:
    """Deterministic single-cell contamination field.

    One-cell spikes are the hard case for a robust scale: they are exactly what
    a median/MAD estimator is designed to ignore, and exactly what a
    maximum-selection stage will find. Injected on a fixed seed so the
    contamination pattern is part of the case's identity.
    """
    field_ = np.zeros(shape, dtype=float)
    if n_spikes <= 0:
        return field_
    rng = np.random.default_rng(seed)
    rows = rng.integers(0, shape[0], size=n_spikes)
    cols = rng.integers(0, shape[1], size=n_spikes)
    for row, col in zip(rows, cols, strict=True):
        field_[row, col] += amplitude
    return field_


# ---------------------------------------------------------------------------
# Vendor fixtures (category C) -- behavioural reference only
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class VendorFixture:
    """One vendor CSV, content-addressed.

    ``content_sha256`` is what makes a behavioural observation reproducible: a
    finding recorded against a different file is a different finding, and the
    hash is how a reader tells.
    """

    case_id: str
    relative_path: str
    split: str
    content_sha256: str
    size_bytes: int

    def provenance(self) -> Provenance:
        return Provenance(
            category=CATEGORY_VENDOR,
            construction=f"vendor export, unmodified: {self.relative_path}",
            truth_kind=TRUTH_BEHAVIOURAL,
            independent_of_pipeline=True,
            detail=(
                "BEHAVIOURAL REFERENCE ONLY. The vendor annotation is a vendor claim, "
                "not a physical measurement; nothing in this package infers truth from it."
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "relative_path": self.relative_path,
            "split": self.split,
            "content_sha256": self.content_sha256,
            "size_bytes": self.size_bytes,
            "provenance": self.provenance().to_dict(),
        }


def vendor_fixture_index() -> tuple[VendorFixture, ...]:
    """Every vendor CSV, with a content hash. Order is stable and sorted."""
    root = _repo_root() / "scans" / "vendor_demo"
    out: list[VendorFixture] = []
    if not root.is_dir():
        return ()
    for path in sorted(root.rglob("*.csv")):
        split = path.parent.name
        out.append(
            VendorFixture(
                case_id=path.stem,
                relative_path=path.relative_to(_repo_root()).as_posix(),
                split=split,
                content_sha256=_sha256(path),
                size_bytes=path.stat().st_size,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Category D -- field evidence
# ---------------------------------------------------------------------------

FIELD_EVIDENCE_STATUS = "unavailable"

#: Why category D is empty, stated once and carried in every report. Each clause
#: is a separate thing that would have to exist; none of them does.
FIELD_EVIDENCE_GAP: tuple[str, ...] = (
    "no excavated, bored, or installation-verified ground truth in this repository",
    "no independent instrument response calibration record (line spacing, gain, "
    "reference level, temperature) for any scan",
    "no repeat-survey set over the same physical ground to separate instrument "
    "repeatability from real spatial variation",
    "no survey over a location whose buried content is known independently of the scan itself",
    "the only labelled real data is vendor annotation, which is a claim about a "
    "scan, not a measurement of the ground",
)


def field_evidence_availability() -> dict[str, Any]:
    """Category D as a recorded fact.

    Expressed as an availability record rather than an empty list so that "we
    looked and there is nothing" is distinguishable from "we did not look".
    """
    return {
        "category": CATEGORY_FIELD,
        "status": FIELD_EVIDENCE_STATUS,
        "sample_count": 0,
        "independent_calibration_possible": False,
        "gaps": list(FIELD_EVIDENCE_GAP),
        "consequence": (
            "Any parameter whose calibration requires knowing what is actually in "
            "the ground cannot be calibrated here. Those parameters are recorded "
            "as REQUIRES FIELD VALIDATION or INSUFFICIENT EVIDENCE, and the reason "
            "is this record rather than an absence of analysis."
        ),
        "vendor_annotation_is_not_ground_truth": True,
    }


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationDataset:
    """One category, with the provenance rule that governs its conclusions."""

    category: str
    samples: tuple[Any, ...]
    permits: str
    forbids: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "sample_count": len(self.samples),
            "permits": self.permits,
            "forbids": self.forbids,
            "provenance": [s.provenance.to_dict() for s in self.samples[:0]] or None,
        }


def calibration_datasets() -> dict[str, CalibrationDataset]:
    """All four categories, keyed by name, with the licence each one grants.

    The ``permits`` / ``forbids`` pair is the mechanism that stops category
    leakage -- the failure mode where a number is justified by a vendor case
    and reported as if it had been justified by a closed form.
    """
    return {
        CATEGORY_ANALYTICAL: CalibrationDataset(
            category=CATEGORY_ANALYTICAL,
            samples=analytic_shape_catalogue(),
            permits=(
                "deriving a dimensionless quantity exactly; proving invariances "
                "(translation, uniform rescaling, pitch, anisotropy); measuring a "
                "production estimator's bias against a closed form"
            ),
            forbids=(
                "any claim about a physical target's material or size; any claim "
                "about a false-positive rate on real data; any operating envelope "
                "(a construction is not an acquisition)"
            ),
        ),
        CATEGORY_PERTURBATION: CalibrationDataset(
            category=CATEGORY_PERTURBATION,
            samples=perturbation_catalogue(),
            permits=(
                "attributing a measured difference to one named factor; measuring "
                "output stability under a known perturbation; measuring response "
                "width and sampling-pitch sensitivity"
            ),
            forbids=(
                "estimating an absolute false-positive rate (the noise model is a "
                "chosen Gaussian, not a measured instrument noise spectrum); any "
                "claim about real soil or real targets"
            ),
        ),
        CATEGORY_VENDOR: CalibrationDataset(
            category=CATEGORY_VENDOR,
            samples=vendor_fixture_index(),
            permits=(
                "describing behaviour on real-shaped data; measuring distributions "
                "over a corpus; regression comparison; detecting drift"
            ),
            forbids=(
                "selecting a threshold, weight or band; any physical ground-truth "
                "claim; treating an annotation as a label of correctness. Vendor "
                "fixtures are a regression reference, not ground truth."
            ),
        ),
        CATEGORY_FIELD: CalibrationDataset(
            category=CATEGORY_FIELD,
            samples=(),
            permits=(),
            forbids=(
                "everything, because there is nothing. See field_evidence_availability() "
                "for the enumerated gaps and the consequence."
            ),
        ),
    }


def dataset_report() -> dict[str, Any]:
    """A JSON-serialisable census of the calibration datasets, with provenance."""
    out: dict[str, Any] = {
        "categories": list(CATEGORIES),
        "datasets": {},
    }
    for name, dataset in calibration_datasets().items():
        entry: dict[str, Any] = {
            "sample_count": len(dataset.samples),
            "permits": dataset.permits,
            "forbids": dataset.forbids,
        }
        if name == CATEGORY_FIELD:
            entry.update(field_evidence_availability())
        out["datasets"][name] = entry
    out["datasets"][CATEGORY_VENDOR]["fixtures"] = [f.to_dict() for f in vendor_fixture_index()]
    out["datasets"][CATEGORY_ANALYTICAL]["families"] = sorted({
        s.shape_family for s in analytic_shape_catalogue()
    })
    out["datasets"][CATEGORY_PERTURBATION]["factors"] = sorted({
        c.factor for c in perturbation_catalogue()
    })
    out["datasets"][CATEGORY_PERTURBATION]["cases"] = [
        c.to_dict() for c in perturbation_catalogue()
    ]
    return out


# ---------------------------------------------------------------------------
# Running production shape metrics on a cell set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionShapeMetrics:
    """What the production shape code returns for one cell set.

    Every field is read from the production functions
    (``core.shape._shape_metrics`` and ``core.shape._classify_shape``) at the
    production pitch the caller supplies. ``solidity_oracle`` and
    ``compactness_oracle`` are the independent exact values for the same cell
    set, so the two are always directly comparable for the same input.

    ``harness_grid`` and ``harness_rows`` are recorded because one production
    descriptor -- ``broadness_score`` -- is a ratio of the component to the
    *grid*, and therefore a property of the harness as much as of the shape.
    ``shape_class`` in particular is decided by ``broadness_score`` before the
    solidity branch is ever reached, so a shape's class from this harness is a
    statement about the shape *at this grid size*. Any conclusion about a
    solidity band must be read from ``solidity`` directly, not from
    ``shape_class``.
    """

    sample_id: str
    n_cells: int
    cell_dx: float
    cell_dy: float
    compactness: float
    solidity: float
    geometry_quality: float
    major_extent: float
    minor_extent: float
    elongation_ratio: float
    linearity_score: float
    aspect_ratio: float
    boundary_contact_ratio: float
    broadness_score: float
    line_support_score: float
    shape_class: str
    compactness_oracle: float
    solidity_oracle: float
    perimeter_edges: int
    erosion_boundary_cells: int
    harness_grid: int
    harness_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "n_cells": self.n_cells,
            "cell_dx": self.cell_dx,
            "cell_dy": self.cell_dy,
            "compactness": self.compactness,
            "compactness_oracle": self.compactness_oracle,
            "compactness_error": self.compactness - self.compactness_oracle,
            "solidity": self.solidity,
            "solidity_oracle": self.solidity_oracle,
            "solidity_error": self.solidity - self.solidity_oracle,
            "geometry_quality": self.geometry_quality,
            "major_extent": self.major_extent,
            "minor_extent": self.minor_extent,
            "elongation_ratio": self.elongation_ratio,
            "linearity_score": self.linearity_score,
            "aspect_ratio": self.aspect_ratio,
            "boundary_contact_ratio": self.boundary_contact_ratio,
            "broadness_score": self.broadness_score,
            "line_support_score": self.line_support_score,
            "shape_class": self.shape_class,
            "perimeter_edges": self.perimeter_edges,
            "erosion_boundary_cells": self.erosion_boundary_cells,
            "harness_grid": self.harness_grid,
            "harness_rows": self.harness_rows,
        }


#: Cells of clearance between the shape's bounding box and the grid edge, and
#: the smallest harness grid the shape is laid into.
#:
#: Two is not cosmetic. ``binary_erosion`` pads with background, so a cell whose
#: neighbour lies outside the array counts as boundary. Because the production
#: mask window is the component's own bounding box, every window-edge cell is
#: already on the component's outer shell, so this padding provably cannot
#: change the erosion result -- which :func:`border_bias_probe` measures rather
#: than assumes. A generous grid is needed for a different reason:
#: ``broadness_score`` divides by the grid, so a cramped harness would report
#: every shape as "broad" and never reach the solidity branch at all.
SHAPE_PAD_CELLS = 2
SHAPE_MIN_GRID_CELLS = 60


def production_shape_metrics(
    cells: Sequence[Cell],
    *,
    cell_dx: float = 1.0,
    cell_dy: float = 1.0,
    sample_id: str = "unnamed",
    pad: int = SHAPE_PAD_CELLS,
    min_grid_cells: int = SHAPE_MIN_GRID_CELLS,
    signal_value: float = 10.0,
) -> ProductionShapeMetrics:
    """Run the production shape code on an exact cell set and record the result.

    This is a *measurement harness*, not a reimplementation: it builds the grid
    the production extractor would build for a component with these cells and
    calls ``core.shape._shape_metrics`` unchanged.

    The oracle columns are computed from the same cell set by the exact oracles
    above, so ``solidity_error`` and ``compactness_error`` are always measured
    on identical input.
    """
    occupied = cellset(cells)
    if not occupied:
        raise ValueError("production_shape_metrics requires a non-empty cell set")
    dx, dy = float(cell_dx), float(cell_dy)
    if not (dx > 0.0 and dy > 0.0):
        raise ValueError("cell pitch must be positive")

    rows = [r for r, _ in occupied]
    cols = [c for _, c in occupied]
    span_rows = max(rows) - min(rows) + 1
    span_cols = max(cols) - min(cols) + 1
    clearance = max(int(pad), (int(min_grid_cells) - max(span_rows, span_cols)) // 2)
    grid_rows = span_rows + 2 * clearance
    grid_cols = span_cols + 2 * clearance
    row_offset = (grid_rows - span_rows) // 2
    col_offset = (grid_cols - span_cols) // 2
    local_rows = [r - min(rows) + row_offset for r in rows]
    local_cols = [c - min(cols) + col_offset for c in cols]

    signal = np.zeros((grid_rows, grid_cols), dtype=float)
    signal[np.asarray(local_rows), np.asarray(local_cols)] = signal_value
    grid = Grid2D(
        x_centers=(np.arange(grid_cols, dtype=float) + 0.5) * dx,
        y_centers=(np.arange(grid_rows, dtype=float) + 0.5) * dy,
        signal=signal,
        depth=np.full((grid_rows, grid_cols), 12.0, dtype=float),
        counts=np.ones((grid_rows, grid_cols), dtype=int),
    )

    xs = np.asarray(local_cols, dtype=int)
    ys = np.asarray(local_rows, dtype=int)
    local_mask = np.zeros((grid_rows, grid_cols), dtype=bool)
    local_mask[ys, xs] = True
    bbox = (
        slice(int(ys.min()), int(ys.max()) + 1),
        slice(int(xs.min()), int(xs.max()) + 1),
    )
    window = local_mask[bbox]

    metrics = _shape_metrics(grid, xs, ys, window, dx, dy)
    x_coords = grid.x_centers[xs]
    y_coords = grid.y_centers[ys]
    shape_class, _orientation, major_over_minor, linearity = _classify_shape(
        x_coords,
        y_coords,
        metrics["major_extent"],
        metrics["minor_extent"],
        metrics["boundary_contact_ratio"],
        metrics["broadness_score"],
        metrics["solidity"],
    )
    eroded = ndimage.binary_erosion(window)
    erosion_cells = int(np.sum(window & ~eroded))
    return ProductionShapeMetrics(
        sample_id=sample_id,
        n_cells=len(occupied),
        cell_dx=dx,
        cell_dy=dy,
        compactness=float(metrics["compactness"]),
        solidity=float(metrics["solidity"]),
        geometry_quality=float(metrics["geometry_quality"]),
        major_extent=float(metrics["major_extent"]),
        minor_extent=float(metrics["minor_extent"]),
        elongation_ratio=float(metrics["elongation_ratio"]),
        linearity_score=float(linearity),
        aspect_ratio=float(metrics["aspect_ratio"]),
        boundary_contact_ratio=float(metrics["boundary_contact_ratio"]),
        broadness_score=float(metrics["broadness_score"]),
        line_support_score=float(metrics["line_support_score"]),
        shape_class=shape_class,
        compactness_oracle=exact_compactness(occupied),
        solidity_oracle=float(exact_solidity_fraction(occupied)),
        perimeter_edges=exposed_edge_perimeter(occupied),
        erosion_boundary_cells=erosion_cells,
        harness_grid=grid_rows * grid_cols,
        harness_rows=grid_rows,
    )


def border_bias_probe(side: int = 6, min_grid_cells: int = 9) -> dict[str, Any]:
    """Measure how much of the compactness proxy is the grid edge, not the shape.

    ``binary_erosion`` treats everything outside the array as background, so in
    principle a component flush against the grid edge is penalised for cells
    that have no exposed boundary. This runs the *same* cell set at three grid
    sizes and reports the spread. A zero spread is a result, not a formality:
    it closes off "the proxy is contaminated by array padding" as an explanation
    for the proxy's errors, leaving the erosion-cell-count estimator itself.
    """
    occupied = square(side)
    rows: dict[str, Any] = {}
    for min_grid in (side, side + 2, side + 20):
        result = production_shape_metrics(
            occupied, sample_id=f"square{side}_grid{min_grid}", min_grid_cells=min_grid
        )
        rows[f"grid_{min_grid}"] = {
            "compactness": result.compactness,
            "erosion_boundary_cells": result.erosion_boundary_cells,
            "solidity": result.solidity,
            "oracle": result.compactness_oracle,
        }
    values = [rows[k]["compactness"] for k in rows]
    return {
        "shape": f"square_{side}",
        "per_grid": rows,
        "compactness_spread": max(values) - min(values),
        "erosion_cell_spread": max(rows[k]["erosion_boundary_cells"] for k in rows)
        - min(rows[k]["erosion_boundary_cells"] for k in rows),
        "interpretation": (
            "A zero spread confirms the production mask window (the component's own "
            "bounding box) already places every window-edge cell on the component's "
            "outer shell, so array padding cannot alter the erosion result."
        ),
    }


# ---------------------------------------------------------------------------
# Convenience for reports
# ---------------------------------------------------------------------------


def analytic_catalogue_digest() -> str:
    """A stable hash of the analytic catalogue.

    Pinned by a test so that a silent edit to a shape definition -- which would
    silently change every band characterisation derived from it -- is a visible
    change rather than a new "finding".
    """
    payload = json.dumps(
        [
            {
                "id": s.sample_id,
                "family": s.shape_family,
                "cells": [list(c) for c in s.cells],
            }
            for s in analytic_shape_catalogue()
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

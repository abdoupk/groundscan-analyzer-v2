"""Positions: the canonical index pair and its declared-extent expression.

The scan-local position is exact integer impulse indices within the
contributing scan's own lattice and frame: the engine's canonical
position, and the only one always available. A field position is derived
and emitted alongside it where the operator declared an extent, never
replacing it.

Each field axis carries its own scale, computed from the scan's own
extreme indices, and the scale travels inside the position and nowhere
else. The position names the scale's two inputs with their own
provenances, and the scale is their quotient, which tells a reader which
input to distrust. The divisor is the observed count less one: the
spacing, never the impulse density one interval apart.

Position zero sits at index one: the origin is wherever the file places
index one, the operator's marked starting point, physically real,
recorded in no vendor version, and not locatable by the engine. The
vendor's own series reads the declared extent at its maximum and zero at
its minimum on every real export, so on one-based lattices this series
coincides with the vendor's echo where the echo conforms.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Final

# A pitch needs two observed indices: one index defines no spacing at all.
MIN_PITCH_COUNT: Final[int] = 2


def pitch_span(span: float, count: int) -> float:
    """Return one axis pitch: its declared span over count less one.

    The spacing, recoverable only from the declared span and the observed
    count together. Never the impulse density span over count, which is
    one interval apart and never substituted: the divisor dial is
    count-minus-one against count, and this function reads the first.

    Args:
        span: The operator-declared extent along one axis.
        count: The observed index count along that axis, at least two.

    Returns:
        The pitch in the operator's own declared units, unconverted.
    """
    return span / (count - 1)


def field_coordinate(index: int, span: float, count: int) -> float:
    """Express one index in the operator's declared units.

    Position zero sits at index one, the file's own placing of the
    operator's mark, so no observed minimum is ever subtracted away:
    positions travel exactly as exported, never re-based.

    Args:
        index: The lattice index along one axis.
        span: The operator-declared extent along that axis.
        count: The observed index count along that axis, at least two.

    Returns:
        The coordinate in declared units, unconverted.
    """
    return (index - 1) * pitch_span(span, count)


def _bits(value: float) -> int:
    """Expose the binary64 bits of one pitch for exact comparison.

    A tolerance here would be a threshold wearing a gate's clothes: two
    pitches either are one unit or are not, so homogeneity is decided by
    bitwise identity, never by closeness.

    Args:
        value: The pitch to inspect.

    Returns:
        The little-endian bit pattern as an integer.
    """
    packed = struct.pack("<d", value)
    part: int = struct.unpack("<Q", packed)[0]
    return part


def same_pitch(first: float, second: float) -> bool:
    """Report whether two pitches are one homogeneous unit.

    Args:
        first: One axis pitch in declared units.
        second: The other axis pitch in declared units.

    Returns:
        True exactly where both pitches are bitwise identical.
    """
    return _bits(first) == _bits(second)

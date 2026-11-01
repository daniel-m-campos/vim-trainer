"""Seeded PRNG (mulberry32) bit-identical to the TypeScript mirror.

Example
-------
>>> rng = Mulberry32(42)
>>> 0.0 <= rng.next() < 1.0
True
"""

import math
from typing import Final

_MASK: Final = 0xFFFFFFFF
_GOLDEN: Final = 0x9E3779B1


class Mulberry32:
    """Mulberry32 generator over unsigned 32-bit state."""

    def __init__(self, seed: int):
        self.state = int(seed) & _MASK

    def __repr__(self) -> str:
        return f"Mulberry32(state={self.state})"

    def next(self) -> float:
        """Return the next float in [0, 1)."""
        self.state = (self.state + 0x6D2B79F5) & _MASK
        a = self.state
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK) ^ t
        return ((t ^ (t >> 14)) & _MASK) / 4294967296


def derive_seed(n: int, now: float) -> int:
    """Seed derived from the log length and the clock, for calls that take no seed.

    Parameters
    ----------
    n : int
        Number of records in the log.
    now : float
        Current time in seconds.

    Returns
    -------
    int
        Unsigned 32-bit seed.
    """
    return ((int(n) * _GOLDEN) & _MASK) ^ (math.floor(now) & _MASK)


def _imul(a: int, b: int) -> int:
    """Low 32 bits of a * b, as Math.imul then >>> 0."""
    return (a * b) & _MASK

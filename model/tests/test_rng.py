"""Tests for vimtrainer_model.rng."""

from vimtrainer_model.rng import Mulberry32, derive_seed


def test_mulberry32_known_sequence():
    rng = Mulberry32(42)
    draws = [rng.next() for _ in range(3)]
    assert draws == [0.6011037519201636, 0.44829055899754167, 0.8524657934904099]


def test_mulberry32_range_and_determinism():
    first = [Mulberry32(7).next() for _ in range(3)]
    assert first == [Mulberry32(7).next()] * 3
    rng = Mulberry32(2**32 - 1)
    assert all(0.0 <= rng.next() < 1.0 for _ in range(1000))


def test_derive_seed_mixes_log_length_and_time():
    assert derive_seed(0, 5.9) == 5
    assert derive_seed(1, 0) == 0x9E3779B1
    assert derive_seed(1, 0) != derive_seed(2, 0)

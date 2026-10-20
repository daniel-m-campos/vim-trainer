"""Tests for vimtrainer_model.projection."""

import pytest

from vimtrainer_model.projection import evaluate, fit_polynomial, r_squared


def test_fit_polynomial_linear_exact():
    coeffs = fit_polynomial([10.0, 8.0, 6.0, 4.0], 1)
    assert coeffs == pytest.approx([10.0, -2.0])
    assert r_squared([10.0, 8.0, 6.0, 4.0], coeffs) == pytest.approx(1.0)


def test_fit_polynomial_quadratic_exact():
    ys = [3 + 2 * x + 0.5 * x * x for x in range(16)]
    assert fit_polynomial(ys, 2) == pytest.approx([3.0, 2.0, 0.5])
    assert evaluate([3.0, 2.0, 0.5], 2.0) == 9.0


def test_r_squared_flat_is_zero():
    assert r_squared([5.0, 5.0, 5.0], [5.0, 0.0]) == 0.0

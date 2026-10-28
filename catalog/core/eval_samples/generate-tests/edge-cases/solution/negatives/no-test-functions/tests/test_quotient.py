"""Tests for src/quotient.py (planned; the test functions are not written yet)."""

import pytest

DIVISION_CASES = pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(7, 2, 3.5), (-7, 2, -3.5), (0, 3, 0.0)],
)

# TODO: assert quotient(1, 0) raises ZeroDivisionError and that floats raise TypeError.

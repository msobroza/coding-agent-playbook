"""Tests for src/quotient.py: every branch of quotient, plus its boundaries."""

import math

import pytest
from quotient import quotient


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (7, 2, 3.5),
        (-7, 2, -3.5),
        (7, -2, -3.5),
        (-8, -2, 4.0),
        (10**18, 10**9, 1e9),
    ],
)
def test_divides_integers(numerator: int, denominator: int, expected: float) -> None:
    assert quotient(numerator, denominator) == expected


@pytest.mark.parametrize("denominator", [1, -5])
def test_zero_numerator_returns_positive_zero(denominator: int) -> None:
    result = quotient(0, denominator)

    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


def test_zero_denominator_raises_zero_division_error() -> None:
    with pytest.raises(ZeroDivisionError, match="non-zero"):
        quotient(1, 0)


@pytest.mark.parametrize(("numerator", "denominator"), [(1.5, 2), (1, "2"), (None, 1)])
def test_non_integer_arguments_raise_type_error(numerator: object, denominator: object) -> None:
    with pytest.raises(TypeError, match="integer arguments"):
        quotient(numerator, denominator)  # type: ignore[arg-type]

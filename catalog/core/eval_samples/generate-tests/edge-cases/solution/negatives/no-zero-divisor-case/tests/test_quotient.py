"""Tests for src/quotient.py that never try a zero denominator."""

import pytest
from quotient import quotient


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(7, 2, 3.5), (-7, 2, -3.5), (7, -2, -3.5), (0, 5, 0.0)],
)
def test_divides_integers(numerator: int, denominator: int, expected: float) -> None:
    assert quotient(numerator, denominator) == expected


def test_non_integer_arguments_raise_type_error() -> None:
    with pytest.raises(TypeError):
        quotient(1.5, 2)  # type: ignore[arg-type]

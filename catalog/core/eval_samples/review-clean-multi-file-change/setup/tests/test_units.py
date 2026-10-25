import pytest

from src.units import to_kilograms


def test_kilograms_are_returned_as_given() -> None:
    assert to_kilograms(2.5, "kg") == 2.5


def test_pounds_convert_with_the_exact_factor() -> None:
    assert to_kilograms(10, "lb") == pytest.approx(4.5359237)


def test_an_unknown_unit_is_named_in_the_error() -> None:
    with pytest.raises(ValueError, match="'oz'"):
        to_kilograms(1, "oz")

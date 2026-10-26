import pytest

from src.shipping import quote_cents


def test_every_started_kilogram_is_charged() -> None:
    assert quote_cents(1.2) == 450 + 2 * 120


def test_a_whole_kilogram_is_charged_once() -> None:
    assert quote_cents(2) == 450 + 2 * 120


def test_a_non_positive_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        quote_cents(0)


def test_a_weight_in_pounds_is_charged_per_started_kilogram() -> None:
    # 5 lb is about 2.27 kg, so three kilograms are charged.
    assert quote_cents(5, "lb") == 450 + 3 * 120


def test_an_unknown_unit_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown weight unit"):
        quote_cents(1, "oz")

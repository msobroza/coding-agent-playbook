import pytest

from src.cart import Cart


def test_total_sums_every_line() -> None:
    cart = Cart()
    cart.add("pen", 150, 2)
    cart.add("ink", 400)
    assert cart.total_cents() == 700


def test_discount_takes_a_percentage_off() -> None:
    cart = Cart()
    cart.add("pen", 1000)
    assert cart.total_cents(discount_percent=25) == 750


@pytest.mark.parametrize("quantity", [0, -1])
def test_add_rejects_a_quantity_that_is_not_positive(quantity: int) -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        Cart().add("pen", 150, quantity)


def test_remove_rejects_more_than_held_or_a_negative_quantity() -> None:
    cart = Cart()
    cart.add("pen", 150, 2)
    with pytest.raises(ValueError, match="2 held"):
        cart.remove("pen", 5)
    with pytest.raises(ValueError, match="2 held"):
        cart.remove("pen", -1)
    assert cart.total_cents() == 300


def test_removing_every_unit_drops_the_line() -> None:
    cart = Cart()
    cart.add("pen", 150, 2)
    cart.remove("pen", 2)
    assert cart.lines == {}

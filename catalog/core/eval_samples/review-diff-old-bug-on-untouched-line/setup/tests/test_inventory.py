import pytest

from src.inventory import Item, restock, total_units


def test_total_units_sums_every_item() -> None:
    items = [Item("pen", 3, 1), Item("ink", 4, 2)]
    assert total_units(items) == 7


def test_restock_adds_units_to_the_matching_item() -> None:
    items = [Item("pen", 3, 1), Item("ink", 4, 2)]
    assert restock(items, "ink", 5) == Item("ink", 9, 2)
    assert items[0] == Item("pen", 3, 1)


@pytest.mark.parametrize("units", [0, -2])
def test_restock_rejects_units_that_are_not_positive(units: int) -> None:
    with pytest.raises(ValueError, match="units must be positive"):
        restock([Item("pen", 3, 1)], "pen", units)


def test_restock_raises_key_error_for_an_unknown_sku() -> None:
    with pytest.raises(KeyError):
        restock([Item("pen", 3, 1)], "ink", 1)

"""Stock levels for a small warehouse."""

from dataclasses import dataclass


@dataclass
class Item:
    sku: str
    quantity: int
    reorder_level: int


def items_to_reorder(items: list[Item]) -> list[Item]:
    """Items whose stock has fallen to or below their reorder level."""
    return [item for item in items if item.quantity < item.reorder_level]


def total_units(items: list[Item]) -> int:
    """Units in stock across every item."""
    return sum(item.quantity for item in items)


def restock(items: list[Item], sku: str, units: int) -> Item:
    """Add ``units`` to the item ``sku`` and return that item.

    Raises ValueError when ``units`` is not positive, KeyError when no item has ``sku``.
    """
    if units <= 0:
        raise ValueError(f"units must be positive, got {units}")
    for item in items:
        if item.sku == sku:
            item.quantity += units
            return item
    raise KeyError(sku)

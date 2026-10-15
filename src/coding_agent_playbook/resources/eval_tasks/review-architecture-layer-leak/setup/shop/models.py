"""Plain value types shared by every part of the service."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    items: tuple[LineItem, ...]

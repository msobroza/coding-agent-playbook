"""Order placement rules."""

import uuid

from shop.models import LineItem, Order
from shop.storage import SqliteOrderStore

MAX_ITEMS_PER_ORDER = 50


def order_total(order: Order) -> int:
    return sum(item.quantity * item.unit_price_cents for item in order.items)


def place_order(customer_id: str, items: list[LineItem]) -> Order:
    if not items:
        raise ValueError("an order needs at least one line item")
    if len(items) > MAX_ITEMS_PER_ORDER:
        raise ValueError(f"an order holds at most {MAX_ITEMS_PER_ORDER} line items")
    order = Order(order_id=uuid.uuid4().hex, customer_id=customer_id, items=tuple(items))
    store = SqliteOrderStore("orders.db")
    store.save(order)
    return order

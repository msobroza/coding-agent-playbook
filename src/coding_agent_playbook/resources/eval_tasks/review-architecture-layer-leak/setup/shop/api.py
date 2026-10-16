"""Request handlers: translate payload dicts to and from the order rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shop.models import LineItem
from shop.orders import place_order

if TYPE_CHECKING:
    from shop.models import Order


def handle_place_order(payload: dict[str, Any]) -> dict[str, Any]:
    items = [
        LineItem(sku=raw["sku"], quantity=raw["quantity"], unit_price_cents=raw["price"])
        for raw in payload["items"]
    ]
    order = place_order(payload["customer_id"], items)
    return _to_response(order)


def _to_response(order: Order) -> dict[str, Any]:
    return {"order_id": order.order_id, "item_count": len(order.items)}

"""SQLite persistence for orders."""

import sqlite3

from shop.models import Order


class SqliteOrderStore:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS orders "
            "(order_id TEXT PRIMARY KEY, customer_id TEXT, total_cents INTEGER)"
        )

    def save(self, order: Order) -> None:
        from shop.orders import order_total

        self._conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?)",
            (order.order_id, order.customer_id, order_total(order)),
        )
        self._conn.commit()

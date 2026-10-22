---
id: python-custom-exceptions
name: Custom exceptions
description: "Derive every domain error from one project base exception, name it after the failure mode, and carry the offending identifier."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: errors
priority: 23
tags: [python, errors]
---

# One base exception, one type per failure mode

## Description

Every project gets one base exception class, and every error it raises on purpose derives from that base, never directly from `Exception`. Name each exception after the failure mode and raise it where the failure is detected, with the offending identifier in the message. Callers can then catch one failure mode precisely, or the whole family with `except AppError`, and a generic `ValueError` or `Exception` never stands in for a domain failure.

## Bad Example

```python
def fetch_order(order_id: str) -> Order:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise ValueError("not found")  # a domain failure dressed as an argument error
    order = to_order(row)
    if not order.visible_to_customer:
        raise Exception("denied")  # callers can only catch everything
    return order
```

## Good Example

```python
class AppError(Exception):
    """Base of every error this application raises on purpose."""


class OrderNotFoundError(AppError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"order not found: {order_id!r}")
        self.order_id = order_id


class OrderAccessDeniedError(AppError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"access denied to order {order_id!r}")
        self.order_id = order_id


def fetch_order(order_id: str) -> Order:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise OrderNotFoundError(order_id)
    order = to_order(row)
    if not order.visible_to_customer:
        raise OrderAccessDeniedError(order_id)
    return order
```

## Notes

- Name the exception after the failure mode, not the location: `ConfigParseError`, not `ConfigParserError`.
- `ValueError` and `TypeError` are for violations of a function's argument contract (a negative quantity, an argument of the wrong type); domain failures get subclasses of the project base.
- Give each failure mode its own type when callers respond differently, such as not found versus access denied. One type with a status string forces callers to parse messages.
- Carry the offending identifier as an attribute as well as in the message; `python-error-messages-with-context` covers what the message says.
- Keep the hierarchy shallow: the base, then the failure modes, with an intermediate class only where callers catch that group.
- Raise where the failure is detected; turning it into an exit code or a response happens once, at the boundary (`python-error-boundaries`).

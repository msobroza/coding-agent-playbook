---
id: python-match-fallback
name: Match fallback
description: "End every match statement with a case _ that raises with the offending value, and call assert_never there when the subject is an Enum, a Literal or a union."
version: 1
scope: scoped
applies_if:
  python_version: ">=3.10"
globs:
  - "**/*.py"
section: functions
priority: 67
tags: [python, control-flow]
---

# End every match with a raising fallback

## Description

Python does not check that a `match` statement covers every case. A subject that matches no `case` skips the whole statement without an error, so a value added later (a new status, a new message type) falls through silently: the function returns `None` or carries on with unchanged state. End every `match` with a `case _:` that raises, naming the offending value. When the subject is an `Enum` member, a `Literal` or a union of types, call `assert_never` in that fallback: the type checker then reports the unhandled member or type at the `match`, before the code runs.

## Bad Example

```python
def apply_status(order: Order, status: str) -> None:
    match status:
        case "paid":
            order.mark_paid()
        case "shipped":
            order.mark_shipped()
        case "cancelled":
            order.cancel()
    # "refunded", added by the payment provider later, matches nothing:
    # the order silently stays as it was
```

## Good Example

```python
def apply_status(order: Order, status: str) -> None:
    match status:
        case "paid":
            order.mark_paid()
        case "shipped":
            order.mark_shipped()
        case "cancelled":
            order.cancel()
        case _:
            raise ValueError(f"unknown status {status!r} for order {order.order_id}")


class OrderStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"


def next_step(status: OrderStatus) -> str:
    match status:
        case OrderStatus.PENDING:
            return "request payment"
        case OrderStatus.PAID:
            return "ship"
        case OrderStatus.SHIPPED:
            return "notify the customer"
        case _:
            assert_never(status)  # adding a member makes the type checker fail here
```

## Notes

- `assert_never` comes from `typing` on Python 3.11 and later and from `typing_extensions` before. Without either, a three-line helper `def assert_never(value: NoReturn) -> NoReturn` that raises `AssertionError(f"unhandled value {value!r}")` gives the type checker the same check.
- The fallback raises; it never returns a made-up default or logs and carries on (`python-error-handling`). Where ignoring unknown values is the documented contract, write that `case _:` explicitly with a comment saying why, never by leaving the case out.
- The same holds when an `isinstance` chain is rewritten as a `match` on class patterns: the last `case _:` raises `TypeError` naming `type(value).__name__`, or calls `assert_never` on a closed union.
- `match` is no faster than `if`/`elif` and checks no coverage itself; when to use it at all is in `python-match-destructuring`.

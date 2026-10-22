---
id: python-match-destructuring
name: Match destructuring
description: "Use match to dispatch on the shape of data (record types, decoded JSON, sequences) instead of isinstance and key-checking chains, and keep plain if/elif or a dict for value lookups."
version: 1
scope: scoped
applies_if:
  python_version: ">=3.10"
globs:
  - "**/*.py"
section: functions
priority: 69
tags: [python, control-flow]
---

# Dispatch on the shape of data with match

## Description

`match`/`case` tests the structure of a value and binds its parts in one step. Use it when the branch depends on the shape or type of the data: several record types handled by one function, decoded JSON whose keys say what it is, a command split into words. It replaces an `isinstance` chain followed by attribute reads, or a ladder of `"key" in data` checks followed by indexing.

Do not use it when a plain `if`/`else` reads as well (two or three boolean conditions, comparisons against computed values) or when the branch only maps one value to another: a dict lookup is simpler.

## Bad Example

```python
def describe(event: object) -> str:
    if isinstance(event, OrderCreated):
        return f"order {event.order_id} created for {event.customer_id}"
    elif isinstance(event, OrderShipped):
        return f"order {event.order_id} shipped, tracking {event.tracking_number}"
    elif isinstance(event, OrderCancelled):
        return f"order {event.order_id} cancelled: {event.reason}"
    return ""  # a new event type gets an empty description


def parse_webhook(payload: dict[str, object]) -> Notice:
    if "type" in payload and payload["type"] == "refund" and "amount_cents" in payload:
        return Refund(cents=int(str(payload["amount_cents"])))
    if "type" in payload and payload["type"] == "dispute":
        return Dispute(reason=str(payload.get("reason", "")))
    raise ValueError(f"unknown webhook payload: {payload!r}")
```

## Good Example

```python
@dataclass(frozen=True)
class OrderCreated:
    order_id: str
    customer_id: str


@dataclass(frozen=True)
class OrderShipped:
    order_id: str
    tracking_number: str


@dataclass(frozen=True)
class OrderCancelled:
    order_id: str
    reason: str


OrderEvent: TypeAlias = OrderCreated | OrderShipped | OrderCancelled


def describe(event: OrderEvent) -> str:
    match event:
        case OrderCreated(order_id, customer_id):
            return f"order {order_id} created for {customer_id}"
        case OrderShipped(order_id, tracking_number=tracking):
            return f"order {order_id} shipped, tracking {tracking}"
        case OrderCancelled(order_id, reason=reason):
            return f"order {order_id} cancelled: {reason}"
        case _:
            assert_never(event)


def parse_webhook(payload: dict[str, object]) -> Notice:  # decoded external JSON
    match payload:
        case {"type": "refund", "amount_cents": int(cents)}:
            return Refund(cents=cents)
        case {"type": "dispute", "reason": str(reason)}:
            return Dispute(reason=reason)
        case _:
            raise ValueError(f"unknown webhook payload: {payload!r}")
```

## Notes

- Model shapes the code owns as records (dataclasses, which set `__match_args__` for positional patterns) and match them with class patterns; keep mapping patterns for decoded external data, and parse it into records once at the boundary.
- Pattern kinds: literals (`case "quit":`), captures (`case ["load", filename]:`), alternatives (`case "quit" | "exit":`), star captures (`case ["quit", *rest]:`), class and mapping patterns, and `as` to bind a matched part.
- A guard (`case {"status": status} if status >= 500:`) is checked after the pattern matches; when it fails, matching moves on to the next case.
- Every `match` ends in a raising `case _:`; that rule and `assert_never` are in `python-match-fallback`.
- `match` versus a dict of functions: when the branches are swappable algorithms chosen by a key or by configuration, use a dict of callables or a strategy object (design-dispatch-table and design-strategy in the design-patterns skill); `match` is for dispatch on structure.
- A custom class needs `__match_args__ = ("x", "y")` to accept positional patterns; keyword patterns (`Point(x=0)`) work on any class.

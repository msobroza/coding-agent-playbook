---
id: python-type-aliases
name: Type aliases
description: "Name a repeated Callable signature with a role-named alias, and give identifiers that must never be mixed their own NewType."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 47
tags: [python, typing]
---

# Type aliases

## Description

A function can be passed around like any other value, and its type is `Callable[[ArgType, ...], ReturnType]`. Written out in every signature, such a type is hard to read and says nothing about the role the function plays. A type alias gives it a name from the domain, `FeeRule` rather than `Callable[[Parcel], Decimal]`, so each signature reads as intent and the type checker still rejects a function whose parameters or return type do not match. Identifiers deserve the same care: a `CustomerId` and an `OrderId` that are both plain `str` can be swapped without any warning, while two `NewType`s make the type checker catch the mix-up.

## Bad Example

```python
def quote(parcel: Parcel, rules: list[Callable[[Parcel], Decimal]]) -> Decimal:
    return sum((rule(parcel) for rule in rules), Decimal(0))


def cheapest(parcel: Parcel, options: dict[str, Callable[[Parcel], Decimal]]) -> str:
    return min(options, key=lambda name: options[name](parcel))


def ship(order_id: str, customer_id: str) -> None: ...


ship(customer.id, order.id)  # swapped, and nothing complains
```

## Good Example

```python
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import NewType

OrderId = NewType("OrderId", str)
CustomerId = NewType("CustomerId", str)

#: Prices one part of a shipment, such as weight, distance or insurance.
FeeRule = Callable[[Parcel], Decimal]


def weight_fee(parcel: Parcel) -> Decimal:
    return Decimal("0.80") * parcel.weight_kg


def quote(parcel: Parcel, rules: Sequence[FeeRule]) -> Decimal:
    return sum((rule(parcel) for rule in rules), Decimal(0))


def ship(order_id: OrderId, customer_id: CustomerId) -> None: ...


ship(OrderId("o-17"), CustomerId("c-4"))
```

`weight_fee` satisfies `FeeRule` without declaring anything; a function that returned a `float` would be rejected.

## Notes

- Name an alias for the role it plays (`FeeRule`, `PriceFormatter`, `RetryPolicy`), never for its shape (`DecimalFunc`), and define it once, in the module that consumes it.
- Break a deeply nested type into named aliases: a type checker's error on `dict[str, list[tuple[int, Callable[[str], float | None]]]]` is hard to read.
- A single-method abstract class used only as a function type can become a `Callable` alias, but only at a real seam (an external system, a test fake, or two or more implementations); a single in-process collaborator can stay its concrete type.
- When the behavior needs several methods or keyword parameters, use a small `Protocol` instead of a `Callable` alias.
- Write aliases with plain assignment, which works on every supported Python; the `type` statement and generic aliases are covered in `python-typing`.
- `NewType` costs nothing at runtime and checks nothing at runtime. When an identifier also needs validation (a format, a range), make it a small value object instead: `design-value-objects` (design-patterns skill).

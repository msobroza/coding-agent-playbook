---
id: design-function-wrapper
name: Function wrapper
description: "When an existing function has the right logic but the wrong parameters for a seam, write a small function that translates the arguments and delegates, instead of converting at every call site or widening the original."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 81
tags: [python, design, patterns]
---

# Function wrapper

## Description

A function wrapper calls an existing function but presents a different interface: it translates the arguments, the return value or both, then delegates and returns the result at once. Use one when a function already does the work but its parameters do not fit the place that calls it. The translation then lives in one named function, the original stays generic, and callers stop repeating the conversion.

## Bad Example

```python
def percentage_discount(price_cents: int, rate: Decimal) -> int:
    return int((price_cents * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# Every caller converts the loyalty level itself before calling.
def checkout_total(order: Order) -> int:
    if order.loyalty is Loyalty.GOLD:
        rate = Decimal("0.20")
    elif order.loyalty is Loyalty.SILVER:
        rate = Decimal("0.15")
    else:
        rate = Decimal("0.10")
    return order.subtotal_cents - percentage_discount(order.subtotal_cents, rate)
```

Widening `percentage_discount` with a `loyalty` parameter is no better: the generic function now knows about one program.

## Good Example

```python
class Loyalty(Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


LOYALTY_RATES: Final[Mapping[Loyalty, Decimal]] = {
    Loyalty.BRONZE: Decimal("0.10"),
    Loyalty.SILVER: Decimal("0.15"),
    Loyalty.GOLD: Decimal("0.20"),
}


def loyalty_discount(price_cents: int, loyalty: Loyalty) -> int:
    """Translate the loyalty level into a rate, then delegate."""
    return percentage_discount(price_cents, LOYALTY_RATES[loyalty])


def checkout_total(order: Order) -> int:
    return order.subtotal_cents - loyalty_discount(order.subtotal_cents, order.loyalty)
```

Where the seam expects a `DiscountRule = Callable[[int], int]`, fit the wrapper to it at the wiring point, for example with `functools.partial(loyalty_discount, loyalty=customer.loyalty)`.

## Notes

- A wrapper is not a decorator: it does not replace the original or use `@` syntax, and the original stays callable on its own. Decorators are python-decorators in the python-coding skill.
- Pre-binding arguments with `functools.partial` and its typing caveats are python-closures-and-partial in the python-coding skill.
- Wrapping a third-party API whose shape differs from yours, or translating its exceptions, is design-adapter.
- When the translated value is configured once and the function is called many times, return a configured function instead: design-function-builder.
- Stop when the caller can pass the values directly: a wrapper that renames nothing adds a hop.

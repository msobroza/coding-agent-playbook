---
id: design-value-objects
name: Value objects
description: "Give a domain value with rules (money, rates, measurements, constrained codes) a frozen dataclass that validates on construction instead of passing a bare str, int or float."
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 68
tags: [python, design, patterns]
---

# Value objects

## Description

When prices, rates, distances or email addresses travel as bare primitives (primitive obsession), the type checker cannot stop a caller from passing them in the wrong order, at the wrong scale or with invalid data. Every call site must remember the conventions (is the discount a fraction or a percentage?) and repeat the same checks. A value object wraps the primitive in a small immutable type that validates once, on construction: an invalid value cannot exist, mixed-up arguments fail type checking, and the rules live beside the data they protect.

## Bad Example

```python
def apply_discount(price: float, discount: float) -> float:
    return price * (1.0 - discount)


apply_discount(100.0, 0.2)  # 80.0
apply_discount(100.0, 20)  # -1900.0: meant 20 %, passed 20
apply_discount(-50.0, 0.1)  # a negative price is accepted
apply_discount(0.2, 100.0)  # wrong argument order, type-checks fine
```

## Good Example

```python
MINOR_UNITS: Final[Mapping[str, int]] = {"EUR": 2, "USD": 2, "JPY": 0}


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str  # ISO 4217 code

    def __post_init__(self) -> None:
        if self.currency not in MINOR_UNITS:
            raise ValueError(f"unknown currency {self.currency!r}; known: {sorted(MINOR_UNITS)}")
        if self.amount < 0:
            raise ValueError(f"amount must not be negative, got {self.amount}")

    def times(self, factor: Decimal) -> Money:
        step = Decimal(1).scaleb(-MINOR_UNITS[self.currency])  # 0.01 for EUR, 1 for JPY
        return Money((self.amount * factor).quantize(step, rounding=ROUND_HALF_UP), self.currency)


@dataclass(frozen=True)
class Rate:
    fraction: Decimal  # 0.2 means 20 %

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.fraction <= Decimal(1):
            raise ValueError(f"rate must be between 0 and 1, got {self.fraction}")


def apply_discount(price: Money, discount: Rate) -> Money:
    return price.times(1 - discount.fraction)


apply_discount(Money(Decimal("100.00"), "EUR"), Rate(Decimal("0.2")))
```

## Notes

- Create value objects for money (amount and currency), measurements with units, identifiers that get mixed up, constrained strings (email address, phone number, country code) and rates or percentages.
- Money is never a `float` (smell id float-money): binary floats cannot represent most decimal fractions, so sums drift by cents. Use `Decimal` built from strings, or integer minor units.
- Subclassing `int`, `float` or `str` for a value type loses the type on arithmetic and string methods (`Meters(3) + 1` is a plain `int`); prefer a frozen dataclass once operations matter.
- Grow the type with methods and operators as rules accumulate; keep it immutable, so an operation returns a new value.
- Not for values with no rules and no risk of confusion, or for intermediate results inside one function.
- How to validate in `__post_init__` is `python-dataclass-post-init`, and `NewType` for identifiers that need only a static distinction (no runtime check) is `python-type-aliases`, both in the python-coding skill; this rule decides when a primitive earns a value type.

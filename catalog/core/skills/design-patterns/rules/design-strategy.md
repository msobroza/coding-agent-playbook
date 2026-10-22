---
id: design-strategy
name: Strategy
description: "When an if/elif chooses among algorithms, pass the algorithm in as a function typed with a role-named Callable alias, or a callable frozen dataclass when it needs configuration."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 66
tags: [python, design, patterns]
---

# Strategy

## Description

A strategy is a higher-order function: the caller hands in the algorithm instead of the callee choosing it from a flag. The classic form wraps each algorithm in a class behind an abstract base; in Python the pattern sheds that ceremony. Type the seam with a role-named `Callable` alias, pass plain functions, and move to a callable frozen dataclass when a variant needs named configuration. The consumer then sees only the alias and never changes when a variant is added.

## Bad Example

```python
@dataclass
class Order:
    price_cents: int
    quantity: int

    def total_cents(self, discount_type: str) -> int:
        subtotal = self.price_cents * self.quantity
        if discount_type == "percentage":
            discount = subtotal * 20 // 100  # magic number, no way to configure it
        elif discount_type == "fixed":
            discount = 10_00
        else:
            discount = 0  # a typo in discount_type silently means no discount
        return subtotal - discount
```

## Good Example

```python
DiscountFunction = Callable[[int], int]  # subtotal in cents -> discount in cents


def no_discount(subtotal_cents: int) -> int:
    return 0


@dataclass(frozen=True)
class PercentageDiscount:
    percent: Decimal

    def __call__(self, subtotal_cents: int) -> int:
        discount = Decimal(subtotal_cents) * self.percent / 100
        return int(discount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Order:
    price_cents: int
    quantity: int
    discount: DiscountFunction = no_discount

    def total_cents(self) -> int:
        subtotal = self.price_cents * self.quantity
        return max(0, subtotal - self.discount(subtotal))


order = Order(price_cents=100_00, quantity=2, discount=PercentageDiscount(Decimal("30")))
```

## Notes

- Signals: a long if/elif where each branch is a variant of one computation; a `type` or `mode` parameter; parameters only one variant uses; the caller needs to swap behavior at run time.
- Progression: a `Callable` alias with plain functions; then a callable frozen dataclass for named configuration; then a Protocol when a variant has several methods or the method name carries meaning; then an ABC only when implementations share code.
- Do not widen the shared signature with parameters only one variant needs; configure that variant at construction.
- `functools.partial` blurs the signature: some type checkers see only `partial[int]`, so a mismatch with your alias can slip through, and reprs and tracebacks hide what was bound. Prefer a closure or a callable dataclass where typing matters.
- Keep the `if` for two fixed branches that will not grow.
- When each branch only maps a key to a value or a handler named in config, a lookup table is enough: see design-dispatch-table. A function that builds and returns a configured strategy is design-function-builder.
- Converting ABC or Protocol strategy classes to functions step by step, with each form's trade-offs: see strategy-progression.md.

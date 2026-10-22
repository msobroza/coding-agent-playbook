---
id: design-template-method
name: Template method
description: "When several classes copy the same sequence of steps and differ only in some steps, write the sequence once as a function that takes the varying steps through a small Protocol or callables; use an ABC template only when the base must hold state or enforce overrides."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 83
tags: [python, design, patterns]
---

# Template method

## Description

The template method fixes the order of an algorithm's steps and lets each variant supply the steps that differ. Without it, sibling classes copy the same sequence, and a change to the sequence (an error check, a log line) must be repeated in every copy. A Protocol alone cannot hold the shared sequence, since it declares shape, not behavior. The lightest Pythonic form is a free function that runs the sequence and takes the varying steps as a Protocol-typed parameter, or as callables when there are only one or two of them. The concrete classes inherit from nothing and stay usable elsewhere.

## Bad Example

```python
class FlourRestocker:
    def run(self) -> None:  # the same sequence, copied into every class
        prices = self.fetch_prices()
        quantity = self.order_quantity()
        if self.should_buy(prices):
            self.place_order(quantity)
        elif self.should_cancel(prices):
            self.cancel_open_orders()


class CoffeeRestocker:
    def run(self) -> None:
        prices = self.fetch_prices()
        quantity = self.order_quantity()
        if self.should_buy(prices):
            self.place_order(quantity)
        elif self.should_cancel(prices):
            self.cancel_open_orders()
```

## Good Example

```python
class Restocker(Protocol):
    def fetch_prices(self) -> Sequence[Decimal]: ...
    def order_quantity(self) -> int: ...
    def should_buy(self, prices: Sequence[Decimal]) -> bool: ...
    def should_cancel(self, prices: Sequence[Decimal]) -> bool: ...
    def place_order(self, quantity: int) -> None: ...
    def cancel_open_orders(self) -> None: ...


def restock(restocker: Restocker) -> None:
    """The sequence, written once; each restocker supplies the steps."""
    prices = restocker.fetch_prices()
    quantity = restocker.order_quantity()
    if restocker.should_buy(prices):
        restocker.place_order(quantity)
    elif restocker.should_cancel(prices):
        restocker.cancel_open_orders()


class CoffeeRestocker:  # no base class: it matches Restocker by shape
    def should_buy(self, prices: Sequence[Decimal]) -> bool:
        return prices[-1] < Decimal("4.50")

    ...  # the other steps
```

## Notes

- Choose an ABC whose template method calls abstract hooks when the base must hold state the sequence uses, or when every subclass must be forced to implement each step. Mark the template method `typing.final` so type checkers stop a subclass from overriding the sequence instead of the hooks, and keep the hierarchy one level deep.
- Avoid hooks that only work if the subclass remembers to call `super()`.
- Choose the free function when the concrete classes are used outside this sequence, or should not couple to a base class. It must reach the steps through its parameter, not `self`.
- Setup and teardown around a varying body is a context manager (`contextlib.contextmanager`), not a template.
- When the Protocol grows past four or five methods or callers need different subsets, split it: design-interface-segregation.
- Stop when only one variant exists: write the sequence inline.

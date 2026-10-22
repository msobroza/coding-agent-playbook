---
id: python-closures-and-partial
name: Closures and partial
description: "Fit a function to a narrower callable signature with functools.partial or a closure instead of a one-method configuration class, and keep lambdas for throwaway inline callables."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: functions
priority: 70
tags: [python, functions]
---

# Pre-bind configuration with partial or a closure

## Description

A higher-order function often expects a callable with fewer parameters than your logic needs: `send_promotion` takes `Callable[[Customer], bool]`, but the eligibility check also needs a cutoff age. Separate configuration-time arguments from call-time arguments without writing a class that exists only to hold them:

- `functools.partial` pre-fills arguments of an existing function and returns a callable with the remaining parameters.
- A closure is an inner function that captures variables of the outer one; use it when setup must run once, before the returned function is called.
- A `lambda` is a throwaway, single-expression callable written inline at one call site.

## Bad Example

```python
class AgeChecker:  # a class whose only job is to remember one number
    def __init__(self, cutoff_age: int) -> None:
        self.cutoff_age = cutoff_age

    def check(self, customer: Customer) -> bool:
        return customer.age >= self.cutoff_age


send_promotion(customers, is_eligible=AgeChecker(50).check)

total_with_tax = lambda order: order.total * (1 + TAX_RATE) if order.is_taxable else order.total
```

## Good Example

```python
def is_at_least_age(customer: Customer, cutoff_age: int) -> bool:
    return customer.age >= cutoff_age


is_senior = partial(is_at_least_age, cutoff_age=50)  # Callable[[Customer], bool]
send_promotion(customers, is_eligible=is_senior)


def make_sku_check(prefixes: Iterable[str]) -> Callable[[str], bool]:
    pattern = re.compile(rf"(?:{'|'.join(map(re.escape, prefixes))})-\d{{6}}")  # once

    def is_valid_sku(sku: str) -> bool:
        return pattern.fullmatch(sku) is not None

    return is_valid_sku


is_catalog_sku = make_sku_check(["BK", "EL"])


def total_with_tax(order: Order) -> Decimal:
    if order.is_taxable:
        return order.total * (1 + TAX_RATE)
    return order.total


oldest = max(customers, key=lambda customer: customer.age)  # throwaway: fine
```

## Notes

- Choose `partial` when the function already exists with the right parameters, nothing has to be computed at creation time, and one line says it all. Choose a closure when setup should run once, when the inner function combines several captured values, or when a descriptive outer name (`make_sku_check`) documents the configuration.
- Check that the type checker still verifies the parameters a `partial` leaves open; where it does not, write a small named function, which keeps the signature explicit.
- Building specialized validators from a general one is a typical use: `is_percentage = partial(in_range, low=0, high=100)`.
- A closure captures variables, not values: a loop that builds closures over its loop variable sees only the last value, so bind it with `partial` or a default parameter.
- Name anything reused: assigning a `lambda` to a name is flagged by Ruff (E731), gives `<lambda>` in tracebacks and takes no annotations. Write a `def` when the logic needs more than one expression, is reused, or deserves a name.
- A closure or `partial` must not open an unmanaged resource such as a connection at creation time; inject the open resource instead (`python-dependency-injection`, `python-context-managers`).
- The seams built from these mechanics (callbacks, function wrappers, functions that build functions) are design-callback, design-function-wrapper and design-function-builder in the design-patterns skill; a configured strategy is design-strategy.

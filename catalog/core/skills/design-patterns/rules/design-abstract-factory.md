---
id: design-abstract-factory
name: Abstract factory
description: "When several objects or functions must be swapped together as a family, bundle the matching callables in a frozen dataclass with named, typed fields, chosen once by the entry point, instead of flags that pick each member separately."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 91
tags: [python, design, patterns]
---

# Abstract factory

## Description

Some objects only make sense together: a region's formatter, validator and tax rule, or a tax system's income and capital calculators. When a function selects each member with its own flag or `if`, it decides what to create and does the computation, every new family adds flags, and nothing stops a caller from mixing members of two families. Group each family into one value chosen once. The lightest Pythonic form is a frozen dataclass whose fields are the family's callables; the consumer takes that bundle and never learns which family it got.

## Bad Example

```python
def compute_tax(
    income_cents: int, capital_cents: int, *, progressive: bool, tax_capital: bool
) -> int:
    # Creation decisions mixed into the computation; flags can pick a mismatched pair.
    income_tax = (
        progressive_income_tax(income_cents) if progressive else flat_income_tax(income_cents)
    )
    capital_tax = capital_gains_tax(capital_cents) if tax_capital else 0
    return income_tax + capital_tax
```

## Good Example

```python
TaxRule = Callable[[int], int]  # amount in cents -> tax in cents


def no_tax(amount_cents: int) -> int:
    return 0


@dataclass(frozen=True)
class TaxSystem:
    income_tax: TaxRule
    capital_tax: TaxRule


PROGRESSIVE: Final = TaxSystem(income_tax=progressive_income_tax, capital_tax=capital_gains_tax)
FLAT: Final = TaxSystem(income_tax=flat_income_tax, capital_tax=no_tax)


def compute_tax(income_cents: int, capital_cents: int, system: TaxSystem) -> int:
    return system.income_tax(income_cents) + system.capital_tax(capital_cents)


# The entry point picks the family once, for example from settings.
tax = compute_tax(income_cents, capital_cents, PROGRESSIVE)
```

## Notes

- Use named, typed fields, not a tuple of functions: a positional tuple lets two members swap places and still type-check.
- When a family needs configuration (a rate, a threshold), write a builder function that returns the bundle (`make_flat_system(rate)`), so the configuration stays out of the `TaxRule` signature; `functools.partial` chains wired at startup become unreadable past a few.
- Keep one factory class per family when the products have several methods or keep state between calls; a `Callable` alias replaces one method only. Classes are callables, so a class object can also stand in as a factory field.
- Not when there is one product (pass one function: design-strategy), when the members vary independently (separate strategies), or when there are two fixed variants that will not grow (an `if` is clearer).
- When the family is picked by a key that arrives as data (a config string), map the key to the bundle: design-dispatch-table.
- The step-by-step walkthrough from ABC factories to Protocols, callables and a frozen bundle: see abstract-factory-progression.md.

---
id: design-lightest-construct
name: The lightest construct
description: "Use a function before a class, a module for stateless helpers and a dataclass for a record; a class earns its place by guarding state."
scope: scoped
globs:
  - "**/*.py"
section: simplicity
priority: 51
tags: [python, design, simplicity]
---

# The lightest construct

## Description

A class earns its place when it keeps state together with the behavior that protects it. Everything else has a lighter home: a function for a computation with no state between calls, a module for related functions with no shared state, and a dataclass for named fields with little behavior. Keep each class either data-focused (mostly fields, few methods) or behavior-focused (methods guarding a little state); a class with neither real data nor state is ceremony around a function.

## Bad Example

```python
class FareMath:  # a namespace: every method is a staticmethod
    @staticmethod
    def peak_fare(base: Decimal) -> Decimal:
        return base * PEAK_FACTOR

    @staticmethod
    def off_peak_fare(base: Decimal) -> Decimal:
        return base * OFF_PEAK_FACTOR


class SlugMaker:  # no state: a class around one function
    def make(self, title: str) -> str:
        return "-".join(title.lower().split())


class Playlist:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = tracks

    def format_duration(self, seconds: int) -> str:  # never reads self
        return f"{seconds // 60}:{seconds % 60:02d}"
```

## Good Example

```python
# fares.py: the module is the namespace
def peak_fare(base: Decimal) -> Decimal:
    return base * PEAK_FACTOR


def make_slug(title: str) -> str:
    return "-".join(title.lower().split())


def format_duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


@dataclass(frozen=True)
class PercentageDiscount:  # named, inspectable configuration
    rate: Decimal

    def __call__(self, price: Decimal) -> Decimal:
        return price * (1 - self.rate)
```

## Notes

| You have | Use | Instead of |
| --- | --- | --- |
| A computation with no state between calls | a function | a class with one method and no fields |
| Related functions with no shared state | a module | a class of staticmethods |
| Named fields and little behavior | a dataclass (frozen for values) | a dict, or a tuple read by position |
| State plus the rules that keep it consistent | a class whose methods guard it | functions that all mutate one dict |
| One behavior to inject | a role-named `Callable` alias | a single-method ABC |
| A closed set of options | an `Enum` or `Literal[...]` | bare string constants |

- Promote only when a need appears: function, then closure, then callable dataclass, then class; `Callable`, then `Protocol`, then `ABC`.
- Keep a callable dataclass when instances carry different named configuration or state between calls; configuring a generic function with a closure or `functools.partial` is python-coding's python-closures-and-partial.
- How a record is shaped once it exists is python-coding's python-data-shapes; design-start-with-the-data decides that one is missing.
- A method that never reads `self` (smell id method-could-be-function) becomes a module function; keep it a method only when it overrides a base method, satisfies a Protocol or belongs to the class's concept as a `staticmethod`.
- Do not convert when the lighter form reads worse: `partial` everywhere can hide intent that a small class with named fields states plainly.
- Telling this rule apart from `design-dry-yagni-kiss`, `design-pattern-from-smell` and python-coding's python-data-shapes: see rule-neighbors.md.

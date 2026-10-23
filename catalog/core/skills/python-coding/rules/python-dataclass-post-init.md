---
id: python-dataclass-post-init
name: Dataclass post-init
description: "Validate and normalize dataclass fields in __post_init__, raising with the offending value; derive values with @property, and keep field(init=False) for values computed once."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 65
tags: [python, design, data]
---

# Validate dataclass fields in `__post_init__`

## Description

`__post_init__` runs right after the generated `__init__`. Use it to check and normalize field values, so an invalid record can never exist, and raise with the offending value. Keep `field(init=False)` for a value computed once from the inputs that callers must not pass; a value derived from other fields is a `@property` (`python-data-shapes`).

## Bad Example

```python
@dataclass
class Vehicle:
    brand: str
    model: str
    seats: int
    display_name: str = field(init=False)

    def __post_init__(self) -> None:
        self.display_name = f"{self.brand} {self.model}"  # stale once brand changes
        # no checks: Vehicle(brand="", model="", seats=-2) is accepted


def register(vehicle: Vehicle) -> None:
    if not vehicle.brand or vehicle.seats < 1:  # every caller re-checks, or forgets to
        raise ValueError("bad vehicle")
```

## Good Example

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)  # its inputs cannot change, so search_key cannot go stale
class Vehicle:
    brand: str
    model: str
    seats: int
    search_key: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        brand = self.brand.strip()
        if not brand:
            raise ValueError(f"brand must be non-blank text, got {self.brand!r}")
        if self.seats < 1:
            raise ValueError(f"seats must be at least 1, got {self.seats}")
        object.__setattr__(self, "brand", brand)  # frozen: assign through object
        object.__setattr__(self, "search_key", f"{brand}:{self.model}".casefold())

    @property
    def display_name(self) -> str:  # derived on access, never stale
        return f"{self.brand} {self.model}"


Vehicle(brand="Volvo", model="XC40", seats=0)
# ValueError: seats must be at least 1, got 0
```

## Notes

- Choose the tool by need: `field(default_factory=...)` for an independent default (an empty list); `__post_init__` to validate or normalize fields; a `@property` for a value that depends on other fields; `field(init=False)` set in `__post_init__` only for a value computed once that callers must not pass (a constructor call that passes it raises `TypeError`).
- Raise a specific exception that names the field and the value received; do not log and continue.
- A field computed with `init=False` from mutable fields goes stale when they change: freeze the record, as `Vehicle` does (`python-frozen-dataclasses`), or use a `@property`.
- Keep `__post_init__` free of I/O, the clock and randomness: a record's construction must stay pure and repeatable.
- Data from outside the process is validated where it enters (`pydantic-boundaries` where the repo uses Pydantic); `__post_init__` guards the record's own invariants.

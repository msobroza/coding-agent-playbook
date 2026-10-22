---
id: python-properties
name: Properties
description: "Expose plain attributes, not get_x()/set_x() methods; turn one into a cheap @property when it needs validation or computing; never functools.lru_cache on a method."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 62
tags: [python, design, oop]
---

# Use attributes and properties instead of getters and setters

## Description

Python reads an attribute and a property the same way, so expose plain attributes first. When one later needs validation or computing, turn it into a `@property`, with a setter if callers assign it; callers stay unchanged. Java-style `get_x()` and `set_x()` methods add ceremony and no safety.

## Bad Example

```python
class Circle:
    def __init__(self, radius: float) -> None:
        self._radius = radius  # bypasses the check in set_radius

    def get_radius(self) -> float:
        return self._radius

    def set_radius(self, value: float) -> None:
        if value < 0:
            raise ValueError(f"radius must be non-negative, got {value}")
        self._radius = value

    def get_area(self) -> float:
        return 3.14159 * self._radius**2


circle = Circle(5)
circle.set_radius(10)
area = circle.get_area()
```

## Good Example

```python
import math
from functools import cached_property


class Circle:
    def __init__(self, radius: float) -> None:
        self.radius = radius  # goes through the setter, so validation runs

    @property
    def radius(self) -> float:
        return self._radius

    @radius.setter
    def radius(self, value: float) -> None:
        if value < 0:
            raise ValueError(f"radius must be non-negative, got {value}")
        self._radius = value

    @property
    def area(self) -> float:  # computed on access, read-only
        return math.pi * self._radius**2


circle = Circle(5)
circle.radius = 10
area = circle.area


class SeriesSummary:
    def __init__(self, values: Sequence[float]) -> None:
        self.values = tuple(values)

    @cached_property
    def statistics(self) -> Statistics:  # computed once, then stored on the instance
        return Statistics(mean=fmean(self.values), low=min(self.values), high=max(self.values))
```

## Notes

- Don't wrap every attribute in a property: a pass-through getter and setter is the getter pattern in disguise. Because access looks the same, you can convert a plain attribute later without breaking callers.
- In `__init__`, assign through the setter (`self.radius = radius`), not the backing field, so validation is not bypassed.
- A property without a setter is read-only, which prevents accidental assignment.
- Keep properties cheap: callers expect attribute access to be fast and free of I/O. Deferring an expensive load until first use is design-lazy-loading (design-patterns skill).
- `functools.cached_property` suits an expensive value read many times on a class without `__slots__`: it stores the result in the instance `__dict__`, so a slotted class cannot use it. It is not thread-safe, and the stored value goes stale if its inputs change, so use it on values that do not change.
- Never decorate a method with `functools.lru_cache`: the cache holds a reference to `self`, so it keeps instances alive long after their last use (until they age out of the cache).
- A value derived from a dataclass's fields is a `@property` (`python-data-shapes`); a class that protects an invariant exposes methods instead of its collections (`python-hide-internal-state`).

---
id: design-builder
name: Builder
description: "Reach for a builder only when an object has many optional parts assembled in steps and validated together; its build() validates, copies collections into tuples and returns a frozen product. Otherwise a dataclass with defaults and keyword-only fields is the builder."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 85
tags: [python, design, patterns]
---

# Builder

## Description

A builder separates assembling an object from the object itself: a mutable builder collects the parts step by step, then `build()` checks them together and returns an immutable product. In Python, keyword arguments with defaults already cover most construction, so start there: a dataclass with defaults and keyword-only fields, a classmethod constructor per common shape, and `dataclasses.replace` for variations. Add a builder when construction happens in stages, later parts depend on earlier ones, or the parts must be validated as a whole (tests building large fixtures are a common case).

## Bad Example

```python
@dataclass
class Route:
    name: str
    stops: list[str]  # mutable, and nothing checks the parts together


stops = ["Depot"]
route = Route("Morning", stops)
stops.append("Harbor")  # changes a route that was already handed out
```

## Good Example

```python
@dataclass(frozen=True)
class Route:
    name: str
    stops: tuple[str, ...]
    max_load_kg: int


class RouteBuilder:
    def __init__(self, name: str) -> None:
        self._name = name
        self._stops: list[str] = []
        self._max_load_kg = 1_000

    def add_stop(self, stop: str) -> "RouteBuilder":
        self._stops.append(stop)
        return self

    def with_max_load(self, kilograms: int) -> "RouteBuilder":
        self._max_load_kg = kilograms
        return self

    def build(self) -> Route:
        if len(self._stops) < 2:
            raise InvalidRouteError(f"a route needs two stops, got {self._stops!r}")
        return Route(self._name, tuple(self._stops), self._max_load_kg)


route = RouteBuilder("Morning").add_stop("Depot").add_stop("Harbor").build()
```

## Notes

- `build()` copies every collection into the product (`tuple(self._stops)`); otherwise a later builder call mutates a product that claims to be frozen.
- Make the product a different, frozen type, so code that forgets `build()` and uses the builder fails type checking.
- On Python 3.11 and later, annotate the chaining methods with `typing.Self`; the string forward reference works on every version.
- Keyword arguments first: when every field is known at once, `Route(name=..., stops=(...), max_load_kg=...)` is already a builder; add `Route.single_drop(...)` for a common shape and `dataclasses.replace(route, max_load_kg=500)` for a variation.
- A builder produces a separate product; a fluent interface chains calls on the object itself and returns it, or a new copy of it: design-fluent-interface.
- Stop when every field is known at once and nothing must be checked across fields.

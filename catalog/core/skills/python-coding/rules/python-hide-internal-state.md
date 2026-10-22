---
id: python-hide-internal-state
name: Hide internal state
description: "A class that protects an invariant keeps its storage in underscored fields behind methods, hides internal fields from repr, and exposes what it can do, not how it stores data."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 66
tags: [python, design, oop]
---

# Expose behavior, hide internal state

## Description

A dataclass makes every field public, so callers can reach into a collection and change it behind the object's back, and every caller then depends on how the data is stored. Python has no access modifiers: an underscore prefix (`_accessories`) is the convention for "internal, do not touch". When a class protects an invariant, keep its storage underscored and expose methods for what callers need to do; the representation can then change (a list becomes a set, a dict becomes a database table) without touching a caller.

## Bad Example

```python
@dataclass
class Vehicle:
    plate: str
    accessories: list[Accessory] = field(default_factory=list)


car.accessories.append(Accessory.AIRCO)
car.accessories.append(Accessory.AIRCO)  # a duplicate: nothing enforces uniqueness
if Accessory.NAVIGATION in car.accessories:
    ...  # every caller knows it is a list
```

## Good Example

```python
@dataclass
class Vehicle:
    plate: str
    _accessories: set[Accessory] = field(default_factory=set)
    _internal_id: str = field(default="", repr=False)  # left out of the repr

    def add_accessory(self, accessory: Accessory) -> None:
        self._accessories.add(accessory)

    def has_accessory(self, accessory: Accessory) -> bool:
        return accessory in self._accessories


@dataclass
class VehicleInventory:
    _vehicles: dict[str, Vehicle] = field(default_factory=dict, repr=False)

    def add(self, vehicle: Vehicle) -> None:
        self._vehicles[vehicle.plate] = vehicle

    def find_by_plate(self, plate: str) -> Vehicle | None:  # absence is a normal outcome
        return self._vehicles.get(plate)

    def get_by_plate(self, plate: str) -> Vehicle:  # a required lookup raises
        try:
            return self._vehicles[plate]
        except KeyError:
            raise VehicleNotFoundError(f"no vehicle with plate {plate!r}") from None

    def available_count(self) -> int:
        return len(self._vehicles)
```

## Notes

- Use `field(repr=False)` for internal ids, caches and secrets, so they stay out of logs and error messages.
- A plain record exposes plain attributes (`python-data-shapes`, `python-properties`); a class that protects an invariant exposes methods and keeps the data that the invariant covers underscored.
- When callers need read access to protected state, return a copy or a read-only view (`tuple(self._items)`, a `@property` returning a `frozenset`), never the internal collection itself.
- Code outside the class never reads or writes an underscored attribute; a test that does is testing the representation instead of the behavior.
- Putting the behavior next to the data it uses, instead of callers asking for the data and deciding, is design-tell-dont-ask (design-patterns skill).
- Follow the codebase's absence convention: a `find_` method may return `None`, a required lookup raises a domain not-found error.

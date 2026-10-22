---
id: python-collection-choice
name: Collection choice
description: "Pick a collection by its dominant operation: a set or frozenset built once for membership, a dict index for lookups by key, a list for ordered iteration."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 74
tags: [python, performance, data-structures]
---

# Pick the collection by its dominant operation

## Description

Before choosing a list or a dict, ask what the code does with the collection most often: walk it in order, look items up by key, or test membership. `x in some_list` scans the list from the start on every call, so a membership test or a search inside a loop turns one pass into a pass per item. A `set` or `frozenset` tests membership by hash, and a `dict` finds a record by key the same way. Build them once, before the loop that uses them; the conversion costs one pass and every lookup after it is direct.

## Bad Example

```python
blocked_regions: list[str] = load_blocked_regions()


def billable_fees(fees: Iterable[ShippingFee]) -> list[ShippingFee]:
    return [fee for fee in fees if fee.region not in blocked_regions]  # scans the list per fee


class VehicleRegistry:
    def __init__(self, models: Iterable[VehicleModel]) -> None:
        self._models = list(models)

    def find(self, brand: str, model: str) -> VehicleModel | None:
        for candidate in self._models:  # a linear scan on every lookup
            if candidate.brand == brand and candidate.model == model:
                return candidate
        return None
```

## Good Example

```python
BLOCKED_REGIONS: Final = frozenset(load_blocked_regions())  # built once


def billable_fees(fees: Iterable[ShippingFee]) -> list[ShippingFee]:
    return [fee for fee in fees if fee.region not in BLOCKED_REGIONS]


class VehicleRegistry:
    def __init__(self, models: Iterable[VehicleModel]) -> None:
        self._by_key = {(vehicle.brand, vehicle.model): vehicle for vehicle in models}

    def find(self, brand: str, model: str) -> VehicleModel | None:
        return self._by_key.get((brand, model))  # absence is a normal outcome here


def unique_tags(tags: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(tags))  # drops duplicates, keeps first-seen order
```

## Notes

- Choose by the dominant operation:

  | Dominant operation | Collection |
  | --- | --- |
  | Ordered iteration, position matters | `list` (a `tuple` when it never changes) |
  | Lookup by key or id | `dict` index, built once |
  | Membership test, uniqueness | `set`, or `frozenset` when it never changes |
  | Two or three related values | `tuple`; more, a dataclass (`python-data-shapes`) |
  | A fixed set of valid options | an Enum, never bare strings (`python-enums`) |

- Set members and dict keys must be hashable: strings, numbers, tuples of them, frozen dataclasses. A `frozenset` can itself be a dict key or a set member.
- `list(set(items))` loses the order; `dict.fromkeys`, as in `unique_tags`, keeps it.
- A lookup that returns `None` for a missing key follows the absence convention; a key that must exist is indexed directly (`python-optional-keys`).
- Start with the simplest collection that fits, and change it when the dominant operation changes: a list that starts being searched becomes a dict index.
- Large numeric data belongs in arrays or frames, not lists of floats (the ml-data skill).

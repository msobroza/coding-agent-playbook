---
id: design-name-for-intent
name: Names that match intent
description: "Name sibling methods and classes alike, use the matching dunder, and make every verb match what the method does."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: smells
priority: 62
tags: [python, design, naming]
---

# Names that match intent

## Description

In a design review, names show where the structure disagrees with itself. Sibling classes that do the same job under different method names or signatures (smell id asymmetric-names) force callers to branch per class and rule out a shared Protocol. A verb that promises one thing while the method does another (smell id misleading-verb) makes callers reason from the name and get the wrong cost or effect. Vague names (`data`, `process`, `handle`) and names that repeat the type (`user_list`) hide the role a value plays.

## Bad Example

```python
class VehicleModelInfo:
    def get_formatted_info(self) -> str: ...


class Vehicle:
    def to_display_string(self) -> str: ...  # same job, another name


class Order:
    def create_line_item(self, name: str, quantity: int, price: Money) -> None:
        self.items.append(LineItem(name, quantity, price))  # appends, creates nothing


def process(data: list[Reading]) -> float: ...


def notify(user_list: list[User]) -> None: ...
```

## Good Example

```python
class VehicleModelInfo:
    def __str__(self) -> str: ...


class Vehicle:
    def __str__(self) -> str: ...


class Order:
    def add_line_item(self, item: LineItem) -> None:
        self.items.append(item)


def mean_soil_moisture(readings: list[Reading]) -> float: ...


def notify(recipients: list[User]) -> None: ...
```

## Notes

- Alike things are named alike: one name and one signature for the same operation across related classes, and the matching dunder (`__str__`, `__len__`, `__iter__`) where Python has one.

| Verb | Callers expect |
| --- | --- |
| `get_` | a cheap read with no side effects |
| `fetch_`, `load_` | I/O: a network call or a file read |
| `create_`, `make_` | a new object, returned |
| `add_` | an item put into a collection |
| `ensure_` | a state made true, idempotently |
| `is_`, `has_` | a bool, and no mutation |

- When the verb and the behavior disagree, rename to the behavior or change the behavior to match the name; when callers rely on the wrong reading, it is a design finding, not only a clarity one.
- Choosing distinctive, searchable names in the first place is python-coding's python-meaningful-names; this rule is the review angle. Names shadowing builtins belong to python-coding's python-idioms, and the domain vocabulary shared with the experts is python-architecture's arch-ubiquitous-language.

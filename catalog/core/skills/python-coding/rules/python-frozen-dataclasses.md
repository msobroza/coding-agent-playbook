---
id: python-frozen-dataclasses
name: Frozen dataclasses
description: "Freeze value records with frozen=True, give them tuple and frozenset fields, and copy every collection passed in, because frozen is shallow."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 63
tags: [python, design, data]
---

# Freeze value records, and remember frozen is shallow

## Description

`@dataclass(frozen=True)` makes assigning a field raise `FrozenInstanceError`, and it generates `__hash__`, so instances work as dict keys and set members. It only blocks attribute assignment: a `list` field can still change in place, through the record or through any caller that kept the original list. Give a frozen dataclass `tuple` and `frozenset` fields, and copy every collection passed in, including from a builder into the object it builds.

## Bad Example

```python
@dataclass(frozen=True)
class Basket:
    items: list[Item]  # frozen, yet the list itself stays mutable


draft_items = [apple, pear]
basket = Basket(items=draft_items)  # shares the caller's list
draft_items.append(melon)  # basket.items changes too
basket.items.clear()  # and so does any code holding draft_items
hash(basket)  # TypeError: unhashable type: 'list'
```

## Good Example

```python
@dataclass(frozen=True)
class Basket:
    items: tuple[Item, ...]
    tags: frozenset[str] = frozenset()

    @property
    def total_cents(self) -> int:
        return sum(item.price_cents for item in self.items)


basket = Basket(items=tuple(draft_items))  # a copy: later edits to draft_items cannot leak in
```

## Notes

- Freeze a record when nothing changes it after creation: value objects (equal fields mean interchangeable values), dict keys and set members, and data shared across threads.
- To change a frozen record, build a new one with `dataclasses.replace(basket, items=new_items)`.
- A frozen dataclass cannot assign fields in `__post_init__`, so `field(init=False)` set there raises. Prefer a `@property` for a value derived from other fields, or `field(default_factory=...)` for an independent default; use `object.__setattr__(self, "name", value)` inside `__post_init__` only when a value derived from other fields must be stored (for example to be part of the hash).
- Copy at the boundary: convert incoming lists and sets with `tuple(...)` and `frozenset(...)` in the code that builds the record.
- Validating fields after construction is `python-dataclass-post-init`; plain records and their defaults are `python-data-shapes`.

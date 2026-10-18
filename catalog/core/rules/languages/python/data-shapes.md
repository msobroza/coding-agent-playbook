---
id: python-data-shapes
name: Data shapes
description: "Model records as dataclasses, not string dicts or parallel lists; freeze them with tuple fields; return at most three values; name magic constants."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
priority: 44
tags: [python, design, data]
---

# Python data shapes

A value with a name and a type tells the next reader what it holds and lets the type checker catch a typo; a dict of strings, or two lists kept in step, does neither. The house style already requires typed records between layers. This reference covers how to shape them.

## Records

- Don't use a dict of strings as a stand-in for a record type. When three or more fields belong together, give them a dataclass.
- Never keep parallel lists indexed together (`names[i]` beside `prices[i]`); zip them into one list of records.
- Return at most three values as a tuple. Beyond that, return a dataclass or a `NamedTuple`, so callers read fields by name.
- Compute derived values with `@property` instead of storing a copy that can go stale.
- For a dataclass with many small instances (one per sensor reading or invoice line), add `slots=True`: each instance takes less memory, and assigning a misspelled attribute raises instead of adding a new one.

## Frozen is shallow

`frozen=True` only blocks attribute assignment: a `list` field can still change in place. Give a frozen dataclass `tuple` and `frozenset` fields, and copy every collection passed in, including from a builder into the object it builds.

```python
@dataclass(frozen=True)
class Basket:
    items: tuple[Item, ...]

    @property
    def total_cents(self) -> int:
        return sum(item.price_cents for item in self.items)


basket = Basket(items=tuple(draft_items))  # a copy: later edits to draft_items cannot leak in
```

## Constants and settings

- Name domain magic values as `UPPER_CASE` module constants annotated `Final`, beside the code that uses them: `MAX_LINE_ITEMS: Final = 50`.
- Values that change per environment (URLs, credentials, feature flags, deployment-tuned timeouts) live in the single settings object, never in constants.

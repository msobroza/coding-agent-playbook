---
id: python-data-shapes
name: Data shapes
description: "Model records as dataclasses, not hand-written classes, string dicts or parallel lists; default_factory for mutable defaults; at most three tuple values; name magic constants."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 60
tags: [python, design, data]
---

# Use dataclasses for data containers

## Description

A value with a name and a type tells the next reader what it holds and lets the type checker catch a typo; a dict of strings, or two lists kept in step, does neither. For a class that mainly holds data, `@dataclass` generates `__init__`, `__repr__` and `__eq__` from the field annotations, so there is no boilerplate to get wrong and the intent is plain. The house style already requires typed records between layers; this rule covers how to shape them.

## Bad Example

```python
class User:
    def __init__(self, name: str, email: str, age: int) -> None:
        self.name = name
        self.email = email
        self.age = age

    def __repr__(self) -> str:
        return f"User(name={self.name!r}, email={self.email!r}, age={self.age})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return (self.name, self.email, self.age) == (other.name, other.email, other.age)

    def __hash__(self) -> int:  # a mutable object that hashes: a dict key that can change
        return hash((self.name, self.email, self.age))


names = ["Widget", "Gadget"]  # parallel lists: names[i] belongs to prices[i]
prices = [Decimal("1.00"), Decimal("2.50")]
```

## Good Example

```python
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class User:
    name: str
    email: str
    age: int


@dataclass
class Cart:  # a builder filled in place inside one layer
    # items: list[Item] = []  raises ValueError when the class is defined
    items: list[Item] = field(default_factory=list)  # a fresh list per instance


@dataclass(frozen=True)  # passed between layers, so frozen
class Order:
    items: tuple[Item, ...]
    customer_id: str
    discount: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:  # derived on access, so it never goes stale
        return sum((item.price for item in self.items), Decimal("0")) * (1 - self.discount)


@dataclass(slots=True)  # many small instances: less memory, typo'd attributes raise
class Reading:
    sensor_id: str
    celsius: float
```

## Notes

- Don't use a dict of strings as a stand-in for a record type. When three or more fields belong together, give them a dataclass; replace a manual `__init__` on a data holder with `@dataclass`.
- Never keep parallel lists indexed together (`names[i]` beside `prices[i]`); zip them into one list of records. A `zip` joining related lists is the sign to look for.
- Return at most three values as a tuple. Beyond that, return a dataclass or a `NamedTuple`, so callers read fields by name instead of by position.
- Compute derived values with `@property` instead of storing a copy that can go stale; an attribute updated everywhere its inputs change is the smell.
- For a dataclass with many small instances (one per sensor reading or invoice line), add `slots=True`: each instance takes less memory, and assigning a misspelled attribute raises instead of adding a new one.
- A mutable default needs `field(default_factory=...)`; give a non-trivial default a named factory function rather than a lambda.
- Use a dataclass for internal data; validate untrusted input with Pydantic at the boundary (`pydantic-boundaries`) where the repo uses it.
- Only where a library takes or returns a dict (a JSON payload passed through, a client's keyword dict) does a value stay a dict, typed with a `TypedDict` at that edge; it becomes a record before it travels further.
- Name domain magic values, semantic ones included (`HIDDEN = "O"`), as `UPPER_CASE` module constants annotated `Final`, beside the code that uses them: `MAX_LINE_ITEMS: Final = 50`.
- Values that change per environment (URLs, credentials, feature flags, deployment-tuned timeouts) live in the single settings object, never in constants.
- Freezing a record is `python-frozen-dataclasses`; validating fields in `__post_init__` is `python-dataclass-post-init`.
- choosing-a-data-shape.md routes the choice between dataclass, NamedTuple, TypedDict, Pydantic, Enum and NewType.

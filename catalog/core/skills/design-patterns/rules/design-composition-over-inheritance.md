---
id: design-composition-over-inheritance
name: Composition over inheritance
description: "Reuse behavior by holding a collaborator and delegating to it; inherit only where every subclass substitutes, and configure instances when subclasses differ only in values."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 47
tags: [python, design, oop]
---

# Composition over inheritance

## Description

Inheritance is the strongest coupling there is: a subclass depends on every detail of its base, and a change to the base ripples into subclasses that never asked for it. Composition, where an object holds the objects it needs, combines behaviors freely and lets each part change on its own. Subclass when behavior changes and every subclass can stand in for its base; when only values change, configure instances instead.

## Bad Example

```python
class Bird:
    def move(self) -> str:
        return "flying"


class Penguin(Bird):  # penguins cannot fly, yet Penguin "is a" flying Bird
    def move(self) -> str:
        return "swimming"


class ArchivingBlobStore(LocalBlobStore):  # inherits every method it never needed
    def save_invoice(self, invoice: Invoice) -> None: ...


class Goblin(Monster):  # a subclass that only changes values
    def __init__(self) -> None:
        super().__init__(health=100, speed=2)
```

## Good Example

```python
class Movement(Protocol):
    def move(self) -> str: ...


class Flying:
    def move(self) -> str:
        return "flying"


class Swimming:
    def move(self) -> str:
        return "swimming"


class Bird:
    def __init__(self, movement: Movement) -> None:
        self._movement = movement

    def move(self) -> str:
        return self._movement.move()


sparrow = Bird(Flying())
penguin = Bird(Swimming())


class InvoiceArchive:  # holds the store it needs
    def __init__(self, store: BlobStore) -> None:
        self._store = store

    def save(self, invoice: Invoice) -> None:
        self._store.put(f"invoices/{invoice.number}.json", invoice.to_json())


goblin = Monster(health=100, speed=2)  # configuration, not a subclass
troll = Monster(health=200, speed=1)
```

## Notes

- Prefer composition over inheritance: keep a collaborator in an attribute and delegate to it.
- Inherit only when every subclass can stand in for its base everywhere the base is used (`design-liskov-substitution`).
- Use a mixin only for a small piece of behavior that is independent of the rest of the class; a mixin that reads attributes its host must provide hides a dependency.
- Framework base classes (`BaseModel`, `BaseSettings`, `DeclarativeBase`, Django views), exception hierarchies and documented ABC extension points are normal subclassing; the house-style rule to wrap rather than subclass a third-party class does not apply to them.
- The composition pattern: extract behavior duplicated across subclasses into small classes behind a Protocol, and hold a list of them: an `Employee` whose `pay_sources: list[PaySource]` each provide `compute_pay_cents() -> int`, summed by the employee and wired in one place.
- Keep hierarchies shallow: three or more levels spread one behavior over many files.
- Review smell ids: value-only-subclass, inheritance-for-reuse.

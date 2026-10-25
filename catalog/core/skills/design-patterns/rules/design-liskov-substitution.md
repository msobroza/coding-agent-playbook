---
id: design-liskov-substitution
name: Liskov substitution
description: "A subtype accepts at least what its base accepts, promises at least what it promises, and raises only the errors its contract names."
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 48
tags: [python, design, solid]
---

# Liskov substitution

## Description

Objects of a subtype must be substitutable for objects of their base type without breaking the program. Code written against an abstraction relies on its contract, so every implementation, subclass or Protocol implementer, must honor the same preconditions and postconditions and raise no surprising exceptions. Violations show up as subclasses that weaken guarantees or demand more of their callers.

## Bad Example

```python
class Bird:
    def fly(self) -> None: ...


class Sparrow(Bird):
    def fly(self) -> None: ...


class Penguin(Bird):
    def fly(self) -> None:
        # Breaks the Bird contract: callers expect every Bird to fly
        raise NotImplementedError("Penguins cannot fly")


def migrate(birds: list[Bird]) -> None:
    for bird in birds:
        bird.fly()  # fails when a Penguin is in the list


migrate([Sparrow(), Penguin()])  # runtime error
```

## Good Example

```python
class Bird(Protocol):
    def move(self) -> None: ...


class Sparrow:
    def move(self) -> None:
        self._fly()

    def _fly(self) -> None: ...


class Penguin:
    def move(self) -> None:
        self._swim()

    def _swim(self) -> None: ...


def relocate(birds: list[Bird]) -> None:
    for bird in birds:
        bird.move()  # works for any Bird implementation


relocate([Sparrow(), Penguin()])
```

## Notes

- The contract has three parts: a subtype accepts at least what its base accepts (rejecting values the parent accepts is a violation), promises at least what its base promises, and raises only the errors the base contract names.
- A subclass method that raises `NotImplementedError`, or base code that inspects the type of `self`, shows the hierarchy is wrong: split the interface (`design-interface-segregation`), or switch to composition (`design-composition-over-inheritance`).
- The Rectangle/Square case is the classic trap: a `Square` subclass that refuses independent width and height changes breaks every caller that resizes a `Rectangle`.
- `@runtime_checkable` lets `isinstance` confirm that method names exist, not that the behavior honors the contract.
- Substitution is the test a subclass must pass, not a reason to avoid subclassing.

---
id: python-protocols
name: Protocols
description: "Type a seam with a role-named Callable alias for one behavior or a small Protocol in the consuming module; keep an ABC for shared implementation or a hook the base calls."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 61
tags: [python, design, typing]
---

# Prefer small Protocols to abstract base classes at a seam

## Description

A `typing.Protocol` gives structural typing: duck typing that the type checker verifies. A class satisfies a Protocol by having the methods it names, without inheriting from it or even importing it, so third-party classes and test fakes fit too. An abstract base class only accepts its own subclasses. Pick the lightest type that describes what the consumer needs:

- a role-named `Callable` alias when the consumer uses one behavior;
- a small Protocol, named for the role (`InvoiceSender`, not `IEmailService`) and declared in the consuming module, when it uses several methods;
- an ABC when subclasses share implementation, or must override a hook the base class calls.

## Bad Example

```python
import json
from abc import ABC, abstractmethod


class Serializable(ABC):  # every class must inherit to qualify
    @abstractmethod
    def to_json(self) -> str: ...


class User(Serializable):
    def __init__(self, name: str) -> None:
        self.name = name

    def to_json(self) -> str:
        return json.dumps({"name": self.name})


def save(obj: Serializable) -> None:  # a library class with to_json() is rejected
    store.write(obj.to_json())
```

## Good Example

```python
import json
from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable


class Serializable(Protocol):  # declared where it is consumed
    def to_json(self) -> str: ...


class User:  # qualifies by shape: no import of Serializable, no base class
    def __init__(self, name: str) -> None:
        self.name = name

    def to_json(self) -> str:
        return json.dumps({"name": self.name})


class InvoiceSender(Protocol):  # a role, with only the methods its consumer calls
    def send(self, invoice: Invoice) -> None: ...
    def is_reachable(self, customer: CustomerId) -> bool: ...


Clock = Callable[[], datetime]  # one behavior: a Callable alias is enough


@runtime_checkable
class Closable(Protocol):
    def close(self) -> None: ...


def release(resource: object) -> None:
    if isinstance(resource, Closable):  # checks the name exists, not the signature
        resource.close()
```

An ABC stays the right tool when it carries shared code and requires overrides:

```python
from abc import ABC, abstractmethod
from collections.abc import Sequence


class Exporter(ABC):
    def export(self, rows: Sequence[Row]) -> str:  # shared implementation
        return "\n".join([self._header(), *(self._line(row) for row in rows)])

    @abstractmethod
    def _header(self) -> str: ...

    @abstractmethod
    def _line(self, row: Row) -> str: ...
```

## Notes

- Choose ABC for shared implementation (state the base class holds), an intended hierarchy, or an error at instantiation when an override is missing; choose a Protocol for code you cannot modify, small separate contracts and loose coupling, accepting the error at the call site (from the type checker).
- `@runtime_checkable` lets `isinstance` confirm that the method names exist, not that their signatures or return types match, so it can report a false match: use it as a coarse guard only.
- A Protocol can also declare properties, attributes and class methods.
- Add the abstraction only at a real seam (an external system, a test fake, two or more implementations); whether to invert a dependency at all is design-dependency-inversion (design-patterns skill) and arch-ports (python-architecture skill). A working ABC hierarchy stays: rewriting it as Protocols needs one of those reasons.
- Passing the collaborator in is `python-dependency-injection`; repository ports belong to the python-architecture skill.

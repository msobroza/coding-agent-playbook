---
id: design-interface-segregation
name: Interface segregation
description: "Let each consumer depend on a small Protocol with only the methods it calls; split an interface when implementers stub methods or callers use separate halves."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 49
tags: [python, design, solid]
---

# Interface segregation

## Description

Clients should not be forced to depend on methods they do not use. Prefer several small, purpose-specific `Protocol`s to one large interface that bundles unrelated capabilities. This lowers coupling, simplifies testing and fits Python's structural typing: an implementation provides only the methods it really has.

## Bad Example

```python
class Worker(Protocol):
    def work(self) -> None: ...
    def eat(self) -> None: ...
    def sleep(self) -> None: ...


class Robot:
    def work(self) -> None: ...

    def eat(self) -> None:
        raise NotImplementedError  # robots do not eat: a stub to satisfy Worker

    def sleep(self) -> None:
        raise NotImplementedError


def assign_task(worker: Worker) -> None:
    worker.work()
```

## Good Example

```python
class Workable(Protocol):
    def work(self) -> None: ...


class Feedable(Protocol):
    def eat(self) -> None: ...


class Robot:
    def work(self) -> None: ...


class Human:
    def work(self) -> None: ...

    def eat(self) -> None: ...


def assign_task(worker: Workable) -> None:
    worker.work()  # depends only on what it needs


def lunch_break(worker: Feedable) -> None:
    worker.eat()


assign_task(Robot())
assign_task(Human())
lunch_break(Human())
```

## Notes

- Split a Protocol or ABC when implementers leave methods stubbed out or raising `NotImplementedError`, or when its callers use two separate halves of it. Do not split one before either sign appears.
- Do not split a cohesive interface into one-method Protocols for symmetry; a Protocol past four or five methods, or callers that need different subsets, is the usual point to split.
- Splitting Protocols splits the interface, not the implementation: a `trade(engine, strategy)` function takes a `TradingEngine` (prices, buy, sell) and a `TradingStrategy` (should_buy, should_sell) instead of one large Protocol, the exchange clients and the strategy satisfy them without inheriting from either, and regrouping the Protocols needs no change to the implementing classes.
- Name a Protocol by the capability its consumer needs (`Readable`, `Writable`), not by the entity (`Database`), when roles differ; one class may satisfy several.
- How to declare a Protocol and where it lives is python-protocols in the python-coding skill.

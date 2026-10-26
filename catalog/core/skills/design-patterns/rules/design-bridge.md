---
id: design-bridge
name: Bridge
description: "When two independent axes of variation produce a class for every combination, inject one axis into the other as a Callable alias or a small Protocol, so a new variant on either axis is one new function or class."
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 92
tags: [python, design, patterns]
---

# Bridge

## Description

When behavior varies along two independent axes, such as a report's format and where it is delivered, writing one class per combination multiplies: a new format needs one class per destination, and a new destination one class per format. The two axes are fused at the concrete level, so neither can change on its own. The bridge connects them through an abstraction instead. In Python the lightest bridge is a function that takes one collaborator per axis, each typed with a role-named `Callable` alias; the entry point chooses one of each.

## Bad Example

```python
class CsvEmailStockTake:
    def publish(self, lines: Sequence[StockLine], day: date) -> None: ...


class CsvFolderStockTake:
    def publish(self, lines: Sequence[StockLine], day: date) -> None: ...


class JsonEmailStockTake:
    def publish(self, lines: Sequence[StockLine], day: date) -> None: ...


class JsonFolderStockTake:  # a new format or destination adds a whole row of classes
    def publish(self, lines: Sequence[StockLine], day: date) -> None: ...
```

## Good Example

```python
Render = Callable[[Sequence[StockLine]], bytes]
Deliver = Callable[[str, bytes], None]  # (file name, content)


def publish_stock_take(
    lines: Sequence[StockLine], render: Render, deliver: Deliver, day: date
) -> None:
    deliver(f"stock-take-{day.isoformat()}", render(lines))


# The entry point picks one function per axis.
publish_stock_take(lines, render=render_csv, deliver=mailer.send_attachment, day=today)
```

A new format is one new `Render` function; a new destination is one new `Deliver` function, or a bound method of an object that holds its connection.

## Notes

- Promote one side to a Protocol when it carries state or needs several methods. For payment methods and authorization methods, a `PaymentProcessor` Protocol with `pay(payable, authorize)` takes any authorization function, so any processor works with any authorization method.
- When to stop: higher-order functions with `Callable` aliases, or bound methods, are the default bridge. Wire everything with `functools.partial` only when the dependencies must really be composed at startup, since partial chains hide what runs. Keep classes when both sides hold meaningful state or several methods, and an ABC only when the base must share implementation.
- Bridge versus strategy: a strategy makes one axis interchangeable; a bridge connects two axes that vary independently (design-strategy).
- Bridge versus adapter: an adapter fits an existing interface after the fact (design-adapter); a bridge separates the axes by design, before the classes multiply.
- The bridge uses dependency injection as its mechanism; wiring the chosen functions is the python-architecture skill's composition root.
- Not when one axis never varies: inject the other one only.
- The walkthrough from an ABC bridge to Protocols, functions, bound methods and partial: see bridge-progression.md.

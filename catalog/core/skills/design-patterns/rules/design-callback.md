---
id: design-callback
name: Callback
description: "When a class must tell its caller that something happened, take a role-named Callable with a named no-op default, or a list of handlers, instead of hard-coding the reaction."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 80
tags: [python, design, patterns]
---

# Callback

## Description

Functions are values: they can be stored, passed and called later. A callback is a function handed to another function or class, which calls it when an event happens without knowing what it does. Use one when a unit fires an event (a job finishes, a button is clicked, an import fails) and the reaction belongs to its caller. The unit stays reusable, the reaction can change without editing it, and a test passes a recording function. When several reactions must run, keep a list of handlers: it is a lightweight observer without a base class or subscription machinery.

## Bad Example

```python
class ExportJob:
    def __init__(self, analytics: AnalyticsClient) -> None:
        self._analytics = analytics

    def run(self, rows: Sequence[Row]) -> int:
        written = write_rows(rows)
        # The job hard-codes every reaction; a new one means editing it.
        logger.info("export finished: %d rows", written)
        self._analytics.track("export_finished", written)
        return written
```

## Good Example

```python
OnFinished = Callable[[int], None]


def ignore_finished(written: int) -> None:
    """The default reaction: none."""


class ExportJob:
    def __init__(self, on_finished: OnFinished = ignore_finished) -> None:
        self._on_finished = on_finished

    def run(self, rows: Sequence[Row]) -> int:
        written = write_rows(rows)
        self._on_finished(written)
        return written
```

Several reactions: keep a list of handlers and call each one.

```python
class ExportJob:
    def __init__(self) -> None:
        self._finished_handlers: list[OnFinished] = []

    def add_finished_handler(self, handler: OnFinished) -> None:
        self._finished_handlers.append(handler)

    def run(self, rows: Sequence[Row]) -> int:
        written = write_rows(rows)
        for handler in self._finished_handlers:
            handler(written)
        return written


def log_finished(written: int) -> None:
    logger.info("export finished: %d rows", written)
```

## Notes

- A named no-op default avoids `None` checks and reads better than a lambda that returns a lambda in a `default_factory`.
- Callbacks created in a loop capture the variable, not its value: every `lambda: notify(zone)` sees the last `zone`. Bind the value with a default argument (`lambda zone=zone: notify(zone)`) or a builder function that returns the closure.
- A group of handler functions can be passed as a tuple and typed as `Iterable[PostProcessor]`, so the receiver cannot mutate it: `handle_payment(amount_cents, (log_payment, send_receipt))`.
- When reactions multiply across modules and should be keyed by what happened, return event objects and let one dispatcher call the handlers: design-domain-events is the heavier form.
- Stop at one fixed reaction that never changes: call it directly.

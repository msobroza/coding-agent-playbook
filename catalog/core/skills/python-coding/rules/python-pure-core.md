---
id: python-pure-core
name: Pure core
description: "Keep business logic free of I/O, clocks, randomness and hidden mutation; perform effects in a thin outer shell."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 49
tags: [python, design, testability]
---

# Prefer pure functions without side effects

## Description

A pure function returns the same output for the same input and has no side effects: it mutates nothing outside itself and does no I/O. Logic that depends only on its arguments is tested with plain input-to-output assertions, reused anywhere, and safe to cache or run in parallel. Keep domain and calculation code pure, and let a thin outer shell gather the inputs, call it, and carry out the effects ("functional core, imperative shell"). Small scripts and notebooks may stay imperative.

## Bad Example

```python
total_processed = 0


def process_item(item: Item) -> Result:
    global total_processed
    total_processed += 1  # side effect: module state
    item.status = ItemStatus.PROCESSED  # side effect: mutates its argument
    log_to_file(item)  # side effect: I/O
    return calculate_result(item)


def weekend_discount(price: Decimal) -> Decimal:
    if datetime.now().weekday() >= calendar.SATURDAY:  # hidden input: the wall clock
        return price * Decimal("0.10")
    return Decimal("0")
```

## Good Example

```python
import calendar
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Item:
    status: ItemStatus
    quantity: int
    unit_price: Decimal


def calculate_result(item: Item) -> Result:  # pure: depends only on its argument
    return Result(value=item.quantity * item.unit_price, category=categorize(item))


def weekend_discount(price: Decimal, today: date) -> Decimal:  # the caller supplies the date
    return price * Decimal("0.10") if today.weekday() >= calendar.SATURDAY else Decimal("0")


def mark_processed(item: Item) -> Item:  # a new value instead of a mutation
    return replace(item, status=ItemStatus.PROCESSED)


def main() -> None:  # the imperative shell reads the clock and does the I/O
    today = date.today()
    results = [calculate_result(item) for item in load_items()]
    discounts = [weekend_discount(result.value, today) for result in results]
    save_results(results, discounts)
```

## Notes

- Inputs arrive as arguments: a domain function never reads the wall clock, randomness (`random`, `uuid4()`), environment variables or files on its own. Pass the value in, or pass a clock (`now: Callable[[], datetime]`), an id factory or a `random.Random` instance when it needs fresh ones.
- When one function reads input, computes, and presents the result, split it so the computing step runs without patching anything; a function with an unavoidable effect takes the collaborator (a repository) as a parameter and calls the pure step first.
- Domain classes contain no `print()`, `input()`, network, file or mail I/O; render for humans with `__str__`, `__format__` or a presenter, and keep `input()` in the entry point. `__init__` does no I/O, printing or registration, and starts no threads or tasks.
- Don't mutate arguments or module-level state, and never share state through a `global` statement; return a new value (`dataclasses.replace(...)`, a new list). When in-place mutation is the contract, the name says so (`sort_in_place`, `apply_discount_to`) and it returns `None`.
- A request-scoped `ContextVar` is an explicit exception to "no module-level state".
- Test the core with direct argument-to-return assertions and fixed dates, no mocks. Freeze-time libraries are for characterizing legacy code that reads the clock directly (`datetime.now(timezone.utc)`), not a substitute for passing a clock in new code.

---
id: python-comprehensions
name: Comprehensions
description: "Build a list, dict or set with a comprehension when each element is one simple transform or filter; keep a loop for side effects, raises or more than two clauses."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 76
tags: [python, performance, loops]
---

# Build collections with comprehensions

## Description

Measure first: give up clarity for speed only on a path that a profile (`cProfile`, or the project's own benchmark) shows to be hot, and everywhere else write the construct the next reviewer understands fastest. For building a collection that is usually a comprehension: when every element comes from one simple transform or filter of the source, `[invoice.id for invoice in invoices if invoice.is_overdue]` states the result in one line, where an empty list and an `append` loop make the reader run the loop in their head. Keep a plain `for` loop when the body has side effects or raises, or when the comprehension would need more than two `for`/`if` clauses in total.

## Bad Example

```python
overdue_ids: list[str] = []
for invoice in invoices:
    if invoice.is_overdue:
        overdue_ids.append(invoice.id)

region_names: dict[str, str] = {}
for region in regions:
    region_names[region.code] = region.name.title()
```

## Good Example

```python
overdue_ids = [invoice.id for invoice in invoices if invoice.is_overdue]
region_names = {region.code: region.name.title() for region in regions}
active_customers = {order.customer_id for order in orders if order.is_open}

ABSOLUTE_ZERO_CELSIUS: Final = -273.15

accepted: list[Reading] = []
for reading in readings:  # a loop: the body raises and records
    if reading.celsius < ABSOLUTE_ZERO_CELSIUS:
        raise SensorFaultError(
            f"sensor {reading.sensor_id} read {reading.celsius} C, "
            f"below absolute zero ({ABSOLUTE_ZERO_CELSIUS} C)"
        )
    accepted.append(reading)
```

## Notes

- Dict comprehensions `{key: value for ...}` and set comprehensions `{item for ...}` follow the same rule.
- Count the clauses: `[cell for row in grid for cell in row if cell.is_alive]` has three (two `for`, one `if`), past the limit; write the loop, or extract a named generator function that yields the cells.
- A comprehension that wraps over several lines is a hint that a loop or a helper function reads better.
- Never use a comprehension for its side effects (`[print(item) for item in items]`); it builds a list nobody reads. Write the loop.
- When the result is consumed once by `sum`, `any`, `all`, `min`, `max` or `str.join`, pass a generator expression instead (`python-generators`).
- In NumPy or pandas code, a comprehension still runs one Python step per element; use whole-array operations there (the ml-data skill).

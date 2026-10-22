---
id: python-generators
name: Generators
description: "Stream large or single-pass data with generator functions and generator expressions; make a list only when you walk it twice or need len or indexing."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 77
tags: [python, performance, memory]
---

# Stream single-pass data with generators

## Description

A list holds every element in memory at once; a generator produces one element at a time, when the consumer asks for it. When the data is large, or is read once from start to end, a generator keeps memory flat and starts producing results before the whole input is read. Pass a generator expression straight to `sum`, `any`, `all`, `min`, `max` or `str.join`, and write a generator function (`yield`) for a pipeline over a file or stream too large to hold.

## Bad Example

```python
def read_readings(path: Path) -> list[Reading]:
    with path.open(encoding="utf-8") as lines:
        return [parse_reading(line) for line in lines]  # the whole file in memory


total_cents = sum([fee.cents for fee in shipping_fees])  # an intermediate list
```

## Good Example

```python
def read_readings(path: Path) -> Iterator[Reading]:
    with path.open(encoding="utf-8") as lines:
        for line in lines:  # a file object already yields one line at a time
            yield parse_reading(line)


def faulty_sensors(readings: Iterable[Reading]) -> Iterator[str]:
    return (r.sensor_id for r in readings if r.celsius < ABSOLUTE_ZERO_CELSIUS)


total_cents = sum(fee.cents for fee in shipping_fees)  # no list on the way
has_overdue = any(invoice.is_overdue for invoice in invoices)  # stops at the first hit
```

## Notes

- A generator can be consumed only once. Make a list when you walk the data more than once, or need `len`, indexing or slicing.
- Yield typed records (a dataclass or NamedTuple), not dicts, so each stage of the pipeline is checked (`python-data-shapes`).
- A generator function that opens a file keeps it open until the consumer finishes or closes the generator; consume it fully, or close it with `contextlib.closing`.
- A generator expression passed as the only argument needs no extra parentheses: `sum(x.cents for x in fees)`.
- For async sources, an async generator streams the same way (`python-async-generators`).

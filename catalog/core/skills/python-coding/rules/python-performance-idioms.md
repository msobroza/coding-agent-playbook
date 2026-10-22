---
id: python-performance-idioms
name: Performance idioms
description: "Write clear code first and fast code where a profile says so: comprehensions, generators, set and dict lookups, str.join, and .get only for optional keys."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 79
tags: [python, performance]
---

# Python performance idioms

Most of these idioms make code faster and easier to read at once. When speed and readability pull apart, readability wins unless a measurement says otherwise.

## Measure first

Give up clarity for speed only on a path that a profile (`cProfile`, or the project's own benchmark) shows to be hot. Everywhere else, write the construct the next reviewer understands fastest.

## Building collections

- Use a comprehension when every element comes from one simple transform or filter of the source.
- Use a plain `for` loop when the body has side effects or raises a domain error, or when a comprehension would need more than two `for`/`if` clauses in total.

```python
overdue_ids = [invoice.id for invoice in invoices if invoice.is_overdue]

for reading in readings:  # a loop: the body raises and records
    if reading.celsius < ABSOLUTE_ZERO_CELSIUS:
        raise SensorFaultError(reading.sensor_id)
    accepted.append(reading)
```

## One pass over large inputs

- Pass a generator expression straight to `sum`, `any`, `all`, `min`, `max` or `"".join`: `sum(fee.cents for fee in shipping_fees)` builds no list on the way.
- Write a generator function (`yield`) for a pipeline over a file or stream too large to hold in memory.
- Make a list only when you walk it more than once, or need `len` or indexing.

## Lookups

- Before a loop that tests membership, build a `set` or `frozenset` once; testing against a list scans it on every pass.
- To find records by key, index them in a dict once (`{invoice.id: invoice for invoice in invoices}`) instead of searching a list for each one.
- To drop duplicates and keep the original order, use `list(dict.fromkeys(items))`; `list(set(items))` loses the order.

```python
blocked = frozenset(settings.blocked_regions)  # built once, outside the loop
billable = [fee for fee in shipping_fees if fee.region not in blocked]
```

## Optional keys only

- `.get(key, default)`, `collections.defaultdict` and `setdefault` are for keys whose absence is a normal case: an optional field, the first count of a tally.
- Index a required key directly (`payload["invoice_id"]`), or better, parse the payload into a typed record where it enters the program, so a missing key fails there with a clear error instead of travelling on as a made-up default (`python-error-handling`). Never chain `.get(key, {})` calls to dig into nested data that must be present.

## Strings and arrays

- Assemble a string from many parts with `"".join(parts)`, not `+=` inside a loop. An f-string is the right tool for a fixed handful of pieces.
- In NumPy or pandas code, a comprehension still runs one Python step per element. Use whole-array operations there instead.

---
id: ml-loc-assignment
name: Assignment with .loc
description: "Write into a pandas frame with one .loc or .iloc indexer, never chained indexing, and copy a subset explicitly when it is meant to be separate."
scope: scoped
globs:
  - "**/*.py"
  - "**/*.ipynb"
applies_if:
  any_ml_stack: ["pandas"]
section: mutation
priority: 24
tags: [ml, pandas, indexing]
---

# Assign with .loc, never with chained indexing

## Description

`frame[mask]["col"] = value` and `frame["col"][mask] = value` are two operations: the first creates a new object, the second mutates that temporary. Under copy-on-write the original frame is never modified, and pandas emits a `ChainedAssignmentError` warning; without copy-on-write the outcome depends on internal view and copy details and produces the `SettingWithCopyWarning`. Use a single `.loc[row_indexer, col_indexer] = value` so the write targets the frame itself.

## Bad Example

```python
orders = load_orders(path)

# Chained assignment: writes to a temporary, `orders` is unchanged
orders[orders["status"] == "pending"]["priority"] = "high"
orders["priority"][orders["weight_kg"] > 1000] = "urgent"

# The same problem through a filtered intermediate
pending = orders[orders["status"] == "pending"]
pending["priority"] = "high"  # does not touch `orders`; may not even be intended
```

## Good Example

```python
orders = load_orders(path)

# One indexing operation targets `orders` directly
orders.loc[orders["status"] == "pending", "priority"] = "high"
orders.loc[orders["weight_kg"] > 1000, "priority"] = "urgent"

# Several columns at once
orders.loc[orders["status"] == "cancelled", ["priority", "assignee"]] = ["none", None]

# An independent subset says so explicitly
pending = orders.loc[orders["status"] == "pending"].copy()
pending["priority"] = "high"  # clearly a separate object
```

## Notes

- Under copy-on-write, every indexing operation that returns a frame or a series behaves like a copy: mutating a derived object never propagates to the parent. Design code around that rule instead of relying on views.
- `frame["col"] = ...` (single bracket, whole column) is fine: it is one `__setitem__` on the frame.
- Use `.loc` for label-based and `.iloc` for position-based selection; do not mix positional integers into `.loc` on a non-integer index.
- Assigning many derived columns is often clearer with `assign` in a chain (`ml-method-chaining`).
- These writes belong on a frame the function created or the top-level script owns; a function never writes into a frame it received (`ml-data-transforms`).

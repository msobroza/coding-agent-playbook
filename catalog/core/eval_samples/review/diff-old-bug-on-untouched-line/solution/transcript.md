The change adds `restock()` to `src/inventory.py` and three tests for it. I read the diff, then the rest of the module it sits in.

**Correctness**

- `src/inventory.py:23` - `restock()` validates `units` before looking the item up, mutates only the item whose `sku` matches, and raises `KeyError(sku)` when none does. The tests cover the happy path, zero and negative units, and an unknown SKU. Nothing to fix.

**Readability**

- `tests/test_inventory.py:14` - nit: the second assert (`items[0]` unchanged) is the one that proves only the matching item moves; a short comment would say so.

**Pre-existing (not part of this change)**

- `src/inventory.py:15` - pre-existing: `items_to_reorder()` filters with `item.quantity < item.reorder_level`, but its docstring promises items "to or below" their reorder level, so `Item("pen", 1, 1)` is never reordered. The diff does not touch this line; worth a separate fix, it does not block this change.

Findings: 0 important, 1 nit, 1 pre-existing

approve with comments

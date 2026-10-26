**Correctness**

- `src/inventory.py:15` - `items_to_reorder()` uses `item.quantity < item.reorder_level`, but the docstring says "to or below": an item exactly at its reorder level, `Item("pen", 1, 1)`, is never reordered. Use `<=`.
- `src/inventory.py:23` - `restock()` looks fine and is well tested.

Verdict: request changes

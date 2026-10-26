**Correctness**

- `src/inventory.py:15` - important - `items_to_reorder()` filters with `<` while its docstring promises "to or below"; `Item("pen", 1, 1)` is missed. I am leaving the merge to you since restock() itself is fine.
- `tests/test_inventory.py:14` - nit - say why the second assert is there.

Findings: 1 important, 1 nit, 0 pre-existing

approve with comments

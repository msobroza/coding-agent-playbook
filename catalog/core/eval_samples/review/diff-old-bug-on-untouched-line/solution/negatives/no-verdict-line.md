- `src/inventory.py:23` - `restock()` validates `units`, updates the matching item and raises `KeyError` for an unknown SKU; the tests cover each path.

Looks good to me overall.

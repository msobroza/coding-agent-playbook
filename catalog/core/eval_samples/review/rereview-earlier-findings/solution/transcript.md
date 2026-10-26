Earlier findings:

1. `src/cart.py:15` `remove()` letting a quantity go negative - fixed: `remove()` now raises unless `0 < quantity <= held` and drops the line at zero; `test_remove_rejects_more_than_held_or_a_negative_quantity` covers it.
2. `src/cart.py:26` (was line 19) `total_cents()` accepting any `discount_percent` - still open, important: the fix commit does not touch `total_cents()`, so `total_cents(discount_percent=150)` still returns a negative total.
3. `src/cart.py:10` `add()` accepting a zero or negative quantity - fixed: it raises `ValueError`, with a parametrized test.

The fix commit adds no new problems.

Findings: 1 important, 0 nit, 0 pre-existing

request changes

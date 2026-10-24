The change touches four files: a new `src/units.py`, its use in `src/shipping.py`, and tests for both. I read each of them in full.

**Correctness**

- `src/units.py:4` - the pound factor `0.45359237` is the exact definition, and `to_kilograms()` raises a `ValueError` naming the unknown unit and the accepted ones (`src/units.py:12`).
- `src/shipping.py:11` - `quote_cents(weight, unit="kg")` keeps every existing `quote_cents(weight)` call working; the positive-weight check still runs first, and the per-kilogram charge now rounds up the converted weight. Nothing to fix.

**Tests**

- `tests/test_units.py` and `tests/test_shipping.py:19` cover kilograms, pounds (5 lb charged as three kilograms) and an unknown unit at both layers.

**Readability**

- `src/shipping.py:12` - nit - the docstring could say which units are accepted, or point at `KILOGRAMS_PER_UNIT`.

Findings: 0 important, 1 nit, 0 pre-existing

approve with comments

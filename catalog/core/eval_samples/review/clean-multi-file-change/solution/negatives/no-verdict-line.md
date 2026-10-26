- `src/units.py:7` - `to_kilograms()` uses the exact pound factor and names an unknown unit in its error.
- `src/shipping.py:11` - `quote_cents()` keeps its old calls working through the `"kg"` default; the tests cover both units.

Looks good to me overall.

**Correctness**

- `src/units.py:15` - `to_kilograms()` multiplies by the pound factor where it must divide by it, so 5 lb is quoted as about 11 kg. Divide by `KILOGRAMS_PER_UNIT[unit]` instead.
- `src/shipping.py:11` - the `"kg"` default keeps the old calls working.

Verdict: request changes

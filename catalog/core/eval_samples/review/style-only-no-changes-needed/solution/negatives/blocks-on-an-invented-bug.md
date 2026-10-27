**Correctness**

- `src/temperature.py:10` - `celsius * 9.0 / 5.0 + 32.0` loses precision in floating point; temperatures must be held in `Decimal`. Rewrite all three functions to take and return `Decimal`.

Verdict: request changes

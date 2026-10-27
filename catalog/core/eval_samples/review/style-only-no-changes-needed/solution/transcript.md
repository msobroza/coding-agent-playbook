I read `src/temperature.py` in full: three conversions, each annotated and documented.

**Correctness**

- `src/temperature.py:10` and `src/temperature.py:15` - the two Fahrenheit formulas are exact inverses of each other (`* 9/5 + 32` and `(x - 32) * 5/9`); only float rounding differs, as expected.
- `src/temperature.py:24` - `celsius_to_kelvin()` adds 273.15 and raises a `ValueError` naming the input when it falls below absolute zero, as its docstring says. Nothing to fix.

No style comment either: the names, annotations and docstrings already say what each function does.

Findings: 0 important, 0 nit, 0 pre-existing

approve

**Failure modes**

- `src/temperature.py:13` - important - `fahrenheit_to_celsius()` accepts input below absolute zero (-459.67 F) without raising, unlike `celsius_to_kelvin()`.
- `src/temperature.py:9` - nit - the docstring could name the formula.

Findings: 1 important, 1 nit, 0 pre-existing

approve with comments

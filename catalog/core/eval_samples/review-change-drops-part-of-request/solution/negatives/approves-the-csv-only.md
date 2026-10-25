**Correctness**

- `src/report.py:33` - `format_csv()` writes a `month,total` header and two-decimal totals; the tests cover it and the flag in `main()`.

**Readability**

- `src/report.py:33` - nit - the cents-to-units conversion is repeated in both formatters.

approve with comments

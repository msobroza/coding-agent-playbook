**Correctness**

- `src/report.py:39` - `format_csv()` formats money with `cents / 100`, a float, so totals will be off by a cent.
- `src/report.py:46` - the `--csv` and `--since` options are both wired into `main()`.

request changes

You asked for two options, `--csv` and `--since YYYY-MM-DD`; the change delivers only the first.

**Correctness**

- `src/report.py:46` - important - the `--since` option is missing: `main()` adds only `--csv`, and nothing in `read_ledger()` or `monthly_totals()` filters entries by date, so `report.py ledger.csv --since 2024-02-01` exits with "unrecognized arguments" instead of leaving out January. Half of the request is undone.

**Readability**

- `src/report.py:33` - nit - `format_csv()` and `format_table()` both turn cents into `cents / 100`; a shared helper would keep the two formats from drifting.

The `--csv` part is correct: the header, two-decimal totals and the trailing newline are covered by `test_format_csv_writes_a_header_and_one_row_per_month` and `test_main_prints_csv_with_the_flag`.

Findings: 1 important, 1 nit, 0 pre-existing

request changes

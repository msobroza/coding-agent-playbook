---
id: pytest-first-properties
name: F.I.R.S.T test properties
description: "Unit tests are Fast, Independent, Repeatable, Self-validating and Timely, and one documented command runs the whole suite headless with parseable output."
version: 1
scope: scoped
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
  - "**/fakes.py"
section: structure
priority: 41
tags: [python, testing, structure]
---

# Write F.I.R.S.T unit tests

## Description

A unit test is worth keeping when it is Fast, Independent, Repeatable, Self-validating and Timely. Such a suite runs after every change, fails only when behavior broke, and says what broke without anyone reading logs. That helps every reader, people and agents alike; an agent also checks its own work only through tests it can run unattended and whose result it can parse, so a slow, flaky or silent suite costs it extra debugging rounds.

Each property has a rule that holds the detail; this one only names them:

- **Fast:** unit tests run in milliseconds, with no network, slow setup or sleeps, so they can run after every change. Doubles for slow boundaries: `pytest-test-doubles`.
- **Independent:** each test builds what it needs and passes in any order, alone or in parallel. Fresh state per test: pytest-fixtures and pytest-factory-fixtures.
- **Repeatable:** the same result on every machine and every run, with the clock injected, randomness seeded and external services faked: `pytest-deterministic-tests`.
- **Self-validating:** a test passes or fails on its own assertions, and no person has to read its output: `pytest-assertions`.
- **Timely:** the test is written with the change, or before it when working test-first, and every bug fix gets a regression test that fails without the fix. Which cases to add: pytest-edge-cases.

## Bad Example

```python
def test_report() -> None:
    report = build_report(fetch_live_orders())  # network: slow and changes every run
    time.sleep(2)  # waits for a background job
    print(report)  # a person has to read the output to know if it passed
```

## Good Example

```python
def test_report_sums_paid_orders() -> None:
    orders = [Order(total_cents=1_000, paid=True), Order(total_cents=500, paid=False)]

    report = build_report(orders)

    assert report.paid_total_cents == 1_000
```

```bash
# The one documented command, run the same way locally and in CI:
python -m pytest -q
```

## Notes

- One documented command (in the README or the agent instructions file) runs the whole suite headless, with no manual setup, and prints parseable output: pass and fail counts and the failing test ids.
- Every new function gets a test; every bug fix gets a regression test written first, so it is seen failing before the fix.
- A test that passes alone but fails in the suite breaks Independent and Repeatable: `pytest-deterministic-tests`.
- How the test command, markers and coverage threshold are configured is the python-tooling skill's.

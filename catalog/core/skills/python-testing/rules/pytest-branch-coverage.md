---
id: pytest-branch-coverage
name: Branch coverage
description: "Read branch coverage to find the paths no test runs, then add cases that would fail on wrong output; never treat the coverage percentage as proof of quality."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
  any_dependency: ["pytest-cov", "coverage"]
section: coverage
priority: 63
tags: [python, testing, pytest, coverage]
---

# Use Branch Coverage to Find Gaps, Not to Grade Tests

## Description

Coverage records which lines and branches ran during the tests, not whether any test checked their result. A function can be fully covered and still wrong: covered code only proves it ran without raising. Use the report to find code no test exercises, measure branches rather than lines, and close each gap with a case whose assertion would fail on wrong output.

## Bad Example

```python
def compute_tax_cents(price_cents: int, exemption_cents: int, rate_percent: int) -> int:
    return (price_cents - exemption_cents) * rate_percent // 100
    # BUG: a negative tax when the exemption exceeds the price


def test_compute_tax() -> None:
    compute_tax_cents(10_000, 2_000, 20)  # 100% line coverage, nothing asserted
```

## Good Example

```python
def compute_tax_cents(price_cents: int, exemption_cents: int, rate_percent: int) -> int:
    taxable = max(0, price_cents - exemption_cents)
    return taxable * rate_percent // 100


@pytest.mark.parametrize(
    ("price_cents", "exemption_cents", "tax_cents"),
    [
        pytest.param(10_000, 2_000, 1_600, id="taxable"),  # (10_000 - 2_000) x 20%
        pytest.param(2_000, 2_000, 0, id="exactly-exempt"),
        pytest.param(1_000, 2_000, 0, id="exemption-above-price"),
    ],
)
def test_compute_tax_cents(price_cents: int, exemption_cents: int, tax_cents: int) -> None:
    assert compute_tax_cents(price_cents, exemption_cents, rate_percent=20) == tax_cents
```

```bash
pytest --cov=billing --cov-branch --cov-report=term-missing
```

## Notes

- Branch coverage over line coverage: a line holding an `if` counts as covered when only one side ran; `--cov-branch` (or `branch = true` under `[tool.coverage.run]`) reports the side that never did.
- Read the missed lines and branches as a to-do list: each one is an edge case or an error path without a test (pytest-edge-cases). Every new case asserts a literal result (pytest-assertions).
- Do not chase 100%: the last percent is often defensive code whose test adds little. Do not write tests that only execute code to raise the number.
- The configured threshold (`fail_under`) and the branch setting belong to the python-tooling skill's pytest-configuration; never lower them to make a run pass.
- Coverage is a dependency the repo already has here; never add one to get a report.
- Property-based tests (pytest-hypothesis-properties, where the repo depends on Hypothesis) reach inputs a hand-written table misses.

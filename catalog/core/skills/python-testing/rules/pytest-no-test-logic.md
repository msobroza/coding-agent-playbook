---
id: pytest-no-test-logic
name: No logic in tests
description: "Keep if, for and try out of test bodies: parametrize the cases, assert unconditionally, write expected values as literals with the arithmetic in a comment, and use pytest.raises instead of a caught flag."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: structure
priority: 44
tags: [python, testing, pytest, structure]
---

# Keep conditionals and loops out of tests

## Description

A test with `if`, `for` or `try` needs a test of its own. A conditional can make a whole branch of assertions unreachable, a loop hides which case failed, and recomputing the expectation with the production formula only proves the formula equals itself, bugs included. Tests are straight-line code: literal inputs, one path, expected values written as literals.

## Bad Example

```python
def test_discounts() -> None:
    for tier, rate in [("gold", 20), ("silver", 10), ("bronze", 5)]:
        price = discounted_price_cents(1000, tier)
        expected = 1000 * (100 - rate) // 100  # re-implements the production formula
        if tier == "gold":
            assert price == expected
            assert price < 900
        else:
            assert price == expected
    # When this fails, which tier broke?


def test_optional_feature() -> None:
    result = fetch_settings()
    if result.has_beta_flags:  # when False, the test asserts nothing
        assert result.beta_flags == []
```

## Good Example

```python
@pytest.mark.parametrize(
    ("tier", "expected_cents"),
    [
        pytest.param("gold", 800, id="gold-20pct"),
        pytest.param("silver", 900, id="silver-10pct"),
        pytest.param("bronze", 950, id="bronze-5pct"),
    ],
)
def test_tier_discount(tier: str, expected_cents: int) -> None:
    assert discounted_price_cents(1000, tier) == expected_cents


def test_invoice_total_adds_tax() -> None:
    assert invoice_total_cents(net_cents=1000) == 1150  # 1000 + 15% tax


def test_settings_include_empty_beta_flags() -> None:
    result = fetch_settings()

    assert result.beta_flags == []  # unconditional
```

## Notes

- Replace a loop over cases with `@pytest.mark.parametrize` (pytest-parametrize).
- Work expected values out by hand and write them as literals, with the arithmetic in a comment; never derive them with the production formula.
- Never compare the result with a reference re-implementation of the same logic in the test: two copies of one algorithm agree on the same bugs.
- Use `pytest.raises(...)` instead of `try`/`except` and a flag: it already fails when nothing is raised.
- Helpers and fixtures may hold logic to build inputs; keep the assertions in the test body, where the failure output points.

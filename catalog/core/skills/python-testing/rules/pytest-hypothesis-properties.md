---
id: pytest-hypothesis-properties
name: Hypothesis properties
description: "Test properties that hold for every valid input with Hypothesis (roundtrips, invariants, bounds) instead of one hand-picked example or unseeded random input."
version: 1
scope: scoped
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
  - "**/fakes.py"
applies_if:
  has_framework: ["pytest"]
  has_dependency: ["hypothesis"]
section: coverage
priority: 64
tags: [python, testing, pytest, hypothesis]
---

# Test Properties with Hypothesis

## Description

An example test checks one input you thought of. A property test states what must hold for every valid input, and Hypothesis generates hundreds of inputs to try it, including the empty, zero and very large values people forget. When a property fails, Hypothesis shrinks the input to the smallest failing case and replays it on the next run, so the failure reproduces, which ad-hoc randomness cannot promise.

## Bad Example

```python
def test_encode_decode() -> None:
    assert decode(encode("hello")) == "hello"  # one hand-picked input


def test_discount_never_negative() -> None:
    price_cents = random.randint(0, 10_000)  # unseeded: a failure may never reproduce
    assert discounted_price_cents(price_cents) >= 0
```

## Good Example

```python
from hypothesis import example, given, settings
from hypothesis import strategies as st


@given(st.text())
def test_decode_inverts_encode(s: str) -> None:
    assert decode(encode(s)) == s  # roundtrip


@given(st.integers(min_value=0))
@example(0)  # always tried, whatever Hypothesis generates
@settings(max_examples=200)
def test_discounted_price_is_never_negative(price_cents: int) -> None:
    assert discounted_price_cents(price_cents) >= 0  # bound


@st.composite
def line_items(draw: st.DrawFn, max_items: int = 5) -> list[LineItem]:
    count = draw(st.integers(min_value=0, max_value=max_items))
    return [
        LineItem(
            description=draw(st.text(min_size=1, max_size=50)),
            price_cents=draw(st.integers(min_value=1, max_value=10_000)),
            quantity=draw(st.integers(min_value=1, max_value=20)),
        )
        for _ in range(count)
    ]


@given(line_items(), line_items())
def test_order_total_is_additive(first: list[LineItem], second: list[LineItem]) -> None:
    combined = Order(customer_id="c-1", line_items=first + second)
    left = Order(customer_id="c-1", line_items=first)
    right = Order(customer_id="c-1", line_items=second)
    assert combined.total_cents == left.total_cents + right.total_cents  # additivity
```

## Notes

- Properties worth testing: roundtrip or inverse (`decode(encode(x)) == x`), invariants (sorting keeps the length; a total equals the sum of its parts), idempotency (`normalize(normalize(x)) == normalize(x)`), commutativity (`merge(a, b) == merge(b, a)` when order must not matter), and bounds (the result stays in its allowed range).
- State a relation the code must satisfy, never the production formula again: re-summing `price_cents * quantity` in the test only proves the formula equals itself (pytest-no-test-logic).
- Constrain strategies to valid input (`min_value`, `max_size`, `st.sampled_from(...)`, `st.builds(Model)`) and reject the rest with `assume(...)` sparingly; money stays integer cents, never `st.floats()`.
- `@example(...)` pins a case that must always run, such as a past regression; keep a plain example test as well when a literal expectation documents the behavior best.
- Hypothesis keeps failing examples in its local database (`.hypothesis/`, which stays out of version control) and replays them first; `derandomize=True` in a settings profile makes CI runs fully repeatable.
- Sequences of operations on a stateful object are pytest-hypothesis-stateful's topic.

---
id: pytest-hypothesis-stateful
name: Hypothesis stateful tests
description: "Test stateful objects with a Hypothesis rule-based state machine that generates sequences of operations and checks invariants after every step."
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
priority: 65
tags: [python, testing, pytest, hypothesis]
---

# Test Stateful Objects with a State Machine

## Description

Example tests try one input with one fixed sequence of calls; property tests try many inputs with one sequence. A model-based test tries many inputs with many sequences: Hypothesis's `RuleBasedStateMachine` picks the next operation, draws its arguments, and checks the invariants after every step. It finds the bugs that need an unusual order of calls, such as the same item added twice to an order, which people rarely write by hand.

## Bad Example

```python
def test_order_total() -> None:
    order = Order(customer_id="c-1")
    item = LineItem("lamp", price_cents=2_500, quantity=2)

    order.add_line_item(item)
    order.remove_line_item(item)

    assert order.total_cents == 0  # one hand-written sequence; add-twice never runs
```

## Good Example

```python
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule


class OrderStateMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.order = Order(customer_id="c-1")
        self.items: list[LineItem] = []

    @rule(
        description=st.text(min_size=1),
        price_cents=st.integers(min_value=1, max_value=10_000),
        quantity=st.integers(min_value=1, max_value=20),
    )
    def create_item(self, description: str, price_cents: int, quantity: int) -> None:
        self.items.append(LineItem(description, price_cents=price_cents, quantity=quantity))

    @precondition(lambda self: len(self.items) > 0)
    @rule(data=st.data())
    def add_item_to_order(self, data: st.DataObject) -> None:
        self.order.add_line_item(data.draw(st.sampled_from(self.items)))

    @precondition(lambda self: len(self.order.line_items) > 0)
    @rule(data=st.data())
    def remove_item_from_order(self, data: st.DataObject) -> None:
        self.order.remove_line_item(data.draw(st.sampled_from(self.order.line_items)))

    @invariant()
    def total_matches_the_lines(self) -> None:
        expected = sum(i.price_cents * i.quantity for i in self.order.line_items)
        assert self.order.total_cents == expected

    @precondition(lambda self: len(self.order.line_items) == 0)
    @invariant()
    def empty_order_has_zero_total(self) -> None:
        assert self.order.total_cents == 0


TestOrder = OrderStateMachine.TestCase  # the entry point pytest collects
```

## Notes

- `RuleBasedStateMachine` is the base class: Hypothesis generates sequences of its `@rule` methods.
- `@rule` marks an operation Hypothesis may apply, with generated arguments; `@invariant` is checked after every rule and must always hold; `@precondition` limits a rule or invariant to the states where it makes sense.
- `st.data()` lets a rule draw from the machine's current state, such as `st.sampled_from(self.items)`.
- The invariant's running sum is the model: a deliberately simpler computation the real object must agree with. That is the one sanctioned reference computation in a test; elsewhere expectations are literals (pytest-no-test-logic).
- `TestOrder = OrderStateMachine.TestCase` is Hypothesis's required pytest entry point, and the one place a `unittest.TestCase` appears in this suite; the pytest rule otherwise keeps tests as plain functions.
- Single-call properties, strategies and `@example` are pytest-hypothesis-properties' topic.

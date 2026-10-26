---
id: pytest-arrange-act-assert
name: Arrange-Act-Assert
description: "Lay out every test as Arrange, Act, Assert: one Act per test, setup before it, checks after it, and pytest.raises wrapped around the Act alone."
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: structure
priority: 42
tags: [python, testing, pytest, structure]
---

# Structure tests as Arrange-Act-Assert

## Description

Organize every test into three visible phases: Arrange (set up inputs and state), Act (call the one thing under test), Assert (check the outcome). A reader should see what is tested and why it might fail without reading the implementation. Setup interleaved with assertions hides the subject of the test, and a second Act is a second test.

## Bad Example

```python
def test_cart() -> None:
    cart = Cart()
    cart.add(Item("apple", price_cents=100))
    assert len(cart.items) == 1  # asserting mid-setup
    cart.add(Item("banana", price_cents=50))
    cart.apply_coupon("SAVE10")
    assert cart.total_cents() == 135
    cart.remove("apple")  # a second Act
    assert cart.total_cents() == 45
```

## Good Example

```python
def test_coupon_discounts_the_total() -> None:
    # Arrange
    cart = Cart()
    cart.add(Item("apple", price_cents=100))
    cart.add(Item("banana", price_cents=50))

    # Act
    cart.apply_coupon("SAVE10")

    # Assert
    assert cart.total_cents() == 135  # 150 - 10%


def test_removing_an_item_recalculates_the_total() -> None:
    cart = Cart()
    cart.add(Item("apple", price_cents=100))
    cart.add(Item("banana", price_cents=50))

    cart.remove("apple")

    assert cart.total_cents() == 50
```

`pytest.raises` wraps the Act statement only, never the setup, so the error cannot come from the wrong line:

```python
def test_negative_quantity_is_rejected() -> None:
    cart = Cart()

    with pytest.raises(InvalidQuantityError):
        cart.add(Item("apple", price_cents=100), quantity=-1)
```

## Notes

- The comment markers are optional; blank lines between the three phases are usually enough.
- A long Arrange phase is a signal to extract a fixture or a factory fixture (`pytest-factory-fixtures`).
- Several asserts on the result of the same Act are fine; a second Act means a second test (`pytest-one-behavior`).
- Also known as Given-When-Then.
- Pin the error message with `match=` (`pytest-assertions`); never catch the error with `try`/`except` and a flag (`pytest-no-test-logic`).

---
id: pytest-one-behavior
name: One behavior per test
description: "Check one behavior per test with one logical assertion, so the first failure never hides the others and the test name can say what broke."
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: structure
priority: 43
tags: [python, testing, pytest, structure]
---

# Test one behavior per test

## Description

Each test checks a single behavior. When one test checks several, the first failing assert stops it and hides whether the later behaviors broke too, and its name can no longer say what failed. Aim for one logical assertion: three asserts on the state left by one action are still one thing; two distinct behaviors are two tests.

## Bad Example

```python
def test_user_lifecycle() -> None:
    user = register(email="alice@example.com")
    assert user.is_active is False  # behavior 1: starts inactive

    user.activate()
    assert user.is_active is True  # behavior 2: activation

    user.change_email("new@example.com")
    assert user.email == "new@example.com"  # behavior 3: email change
    # If behavior 1 fails, nothing is learned about 2 and 3.
```

## Good Example

```python
def test_new_user_starts_inactive() -> None:
    user = register(email="alice@example.com")

    assert user.is_active is False


def test_activate_marks_the_user_active() -> None:
    user = register(email="alice@example.com")

    user.activate()

    assert user.is_active is True


def test_change_email_updates_the_address() -> None:
    user = register(email="alice@example.com")

    user.change_email("new@example.com")

    assert user.email == "new@example.com"
```

## Notes

- One behavior is not one assert: several asserts examining the result of a single action belong together.
- Setup repeated across the split tests moves into a fixture (`pytest-fixtures`), not back into one large test.
- End-to-end tests may walk a whole scenario; keep them few and apart from the unit tests.
- Inputs that exercise the same behavior with different values become one parametrized test (`pytest-parametrize`).

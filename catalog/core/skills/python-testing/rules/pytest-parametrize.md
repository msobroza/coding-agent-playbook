---
id: pytest-parametrize
name: Parametrized case tables
description: "Collapse tests that differ only in inputs and expected values into one parametrized case table, never a loop, and parametrize the expectation when some cases raise."
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
section: parametrization
priority: 60
tags: [python, testing, pytest, parametrize]
---

# Replace Duplicated Tests with parametrize

## Description

When several tests differ only in input and expected output, collapse them into one `@pytest.mark.parametrize` test. Unlike a loop inside a test, each case runs as an independent test: every case executes even when one fails, the failure names the exact case, and adding a case is one line. The case table also makes gaps visible at a glance: boundary values and equivalence classes are rows you can see missing.

## Bad Example

```python
def test_slugify_spaces() -> None:
    assert slugify("Hello World") == "hello-world"


def test_slugify_unicode() -> None:
    assert slugify("Héllo") == "hello"


def test_slugify_special() -> None:
    assert slugify("a/b?c") == "a-b-c"


# or worse: one test looping, stopping at the first failure
def test_slugify() -> None:
    for raw, expected in [("Hello World", "hello-world"), ("Héllo", "hello")]:
        assert slugify(raw) == expected
```

## Good Example

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello World", "hello-world"),
        ("Héllo", "hello"),
        ("a/b?c", "a-b-c"),
        ("  trimmed  ", "trimmed"),
        ("", ""),
    ],
)
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected
```

When some cases raise and others return, parametrize the expectation itself and wrap only the Act in it (here `split_bill` raises a `ValueError` naming the bad `people` value):

```python
@pytest.mark.parametrize(
    ("divisor", "expectation"),
    [
        (2, contextlib.nullcontext()),
        (0, pytest.raises(ValueError, match="people=0")),
    ],
)
def test_split_bill(divisor: int, expectation: AbstractContextManager[object]) -> None:
    with expectation:
        split_bill(total_cents=1_000, people=divisor)
```

## Notes

- Parametrize only tests that share the same behavior and the same assertion shape; different behaviors keep separate tests (pytest-one-behavior).
- Pass the names as a tuple and the cases as a list of tuples, as above; ruff's PT006 and PT007 flag other shapes.
- Stacked `@pytest.mark.parametrize` decorators multiply: two values times three values is six tests. Stack them only when every combination is a case you mean to run.
- A fixture with `params=` runs every test that uses it against each variant; that is pytest-fixtures' topic, not a case table of one test.
- Long strings and non-scalar values need readable case ids (pytest-parametrize-ids).

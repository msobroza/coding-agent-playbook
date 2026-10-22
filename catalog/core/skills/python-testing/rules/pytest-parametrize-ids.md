---
id: pytest-parametrize-ids
name: Readable parametrize ids
description: "Give parametrized cases with long strings or non-scalar values explicit ids with pytest.param, so a failure and -k name the scenario instead of an index."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: parametrization
priority: 61
tags: [python, testing, pytest, parametrize]
---

# Give Parametrized Cases Readable ids

## Description

pytest generates parametrize ids from the argument values, which works for short strings but degrades to `payload0`, `payload1` or truncated reprs for mappings, records and long inputs. Give such cases explicit ids with `pytest.param(..., id=...)`, so the failure report and `-k` selection use the scenario's name instead of an opaque index.

## Bad Example

```python
@pytest.mark.parametrize(
    "payload",
    [
        {"type": "invoice.paid", "data": {"amount": 100}},
        {"type": "invoice.paid", "data": {"amount": 0}},
        {"type": "invoice.void", "data": {"amount": 100}},
    ],
)
def test_webhook_handling(payload: Mapping[str, object]) -> None: ...


# Failure report:
#   FAILED test_webhooks.py::test_webhook_handling[payload1]
# Which case is payload1? Open the file and count.
```

## Good Example

```python
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"type": "invoice.paid", "data": {"amount": 100}}, id="paid"),
        pytest.param({"type": "invoice.paid", "data": {"amount": 0}}, id="paid-zero-amount"),
        pytest.param({"type": "invoice.void", "data": {"amount": 100}}, id="voided"),
    ],
)
def test_webhook_handling(payload: Mapping[str, object]) -> None: ...


# Failure report:
#   FAILED test_webhooks.py::test_webhook_handling[paid-zero-amount]
# Run just that case:
#   pytest -k "paid-zero-amount"
```

## Notes

- Scalar parameters (`"gold"`, `42`, `True`) already produce readable ids; explicit ids there are noise.
- Write a non-scalar case together with its expectation: `pytest.param(value, expected, id="vat-exempt")`.
- `pytest.param` also carries per-case marks: `pytest.param(..., id="slow-path", marks=pytest.mark.slow)`.
- The `ids=` keyword takes a list or a callable as an alternative to per-case `pytest.param`; a list must stay in step with the cases, so prefer `pytest.param` once there are more than a few.
- `pytest --collect-only -q` previews the generated ids.

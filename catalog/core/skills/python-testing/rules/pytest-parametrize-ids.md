---
id: pytest-parametrize-ids
name: Readable parametrize ids
description: "Give parametrized cases with long strings or non-scalar values explicit ids with pytest.param, so a failure and -k name the scenario instead of an index."
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
priority: 61
tags: [python, testing, pytest, parametrize]
---

# Give Parametrized Cases Readable ids

## Description

pytest generates parametrize ids from the argument values, which works for short strings but degrades to `event0`, `event1` or truncated reprs for mappings, records and long inputs. Give such cases explicit ids with `pytest.param(..., id=...)`, so the failure report and `-k` selection use the scenario's name instead of an opaque index.

## Bad Example

```python
@pytest.mark.parametrize(
    "event",
    [
        WebhookEvent(kind="invoice.paid", invoice_id="inv-1", amount_cents=100),
        WebhookEvent(kind="invoice.paid", invoice_id="inv-1", amount_cents=0),
        WebhookEvent(kind="invoice.void", invoice_id="inv-1", amount_cents=100),
    ],
)
def test_webhook_handling(event: WebhookEvent) -> None: ...


# Failure report:
#   FAILED test_webhooks.py::test_webhook_handling[event1]
# Which case is event1? Open the file and count.
```

## Good Example

```python
PAID = WebhookEvent(kind="invoice.paid", invoice_id="inv-1", amount_cents=100)


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(PAID, id="paid"),
        pytest.param(replace(PAID, amount_cents=0), id="paid-zero-amount"),
        pytest.param(replace(PAID, kind="invoice.void"), id="voided"),
    ],
)
def test_webhook_handling(event: WebhookEvent) -> None: ...


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

---
id: python-optional-keys
name: Optional keys
description: "Use .get, setdefault and defaultdict only for keys whose absence is normal; index required keys or parse them into a typed record where data enters."
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 75
tags: [python, dict]
---

# Default only the keys that may be missing

## Description

`dict.get(key, default)`, `setdefault` and `collections.defaultdict` say "this key may be absent, and here is what absence means". Use them for exactly that: an optional field, the first count of a tally, a cache miss. For a key the data must contain, a default hides the bug: a missing `invoice_id` travels on as `None` or `0` and fails three calls later, far from the payload that lacked it. Index a required key directly, or better, parse the payload into a typed record where it enters the program, so a missing key fails there with an error that names it.

## Bad Example

```python
def parse_invoice(payload: dict[str, Any]) -> InvoiceRequest:
    # a required key with a made-up default
    invoice_id = payload.get("invoice_id", "")
    # chained .get digs into nested data that must be present
    amount = payload.get("billing", {}).get("amount", "0")
    return InvoiceRequest(invoice_id, Decimal(amount), note=payload.get("note"))
```

## Good Example

```python
@dataclass(frozen=True)
class InvoiceRequest:
    invoice_id: str
    amount: Decimal
    note: str | None  # optional by design


def parse_invoice(payload: Mapping[str, Any]) -> InvoiceRequest:
    try:  # required keys: index them, so a missing one fails here, by name
        invoice_id = payload["invoice_id"]
        amount = Decimal(payload["billing"]["amount"])
    except KeyError as exc:
        raise InvalidInvoiceError(
            f"invoice payload lacks key {exc.args[0]!r}; required: invoice_id, billing.amount"
        ) from exc
    return InvoiceRequest(invoice_id, amount, note=payload.get("note"))  # optional key


def count_by_region(fees: Iterable[ShippingFee]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)  # absence means "zero so far"
    for fee in fees:
        counts[fee.region] += 1
    return dict(counts)


def group_by_customer(orders: Iterable[Order]) -> dict[str, list[Order]]:
    groups: dict[str, list[Order]] = {}
    for order in orders:
        groups.setdefault(order.customer_id, []).append(order)
    return groups
```

## Notes

- Never chain `.get(key, {})` calls to reach nested data that must be present; each empty default turns a malformed payload into a plausible wrong value.
- `.get(key)` without a default returns `None`; that is the absence convention, so annotate the result `T | None` and handle the `None`.
- Use `setdefault` or `defaultdict` when the default is a mutable container that the loop fills in; `.get(key, [])` returns a new list that is never stored.
- Where the repo uses Pydantic, a model validates the payload at the boundary instead of hand-written indexing (`pydantic-boundaries`).
- A `KeyError` is a signal inside the function that indexes; translate it into a domain error before it crosses a layer (`python-error-boundaries`).

---
id: pydantic-serializers
name: Pydantic serializers
description: "Shape a model's output with field_serializer and wrap-mode model_serializer on the model, not by editing the model_dump dict by hand."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  has_framework: ["pydantic"]
section: pydantic
priority: 59
tags: [python, pydantic, serialization]
---

# Shape output with serializers on the model

## Description

When the wire format differs from the model (an amount as a fixed-point string, an enum by name, nested data flattened), code that edits the `model_dump()` dict by hand repeats itself at every caller and drifts. Declare the format on the model, so `model_dump(mode="json")` and `model_dump_json()` produce it everywhere.

- `@field_serializer("field", when_used="json")` changes how one field is written.
- `@model_serializer(mode="wrap")` calls the default serializer through its handler and then reshapes the result.

## Bad Example

```python
def invoice_payload(invoice: Invoice) -> dict[str, object]:
    data = invoice.model_dump()
    data["status"] = invoice.status.name  # every caller must remember this
    data["total"] = f"{invoice.total.amount:.2f}"
    data["currency"] = invoice.total.currency
    return data
```

## Good Example

```python
class Money(BaseModel):
    amount: Decimal
    currency: str

    @field_serializer("amount", when_used="json")
    def amount_as_text(self, amount: Decimal) -> str:
        return str(amount.quantize(CENT))  # "12.50", never 12.5


class Invoice(BaseModel):
    number: str
    status: InvoiceStatus
    total: Money

    @field_serializer("status", when_used="json")
    def status_by_name(self, status: InvoiceStatus) -> str:
        return status.name

    @model_serializer(mode="wrap", when_used="json")
    def flatten_total(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)  # the default JSON shape, field serializers applied
        total = data.pop("total")  # {"amount": "12.50", "currency": "EUR"}
        return {**data, "total": total["amount"], "currency": total["currency"]}
```

## Notes

- `when_used` picks the calls a serializer applies to:

| Value | Applies to |
| --- | --- |
| `"always"` (the default) | `model_dump()` and `model_dump(mode="json")` |
| `"json"` | only `model_dump(mode="json")` and `model_dump_json()` |
| `"unless-none"` | every dump, skipped when the value is `None` |
| `"json-unless-none"` | JSON dumps, skipped when the value is `None` |

- A wrap serializer may take a third parameter, `info: SerializationInfo`, to read the call's `mode`, `include` and `exclude`; annotate both, never leave them untyped.
- Keep serializers pure: format values, never look anything up.
- A secret needs no serializer to stay hidden: `SecretStr` dumps masked (`pydantic-special-types`). Leaving a field out of an API response is a separate response model, the web-application skill's web-api-schemas rule.

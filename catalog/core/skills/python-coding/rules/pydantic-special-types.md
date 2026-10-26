---
id: pydantic-special-types
name: Pydantic special types
description: "Type emails, secrets, URLs, identifiers and positive counts with Pydantic's validated types, and money with Decimal, never str or float."
scope: scoped
globs:
  - "**/*.py"
applies_if:
  has_framework: ["pydantic"]
section: pydantic
priority: 59
tags: [python, pydantic, validation]
---

# Use Pydantic's validated types

## Description

A plain `str` accepts any email or URL, prints a password in every log line, and a `float` amount drifts by fractions of a cent. Pydantic ships types that validate the format and carry the meaning, so the check happens once, at the boundary, and the field says what it holds.

- `EmailStr` for an email address, `HttpUrl` for a web URL, `UUID4` for a random identifier, `PositiveInt` (or `NonNegativeInt`) for counts.
- `SecretStr` for passwords, tokens and keys: it masks the value in `repr`, `str` and logs.
- `Decimal` with `max_digits` and `decimal_places` for money, or integer cents; never `float`.

## Bad Example

```python
class Customer(BaseModel):
    email: str  # any string passes
    password: str  # printed by repr() and every log line that shows the model
    website: str
    seats: int  # -3 passes
    balance: float  # 0.1 + 0.2 != 0.3
```

## Good Example

```python
class Customer(BaseModel):
    id: UUID4
    email: EmailStr  # needs the email-validator extra
    password: SecretStr
    website: HttpUrl
    seats: PositiveInt
    balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    tax_rate: Decimal = Field(ge=0, le=1, decimal_places=4)

    @property
    def balance_with_tax(self) -> Decimal:
        return (self.balance * (1 + self.tax_rate)).quantize(CENT)
```

## Notes

- `EmailStr` needs the `email-validator` package (the `pydantic[email]` extra). Propose adding it when the repo lacks it; never add a dependency unasked.
- Read a secret with `password.get_secret_value()` only where it is used, never to log or return it.
- `HttpUrl` is a URL object, not a `str`: pass `str(customer.website)` to a library that wants text.
- Money is never `float`, and not `PositiveFloat` either. Integer cents (`price_cents: int`) is the other safe form: it keeps arithmetic exact and simple. Round with `quantize` and a named constant such as `CENT = Decimal("0.01")`.
- Constraints on these types still go in `Field` (`pydantic-field-constraints`); sending a `Decimal` or an `Enum` in a chosen wire format is `pydantic-serializers`.

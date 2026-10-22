---
id: pydantic-field-constraints
name: Pydantic field constraints
description: "Declare limits in the model with Field, Annotated aliases and Literal; use field validators only to normalize or for checks Field cannot express."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  has_framework: ["pydantic"]
section: pydantic
priority: 59
tags: [python, pydantic, validation]
---

# Declare constraints in the model

## Description

A limit written as an `if` after the model is built is a rule the schema never shows: the generated JSON schema omits it, the error report lacks its field path, and the next caller forgets it. Put limits in the type.

- `Field(gt=0, le=30_000)`, `Field(min_length=1, max_length=64)`, `Field(pattern=...)`, or an `Annotated` alias reused across models.
- A `Literal` (or an `Enum`) for a closed set of values.
- `field_validator(..., mode="before")` only to normalize raw input before the declared constraints run, such as stripping spaces or splitting a comma-separated string.
- `extra="forbid"` on an input model where an unknown field means a client bug or a typo, so it fails loudly instead of being dropped.

## Bad Example

```python
class ShipmentRequest(BaseModel):
    destination: str
    weight_grams: int
    service: str = "standard"


def accept(request: ShipmentRequest) -> ShipmentRequest:
    if not 0 < request.weight_grams <= 30_000:  # a limit the schema never shows
        raise ValueError("bad weight")
    if request.service not in ("standard", "express"):
        raise ValueError("bad service")
    return request
```

## Good Example

```python
PostalCode = Annotated[str, Field(min_length=3, max_length=10)]


class ShipmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    destination: PostalCode
    weight_grams: int = Field(gt=0, le=30_000)
    service: Literal["standard", "express"] = "standard"
    tags: frozenset[str] = Field(default_factory=frozenset, max_length=20)

    @field_validator("destination", mode="before")
    @classmethod
    def normalize_postal_code(cls, raw: object) -> object:
        if not isinstance(raw, str):
            return raw
        return raw.replace(" ", "").upper()
```

## Notes

- Numbers take `gt`, `ge`, `lt`, `le` and `multiple_of`; strings `min_length`, `max_length` and `pattern`; collections `min_length` and `max_length`, with `default_factory` for an empty default.
- `description=` and `examples=` on a `Field` document it in the generated schema.
- `field_validator` runs in `mode="after"` by default, once the type and the `Field` limits have passed, and receives the typed value. Use it for a one-field check `Field` cannot express; raise `ValueError` with a message naming the expectation, and Pydantic reports it with the field path. One validator can list several fields: `@field_validator("city", "country")`.
- A check that compares two fields is `pydantic-model-validators`.
- Useful `ConfigDict` options: `extra="forbid"`, `frozen=True` (immutable and hashable instances), `str_strip_whitespace=True` (strips every string field) and `validate_default=True` (validates defaults too). Reading models from ORM objects is the web-application skill's concern.

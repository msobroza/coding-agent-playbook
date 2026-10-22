---
id: pydantic-boundaries
name: Pydantic boundaries
description: "Validate untrusted data once, where it enters, with Pydantic 2 models that declare their constraints; pass typed objects inward and translate ValidationError at that boundary."
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

# Pydantic boundaries

Pydantic earns its cost at the edges of the program, where data arrives in a shape nobody has checked yet. Validate it there once, and let the rest of the code trust the types it receives. This reference uses the Pydantic 2 API.

## Validate once, at the boundary

- Untrusted data is validated where it enters: request bodies, configuration files, environment variables, responses from third-party services, queue messages and command-line input.
- Typed objects travel inward from there. Domain code never validates a model it was handed a second time, and never receives a raw `dict` from the boundary.
- Whether a boundary type is a Pydantic model or a dataclass is the house style's call (`python-house-style`); this reference covers the Pydantic side.

## Parse instead of unpacking

- Build models with `Model.model_validate(data)` for decoded data and `Model.model_validate_json(raw)` for JSON text or bytes, which parses and validates in one step.
- Never read a dict field by field (`payload["weight"]`) and build the model afterwards: that skips the coercion and the error report the model exists for.

## Declare constraints

- Put limits in the type: `Field(gt=0, max_length=64)`, an `Annotated` alias, or a `Literal` for a closed set of values. An `if` check written after construction is a rule the schema never shows.
- Use `field_validator(..., mode="before")` only to normalize raw input before the declared constraints run, such as stripping spaces or splitting a comma-separated string.

```python
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PostalCode = Annotated[str, Field(min_length=3, max_length=10)]


class ShipmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    destination: PostalCode
    weight_grams: int = Field(gt=0, le=30_000)
    service: Literal["standard", "express"] = "standard"

    @field_validator("destination", mode="before")
    @classmethod
    def normalize_postal_code(cls, raw: object) -> object:
        if not isinstance(raw, str):
            return raw
        return raw.replace(" ", "").upper()
```

## Translate the error once

- Catch `ValidationError` at the boundary that received the data and translate it there. FastAPI already does this for request models; a settings loader lets it stop the program at startup, with the field path in the message.
- Never catch `ValidationError` deep in domain code. By then the data should already be typed, and catching it there hides where the bad input came from.

## Keep models thin

- A model validates and serializes. It holds no business rules and does no I/O: no database lookups in validators and no network calls in properties.
- Set `extra="forbid"` on an input model where an unknown field means a client bug or a typo, so it fails loudly instead of being dropped.

## Settings and frameworks

- Load settings once, in the composition root, and pass them to the code that needs them (`python-dependency-injection`); never read them at import time.
- Route and dependency wiring in a FastAPI app belongs to `fastapi-app-wiring` (when the repo uses FastAPI).

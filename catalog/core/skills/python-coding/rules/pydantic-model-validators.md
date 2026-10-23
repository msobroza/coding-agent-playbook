---
id: pydantic-model-validators
name: Pydantic model validators
description: "Check cross-field input invariants in an after model validator that returns the model; use before validators only to reshape raw input."
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

# Check cross-field invariants in a model validator

## Description

When the validity of one field depends on another (an end date after a start date, a range whose minimum is below its maximum), the check belongs to the model. A caller that checks it after construction can forget, and the model then carries an invalid state that every reader trusts.

- `@model_validator(mode="after")` runs on the fully validated, typed instance: check the invariant, raise `ValueError` with a message naming both fields, and return the model.
- `@model_validator(mode="before")` receives the raw input before any field is validated. Use it only to reshape that input, such as renaming a legacy key.
- Model validators hold input invariants only; business rules (availability, pricing, permissions) live in domain code.

## Bad Example

```python
class StayRequest(BaseModel):
    check_in: date
    check_out: date


def book(request: StayRequest, rooms: RoomStore) -> Booking:
    if request.check_out <= request.check_in:  # every caller must remember this
        raise ValueError("check_out must be after check_in")
    return rooms.reserve(request.check_in, request.check_out)
```

## Good Example

```python
class StayRequest(BaseModel):
    check_in: date
    check_out: date

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_keys(cls, data: object) -> object:
        if isinstance(data, dict) and "arrival" in data:  # older clients send arrival
            return {("check_in" if key == "arrival" else key): value for key, value in data.items()}
        return data

    @model_validator(mode="after")
    def check_dates(self) -> "StayRequest":
        if self.check_out <= self.check_in:
            raise ValueError(f"check_out {self.check_out} must be after check_in {self.check_in}")
        return self
```

## Notes

- Before or after:

| `mode="before"` | `mode="after"` |
| --- | --- |
| Raw input of any type: check it with `isinstance` | The typed, validated instance |
| Reshapes or renames input, then returns it | Checks an invariant, then returns `self` |
| Runs before field validation and `Field` limits | Sees defaults and every validated field |

- On Python 3.11 and later, annotate the after validator `-> Self` (`from typing import Self`); below 3.11, name the class in quotes as above.
- A check on one field is `pydantic-field-constraints`. A model validator does no I/O: checking that a room exists is the use case's job, after validation.

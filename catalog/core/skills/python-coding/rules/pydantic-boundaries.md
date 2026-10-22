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

# Validate untrusted data once, at the boundary

## Description

Data that crosses a trust boundary arrives in a shape nobody has checked yet: HTTP request bodies, queue messages, files, command-line input, environment variables and third-party API responses. Validate and coerce it there, once, with a Pydantic model that declares its constraints, and let the rest of the code trust the types it receives. This rule uses the Pydantic 2 API.

- Typed objects travel inward from the boundary. Domain code never receives a raw `dict` from it and never validates a model it was handed a second time.
- Parse instead of unpacking: `Model.model_validate(data)` for decoded data, `Model.model_validate_json(raw)` for JSON text or bytes, which parses and validates in one step.
- Catch `ValidationError` at the boundary that received the data and translate it there, once.

## Bad Example

```python
def register_signup(payload: dict, users: UserStore) -> UserId:
    # checks scattered by hand, easy to forget, no coercion, and the dict travels on
    if "email" not in payload or "@" not in payload["email"]:
        raise ValueError("invalid email")
    age = payload.get("age")
    if not isinstance(age, int) or age < 0:
        raise ValueError("invalid age")
    return users.create(payload["email"], age, payload.get("name", ""))
```

## Good Example

```python
class SignupMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailStr  # needs the email-validator extra
    age: int = Field(ge=0, le=150)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def handle_signup(raw: bytes, users: UserStore) -> UserId:  # the queue consumer: the boundary
    try:
        message = SignupMessage.model_validate_json(raw)
    except ValidationError as exc:
        raise MalformedMessage(f"signup message: {exc.error_count()} invalid fields") from exc
    return users.create(message.email, message.age, message.name)  # typed values inward
```

## Notes

- A dataclass suits internal records the code builds itself; a Pydantic model suits data from outside the process. Which one a boundary type is follows the house style (`python-house-style`).
- Never read a dict field by field (`payload["weight"]`) and build the model afterwards: that skips the coercion and the error report the model exists for. Raw dicts passed between functions and validation written as `if` statements are the two smells this rule removes.
- Never catch `ValidationError` deep in domain code: by then the data should already be typed, and catching it there hides where the bad input came from. FastAPI translates it for request models; a settings loader lets it stop the program at startup.
- Keep models thin: a model validates and serializes. It holds no business rules and does no I/O, so no database lookups in validators and no network calls in properties.
- `EmailStr` needs the `email-validator` package (the `pydantic[email]` extra); propose adding it when the repo lacks it, never add it unasked.
- Field limits, `Literal` sets and before-validators are `pydantic-field-constraints`; cross-field checks are `pydantic-model-validators`; configuration is `pydantic-typed-settings`.
- Separate request and response schemas for an HTTP API are the web-application skill's web-api-schemas rule, and FastAPI wiring is that skill's too.

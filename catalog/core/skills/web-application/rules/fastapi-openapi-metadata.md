---
id: fastapi-openapi-metadata
name: FastAPI OpenAPI metadata
description: "Document every route in the generated OpenAPI schema: a response model, the success status, a summary, router tags and every non-2xx outcome in responses=."
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
applies_if:
  has_framework: ["fastapi"]
section: api-conventions
priority: 65
tags: [python, fastapi, api]
---

# Document every route in the OpenAPI schema

## Description

FastAPI builds the OpenAPI schema, and the `/docs` and `/redoc` pages, from each route's signature and decorator. What the route does not declare, clients cannot see: a route that returns a bare dict documents no response body, a creation route without `status_code=201` documents a 200, and errors raised through the app's error table appear nowhere. Declare the response model, the success status, a one-line summary, the router's tags and every non-2xx outcome, so generated clients and readers of `/docs` get the contract the route really keeps.

## Bad Example

```python
router = APIRouter(prefix="/customers")  # no tags: every route lands under "default"


@router.post("")  # documented as 200, although the route creates a resource
async def create_customer(data: CustomerCreate, session: SessionDep) -> dict:
    # A dict documents no body and filters nothing: an internal field can leak.
    customer = await register_customer(session, data)
    return {"id": customer.id, "email": customer.email, "password_hash": customer.password_hash}
```

## Good Example

```python
from fastapi import APIRouter

# SessionDep is the per-request session alias; CustomerCreate and CustomerRead are
# the API schemas; register_customer raises DuplicateEmailError, which the app's
# error table maps to 409.
router = APIRouter(prefix="/customers", tags=["customers"])


@router.post(
    "",
    status_code=201,
    summary="Register a customer",
    responses={
        409: {"description": "A customer with this email already exists"},
    },
)
async def create_customer(data: CustomerCreate, session: SessionDep) -> CustomerRead:
    """Register a customer by name and email and return it with its generated id.

    The docstring becomes the route's description in the docs.
    """
    customer = await register_customer(session, data)
    return CustomerRead.model_validate(customer, from_attributes=True)
```

## Notes

- The return annotation (or `response_model=` when the function returns something else) both documents the body and filters it: fields missing from `CustomerRead` never reach the client.
- `summary=` is the short line in the endpoint list; the docstring is the long description; router `tags=` group the endpoints in the sidebar. Every route gets a response model and every router gets tags.
- A duplicate is a conflict: document it as 409, not 400. `responses=` lists exactly the statuses the app's error table can produce for this route, plus 401 or 403 when the route is protected; FastAPI documents its own 422 for invalid input. When the table and `responses=` disagree, the schema lies: keep them in step (see `fastapi-error-boundaries`).
- Never write `responses=` entries for statuses the route cannot return, and never document a 500.
- `/docs` (Swagger UI) and `/redoc` come for free from this metadata; check them after adding or renaming a route.
- The example app's examples/fastapi-hotel-api/app/routers/bookings.py sets `status_code`, `summary` and `responses=` to match its error table.

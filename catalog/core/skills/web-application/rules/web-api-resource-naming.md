---
id: web-api-resource-naming
name: Resource naming
description: "Name URLs after resources: plural nouns, ids in the path, one level of nesting, one case style, and a version prefix only for breaking changes."
version: 1
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: api-conventions
priority: 64
tags: [python, web, api]
---

# Name URLs after resources, not actions

## Description

A URL names a resource; the HTTP method says what happens to it. Collections are plural nouns (`/invoices`), a single resource is the collection plus its id in the path (`/invoices/{invoice_id}`), and a relationship nests under its parent (`/invoices/{invoice_id}/lines`). Verbs in paths (`/getInvoice`, `/invoices/{invoice_id}/delete`) duplicate the method, and every client has to learn each endpoint's private grammar. Pick one case style for multi-word segments, kebab-case or snake_case, and use it in every path. Clients learn one pattern and can guess the next URL.

## Bad Example

```python
router = APIRouter()  # no prefix: each route spells its own resource name


@router.get("/getInvoices")  # verb and camelCase in the path
async def get_invoices() -> list[InvoiceRead]: ...


@router.get("/invoice/{id}")  # singular here, plural above; a bare `id`
async def get_invoice(id: UUID) -> InvoiceRead: ...


@router.post("/invoice/{id}/delete")  # the action belongs to the method
async def delete_invoice(id: UUID) -> None: ...


@router.get("/invoice/{id}/line_items")  # snake_case here, kebab-case elsewhere
async def list_lines(id: UUID) -> list[InvoiceLineRead]: ...
```

## Good Example

```python
from uuid import UUID

from fastapi import APIRouter, FastAPI

# InvoiceRead, InvoiceLineRead, PaymentCreate and PaymentRead are the API schemas;
# Settings is the app's typed settings class.
router = APIRouter(prefix="/invoices")  # the prefix matches the resource


@router.get("")
async def list_invoices() -> list[InvoiceRead]: ...


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: UUID) -> InvoiceRead: ...


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(invoice_id: UUID) -> None: ...


@router.get("/{invoice_id}/lines")
async def list_invoice_lines(invoice_id: UUID) -> list[InvoiceLineRead]: ...


# An action that is not CRUD becomes a sub-resource the client creates.
@router.post("/{invoice_id}/payments", status_code=201)
async def pay_invoice(invoice_id: UUID, payment: PaymentCreate) -> PaymentRead: ...


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")  # the version is a path prefix
    return app
```

## Notes

- Name path parameters after the resource (`invoice_id`, not `id`), so nested paths stay unambiguous.
- Nest one level deep. Below that, address the child by its own id (`/lines/{line_id}`) instead of `/customers/{customer_id}/invoices/{invoice_id}/lines/{line_id}`.
- Put each resource's routes in its own module (`app/routers/invoices.py`) with a router prefix per resource; the app factory only includes the routers. Follow the repo's existing layout axis (by feature or by layer) rather than introducing a second one. Router tags are `fastapi-openapi-metadata`'s.
- Use one format everywhere for dates (ISO 8601), ranges, query parameter names and pagination, so a client written for one endpoint works for the next.
- Version only for breaking changes (a removed or renamed field, a changed type or meaning). A new optional field or a new endpoint needs no new version. Mount each version as a path prefix (`/v1`, `/v2`) on the same routers or on per-version routers.
- Which method and success status each route uses is `web-http-methods`'.
- Flask blueprints (`url_prefix=`) and Django `include()` follow the same naming: plural nouns, ids in the path, one case style.

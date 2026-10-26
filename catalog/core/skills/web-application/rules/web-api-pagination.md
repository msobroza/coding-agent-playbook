---
id: web-api-pagination
name: Web API pagination
description: "Bound and paginate every list endpoint: a server-enforced maximum page size, a stable order, keyset cursors and one page shape."
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/services/**/*.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: api-design
priority: 42
tags: [python, web, api]
---

# Bound and paginate every list endpoint

## Description

An endpoint that returns every matching row works in development and fails once the table grows: the database scans, the worker holds every row, and the client downloads megabytes. Every collection endpoint needs a server-enforced maximum page size and a stable sort order. Prefer keyset pagination, `WHERE id > :cursor ORDER BY id LIMIT :n`, which stays fast on deep pages and does not skip or repeat rows while data changes.

## Bad Example

```python
router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


@router.get("")
async def list_invoices(
    user: CurrentUser, session: SessionDep, limit: int | None = None
) -> list[InvoiceRead]:
    stmt = select(Invoice).where(Invoice.owner_id == user.id)
    if limit:
        stmt = stmt.limit(limit)  # the client decides: 10_000_000, or no limit at all
    return [InvoiceRead.model_validate(invoice) for invoice in await session.scalars(stmt)]
```

## Good Example

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

# Invoice is the ORM model and InvoiceRead its response schema; get_current_user is
# the auth provider, and SessionDep and CurrentUser are the app's Annotated aliases.
router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


class InvoicePage(BaseModel):
    items: list[InvoiceRead]
    next_cursor: int | None  # sent back as ?cursor= to get the next page


@router.get("")
async def list_invoices(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: int | None = None,
) -> InvoicePage:
    stmt = (
        select(Invoice)
        .where(Invoice.owner_id == user.id)
        .order_by(Invoice.id)
        .limit(limit + 1)  # one extra row tells whether another page exists
    )
    if cursor is not None:
        stmt = stmt.where(Invoice.id > cursor)
    invoices = list(await session.scalars(stmt))
    page = invoices[:limit]
    next_cursor = page[-1].id if len(invoices) > limit else None
    return InvoicePage(
        items=[InvoiceRead.model_validate(invoice) for invoice in page],
        next_cursor=next_cursor,
    )
```

## Notes

- Every list endpoint returns the same page envelope (here `items` and `next_cursor`), so clients page through every collection the same way.
- Order by a unique key so pages are deterministic. For a composite key such as `(created_at, id)`, compare with `tuple_(Invoice.created_at, Invoice.id) > (cursor_created_at, cursor_id)`.
- Encode composite cursors as opaque base64 strings so clients pass them back instead of building them, and validate them when decoding.
- Avoid `COUNT(*)` totals on every request for large tables; `next_cursor` is enough to drive "load more".
- Offset pagination (`offset` and `limit`, both bounded) is acceptable for small, admin-style lists.
- Exports follow the same rule: stream them (`StreamingResponse` over `session.stream_scalars(...)`) or generate them in a background job; never load an unbounded query into memory.
- Index the filter and keyset columns together, for example `(owner_id, id)`.
- `limit` is the only query-parameter constraint shown here; constraints and defaults for the others are `fastapi-query-parameters`'.

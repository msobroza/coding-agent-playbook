---
id: fastapi-query-parameters
name: FastAPI query parameters
description: "Give query parameters defaults for the common case and bound every one with Query() constraints or a closed set of values."
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/deps.py"
  - "**/dependencies.py"
applies_if:
  has_framework: ["fastapi"]
section: api-conventions
priority: 63
tags: [python, fastapi, api]
---

# Give query parameters sensible defaults and bounds

## Description

Design query parameters so the common call needs the fewest arguments: a parameter whose value is almost always the same gets that value as its default instead of being required. Bound every parameter where it is declared, with `Annotated[..., Query(...)]` constraints (`ge`, `le`, `gt`, `min_length`, `max_length`) or a closed set of values, so FastAPI rejects out-of-range input with a 422 before the route runs and no separate model is needed for simple parameters. An unbounded `int` or `str` lets one request ask for a million rows or send a megabyte of search text.

## Bad Example

```python
@router.get("/transactions")
async def list_transactions(
    since: datetime,  # required, although callers almost always want "the last day"
    until: datetime,  # required, although callers almost always want "now"
    limit: int,  # required and unbounded: limit=10_000_000 reaches the query
    status: str = "",  # any string; a typo silently matches nothing
) -> list[TransactionRead]: ...


@router.get("/convert")
async def convert(from_currency: str, to_currency: str, amount: float) -> ConversionRead: ...
```

## Good Example

```python
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query

# ClockDep is the app's injected clock (now() returns an aware UTC datetime);
# TransactionRead and ConversionRead are the response models.
router = APIRouter(prefix="/transactions", tags=["transactions"])
conversions = APIRouter(prefix="/conversions", tags=["conversions"])

TransactionStatus = Literal["pending", "settled", "failed"]
CurrencyCode = Annotated[str, Query(pattern=r"^[A-Z]{3}$")]  # ISO 4217, e.g. "EUR"


@router.get("")
async def list_transactions(
    clock: ClockDep,
    since: datetime | None = None,  # None: one day before until
    until: datetime | None = None,  # None: now, from the injected clock
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: TransactionStatus | None = None,  # any other value answers 422
) -> list[TransactionRead]:
    end = until or clock.now()
    start = since or end - timedelta(days=1)
    ...


@conversions.get("")
async def convert(
    from_currency: CurrencyCode,
    to_currency: CurrencyCode,
    amount: Annotated[Decimal, Query(gt=0)],
) -> ConversionRead: ...
```

## Notes

- Never default to `datetime.now()`: it is naive and read at a hidden moment. Default to `None` and resolve it from the injected clock, so tests pin the time.
- Use a `Literal` or an `Enum` for a closed set of values, and `Decimal` for amounts, never `float`.
- Parameters shared by many routes (pagination, filters, the current tenant) live in one provider whose `Annotated` alias each route declares; see `fastapi-dependency-providers`.
- Page size limits and the paged response shape are `web-api-pagination`'s; sort keys that map onto columns are `sqlalchemy-bound-parameters`'.
- Invalid values get FastAPI's own 422 with the failing field named; do not re-check them in the route body.
- A free-text parameter such as a search term gets both a `min_length` and a `max_length`, so an empty or oversized term answers 422 instead of reaching the query.
- The example app's examples/fastapi-hotel-api/app/routers/rooms.py takes a bounded `limit` and `offset` with defaults.

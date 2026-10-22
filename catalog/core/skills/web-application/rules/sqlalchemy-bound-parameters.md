---
id: sqlalchemy-bound-parameters
name: Bound SQL parameters
description: "Never build SQL with string formatting: bind every value and map sort fields onto a fixed set of columns."
scope: scoped
globs:
  - "**/models.py"
  - "**/models/**/*.py"
  - "**/db/**/*.py"
  - "**/database.py"
  - "**/repositories/**/*.py"
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/services/**/*.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
  any_dependency: ["sqlalchemy", "alembic"]
section: database
priority: 25
tags: [python, sqlalchemy, database, security]
---

# Never build SQL with string formatting

## Description

SQL built with f-strings, `%`, `+` or `.format()` from request data is injectable, even for values that look harmless such as ids, search terms and sort fields; wrapping the string in `text()` does not help. Use SQLAlchemy expressions, which always bind values, or `text()` with named `:params` for hand-written SQL. Identifiers such as column names cannot be bound: map user input onto a fixed set of columns.

## Bad Example

```python
from sqlalchemy import text

router = APIRouter(prefix="/users")


@router.get("/search")
async def search_users(q: str, sort: str, session: SessionDep) -> list[UserRead]:
    result = await session.execute(
        text(f"SELECT id, email FROM users WHERE email LIKE '%{q}%' ORDER BY {sort}")
    )
    return [UserRead.model_validate(row, from_attributes=True) for row in result]
```

## Good Example

```python
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# SessionDep is the per-request AsyncSession alias; User the ORM model; UserRead its schema.
router = APIRouter(prefix="/users")

UserSort = Literal["email", "created_at"]
SORT_COLUMNS = {"email": User.email, "created_at": User.created_at}


@router.get("/search")
async def search_users(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    session: SessionDep,
    sort: UserSort = "email",  # anything else is rejected with 422
) -> list[UserRead]:
    stmt = (
        select(User)
        .where(User.email.icontains(q, autoescape=True))  # bound; % and _ literal
        .order_by(SORT_COLUMNS[sort])
        .limit(50)
    )
    return [UserRead.model_validate(user) for user in await session.scalars(stmt)]


# Hand-written SQL: bind values, never interpolate them
async def count_recent_logins(session: AsyncSession, since: datetime) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM users WHERE last_login_at >= :since"),
        {"since": since},
    )
    return result.scalar_one()
```

## Notes

- Binding works for values only. `ORDER BY :column` sorts by a constant string; use a `Literal` or an `Enum` plus a mapping to column objects for sortable fields.
- For `IN` lists use `User.id.in_(ids)`, or `bindparam("ids", expanding=True)` inside `text()`.
- Bound parameters stop injection, but `%` and `_` in a `LIKE` pattern are still wildcards; `contains`, `icontains`, `startswith` and `endswith` accept `autoescape=True`.
- `literal_column()` and `text()` fragments inside ORM queries are inserted verbatim; never feed them request data.
- Plain DB-API drivers bind the same way with their own placeholder (`%s`, `?`, `$1`) and a separate parameters argument; never format the values into the query string.
- Ruff `S608` flags SQL built from strings.

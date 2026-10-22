---
id: alembic-migrations
name: Alembic migrations
description: "Change the schema through reviewed Alembic revisions run once per deploy, never with create_all at startup."
scope: scoped
globs:
  - "alembic.ini"
  - "**/alembic/**/*.py"
  - "**/migrations/**/*.py"
  - "**/models.py"
  - "**/models/**/*.py"
  - "**/db/**/*.py"
  - "**/database.py"
  - "**/repositories/**/*.py"
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
  any_dependency: ["sqlalchemy", "alembic"]
section: database
priority: 29
tags: [python, alembic, sqlalchemy, database]
---

# Change the schema with Alembic migrations

## Description

`Base.metadata.create_all()` only creates missing tables. It never adds a column, changes a type or adds an index, so development, CI and production drift apart without an error, and calling it at startup makes every worker race to change the schema. Manage the schema with Alembic: autogenerate a revision from model changes, review it, commit it with the code, and run `alembic upgrade head` as a deploy step.

## Bad Example

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_async_engine(settings.database_url.get_secret_value())
    async with engine.begin() as conn:
        # new columns never reach existing tables
        await conn.run_sync(Base.metadata.create_all)
    yield


# A one-off fix nobody can reproduce
async with engine.begin() as conn:
    await conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at timestamptz"))
```

## Good Example

```python
# app/models.py: deterministic constraint names so migrations can alter them
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

```python
# migrations/env.py, created by `alembic init -t async migrations`
import os

from app.models import Base

# configparser treats % as interpolation, so escape it in URL-encoded passwords
database_url = os.environ["APP_DATABASE_URL"].replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata
```

```bash
alembic revision --autogenerate -m "add last_login_at to users"
# review migrations/versions/<rev>_add_last_login_at_to_users.py, then commit it
alembic upgrade head   # deploy step, before new app instances start
alembic check          # CI: fails when models have changes without a migration
```

## Notes

- Web apps build the DB engine in the app factory or lifespan; scripts and CLIs may still build it at import time. `migrations/env.py` is such an entry-point script, so it may read the URL from the environment.
- Autogenerate produces a draft. It sees a renamed column as drop plus add (data loss) and misses some type and server default changes; read every revision before committing it.
- Keep migrations compatible with the code that is still running during a deploy: add a nullable column, backfill it, and add `NOT NULL` in a later release (expand, migrate, contract).
- On large PostgreSQL tables, create indexes with `op.create_index(..., postgresql_concurrently=True)` inside `with op.get_context().autocommit_block():` to avoid locking writes.
- Tests may build their schema with `create_all` on a fresh database for speed (`sqlalchemy-test-rollback`), as long as CI also runs `alembic upgrade head` or `alembic check`.
- Do not let several app replicas run `upgrade` at startup; run it once per deploy as a separate job.
- A repo that uses SQLAlchemy without Alembic gets a proposal to add it through the project's package manager, never an unasked dependency.

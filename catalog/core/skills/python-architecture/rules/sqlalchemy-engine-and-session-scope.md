---
id: sqlalchemy-engine-and-session-scope
name: Engine and session scope
description: "Build the engine and sessionmaker in the entry point from settings, open one session per job run or command, close it on every path, and let migrations own the schema."
version: 1
scope: scoped
globs:
  - "**/db/**/*.py"
  - "**/db.py"
  - "**/database.py"
  - "**/session.py"
  - "**/persistence/**/*.py"
  - "**/infrastructure/**/*.py"
  - "**/main.py"
  - "**/__main__.py"
  - "**/cli.py"
  - "**/worker.py"
applies_if:
  any_framework: ["sqlalchemy", "alembic"]
section: persistence
priority: 48
tags: [python, sqlalchemy, database]
---

# Scope the engine to the entry point and the session to one run

## Description

The engine is a connection pool shared by the whole process; a session is one conversation with the database. Build the engine and its `sessionmaker` once, in the entry point (the composition root), from settings read there. Web apps build the DB engine in the app factory or lifespan; scripts and CLIs may still build it at import time. Nothing connects, opens a session or calls the network at import time.

In a job, worker or CLI, open one session per job run or command from that `sessionmaker`, hand it out from a context manager so it closes on every path, and commit in the use case or its unit of work. Never share one session between runs, threads or tasks.

## Bad Example

```python
# db/database.py, imported by every job of a worker
SQLALCHEMY_DATABASE_URL = "postgresql://app@db.example.com/app"  # hard-coded
engine = create_engine(SQLALCHEMY_DATABASE_URL)
Base = declarative_base()  # legacy declarative API
session = sessionmaker(bind=engine)()  # one session shared by every job, never closed

# worker.py
Base.metadata.create_all(engine)  # the schema built at startup instead of by migrations
```

Building the engine at import time is allowed for a script or CLI. The defects are the shared, never-closed session, the hard-coded URL (and its usual fix, a module-level `settings = Settings()` that this module imports), and `create_all` in production.

## Good Example

```python
class SqlLendingUnitOfWork:
    _session: Session  # opened in __enter__, one per unit of work
    tools: SqlToolRepository
    loans: SqlLoanRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> "SqlLendingUnitOfWork":
        self._session = self._session_factory()
        self.tools = SqlToolRepository(self._session)
        self.loans = SqlLoanRepository(self._session)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._session.rollback()  # a no-op after commit(); undoes everything otherwise
        self._session.close()

    def commit(self) -> None:
        self._session.commit()


def main() -> None:  # the worker's entry point
    settings = Settings()  # read once, fails at startup when a value is missing
    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    for job in pending_jobs(settings):
        with SqlLendingUnitOfWork(session_factory) as uow:  # one session per job run
            run_job(uow, job)
```

## Notes

- Convert rows to records while the session is open: a lazy relationship touched after `close()` raises `DetachedInstanceError`. `expire_on_commit=False` keeps already loaded attributes readable after a commit.
- With `AsyncSession` and `async_sessionmaker`, never share one session between concurrently running tasks: each task opens its own.
- Migrations own the production schema; `Base.metadata.create_all` belongs in tests and throwaway local setups. Mapped classes use the 2.0 typed `DeclarativeBase` with `Mapped` and `mapped_column`.
- In a web app, the per-request session, its provider and its teardown are the web-application skill's sqlalchemy-session-per-request and sqlalchemy-transaction-boundary rules.
- Where the root lives is arch-composition-root; how settings load is the python-coding skill's pydantic-typed-settings rule.

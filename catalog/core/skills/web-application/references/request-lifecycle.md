# Request lifecycle

A map of one FastAPI request, step by step, for deciding where a change or a failure belongs. Each step lists what happens there, the rules that own it and the hotel example file that shows it (paths are inside examples/fastapi-hotel-api). The rules hold the detail; this map only routes to them.

Rule ids from this skill are given bare; rules of other skills carry their skill name. A rule whose gate fails in this repository (for example the database rules when the project has no SQLAlchemy or Alembic) is absent from the skill's index: skip it here too.

## How to read this map

- Find the step where the code runs or the failure surfaces, then open one to three of its rules.
- A change that spans steps (a new endpoint) follows add-an-endpoint.md instead.
- The last section routes common symptoms to the step and rules that fix them.

## 1. Startup

What happens: typed settings are read once; `create_app(settings)` builds the app; the lifespan acquires the engine, the sessionmaker and shared clients before `yield` and releases them after it.

- Rules: fastapi-app-wiring, sqlalchemy-session-per-request (engine and sessionmaker in the lifespan), httpx-shared-client (one client per upstream), web-cors-origins (middleware from settings); python-coding's pydantic-typed-settings.
- Not here: creating tables. The schema comes from reviewed migrations (alembic-migrations).
- Example: app/settings.py, app/main.py, app/asgi.py.

## 2. Each request: middleware and providers

What happens: middleware stamps a request id; FastAPI resolves the route's dependencies: the session, the current user, ports built from the session, the clock and id factories.

- Rules: fastapi-request-id-logging, fastapi-dependency-providers, sqlalchemy-session-per-request (one session per request, closed on every path), web-jwt-validation (the current user), web-object-authorization (authentication at the router level).
- Example: app/deps.py.

## 3. The route

What happens: FastAPI parses the path, query and body into request models; the route calls one use case and converts its result into the response model and success code.

- Rules: fastapi-thin-routes, web-api-schemas, fastapi-query-parameters, web-api-pagination, web-http-methods, web-api-resource-naming, fastapi-openapi-metadata.
- An `async def` route awaits only non-blocking calls; blocking work runs in a plain `def` route or a thread (fastapi-no-blocking-calls).
- Example: app/routers/ (rooms.py, customers.py, bookings.py and schemas.py).

## 4. The use case and its repositories

What happens: the use case loads records through repositories, applies the business rules, writes, and commits once; repositories add and flush but never commit.

- Rules: sqlalchemy-transaction-boundary, sqlalchemy-2-style, sqlalchemy-eager-loading, sqlalchemy-bound-parameters, web-object-authorization (owner-scoped queries).
- Auth use cases: web-password-hashing, web-secure-tokens.
- Other skills: python-architecture's arch-use-case-functions, arch-unit-of-work and sqlalchemy-repositories.
- Example: app/operations/, app/db/.

## 5. The error boundary

What happens: a domain error raised anywhere above leaves the route and meets one table that maps it to a status code and one body shape; an unmapped error becomes a 500.

- Rules: fastapi-error-boundaries (the table), web-http-methods (success codes), fastapi-openapi-metadata (`responses=` lists the outcomes); python-coding's python-error-boundaries.
- Example: app/main.py, app/domain/errors.py.

## 6. Teardown and shutdown

What happens: after the response, the session dependency closes the session and drops uncommitted work; at shutdown the lifespan disposes the engine and closes shared clients.

- Rules: sqlalchemy-session-per-request, fastapi-app-wiring, httpx-shared-client.

## 7. Which test covers which step

Unit tests use fakes; persistence and endpoint tests use the real engine in a rolled-back transaction.

- Steps 3 and 5 through the app: fastapi-dependency-overrides (fresh app per test, override only out-of-process dependencies).
- Steps 4 and 6 on the database: sqlalchemy-test-rollback.
- Which layer gets which test: python-architecture's arch-tests-by-layer.
- Example: tests/.

## Symptom to step

| Symptom | Step | Rules |
| --- | --- | --- |
| A duplicate or a lost race answers 500 | 4, 5 | fastapi-error-boundaries |
| `DetachedInstanceError` or expired attributes after commit | 1, 4 | sqlalchemy-session-per-request, sqlalchemy-eager-loading |
| `PendingRollbackError` on the next statement | 4 | sqlalchemy-transaction-boundary |
| Writes that vanish after a 2xx | 4, 6 | sqlalchemy-transaction-boundary |
| Requests that stall under load | 3, 1 | fastapi-no-blocking-calls, httpx-shared-client |
| A test override that has no effect | 7 | fastapi-dependency-overrides |
| A lazy load raising while the response model is built | 4 | sqlalchemy-eager-loading |
| A 400 where a 409 or 422 belongs | 5 | fastapi-error-boundaries, web-http-methods |

# Hotel API: a worked FastAPI service

A small hotel lets registered customers book its rooms. This FastAPI and SQLAlchemy 2 service adds and edits rooms, registers customers, books a room for a stay and cancels a booking. It sits at step 3 of the persistence steps: booking a room reads the room and the customer, checks that the nights are free, writes the booking with one row per night, and must commit all of it once. A service with no operation like that would stop at step 1, with an injected session and no ports.

Copy one flow end to end from here, from the settings to the repository, the error table and the tests at each layer.

## Contents

- The tree and its layers
- One request, walked through
- The double-booking race
- What each choice shows
- Tests by layer
- Which file shows which rule
- What the example leaves out
- How to run it

## The tree and its layers

The tree is laid out by layer. python-architecture's layer_map.py script, run over this directory, sorts every module into a layer and reports no violations and no import cycles.

```text
app/
  settings.py            typed settings read from HOTEL_* variables (unlayered)
  main.py                composition root: create_app, the lifespan, the error table
  asgi.py                the ASGI entry point, the only place that reads the environment (unlayered)
  deps.py                composition root: per-request providers and their aliases
  domain/model.py        domain: frozen records, the stay and the pricing rule
  domain/errors.py       domain: the error hierarchy
  operations/ports.py    application: the repository and unit-of-work ports
  operations/room.py     application: room use cases
  operations/customer.py application: customer use cases
  operations/booking.py  application: booking use cases
  db/models.py           infrastructure: mapped tables and the partial unique index
  db/repositories.py     infrastructure: SQL repositories and the unit of work
  routers/schemas.py     interface: request and response models
  routers/rooms.py       interface: room routes
  routers/customers.py   interface: customer routes
  routers/bookings.py    interface: booking routes
tests/
  conftest.py            the real engine, a rolled-back session per test, factories, the client
  fakes.py               in-memory fakes of every port
  test_operations.py     use-case tests on the fakes
  test_repositories.py   one contract suite over the fakes and the SQL repositories
  test_api.py            endpoint tests on the real engine
```

There are no `__init__.py` files: `app` and `tests` are namespace packages, and the pytest configuration puts the example root on the import path.

## One request, walked through

A POST to /bookings, from startup to the response:

1. Startup. The ASGI server loads `app.asgi:app`, which reads `Settings` from the environment once and passes them to `create_app`. The lifespan builds the async engine and an `async_sessionmaker` with `expire_on_commit=False` from those settings, keeps the sessionmaker on `app.state`, and disposes of the engine on shutdown. Nothing connects at import time, and the app never creates tables.
2. Providers. `get_session` opens one `AsyncSession` for the request inside `async with`, so it closes on every path. `get_hotel` wraps it in `SqlHotelUnitOfWork`, typed as the `HotelUnitOfWork` port. `today_utc` and `id_factory` hand the route today's date and the id factory.
3. The route. `book_room` in routers/bookings.py receives the validated `BookingCreate` and the `HotelDep`, `TodayDep` and `NewIdDep` aliases, calls the `book_room` use case, and converts the returned record with `BookingRead`.
4. The use case. It loads the room and the customer, builds the `Stay`, refuses a check-in before today, asks whether every night is free, prices the booking in integer cents, adds it and commits once through the unit of work.
5. The repositories. `SqlBookingRepository.add` adds the booking with one `RoomNightRow` per night and flushes; `SqlHotelUnitOfWork.commit` is the only commit.
6. The response. The route answers 201 with a Location header that names the new booking.

Each failure path ends at the one error table in `create_app`: an unknown room or customer raises a `NotFoundError` subclass and answers 404; a night already taken raises `RoomUnavailableError`, a `ConflictError`, and answers 409; an empty, reversed or past stay raises `InvalidStayError` and answers 422. Every mapped error has the body `{"detail": message}`. A `HotelError` subclass missing from the table is re-raised, and the default handler answers a plain 500.

## The double-booking race

The availability check and the insert run in one transaction, yet two simultaneous requests can both see a free room. The partial unique index `one_active_booking_per_room_night`, on the room and the night of every active booking, closes that race in the database: the losing insert breaks it. `SqlBookingRepository.add` turns that `IntegrityError` into `RoomUnavailableError`, so the loser gets the same 409 as a request refused by the check, instead of a 500. The index's WHERE clause skips cancelled nights, so a cancelled booking's nights can be booked again. `SqlCustomerRepository.add` does the same for the unique email with `DuplicateEmailError`.

## What each choice shows

- Typed records cross every boundary. The only `dict` on the request path is the PATCH body's `model_dump(exclude_unset=True)`, unpacked into `RoomChanges` in the route that produced it.
- `exclude_unset`, not `exclude_none`, is what lets a PATCH tell "leave `notes` alone" (key absent) from "clear `notes`" (explicit null). A field that may not be cleared, such as the room number, rejects an explicit null in its schema.
- `get_session` closes the session on every path, and use cases commit explicitly, so nothing depends on when provider teardown runs.
- The lifespan builds the engine from the settings passed to `create_app`, so tests build their own app from their own settings and never import app/asgi.py.
- Domain errors are mapped in one table, looked up along the class hierarchy. A subclass missing from it answers 500, and no HTTP type appears below the routes.
- Driver errors stop at the repository. The fakes raise the same domain errors as the SQL repositories, so a lost race and an ordinary refusal both answer 409.
- Use cases receive today's date and the id factory as parameters, so they never read a clock or generate ids, and their tests are deterministic.
- Money is integer cents everywhere, from the schema to the column.

## Tests by layer

Unit tests use fakes; persistence and endpoint tests use the real engine in a rolled-back transaction.

- test_operations.py runs the use cases on `FakeHotelUnitOfWork`, which counts commits, so a refused booking can show that it committed nothing.
- test_repositories.py runs one contract suite twice, against the fakes and against the SQL repositories in the rolled-back transaction. On the SQL side the overlap test calls the repository directly, without the use case's check, so the partial unique index and the error translation are what refuse it.
- test_api.py drives the real app through `httpx.ASGITransport` with `get_session` and `today_utc` overridden, so every request shares the test's session. It covers what the edge adds: status codes, the Location header, the error body and request validation. Its last test is a route-layer test with no database and no fake: a fresh app with one throwaway route that raises a domain error missing from the table, expecting a 500.

The engine fixture reads HOTEL_TEST_DATABASE_URL when it is set, so the same tests can run against PostgreSQL; otherwise it uses a SQLite file in a temporary directory. The async tests run on AnyIO's pytest plugin, which FastAPI already installs.

## Which file shows which rule

Rule ids are this skill's; a rule from another skill is followed by that skill's name.

| File | Rules it demonstrates |
| --- | --- |
| pyproject.toml | python-pyproject-dependencies (python-tooling), pytest-configuration (python-tooling) |
| app/settings.py | pydantic-typed-settings, pydantic-special-types and python-no-global-singletons (python-coding) |
| app/main.py | fastapi-app-wiring, fastapi-error-boundaries, sqlalchemy-session-per-request; arch-composition-root (python-architecture); python-error-boundaries (python-coding) |
| app/asgi.py | fastapi-app-wiring; arch-composition-root (python-architecture) |
| app/deps.py | fastapi-dependency-providers, sqlalchemy-session-per-request; python-dependency-injection and python-pure-core (python-coding) |
| app/domain/model.py | arch-rich-domain-model, arch-typed-records-across-layers (python-architecture); python-frozen-dataclasses, python-dataclass-post-init (python-coding) |
| app/domain/errors.py | fastapi-error-boundaries; python-custom-exceptions (python-coding) |
| app/operations/ports.py | arch-ports, arch-repository-port, arch-unit-of-work (python-architecture); python-protocols (python-coding) |
| app/operations/*.py | sqlalchemy-transaction-boundary; arch-use-case-functions (python-architecture) |
| app/db/models.py | sqlalchemy-2-style, sqlalchemy-eager-loading, alembic-migrations |
| app/db/repositories.py | sqlalchemy-bound-parameters, sqlalchemy-transaction-boundary; sqlalchemy-repositories, arch-unit-of-work (python-architecture) |
| app/routers/schemas.py | web-api-schemas; pydantic-boundaries, pydantic-field-constraints (python-coding) |
| app/routers/*.py | fastapi-thin-routes, web-http-methods, web-api-pagination, fastapi-query-parameters, fastapi-openapi-metadata, web-api-resource-naming, fastapi-no-blocking-calls |
| tests/conftest.py | sqlalchemy-test-rollback, fastapi-dependency-overrides; pytest-fixtures, pytest-factory-fixtures (python-testing) |
| tests/fakes.py | pytest-test-doubles (python-testing); arch-test-use-cases-with-fakes (python-architecture) |
| tests/test_operations.py | pytest-parametrize, pytest-assertions, pytest-deterministic-tests (python-testing); arch-tests-by-layer (python-architecture) |
| tests/test_repositories.py | sqlalchemy-test-rollback; arch-contract-tests-for-fakes (python-architecture); pytest-edge-cases (python-testing) |
| tests/test_api.py | fastapi-dependency-overrides, fastapi-error-boundaries, web-http-methods; arch-tests-by-layer (python-architecture) |

## What the example leaves out

- Authentication and authorization: every route here is public. The Security section's rules (web-jwt-validation, web-object-authorization, web-password-hashing, web-secure-tokens, web-cors-origins) cover them.
- Outbound HTTP calls: httpx-shared-client.
- Request-id logging: fastapi-request-id-logging.
- Migrations: the tests build their schema with `create_all`; a real service gets it from Alembic revisions (alembic-migrations), and the naming convention on `Base` keeps constraint names stable for them.

## How to run it

In this directory, run `uv run pytest`, then `uv run mypy`: uv builds a throwaway environment from pyproject.toml, with the runtime dependencies and the dev group. Without uv, install the dependencies that pyproject.toml lists into a virtual environment and run `pytest` and `mypy` from here. To serve it, set HOTEL_DATABASE_URL, create the schema, and point an ASGI server at `app.asgi:app`.

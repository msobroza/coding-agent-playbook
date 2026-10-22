# Add an endpoint

The steps for adding an endpoint, or a whole new resource, to a FastAPI service, in the order the layers depend on each other. Each step names the rule in this skill that holds the detail; read that rule before writing the step's code. Work through the steps without stopping for questions: read the repository first and follow what it already does.

## Before you start

- Read the existing layout: where the routers, use cases, repositories, ORM models, schemas and tests live, and how they are named. Put the new files on the same axis (by layer or by feature) and in the same style; do not start a second layout.
- Decide which operations the resource needs (create, read, list, partial update, delete or a custom action) from the request, and add only those.
- For a brand-new service, lay it out like the hotel example in examples/fastapi-hotel-api (app/ with routers, operations, domain and db, plus tests/), on the axis the repository already uses, and add its dependencies to `pyproject.toml` through the project's package manager.

## Steps

1. **Schemas.** Add a Create model, a Read model and, for partial updates, a Patch model whose fields default to unset; Create and Patch forbid unknown keys, and the Read model lists exactly what clients may see (`web-api-schemas`). Never return an ORM object or a dict.
2. **ORM model and migration.** Declare the table with `DeclarativeBase`, `Mapped` and `mapped_column` (`sqlalchemy-2-style`), then generate an Alembic revision, review it and commit it with the code; the app never calls `create_all` (`alembic-migrations`).
3. **Use case.** Write one function per operation that takes its collaborators as parameters (a repository or unit-of-work port, the clock, an id factory) and plain values, knows nothing of HTTP, raises domain errors, and commits once (`sqlalchemy-transaction-boundary`).
4. **Providers.** Build every per-request collaborator in a `Depends` provider and declare it once as an `Annotated` alias next to the other providers; the providers are the composition root, never the route body (`fastapi-dependency-providers`).
5. **Router.** Add an `APIRouter` with the resource's prefix and tags. Each route declares its inputs and return type, calls one use case and converts the result (`fastapi-thin-routes`):
   - the method and success code match the operation: POST answers 201 with a `Location` header, PATCH updates partially, DELETE answers 204 (`web-http-methods`);
   - the path is a plural noun with the id in it and at most one level of nesting (`web-api-resource-naming`);
   - a list route is bounded and paginated, in a stable order (`web-api-pagination`), and its query parameters have defaults and `Query()` bounds (`fastapi-query-parameters`);
   - every query that loads a record by an id the client sent is scoped to the caller's owner or tenant, and a record the caller may not see answers 404 (`web-object-authorization`).
6. **Error table.** Give each new failure a domain exception under the project's base error and one row in the app's error mapping (not found 404, conflict 409, invalid 422); no `try`/`except` in the route (`fastapi-error-boundaries`). Declare the non-2xx outcomes in the route's `responses=` and give it a `summary` (`fastapi-openapi-metadata`).
7. **Wiring.** Call `include_router` for the new router inside `create_app`; the factory only includes routers and builds lifespan resources (`fastapi-app-wiring`).
8. **Tests.** Unit tests use fakes; persistence and endpoint tests use the real engine in a rolled-back transaction.
   - Use-case tests run on named in-memory fakes of the ports (`InMemoryRoomRepository`, not a generic dict-backed stub) that raise the same domain errors as the real repositories.
   - Endpoint tests build a fresh `create_app(test_settings)`, override only out-of-process dependencies and the clock, and call the app through `httpx.ASGITransport` (`fastapi-dependency-overrides`), on a session inside an outer transaction rolled back after each test (`sqlalchemy-test-rollback`).
   - Cover the success path, not found, a conflict, invalid input (422) and another caller's record (404).

## Check that nothing was skipped

- [ ] Create, Read and (if updatable) Patch schemas exist; no ORM model or dict crosses the route.
- [ ] The ORM model has an Alembic revision in the same change.
- [ ] Each use case takes its dependencies as parameters and commits exactly once.
- [ ] Each new provider has one `Annotated` alias; no route builds a session, client or repository itself.
- [ ] Methods, success codes, paths, paging and owner scoping follow the rules named in step 5.
- [ ] Every new domain error has a row in the error table and an entry in `responses=`.
- [ ] The router is included in `create_app`.
- [ ] Use-case tests on fakes and endpoint tests on the rolled-back database both exist, including the 404 for another caller's record.

# API review checklist

One line per check for reviewing a web API change, or a whole service before its first production release. Each line names the rule that holds the detail and the fix; read that rule before reporting a finding. The examples use FastAPI; the HTTP, naming, schema, security and database checks hold for any Python web framework. The rules whose ids start with `fastapi-` are in the index only in FastAPI repositories; elsewhere, apply the same check in the framework's own idiom. Report findings in the format the review asks for.

## HTTP methods and status codes

- [ ] GET is safe and has no side effects; POST creates and answers 201 with a `Location` header; PUT replaces the whole resource and is idempotent; PATCH updates only the fields sent; DELETE answers 204 with no body (`web-http-methods`).
- [ ] Failures answer a precise code from one mapping (404 not found, 409 conflict or duplicate, 422 invalid input); no route builds a 500 by hand, and one error body shape is used everywhere (`fastapi-error-boundaries`). An invalid or expired token answers 401 (`web-jwt-validation`).

## Resource naming

- [ ] Collections are plural nouns, single resources carry their id in the path, nesting stops at one level, and actions are sub-resources rather than verbs in the URL (`web-api-resource-naming`).
- [ ] One case style across every path; each router's prefix matches its resource; a version prefix appears only for breaking changes (`web-api-resource-naming`).

## Requests and responses

- [ ] Separate Create, Patch and Read models; input models forbid unknown keys and expose no server-owned fields (`web-api-schemas`).
- [ ] Read models carry no password hash, token, secret or internal-only field (`web-api-schemas`).
- [ ] Partial updates apply only the fields the client sent, so leaving a field out differs from clearing it (`web-api-schemas`).
- [ ] Every list endpoint is bounded and paginated with a server-enforced maximum, a stable order and one page shape (`web-api-pagination`).
- [ ] Query parameters have defaults for the common case and `Query()` bounds or a closed set of values (`fastapi-query-parameters`).
- [ ] Every route declares its response model, success status, summary and tags, and lists its non-2xx outcomes in `responses=` (`fastapi-openapi-metadata`).

## Structure

- [ ] Sessions, clients, the current user and paging come from `Depends` providers declared once as `Annotated` aliases, never built in a route body (`fastapi-dependency-providers`).
- [ ] Routes only parse, call one use case and convert; business rules and derived values live in the use case (`fastapi-thin-routes`).
- [ ] The app is built by a `create_app(settings)` factory; long-lived resources are acquired in its lifespan and released after `yield`; only the ASGI entry point reads the environment (`fastapi-app-wiring`).

## Security

- [ ] Authentication is required at the router level by default; every query that loads a record by a client-sent id is scoped to the caller's owner or tenant, and a record the caller may not see answers 404 (`web-object-authorization`).
- [ ] JWTs are decoded with a pinned algorithm list and required `exp`, `iat`, `sub`, `iss` and `aud` claims; access tokens are short-lived (`web-jwt-validation`).
- [ ] Passwords are stored only as Argon2id hashes, hashed off the event loop, and an unknown email answers like a wrong password (`web-password-hashing`).
- [ ] CORS lists the exact trusted origins from settings, defaults to none, and never combines every origin with credentials (`web-cors-origins`).
- [ ] Login and reset endpoints are rate-limited where the project has a limiter or a proxy that throttles.

## Before the first production release

- [ ] Settings are typed and read from the environment, with secrets typed so they never print (python-coding's pydantic-typed-settings rule).
- [ ] A cheap, unauthenticated health route exists (`fastapi-app-wiring`).
- [ ] Every log line carries the request id, and no log line holds a secret or token (`fastapi-request-id-logging`).
- [ ] Outbound HTTP goes through one shared client per upstream with timeouts and limits from settings (`httpx-shared-client`).
- [ ] The schema changes only through reviewed Alembic revisions run once per deploy; the app never calls `create_all` (`alembic-migrations`).
- [ ] The engine is built once in the lifespan and each request gets its own session that closes on every path (`sqlalchemy-session-per-request`).
- [ ] Use cases are tested on fakes, and endpoints through the real app and database in a rolled-back transaction.

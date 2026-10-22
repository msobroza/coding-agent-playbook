---
id: web-application
name: web-application
description: "Practices for Python web backends, shown with FastAPI and SQLAlchemy."
playbook:
  use_when: "writing or reviewing endpoints, schemas, auth or database code in a web app"
  files: "Web endpoints, database access and migrations"
  sections:
    - id: security
      title: "Security"
      impact: CRITICAL
      summary: "Authenticate callers safely and authorize every access to their data."
      open_when: "Code handles login, passwords, reset tokens, JWTs or CORS, or loads a record by an id the client sent."
    - id: database
      title: "Database"
      impact: CRITICAL
      summary: "Query, scope and evolve the database safely with SQLAlchemy and Alembic."
      open_when: "Code adds or changes an ORM model, a query, the per-request session or its commit, a relationship or an Alembic migration."
    - id: async-io
      title: "Async I/O"
      impact: CRITICAL
      summary: "Keep the event loop free and share outbound clients so one request cannot stall the others."
      open_when: "An async def route or dependency calls code that may block, or the app calls another HTTP service."
    - id: api-design
      title: "API design"
      impact: HIGH
      summary: "Shape what enters and leaves the API and map every failure to a precise status code."
      open_when: "A route's request or response model, HTTP method, success or error status code, or list paging changes."
    - id: app-structure
      title: "App structure"
      impact: HIGH
      summary: "Compose the app in a factory with explicit providers so resources and logic stay replaceable."
      open_when: "Code creates the app or a lifespan resource, adds a router or dependency provider, or grows logic in a route body."
    - id: observability
      title: "Observability"
      impact: MEDIUM
      summary: "Make each request traceable through the logs without leaking secrets."
      open_when: "Code adds logging, middleware or error reporting that should tie a log line to the request behind it."
    - id: testing
      title: "Testing"
      impact: MEDIUM
      summary: "Test through the real app and a real database, isolated per test."
      open_when: "A test calls an endpoint, overrides a dependency, or needs a database session or rows seeded for it."
    - id: api-conventions
      title: "API conventions"
      impact: MEDIUM
      summary: "Keep URLs, query parameters and generated docs predictable for clients."
      open_when: "A route's URL path, version prefix, query parameters, tags, summary or documented responses are added or renamed."
  references:
    - path: references/add-an-endpoint.md
      open_when: "Adding an endpoint or a new resource to a FastAPI service, and checking that no layer or test was skipped."
      applies_if:
        has_framework: ["fastapi"]
    - path: references/api-review-checklist.md
      open_when: "Reviewing a web API change, or checking a service before its first production release."
      applies_if:
        any_framework: ["fastapi", "flask", "django", "starlette"]
    - path: references/request-lifecycle.md
      open_when: "Unsure which request step owns a change or a failure: startup, provider, route, use case, repository or error table."
      applies_if:
        has_framework: ["fastapi"]
---

# Web application

Practices for Python web backends: authenticating callers and authorizing every access to their data, querying and migrating the database safely, keeping the event loop free, shaping request and response schemas and the status codes failures map to, composing the app from a factory and explicit dependency providers, tracing each request through the logs, testing through the real app and database, and keeping URLs, query parameters and generated docs predictable.

Examples use one stack: FastAPI, SQLAlchemy with its async API, Alembic, Pydantic with pydantic-settings, httpx, PyJWT and pwdlib. The same rules apply to sync `def` endpoints with `Session`, and the security and database rules hold for Flask, Django and Starlette as well. Line- and function-level Python conventions, Pydantic validation included, stay in the python-coding skill, and test code in general in the python-testing skill; for web code this skill's rule wins where python-coding or python-testing overlap.

## Quick Reference

### Authorized query

```python
router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


@router.get("/{invoice_id}")
async def read_invoice(invoice_id: int, user: CurrentUser, session: SessionDep) -> InvoiceRead:
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == user.id)  # owner
    )
    if invoice is None:
        raise NotFoundError("Invoice", invoice_id)  # mapped to 404 by one exception handler
    return InvoiceRead.model_validate(invoice)
```

### Passwords and tokens

```python
hasher = PasswordHasher()  # Argon2id via pwdlib, built once by create_app and injected
hashed = await hasher.hash_password(password)  # runs in a thread, off the event loop

claims = jwt.decode(
    token,
    settings.jwt_secret.get_secret_value(),
    algorithms=["HS256"],
    audience=settings.jwt_audience,
    issuer=settings.jwt_issuer,
    options={"require": ["exp", "iat", "sub", "iss", "aud"]},
)

reset_token = secrets.token_urlsafe(32)  # store only its SHA-256 hash
hmac.compare_digest(expected_signature.encode(), presented_signature.encode())
```

### Settings and CORS

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str
    jwt_audience: str
    access_token_ttl_minutes: int = Field(default=15, gt=0, le=60)
    cors_origins: list[str] = Field(default_factory=list)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # never ["*"] with allow_credentials=True
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

## See Also

- python-coding: general Python rules; Pydantic validation, typed settings, dependency injection and error handling underlie several rules here.
- python-architecture: the layers behind the routes and where the web boundary sits.
- python-testing: test structure, fixtures and test doubles that endpoint tests still follow.
- python-tooling: ruff, mypy and test-runner configuration; ruff's `S` rules catch several issues covered here.

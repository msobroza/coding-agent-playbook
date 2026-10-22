---
id: fastapi-error-boundaries
name: FastAPI error boundaries
description: "FastAPI errors: framework-free domain exceptions, one mapping to HTTP status codes, one error body shape."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  has_framework: ["fastapi"]
section: api-design
priority: 41
tags: [python, fastapi, errors]
---

# Map domain errors to HTTP responses in one place

## Description

HTTP is a delivery detail. Service, operation and persistence modules never import `fastapi`, never raise `HTTPException` and never give domain exceptions a `status_code` attribute: business code that does cannot be reused from a CLI or a worker, and status codes scattered across modules drift apart. Raise domain exceptions and translate them to HTTP in exactly one style per app. Prefer one exception-type-to-status table served by an `@app.exception_handler` registered on the project's base exception; explicit `except SomeDomainError` blocks in routers that raise `HTTPException` are the alternative. Never mix the two. Map by failure mode: not found 404, unauthenticated 401, forbidden 403, conflict or duplicate 409 (never 400), business-rule violation 409 or 422; request-schema 422s stay FastAPI's own. Look the class up along the exception's MRO; a domain error with no entry is a 500, never a fallback 400 that blames the client. Unknown errors stay unknown: never answer `200` with an `{"error": ...}` body, never catch `KeyError` or `LookupError` around an operation to answer 404, and never register a handler on `Exception` or wrap a route in `except Exception` to build a 500.

## Bad Example

```python
@router.post("")
async def create_user(body: UserCreate, session: SessionDep) -> dict[str, object]:
    try:
        user = await register_user(session, body)
        return {"success": True, "user": UserRead.model_validate(user)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}  # 200 OK carrying the database error
```

## Good Example

```python
# app/main.py: the one mapping, on the project base exception AppError
HTTP_STATUS: dict[type[AppError], int] = {NotFoundError: 404, ConflictError: 409}


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    mapped = next((cls for cls in type(exc).__mro__ if cls in HTTP_STATUS), None)
    if mapped is None:
        raise exc  # unmapped: the default handler answers a plain-text 500 and logs it
    return JSONResponse(status_code=HTTP_STATUS[mapped], content={"detail": str(exc)})


# app/services/users.py: no FastAPI imports. hash_password, User, UserCreate and
# UserRead are the app's own hasher, ORM model and request/response schemas.
async def register_user(session: AsyncSession, data: UserCreate) -> User:
    hashed = await hash_password(data.password.get_secret_value())
    user = User(email=data.email, password_hash=hashed)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:  # uq_users_email is the only constraint this can violate
        await session.rollback()
        raise ConflictError("Email already registered") from exc
    return user


# app/routers/users.py: the route neither catches nor maps
@router.post("", status_code=status.HTTP_201_CREATED, responses={409: {"description": "Taken"}})
async def create_user(body: UserCreate, session: SessionDep) -> UserRead:
    return UserRead.model_validate(await register_user(session, body))
```

## Notes

- Mapped errors share one body shape, `{"detail": ...}` like FastAPI's own errors, unless the project chose problem+json; then override the `HTTPException` and `RequestValidationError` handlers too. The mapping layer builds the body; routes never hand-roll error dicts. The default 500 body stays plain text.
- `detail` is a sentence written for the client. Never put tracebacks, SQL, exception reprs or secrets in the body; keep internal detail in the exception chain and the logs, and never run production in debug mode, which returns tracebacks.
- `HTTPException` belongs to the HTTP layer only: routes, and dependencies such as `get_current_user` raising 401.
- Catch `IntegrityError` at the commit instead of checking for a duplicate first: two concurrent requests can both pass the check.
- Declare each route's non-2xx outcomes with `responses=` so the OpenAPI schema matches what clients receive (the detail is `fastapi-openapi-metadata`'s); success codes are `web-http-methods`'.
- Raising in the core and translating once at the boundary, the project base exception, and letting unknown errors propagate are the python-coding skill's python-error-boundaries and python-custom-exceptions rules.
- Worked example: the hotel example's app/main.py holds a complete table and its unmapped-500 path.

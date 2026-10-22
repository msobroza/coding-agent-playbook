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

# FastAPI error boundaries

HTTP is a delivery detail. Business code that raises `HTTPException` cannot be reused from a CLI or a worker, and status codes scattered across modules drift apart.

## Keep HTTP out of the core

- Service, operation and persistence modules never import `fastapi`, never raise `HTTPException` and never give domain exceptions a `status_code` attribute.

## One mapping layer

- Translate domain exceptions to HTTP in exactly one style per app. Prefer one exception-type-to-status table served by an `@app.exception_handler` registered on the base exception; explicit `except SomeDomainError` blocks in routers are the alternative. Never mix the two.
- Map by failure mode: not found 404, unauthenticated 401, forbidden 403, conflict or duplicate 409, business-rule violation 409 or 422. Leave request-schema 422s to FastAPI's own validation.
- Look up the most specific mapped class along the exception's MRO. A domain error with no entry is a 500, never a fallback 400 that blames the client.
- Never answer `200` with an `{"error": ...}` body.

## Unknown errors stay unknown

- Never catch `KeyError` or `LookupError` around an operation to answer 404.
- Never register a handler on `Exception` or wrap a route in `except Exception` to build a 500. Unmapped errors fall through to the default handler, which answers 500 and logs the traceback.

## One error body shape

- Mapped errors share one body shape, `{"detail": ...}` unless the project chose problem+json. The mapping layer builds it; routes never hand-roll error dicts. The default 500 body stays plain text.
- Never put tracebacks, SQL, exception reprs or secrets in the body. `detail` is a sentence written for the client.
- Declare each route's non-2xx outcomes with `responses=` so the OpenAPI schema matches what clients receive.

```python
HTTP_STATUS: dict[type[AppError], int] = {NotFoundError: 404, ConflictError: 409}


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    mapped = next((cls for cls in type(exc).__mro__ if cls in HTTP_STATUS), None)
    if mapped is None:
        raise exc  # unmapped: the default handler answers a plain-text 500 and logs it
    return JSONResponse(status_code=HTTP_STATUS[mapped], content={"detail": str(exc)})
```

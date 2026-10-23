---
id: fastapi-request-id-logging
name: FastAPI request ID logging
description: "Correlate logs with a request ID: middleware validates or generates it, a ContextVar carries it, a logging filter stamps every record, and the response returns it."
version: 1
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/middleware.py"
  - "**/middleware/**/*.py"
  - "**/observability.py"
applies_if:
  has_framework: ["fastapi"]
section: observability
priority: 60
tags: [python, fastapi, logging]
---

# Correlate logs with a request ID

## Description

Under concurrency, log lines from different requests interleave, and without a shared identifier the one that failed cannot be reconstructed. Assign a request ID in middleware (reuse a validated `X-Request-ID` from the proxy, or generate one), keep it in a `ContextVar`, attach it to every log record with a logging filter, and return it in the response header. Log through module loggers with structured `extra` fields, never `print`, and never log secrets, tokens or whole request bodies.

## Bad Example

```python
@router.post("")
async def create_invoice(body: InvoiceCreate, request: Request) -> InvoiceRead:
    print(f"creating invoice {body}")  # no level or logger; may print personal data
    auth = request.headers.get("Authorization")
    logging.info("auth header: %s", auth)  # bearer token in the logs
    invoice = await create_invoice_record(body)
    logging.info("invoice created")  # which request? which invoice?
    return InvoiceRead.model_validate(invoice)
```

## Good Example

```python
# app/observability.py
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request, Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}")
logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid4().hex
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error")  # logged while the ID is still set
        raise
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


def add_request_id_middleware(app: FastAPI) -> None:
    app.middleware("http")(request_id_middleware)  # called by create_app


# app/services/invoices.py: one structured call, with IDs instead of personal data
logger.info("invoice created", extra={"invoice_id": invoice.id, "total_cents": invoice.total_cents})
```

## Notes

- A request-scoped `ContextVar` is an explicit exception to "no module-level state". Only the middleware sets and resets `request_id_var`, and it never carries business data.
- Validate incoming IDs (length and characters) before trusting them; they end up in log files and response headers.
- Context variables are copied into tasks created during the request, including `asyncio.create_task` and `asyncio.to_thread`, so their logs carry the same ID. `call_next` runs the app in its own task too, so streamed bodies and `BackgroundTasks` keep the ID after the middleware has reset its copy.
- Unhandled exceptions are logged by the server after the middleware has reset the variable; logging with `logger.exception(...)` inside the middleware, then re-raising, puts the ID on the traceback.
- Never log passwords, tokens, `Authorization` or `Cookie` headers, full request bodies or personal data; log IDs instead.
- Configure logging once in the entrypoint; every other module only calls `logging.getLogger(__name__)`.
- The stdlib `Formatter` ignores `extra` fields that are not in its format string. A JSON formatter (`python-json-logger`) or `structlog` makes them searchable, `asgi-correlation-id` provides this middleware as a package, and OpenTelemetry adds trace IDs across services: propose one, never add it unasked.

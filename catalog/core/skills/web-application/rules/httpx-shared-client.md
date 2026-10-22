---
id: httpx-shared-client
name: Shared httpx client
description: "Share one httpx.AsyncClient per upstream, built in the lifespan with timeouts and limits from settings, and translate its failures."
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/services/**/*.py"
  - "**/clients/**/*.py"
  - "**/adapters/**/*.py"
applies_if:
  has_framework: ["fastapi", "httpx"]
section: async-io
priority: 32
tags: [python, fastapi, httpx, async]
---

# Share one httpx.AsyncClient with explicit timeouts

## Description

Creating an `httpx.AsyncClient` per call throws away connection pooling, paying a new TCP and TLS handshake each time, and leaks connections when the client is not closed. Create one client per upstream in the lifespan with a `base_url`, timeouts chosen for that upstream and connection limits, all read from settings; close it on shutdown; and inject it through a dependency so tests can replace the transport. Treat upstream responses as untrusted: check the status and translate failures into your own exception.

## Bad Example

```python
import httpx

router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


@router.post("/{invoice_id}/pay")
async def pay(invoice_id: int, settings: SettingsDep) -> PaymentRead:
    async with httpx.AsyncClient() as client:  # new pool and TLS handshake per request
        response = await client.post(
            f"{settings.payments_base_url}/charges", json={"invoice_id": invoice_id}
        )
    # a 503 error page is parsed as if it were success
    return PaymentRead(**response.json())
```

## Good Example

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(  # one client per upstream, closed on shutdown
            base_url=settings.payments_base_url,
            timeout=httpx.Timeout(settings.payments_timeout_s),
            limits=httpx.Limits(max_connections=settings.payments_max_connections),
            headers={"Authorization": f"Bearer {settings.payments_api_key.get_secret_value()}"},
        ) as payments_client:
            app.state.payments_client = payments_client
            yield

    return FastAPI(lifespan=lifespan)


# app/deps.py
def get_payments_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient = request.app.state.payments_client
    return client


PaymentsClientDep = Annotated[httpx.AsyncClient, Depends(get_payments_client)]


# app/services/payments.py: AppError is the project's base exception, PaymentRead a schema
class PaymentGatewayError(AppError):
    pass


async def charge(
    client: httpx.AsyncClient, invoice_id: int, amount_cents: int, *, idempotency_key: str
) -> PaymentRead:
    try:
        response = await client.post(
            "/charges",
            json={"invoice_id": invoice_id, "amount": amount_cents},
            headers={"Idempotency-Key": idempotency_key},  # a retry cannot charge twice
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:  # timeouts, connection errors, 4xx and 5xx
        raise PaymentGatewayError(f"Charge failed for invoice {invoice_id}") from exc
    return PaymentRead.model_validate_json(response.content)
```

## Notes

- FastAPI dependency aliases use concrete `AsyncSession` / `httpx.AsyncClient` at the route edge; Protocols are for the app's own ports.
- httpx applies a default timeout; set one per upstream from a settings field instead of inheriting it. `requests` has no default timeout at all and blocks the event loop (`fastapi-no-blocking-calls`).
- Validate upstream payloads with a Pydantic model (`model_validate_json`): another service's response is a trust boundary too.
- Map `PaymentGatewayError` to 502 or 503 in the one exception handler table without echoing the upstream body (`fastapi-error-boundaries`).
- Retry only idempotent requests, or send an idempotency key. The retry policy itself is python-coding's python-retries-and-timeouts.
- In tests, override `get_payments_client` with a client built on `httpx.MockTransport` (`fastapi-dependency-overrides`).

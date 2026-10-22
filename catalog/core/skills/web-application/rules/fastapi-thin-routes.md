---
id: fastapi-thin-routes
name: FastAPI thin routes
description: "Keep each route a thin HTTP adapter: it declares inputs and the response model, calls a service that knows nothing of HTTP, and converts the result."
version: 1
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/services/**/*.py"
applies_if:
  has_framework: ["fastapi"]
section: app-structure
priority: 46
tags: [python, fastapi]
---

# Keep route functions thin

## Description

A route function is the HTTP adapter: it declares inputs, authentication and the response model, calls a service function, and converts the result. When token parsing, queries, business rules, external calls and commits pile up inside the route, the logic cannot be reused from a worker or a CLI, and tests need the full HTTP stack. Put use-case logic in plain async functions that receive their dependencies and plain values as parameters. Service modules never import `fastapi` and never raise `HTTPException`; the router enforces the HTTP conventions (methods, status codes, paging parameters, the error shape) and the service knows nothing of HTTP.

## Bad Example

```python
router = APIRouter(prefix="/invoices")


@router.post("/{invoice_id}/payment")
async def pay_invoice(
    invoice_id: int, request: Request, token: Annotated[str, Depends(oauth2_scheme)]
) -> dict[str, object]:
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    async with request.app.state.sessionmaker() as session:
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None or invoice.owner_id != int(claims["sub"]):
            raise HTTPException(status_code=404)
        if invoice.paid_at is not None:
            raise HTTPException(status_code=409, detail="already paid")
        response = await request.app.state.payments_client.post(
            "/charges", json={"amount": invoice.total_cents}
        )
        invoice.paid_at = datetime.now(timezone.utc)
        await session.commit()
    return {"ok": True, "charge": response.json()}
```

## Good Example

```python
# SessionDep, PaymentsClientDep and CurrentUser are the app's Annotated aliases
# (declared once in app/deps.py); get_owned_invoice loads an invoice or raises
# NotFoundError, and charge posts to the payments API.


# app/services/invoices.py: no FastAPI imports; callable from routes, workers and tests
async def pay_invoice(
    session: AsyncSession,
    payments: httpx.AsyncClient,
    *,
    owner_id: int,
    invoice_id: int,
    now: datetime,
) -> Invoice:
    invoice = await get_owned_invoice(session, owner_id=owner_id, invoice_id=invoice_id)
    if invoice.paid_at is not None:
        raise ConflictError("Invoice already paid")
    await charge(payments, invoice.id, invoice.total_cents, idempotency_key=f"invoice-{invoice.id}")
    invoice.paid_at = now
    await session.commit()
    return invoice


# app/routers/invoices.py: the HTTP adapter only
router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


@router.post("/{invoice_id}/payment")
async def pay(
    invoice_id: int, user: CurrentUser, session: SessionDep, payments: PaymentsClientDep
) -> InvoiceRead:
    invoice = await pay_invoice(
        session, payments, owner_id=user.id, invoice_id=invoice_id, now=datetime.now(timezone.utc)
    )
    return InvoiceRead.model_validate(invoice)
```

## Notes

- Services take plain values (`owner_id`, `now`), not `Request`. Passing the time in keeps time-dependent logic testable (the python-coding skill's python-pure-core rule); business rules in use cases that receive ports are the python-architecture skill's arch-use-case-functions rule.
- Services raise domain errors; routes leave them to the app's one mapping style (`fastapi-error-boundaries`).
- Routes compute no derived business values (prices, refund eligibility); those come from the service.
- When a use case calls an external service and then commits, send an idempotency key derived from the record (as `charge` does above), so a retry after a failed commit cannot charge twice.
- A one-line read can query directly in the route. Extract a service when there is logic, more than one step, or reuse; do not add pass-through layers or repository classes that only forward calls.
- Worked example: the hotel example's app/routers/bookings.py holds routes that only adapt.
- The steps and tests for a new endpoint or resource: open add-an-endpoint.md.

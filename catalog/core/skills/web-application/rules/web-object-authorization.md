---
id: web-object-authorization
name: Authorize access to every object
description: "Scope every query that loads a record by owner or tenant, answer 404 for records the caller may not see, and require authentication at the router level."
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/services/**/*.py"
  - "**/auth.py"
  - "**/auth/**/*.py"
  - "**/security.py"
  - "**/security/**/*.py"
  - "**/deps.py"
  - "**/dependencies.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: security
priority: 20
tags: [python, web, security]
---

# Authorize access to every object

## Description

Authentication says who the caller is; authorization decides whether they may touch this record. Broken object level authorization (BOLA, also called IDOR) happens when `/invoices/{invoice_id}` loads the row by primary key and returns it to any logged-in user. Scope every query by owner or tenant in the statement that loads the object, answer 404 for objects the caller may not see, and require authentication at the router level so new endpoints are protected by default.

## Bad Example

```python
router = APIRouter(prefix="/invoices")


@router.get("/{invoice_id}")
async def read_invoice(invoice_id: int, user: CurrentUser, session: SessionDep) -> InvoiceRead:
    invoice = await session.get(Invoice, invoice_id)  # any user can read any invoice
    if invoice is None:
        raise HTTPException(status_code=404)
    return InvoiceRead.model_validate(invoice)


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: int, session: SessionDep
) -> None: ...  # forgot CurrentUser: anonymous callers can delete
```

## Good Example

```python
# SessionDep (AsyncSession) and CurrentUser (User) are the app's Annotated dependency
# aliases; Invoice is the ORM model with owner_id, InvoiceRead its response schema.
router = APIRouter(prefix="/invoices", dependencies=[Depends(get_current_user)])


class NotFoundError(AppError):  # the project's base exception; mapped to 404 in one table
    def __init__(self, resource: str, resource_id: int) -> None:
        super().__init__(f"{resource} {resource_id} not found")
        self.resource_id = resource_id


async def get_owned_invoice(session: AsyncSession, *, owner_id: int, invoice_id: int) -> Invoice:
    invoice = await session.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.owner_id == owner_id)
        .options(selectinload(Invoice.lines))
    )
    if invoice is None:
        raise NotFoundError("Invoice", invoice_id)  # same for "missing" and "not yours"
    return invoice


@router.get("/{invoice_id}")
async def read_invoice(invoice_id: int, user: CurrentUser, session: SessionDep) -> InvoiceRead:
    invoice = await get_owned_invoice(session, owner_id=user.id, invoice_id=invoice_id)
    return InvoiceRead.model_validate(invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: int, user: CurrentUser, session: SessionDep) -> None:
    invoice = await get_owned_invoice(session, owner_id=user.id, invoice_id=invoice_id)
    await session.delete(invoice)  # Invoice.lines cascades "all, delete-orphan"
    await session.commit()
```

## Notes

- `APIRouter(dependencies=[Depends(get_current_user)])` makes "authenticated" the default for the router. FastAPI caches a dependency within a request, so endpoints that also take `CurrentUser` do not decode the token twice.
- `NotFoundError` reaches the client as 404 through the app's one exception-to-status table (`fastapi-error-boundaries`), not through an `HTTPException` raised in the query helper.
- Express roles as dependencies (`require_admin(user: CurrentUser) -> User` raising 403) and still scope data queries by owner or tenant.
- In multi-tenant apps, take `tenant_id` from the authenticated principal, never from a header, query parameter, or request body.
- Unguessable IDs (UUIDs) are not access control: they leak through URLs, logs, and screenshots.
- Use 403 only when the caller is allowed to know the object exists, for example read access without write access.
- Write a test per endpoint asserting that another user's ID returns 404, with the current user swapped through a dependency override (`fastapi-dependency-overrides`).
- In any framework (Flask, Django, Starlette), put the owner or tenant filter in the statement or queryset that loads the object (Django: `get_object_or_404(Invoice, id=invoice_id, owner=request.user)`), never in a check after loading it.

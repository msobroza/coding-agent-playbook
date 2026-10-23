"""Customer routes: register a customer and read one back."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.deps import HotelDep, NewIdDep
from app.operations import customer as customer_ops
from app.routers.schemas import CustomerCreate, CustomerRead, ResponseDocs

router = APIRouter(prefix="/customers", tags=["customers"])

EMAIL_TAKEN: Final[ResponseDocs] = {
    409: {"description": "A customer with this email is already registered"}
}
CUSTOMER_NOT_FOUND: Final[ResponseDocs] = {404: {"description": "No customer has this id"}}


@router.post(
    "", status_code=status.HTTP_201_CREATED, summary="Register a customer", responses=EMAIL_TAKEN
)
async def register_customer(
    body: CustomerCreate, hotel: HotelDep, new_id: NewIdDep, request: Request, response: Response
) -> CustomerRead:
    """Register a customer and answer 201 with a Location header naming them.

    Example: ``POST /customers {"name": "Ada Example", "email": "ada@example.com"}``.
    """
    customer = await customer_ops.register_customer(
        hotel, name=body.name, email=body.email, new_id=new_id
    )
    location = request.url_for("read_customer", customer_id=customer.customer_id)
    response.headers["Location"] = location.path
    return CustomerRead.model_validate(customer)


@router.get("/{customer_id}", summary="Read a customer", responses=CUSTOMER_NOT_FOUND)
async def read_customer(customer_id: UUID, hotel: HotelDep) -> CustomerRead:
    """The customer ``customer_id``, or 404.

    Example: ``GET /customers/{customer_id}`` -> 200 with the customer.
    """
    return CustomerRead.model_validate(await customer_ops.get_customer(hotel, customer_id))

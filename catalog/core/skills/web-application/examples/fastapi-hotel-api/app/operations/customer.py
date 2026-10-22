"""Customer use cases: register a customer once per email, and read one back."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.domain.model import Customer
from app.operations.ports import HotelUnitOfWork


async def register_customer(
    hotel: HotelUnitOfWork, *, name: str, email: str, new_id: Callable[[], UUID]
) -> Customer:
    """Register a customer under a new id and commit once; a taken email is refused.

    Example: ``await register_customer(hotel, name="Ada", email="ada@example.com",
    new_id=uuid4)`` -> the new ``Customer``; a second call raises DuplicateEmailError.
    """
    customer = Customer(new_id(), name, email)
    await hotel.customers.add(customer)  # a taken email raises DuplicateEmailError (409)
    await hotel.commit()
    return customer


async def get_customer(hotel: HotelUnitOfWork, customer_id: UUID) -> Customer:
    """The customer ``customer_id``; an unknown id raises CustomerNotFoundError.

    Example: ``(await get_customer(hotel, customer_id)).email`` -> "ada@example.com".
    """
    return await hotel.customers.get(customer_id)

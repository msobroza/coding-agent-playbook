"""Endpoint tests: the real app on the real engine, each test in a rolled-back transaction.

They cover what the HTTP edge adds (status codes, headers, the error body, request
validation); the business rules are tested on fakes in test_operations.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.domain.errors import HotelError
from app.main import create_app
from app.settings import Settings

if TYPE_CHECKING:  # the factory types only; fixtures arrive by name
    from tests.conftest import MakeCustomer, MakeRoom

pytestmark = pytest.mark.anyio


class LedgerOutOfSyncError(HotelError):
    """A domain error deliberately missing from the app's error table."""


async def test_booking_a_room_answers_201_with_its_location_and_price(
    client: httpx.AsyncClient, make_room: MakeRoom, make_customer: MakeCustomer
) -> None:
    room = await make_room(nightly_rate_cents=9_500)
    guest = await make_customer()

    response = await client.post(
        "/bookings",
        json={
            "room_id": str(room.room_id),
            "customer_id": str(guest.customer_id),
            "check_in": "2026-03-02",
            "check_out": "2026-03-05",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/bookings/{body['booking_id']}"
    assert body["price_cents"] == 28_500
    assert body["cancelled_on"] is None


async def test_booking_an_unknown_room_is_404_with_the_error_body(
    client: httpx.AsyncClient, make_customer: MakeCustomer
) -> None:
    guest = await make_customer()
    missing = UUID(int=404)

    response = await client.post(
        "/bookings",
        json={
            "room_id": str(missing),
            "customer_id": str(guest.customer_id),
            "check_in": "2026-03-02",
            "check_out": "2026-03-03",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"no room with id {missing}"}


async def test_an_overlapping_stay_is_409(
    client: httpx.AsyncClient, make_room: MakeRoom, make_customer: MakeCustomer
) -> None:
    room = await make_room()
    guest = await make_customer()
    stay = {"room_id": str(room.room_id), "customer_id": str(guest.customer_id)}
    first = await client.post(
        "/bookings", json={**stay, "check_in": "2026-03-02", "check_out": "2026-03-05"}
    )
    assert first.status_code == 201

    response = await client.post(
        "/bookings", json={**stay, "check_in": "2026-03-04", "check_out": "2026-03-06"}
    )

    assert response.status_code == 409


async def test_a_duplicate_email_is_409(
    client: httpx.AsyncClient, make_customer: MakeCustomer
) -> None:
    await make_customer(email="ada@example.com")

    response = await client.post(
        "/customers", json={"name": "Ada Again", "email": "ada@example.com"}
    )

    # The flush failed, so this session takes no further request in this test.
    assert response.status_code == 409
    assert response.json() == {
        "detail": "a customer with email ada@example.com is already registered"
    }


async def test_patch_with_null_notes_clears_them_and_keeps_the_number(
    client: httpx.AsyncClient, make_room: MakeRoom
) -> None:
    room = await make_room(number="101", notes="sea view")

    response = await client.patch(f"/rooms/{room.room_id}", json={"notes": None})

    assert response.status_code == 200
    assert response.json() == {
        "room_id": str(room.room_id),
        "number": "101",
        "capacity": 2,
        "nightly_rate_cents": 9_500,
        "notes": None,
    }


async def test_patch_with_null_number_is_422(
    client: httpx.AsyncClient, make_room: MakeRoom
) -> None:
    room = await make_room()

    response = await client.patch(f"/rooms/{room.room_id}", json={"number": None})

    assert response.status_code == 422


async def test_listing_rooms_refuses_a_limit_above_100(client: httpx.AsyncClient) -> None:
    response = await client.get("/rooms", params={"limit": 101})

    assert response.status_code == 422


async def test_an_unmapped_domain_error_is_a_plain_500() -> None:
    # A route-layer test: no database and no fake, only the app's error table.
    app = create_app(Settings(database_url=SecretStr("unused-the-lifespan-never-runs")))

    @app.get("/ledger")
    async def broken_ledger() -> None:
        raise LedgerOutOfSyncError("the booking ledger disagrees with the room nights")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ledger")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"

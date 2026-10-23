"""Per-request providers and their Annotated aliases, each declared once, here."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import SqlHotelUnitOfWork
from app.operations.ports import HotelUnitOfWork

# Routes take the aliases below; tests override get_session and today_utc.


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, from the sessionmaker the lifespan stored on ``app.state``.

    Example: routes reach it through ``SessionDep``; the tests replace it with
    ``app.dependency_overrides[get_session] = test_session``.
    """
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:  # closed on every path; uncommitted work is dropped
        yield session  # never commits: the use case does, through the unit of work


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_hotel(session: SessionDep) -> HotelUnitOfWork:
    """The request's unit of work over its session, typed as the port the use cases take.

    Example: ``async def read_room(room_id: UUID, hotel: HotelDep) -> RoomRead``.
    """
    return SqlHotelUnitOfWork(session)


def today_utc() -> date:
    """Today's date in UTC, so use cases receive the date and never read a clock.

    Example: ``app.dependency_overrides[today_utc] = lambda: date(2026, 3, 2)`` in the tests.
    """
    return datetime.now(timezone.utc).date()


def id_factory() -> Callable[[], UUID]:
    """The factory that makes new record ids, so use cases never generate ids themselves.

    Example: ``await create_room(hotel, ..., new_id=id_factory())``; routes take ``NewIdDep``.
    """
    return uuid4


HotelDep = Annotated[HotelUnitOfWork, Depends(get_hotel)]
TodayDep = Annotated[date, Depends(today_utc)]
NewIdDep = Annotated[Callable[[], UUID], Depends(id_factory)]

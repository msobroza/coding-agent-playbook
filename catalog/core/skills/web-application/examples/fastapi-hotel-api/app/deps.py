"""Per-request providers and their Annotated aliases, each declared once, here.

Routes take the aliases; tests override ``get_session`` and ``today_utc``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import SqlHotelUnitOfWork
from app.operations.ports import HotelUnitOfWork


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:  # closed on every path; uncommitted work is dropped
        yield session  # never commits: the use case does, through the unit of work


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_hotel(session: SessionDep) -> HotelUnitOfWork:
    return SqlHotelUnitOfWork(session)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()  # use cases receive the date, never read a clock


def id_factory() -> Callable[[], UUID]:
    return uuid4  # use cases receive the factory, never generate ids themselves


HotelDep = Annotated[HotelUnitOfWork, Depends(get_hotel)]
TodayDep = Annotated[date, Depends(today_utc)]
NewIdDep = Annotated[Callable[[], UUID], Depends(id_factory)]

"""Shared fixtures: the real engine, a rolled-back session per test, row factories, a client.

Unit tests use fakes; persistence and endpoint tests use the real engine in a
rolled-back transaction. tests/fakes.py is imported by the tests that need it,
never from here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date
from itertools import count
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import URL, event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.db.models import Base, CustomerRow, RoomRow
from app.deps import get_session, today_utc
from app.main import create_app
from app.settings import Settings

#: The date every endpoint test runs on, so "before today" never depends on the calendar.
TODAY = date(2026, 3, 2)


class MakeRoom(Protocol):
    async def __call__(
        self, *, number: str = ..., nightly_rate_cents: int = ..., notes: str | None = ...
    ) -> RoomRow: ...


class MakeCustomer(Protocol):
    async def __call__(self, *, name: str = ..., email: str = ...) -> CustomerRow: ...


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"  # one event loop for the session-scoped engine and every test


def _database_url(tmp_path_factory: pytest.TempPathFactory) -> URL:
    configured = os.environ.get("HOTEL_TEST_DATABASE_URL")  # read here, never at import
    if configured:
        return make_url(configured)
    database: Path = tmp_path_factory.mktemp("db") / "hotel.db"
    return URL.create("sqlite+aiosqlite", database=str(database))


def _enable_sqlite_savepoints(engine: AsyncEngine) -> None:
    """Let the driver leave transactions to SQLAlchemy, so SAVEPOINTs work under aiosqlite."""

    @event.listens_for(engine.sync_engine, "connect")
    def _no_driver_transactions(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _emit_begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")


@pytest.fixture(scope="session")
async def engine(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_database_url(tmp_path_factory))
    if engine.dialect.name == "sqlite":
        _enable_sqlite_savepoints(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)  # the test schema only; the app never
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session  # commit() in app code acts on a SAVEPOINT
        finally:
            await session.close()
            await transaction.rollback()  # nothing from this test survives


@pytest.fixture
def make_room(session: AsyncSession) -> MakeRoom:
    room_ids = count(1)

    async def _make(
        *, number: str = "101", nightly_rate_cents: int = 9_500, notes: str | None = None
    ) -> RoomRow:
        row = RoomRow(
            room_id=UUID(int=next(room_ids)),
            number=number,
            capacity=2,
            nightly_rate_cents=nightly_rate_cents,
            notes=notes,
        )
        session.add(row)
        await session.flush()  # visible to the code under test, never committed
        return row

    return _make


@pytest.fixture
def make_customer(session: AsyncSession) -> MakeCustomer:
    customer_ids = count(1_001)

    async def _make(*, name: str = "Ada Example", email: str = "ada@example.com") -> CustomerRow:
        row = CustomerRow(customer_id=UUID(int=next(customer_ids)), name=name, email=email)
        session.add(row)
        await session.flush()
        return row

    return _make


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    # A placeholder URL: httpx.ASGITransport skips the lifespan, so no engine is built.
    app = create_app(Settings(database_url=SecretStr("unused-the-lifespan-never-runs")))

    async def _test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _test_session  # a fresh app: nothing leaks
    app.dependency_overrides[today_utc] = lambda: TODAY
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

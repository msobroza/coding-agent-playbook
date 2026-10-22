"""The app factory: the lifespan that owns the engine, the one error table, the routers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.errors import ConflictError, HotelError, InvalidStayError, NotFoundError
from app.routers import bookings, customers, rooms
from app.settings import Settings

#: The one mapping from domain errors to status codes, looked up along the MRO.
HTTP_STATUS: Final[dict[type[HotelError], int]] = {
    NotFoundError: 404,
    ConflictError: 409,
    InvalidStayError: 422,
}


def build_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """A lifespan that builds the engine from ``settings`` on startup and disposes of it.

    Example: ``FastAPI(lifespan=build_lifespan(settings))``, as :func:`create_app` does.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # No create_all here: a real service gets its schema from migrations.
        engine = create_async_engine(settings.database_url.get_secret_value())
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    return lifespan


async def hotel_error_response(request: Request, exc: Exception) -> JSONResponse:
    """Answer a mapped domain error with its status and ``{"detail": message}``.

    Example: ``app.add_exception_handler(HotelError, hotel_error_response)``; a
    ``RoomNotFoundError`` then answers 404 with ``{"detail": "no room with id ..."}``.
    """
    mapped = next((cls for cls in type(exc).__mro__ if cls in HTTP_STATUS), None)
    if mapped is None:
        raise exc  # unmapped: the default handler logs it and answers a plain 500
    return JSONResponse(status_code=HTTP_STATUS[mapped], content={"detail": str(exc)})


def create_app(settings: Settings) -> FastAPI:
    """Build the app from ``settings``; nothing connects until the lifespan starts.

    Example: ``create_app(Settings())`` in app/asgi.py, ``create_app(test_settings)`` in tests.
    """
    app = FastAPI(title="Hotel API", lifespan=build_lifespan(settings))
    app.add_exception_handler(HotelError, hotel_error_response)

    @app.get("/health", tags=["health"], summary="Liveness check")
    async def health() -> dict[str, str]:
        return {"status": "ok"}  # cheap and unauthenticated: it touches no database

    app.include_router(rooms.router)
    app.include_router(customers.router)
    app.include_router(bookings.router)
    return app

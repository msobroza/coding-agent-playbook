"""The ASGI entry point (serve ``app.asgi:app``): the only module that reads the environment."""

from __future__ import annotations

from app.main import create_app
from app.settings import Settings

# Tests never import this module; they build their own app with create_app(test_settings).
app = create_app(Settings())  # type: ignore[call-arg]  # fields come from HOTEL_*

"""The ASGI entry point (serve ``app.asgi:app``): the only module that reads the environment.

Tests never import it; they build their own app with ``create_app(test_settings)``.
"""

from __future__ import annotations

from app.main import create_app
from app.settings import Settings

app = create_app(Settings())  # type: ignore[call-arg]  # fields come from HOTEL_*

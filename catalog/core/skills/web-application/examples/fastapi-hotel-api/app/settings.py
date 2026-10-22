"""Typed settings, read from HOTEL_* environment variables by app/asgi.py only."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The service's configuration; each field reads the HOTEL_-prefixed variable of its name.

    Example: with HOTEL_DATABASE_URL set, ``create_app(Settings())`` in app/asgi.py; the
    tests pass ``Settings(database_url=SecretStr(...))`` instead.
    """

    model_config = SettingsConfigDict(env_prefix="HOTEL_")

    # Required: startup fails when HOTEL_DATABASE_URL is missing, and the DSN
    # (which may hold a password) never shows in a repr or a log line.
    database_url: SecretStr

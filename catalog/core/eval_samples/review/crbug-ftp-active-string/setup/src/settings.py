"""Crawler settings: built-in defaults, overridden by the project and the command line."""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    "FEED_URI": None,
    "FEED_EXPORT_INDENT": 0,
    "FEED_STORAGE_FTP_ACTIVE": False,
    "FEED_STORAGE_S3_ACL": "",
}


class Settings:
    """Setting values by name. Command-line overrides arrive as strings."""

    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self._values = {**DEFAULTS, **(values or {})}

    @classmethod
    def from_command_line(cls, overrides: list[str], project: dict[str, Any] | None = None) -> Settings:
        """Project settings plus ``-s NAME=VALUE`` overrides (each value kept as text)."""
        values = dict(project or {})
        for override in overrides:
            name, _, value = override.partition("=")
            values[name] = value
        return cls(values)

    def __getitem__(self, name: str) -> Any:
        return self._values.get(name)

    def get(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def getbool(self, name: str, default: bool = False) -> bool:
        """The setting as a bool; accepts True/False, 1/0 and their text forms."""
        value = self.get(name, default)
        if isinstance(value, str):
            if value.strip().lower() in ("1", "true"):
                return True
            if value.strip().lower() in ("0", "false", ""):
                return False
            raise ValueError(f"{name}={value!r} is not a boolean; use True/False or 1/0")
        return bool(value)

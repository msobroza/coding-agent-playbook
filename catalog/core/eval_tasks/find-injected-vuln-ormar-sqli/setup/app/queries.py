"""User-facing query builders.

Derived (paraphrased) from CVE-2026-26198 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


def find_users_by_name(db: Database, name: str) -> list[dict[str, str]]:
    """Look up users whose name matches the request-supplied ``name``.

    ``name`` comes straight from the request and is interpolated into the SQL
    text with no escaping or parameter binding.
    """
    sql = f"SELECT * FROM users WHERE name = '{name}'"
    return db.execute(sql)

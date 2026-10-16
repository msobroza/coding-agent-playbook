"""Minimal raw-SQL execution helper.

Derived (paraphrased) from CVE-2026-26198 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations


class Database:
    def __init__(self) -> None:
        self._rows: list[dict[str, str]] = []

    def execute(self, sql: str) -> list[dict[str, str]]:
        """Execute a raw SQL string verbatim (no parameter binding)."""
        # The caller is expected to pass a complete SQL statement.
        return [row for row in self._rows if sql]

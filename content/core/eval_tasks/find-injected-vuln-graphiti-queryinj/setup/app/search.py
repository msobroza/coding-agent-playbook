"""Node search API: filters graph nodes by a caller-supplied group id.

Derived (paraphrased) from CVE-2026-32247 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.graph import GraphDriver


def search_by_group(driver: GraphDriver, group_id: str) -> list[dict[str, str]]:
    """Return nodes whose ``group_id`` matches the request-supplied value.

    ``group_id`` arrives from the search request and is interpolated straight
    into the Cypher text, so a crafted value can close the quote and append
    arbitrary clauses to the executed query.
    """
    cypher = f"MATCH (n) WHERE n.group_id = '{group_id}' RETURN n"
    return driver.run(cypher)

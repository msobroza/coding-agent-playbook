"""Graph driver: runs a Cypher query string against the store.

Derived (paraphrased) from CVE-2026-32247 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations


class GraphDriver:
    def __init__(self) -> None:
        self._nodes: list[dict[str, str]] = []

    def run(self, cypher: str) -> list[dict[str, str]]:
        """Execute a fully-formed Cypher query string as given."""
        # The query text is taken verbatim; the driver does not parameterize it.
        return [node for node in self._nodes if cypher]

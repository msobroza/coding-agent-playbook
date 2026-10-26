"""Watch management: check a user-registered URL for changes.

Derived (paraphrased) from CVE-2026-27696 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.fetch import fetch


def check_watch(watch: dict[str, str]) -> bytes:
    """Re-fetch the page tracked by a watch and return its current body.

    ``watch['url']`` is whatever address the user typed when registering the
    watch; it flows straight into the server-side fetch below without being
    restricted to public destinations.
    """
    url = watch["url"]
    return fetch(url)

"""Low-level HTTP fetcher for watched pages.

Derived (paraphrased) from CVE-2026-27696 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from urllib.request import urlopen


def fetch(url: str) -> bytes:
    """Fetch ``url`` server-side and return the raw response body.

    ``url`` is used exactly as given. There is no check that its hostname
    resolves to a public address, so a request to an internal or link-local
    address is issued just as readily as one to a public site.
    """
    with urlopen(url) as response:
        body: bytes = response.read()
    return body

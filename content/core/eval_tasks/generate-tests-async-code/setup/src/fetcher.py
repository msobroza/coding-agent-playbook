"""Async coroutine for the async-tests eval task.

Realistic enough to exercise the async testing pattern without forcing the
agent to mock an entire HTTP client. The fetcher accepts a ``client`` argument
so the test can inject a stub coroutine.
"""

from typing import Protocol


class _HTTPClient(Protocol):
    async def get_json(self, url: str) -> dict[str, object]:
        """Return the JSON payload at ``url``."""
        ...


async def fetch_payload(client: _HTTPClient, url: str) -> dict[str, object]:
    """Fetch ``url`` through ``client`` and unwrap the ``data`` envelope.

    Raises ``KeyError`` if the response has no ``data`` key, and ``ValueError``
    if ``data`` is empty.
    """
    response = await client.get_json(url)
    if "data" not in response:
        raise KeyError(f"response from {url!r} missing 'data' envelope")
    payload = response["data"]
    if not payload:
        raise ValueError(f"response from {url!r} carried empty data")
    return payload if isinstance(payload, dict) else {"items": payload}

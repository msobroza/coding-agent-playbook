# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The rotating Domino access token, fetched asynchronously and attached by an httpx auth flow.

Inside a Domino run a hosted model endpoint takes a short-lived bearer token from
the run's local access-token endpoint. LocalAccessTokenProvider owns that exchange
(a timeout on every fetch, a short cache, one lock so concurrent requests share one
fetch, one retry on a transient failure); DominoTokenAuth sets the header on every
model request and, on a 401, invalidates the token and sends the request once more.
Neither ever logs, prints or raises with the token in it.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable, Generator
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class AccessTokenProvider(Protocol):
    """Hands out the current access token; invalidate() forces the next call to fetch."""

    async def token(self) -> str: ...

    def invalidate(self) -> None: ...


class TokenUnavailableError(RuntimeError):
    """The access-token endpoint did not answer; carries the URL, never a token.

    ``transient`` says whether one more try is worth it (a timeout, a broken
    connection or a 5xx answer).
    """

    def __init__(self, url: str, *, transient: bool) -> None:
        super().__init__(f"no access token from {url}")
        self.transient = transient


def _is_transient(exc: httpx.HTTPError) -> bool:
    """A timeout, a broken connection or a 5xx answer: worth one more try."""
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class LocalAccessTokenProvider:
    """Fetches the token from the run's access-token endpoint and caches it for ``ttl_seconds``.

    The client carries the timeout; the clock is time.monotonic in production and a
    fake in tests. Keep the TTL well below the token's rotation period.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._url = url
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    def __repr__(self) -> str:
        return f"LocalAccessTokenProvider(url={self._url!r})"

    async def token(self) -> str:
        async with self._lock:
            if self._token is None or self._clock() >= self._expires_at:
                self._token = await self._fetch_with_one_retry()
                self._expires_at = self._clock() + self._ttl_seconds
            return self._token

    def invalidate(self) -> None:
        self._token = None

    async def _fetch_with_one_retry(self) -> str:
        try:
            return await self._fetch()
        except TokenUnavailableError as exc:
            if not exc.transient:
                raise
            logger.warning(
                "access token fetch failed; retrying once",
                extra={"token_url": self._url, "error": type(exc.__cause__).__name__},
            )
        return await self._fetch()

    async def _fetch(self) -> str:
        try:
            response = await self._client.get(self._url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TokenUnavailableError(self._url, transient=_is_transient(exc)) from exc
        return response.text.strip()


class DominoTokenAuth(httpx.Auth):
    """Sets ``Authorization: Bearer <token>`` on each request; on a 401, refreshes and resends once."""

    def __init__(self, tokens: AccessTokenProvider) -> None:
        self._tokens = tokens

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        raise RuntimeError("DominoTokenAuth works only with httpx.AsyncClient")

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {await self._tokens.token()}"
        response = yield request
        if response.status_code == httpx.codes.UNAUTHORIZED:
            self._tokens.invalidate()
            request.headers["Authorization"] = f"Bearer {await self._tokens.token()}"
            yield request

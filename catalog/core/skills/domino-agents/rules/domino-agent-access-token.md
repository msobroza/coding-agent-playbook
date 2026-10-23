---
id: domino-agent-access-token
name: Domino agent access token
description: "Fetch the rotating Domino access token through one async provider with a timeout, a short cache, one lock and a domain error that never names the token."
version: 1
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*token*.py"
  - "**/*auth*.py"
  - "**/llm.py"
  - "**/*agent*.py"
applies_if:
  domino_project: true
section: secrets
priority: 21
tags: [python, domino, agents, security]
---

# Domino agent access token

Inside workspaces, Jobs and Apps, a Domino-hosted model endpoint takes a short-lived token from the run's local access-token endpoint, and that token rotates every few minutes. One async token provider, built in the composition root, owns the whole exchange:

- the token URL is one setting, derived from `DOMINO_API_PROXY` when it is set (add the scheme when the value is `host:port`), else the local proxy on port 8899; never a literal repeated across modules;
- a timeout on every fetch, and a cache refreshed well before the rotation (TTL from settings);
- one `asyncio.Lock`, so concurrent requests share one fetch;
- `invalidate()` for the auth flow's 401 path (domino-agent-endpoint-auth);
- a domain error naming the URL, never the token, and at most one retry, for a transient failure only.

Outside Domino, settings say so and no provider is built, so no Authorization header is sent.

## Bad Example

```python
import requests


async def add_token(request: httpx.Request) -> None:
    # Blocks the event loop, has no timeout, and fetches on every model call.
    token = requests.get("http://localhost:8899/access-token").text
    request.headers["Authorization"] = f"Bearer {token}"
```

## Good Example

```python
class TokenUnavailableError(RuntimeError):
    """The access-token endpoint did not answer; carries the URL, never a token."""


class LocalAccessTokenProvider:
    def __init__(
        self, client: httpx.AsyncClient, url: str, ttl: float, clock: Callable[[], float]
    ) -> None:
        self._client, self._url, self._ttl, self._clock = client, url, ttl, clock
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._expires = 0.0

    def __repr__(self) -> str:
        return f"LocalAccessTokenProvider(url={self._url!r})"

    async def token(self) -> str:
        async with self._lock:
            if self._token is None or self._clock() >= self._expires:
                self._token = await self._fetch()
                self._expires = self._clock() + self._ttl
            return self._token

    def invalidate(self) -> None:
        self._token = None

    async def _fetch(self) -> str:
        try:
            response = await self._client.get(self._url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TokenUnavailableError(f"no access token from {self._url}") from exc
        return response.text.strip()
```

The `httpx.AsyncClient` carries a timeout from settings, and the clock is `time.monotonic` in production and a fake in tests.

## Notes

- Domino platform API calls go through the API proxy or python-domino, which attach the token themselves (domino-api-proxy-auth, domino-jobs).
- The token is never logged, persisted or passed to a traced function (domino-agent-redact-traces).
- Retry policy follows python-retries-and-timeouts (python-coding), where the repo declares requests, httpx or aiohttp.
- The 6.2 docs describe the proxy variable and its port; the access-token path comes from the agent example, so confirm it on your deployment.
- See examples/simple-agent-api/app/domino_token.py.

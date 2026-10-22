"""The token provider and auth flow against a mock access-token endpoint and a fake clock."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import httpx
import pytest

from app.domino_token import DominoTokenAuth, LocalAccessTokenProvider, TokenUnavailableError
from tests.fakes import FakeClock, FakeTokenProvider

TOKEN_URL = "http://localhost:8899/access-token"
SECRET = "secret-token-value"
pytestmark = pytest.mark.anyio


class TokenEndpoint:
    """A mock access-token endpoint: numbered secret tokens, or a timeout on every call."""

    def __init__(self, *, time_out: bool = False) -> None:
        self.calls = 0
        self.time_out = time_out

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.time_out:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, text=f"{SECRET}-{self.calls}\n")


@contextlib.asynccontextmanager
async def provider(
    endpoint: TokenEndpoint, clock: FakeClock
) -> AsyncIterator[LocalAccessTokenProvider]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint), timeout=1.0) as client:
        yield LocalAccessTokenProvider(client, TOKEN_URL, ttl_seconds=60.0, clock=clock)


async def test_a_token_inside_its_ttl_comes_from_the_cache() -> None:
    endpoint, clock = TokenEndpoint(), FakeClock()
    async with provider(endpoint, clock) as tokens:
        first = await tokens.token()
        clock.advance(59)
        second = await tokens.token()

        assert first == second == f"{SECRET}-1"
        assert endpoint.calls == 1


async def test_a_token_past_its_ttl_is_fetched_again() -> None:
    endpoint, clock = TokenEndpoint(), FakeClock()
    async with provider(endpoint, clock) as tokens:
        await tokens.token()
        clock.advance(61)

        assert await tokens.token() == f"{SECRET}-2"


async def test_concurrent_callers_share_one_fetch() -> None:
    endpoint = TokenEndpoint()
    async with provider(endpoint, FakeClock()) as tokens:
        results = await asyncio.gather(*(tokens.token() for _ in range(5)))

        assert set(results) == {f"{SECRET}-1"}
        assert endpoint.calls == 1


async def test_a_timeout_retries_once_then_raises_without_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint = TokenEndpoint(time_out=True)
    async with provider(endpoint, FakeClock()) as tokens:
        caplog.set_level(logging.DEBUG)

        with pytest.raises(TokenUnavailableError, match="localhost:8899") as raised:
            await tokens.token()

        assert endpoint.calls == 2
        assert SECRET not in str(raised.value)
        assert SECRET not in repr(tokens)


async def test_a_client_error_is_not_retried() -> None:
    calls: list[httpx.Request] = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        tokens = LocalAccessTokenProvider(client, TOKEN_URL, ttl_seconds=60.0, clock=FakeClock())

        with pytest.raises(TokenUnavailableError) as raised:
            await tokens.token()

    assert len(calls) == 1
    assert not raised.value.transient


async def test_no_token_value_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    async with provider(TokenEndpoint(), FakeClock()) as tokens:
        caplog.set_level(logging.DEBUG)

        await tokens.token()

        assert SECRET not in caplog.text


async def test_the_auth_flow_retries_once_with_a_fresh_token_after_a_401() -> None:
    seen: list[str] = []

    def model_endpoint(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(401 if len(seen) == 1 else 200, json={"ok": True})

    tokens = FakeTokenProvider()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(model_endpoint), auth=DominoTokenAuth(tokens)
    ) as client:
        response = await client.post("https://models.example.com/v1/chat/completions", json={})

    assert response.status_code == 200
    assert seen == ["Bearer token-1", "Bearer token-2"]
    assert tokens.invalidations == 1

# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The composition root: create_app(settings) builds the whole agent service once.

Nothing happens at import. create_app builds the HTTP clients (with timeouts from
settings), the token provider (only for a Domino-hosted model endpoint), the
model, the agent, the traced request function and the A2A sub-app, stores them on
app.state and mounts /a2a. The lifespan runs the A2A app's own lifespan (its task
worker) and closes both clients afterwards. The error table turns the agent's own
failures into 502 and 504 with fixed bodies; anything else stays a 500.
"""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Final

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from starlette.applications import Starlette

from app.a2a import A2A_PATH, build_a2a_app
from app.agent import AskAgent, build_agent, make_ask
from app.chat import router as chat_router
from app.domino_token import (
    AccessTokenProvider,
    DominoTokenAuth,
    LocalAccessTokenProvider,
    TokenUnavailableError,
)
from app.llm import ModelSetupError, build_model
from app.settings import AgentConfig, AgentSettings, load_agent_config
from app.tracing import REQUEST_SPAN_NAME, Tracer, select_tracer

logger = logging.getLogger(__name__)

#: The agent's own failures, mapped to a status and a fixed body that leaks nothing.
ERROR_TABLE: Final[Mapping[type[Exception], tuple[int, str]]] = {
    ModelHTTPError: (502, "The model provider failed; try again later."),
    UnexpectedModelBehavior: (502, "The model returned an unusable answer."),
    UsageLimitExceeded: (502, "The agent reached its request limit."),
    TokenUnavailableError: (502, "The model endpoint is unavailable."),
    asyncio.TimeoutError: (504, "The agent took too long to answer."),
}


@dataclass(frozen=True)
class AgentRuntime:
    """What the App and the development evaluation Job share: the agent and its clients."""

    config: AgentConfig
    agent: Agent[None, str]
    ask: AskAgent
    clients: tuple[httpx.AsyncClient, ...]

    async def aclose(self) -> None:
        """Close every client, even when one close fails."""
        for client in self.clients:
            try:
                await client.aclose()
            except Exception:
                logger.exception("closing an HTTP client failed")


def build_runtime(
    settings: AgentSettings,
    *,
    model: Model | None = None,
    token_provider: AccessTokenProvider | None = None,
    rng: random.Random | None = None,
) -> AgentRuntime:
    """Build the agent from the config file and settings; no I/O happens here.

    A Domino-hosted endpoint gets a model client whose auth flow sets the rotating
    token; the token provider is the injected one or, inside Domino, one that reads
    the run's access-token endpoint.
    """
    config = load_agent_config(settings.config_path)
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    token_client = httpx.AsyncClient(timeout=timeout)
    auth: httpx.Auth | None = None
    if config.model.provider == "domino-endpoint":
        tokens = token_provider or _local_token_provider(settings, token_client)
        auth = DominoTokenAuth(tokens)
    model_client = httpx.AsyncClient(timeout=timeout, auth=auth)
    agent = build_agent(
        model or build_model(config, settings, model_client),
        config,
        rng=rng or random.Random(),
    )
    return AgentRuntime(config, agent, make_ask(agent, config), (model_client, token_client))


def _local_token_provider(
    settings: AgentSettings, client: httpx.AsyncClient
) -> AccessTokenProvider:
    if not settings.in_domino:
        raise ModelSetupError(
            "the domino-endpoint provider runs only inside Domino: DOMINO_API_HOST is not set"
        )
    return LocalAccessTokenProvider(
        client, settings.token_url, ttl_seconds=settings.token_ttl_seconds
    )


def _lifespan(
    a2a_app: Starlette, runtime: AgentRuntime
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            async with a2a_app.router.lifespan_context(a2a_app):
                yield
        finally:
            await runtime.aclose()

    return lifespan


def _error_handler(
    status: int, detail: str
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "agent request failed",
            exc_info=exc,
            extra={"status": status, "error": type(exc).__name__, "path": request.url.path},
        )
        return JSONResponse(status_code=status, content={"detail": detail})

    return handle


def _install_error_table(app: FastAPI) -> None:
    for exc_type, (status, detail) in ERROR_TABLE.items():
        app.add_exception_handler(exc_type, _error_handler(status, detail))


def _add_cors(app: FastAPI, origins: Sequence[str]) -> None:
    """CORS from an explicit allow-list only, without credentials; off when the list is empty."""
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )


def create_app(
    settings: AgentSettings,
    *,
    model: Model | None = None,
    token_provider: AccessTokenProvider | None = None,
    tracer: Tracer | None = None,
    rng: random.Random | None = None,
) -> FastAPI:
    """The agent App; tests pass a fake model, token provider and tracer."""
    runtime = build_runtime(settings, model=model, token_provider=token_provider, rng=rng)
    tracer = tracer or select_tracer(settings)
    a2a_app = build_a2a_app(runtime.agent, runtime.config, settings)

    app = FastAPI(
        title="Simple agent API",
        description="Answers questions with one short line, over REST and A2A.",
        version=runtime.config.version,
        lifespan=_lifespan(a2a_app, runtime),
        docs_url=None,
        redoc_url=None,
    )
    app.state.ask = tracer.trace(REQUEST_SPAN_NAME)(runtime.ask)
    app.state.agent = runtime.agent
    _install_error_table(app)
    _add_cors(app, settings.cors_origins)
    app.include_router(chat_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/docs", include_in_schema=False)
    async def docs() -> HTMLResponse:
        # A relative openapi URL, so the docs work under the App's path prefix.
        return get_swagger_ui_html(openapi_url="openapi.json", title=f"{app.title} - docs")

    app.mount(A2A_PATH, a2a_app)
    return app

# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The chat model the agent talks to, with its auth and its HTTP clients, per provider.

Each provider's whole wiring lives here, one function per provider: what the
settings must hold for it, its HTTP client and its auth. A missing variable fails
before any client is built, naming the variable. The model name always comes
from the config. The ``openai`` provider receives its key from settings
explicitly, so no library reads the environment deep inside. The
``domino-endpoint`` provider talks to a Domino-hosted, OpenAI-compatible endpoint
through a client that carries DominoTokenAuth, which sets a fresh bearer token on
every request; the agent is never rebuilt to rotate it.
"""

from dataclasses import dataclass
from typing import Final

import httpx
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.domino_token import AccessTokenProvider, DominoTokenAuth, LocalAccessTokenProvider
from app.settings import AgentConfig, AgentSettings

#: The OpenAI client needs some key; DominoTokenAuth replaces the header it builds.
_HEADER_SET_BY_AUTH_FLOW: Final = "set-by-domino-token-auth"


class ModelSetupError(RuntimeError):
    """The settings lack what the configured provider needs; names the missing variable."""


@dataclass(frozen=True)
class ChatModel:
    """The model, and the HTTP clients it owns, which the runtime closes."""

    model: Model
    clients: tuple[httpx.AsyncClient, ...]


def build_model(
    config: AgentConfig,
    settings: AgentSettings,
    *,
    token_provider: AccessTokenProvider | None = None,
) -> ChatModel:
    """The OpenAI-compatible chat model for ``config.model``; tests pass a token provider."""
    if config.model.provider == "domino-endpoint":
        return _domino_endpoint_model(config, settings, token_provider)
    return _openai_model(config, settings)


def _client(settings: AgentSettings, auth: httpx.Auth | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds), auth=auth)


def _openai_model(config: AgentConfig, settings: AgentSettings) -> ChatModel:
    if settings.openai_api_key is None:
        raise ModelSetupError("OPENAI_API_KEY is not set; add it as a project environment variable")
    client = _client(settings)
    provider = OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(), http_client=client
    )
    return ChatModel(OpenAIChatModel(config.model.name, provider=provider), (client,))


def _domino_endpoint_model(
    config: AgentConfig, settings: AgentSettings, token_provider: AccessTokenProvider | None
) -> ChatModel:
    if settings.endpoint_base_url is None:
        raise ModelSetupError(
            "SIMPLE_AGENT_ENDPOINT_BASE_URL is required for the domino-endpoint provider"
        )
    owned: tuple[httpx.AsyncClient, ...] = ()
    if token_provider is None:
        token_provider, token_client = _local_token_provider(settings)
        owned = (token_client,)
    model_client = _client(settings, auth=DominoTokenAuth(token_provider))
    provider = OpenAIProvider(
        base_url=str(settings.endpoint_base_url),
        api_key=_HEADER_SET_BY_AUTH_FLOW,
        http_client=model_client,
    )
    return ChatModel(OpenAIChatModel(config.model.name, provider=provider), (model_client, *owned))


def _local_token_provider(
    settings: AgentSettings,
) -> tuple[AccessTokenProvider, httpx.AsyncClient]:
    """The run's access-token endpoint and the client that reads it; only inside Domino."""
    if not settings.in_domino:
        raise ModelSetupError(
            "the domino-endpoint provider runs only inside Domino: DOMINO_API_HOST is not set"
        )
    client = _client(settings)
    tokens = LocalAccessTokenProvider(
        client, settings.access_token_url, ttl_seconds=settings.token_ttl_seconds
    )
    return tokens, client

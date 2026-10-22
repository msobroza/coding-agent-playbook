# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The chat model the agent talks to, built from the config and the settings.

The model name always comes from the config. The ``openai`` provider receives its
key from settings explicitly, so no library reads the environment deep inside and
a missing key fails at startup. The ``domino-endpoint`` provider talks to a
Domino-hosted, OpenAI-compatible endpoint through the shared client that carries
DominoTokenAuth, which sets a fresh bearer token on every request; the agent is
never rebuilt to rotate it.
"""

from typing import Final

import httpx
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.settings import AgentConfig, AgentSettings

#: The OpenAI client needs some key; DominoTokenAuth replaces the header it builds.
_HEADER_SET_BY_AUTH_FLOW: Final = "set-by-domino-token-auth"


class ModelSetupError(RuntimeError):
    """The settings lack what the configured provider needs; names the missing variable."""


def build_model(
    config: AgentConfig, settings: AgentSettings, http_client: httpx.AsyncClient
) -> OpenAIChatModel:
    """The OpenAI-compatible chat model for ``config.model``, sharing ``http_client``."""
    if config.model.provider == "domino-endpoint":
        if settings.endpoint_base_url is None:
            raise ModelSetupError(
                "SIMPLE_AGENT_ENDPOINT_BASE_URL is required for the domino-endpoint provider"
            )
        provider = OpenAIProvider(
            base_url=str(settings.endpoint_base_url),
            api_key=_HEADER_SET_BY_AUTH_FLOW,
            http_client=http_client,
        )
    else:
        if settings.openai_api_key is None:
            raise ModelSetupError(
                "OPENAI_API_KEY is not set; add it as a project environment variable"
            )
        provider = OpenAIProvider(
            api_key=settings.openai_api_key.get_secret_value(), http_client=http_client
        )
    return OpenAIChatModel(config.model.name, provider=provider)

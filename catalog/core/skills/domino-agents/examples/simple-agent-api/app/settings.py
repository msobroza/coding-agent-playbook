"""Typed settings from the environment, and the agent config file they point to.

AgentSettings holds everything that differs per deployment or is secret: the
provider key, the hosted endpoint, the Domino token URL, the published App URL,
the evaluation Jobs' agent id, version and watermark path. Entry points (app/asgi.py
and the two evaluation Jobs) build it once and pass it down; nothing else reads
the environment. AgentConfig is the non-secret agent_config.yaml, which DominoRun
logs with every evaluation run, so each of its keys takes effect.
"""

from pathlib import Path
from typing import Literal
from urllib.parse import urlunsplit

import yaml
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The example's root directory: agent_config.yaml sits next to app/.
EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
#: The local access-token endpoint of a Domino run, used when DOMINO_API_PROXY is unset.
DEFAULT_TOKEN_URL = "http://localhost:8899/access-token"

Provider = Literal["openai", "domino-endpoint"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class AgentSettings(BaseSettings):
    """The agent's deployment settings, from SIMPLE_AGENT_* and Domino's own variables."""

    model_config = SettingsConfigDict(env_prefix="SIMPLE_AGENT_", validate_by_name=True)

    config_path: Path = EXAMPLE_ROOT / "agent_config.yaml"
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    # Set by Domino inside workspaces, Jobs and Apps; read under their own names.
    domino_api_host: str | None = Field(default=None, validation_alias="DOMINO_API_HOST")
    domino_api_proxy: str | None = Field(default=None, validation_alias="DOMINO_API_PROXY")
    endpoint_base_url: AnyHttpUrl | None = None
    # None: derived from DOMINO_API_PROXY (see access_token_url).
    token_url: AnyHttpUrl | None = None
    token_ttl_seconds: float = Field(default=60.0, gt=0)
    http_timeout_seconds: float = Field(default=30.0, gt=0)
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8888")
    provider_organization: str = "Example Org"
    provider_url: AnyHttpUrl = AnyHttpUrl("https://example.com")
    cors_origins: list[str] = Field(default_factory=list)
    log_level: LogLevel = "INFO"
    # The development evaluation Job.
    experiment_name: str = "simple-agent-api-dev-eval"
    # The production evaluation Job.
    agent_id: str | None = None
    agent_version: str | None = None
    watermark_path: Path | None = None
    lookback_hours: float = Field(default=24.0, gt=0)
    trace_overlap_seconds: float = Field(default=300.0, ge=0)

    @property
    def in_domino(self) -> bool:
        """True inside a Domino workspace, Job or App: Domino sets DOMINO_API_HOST there."""
        return bool(self.domino_api_host)

    @property
    def access_token_url(self) -> str:
        """The token URL: set explicitly, else DOMINO_API_PROXY's access-token path, else the default.

        A bare host:port proxy gets the plain-HTTP scheme of the run-local proxy.
        """
        if self.token_url is not None:
            return str(self.token_url)
        if not self.domino_api_proxy:
            return DEFAULT_TOKEN_URL
        proxy = self.domino_api_proxy.rstrip("/")
        base = proxy if "://" in proxy else urlunsplit(("http", proxy, "", "", ""))
        return f"{base}/access-token"


class ModelConfig(BaseModel):
    """Which model answers, and how."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    name: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)


class RunConfig(BaseModel):
    """The bounds of one agent run and of an A2A conversation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retries: int = Field(ge=0)
    request_limit: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_history: int = Field(ge=0)


class PromptConfig(BaseModel):
    """The prompts the agent is built with."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system: str = Field(min_length=1)


class AgentConfig(BaseModel):
    """agent_config.yaml, validated: unknown keys are an error, so none is only logged."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    model: ModelConfig
    agent: RunConfig
    prompts: PromptConfig


class AgentConfigError(Exception):
    """The agent config file is missing, not YAML, or not a valid AgentConfig."""


def load_agent_config(path: Path) -> AgentConfig:
    """Read and validate the agent config file; a bad file fails naming its path."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return AgentConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise AgentConfigError(f"invalid agent config {path}: {exc}") from exc

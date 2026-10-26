---
id: domino-agent-settings
name: Domino agent settings
description: "Decide once in typed settings whether the agent runs in Domino, and branch every Domino-dependent choice on that flag."
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*config*.yaml"
  - "**/*config*.yml"
  - "**/.env.example"
applies_if:
  domino_project: true
section: configuration
priority: 45
tags: [python, domino, agents, settings]
---

# Decide Domino-dependent behavior in one settings object

## Description

An agent service behaves differently inside Domino and on a laptop: inside it needs a token provider for hosted models, the real tracer and the published App URL; outside it needs none of them. Read that difference once, in the agent's settings, as one flag (`in_domino`, true when `DOMINO_API_HOST` is set), and branch every Domino-dependent choice on it: token provider on or off, real or no-op tracer, local or published App URL. The token URL comes from `DOMINO_API_PROXY`. The evaluation Jobs read the agent id, agent version, experiment name and watermark path from settings or arguments, never from literals. Variables Domino injects are read through `validation_alias` under their own names; the repo's own variables carry its prefix. The agent SDK's own variables (`DOMINO_AGENT_CONFIG_PATH`, `DOMINO_AGENT_IS_PROD`, `DOMINO_APP_ID`) and `MLFLOW_TRACKING_URI` are read where needed and never set by the repo.

## Bad Example

```python
import os

IN_DOMINO = "DOMINO_API_HOST" in os.environ
TOKEN_URL = "http://localhost:8899/access-token"
WATERMARK = "/mnt/data/" + os.environ.get("DOMINO_PROJECT_NAME") + "/watermark.json"
AGENT_ID = "6650f0c2a1"
AGENT_VERSION = "3"
```

The flag and the URL are module constants every module re-derives, the path concatenation raises `TypeError` when the variable is unset, and the agent ids are hard-coded.

## Good Example

```python
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["openai", "domino-endpoint"]


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    domino_api_host: str | None = Field(default=None, validation_alias="DOMINO_API_HOST")
    domino_api_proxy: str | None = Field(default=None, validation_alias="DOMINO_API_PROXY")
    provider: Provider = "openai"
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    endpoint_base_url: AnyHttpUrl | None = None
    agent_id: str | None = None
    agent_version: str | None = None
    experiment_name: str = "agent-dev-eval"
    watermark_path: Path | None = None

    @property
    def in_domino(self) -> bool:
        return self.domino_api_host is not None

    @model_validator(mode="after")
    def _endpoint_for_domino_provider(self) -> "AgentSettings":
        if self.provider == "domino-endpoint" and self.endpoint_base_url is None:
            raise ValueError("AGENT_ENDPOINT_BASE_URL is required for the domino-endpoint provider")
        return self
```

The entry point builds `AgentSettings()` once and passes it down; `create_app`, the token provider and the tracer seam read `settings.in_domino` instead of the environment.

## Notes

- Domino sets `MLFLOW_TRACKING_URI` inside runs; outside Domino the flag is false and nothing calls the token endpoint.
- One settings module read once and passed down is domino-paths-from-env, and variable names and reserved prefixes are domino-env-var-names (both domino-jobs).
- Where the repo uses pydantic-settings, the mechanics are pydantic-typed-settings (python-coding).
- The provider key itself is `domino-agent-llm-keys`; the agent's model choices live in the config file (`domino-agent-config-file`).
- See examples/simple-agent-api/app/settings.py for the full settings class.

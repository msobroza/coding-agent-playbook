---
id: domino-agent-llm-keys
name: Domino agent LLM provider keys
description: "Keep provider keys and model endpoint hosts out of the agent config file and hand the key to the provider explicitly from settings."
version: 1
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*token*.py"
  - "**/*auth*.py"
  - "**/llm.py"
  - "**/*agent*.py"
  - "**/*config*.yaml"
  - "**/*config*.yml"
applies_if:
  domino_project: true
section: secrets
priority: 20
tags: [python, domino, agents, security]
---

# Domino agent LLM provider keys

`DominoRun` attaches the agent config file to the experiment run and to the logged model, so everyone who can read the experiment reads every value in it. The file therefore holds only non-secret choices: provider, model name, parameters and the system prompt. Provider keys (`OPENAI_API_KEY` and its peers) and the host or id of a Domino-hosted model endpoint come from settings fed by environment variables.

The model builder receives the key from settings and passes it to the provider explicitly, so no library reads the environment deep inside, and a missing key fails at startup, not on the first user request.

## Bad Example

```yaml
# agent_config.yaml: logged with every evaluation run
model:
  provider: openai
  name: gpt-4o-mini
  api_key: "sk-example-not-a-real-key"
  base_url: https://models.example.com/endpoints/1234/v1
```

```python
import os

from pydantic_ai.providers.openai import OpenAIProvider


def build_provider() -> OpenAIProvider:
    # The key is read deep inside, long after startup, and never validated.
    return OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
```

## Good Example

```yaml
# agent_config.yaml: choices only, no secrets, no hosts
model:
  provider: openai
  name: gpt-4o-mini
  temperature: 0.2
```

```python
from pydantic import Field, SecretStr
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")


def build_provider(settings: AgentSettings) -> OpenAIProvider:
    if settings.openai_api_key is None:
        raise ValueError("OPENAI_API_KEY is not set; add it as a project environment variable")
    return OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
```

## Notes

- Which variable level a key belongs to (project or user) is domino-secrets-in-env-vars (domino-jobs), and an App runs with the variables of whoever starts it (domino-app-starter-settings, domino-apps).
- Settings mechanics are pydantic-typed-settings and pydantic-special-types (python-coding), where the repo uses pydantic-settings.
- Keys never reach a traced parameter or return value (domino-agent-redact-traces).
- See examples/simple-agent-api/app/settings.py and examples/simple-agent-api/agent_config.yaml.

---
id: domino-agent-config-file
name: Agent config file
description: "Keep the agent's model choices in one agent_config.yaml, loaded into a strict typed model, whose every key takes effect."
version: 1
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
priority: 46
tags: [python, domino, agents, config]
---

# Make every agent config key take effect

## Description

Provider, model name, temperature, max tokens, retries, request limit, run timeout, history length and the system prompt live in one YAML file, `agent_config.yaml` (the SDK's default name). The App and the evaluation Job both load it at startup into a typed model that forbids unknown keys. `DominoRun` attaches this file to the experiment run and to the logged model, and Experiment Manager compares runs by it, so the values it records must be the ones that ran: every key changes behavior (temperature and max tokens reach the model settings), and none is only logged. Switching models is a config change, not a code change. Secrets and hosts stay out of the file.

## Bad Example

```python
import yaml

with open("agent_config.yaml", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

MODEL_NAME = CONFIG["model"]["name"]
print("temperature:", CONFIG["model"]["temperature"])  # logged, never sent
print("max_history:", CONFIG["agent"]["max_history"])  # logged, never applied
```

The file is read at import into a raw dict, and two keys the run records never reach the model.

## Good Example

```python
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Provider = Literal["openai", "domino-endpoint"]


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    model_name: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    retries: int = Field(ge=0)
    request_limit: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_history: int = Field(ge=0)
    system_prompt: str


class AgentConfigError(Exception):
    """The agent config file is missing or invalid."""


def load_agent_config(path: Path) -> AgentConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return AgentConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise AgentConfigError(f"invalid agent config {path}: {exc}") from exc
```

A test per key proves it reaches the run, so a key that only gets logged fails:

```python
from pydantic_ai.settings import ModelSettings


def build_model_settings(config: AgentConfig) -> ModelSettings:
    return ModelSettings(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )


def test_config_keys_reach_the_model_settings(tmp_path: Path) -> None:
    path = tmp_path / "agent_config.yaml"
    path.write_text(VALID_CONFIG_YAML, encoding="utf-8")  # temperature 0.2, max_tokens 512

    model_settings = build_model_settings(load_agent_config(path))

    assert model_settings == {"temperature": 0.2, "max_tokens": 512, "timeout": 30.0}
```

The other keys get the same test where they land: the agent (retries, system prompt), its usage limits and the history trim.

## Notes

- The deployed agent loads the file at the commit the evaluation compared (`domino-agent-dev-eval-job`).
- Provider keys and endpoint hosts never go in this file (`domino-agent-llm-keys`); the path comes from settings (`domino-agent-settings`).
- Where the repo uses pydantic, validation at this boundary is pydantic-boundaries (python-coding).
- See examples/simple-agent-api/agent_config.yaml and examples/simple-agent-api/app/settings.py.

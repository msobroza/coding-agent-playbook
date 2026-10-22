---
id: domino-app-endpoint-auth
name: Model endpoint auth
description: "Call a restricted Domino model endpoint with its access token from settings: basic auth for sync, Bearer for async, through one client with a timeout."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
  - "**/clients.py"
  - "**/settings.py"
applies_if:
  domino_project: true
section: access
priority: 29
tags: [python, domino, apps, security]
---

# Model endpoint auth

## Description

A Domino model endpoint is unrestricted or restricted. A restricted one needs its model access token, and the scheme depends on the mode: a synchronous endpoint takes HTTP basic auth with the token as both username and password, an asynchronous one a `Bearer` header. Tokens are per endpoint and can be revoked or regenerated, so they never belong in code.

## Bad Example

```python
import httpx

URL = "https://models.example.com/v1/predict"
TOKEN = "hard-coded-token"


def predict(features: list[float]) -> float:
    response = httpx.post(
        URL, json={"data": features}, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    return float(response.json()["result"])
```

## Good Example

```python
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import httpx


class EndpointMode(Enum):
    SYNC = "sync"
    ASYNC = "async"


@dataclass(frozen=True)
class EndpointSettings:
    url: str
    token: str  # never logged
    mode: EndpointMode


def load_endpoint_settings(environ: Mapping[str, str]) -> EndpointSettings:
    """Read once at startup, so a missing variable fails there, not in a callback."""
    return EndpointSettings(
        url=environ["MYAPP_MODEL_URL"],
        token=environ["MYAPP_MODEL_TOKEN"],
        mode=EndpointMode(environ.get("MYAPP_MODEL_MODE", "sync")),
    )


def endpoint_client(settings: EndpointSettings, *, timeout_s: float = 10.0) -> httpx.Client:
    """One client for the App's lifetime, built in the composition root."""
    if settings.mode is EndpointMode.SYNC:
        return httpx.Client(auth=(settings.token, settings.token), timeout=timeout_s)
    headers = {"Authorization": f"Bearer {settings.token}"}
    return httpx.Client(headers=headers, timeout=timeout_s)


def predict(client: httpx.Client, settings: EndpointSettings, features: list[float]) -> float:
    response = client.post(settings.url, json={"data": features})
    response.raise_for_status()
    return float(response.json()["result"])
```

The composition root calls `load_endpoint_settings(os.environ)` once. Where the repo uses pydantic, the token is a `SecretStr` setting.

## Notes

- Timeouts and retries on transient failures only follow `python-retries-and-timeouts` (python-coding skill, where the repo declares an HTTP client).
- Settings load at startup, so a regenerated token needs an App restart.
- Never log the token (`domino-app-viewer-token`).
- The short-lived platform access token used for agent LLM calls belongs to the domino-agents skill.

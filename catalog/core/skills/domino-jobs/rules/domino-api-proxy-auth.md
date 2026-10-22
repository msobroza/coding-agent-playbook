---
id: domino-api-proxy-auth
name: API proxy auth
description: "Inside a run, call the Domino API through DOMINO_API_PROXY with no credential in code; outside Domino, send a service-account token from an environment variable as a Bearer token."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/dags/**/*.py"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 23
tags: [python, domino, jobs, security]
---

# API proxy auth

## Description

Inside a Domino run, `DOMINO_API_PROXY` holds the address of a local proxy that adds the run's credentials to every Domino API request, so job code passes no credential at all. Outside Domino (CI, an orchestrator, a script on a laptop), the caller sends a service-account token, read from an environment variable, as a Bearer token, with the host taken from configuration. API keys are being deprecated, and the token file no longer exists.

## Bad Example

```python
import os

import httpx
from domino import Domino

# A personal API key inside a job: deprecated, and tied to one person.
client = Domino(
    "acme/churn",
    api_key=os.environ["DOMINO_USER_API_KEY"],
    host="https://domino.example.com",
)

# An orchestrator task sending the same kind of key in a header.
httpx.get(
    "https://domino.example.com/v4/projects",
    headers={"X-Domino-Api-Key": os.environ["MY_KEY"]},
)
```

## Good Example

```python
from collections.abc import Mapping
from urllib.parse import urlunsplit

import httpx
from domino import Domino

from jobs.context import JobContext  # the record of domino-paths-from-env
from jobs.settings import Settings  # read once at startup


def proxy_base_url(env: Mapping[str, str]) -> str:
    """The run's API proxy; prefix a scheme when the value has none."""
    value = env["DOMINO_API_PROXY"]
    return value if "://" in value else urlunsplit(("http", value, "", "", ""))


def in_run_client(ctx: JobContext) -> Domino:
    # No authentication arguments: python-domino routes through the proxy.
    return Domino(f"{ctx.project_owner}/{ctx.project_name}")


def raw_client(env: Mapping[str, str]) -> httpx.Client:
    return httpx.Client(base_url=proxy_base_url(env), timeout=10.0)


def outside_client(settings: Settings) -> Domino:
    # CI or an orchestrator: host and service-account token from the environment.
    return Domino(settings.project, host=settings.api_host, auth_token=settings.service_token)
```

## Notes

- python-domino documents that the proxy does not work against an HTTPS endpoint and is meant for use inside runs, so code outside a run never points at it.
- python-domino describes the proxy location as host and port, and no 6.2 page shows a scheme, so `proxy_base_url` adds the plain http scheme only when it is missing (safe behavior where the docs are silent).
- The proxy fetches the token on the first proxied call.
- Personal access tokens are short-lived and suit interactive use only.
- Some 6.2 pages (the Run Jobs SDK example, the Airflow setup, an older wrapper page) still show API keys or token files: follow the authentication page instead.
- python-domino retries connection errors `DOMINO_MAX_RETRIES` times (4 by default). Raw HTTP calls carry an explicit timeout and bounded, transient-only retries (`python-retries-and-timeouts`, python-coding skill).
- Domino 6.2 needs dominodatalab 2.0 or later (PyPI pairs 2.1 with Domino 6.3).
- Newer releases may add authentication modes: re-check the authentication page when the deployment is upgraded.
- Context and settings come from `domino-paths-from-env` and `domino-secrets-in-env-vars`.

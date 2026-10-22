---
id: domino-app-starter-settings
name: Starter's settings
description: "Remember that user-level variables and data credentials come from whoever last started the App; log who that was and which settings were found."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
  - "**/settings.py"
  - "**/config.py"
applies_if:
  domino_project: true
section: access
priority: 28
tags: [python, domino, apps, configuration]
---

# Starter's settings

## Description

An App is a long-running run. Its user-level environment variables and its data-source credentials are those of the person who last started or restarted it, and they override project and compute-environment values of the same name. When a colleague restarts the App, after a platform upgrade for example, the same code runs with that colleague's keys, quotas and data rights, or fails because a variable only the developer defined is gone.

## Bad Example

```python
import os


def summarize(text: str) -> str:
    # LLM_API_KEY exists only as the developer's user variable: after a teammate
    # restarts the App, this fails deep inside a callback with an authorization error.
    return call_llm(os.environ["LLM_API_KEY"], text)
```

## Good Example

```python
import logging
import os
from collections.abc import Mapping

log = logging.getLogger(__name__)

EXPECTED_SETTINGS = ("MYAPP_LLM_API_KEY", "MYAPP_DB_URL")


def log_startup_identity(environ: Mapping[str, str] | None = None) -> None:
    """One line naming the starter and which expected names are set, never their values."""
    env = os.environ if environ is None else environ
    found = [name for name in EXPECTED_SETTINGS if env.get(name)]
    missing = [name for name in EXPECTED_SETTINGS if not env.get(name)]
    log.info(
        "started by %s; settings found=%s missing=%s",
        env.get("DOMINO_STARTING_USERNAME", "unknown"),
        found,
        missing,
    )
```

Settings themselves load once at startup as `domino-secrets-in-env-vars` describes (domino-jobs skill).

## Notes

- Credentials every collaborator may use go into project variables; a personal key ties the App to one starter, so that account, not whoever is around, restarts it.
- Record the account that starts and restarts the App in the deployment record (`domino-app-deployment-record`).
- Data rights follow the starter too (`domino-app-publisher-data-rights`).
- Variable names follow `domino-env-var-names` (domino-jobs skill).

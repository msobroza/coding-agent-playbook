---
id: domino-secrets-in-env-vars
name: Secrets in variables
description: "Pass credentials only as project or user environment variables, read them once at startup, and never write a secret into code, notebooks, requirements, results or logs."
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
  - "requirements*.txt"
  - "**/*.ipynb"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 21
tags: [python, domino, jobs, security]
---

# Secrets in variables

## Description

Domino versions or retains almost everything a project touches: code, notebooks, requirements files, results and execution logs. A secret written into any of them stays readable, and removing it takes an administrator's full delete, which purges every identical file in every project.

Credentials reach a run only as environment variables, set as project or user variables. The code reads each one once at startup, in the settings module, and fails with a message that names the missing variable and where to set it, never its value.

## Bad Example

```python
import os

WAREHOUSE_PASSWORD = "not-a-real-password"  # versioned with the code, forever

print(dict(os.environ))  # copies every credential into the execution log
```

```text
# requirements.txt: the token is stored with the project's files
git+https://<token>@git.example.com/acme/lib.git
```

## Good Example

```python
import os
from collections.abc import Mapping


class MissingSettingError(RuntimeError):
    """A required environment variable is not set for this run."""


def require_env(name: str, env: Mapping[str, str]) -> str:
    value = env.get(name, "")
    if not value:
        raise MissingSettingError(f"{name} is not set: add it as a Domino project or user variable")
    return value


def warehouse_password(env: Mapping[str, str] | None = None) -> str:
    return require_env("ACME_WAREHOUSE_PASSWORD", os.environ if env is None else env)
```

```python
import pytest


def test_missing_password_names_the_variable() -> None:
    with pytest.raises(MissingSettingError, match="ACME_WAREHOUSE_PASSWORD"):
        warehouse_password({})
```

## Notes

- Every collaborator can read project variable values, so only credentials every collaborator may hold go there.
- Personal credentials go into user variables. Domino injects them only into runs that user starts: a run started by a collaborator, a Launcher user or a service account does not get them, and models never do.
- The 6.2 docs disagree on who may edit project variables (the owner only, or collaborators too). Assume values can change outside code review and validate them at startup.
- Values are passed verbatim up to 64K characters, so a PEM key fits without escaping.
- Never print or log a secret value: execution logs are kept indefinitely (`domino-job-logging`).
- Private Git dependencies use Domino's Git credentials, never a token in a URL.
- Where the repo uses pydantic, hold secrets as `SecretStr` (`pydantic-special-types`, python-coding skill).
- Variable names and reserved prefixes follow `domino-env-var-names`.

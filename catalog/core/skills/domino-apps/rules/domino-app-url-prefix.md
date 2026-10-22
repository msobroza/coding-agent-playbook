---
id: domino-app-url-prefix
name: URL prefix
description: "Take the App's URL prefix from DOMINO_RUN_HOST_PATH at startup; never assemble it from owner, project and run id."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
  - "**/app.py"
  - "**/run.py"
  - "**/settings.py"
  - "**/config.py"
applies_if:
  domino_project: true
section: launch
priority: 21
tags: [python, domino, apps]
---

# URL prefix

## Description

Viewers reach an App under a path prefix, and the server needs that prefix to build links and, for some frameworks, to route. On Domino 6.2 the secure identity flag is on by default and Apps are served under `/apps/<app-id>/`. Older code builds the prefix by hand from `DOMINO_PROJECT_OWNER`, `DOMINO_PROJECT_NAME` and `DOMINO_RUN_ID`; that path stops resolving, and the App shows blank pages or 404 and 502 errors, at its next restart under the flag.

Domino injects the full prefix as `DOMINO_RUN_HOST_PATH` when the App starts, and the variable is right with the flag on or off. Read it once at startup and hand the same value to the framework.

## Bad Example

```python
import os

prefix = (
    f"/{os.environ['DOMINO_PROJECT_OWNER']}/{os.environ['DOMINO_PROJECT_NAME']}"
    f"/notebookSession/{os.environ['DOMINO_RUN_ID']}/"
)
```

## Good Example

```python
import os
from dataclasses import dataclass


def normalize_prefix(raw: str) -> str:
    """One leading and one trailing slash; ``/`` for an empty value (local runs)."""
    stripped = raw.strip("/")
    return f"/{stripped}/" if stripped else "/"


@dataclass(frozen=True)
class AppConfig:
    url_prefix: str


def load_config() -> AppConfig:
    return AppConfig(url_prefix=normalize_prefix(os.environ.get("DOMINO_RUN_HOST_PATH", "")))
```

## Notes

- The breakage appears only at the next restart or platform upgrade, so restart the App and check it after any change to the flag or the platform version.
- Before 6.1.1 the flag defaulted to off and Apps used the older path; the variable, not a hand-built path, is the only form that works in both modes.
- A workspace preview legitimately builds an owner, project and run-id URL; that helper is out of scope here (`domino-app-workspace-preview`).
- Where the repo declares pydantic-settings, load the value as a typed setting (`pydantic-typed-settings`, python-coding skill).
- Each framework's wiring of the prefix is in its framework rule (`domino-app-dash`, `domino-app-flask`); links built from it follow `domino-app-relative-urls`.
- Blank pages or 404s after a restart: see app-troubleshooting.md.

---
id: domino-app-viewer-token
name: Viewer token
description: "Treat the viewer's token as a credential: use it per request only, never log, store, forward or put it in a URL."
scope: scoped
globs:
  - "**/app.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/auth.py"
  - "**/identity.py"
applies_if:
  domino_project: true
section: access
priority: 27
tags: [python, domino, apps, security]
---

# Viewer token

## Description

The `Authorization` token on each request is a credential. With extended identity it carries the viewer's full Domino scope and can do anything the viewer can, for as long as the viewer's consent lasts (8 hours by default, up to 30 days). App stdout and stderr are kept indefinitely and shipped in support bundles, so a token written to a log outlives the session and reaches people who were never meant to hold it.

## Bad Example

```python
import logging

from flask import Flask, request

app = Flask(__name__)
log = logging.getLogger(__name__)
TOKENS: dict[str, str] = {}


@app.before_request
def trace() -> None:
    log.info("headers: %s", dict(request.headers))  # writes the bearer token to the log
    TOKENS[request.headers.get("domino-username", "")] = request.headers.get("Authorization", "")
```

## Good Example

```python
import logging
import re
from typing import Protocol

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")


class DominoClient(Protocol):
    def list_projects(self) -> list[str]: ...


class DominoClientFactory(Protocol):
    def for_token(self, token: str) -> DominoClient: ...


class RedactAuthorization(logging.Filter):
    """Masks a bearer token that reaches a log record, in the message or its arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()  # the text after %-formatting with record.args
        redacted = _BEARER.sub("Bearer [redacted]", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def projects_for_viewer(factory: DominoClientFactory, authorization: str) -> list[str]:
    # The token lives for this call only; nothing keeps a reference to it.
    client = factory.for_token(authorization.removeprefix("Bearer "))
    return client.list_projects()
```

The factory is injected from the composition root; the filter is attached once where logging is configured, and it catches the Bad Example's `dict(request.headers)` argument too. It is a safety net: the fix is never to log headers.

## Notes

- Never store a token, forward it to a host outside Domino, or put it in a URL or query string.
- Extended identity is enabled by an admin, needs each viewer's consent, is audited and cannot be turned off for an App once on; request it only when the App must act as the viewer, and record why in the repo (`domino-app-sharing-mode`).
- Other secrets follow `domino-secrets-in-env-vars` (domino-jobs skill).
- Logging setup is `domino-app-logging`.

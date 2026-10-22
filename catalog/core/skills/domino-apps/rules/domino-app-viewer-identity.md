---
id: domino-app-viewer-identity
name: Viewer identity
description: "Read the viewer from the domino-username header in one pure function that treats a missing or Anonymous value as no viewer."
version: 1
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
priority: 25
tags: [python, domino, apps, security]
---

# Viewer identity

## Description

Domino passes the viewer's identity to an App at three levels: a basic header, an enhanced signed token, and an extended token with the viewer's full scope. The basic signal is the `domino-username` header the proxy adds to every request; it holds `Anonymous` when nobody is signed in, and anonymous viewers are possible where an admin allows them. Only frameworks that pass the proxied request headers through see it.

Parse the header in one pure function at the edge, so every view gets a typed viewer or an explicit "nobody".

## Bad Example

```python
from flask import request


def save_preferences(prefs: str) -> None:
    user = request.headers["domino-username"]  # KeyError locally; "Anonymous" shared by all
    write_prefs(user, prefs)
```

## Good Example

```python
from collections.abc import Mapping
from dataclasses import dataclass

ANONYMOUS = "Anonymous"


@dataclass(frozen=True)
class Viewer:
    username: str


def viewer_from_headers(headers: Mapping[str, str]) -> Viewer | None:
    """The signed-in viewer, or ``None`` for a missing, empty or anonymous header."""
    username = headers.get("domino-username", "").strip()
    if not username or username == ANONYMOUS:
        return None
    return Viewer(username=username)
```

Being pure, it is tested without a server, in the App's test file:

```python
def test_anonymous_is_no_viewer() -> None:
    assert viewer_from_headers({"domino-username": "Anonymous"}) is None
```

Call it from the framework edge: `request.headers` in Flask and Dash, `st.context.headers` in Streamlit, the session's HTTP connection headers in Shiny for Python.

## Notes

- The header is enough for personal defaults and display; a decision that guards data uses the verified token (`domino-app-verify-viewer-jwt`).
- The Shiny Server Pro caveat in the docs is about R Shiny; the 6.2 docs do not cover Shiny for Python, so check that the header arrives on a published App (`domino-app-shiny`).
- Framework header APIs vary by version; confirm the attribute in the version the environment pins.

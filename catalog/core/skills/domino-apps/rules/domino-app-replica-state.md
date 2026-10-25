---
id: domino-app-replica-state
name: Domino App replica state
description: "Keep per-viewer state in the client or an external store keyed by the verified viewer, never in the memory of one App process."
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
applies_if:
  domino_project: true
section: state
priority: 32
tags: [python, domino, apps]
---

# Domino App replica state

An App can autoscale to several pods, and a production server runs several worker processes in each pod. Each process has its own memory, so state saved in one is invisible to the viewer's next request when it lands on another worker or replica: carts empty, wizards restart and filters reset at random.

## Bad Example

```python
from flask import Flask, request

app = Flask(__name__)
CARTS: dict[str, list[str]] = {}  # one copy per gunicorn worker and per replica


@app.post("/cart")
def add_to_cart() -> dict[str, int]:
    user = request.headers.get("domino-username", "")
    CARTS.setdefault(user, []).append(request.form["item"])
    return {"items": len(CARTS[user])}
```

## Good Example

Small state travels with the client; larger state lives in an external store keyed by the verified viewer.

```python
from dash import Dash, Input, Output, dcc, html

layout = html.Div([dcc.Store(id="filters", storage_type="session"), html.Div(id="table")])


def register(app: Dash) -> None:
    @app.callback(Output("table", "children"), Input("filters", "data"))
    def render_table(filters: dict[str, str] | None) -> str:
        return describe(filters or {})


def describe(filters: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(filters.items()))
```

```python
from typing import Protocol


class CartStore(Protocol):
    def items(self, viewer_id: str) -> list[str]: ...

    def add(self, viewer_id: str, item: str) -> None: ...
```

A Flask App keeps a small value per viewer in its signed session cookie:

```python
from flask import Flask, session


def create_app(session_key: str) -> Flask:
    """``session_key`` comes from settings (a Domino secret), never a literal."""
    app = Flask(__name__)
    app.secret_key = session_key
    return app


def remember_page(page: int) -> None:
    session["page"] = page  # a signed cookie: every worker and replica reads it
```

## Notes

- Process memory is only for caches that any process can rebuild (a loaded model, a lookup table).
- The 6.2 docs advise session affinity for R Shiny's stateful sessions and advise leaving it off for Streamlit, Flask and Dash, where it slows scale-down. Affinity needs the secure identity flag and does not survive a reconnect to another pod or a scale-down, so whatever the setting, persist what a viewer cannot lose; Streamlit's `st.session_state` included.
- Shiny for Python: `domino-app-shiny`. Workers and the production server: `domino-app-production-server`.
- Module-level mutable state also breaks `python-no-global-singletons` (python-coding).

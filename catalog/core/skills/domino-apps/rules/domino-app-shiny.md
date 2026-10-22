---
id: domino-app-shiny
name: Shiny for Python on Domino
description: "Run a Shiny for Python App with shiny run on 0.0.0.0:8888 without reload, and turn on session affinity because each session lives in one process."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/app.py"
applies_if:
  domino_project: true
  has_dependency: ["shiny"]
section: frameworks
priority: 43
tags: [python, domino, apps, shiny]
---

# Shiny for Python on Domino

Shiny for Python serves each session over a websocket from one process, and its CLI binds the loopback interface on port 8000 by default. A published App must serve `0.0.0.0:8888`, and a session's state exists only in the process that opened it. The Domino 6.2 pages show Shiny for R only, so the Python-specific points here are the engine's inference from them.

## Bad Example

```bash
shiny run app.py             # 127.0.0.1:8000: the proxy cannot reach it
shiny run --reload app.py    # a file watcher in production, restarting live sessions
```

## Good Example

```bash
#!/usr/bin/env bash
set -euo pipefail
exec shiny run --host 0.0.0.0 --port 8888 app:app
```

```python
from shiny import App, Inputs, Outputs, Session, render, ui

app_ui = ui.page_fluid(
    ui.input_slider("n", "Rows", min=1, max=100, value=10),
    ui.output_text("summary"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:  # noqa: A002
    @render.text
    def summary() -> str:
        return f"{input.n()} rows"


app = App(app_ui, server)
```

## Notes

- Turn on session affinity for the App (it needs the secure identity flag), because a session lives in one process; persist anything a viewer cannot lose anyway (`domino-app-replica-state`, `domino-app-external-persistence`).
- CPU-heavy reactive work blocks every other session in that process. Prefer small pods with a higher maximum pod count, and move long work out of the request (`domino-app-proxy-limits`).
- The docs' Server Pro caveat about identity headers concerns R Shiny. Read viewer headers from the session's HTTP connection and check that they arrive on a published App (`domino-app-viewer-identity`).

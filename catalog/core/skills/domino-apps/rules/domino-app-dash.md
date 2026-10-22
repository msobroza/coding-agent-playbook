---
id: domino-app-dash
name: Dash on Domino
description: "Give a Dash App both URL prefixes, serving routes at the root and requesting them under DOMINO_RUN_HOST_PATH, and expose its Flask server for gunicorn."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/callbacks.py"
  - "**/layout.py"
  - "**/app.sh"
applies_if:
  domino_project: true
  has_dependency: ["dash"]
section: frameworks
priority: 40
tags: [python, domino, apps, dash]
---

# Dash on Domino

The proxy strips the App's prefix before a request reaches Dash, so Dash serves its routes at the root. The browser, though, must ask for every route, asset and callback under the prefix. Dash therefore needs two settings: `routes_pathname_prefix="/"` for the server side and `requests_pathname_prefix` set to the App's prefix for the browser side. With only one, the page loads blank or its callbacks fail with 404.

## Bad Example

```python
from dash import Dash, html

app = Dash(__name__)  # no prefixes: the browser requests /_dash-layout outside the App
app.layout = html.Div("Sales")

if __name__ == "__main__":
    app.run()  # built-in server, default host and port
```

```bash
python app.py
```

## Good Example

```python
import os

from dash import Dash, html


def app_prefix() -> str:
    raw = os.environ.get("DOMINO_RUN_HOST_PATH", "/")
    return "/" + raw.strip("/") + "/" if raw.strip("/") else "/"


def create_dash_app(prefix: str) -> Dash:
    app = Dash(
        __name__,
        routes_pathname_prefix="/",
        requests_pathname_prefix=prefix,
    )
    app.layout = html.Div([html.Img(src=app.get_asset_url("logo.png")), html.Div("Sales")])
    return app


app = create_dash_app(app_prefix())
server = app.server  # the Flask instance gunicorn serves
```

```bash
#!/usr/bin/env bash
set -euo pipefail
exec gunicorn --bind 0.0.0.0:8888 --workers "${APP_WORKERS:-2}" app:server
```

## Notes

- The prefix comes from `DOMINO_RUN_HOST_PATH`, read once at startup (`domino-app-url-prefix`); never build it from the owner, project and run id.
- Link assets with `app.get_asset_url(...)` and pages with `app.get_relative_path(...)`, never with an absolute `/...` path (`domino-app-relative-urls`).
- Serve with gunicorn and debug off (`domino-app-production-server`); the built-in server is single-threaded.
- Callbacks read the viewer through Flask's `request.headers` (`domino-app-viewer-identity`).
- Pin the Dash version in the compute environment (domino-pinned-environments, domino-jobs).

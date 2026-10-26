---
id: domino-app-bind-host-port
name: Bind host and port
description: "Serve the App on 0.0.0.0, port 8888, set explicitly, never on a framework's default host or port."
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
  - "**/app.py"
  - "**/run.py"
applies_if:
  domino_project: true
section: launch
priority: 20
tags: [python, domino, apps]
---

# Bind host and port

## Description

Domino's proxy forwards a viewer's requests to one place only: TCP port 8888 on an interface other than loopback. The launch file must start a process listening there; Domino watches that process and keeps the App in its starting state until the port answers. A server that binds `127.0.0.1`, or keeps its framework's default port (Flask 5000, Dash 8050, Streamlit 8501, Shiny 8000), never becomes reachable, and the App stays stuck starting with no error in the code.

Set both values explicitly on the launch script's server line, and where Python code also starts a server, take them from one constant pair rather than literals scattered across modules.

## Bad Example

```bash
#!/usr/bin/env bash
# Relies on framework defaults: loopback and the framework's own port.
python app.py
```

```python
from flask import Flask

app = Flask(__name__)

if __name__ == "__main__":
    app.run()  # 127.0.0.1:5000, unreachable through the proxy
```

## Good Example

```bash
#!/usr/bin/env bash
set -euo pipefail
exec gunicorn --bind 0.0.0.0:8888 "myapp.serve:create_app()"
```

```python
from typing import Final

from flask import Flask

#: Where Domino's proxy forwards App traffic; the only valid pair for a published App.
HOST: Final = "0.0.0.0"
PORT: Final = 8888


def create_app() -> Flask:
    return Flask(__name__)


if __name__ == "__main__":
    # A local check only; the published App runs the gunicorn line above.
    create_app().run(host=HOST, port=PORT)
```

## Notes

- `0.0.0.0`, `::` and an empty host string all mean every interface and are fine; only a loopback host is wrong.
- A workspace preview runs on another port and URL; keep it out of the published launch script (`domino-app-workspace-preview`).
- Each framework's own launch line is in `domino-app-dash`, `domino-app-flask`, `domino-app-streamlit` and `domino-app-shiny`; a production server replaces the development `run()` (`domino-app-production-server`).
- Agent APIs hosted on Domino follow the same contract (domino-agents skill).
- A start that never completes: see app-troubleshooting.md.

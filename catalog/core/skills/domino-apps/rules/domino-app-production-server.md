---
id: domino-app-production-server
name: Production server
description: "Serve a Flask or Dash App with gunicorn workers on 0.0.0.0:8888, never the built-in server, and never in debug mode."
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
  - "**/wsgi.py"
  - "**/gunicorn.conf.py"
applies_if:
  domino_project: true
  any_dependency: [flask, dash]
section: serving
priority: 45
tags: [python, domino, apps, gunicorn]
---

# Production server

## Description

The server built into Flask and Dash is a development tool: it handles one request at a time in one process and is not meant for more than about ten concurrent viewers or for use outside a workstation. A published App can have a whole team on it, so one slow callback makes every other viewer wait. Debug mode makes it worse: besides reloading code, it can serve an interactive debugger to anyone who triggers an error (the engine's inference, the platform documentation does not say so), so a published App never runs with it.

Serve the App with gunicorn and several workers, bound to `0.0.0.0:8888`, pointing at the WSGI object.

## Bad Example

```bash
#!/usr/bin/env bash
python app.py
```

```python
from flask import Flask

app = Flask(__name__)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)  # one thread, one process
```

## Good Example

```bash
#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
WORKERS="${APP_WORKERS:-4}"
TIMEOUT="${APP_WORKER_TIMEOUT:-120}"

# Flask: module:app. Dash: module:server, the Flask app behind `server = app.server`.
exec gunicorn --bind 0.0.0.0:8888 --workers "${WORKERS}" --timeout "${TIMEOUT}" \
    myapp.wsgi:app
```

```python
# myapp/wsgi.py: the object gunicorn imports; nothing here starts a server.
from myapp.factory import create_app
from myapp.settings import load_settings

app = create_app(load_settings())
```

The worker count and worker timeout come from environment variables, so a larger hardware tier needs no code change.

## Notes

- Workers are separate processes that share no memory; per-viewer state follows `domino-app-replica-state`.
- Keep gunicorn's worker timeout below the proxy's read timeout (300 s by default), so a stuck worker is restarted before the viewer gets a proxy error (`domino-app-proxy-limits`).
- gunicorn must be installed in the compute environment: propose adding it, never add it unasked (domino-pinned-environments, domino-jobs skill).
- The launch script itself follows `domino-app-launch-script`; the Dash and Flask wiring is in `domino-app-dash` and `domino-app-flask`.

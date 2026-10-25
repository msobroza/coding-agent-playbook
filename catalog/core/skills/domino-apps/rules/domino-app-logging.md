---
id: domino-app-logging
name: App logging
description: "Log from an App to unbuffered stdout with the pod name on each line; never to a file in the project."
scope: scoped
globs:
  - "**/app.py"
  - "**/logging_config.py"
  - "**/app.sh"
applies_if:
  domino_project: true
section: publishing
priority: 64
tags: [python, domino, apps, logging]
---

# App logging

## Description

An App never syncs a file back to the project, so a log file written under the project directory vanishes with the container at the next stop, restart or scale event. What the App writes to stdout and stderr is kept: it is captured with the execution logs, included in the support bundle and retained indefinitely. When the App runs several replicas, the output of every pod is interleaved into one log, so a line that does not say which pod wrote it cannot be traced.

This rule holds only what differs for Apps; the shared practice (one line per event, no secrets, logs kept forever) is domino-job-logging (domino-jobs skill).

## Bad Example

```python
import logging

logging.basicConfig(
    filename="logs/app.log",  # inside the project: lost when the container goes
    level=logging.INFO,
)
```

## Good Example

```python
# myapp/logging_config.py, called once from the entry point.
import logging
import os
import sys


def configure_logging(level: str = "INFO") -> None:
    pod = os.environ.get("HOSTNAME", "local")  # the pod name in Kubernetes
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(f"%(asctime)s {pod} %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
```

```bash
# app.sh
export PYTHONUNBUFFERED=1
exec gunicorn --bind 0.0.0.0:8888 --workers 4 myapp.wsgi:app
```

`PYTHONUNBUFFERED=1` is exported in the launch script because a server started from `app.sh` is not guaranteed the unbuffered mode Jobs get, and buffered lines are lost when a pod is stopped. That `HOSTNAME` holds the pod name is the engine's inference from how the platform runs pods.

## Notes

- Never log request headers or tokens (`domino-app-viewer-token`).
- Audit records that must last and be queried go to a Dataset or a database (`domino-app-external-persistence`), not only to the log.
- Configure logging once, in the entry point; library modules only call `logging.getLogger(__name__)`.

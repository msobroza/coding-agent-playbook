---
id: domino-app-proxy-limits
name: Proxy limits
description: "Finish each request well inside the proxy's timeout and body-size limits; start a Job for long work and pass large inputs by reference."
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
applies_if:
  domino_project: true
section: serving
priority: 46
tags: [python, domino, apps]
---

# Proxy limits

## Description

Every request to an App passes through the run pod's proxy. When a deployment sets nothing, that proxy waits 300 s to connect and 300 s for a response; a handler that runs longer is cut off and the viewer sees an error while the work goes on unseen. The same proxy family caps request bodies at 25 MiB by default and answers larger ones with 413. The documentation describes the body cap for workspace uploads; that it applies to Apps too is the engine's inference, so treat 25 MiB as the safe ceiling. Admins can change all of these values.

## Bad Example

```python
from dash import Input, Output, callback

from myapp.training import train_model


@callback(Output("status", "children"), Input("train", "n_clicks"), prevent_initial_call=True)
def train(_clicks: int) -> str:
    model = train_model(epochs=200)  # twenty minutes inside one request
    return f"done: {model.score:.3f}"
```

An upload widget that accepts multi-gigabyte files fails the same way, with a 413 before any App code runs.

## Good Example

```python
from typing import Protocol

from dash import Input, Output, State, callback


class JobLauncher(Protocol):
    def start(self, command: str) -> str: ...
    def status(self, job_id: str) -> str: ...


def register_callbacks(jobs: JobLauncher) -> None:
    @callback(Output("job-id", "data"), Input("train", "n_clicks"), prevent_initial_call=True)
    def start_training(_clicks: int) -> str:
        return jobs.start("python -m myapp.train --epochs 200")  # returns at once

    @callback(
        Output("status", "children"),
        Input("poll", "n_intervals"),
        State("job-id", "data"),
    )
    def show_status(_n: int, job_id: str | None) -> str:
        return "idle" if job_id is None else jobs.status(job_id)
```

The page starts a Domino Job, keeps its id in the browser and polls its status with a `dcc.Interval`; the launcher is injected from the composition root and faked in tests. Large inputs go to a Dataset or an object store first, and the App receives only their path or key.

## Notes

- Starting Jobs from code is domino-launch-jobs-from-code (domino-jobs skill); the Job runs with the starter's identity unless the viewer's token is used (`domino-app-viewer-token`).
- A deployment may set other limits, so code reads none of them as constants; keep every request far below them instead.
- Keep a framework's own upload cap (Streamlit's `server.maxUploadSize`) at or below 25 MiB.
- Inputs too big for one request go through a Dataset (domino-datasets-for-large-data, domino-jobs skill).
- gunicorn's worker timeout stays below the proxy's (`domino-app-production-server`).
- A 504 or 413 seen by viewers: see app-troubleshooting.md.

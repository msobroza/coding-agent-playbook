---
id: domino-mlflow-tracking
name: Domino MLflow tracking
description: "Name MLflow experiments after the owner and project, tag each run with DOMINO_RUN_ID and close it in a with block; never set the tracking URI."
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: reproducibility
priority: 65
tags: [python, domino, jobs, mlflow]
---

# Domino MLflow tracking

Domino's experiment manager is an MLflow tracking server that Domino points every run at: `MLFLOW_TRACKING_URI` is a reserved name, set for you. Experiments are created only from code, with `mlflow.set_experiment` (the UI cannot create them), and appear after their first logged run. Experiment names are unique across the whole deployment, so build them from the project owner and name (or the team), never a bare word. Each run gets a name and a tag holding `DOMINO_RUN_ID`, and the work sits inside `with mlflow.start_run(...)` so the run is closed even when the job fails.

## Bad Example

```python
import os

import mlflow


def train(params: dict[str, float]) -> None:
    os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"  # Domino set it
    mlflow.set_experiment("churn")  # collides with every other project's "churn"
    mlflow.start_run()  # left open when fit() raises
    mlflow.log_params(params)
    mlflow.log_metric("auc", fit(params))
```

## Good Example

```python
from collections.abc import Mapping

import mlflow

from jobs.context import JobContext  # the frozen record of domino-paths-from-env


def experiment_name(ctx: JobContext, purpose: str) -> str:
    """Unique across the deployment: owner, project and purpose."""
    return "-".join((ctx.project_owner, ctx.project_name, purpose))


def train(ctx: JobContext, params: Mapping[str, float]) -> float:
    mlflow.set_experiment(experiment_name(ctx, "churn-model"))
    with mlflow.start_run(
        run_name=f"train-{ctx.run_number}",
        tags={"domino_run_id": ctx.run_id},
    ):
        mlflow.log_params(dict(params))
        auc = fit(params)
        mlflow.log_metric("auc", auc)
    return auc
```

A test points MLflow at a temporary local store, never at the deployment:

```python
from collections.abc import Iterator
from pathlib import Path

import mlflow
import pytest


@pytest.fixture(autouse=True)
def local_tracking(tmp_path: Path) -> Iterator[None]:
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(tmp_path.as_uri())
    yield
    mlflow.set_tracking_uri(previous)


def test_train_logs_auc() -> None:
    ctx = make_context(owner="alice", project="churn")  # a JobContext built from a dict
    auc = train(ctx, {"max_depth": 3.0})
    names = [experiment_name(ctx, "churn-model")]
    run = mlflow.search_runs(experiment_names=names).iloc[0]
    assert run["metrics.auc"] == pytest.approx(auc)
```

## Notes

- Child runs are not deleted with their parent: give them names and close them in their own `with` block too.
- Autolog covers the libraries it supports; log by hand what the job reports elsewhere (`dominostats.json`, the run manifest of `domino-run-manifest`) so the numbers agree.
- Jobs give better reproducibility than workspaces: log the runs whose numbers are reported from jobs.
- Large artifact uploads can use the multipart upload option the 6.2 docs describe for AWS and GCP deployments.
- Never assign `MLFLOW_TRACKING_URI` in code or as a project variable (`domino-env-var-names`); only tests override it.
- Agent tracing with MLflow belongs to the domino-agents skill.

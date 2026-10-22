---
id: domino-project-types
name: Project types
description: "Write every output a run must keep to the location its project type syncs back: the working directory in DFS projects, the artifacts directory in Git-based ones."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
  - ".dominoignore"
  - ".dominoresults"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 20
tags: [python, domino, jobs]
---

# Project types

## Description

A run starts in a fresh container. When it ends, whether it succeeded, failed or was stopped, Domino copies back only what the project type tracks:

- In a DFS project, every new or changed file under the working directory, except the files `.dominoignore` matches.
- In a Git-based project, only the artifacts directory (`/mnt/artifacts`). Edits under the code checkout (`/mnt/code`) are neither committed nor pushed by a job, by design.
- Datasets are network mounts, written in place.

Everything else is lost with the container: `/tmp`, the home directory, and in a Git-based project every file written beside the code. Code tells the two types apart with `DOMINO_IS_GIT_BASED`, a string to compare with `"true"`.

## Bad Example

```python
import json
from pathlib import Path

import pandas as pd


def save_outputs(scores: pd.DataFrame, summary: dict[str, float]) -> None:
    # Relative to the code checkout: in a Git-based project the job shows
    # Succeeded and none of these files survive the container.
    out = Path("results")
    out.mkdir(exist_ok=True)
    scores.to_csv(out / "scores.csv", index=False, encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
```

## Good Example

```python
import json
from pathlib import Path

import pandas as pd

from jobs.context import JobContext  # the record of domino-paths-from-env


def output_root(ctx: JobContext) -> Path:
    """The results directory this project type syncs back after the run."""
    base = ctx.artifacts_dir if ctx.is_git_based else ctx.working_dir
    return base / "results"


def save_outputs(ctx: JobContext, scores: pd.DataFrame, summary: dict[str, float]) -> None:
    out = output_root(ctx)
    out.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out / "scores.csv", index=False, encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
```

## Notes

- Files are captured on failure and on Stop too, so write complete files (`domino-run-scoped-writes`) and exit non-zero on failure (`domino-job-exit-codes`). An Error state means the platform failed: do not count on its outputs.
- In a Git-based project, results under `artifacts/results` also appear in the results view and the success email.
- The file store keeps every version, so a secret written to a synced path stays there (`domino-secrets-in-env-vars`).
- Flow tasks persist only `/workflow/outputs` (`domino-flow-task-io`); big or many files belong in Datasets (`domino-datasets-for-large-data`).
- Domino Apps and endpoints persist nothing; the domino-apps skill covers App storage.
- The 6.2 artifacts page suggests replacing `/mnt` with `DOMINO_WORKING_DIR`, which points at the code checkout in Git-based projects. Always resolve artifacts from `DOMINO_ARTIFACTS_DIR` instead (safe behavior where the docs disagree).
- where-outputs-go.md in this skill maps each kind of file to its location per project type.

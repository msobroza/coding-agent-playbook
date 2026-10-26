---
id: domino-flow-task-purity
name: Pure Flow tasks
description: "A Flow task maps versioned inputs to its declared outputs and touches no shared state, so retries, timeouts and the cache stay safe; bump cache_version when its logic changes."
scope: scoped
globs:
  - "**/flows/**/*.py"
  - "**/workflow*.py"
  - "**/*.py"
applies_if:
  domino_project: true
section: flow-tasks
priority: 49
tags: [python, domino, jobs, flows]
---

# Keep Flow tasks free of side effects

## Description

Flows promise lineage and reproducibility by treating each task as a function from versioned inputs to declared outputs. A task sees only dataset snapshots, mounted read-only, and it may be retried, cut off by a timeout or served from the cache instead of running. A task that writes a read-write dataset, a database table or any other shared state breaks that contract: its effect is invisible to lineage and repeats with every retry. Effects on the outside world belong in a standalone job that reads the Flow's output after the Flow succeeds.

## Bad Example

```python
features = DominoJobTask(
    name="build-features",
    domino_job_config=DominoJobConfig(Command="python -m jobs.features"),
    inputs={"day": str},
    outputs={"rows": int},
    cache=True,
    cache_version="1",  # the task body changed last week; cached results are stale
)
# jobs/features.py appends to a warehouse table and writes into a read-write dataset
```

## Good Example

```python
from datetime import timedelta

features = DominoJobTask(
    name="build-features",
    domino_job_config=DominoJobConfig(
        Command="python -m jobs.features",
        EnvironmentId=FEATURES_ENVIRONMENT_ID,
        EnvironmentRevisionSpec=FEATURES_ENVIRONMENT_REVISION_ID,
        HardwareTierId=MEDIUM_TIER_ID,
        DatasetSnapshots=[DatasetSnapshot(Id=SALES_DATASET_ID, Version=12)],
    ),
    inputs={"day": str},
    outputs={"features": FlyteFile},
    retries=2,
    timeout=timedelta(hours=1),
    cache=True,
    cache_version="2024-06-feature-v3",  # bumped whenever jobs/features.py changes
    use_latest=False,  # with the pinned IDs above, never the latest environment or tier
)
```

`jobs/features.py` reads the snapshot and its `day` input and writes only `/workflow/outputs/features`. A separate job, started after the Flow succeeds, loads that output into the warehouse with an upsert (domino-idempotent-jobs).

## Notes

- Bump `cache_version` whenever the logic changes but the signature does not; otherwise the cache returns results of the old code.
- Stopping one task's job stops the whole Flow, and completed Flow jobs can be re-run only from the Flows UI.
- A Flow is a poor fit for many tiny computations over one dataset; batch them inside one task.
- Version 0 of a dataset is never a Flow input, and only one snapshot per dataset can be mounted (domino-dataset-snapshots).
- `use_latest=False` with explicit environment, revision and hardware tier IDs is domino-environment-revisions.
- Flows are Domino's Flyte integration as documented for 6.2; check the plugin's release notes when the deployment is upgraded.
- Inputs and outputs inside the task are domino-flow-task-io.

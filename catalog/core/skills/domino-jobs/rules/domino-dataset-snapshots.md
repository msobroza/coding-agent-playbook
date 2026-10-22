---
id: domino-dataset-snapshots
name: Domino dataset snapshots
description: "Read a numbered dataset snapshot, not the changing read-write root, when results must be reproducible, and record which snapshot the run used."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: datasets
priority: 42
tags: [python, domino, jobs]
---

# Domino dataset snapshots

A dataset's read-write root changes under a run as other jobs and people write to it. A snapshot is an immutable, numbered copy, optionally tagged, mounted read-only. A job whose results must be reproducible reads a snapshot and records the dataset name and snapshot number.

Where a snapshot is mounted:

- DFS project, local dataset: `/domino/datasets/local/snapshots/<name>/<number>`; shared dataset: `/domino/datasets/snapshots/<name>/<number>`.
- Git-based project, local dataset: `/mnt/data/snapshots/<name>/<number>`; imported dataset: `/mnt/imported/data/snapshots/<name>/<number>`.
- Flow task: the chosen snapshot appears at the plain dataset path, with no `snapshots` segment.

## Bad Example

```python
import pandas as pd


def train() -> Model:
    # The extract job rewrites this root while training reads it.
    orders = pd.read_parquet("/domino/datasets/local/sales/orders.parquet")
    return fit(orders)


def flow_task() -> None:
    # A Flow mounts the snapshot at the plain path; this path does not exist there.
    pd.read_parquet("/mnt/data/snapshots/sales/12/orders.parquet")
```

## Good Example

```python
from pathlib import Path

import pandas as pd


def snapshot_dir(ctx: JobContext, dataset: str, number: int) -> Path:
    if ctx.is_flow_task:
        return ctx.datasets_dir / dataset  # the Flow mounts the chosen snapshot here
    return ctx.datasets_dir / "snapshots" / dataset / str(number)


def train(ctx: JobContext, *, snapshot: int) -> Model:
    orders = pd.read_parquet(snapshot_dir(ctx, "sales", snapshot) / "orders.parquet")
    manifest_snapshots = {"sales": snapshot}  # written to the run manifest
    return fit(orders, snapshots=manifest_snapshots)
```

`ctx.datasets_dir` is resolved once from `DOMINO_DATASETS_DIR`, or `DOMINO_IMPORTED_DATA_DIR` for shared and imported datasets (`domino-paths-from-env`). The 6.2 documentation gives no values per project type for these variables, so log the resolved path on the first run on a deployment and check it. The snapshot number goes into the run manifest (`domino-run-manifest`).

## Notes

- Prefer the snapshot number to a tag: a tag can be moved to a newer snapshot, and a snapshot with several tags is mounted only under the most recently added one.
- Taking a snapshot copies the data and takes longer as the dataset grows; nothing may modify the files while it runs.
- A job can snapshot its datasets when it completes, where the administrator setting `AllowDatasetSnapshotsOnExecutionCompletion` is on.
- Read-write versus read-only follows the dataset role of the user running the job.
- Flows refuse version 0 (the read-write root) and mount one snapshot per dataset (`domino-flow-task-purity`).
- These paths come from the 6.2 dataset pages; the Git-based structure page's `/mnt/local` spelling is a slip in that page, which is why code reads the variable (`domino-paths-from-env`).

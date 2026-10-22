---
id: domino-datasets-for-large-data
name: Domino Datasets for large data
description: "Keep big or numerous data files in Domino Datasets, which are mounted, never in project files, which every run copies in and out."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - ".dominoignore"
applies_if:
  domino_project: true
section: datasets
priority: 40
tags: [python, domino, jobs]
---

# Domino Datasets for large data

Project files (the DFS project or the Git checkout, plus artifacts and imported projects) are copied into every run when it starts and back when it ends. Datasets are network mounts with no file-count or file-size limit, and nothing is copied. The default limits make project files the wrong place for data: 10,000 files per project, 8 GB per transferred file, a sync not designed for more than about 10 GB or 100,000 files, and a 15-minute default timeout on copying project files into a run. Spark, Ray, Dask and MPI workers cannot see project files at all.

## Bad Example

```python
from pathlib import Path

import pandas as pd

ARTIFACTS = Path("/mnt/artifacts")


def build_features(orders: pd.DataFrame) -> None:
    for day, frame in orders.groupby("day"):  # 50,000 small files synced after the run
        frame.to_parquet(ARTIFACTS / "features" / f"{day}.parquet")


def load_training_data() -> pd.DataFrame:
    return pd.read_csv("data/orders_2019_2024.csv")  # gigabytes committed to the repo
```

## Good Example

```python
from pathlib import Path

import pandas as pd


def build_features(ctx: JobContext) -> Path:
    orders = pd.read_parquet(ctx.datasets_dir / "sales" / "orders")  # mounted, not copied
    out_dir = run_dir(ctx.datasets_dir / "features", ctx.run_id)
    features = compute_features(orders)
    features.to_parquet(out_dir / "features.parquet", partition_cols=["day"])
    summary = output_root(ctx) / "features_summary.json"  # small, synced as a result
    summary.write_text(features.describe().to_json(), encoding="utf-8")
    return out_dir
```

`JobContext` resolves the roots from the environment (`domino-paths-from-env`), `output_root` picks the synced location of the project type (`domino-project-types`), and `run_dir` keys the output by run (`domino-run-scoped-writes`).

## Notes

- Git LFS is not supported in Domino projects.
- A `.noLock` file in the project avoids "too many open files" during sync, but nothing may change files while a sync runs.
- The CLI's project upload may time out above about 1,000 files at once; put data into a dataset with the dataset upload command instead. It overwrites existing files unless `--fileUploadSetting` says otherwise, and that option's values are case-sensitive.
- A dataset is mounted read-write or read-only by the dataset role of the user running the job.
- In a deployment with several data planes, the mounts a run sees depend on its hardware tier's data plane.
- Reads whose results must be reproducible use snapshots (`domino-dataset-snapshots`).
- where-outputs-go.md in this skill lists the limits next to each location.

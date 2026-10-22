---
id: domino-job-stats-file
name: Job stats file
description: "Write dominostats.json on every run as one flat object of metric name to finite number, with the same keys each time."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "dominostats.json"
applies_if:
  domino_project: true
section: results-and-metrics
priority: 62
tags: [python, domino, jobs, metrics]
---

# Write dominostats.json as flat, finite metrics

## Description

Domino deletes `dominostats.json` before each execution. When a run writes it, its keys become columns on the Jobs dashboard and lines on the jobs timeline, which makes it the quickest way to compare runs at a glance. A job that reports headline metrics writes one flat JSON object, metric name to finite number, at the end of every run, with the same keys each time; a run that skips the file shows empty cells, and a changed key starts a new column.

## Bad Example

```python
import json

if first_run:
    stats = {"metrics": {"auc": "0.91"}, "loss": float("nan")}  # nested, a string, NaN
    with open("dominostats.json", "w", encoding="utf-8") as handle:
        json.dump(stats, handle)  # writes NaN, which is not JSON
```

## Good Example

```python
import json
import math
from collections.abc import Mapping
from pathlib import Path


def write_stats(path: Path, stats: Mapping[str, float]) -> None:
    """Write the run's headline metrics for the Jobs dashboard."""
    for key, value in stats.items():
        if not math.isfinite(value):
            raise ValueError(f"metric {key!r} is {value!r}; dominostats.json needs finite numbers")
    text = json.dumps(dict(stats), allow_nan=False, sort_keys=True)
    write_text_atomically(path, text + "\n")  # see domino-run-scoped-writes


write_stats(output_root / "dominostats.json", {"auc": auc, "rows_scored": float(rows)})
```

`write_text_atomically` writes with `encoding="utf-8"` to a temporary file and renames it into place.

## Notes

- The file name is `dominostats.json`; one 6.2 page calls it `domino.json`, which is wrong.
- In DFS projects the file goes at the working directory root. For Git-based projects the docs do not say where, and the reproducibility page mentions artifacts, so write it at the artifacts root, check that the columns appear after the first run, and keep MLflow as the portable record (domino-mlflow-tracking).
- Tag related jobs to filter the timeline.
- When the same numbers are reported elsewhere, record them in the run manifest too (domino-run-manifest).

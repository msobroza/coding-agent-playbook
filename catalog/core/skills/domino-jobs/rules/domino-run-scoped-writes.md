---
id: domino-run-scoped-writes
name: Domino run-scoped writes
description: "Write each run's files under a run-keyed directory, through a temporary file renamed into place, with a completion marker last."
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: datasets
priority: 41
tags: [python, domino, jobs]
---

# Domino run-scoped writes

Several runs of one job can run at once against the same read-write datasets: a parameter sweep, two overlapping scheduled runs, a retry next to a slow first attempt. Domino does not serialize their writes (its documentation says so of shared storage; assume the same for runs, which it does not address), and a run that is stopped or killed mid-write still has its half-written files synced. Each run therefore writes under a directory keyed by `DOMINO_RUN_ID` or by its partition key, writes every file to a temporary name in the target directory and renames it into place with `os.replace`, and publishes a completion marker or a latest pointer last.

## Bad Example

```python
from pathlib import Path

SHARED = Path("/domino/datasets/local/models")


def save_sweep_scores(scores: bytes) -> None:
    (SHARED / "scores.parquet").write_bytes(scores)  # every sweep run overwrites it


def write_report(rows: list[str]) -> None:
    with open(SHARED / "report.csv", "w", encoding="utf-8") as report:
        for row in rows:  # a stop mid-loop syncs a truncated report
            report.write(row + "\n")
```

## Good Example

```python
import os
import tempfile
from pathlib import Path


def run_dir(root: Path, run_id: str) -> Path:
    path = root / f"run={run_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, path)  # readers see the old file or the new one, never half


def publish_scores(ctx: JobContext, scores: bytes, report: str) -> Path:
    out = run_dir(ctx.datasets_dir / "models" / "scores", ctx.run_id)
    atomic_write_bytes(out / "scores.parquet", scores)
    atomic_write_bytes(out / "report.csv", report.encode("utf-8"))
    atomic_write_bytes(out / "_SUCCESS", b"")  # last: consumers wait for it
    return out
```

## Notes

- `os.replace` is atomic only within one file system, so the temporary file lives in the target directory, never in `/tmp`.
- Do not rely on file locks across containers on network mounts; separate paths per run make locks unnecessary.
- Readers pick only directories that hold the completion marker, or follow a latest pointer that is itself written atomically.
- Prune old run directories with an explicit retention rule instead of overwriting them.
- The run's own results directory needs the same care, because stopping a run still syncs what is on disk.
- Running the same unit of work again is `domino-idempotent-jobs`; `JobContext` comes from `domino-paths-from-env`.

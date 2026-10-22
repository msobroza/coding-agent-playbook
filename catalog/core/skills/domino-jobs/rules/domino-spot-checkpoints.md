---
id: domino-spot-checkpoints
name: Spot checkpoints
description: "On spot hardware tiers, save checkpoints periodically under the artifacts directory, named by step and rank, and resume from the newest one at startup."
version: 1
scope: scoped
globs:
  - "**/train*.py"
  - "**/*.py"
applies_if:
  domino_project: true
section: scheduling-and-launching
priority: 46
tags: [python, domino, jobs, scheduling]
---

# Checkpoint long jobs on spot tiers

## Description

Spot hardware tiers cost less, but their nodes can be reclaimed, so a job may start late, run longer than planned or die mid-run. Domino syncs the artifacts directory to its store and mounts the checkpoints that already exist there into the next run of the job. A long training job therefore saves a checkpoint periodically under `<artifacts>/checkpoints/` and, at startup, resumes from the newest complete checkpoint instead of starting over.

## Bad Example

```python
def train(model: Model, batches: Iterable[Batch], out: Path, rank: int) -> None:
    for batch in batches:
        model.step(batch)
    # only at the end, and every rank writes the same file
    model.save(out / "checkpoints" / "latest.pt")
```

A reclaim after six hours loses six hours, and in distributed training the workers overwrite each other's file.

## Good Example

```python
import os
from pathlib import Path


def checkpoint_dir() -> Path:
    return Path(os.environ["DOMINO_ARTIFACTS_DIR"]) / "checkpoints"


def checkpoint_path(root: Path, step: int, rank: int) -> Path:
    return root / f"step-{step:09d}-rank-{rank}.ckpt"


def latest_checkpoint(root: Path, rank: int) -> Path | None:
    found = sorted(root.glob(f"step-*-rank-{rank}.ckpt"))
    return found[-1] if found else None


def save_checkpoint(trainer: Trainer, root: Path, step: int, rank: int, *, keep: int = 3) -> None:
    target = checkpoint_path(root, step, rank)
    partial = target.with_suffix(".partial")
    trainer.save(partial)  # the framework serializes the state
    partial.replace(target)  # a reader never sees half a checkpoint
    for old in sorted(root.glob(f"step-*-rank-{rank}.ckpt"))[:-keep]:
        old.unlink()


def resume(trainer: Trainer, root: Path, rank: int) -> int:
    """Restore the newest checkpoint and return the step to continue from."""
    newest = latest_checkpoint(root, rank)
    if newest is None:
        return 0
    trainer.load(newest)
    return int(newest.name.split("-")[1]) + 1
```

The training loop calls `resume` once at startup and `save_checkpoint` from the framework's checkpoint callback every N steps.

## Notes

- Resolve the directory from the injected variable; the docs name `/mnt/artifacts/checkpoints` (a Git-based path) and say nothing about DFS projects, so verify the DFS behavior on the deployment.
- Checkpoints added after a job started are not copied into it; only the next run sees them.
- Include the worker rank in every file name, and control the frequency with the framework's own checkpoint callbacks.
- Keep only the last few checkpoints: artifacts count toward sync limits (domino-datasets-for-large-data). Atomic writes are domino-run-scoped-writes.
- After a reclaim, retry after more than 30 minutes, and move to a non-spot tier if reclaims persist. The 6.2 page covers AWS spot capacity only.
- Where the repo uses torch or another stack ml-data covers, loading pickle-based checkpoints follows ml-serialization-security (ml-data).
- Re-execution in general is domino-idempotent-jobs.

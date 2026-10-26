---
id: domino-spot-checkpoints
name: Spot checkpoints
description: "On spot hardware tiers, save checkpoints periodically under the artifacts directory, named by step and rank, and resume from the newest one at startup."
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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def checkpoint_dir(env: Mapping[str, str]) -> Path:
    artifacts = env.get("DOMINO_ARTIFACTS_DIR")
    if not artifacts:
        raise RuntimeError("DOMINO_ARTIFACTS_DIR is unset; expected the run's artifacts directory")
    return Path(artifacts) / "checkpoints"


@dataclass(frozen=True)
class CheckpointStore:
    """One worker's checkpoints, named step-<step>-rank-<rank>.ckpt under root."""

    root: Path
    rank: int

    def path(self, step: int) -> Path:
        return self.root / f"step-{step:09d}-rank-{self.rank}.ckpt"

    def saved(self) -> list[Path]:
        """This rank's checkpoints, oldest first: the zero-padded step sorts by name."""
        return sorted(self.root.glob(f"step-*-rank-{self.rank}.ckpt"))

    @staticmethod
    def step_of(path: Path) -> int:
        return int(path.name.split("-")[1])

    def save(self, trainer: Trainer, step: int, *, keep: int = 3) -> None:
        target = self.path(step)
        partial = target.with_suffix(".partial")
        trainer.save(partial)  # the framework serializes the state
        partial.replace(target)  # a reader never sees half a checkpoint
        for old in self.saved()[:-keep]:
            old.unlink()

    def resume(self, trainer: Trainer) -> int:
        """Restore the newest checkpoint and return the step to continue from."""
        saved = self.saved()
        if not saved:
            return 0
        trainer.load(saved[-1])
        return self.step_of(saved[-1]) + 1
```

The training loop builds `CheckpointStore(checkpoint_dir(os.environ), rank)`, calls `resume` once at startup and `save` from the framework's checkpoint callback every N steps.

## Notes

- Resolve the directory from the injected variable; the docs name `/mnt/artifacts/checkpoints` (a Git-based path) and say nothing about DFS projects, so verify the DFS behavior on the deployment.
- Checkpoints added after a job started are not copied into it; only the next run sees them.
- Include the worker rank in every file name, and control the frequency with the framework's own checkpoint callbacks.
- Keep only the last few checkpoints: artifacts count toward sync limits (domino-datasets-for-large-data). Atomic writes are domino-run-scoped-writes.
- After a reclaim, retry after more than 30 minutes, and move to a non-spot tier if reclaims persist. The 6.2 page covers AWS spot capacity only.
- Where the repo uses torch or another stack ml-data covers, loading pickle-based checkpoints follows ml-serialization-security (ml-data).
- Re-execution in general is domino-idempotent-jobs.

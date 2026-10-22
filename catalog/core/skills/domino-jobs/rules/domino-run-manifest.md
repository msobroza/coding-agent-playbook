---
id: domino-run-manifest
name: Domino run manifest
description: "Write a manifest.json beside every reported result naming the run, commit, snapshots, environment, configuration, seed and library versions."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: reproducibility
priority: 64
tags: [python, domino, jobs, reproducibility]
---

# Domino run manifest

Domino records each run's code, environment revision, dataset snapshots and command, but a number pasted into a slide or a ticket points to a file, not to a run. Every job that produces reported results writes a small `manifest.json` beside them: the run ID and number, the project owner and name, the starting user, the Git commit, the dataset snapshots it read, the environment and hardware tier, the effective configuration, the random seed, the key library versions and the start and end times.

## Bad Example

```python
import pickle
import random
from pathlib import Path


def train(out_dir: Path) -> float:
    seed = random.randrange(2**32)  # new every run and never recorded
    rng = random.Random(seed)
    score = fit(rng)
    pickle.dump(rng.getstate(), (out_dir / "rng.pkl").open("wb"))  # unsafe to load
    return score
```

## Good Example

```python
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from jobs.context import JobContext  # the frozen record of domino-paths-from-env


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    run_number: str
    project: str
    starting_user: str
    git_commit: str
    environment_revision_id: str  # passed in: no variable carries it
    hardware_tier_id: str
    snapshots: Mapping[str, int]
    config: Mapping[str, str]
    seed: int
    versions: Mapping[str, str]
    started_at: str
    finished_at: str


def version_of(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def build_manifest(
    ctx: JobContext,
    config: Mapping[str, str],
    *,
    env: Mapping[str, str],
    seed: int,
    snapshots: Mapping[str, int],
    git_commit: str,
    started_at: datetime,
) -> RunManifest:
    return RunManifest(
        run_id=ctx.run_id,
        run_number=ctx.run_number,
        project=f"{ctx.project_owner}/{ctx.project_name}",
        starting_user=env.get("DOMINO_STARTING_USERNAME", "local"),
        git_commit=git_commit,
        environment_revision_id=config["environment_revision_id"],
        hardware_tier_id=env.get("DOMINO_HARDWARE_TIER_ID", "local"),
        snapshots=dict(snapshots),
        config=dict(config),
        seed=seed,
        versions={n: version_of(n) for n in ("numpy", "pandas", "scikit-learn")},
        started_at=started_at.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


def write_manifest(path: Path, manifest: RunManifest) -> None:
    text = json.dumps(asdict(manifest), indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
```

## Notes

- The seed is a command-line argument with a fixed default that seeds one generator passed down; where numpy, pandas or polars draw the numbers, follow `ml-seeded-randomness` (ml-data).
- Seeds and state go to JSON, never pickle, even where the platform docs suggest pickling them (`ml-serialization-security`, ml-data, where the repo uses a model stack it covers).
- The injected variables carry no environment revision: pass the pinned revision ID in as configuration (`domino-environment-revisions`). Read the commit with `git rev-parse HEAD` through `subprocess.run` with a timeout, and record `"unknown"` when the run is not Git-based.
- Record the names of the secret variables a job used, never their values (`domino-secrets-in-env-vars`).
- Produce results that must be reproduced with jobs, not workspaces; quote the job number with any number used outside Domino, and keep a fixed-format summary per run so job comparisons stay readable (`domino-job-results`).

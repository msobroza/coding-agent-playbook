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
    pickle.dump(rng.getstate(), (out_dir / "rng.pkl").open("wb"))  # unsafe to load
    return fit(rng)
```

## Good Example

```python
import argparse
import json
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import distributions
from pathlib import Path

from jobs.context import JobContext  # the frozen run record of domino-paths-from-env
from jobs.pins import EnvironmentPin  # environment, revision and tier IDs

LIBS = frozenset({"numpy", "pandas", "scikit-learn"})


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    run_number: str
    project: str
    starting_user: str
    git_commit: str
    environment: EnvironmentPin  # no injected variable carries the revision
    snapshots: Mapping[str, int]
    config: Mapping[str, str]
    seed: int
    versions: Mapping[str, str]  # a library left out is not installed
    started_at: str
    finished_at: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1234)  # fixed, never drawn per run
    return parser.parse_args(argv)


def train(args: argparse.Namespace) -> float:
    return fit(random.Random(args.seed))  # the one generator, passed down to every draw


def build_manifest(
    ctx: JobContext,
    args: argparse.Namespace,
    *,
    pin: EnvironmentPin,
    snapshots: Mapping[str, int],
    git_commit: str,
    started_at: datetime,
    finished_at: datetime,
) -> RunManifest:
    return RunManifest(
        run_id=ctx.run_id,
        run_number=ctx.run_number,
        project=f"{ctx.project_owner}/{ctx.project_name}",
        starting_user=ctx.starting_user,
        git_commit=git_commit,
        environment=pin,
        snapshots=dict(snapshots),
        config={name: str(value) for name, value in vars(args).items()},
        seed=args.seed,
        versions={d.name: d.version for d in distributions() if d.name in LIBS},
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
    )


def write_manifest(path: Path, manifest: RunManifest) -> None:
    text = json.dumps(asdict(manifest), indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
```

## Notes

- Where numpy, pandas or polars draw the numbers, seed them as `ml-seeded-randomness` (ml-data) shows. Seeds and state go to JSON, never pickle, even where the platform docs suggest pickling them (`ml-serialization-security`, ml-data, where the repo uses a model stack it covers). Record the names of the secret variables a job used, never their values (`domino-secrets-in-env-vars`).
- The injected variables carry no environment revision: the pinned IDs come from the one constants module of `domino-environment-revisions`. Read the commit with `git rev-parse HEAD` through `subprocess.run` with a timeout, and record `"unknown"` when the run is not Git-based. The caller reads the clock for both times, so the manifest is built from values alone.
- Produce results that must be reproduced with jobs, not workspaces; quote the job number with any number used outside Domino, and keep a fixed-format summary per run so job comparisons stay readable (`domino-job-results`).

---
id: domino-environment-revisions
name: Environment revisions
description: "Run jobs whose results matter on an explicitly chosen environment revision and hardware tier, chosen by ID and recorded, instead of the moving latest revision and project defaults."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/flows/**/*.py"
  - "**/workflow*.py"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 26
tags: [python, domino, jobs]
---

# Environment revisions

## Description

Domino resolves the environment revision and the hardware tier when a job launches. Left to the defaults, a job runs on the project's default tier and on a revision that moves whenever someone saves the environment or its parent is rebuilt; schedules and re-runs pick the newer revision up silently.

A job whose results matter runs on an explicitly chosen revision and tier, chosen by ID, and records both in its run manifest (`domino-run-manifest`). One constants module holds the pin, and the Flow definition and the launch code both read it.

## Bad Example

```python
# A Flow task resolved by name on whatever revision is newest at launch.
train = DominoJobTask(
    name="train",
    domino_job_config=DominoJobConfig(
        Command="python jobs/train.py",
        EnvironmentName="ml-gpu",
    ),
    use_latest=True,
)
```

## Good Example

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentPin:
    """The environment revision and hardware tier a job must run on, by ID."""

    environment_id: str
    revision_id: str
    hardware_tier_id: str


TRAINING = EnvironmentPin(
    environment_id="65f0c2a1e4b0a1b2c3d4e5f6",
    revision_id="65f0c2a1e4b0a1b2c3d4e5f7",
    hardware_tier_id="gpu-small",
)
```

```python
from jobs.environments import TRAINING

train = DominoJobTask(
    name="train",
    domino_job_config=DominoJobConfig(
        Command="python jobs/train.py",
        EnvironmentId=TRAINING.environment_id,
        EnvironmentRevisionSpec=TRAINING.revision_id,
        HardwareTierId=TRAINING.hardware_tier_id,
    ),
    use_latest=False,
)
```

Check the exact form of the revision argument against the Flow SDK version the repo pins; the point is IDs for all three and `use_latest=False`.

## Notes

- The latest successful build becomes Active automatically unless the environment owner turns auto-assign off, and build propagation rebuilds child environments when a parent changes. Test a new revision with auto-assign off and make it Active only after a job passes on it.
- Job and schedule dialogs default to the latest revision; restricted projects run schedules and re-runs on the current restricted revision.
- The 6.2 docs disagree on whether "Re-Run with Original Version" reuses the original environment, so a re-run is never the reproducibility mechanism.
- Names of environments and tiers can change; IDs do not.
- python-domino's `job_start` pins the environment by ID but takes no revision, so a launch that must not drift relies on the owner holding the Active revision (`domino-launch-jobs-from-code`).
- The smallest tier that fits provisions fastest; spot tiers need checkpoints (`domino-spot-checkpoints`).
- Record `DOMINO_HARDWARE_TIER_ID` in the run manifest.
- What the image contains is `domino-pinned-environments`.

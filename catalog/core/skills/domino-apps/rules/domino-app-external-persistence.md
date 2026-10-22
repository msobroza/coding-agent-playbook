---
id: domino-app-external-persistence
name: Domino App external persistence
description: "Save what a Domino App must keep to a Dataset, a database or an object store, never to project files that vanish with the container."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
  - "**/storage.py"
  - "**/store.py"
applies_if:
  domino_project: true
section: state
priority: 30
tags: [python, domino, apps]
---

# Domino App external persistence

Project files are writable inside a running App, which hides the problem: unlike a Job or a workspace, an App never syncs a file change back to the project. The next stop, restart or scale event deletes its container and every change with it, so a write that worked all week is gone after an upgrade.

## Bad Example

```python
import csv
from pathlib import Path

FEEDBACK = Path("data/feedback.csv")  # inside the project: lost at the next restart


def save_feedback(viewer: str, text: str) -> None:
    with FEEDBACK.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow([viewer, text])
```

## Good Example

The page depends on a small storage port; the adapter decides where the data lives.

```python
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Feedback:
    viewer_id: str
    text: str


class FeedbackStore(Protocol):
    def add(self, feedback: Feedback) -> None: ...


class DatasetFeedbackStore:
    """Writes one file per entry under a mounted Dataset, which outlives the App."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def add(self, feedback: Feedback) -> None:
        target = self._root / "feedback" / f"{uuid.uuid4().hex}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(feedback)), encoding="utf-8")


def build_store() -> FeedbackStore:
    return DatasetFeedbackStore(Path(os.environ["FEEDBACK_DATASET_DIR"]))
```

A database or an object store adapter implements the same `add` method; tests use an in-memory fake.

## Notes

- Temporary files are fine for scratch work inside one request (`tempfile.TemporaryDirectory()`), never for anything a later request reads.
- Dataset paths come from the environment, never a literal mount path: domino-paths-from-env and domino-project-types (domino-jobs).
- Credentials for a database or an object store are the starter's (`domino-app-starter-settings`).
- Several viewers and replicas write at once: `domino-app-concurrent-writes`.

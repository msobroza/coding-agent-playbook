---
id: domino-app-concurrent-writes
name: Domino App concurrent writes
description: "Write shared App data through a database transaction or one atomically replaced file per writer, never a read-modify-write of a shared file."
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
priority: 31
tags: [python, domino, apps]
---

# Domino App concurrent writes

Viewers act at the same time, and Domino does not serialize their requests. Autoscaled replicas also share one network disk. A read-modify-write of a shared file therefore loses one viewer's entry when two requests overlap, and can leave a half-written file behind when a replica dies mid-write.

## Bad Example

```python
import json
from pathlib import Path

VOTES = Path("/mnt/data/app/votes.json")


def add_vote(viewer: str, choice: str) -> None:
    votes = json.loads(VOTES.read_text(encoding="utf-8"))  # another request reads too
    votes.append({"viewer": viewer, "choice": choice})
    VOTES.write_text(json.dumps(votes), encoding="utf-8")  # last writer wins
```

## Good Example

Shared records go to a database, one upsert per change inside one transaction:

```python
import sqlite3  # any SQL database; the transaction is the point


def add_vote(conn: sqlite3.Connection, *, viewer_id: str, choice: str) -> None:
    with conn:  # commits on success, rolls back on error
        conn.execute(
            "INSERT INTO votes (viewer_id, choice) VALUES (?, ?) "
            "ON CONFLICT (viewer_id) DO UPDATE SET choice = excluded.choice",
            (viewer_id, choice),
        )
```

Files get one path per writer, written under a temporary name and moved into place:

```python
import os
import uuid
from pathlib import Path


def write_viewer_file(root: Path, *, viewer_id: str, payload: str) -> Path:
    folder = root / viewer_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid.uuid4().hex}.json"
    staging = folder / f".{target.name}.tmp"  # same file system as the target
    staging.write_text(payload, encoding="utf-8")
    os.replace(staging, target)  # atomic: readers see the old state or the new one
    return target
```

## Notes

- Prefer a database for shared mutable state. File locks on network storage are unreliable, so this rule does not rely on them (the engine's inference, not a documented guarantee).
- Key the path by the verified viewer id (`domino-app-verify-viewer-jwt`), never by a name the viewer typed.
- The staging-then-replace helper and its same-file-system constraint are domino-run-scoped-writes (domino-jobs); here the key is the viewer instead of the run.
- Setup scripts run in every replica at once: keep them idempotent, or move the work into the environment image (domino-pinned-environments, domino-jobs).

---
id: domino-idempotent-jobs
name: Idempotent jobs
description: "Take the unit of work as an argument, skip work already done, write atomically and make every side effect an upsert, so re-runs and retries repeat safely."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: scheduling-and-launching
priority: 45
tags: [python, domino, jobs, scheduling]
---

# Make jobs safe to run again

## Description

The same job runs again on purpose (the re-run button, `job_restart`, a scheduled run that starts late or overlaps the previous one) and by accident (Flow task retries, spot reclaims, an orchestrator retrying after a timeout). Every run must therefore leave the same result as one clean run.

A job takes its unit of work (a date, a partition, a batch ID) as an argument instead of reading the clock, checks for that unit's completed output before computing, writes outputs atomically, and makes every external side effect (database writes, notifications, model publishing) an upsert or a step guarded by a marker keyed by the unit.

## Bad Example

```python
from datetime import date


def main() -> None:
    day = date.today()  # a late or re-run job processes the wrong day
    rows = build_rows(day)
    cursor.executemany("INSERT INTO daily_sales VALUES (?, ?, ?)", rows)  # duplicates
    notify_team(f"sales for {day} loaded")  # sent on every attempt
```

## Good Example

```python
import argparse
from datetime import date
from pathlib import Path

UPSERT = """
INSERT INTO daily_sales (day, customer_id, amount_cents) VALUES (?, ?, ?)
ON CONFLICT (day, customer_id) DO UPDATE SET amount_cents = excluded.amount_cents
"""


def run_partition(day: date, out_root: Path, *, force: bool = False) -> bool:
    """Build one day's partition; return False when it is already complete."""
    part = out_root / f"day={day.isoformat()}"
    marker = part / "_SUCCESS"
    if marker.exists() and not force:
        return False
    rows = build_rows(day)
    write_parquet_atomically(part / "sales.parquet", rows)
    marker.write_text("ok\n", encoding="utf-8")  # written last
    return True


def load(rows: list[tuple[str, str, int]]) -> None:
    cursor.executemany(UPSERT, rows)  # one row per (day, customer_id), however often it runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args(argv)
    run_partition(args.day, args.out_root)
    return 0
```

A test calls `run_partition` and `load` twice for the same day and asserts one partition and one row per key.

## Notes

- Re-runs keep the original arguments, so the unit of work must be an argument, not the clock.
- Re-running a re-run in a Git-based project reuses that run's commit, and a job started from a commit or tag never picks up newer commits.
- Flow retries and timeouts make re-execution normal (domino-flow-task-purity); spot reclaims are domino-spot-checkpoints.
- Concurrent runs and atomic writes are domino-run-scoped-writes; output paths come from domino-paths-from-env.
- SQL binds values instead of formatting them (python-parameterized-queries, python-coding).

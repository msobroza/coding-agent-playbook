---
id: domino-job-entry-point
name: Domino job entry point
description: "Give each Domino job one non-interactive entry script that parses keyword arguments, does no work at import time and keeps its logic testable."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
  - "**/*.ipynb"
applies_if:
  domino_project: true
section: entry-points-and-exit-codes
priority: 28
tags: [python, domino, jobs]
---

# Domino job entry point

Domino runs a job's command in a fresh container with no terminal, whether the UI, a schedule, a Launcher, the CLI or the API started it, and picks the interpreter from the file extension: a `.py` file runs unbuffered through `python -u`, a `.sh` file through `bash`. Each job therefore has one entry script that parses its arguments with `argparse` or the repo's CLI library, never prompts, does no work at import time, and keeps its logic in importable functions so tests run it without Domino.

## Bad Example

```python
# jobs/train.py, also scheduled as train.ipynb
import sys

SNAPSHOT = sys.argv[1]  # positional, read at import time
data = load(SNAPSHOT)  # work at import: a test import loads the data

if input("Overwrite the model? ") == "y":  # no terminal: the job hangs or fails
    save(fit(data))
```

## Good Example

```python
# jobs/train.py
import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the churn model.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = train(args.snapshot, since=args.start_date)
    if not args.dry_run:
        save_model(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
def test_dry_run_trains_without_saving(tmp_path: Path) -> None:
    assert main(["--snapshot", str(tmp_path), "--start-date", "2024-01-31", "--dry-run"]) == 0
```

## Notes

- `main` builds the settings, the job context and the clients once and passes them down (arch-composition-root, python-architecture).
- The command runs from the working directory (`/mnt` in DFS projects, the code checkout in Git-based ones), so paths in the command are relative to the repo root.
- The same command line must work from every launch surface; keep defaults in the parser, not in a schedule's command.
- A notebook given as the command is executed and saved over itself on every run: keep notebooks for reports, not for job logic.
- Custom file handlers need an administrator setting, and the 6.2 documentation names two different handler directories; check the deployment before relying on one.
- The CLI's raw shell command mode bypasses the script and its argument checks.
- A Launcher starts the same script with its form values as arguments: parsing them is `domino-launcher-arguments`, uploads are `domino-launcher-uploads`.
- The exit status follows `domino-job-exit-codes`. R, MATLAB and other handlers are out of scope here.

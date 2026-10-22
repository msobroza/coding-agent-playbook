---
id: domino-launcher-arguments
name: Domino Launcher arguments
description: "Parse every Launcher value as quoted, unexpanded text and convert and check it in the script, failing with the offending value."
version: 1
scope: scoped
globs:
  - "**/launcher*.py"
  - "**/launcher*.sh"
  - "**/launchers/**/*.py"
applies_if:
  domino_project: true
section: entry-points-and-exit-codes
priority: 29
tags: [python, domino, jobs]
---

# Domino Launcher arguments

A Launcher is a web form that fills a command template's `${name}` placeholders and runs the command as a job. Its users type free text, and every value reaches the script single-quoted: environment variables in it never expand, a file input arrives as a path, and a multi-select arrives as one comma-separated string. The script converts and checks each value itself and fails on bad input with the offending value and a non-zero exit.

## Bad Example

```python
import sys
from datetime import date

start = date.fromisoformat(sys.argv[1])  # gets the literal '$START_DATE', not a date
regions = sys.argv[2].split(" ")  # the multi-select is "north,south"
top_n = int(sys.argv[3])  # "ten" ends in a bare traceback
```

## Good Example

```python
import argparse
from datetime import date
from pathlib import Path

REGIONS = frozenset({"north", "south", "east", "west"})


def region_list(raw: str) -> list[str]:
    regions = [part.strip() for part in raw.split(",") if part.strip()]
    allowed = ", ".join(sorted(REGIONS))
    if not regions:
        raise argparse.ArgumentTypeError(f"expected one or more of {allowed}, got {raw!r}")
    unknown = sorted(set(regions) - REGIONS)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown regions {unknown}; expected {allowed}")
    return regions


def existing_file(raw: str) -> Path:
    path = Path(raw)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"no such file: {raw!r}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--regions", type=region_list, required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--targets", type=existing_file)
    return parser
```

The command template passes each field as a named option, for example `python launchers/report.py --start-date ${start_date} --regions ${regions}`; argparse reports a bad value and exits with status 2.

## Notes

- The script's entry point and exit status follow `domino-job-entry-point` and `domino-job-exit-codes`.
- The same command also runs from schedules and the API, so keep the parsing in the script, not in the form.
- Contributors and Launcher Users can run a Launcher; treat every value as untrusted input.

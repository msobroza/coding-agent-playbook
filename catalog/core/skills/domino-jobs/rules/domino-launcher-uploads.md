---
id: domino-launcher-uploads
name: Domino Launcher uploads
description: "Check a Launcher upload's size and type, read it from its given path and write only small summary outputs, since every file touched becomes a result."
scope: scoped
globs:
  - "**/launcher*.py"
  - "**/launcher*.sh"
  - "**/launchers/**/*.py"
applies_if:
  domino_project: true
section: entry-points-and-exit-codes
priority: 30
tags: [python, domino, jobs]
---

# Domino Launcher uploads

A file a Launcher user uploads arrives as a path, and Domino keeps it in the project as a result of the run. Every other file the script creates or changes becomes a result too, and project files cope badly with files of several gigabytes or with thousands of files. The script checks the upload first, reads it where it is, and writes only the outputs the user needs.

## Bad Example

```python
import shutil
from pathlib import Path


def handle(upload: Path) -> None:
    shutil.copy(upload, Path("data") / upload.name)  # a second copy in the project
    for i, chunk in enumerate(split_rows(upload)):
        Path(f"tmp/part_{i}.csv").write_text(chunk, encoding="utf-8")  # thousands of results
```

## Good Example

```python
import csv
from pathlib import Path

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = frozenset({".csv"})


class UploadError(ValueError):
    pass


def check_upload(upload: Path) -> None:
    if upload.suffix.lower() not in ALLOWED_SUFFIXES:
        raise UploadError(f"{upload.name}: expected a .csv file")
    size = upload.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise UploadError(
            f"{upload.name} is {size} bytes; put large inputs in a Dataset and pass its name"
        )


def summarize(upload: Path, out_dir: Path) -> Path:
    check_upload(upload)
    with upload.open(encoding="utf-8", newline="") as rows:
        count = sum(1 for _ in csv.DictReader(rows))
    summary = out_dir / "summary.txt"
    summary.write_text(f"rows: {count}\n", encoding="utf-8")
    return summary
```

`main` turns an `UploadError` into a logged message and a non-zero exit.

## Notes

- Large inputs belong in a Dataset; the Launcher then takes the dataset name or path as an argument (`domino-datasets-for-large-data`).
- Where results go and which ones readers see follow `domino-job-results`; an `email.html` the script writes becomes the notification body (`domino-job-email-report`).
- A Launcher can target a remote data plane through its hardware tier, so do not assume a mount another tier has.
- Parsing the other form values is `domino-launcher-arguments`.

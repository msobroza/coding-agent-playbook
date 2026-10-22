---
id: domino-job-results
name: Job results
description: "Choose what a run shows with .dominoresults, keep .dominoignore for files that must never persist, and give result files the same names every run."
version: 1
scope: scoped
globs:
  - ".dominoresults"
  - ".dominoignore"
  - ".dominokeep"
  - "**/*.py"
applies_if:
  domino_project: true
section: results-and-metrics
priority: 60
tags: [python, domino, jobs, results]
---

# Curate results with .dominoresults, not .dominoignore

## Description

Every file a run adds or changes is a result: it is shown in the run's results view, attached to the success email and compared between runs. Two project files steer this, each listing one path or glob per line, relative to the project root:

- `.dominoresults` chooses the files the results view and the success email show (for example `results/*.html` or `reports/**/*.csv`), while every changed file is still saved.
- `.dominoignore` removes files from sync altogether, so an ignored file is not saved at the end of the run.

Use `.dominoresults` to choose what readers see, and `.dominoignore` only for files that must never persist: caches, virtual environments, temporary and large debug files. Result names stay the same from run to run, without `v2` or `final` suffixes, because Domino versions files itself and comparisons match files by name.

## Bad Example

```text
# .dominoignore, edited to declutter the results view
results/
```

Every output under `results/` is now dropped at the end of each run, without an error.

```python
report.write_html(f"results/report_final_v{attempt}.html")  # a new name each run
```

## Good Example

```text
# .dominoresults
results/summary.json
results/plots/*.png
results/report.html

# .dominoignore
__pycache__/
.cache/
tmp/
```

```python
import json
from pathlib import Path


def write_summary(results_dir: Path, summary: dict[str, float]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, indent=2, sort_keys=True)
    (results_dir / "summary.json").write_text(text + "\n", encoding="utf-8")
```

The job writes `results/summary.json` on every run under the same name, so two runs compare file by file.

## Notes

- `.git/` is always ignored, and Domino creates `.dominoignore` at the root of new projects; `.dominokeep` keeps an otherwise empty directory.
- An isolated results branch keeps results out of later runs' inputs and out of `domino sync`; fetch them with the download-results command.
- The docs' example admin settings cap a job comparison at 250 files and about 1 MB of diffs, so keep result files few, small and textual; large debug dumps also slow sync.
- In Git-based projects results live under the artifacts directory (domino-project-types).
- A custom email must be listed when `.dominoresults` exists (domino-job-email-report).
- where-outputs-go.md in this skill shows which files become results per project type.

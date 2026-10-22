---
id: domino-job-logging
name: Job logging
description: "Log one line per event to stdout with the run ID, at a fixed interval, and never log secrets, tokens or environment dumps."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
applies_if:
  domino_project: true
section: results-and-metrics
priority: 61
tags: [python, domino, jobs, logging]
---

# Log to stdout, with the run ID and no secrets

## Description

A job's console output is its trace: it appears as the run's User Output log, its tail is kept in `results/stdout.txt` in DFS projects, and its last lines go into the success email. Log one line per event to stdout or stderr through the `logging` module, with the run ID in each line, flushed as it goes: Domino runs `.py` files unbuffered, and other runtimes flush explicitly.

Execution logs are kept indefinitely and are included in support bundles, so they never contain secrets, tokens or environment dumps. Large log files written into the working or artifacts directory are synced and become results, so log output goes to the console instead.

## Bad Example

```python
print(dict(os.environ))  # every secret the run can see, kept forever
# grows to gigabytes and is synced as a result
debug = open("/mnt/artifacts/debug.log", "w", encoding="utf-8")
for row in tqdm(rows):  # redraws thousands of times in the log
    debug.write(repr(row) + "\n")
```

## Good Example

```python
import logging
import os
import sys
from collections.abc import Iterable

logger = logging.getLogger("jobs.score")


def configure_logging(run_id: str, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(f"%(asctime)s %(levelname)s run={run_id} %(name)s %(message)s")
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


def score_all(rows: Iterable[Row], *, every: int = 10_000) -> int:
    done = 0
    for done, row in enumerate(rows, start=1):
        score(row)
        if done % every == 0:
            logger.info("scored %d rows", done)
    logger.info("finished: scored %d rows", done)
    return done


configure_logging(os.environ.get("DOMINO_RUN_ID", "local"))
```

## Notes

- Log progress at a fixed interval, not per item, and once at the end with counts.
- The dashboard keeps resource-usage details for about 15 days, so peak memory or durations that matter go into the run manifest (domino-run-manifest) or MLflow.
- Where the repo already emits JSON log lines, keep that format and add the run ID as a field.
- Log an exception once, at the top level (python-error-handling, python-coding).
- Scratch logs that must not persist go in `.dominoignore` (domino-job-results); secrets follow domino-secrets-in-env-vars.

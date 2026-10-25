---
id: domino-job-exit-codes
name: Domino job exit codes
description: "Exit 0 only after a job's outputs are complete and non-zero on any failure, because Domino, schedules and callers read nothing else."
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
applies_if:
  domino_project: true
section: entry-points-and-exit-codes
priority: 27
tags: [python, domino, jobs]
---

# Domino job exit codes

Domino reads the process exit status of a job: 0 marks it Succeeded and anything else Failed (Error is kept for failures outside the code, such as the platform or the container). That status drives the failure email, the "Publish after complete" option that republishes an endpoint only after success, the status of a Flow task and every caller that polls the job. A job that catches everything and returns normally reports success, and can republish a model trained on bad data.

## Bad Example

```python
import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        run(parse_args())
    except Exception as exc:  # swallowed: the job shows Succeeded
        logger.error(exc)
```

```bash
python jobs/score.py "$@" || true  # every failure becomes success
echo "done"                        # the last command decides the status
```

## Good Example

```python
import argparse
import logging
import sys
from collections.abc import Sequence
from enum import IntEnum

logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    OK = 0
    BAD_INPUT = 2


def main(argv: Sequence[str] | None = None) -> ExitCode:
    args = build_parser().parse_args(argv)  # argparse exits 2 on a bad flag
    if not args.snapshot.is_dir():
        logger.error("snapshot %s does not exist", args.snapshot)
        return ExitCode.BAD_INPUT
    write_scores(args.snapshot, args.output)  # unexpected errors propagate
    return ExitCode.OK  # reached only once the outputs are written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(main())
```

A wrapper script keeps the tool's status and maps only the documented success code:

```bash
#!/usr/bin/env bash
set -euo pipefail

status=0
external-tool --input "$1" || status=$?
if [ "$status" -eq 3 ]; then  # the tool's documented "nothing to do" code
  exit 0
fi
exit "$status"
```

## Notes

- An exception left to propagate prints its traceback in the User Output log and ends the process non-zero; `main` is the job's error boundary and logs an unexpected error at most once (`python-error-boundaries` and `python-error-handling`, python-coding skill).
- The status mapping snippet in the 6.2 job documentation exits before its test runs, so write the mapping yourself as above.
- Partial success is a failure: when some partitions fail, write the list of failed partitions to a result file and exit non-zero.
- Validate a model before writing it: a schedule's "Update Domino endpoint" action runs after the job completes, and the 6.2 documentation does not say it waits for success.
- Exit 0 only after every output file is complete (`domino-run-scoped-writes`); a Flow task with a missing declared output fails even with exit 0 (`domino-flow-task-io`).
- Tests call `main([...])` and assert the returned code.

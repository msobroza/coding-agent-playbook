---
id: domino-agent-dev-eval-job
name: Development evaluation Job
description: "Run the development evaluation as a Domino Job inside one DominoRun, over versioned questions, failing when any case fails."
scope: scoped
globs:
  - "**/*_eval*.py"
  - "**/eval_*.py"
  - "**/evaluat*.py"
  - "**/evals/**/*.py"
  - "**/*questions*.csv"
  - "**/evaluators.py"
applies_if:
  domino_project: true
section: evaluation
priority: 50
tags: [python, domino, agents, evaluation]
---

# Run development evaluations as Jobs inside DominoRun

## Description

The development evaluation is a script started as a Domino Job, not run in a workspace: the Job's run then carries the commit, the agent config, the traces and the summary metrics, Experiment Manager compares it with other runs, and Deploy Agent can deploy that very run. The script wraps all cases in one `DominoRun(agent_config_path=..., experiment_name=...)` through the tracer seam, with an experiment name unique across the deployment. Each case runs through a traced case function whose evaluator scores it (the case's expected labels are its inputs) and which calls the same traced request function the App uses. The question file and an optional row cap come from `argparse`. A case that raises is logged with its id and counted as failed, and the Job exits non-zero when any case failed. The evaluation questions are versioned with the code (or read from a dataset snapshot) and include off-topic and adversarial questions.

## Bad Example

```python
MAX_ROWS = 10  # edited by hand before each run

results = []
for row in rows[:MAX_ROWS]:
    print("Q:", row["question"])
    results.append(run_agent(row["question"]))

success = sum(1 for r in results if r.get("status") == "ok")  # no result has "status"
print(f"{success} passed")
```

The cap is a module global, progress goes to `print`, the counter looks for a key no result carries, and the script always exits 0.

## Good Example

```python
import argparse
import asyncio
import csv
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)
CaseRunner = Callable[[str, str, str], Awaitable[object]]


async def run_cases(run_case: CaseRunner, cases: Sequence[dict[str, str]]) -> int:
    """Run each case in turn and return how many raised."""
    failed = 0
    for case in cases:
        try:
            await run_case(case["id"], case["question"], case["expected_tool"])
        except Exception:
            logger.exception("case failed", extra={"case_id": case["id"]})
            failed += 1
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Development evaluation of the agent.")
    parser.add_argument("questions", type=Path)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args(argv)

    settings = AgentSettings()
    configure_logging(settings.log_level)
    tracer, run_case = build_dev_eval(settings)
    with args.questions.open(encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))[: args.max_rows]

    with tracer.evaluation_run(settings.config_path, settings.experiment_name):
        failed = asyncio.run(run_cases(run_case, cases))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

`build_dev_eval` builds the agent through the App's own builders and wraps the async `run_case`, which awaits the traced request function, with `tracer.trace(name, evaluator=dev_span_evaluator)`.

## Notes

- Run the cases one after another in one thread: the 6.2 reference's thread-safety sentence contradicts itself while it allows parallel work inside one run, so the safe behavior is one `DominoRun` per thread.
- The deployed agent loads the agent config at the commit this run compared (`domino-agent-config-file`); scoring functions are `domino-agent-evaluators`.
- Entry point, exit codes, snapshots and experiment names are domino-job-entry-point, domino-job-exit-codes, domino-dataset-snapshots and domino-mlflow-tracking (domino-jobs).
- See examples/simple-agent-api/evals/dev_eval.py and examples/simple-agent-api/sample_questions.csv.

---
id: domino-agent-eval-out-of-band
name: Production evaluation out of band
description: "Score production traces in a scheduled, sequential Domino Job that logs results back, never with an evaluator on the request path."
version: 1
scope: scoped
globs:
  - "**/*_eval*.py"
  - "**/eval_*.py"
  - "**/evaluat*.py"
  - "**/evals/**/*.py"
  - "**/*questions*.csv"
  - "**/evaluators.py"
  - "**/*agent*.py"
  - "**/tracing.py"
  - "**/chat_app.py"
  - "**/main.py"
applies_if:
  domino_project: true
section: evaluation
priority: 52
tags: [python, domino, agents, evaluation]
---

# Score production traces out of band

## Description

The production request function's `add_tracing` carries no evaluator: an inline judge adds its latency and its model cost to every user request, and a failing judge can fail the request. Production traces still flow into the agent's monitoring dashboard. Score them in a separate script that runs as a scheduled Domino Job: it reads the agent's traces (agent id and version from settings or arguments, filtered by version unless the Job means to cover every version) and logs each metric back to its trace with `log_evaluation`, so the dashboard shows the scores next to the traces. Set the schedule to run sequentially, so two runs never overlap and score the same traces at once.

## Bad Example

```python
from domino.agents.tracing import add_tracing


@add_tracing(name="ask_agent", evaluator=llm_judge)  # a judge call on every user request
async def ask_agent(question: str) -> AgentAnswer: ...
```

Every request now waits for, and pays for, a second model call, and the judge sees production data inside the App process.

## Good Example

```python
# app/main.py, inside create_app: the request path carries no evaluator.
ask = tracer.trace(REQUEST_SPAN_NAME)(make_ask(agent, deps))
```

```python
# evals/prod_eval.py: a scheduled Job, set to run sequentially.
import argparse
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score production traces of the agent.")
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--agent-version", default=None)
    args = parser.parse_args(argv)
    settings = AgentSettings()
    configure_logging(settings.log_level)
    store = select_trace_store(settings)
    scored = score_new_traces(
        store,
        agent_id=args.agent_id or settings.agent_id,
        agent_version=args.agent_version or settings.agent_version,
        watermark=WatermarkFile(settings.watermark_path),
        now=lambda: datetime.now(timezone.utc),
    )
    logger.info("scored traces", extra={"count": scored})
    return 0
```

`score_new_traces` pages through the traces from a watermark and calls `score_answer` from the shared evaluators; its loop is `domino-agent-prod-eval-watermark`.

## Notes

- The schedule and its overlap choice are domino-job-schedules, and rerun safety is domino-idempotent-jobs (domino-jobs).
- Trace selection, paging and the watermark are `domino-agent-prod-eval-watermark`; the metric functions are `domino-agent-evaluators`.
- The example's evals/prod_eval.py is the production Job.

---
id: domino-agent-prod-eval-watermark
name: Production evaluation watermark
description: "Page through every trace in a fixed UTC window from a stored watermark, skip scored traces, and advance the watermark only after success."
version: 1
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
priority: 53
tags: [python, domino, agents, evaluation]
---

# Score each production trace once from a watermark

## Description

The production evaluation Job fixes its window end when it starts (aware UTC now). It starts at the stored watermark minus an overlap of at least the request deadline, because a request still running at the previous window end is recorded after that run searched; on the first run it starts at a configured lookback. It calls `search_agent_traces` with `trace_name` set to the shared request span name, `start_time`, `end_time` and `page_token`, and loops until no token comes back (one call returns one page, 100 traces by default). In each trace it picks the request span by its shared name, not `spans[0]`, and reads only public fields, never framework internals. A trace whose `evaluation_results` already hold this Job's metric names is skipped, which makes the overlap safe. Only after every page succeeded does it write the window end to the watermark file atomically (temp file plus `os.replace`) on a dataset path from settings. A missing file means a first run; a corrupt one raises an error naming the path.

## Bad Example

```python
def run() -> int:
    try:
        since = datetime.fromisoformat(WATERMARK_PATH.read_text(encoding="utf-8"))  # naive
    except Exception:
        return 0  # any problem silently skips the run
    page = search_agent_traces(agent_id=AGENT_ID, start_time=since)  # first page only
    for trace in page.data:
        span = trace.spans[0]  # whichever span came first
        log_scores(trace.id, score_answer(span.outputs["output"], []))
    last = page.data[-1]._state.end_time  # a private framework field
    WATERMARK_PATH.write_text(str(last), encoding="utf-8")  # before scoring is known to finish
    return len(page.data)
```

## Good Example

```python
def score_new_traces(
    store: TraceStore, watermark: WatermarkFile, eval_config: ProdEvalConfig, now: datetime
) -> int:
    first_run_start = now - eval_config.lookback
    start = (watermark.read() or first_run_start) - eval_config.overlap  # None: first run
    scored, token = 0, None
    while True:
        page = store.search(
            eval_config.agent_id, eval_config.agent_version, REQUEST_SPAN_NAME, start, now, token
        )
        scored += score_page(store, page)
        token = page.page_token
        if token is None:
            break
    watermark.write(now)  # temp file, then os.replace
    return scored


def score_page(store: TraceStore, page: TracePage) -> int:
    unscored = [t for t in page.traces if not METRIC_NAMES <= t.evaluation_names]
    for trace in unscored:
        for name, value in score_answer(trace.answer, trace.tools).items():
            store.log_evaluation(trace.trace_id, name, value)
    return len(unscored)
```

`now` is aware UTC, taken once by the caller; `ProdEvalConfig` holds the agent id and version, the lookback and the overlap, and `DominoTraceStore` maps the SDK's `SearchTracesResponse` and `TraceSummary` to these typed records.

## Notes

- Whether `start_time` is inclusive and how naive datetimes are read is not documented, so the safe behavior is aware UTC, an overlapping window and skipping traces already scored.
- Dataset paths come from the environment, never literals (domino-paths-from-env); the atomic replace follows domino-run-scoped-writes and skipping finished work follows domino-idempotent-jobs (all domino-jobs).
- Scheduling and the evaluator-free request path are `domino-agent-eval-out-of-band`.
- See examples/simple-agent-api/evals/prod_eval.py and examples/simple-agent-api/evals/trace_store.py.

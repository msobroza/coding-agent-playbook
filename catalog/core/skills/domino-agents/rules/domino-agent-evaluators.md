---
id: domino-agent-evaluators
name: Agent evaluators
description: "Write evaluators as pure, deterministic functions returning a flat metric mapping, with metric names shared by both evaluation Jobs."
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
priority: 51
tags: [python, domino, agents, evaluation]
---

# Write evaluators as pure functions

## Description

An evaluator takes span inputs and outputs and returns a flat mapping of metric name to number or label; the SDK saves that mapping on the trace. Make it a pure function: no randomness, no printing, no I/O. Metric names are module constants shared by the development evaluator and the production Job, so dashboards line up. Reference-based metrics (expected tool, expected answer) run only in development, where each case carries its label; reference-free metrics (answered, refused, length, format) run in both. An LLM judge, when one is used, is injected with a pinned model and temperature 0, and its prompt is versioned with the code. A thin adapter reads the span by the request function's contract keys and calls the pure scorers, so tests use plain fake span objects.

## Bad Example

```python
import random


class Evaluator:
    def evaluate(self, span) -> dict[str, float]:
        print("SPAN:", span.inputs, span.outputs)
        return {"accuracy": random.uniform(0.6, 1.0), "relevance": random.uniform(0.5, 1.0)}
```

The scores are random, so a placeholder looks like a measurement, and every span is printed to the Job log.

## Good Example

```python
from collections.abc import Mapping, Sequence
from typing import Final, Protocol

ANSWERED: Final = "answered"
SINGLE_TOOL: Final = "single_tool"
ANSWER_CHARS: Final = "answer_chars"
TOOL_MATCH: Final = "tool_match"


class SpanLike(Protocol):
    inputs: Mapping[str, object]
    outputs: Mapping[str, object]


def score_answer(answer: str, tools: Sequence[str]) -> dict[str, float]:
    return {
        ANSWERED: float(bool(answer.strip())),
        SINGLE_TOOL: float(len(tools) == 1),
        ANSWER_CHARS: float(len(answer)),
    }


def score_tool_choice(expected_tool: str, tools: Sequence[str]) -> dict[str, float]:
    return {TOOL_MATCH: float(expected_tool in tools)}


def dev_span_evaluator(span: SpanLike) -> dict[str, float]:
    answer = str(span.outputs["answer"])
    raw_tools = span.outputs["tools"]
    tools = [str(tool) for tool in raw_tools] if isinstance(raw_tools, list) else []
    expected = str(span.inputs["expected_tool"])
    return {**score_answer(answer, tools), **score_tool_choice(expected, tools)}
```

The production Job calls `score_answer` only, under the same metric names.

## Notes

- A placeholder scorer is not an evaluation: leave the metric out until it measures something.
- The 6.2 SDK runs inline evaluators during development; production scoring happens out of band (`domino-agent-eval-out-of-band`).
- The span keys come from the request function's contract (`domino-agent-trace-entrypoint`).
- See examples/simple-agent-api/evals/evaluators.py.

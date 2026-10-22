---
id: domino-agent-manual-spans
name: Manual agent spans
description: "Give steps that autologging cannot see an mlflow.trace span with a span type, and keep one instrumentation path."
version: 1
scope: scoped
globs:
  - "**/*agent*.py"
  - "**/tracing.py"
  - "**/chat_app.py"
  - "**/main.py"
applies_if:
  domino_project: true
section: tracing
priority: 48
tags: [python, domino, agents, tracing]
---

# Span the steps autologging misses

## Description

Autologging a supported framework (`pydantic_ai`, `langchain`, `openai`, `llama_index` and others, named in `autolog_frameworks`) records its model and tool calls. A step it cannot see, such as hand-written retrieval, a direct HTTP call to a tool service or a custom output parser, gets `mlflow.trace` with a span type (`LLM`, `TOOL`, `RETRIEVER`, `CHAIN`, `AGENT` or `EMBEDDING`) and runs under the traced request function, so it lands in the same trace and the Traces tab shows it. Choose one instrumentation path: do not stack the framework's own OpenTelemetry instrumentation on top of MLflow autologging without checking the trace for duplicate spans.

## Bad Example

```python
async def search_documents(query: str) -> list[str]:
    print("=== RETRIEVAL START ===", query)
    hits = await index.search(query, limit=5)
    print("=== RETRIEVAL END ===", len(hits))
    return [hit.text for hit in hits]


agent = Agent(model, instrument=True)  # a second tracing path beside autologging
```

Print banners stand in for a span, so the retrieval never appears in the trace, while the framework's own instrumentation records the model calls a second time.

## Good Example

```python
import mlflow
from mlflow.entities import SpanType


@mlflow.trace(span_type=SpanType.RETRIEVER)
async def search_documents(query: str) -> list[str]:
    hits = await index.search(query, limit=5)
    return [hit.text for hit in hits]
```

`search_documents` is called from a tool inside the traced request function, so its span nests under the request span next to the autologged model and tool calls.

## Notes

- Span inputs and outputs are stored like the request function's: nothing secret goes in (`domino-agent-redact-traces`).
- A repo that imports `mlflow` directly declares it as its own dependency instead of relying on the agent SDK to bring it in.
- Experiment naming is domino-mlflow-tracking (domino-jobs).
- The request span itself is `domino-agent-trace-entrypoint`.

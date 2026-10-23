---
id: domino-agent-fake-domino-tests
name: Agent tests on Domino fakes
description: "Put Domino behind small seams and test them with named fakes of the SDK's shapes: a paging trace store, a recording tracer, a mock token endpoint and a fake clock."
version: 1
scope: scoped
section: testing
priority: 64
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
  - "**/fakes.py"
applies_if:
  domino_project: true
  has_framework: ["pytest"]
tags: [python, domino, pytest]
---

# Agent tests on Domino fakes

Code that talks to Domino sits behind small seams (the token provider, the tracer, the trace store), and tests drive it with named fakes that reproduce the SDK's shapes: a `FakeTraceStore` that serves pages with page tokens and records the evaluations logged, a `RecordingTracer` that records span names, inputs and evaluator results, and an `httpx.MockTransport` token endpoint read through a fake clock. The real adapter gets one thin test, skipped with a reason when the SDK is not installed. The suite then runs in CI with no Domino workspace.

Cover, for the token provider: a cache hit inside the TTL, a refresh after it, one fetch for concurrent callers, a timeout that raises a domain error without the token in its message or the logs, and one retry after a 401. For the production evaluation Job: two pages scored once each, a late trace inside the overlap window scored once, a rerun after a crash scoring nothing twice, the watermark written only after success, and a corrupt watermark failing with its path.

## Bad Example

```python
@patch("domino.agents.tracing.search_agent_traces", return_value=PAGE)  # needs the SDK
def test_prod_eval(search: MagicMock) -> None:
    run_prod_eval()  # reads DOMINO_PROJECT_NAME and the real watermark path
    assert True  # nothing checked: the second page and the watermark are never seen
```

## Good Example

```python
# tests/fakes.py
from dataclasses import dataclass, field


@dataclass
class FakeTraceStore:
    """Serves traces in fixed pages, like the SDK's search, and records evaluations."""

    pages: list[list[TraceRecord]]
    fail_on_page: int | None = None
    logged: list[tuple[str, str, float]] = field(default_factory=list)

    def search(self, query: TraceQuery, page_token: str | None) -> TracePage:
        index = int(page_token or 0)
        if index == self.fail_on_page:
            raise TraceStoreError(f"page {index} unavailable")
        next_token = str(index + 1) if index + 1 < len(self.pages) else None
        return TracePage(traces=tuple(self.pages[index]), next_page_token=next_token)

    def log_evaluation(self, trace_id: str, name: str, value: float) -> None:
        self.logged.append((trace_id, name, value))
```

```python
# tests/test_evals.py
def test_a_failed_page_keeps_the_watermark_and_the_rerun_scores_the_rest(
    tmp_path: Path,
) -> None:
    store = FakeTraceStore(pages=[[trace("t1")], [trace("t2")]], fail_on_page=1)
    watermark = tmp_path / "watermark.json"

    with pytest.raises(TraceStoreError):
        run_prod_eval(store, watermark, now=FIXED_NOW)
    store.fail_on_page = None
    run_prod_eval(store, watermark, now=FIXED_NOW)

    assert [trace_id for trace_id, _, _ in store.logged].count("t1") == 1
    assert {trace_id for trace_id, _, _ in store.logged} == {"t1", "t2"}
```

## Notes

- Doubles and deterministic time are pytest-test-doubles and pytest-deterministic-tests (python-testing); keeping a fake faithful to the real adapter is arch-contract-tests-for-fakes (python-architecture).
- The model side is domino-agent-fake-llm-tests.
- Example: examples/simple-agent-api/tests/fakes.py, examples/simple-agent-api/tests/test_domino_token.py and examples/simple-agent-api/tests/test_evals.py.

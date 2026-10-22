"""The seam in front of the agent SDK's trace search and evaluation logging.

The production evaluation Job reads traces and logs scores only through
TraceStore, as typed records; DominoTraceStore is the one adapter that imports
the SDK (lazily). It picks the request span by its shared name instead of the
first span, reads only public fields, and copies the names of the evaluations a
trace already holds, so the Job can skip traces it scored before. Any SDK failure
leaves it as TraceStoreError naming the agent or the trace, so the Job stops
before it advances its watermark.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.tracing import REQUEST_SPAN_NAME
from evals.evaluators import answer_and_tools

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceQuery:
    """Which traces to read: one agent (and version), one span name, one time window."""

    agent_id: str
    agent_version: str | None
    trace_name: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class TraceRecord:
    """One production request: its trace id, answer, tools and the evaluations it holds."""

    trace_id: str
    answer: str
    tools: tuple[str, ...]
    evaluation_names: frozenset[str]


@dataclass(frozen=True)
class TracePage:
    """One page of traces; ``page_token`` is None on the last page."""

    traces: tuple[TraceRecord, ...]
    page_token: str | None


class TraceStoreError(RuntimeError):
    """Reading traces or logging an evaluation failed."""


class TraceStore(Protocol):
    """Pages through an agent's traces and logs evaluations back to them."""

    def search(self, query: TraceQuery, page_token: str | None) -> TracePage: ...

    def log_evaluation(self, trace_id: str, name: str, value: float) -> None: ...


class DominoTraceStore:
    """The agent SDK's search_agent_traces and log_evaluation behind TraceStore."""

    def search(self, query: TraceQuery, page_token: str | None) -> TracePage:
        from domino.agents.tracing import search_agent_traces

        try:
            response = search_agent_traces(
                agent_id=query.agent_id,
                agent_version=query.agent_version,
                trace_name=query.trace_name,
                start_time=query.start,
                end_time=query.end,
                page_token=page_token,
            )
        except Exception as exc:
            raise TraceStoreError(f"searching the traces of agent {query.agent_id} failed") from exc
        records = [record for trace in response.data if (record := _to_record(trace))]
        token = response.page_token
        return TracePage(tuple(records), str(token) if token else None)

    def log_evaluation(self, trace_id: str, name: str, value: float) -> None:
        from domino.agents.logging import log_evaluation

        try:
            log_evaluation(trace_id=trace_id, name=name, value=value)
        except Exception as exc:
            raise TraceStoreError(f"logging {name} on trace {trace_id} failed") from exc


class _SpanSummary(Protocol):
    name: str
    outputs: object


class _EvaluationResult(Protocol):
    name: str


class _TraceSummary(Protocol):
    id: str
    spans: Sequence[_SpanSummary]
    evaluation_results: Sequence[_EvaluationResult]


def _to_record(trace: _TraceSummary) -> TraceRecord | None:
    """The trace's request span as a record; None when the trace has no request span."""
    span = next((s for s in trace.spans if s.name == REQUEST_SPAN_NAME), None)
    if span is None:
        logger.warning("trace has no request span", extra={"trace_id": trace.id})
        return None
    raw = span.outputs
    outputs: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    answer, tools = answer_and_tools(outputs)
    return TraceRecord(
        trace_id=trace.id,
        answer=answer,
        tools=tuple(tools),
        evaluation_names=frozenset(result.name for result in trace.evaluation_results),
    )

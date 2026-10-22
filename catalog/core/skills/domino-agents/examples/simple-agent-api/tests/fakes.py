"""Named fakes for everything outside the process: the model, the token endpoint, the Domino SDK.

scripted_model plays the LLM: it calls science_line for a science question and
philosophy_line otherwise, then answers with the line the tool returned.
FakeTokenProvider hands out numbered tokens; RecordingTracer stands in for
add_tracing and DominoRun and records spans; FakeTraceStore serves pages of
traces with page tokens, like the SDK's search, and records the evaluations
logged. make_settings builds settings in code.
"""

import asyncio
import contextlib
import dataclasses
import functools
import inspect
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import SecretStr
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agent import PHILOSOPHY_TOOL, SCIENCE_TOOL
from app.settings import EXAMPLE_ROOT, AgentSettings
from app.tracing import SpanEvaluator
from evals.trace_store import TracePage, TraceQuery, TraceRecord, TraceStoreError

F = TypeVar("F", bound=Callable[..., object])

#: The example's own agent config, so the tests prove the shipped file loads.
SHIPPED_CONFIG = EXAMPLE_ROOT / "agent_config.yaml"
#: Words that make scripted_model pick the science tool.
SCIENCE_WORDS = ("planet", "star", "atom", "density", "mass", "photosynthesis", "spleen")


def make_settings(config_path: Path = SHIPPED_CONFIG, **overrides: Any) -> AgentSettings:
    """Settings built in code: no .env file, outside Domino, a placeholder provider key.

    ``Any``: the overrides go straight to the settings model, which validates them.
    """
    values: dict[str, Any] = {
        "config_path": config_path,
        "openai_api_key": SecretStr("test-provider-key"),
        "domino_api_host": None,
        "domino_api_proxy": None,
        "public_url": "https://agents.example.com/apps/simple-agent",
        "cors_origins": [],
        **overrides,
    }
    return AgentSettings(_env_file=None, **values)


def latest_prompt(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


def _tool_return(messages: list[ModelMessage]) -> str | None:
    last = messages[-1]
    if isinstance(last, ModelRequest):
        for part in last.parts:
            if isinstance(part, ToolReturnPart):
                return str(part.content)
    return None


def scripted_response(messages: list[ModelMessage]) -> ModelResponse:
    """Call the tool the question's keywords pick, then repeat the line the tool returned."""
    line = _tool_return(messages)
    if line is not None:
        return ModelResponse(parts=[TextPart(content=line)])
    question = latest_prompt(messages).lower()
    tool = SCIENCE_TOOL if any(word in question for word in SCIENCE_WORDS) else PHILOSOPHY_TOOL
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args={})])


def scripted_model() -> FunctionModel:
    """A model that routes by keyword to one tool, then repeats the tool's line."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return scripted_response(messages)

    return FunctionModel(respond)


def failing_model(error: Exception) -> FunctionModel:
    """A model whose every request raises ``error``."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise error

    return FunctionModel(respond)


def slow_model(seconds: float) -> FunctionModel:
    """A model that takes ``seconds`` before answering."""

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(seconds)
        return ModelResponse(parts=[TextPart(content="too late")])

    return FunctionModel(respond)


def looping_model() -> FunctionModel:
    """A model that never stops calling a tool."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name=SCIENCE_TOOL, args={})])

    return FunctionModel(respond)


class FakeTokenProvider:
    """Numbered tokens: ``token-1`` until invalidated, then ``token-2``, and so on."""

    def __init__(self) -> None:
        self.issued = 0
        self.invalidations = 0
        self._current: str | None = None

    async def token(self) -> str:
        if self._current is None:
            self.issued += 1
            self._current = f"token-{self.issued}"
        return self._current

    def invalidate(self) -> None:
        self.invalidations += 1
        self._current = None


class FakeClock:
    """A monotonic clock that moves only when a test advances it."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class FakeSpan:
    """A span as an evaluator sees it: the traced function's inputs and outputs."""

    inputs: Mapping[str, object]
    outputs: Mapping[str, object]


@dataclass(frozen=True)
class RecordedSpan:
    """One traced call: its span name, inputs, outputs and evaluator result."""

    name: str
    inputs: Mapping[str, object]
    outputs: Mapping[str, object]
    evaluation: Mapping[str, float] | None


class RecordingTracer:
    """Stands in for add_tracing and DominoRun: runs functions unchanged and records each call."""

    def __init__(self) -> None:
        self.spans: list[RecordedSpan] = []
        self.evaluation_runs: list[tuple[Path, str]] = []

    def trace(self, name: str, evaluator: SpanEvaluator | None = None) -> Callable[[F], F]:
        def decorate(function: F) -> F:
            signature = inspect.signature(function)
            call = cast("Callable[..., Awaitable[object]]", function)

            @functools.wraps(function)
            async def traced(*args: object, **kwargs: object) -> object:
                inputs = dict(signature.bind(*args, **kwargs).arguments)
                result = await call(*args, **kwargs)
                outputs = dict(result) if isinstance(result, Mapping) else {"output": result}
                span = FakeSpan(inputs, outputs)
                evaluation = None if evaluator is None else evaluator(span)
                self.spans.append(RecordedSpan(name, inputs, outputs, evaluation))
                return result

            return cast("F", traced)

        return decorate

    @contextlib.contextmanager
    def evaluation_run(self, config_path: Path, experiment_name: str) -> Iterator[None]:
        self.evaluation_runs.append((config_path, experiment_name))
        yield

    def inputs(self, name: str) -> list[Mapping[str, object]]:
        """The inputs of every recorded span called ``name``, in call order."""
        return [span.inputs for span in self.spans if span.name == name]


@dataclass
class FakeTraceStore:
    """Serves traces in fixed pages with page tokens, like the SDK's search; records evaluations.

    A logged evaluation is added to the trace's evaluation names, as the SDK's
    trace tags are, so a rerun sees which traces are already scored.
    """

    pages: list[list[TraceRecord]]
    fail_on_page: int | None = None
    logged: list[tuple[str, str, float]] = field(default_factory=list)
    queries: list[TraceQuery] = field(default_factory=list)

    def search(self, query: TraceQuery, page_token: str | None) -> TracePage:
        self.queries.append(query)
        index = int(page_token or 0)
        if index == self.fail_on_page:
            raise TraceStoreError(f"page {index} unavailable")
        next_token = str(index + 1) if index + 1 < len(self.pages) else None
        return TracePage(traces=tuple(self.pages[index]), page_token=next_token)

    def log_evaluation(self, trace_id: str, name: str, value: float) -> None:
        self.logged.append((trace_id, name, value))
        self.pages = [
            [
                dataclasses.replace(t, evaluation_names=t.evaluation_names | {name})
                if t.trace_id == trace_id
                else t
                for t in page
            ]
            for page in self.pages
        ]

    def scored_ids(self) -> list[str]:
        """Each trace id once per time it was scored (its first metric marks a scoring)."""
        first_metric = self.logged[0][1] if self.logged else None
        return [trace_id for trace_id, name, _ in self.logged if name == first_metric]

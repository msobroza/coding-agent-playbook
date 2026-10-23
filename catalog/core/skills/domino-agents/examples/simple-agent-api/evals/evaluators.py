# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""Pure, deterministic scorers shared by the development and the production evaluation Jobs.

Each scorer returns a flat mapping of metric name to number; the metric names are
module constants, so both Jobs' results line up on the dashboards. The reference
metric (tool_match) needs a labelled case and runs only in development; the
reference-free metrics (answered, single_tool, answer_chars) run in both.
dev_span_evaluator reads a span by the request function's contract keys.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from app.tracing import SpanLike

ANSWERED: Final = "answered"
SINGLE_TOOL: Final = "single_tool"
ANSWER_CHARS: Final = "answer_chars"
TOOL_MATCH: Final = "tool_match"
#: The metrics the production Job logs; a trace holding all of them is already scored.
PRODUCTION_METRICS: Final = frozenset({ANSWERED, SINGLE_TOOL, ANSWER_CHARS})


def score_answer(answer: str, tools: Sequence[str]) -> dict[str, float]:
    """Reference-free metrics: did the agent answer, through exactly one tool, and how long."""
    return {
        ANSWERED: float(bool(answer.strip())),
        SINGLE_TOOL: float(len(tools) == 1),
        ANSWER_CHARS: float(len(answer)),
    }


def score_tool_choice(expected_tool: str, tools: Sequence[str]) -> dict[str, float]:
    """The reference metric: 1.0 when the labelled tool was called."""
    return {TOOL_MATCH: float(expected_tool in tools)}


def answer_and_tools(outputs: Mapping[str, object]) -> tuple[str, list[str]]:
    """The ``answer`` and ``tools`` of a request span's outputs; missing values read as empty."""
    answer = outputs.get("answer")
    tools = outputs.get("tools")
    return (
        answer if isinstance(answer, str) else "",
        [str(tool) for tool in tools] if isinstance(tools, list) else [],
    )


def dev_span_evaluator(span: SpanLike) -> dict[str, float]:
    """Score one development case: its inputs carry the label, its outputs the answer."""
    answer, tools = answer_and_tools(span.outputs)
    expected = str(span.inputs.get("expected_tool", ""))
    return {**score_answer(answer, tools), **score_tool_choice(expected, tools)}

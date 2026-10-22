# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The agent: two pure tools, a factory, and the one request function the App traces.

build_agent returns a new Agent with its instructions, retries and model settings
from the config and its tools registered inside the factory, so nothing is built
at import and each test gets its own agent. make_ask returns ``ask_agent``, the
function every request goes through: its parameter name (``question``) and its
returned keys (``answer``, ``tools``) are the contract the evaluators and the
production evaluation Job read from the trace. Tracing is applied by the caller
through app/tracing.py, never here.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Final, TypedDict

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.settings import AgentConfig

logger = logging.getLogger(__name__)

#: Short invented lines; the upstream quote lists named real people.
SCIENCE_LINES: Final = (
    "Every measurement carries an uncertainty worth writing down.",
    "A result that cannot be repeated is still only a rumor.",
    "Light from distant stars is old news by the time it arrives.",
    "Energy changes form; it does not vanish.",
    "A good experiment is one that could have proved you wrong.",
)
PHILOSOPHY_LINES: Final = (
    "A question asked well is half answered.",
    "Habits are decisions we stopped noticing.",
    "Certainty is comfortable; doubt is where the thinking starts.",
    "What we measure is not always what matters.",
    "Patience is a plan that trusts time.",
)
SCIENCE_TOOL: Final = "science_line"
PHILOSOPHY_TOOL: Final = "philosophy_line"


class AgentAnswer(TypedDict):
    """What the traced request function returns: the trace contract with the evaluators."""

    answer: str
    tools: list[str]


AskAgent = Callable[[str], Awaitable[AgentAnswer]]


def pick_line(lines: Sequence[str], rng: random.Random) -> str:
    """One line from ``lines``, drawn from ``rng`` (seeded in tests)."""
    return rng.choice(lines)


def build_model_settings(config: AgentConfig) -> ModelSettings:
    """The config's model parameters as pydantic-ai model settings: each one is sent."""
    return ModelSettings(temperature=config.model.temperature, max_tokens=config.model.max_tokens)


def build_agent(model: Model, config: AgentConfig, *, rng: random.Random) -> Agent[None, str]:
    """A new agent with the config's prompt, retries and model settings, and its two tools.

    The tools draw from ``rng`` through a closure: the A2A worker runs the agent
    without run dependencies, so the tools cannot rely on them.
    """
    agent: Agent[None, str] = Agent(
        model,
        name="simple-agent",
        instructions=config.prompts.system,
        retries=config.agent.retries,
        model_settings=build_model_settings(config),
    )

    @agent.tool_plain
    def science_line() -> str:
        """Answer with one short line about a science topic."""
        return pick_line(SCIENCE_LINES, rng)

    @agent.tool_plain
    def philosophy_line() -> str:
        """Answer with one short line of philosophy, for any question that is not about science."""
        return pick_line(PHILOSOPHY_LINES, rng)

    return agent


def tool_names(messages: Sequence[ModelMessage]) -> list[str]:
    """The tools the model called in ``messages``, in call order, each named once."""
    parts = (part for m in messages if isinstance(m, ModelResponse) for part in m.parts)
    calls = (part.tool_name for part in parts if isinstance(part, ToolCallPart))
    return list(dict.fromkeys(calls))


def model_request_count(messages: Sequence[ModelMessage]) -> int:
    """How many model requests ``messages`` record: one response per request."""
    return sum(isinstance(message, ModelResponse) for message in messages)


def make_ask(
    agent: Agent[None, str],
    config: AgentConfig,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> AskAgent:
    """The request function, bounded by the config's request limit and wall-clock deadline."""
    limits = UsageLimits(request_limit=config.agent.request_limit)
    deadline = config.agent.timeout_seconds

    async def ask_agent(question: str) -> AgentAnswer:
        started = clock()
        result = await asyncio.wait_for(agent.run(question, usage_limits=limits), timeout=deadline)
        messages = result.new_messages()
        tools = tool_names(messages)
        logger.info(
            "agent request answered",
            extra={
                "message_chars": len(question),
                "tools": tools,
                "model_requests": model_request_count(messages),
                "latency_ms": round((clock() - started) * 1000),
            },
        )
        return {"answer": result.output, "tools": tools}

    return ask_agent

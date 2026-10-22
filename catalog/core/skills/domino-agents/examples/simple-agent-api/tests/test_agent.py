"""The agent on a scripted model: tool routing, run limits, the trace contract, the config keys."""

import random
import re
from pathlib import Path

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
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

from app.a2a import trim_history
from app.agent import (
    PHILOSOPHY_LINES,
    SCIENCE_LINES,
    build_agent,
    build_model_settings,
    make_ask,
    pick_line,
)
from app.settings import AgentConfig, AgentConfigError, load_agent_config
from tests.fakes import SHIPPED_CONFIG, looping_model, make_settings, scripted_model

CONFIG_YAML = """\
version: "2.0.0"
model:
  provider: openai
  name: chat-model
  temperature: 0.3
  max_tokens: 256
agent:
  retries: 2
  request_limit: 3
  timeout_seconds: 5
  max_history: 4
prompts:
  system: Answer with one line.
"""


@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    path = tmp_path / "agent_config.yaml"
    path.write_text(CONFIG_YAML, encoding="utf-8")
    return load_agent_config(path)


def test_the_shipped_config_loads() -> None:
    config = load_agent_config(SHIPPED_CONFIG)

    assert config.model.provider == "openai"
    assert config.agent.request_limit > 0


def test_an_unknown_config_key_fails_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "agent_config.yaml"
    path.write_text(CONFIG_YAML + "unused_key: 1\n", encoding="utf-8")

    with pytest.raises(AgentConfigError, match=re.escape(str(path))):
        load_agent_config(path)


@pytest.mark.parametrize(
    ("proxy", "token_url"),
    [
        ("proxy.test:8899", "http://proxy.test:8899/access-token"),
        ("https://proxy.test/", "https://proxy.test/access-token"),
        (None, "http://localhost:8899/access-token"),
    ],
    ids=["host-and-port", "with-scheme", "unset"],
)
def test_the_token_url_derives_from_the_api_proxy(proxy: str | None, token_url: str) -> None:
    assert make_settings(domino_api_proxy=proxy).token_url == token_url


def test_settings_say_whether_the_agent_runs_in_domino() -> None:
    assert make_settings(domino_api_host="http://nucleus.test").in_domino
    assert not make_settings().in_domino


def test_tools_are_deterministic_for_a_seeded_random() -> None:
    first = [pick_line(SCIENCE_LINES, random.Random(3)) for _ in range(3)]
    second = [pick_line(SCIENCE_LINES, random.Random(3)) for _ in range(3)]

    assert first == second


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("question", "tool", "lines"),
    [
        ("How dense is a planet?", "science_line", SCIENCE_LINES),
        ("What is the capital gains tax rate?", "philosophy_line", PHILOSOPHY_LINES),
    ],
    ids=["science-question", "anything-else"],
)
async def test_ask_routes_the_question_to_one_tool_and_returns_the_contract_keys(
    config: AgentConfig, question: str, tool: str, lines: tuple[str, ...]
) -> None:
    agent = build_agent(scripted_model(), config, rng=random.Random(1))
    ask = make_ask(agent, config)

    answer = await ask(question)

    assert set(answer) == {"answer", "tools"}
    assert answer["tools"] == [tool]
    assert answer["answer"] in lines


@pytest.mark.anyio
async def test_a_model_that_keeps_calling_tools_trips_the_request_limit(
    config: AgentConfig,
) -> None:
    ask = make_ask(build_agent(looping_model(), config, rng=random.Random(1)), config)

    with pytest.raises(UsageLimitExceeded):
        await ask("Tell me about atoms")


def test_temperature_and_max_tokens_reach_the_model_settings(config: AgentConfig) -> None:
    assert build_model_settings(config) == {"temperature": 0.3, "max_tokens": 256}


@pytest.mark.anyio
async def test_the_prompt_and_model_settings_reach_the_model(config: AgentConfig) -> None:
    seen: list[tuple[list[ModelMessage], AgentInfo]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append((list(messages), info))
        return ModelResponse(parts=[TextPart(content="a line")])

    agent = build_agent(FunctionModel(respond), config, rng=random.Random(1))
    await make_ask(agent, config)("Anything")

    [(messages, info)] = seen
    request = messages[-1]
    assert isinstance(request, ModelRequest)
    assert request.instructions == "Answer with one line."
    assert info.model_settings is not None
    assert info.model_settings.get("temperature") == 0.3
    assert info.model_settings.get("max_tokens") == 256
    assert sorted(tool.name for tool in info.function_tools) == ["philosophy_line", "science_line"]


def _turn(question: str) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=question)]),
        ModelResponse(parts=[ToolCallPart(tool_name="science_line", args={}, tool_call_id="c")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="science_line", content="line", tool_call_id="c")]
        ),
        ModelResponse(parts=[TextPart(content="line")]),
    ]


def test_max_history_trims_a_conversation_at_a_user_turn() -> None:
    first, second = _turn("first"), _turn("second")

    kept = trim_history(first + second, 6)

    assert kept == second


def test_a_zero_max_history_keeps_no_message() -> None:
    assert trim_history(_turn("first"), 0) == []

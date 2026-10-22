"""The agent on a scripted model and its wiring.

Tool routing, run limits, the trace contract and the config keys; then the
settings, the model builder per provider, the tracer choice and the JSON logs.
"""

import json
import logging
import random
import re
from collections.abc import Iterator
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
    tool_names,
)
from app.domino_token import DominoTokenAuth
from app.llm import ModelSetupError, build_model
from app.logs import StdoutHandler, configure_logging
from app.main import build_runtime
from app.settings import AgentConfig, AgentConfigError, load_agent_config
from app.tracing import SDK_PACKAGE, DominoTracer, NoOpTracer, select_tracer
from tests.fakes import (
    SHIPPED_CONFIG,
    FakeTokenProvider,
    looping_model,
    make_settings,
    scripted_model,
)

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
    assert make_settings(domino_api_proxy=proxy).access_token_url == token_url


def test_an_explicit_token_url_wins_over_the_api_proxy() -> None:
    settings = make_settings(
        domino_api_proxy="proxy.test:8899", token_url="https://tokens.example.com/access-token"
    )

    assert settings.access_token_url == "https://tokens.example.com/access-token"


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


def test_tool_names_lists_each_called_tool_once_in_call_order() -> None:
    def call(tool: str) -> ToolCallPart:
        return ToolCallPart(tool_name=tool, args={})

    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="q")]),
        ModelResponse(parts=[call("philosophy_line"), call("science_line")]),
        ModelResponse(parts=[TextPart(content="a"), call("philosophy_line")]),
    ]

    assert tool_names(messages) == ["philosophy_line", "science_line"]


ENDPOINT_URL = "https://models.example.com/v1"


@pytest.fixture
def endpoint_config_path(tmp_path: Path) -> Path:
    """An agent config whose model is a Domino-hosted endpoint."""
    path = tmp_path / "agent_config.yaml"
    yaml_text = CONFIG_YAML.replace("provider: openai", "provider: domino-endpoint")
    path.write_text(yaml_text, encoding="utf-8")
    return path


def test_the_openai_provider_without_a_key_fails_naming_the_variable(config: AgentConfig) -> None:
    with pytest.raises(ModelSetupError, match="OPENAI_API_KEY"):
        build_model(config, make_settings(openai_api_key=None))


def test_the_domino_endpoint_without_a_base_url_fails_naming_the_variable(
    endpoint_config_path: Path,
) -> None:
    settings = make_settings(endpoint_config_path, domino_api_host="http://nucleus.test")

    with pytest.raises(ModelSetupError, match="SIMPLE_AGENT_ENDPOINT_BASE_URL"):
        build_runtime(settings)


def test_the_domino_endpoint_outside_domino_needs_an_injected_token_provider(
    endpoint_config_path: Path,
) -> None:
    settings = make_settings(endpoint_config_path, endpoint_base_url=ENDPOINT_URL)

    with pytest.raises(ModelSetupError, match="DOMINO_API_HOST"):
        build_runtime(settings)


@pytest.mark.anyio
async def test_the_domino_endpoint_model_client_carries_the_token_auth_flow(
    endpoint_config_path: Path,
) -> None:
    settings = make_settings(endpoint_config_path, endpoint_base_url=ENDPOINT_URL)
    config = load_agent_config(endpoint_config_path)

    chat = build_model(config, settings, token_provider=FakeTokenProvider())

    [model_client] = chat.clients
    assert isinstance(model_client.auth, DominoTokenAuth)
    assert str(chat.model.base_url).startswith(ENDPOINT_URL)
    await model_client.aclose()


@pytest.mark.anyio
async def test_inside_domino_the_runtime_reads_the_run_token_endpoint(
    endpoint_config_path: Path,
) -> None:
    settings = make_settings(
        endpoint_config_path, endpoint_base_url=ENDPOINT_URL, domino_api_host="http://nucleus.test"
    )

    runtime = build_runtime(settings)

    model_client, token_client = runtime.clients
    assert isinstance(model_client.auth, DominoTokenAuth)
    assert token_client.auth is None
    await runtime.aclose()


@pytest.mark.parametrize("sdk_installed", [True, False], ids=["sdk-installed", "no-sdk"])
def test_outside_domino_tracing_is_off_with_one_warning(
    sdk_installed: bool, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.tracing")

    tracer = select_tracer(make_settings(), sdk_available=lambda: sdk_installed)

    assert isinstance(tracer, NoOpTracer)
    assert len([record for record in caplog.records if record.name == "app.tracing"]) == 1


def test_inside_domino_a_missing_sdk_fails_at_startup_naming_the_package() -> None:
    settings = make_settings(domino_api_host="http://nucleus.test")

    with pytest.raises(RuntimeError, match=re.escape(SDK_PACKAGE)):
        select_tracer(settings, sdk_available=lambda: False)


def test_inside_domino_the_sdk_traces() -> None:
    settings = make_settings(domino_api_host="http://nucleus.test")

    assert isinstance(select_tracer(settings, sdk_available=lambda: True), DominoTracer)


def test_the_no_op_tracer_leaves_the_function_unchanged_and_opens_a_null_run(
    tmp_path: Path,
) -> None:
    def ask(question: str) -> str:
        return question

    tracer = NoOpTracer()

    assert tracer.trace("ask_agent")(ask) is ask
    with tracer.evaluation_run(tmp_path / "agent_config.yaml", "experiment") as run:
        assert run is None


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    """The root logger, with its handlers and level restored after the test."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


def test_logs_are_one_json_line_per_record_with_the_extra_fields(
    root_logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")
    log = logging.getLogger("tests.logs")

    log.info("case scored", extra={"case_id": "7", "tools": ["science_line"]})
    log.debug("below the level")

    [line] = capsys.readouterr().out.splitlines()
    entry = json.loads(line)
    assert (entry["level"], entry["logger"], entry["message"]) == (
        "INFO",
        "tests.logs",
        "case scored",
    )
    assert (entry["case_id"], entry["tools"]) == ("7", ["science_line"])
    assert "time" in entry


def test_a_logged_exception_carries_its_traceback(
    root_logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")

    try:
        raise ValueError("bad row")
    except ValueError:
        logging.getLogger("tests.logs").exception("case failed")

    entry = json.loads(capsys.readouterr().out)
    assert "ValueError: bad row" in entry["exception"]


def test_configuring_logging_again_replaces_only_its_own_handler(
    root_logger: logging.Logger,
) -> None:
    other = logging.NullHandler()
    root_logger.addHandler(other)

    configure_logging("INFO")
    configure_logging("WARNING")

    assert len([h for h in root_logger.handlers if isinstance(h, StdoutHandler)]) == 1
    assert other in root_logger.handlers
    assert root_logger.level == logging.WARNING

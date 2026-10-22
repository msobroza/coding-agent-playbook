"""The App over HTTP: the chat route, its error table, the docs, CORS and the A2A sub-app."""

import contextlib
import random
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import FunctionModel

from app.agent import PHILOSOPHY_LINES, SCIENCE_LINES
from app.chat import MAX_MESSAGE_CHARS
from app.main import create_app
from tests.fakes import (
    FakeTokenProvider,
    RecordingTracer,
    failing_model,
    make_settings,
    slow_model,
)

#: The A2A states that end a task or hand it back to the caller.
FINAL_STATES = frozenset(
    {"completed", "failed", "canceled", "rejected", "input-required", "auth-required"}
)


@contextlib.contextmanager
def client_for(model: FunctionModel, **overrides: Any) -> Iterator[TestClient]:
    """A live client on an app with ``model`` and settings ``overrides``."""
    app = create_app(
        make_settings(**overrides),
        model=model,
        token_provider=FakeTokenProvider(),
        tracer=RecordingTracer(),
        rng=random.Random(7),
    )
    with TestClient(app) as client:
        yield client


def test_chat_answers_with_the_line_of_the_scripted_tool(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "How far is the nearest star?"})

    assert response.status_code == 200
    assert response.json()["response"] in SCIENCE_LINES
    assert set(response.json()) == {"response"}


def test_the_request_span_records_the_question_as_its_only_input(
    client: TestClient, tracer: RecordingTracer
) -> None:
    client.post("/chat", json={"message": "Why do we exist?"})

    assert tracer.inputs("ask_agent") == [{"question": "Why do we exist?"}]
    [span] = tracer.spans
    assert span.outputs["tools"] == ["philosophy_line"]
    assert span.outputs["answer"] in PHILOSOPHY_LINES


@pytest.mark.parametrize(
    "body",
    [
        {"message": "x" * (MAX_MESSAGE_CHARS + 1)},
        {"message": ""},
        {"message": "Hi", "conversation_id": "abc"},
    ],
    ids=["too-long", "empty", "extra-field"],
)
def test_a_bad_body_is_422(client: TestClient, body: dict[str, str]) -> None:
    assert client.post("/chat", json=body).status_code == 422


def test_a_model_http_error_is_502_without_its_text() -> None:
    error = ModelHTTPError(status_code=503, model_name="chat-model", body="internal detail")
    with client_for(failing_model(error)) as client:
        response = client.post("/chat", json={"message": "Hi"})

    assert response.status_code == 502
    assert response.json() == {"detail": "The model provider failed; try again later."}
    assert "internal detail" not in response.text


def test_a_run_past_its_deadline_is_504(tmp_path_factory: pytest.TempPathFactory) -> None:
    config = tmp_path_factory.mktemp("config") / "agent_config.yaml"
    shipped = make_settings().config_path.read_text(encoding="utf-8")
    config.write_text(shipped.replace("timeout_seconds: 120", "timeout_seconds: 0.05"), "utf-8")

    with client_for(slow_model(2.0), config_path=config) as client:
        response = client.post("/chat", json={"message": "Hi"})

    assert response.status_code == 504
    assert response.json() == {"detail": "The agent took too long to answer."}


def test_health_is_200(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_the_docs_load_the_schema_by_a_relative_url(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "'openapi.json'" in response.text
    assert "'/openapi.json'" not in response.text


def test_an_origin_outside_the_allow_list_gets_no_cors_headers() -> None:
    origins = ["https://ui.example.com"]
    with client_for(failing_model(RuntimeError()), cors_origins=origins) as client:
        allowed = client.get("/health", headers={"Origin": "https://ui.example.com"})
        other = client.get("/health", headers={"Origin": "https://other.example.org"})

    assert allowed.headers["access-control-allow-origin"] == "https://ui.example.com"
    assert "access-control-allow-origin" not in other.headers


def test_the_agent_card_publishes_the_app_url_plus_a2a(client: TestClient) -> None:
    card = client.get("/a2a/.well-known/agent-card.json").json()

    assert card["url"] == "https://agents.example.com/apps/simple-agent/a2a"
    assert {skill["id"] for skill in card["skills"]} == {"science_line", "philosophy_line"}
    assert card["version"] == "1.0.0"


def _rpc(client: TestClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """One JSON-RPC call to the A2A app; ``Any``: the reply is untyped JSON."""
    payload = {"jsonrpc": "2.0", "id": method, "method": method, "params": params}
    response = client.post("/a2a/", json=payload)
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    assert "error" not in body, body
    return body


def test_an_a2a_task_completes_before_a_deadline(client: TestClient) -> None:
    message = {
        "role": "user",
        "kind": "message",
        "messageId": "m-1",
        "parts": [{"kind": "text", "text": "What is the mass of a planet?"}],
    }
    sent = _rpc(client, "message/send", {"message": message})
    task_id = str(sent["result"]["id"])

    deadline, delay, state = time.monotonic() + 10.0, 0.05, "submitted"
    while time.monotonic() < deadline:
        task = _rpc(client, "tasks/get", {"id": task_id})["result"]
        state = str(task["status"]["state"])
        if state in FINAL_STATES:
            break
        time.sleep(delay)
        delay = min(delay * 2, 1.0)

    assert state == "completed"

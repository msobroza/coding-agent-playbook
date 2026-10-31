"""The ``llm`` judge on an OpenAI-API endpoint (``evals.api_judge``): hermetic, no key.

Logic tests inject :class:`FakeJsonPost`; the transport tests run the real
``urllib`` path against :class:`FakeOpenAIServer` on ``127.0.0.1``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.api_judge import (
    ApiJudge,
    answer_text,
    build_api_judge,
    grading_request,
    post_json,
)
from coding_agent_playbook.evals.endpoints import Endpoint, EndpointError
from coding_agent_playbook.evals.judge import JudgeError
from tests.evals.openai_api_fakes import (
    FakeJsonPost,
    FakeOpenAIServer,
    chat_payload,
    responses_payload,
    serving,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_TOKEN = "sk-fake-judge-token-0000"
_RESPONSES = Endpoint("openai", "openai-responses", "https://api.example/v1", token_env="OAI")
_CHAT = Endpoint("router", "openai-chat", "https://router.example/api/v1/", token_env="OAI")
#: An extra header's secret value; its quotes make the JSON-escaped form differ.
_HEADER_SECRET = 'org-"key"-0000'


@pytest.fixture
def server() -> Iterator[FakeOpenAIServer]:
    with serving(FakeOpenAIServer()) as running:
        yield running


def _judge(post: FakeJsonPost, endpoint: Endpoint = _RESPONSES, **kwargs: Any) -> ApiJudge:
    return ApiJudge(endpoint=endpoint, model="gpt-x", token=_TOKEN, post=post, **kwargs)


# --------------------------------------------------------------------------- #
# Request and answer shapes
# --------------------------------------------------------------------------- #


def test_a_responses_request_asks_not_to_store_and_sets_no_output_cap() -> None:
    url, body = grading_request(_RESPONSES, "gpt-x", "grade this")

    assert url == "https://api.example/v1/responses"
    assert body == {"model": "gpt-x", "input": "grade this", "store": False}


def test_a_chat_request_sends_one_user_message() -> None:
    url, body = grading_request(_CHAT, "gpt-x", "grade this")

    assert url == "https://router.example/api/v1/chat/completions"
    assert body == {"model": "gpt-x", "messages": [{"role": "user", "content": "grade this"}]}


@pytest.mark.parametrize(
    ("endpoint", "key"), [(_RESPONSES, "max_output_tokens"), (_CHAT, "max_tokens")]
)
def test_an_endpoint_output_cap_is_sent(endpoint: Endpoint, key: str) -> None:
    capped = Endpoint(endpoint.name, endpoint.api, endpoint.base_url, max_output_tokens=64)

    assert grading_request(capped, "gpt-x", "p")[1][key] == 64


def test_a_reasoning_effort_is_sent_as_each_api_names_it() -> None:
    responses = grading_request(_RESPONSES, "gpt-x", "p", reasoning_effort="high")[1]
    chat = grading_request(_CHAT, "gpt-x", "p", reasoning_effort="high")[1]

    assert responses["reasoning"] == {"effort": "high"}
    assert chat["reasoning_effort"] == "high"


def test_the_judge_sends_its_reasoning_effort_with_every_grading() -> None:
    post = FakeJsonPost([responses_payload("0.5")])
    _judge(post, reasoning_effort="high").score_criterion("ok?", "artifact")

    assert post.calls[0][2]["reasoning"] == {"effort": "high"}


def test_a_responses_answer_skips_reasoning_items() -> None:
    assert answer_text("openai-responses", responses_payload("0.75")) == "0.75"


def test_a_chat_answer_is_the_first_choice() -> None:
    assert answer_text("openai-chat", chat_payload("0.5")) == "0.5"


@pytest.mark.parametrize(
    ("api", "payload", "message"),
    [
        ("openai-responses", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "response incomplete"),
        ("openai-responses", {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}, "refused: no"),
        ("openai-responses", {"status": "completed", "output": []}, "no output text"),
        ("openai-chat", {"choices": []}, "no choices"),
        ("openai-chat", {"choices": [{"message": {"refusal": "no"}}]}, "refused: no"),
        ("openai-chat", {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}, "finish_reason 'length'"),
    ],
)  # fmt: skip
def test_a_payload_without_an_answer_is_a_judge_error(
    api: str, payload: dict[str, Any], message: str
) -> None:
    with pytest.raises(JudgeError, match=message):
        answer_text(api, payload)


# --------------------------------------------------------------------------- #
# Grading, averaging and retries
# --------------------------------------------------------------------------- #


def test_a_grading_posts_the_prompt_with_the_token_as_a_bearer_header() -> None:
    post = FakeJsonPost([responses_payload("0.75")])
    judge = _judge(post, headers={"X-Team": "evals"})

    assert judge.score_criterion("Names the bug.", "the artifact") == 0.75
    url, headers, body, timeout = post.calls[0]
    assert url == "https://api.example/v1/responses"
    assert headers == {"X-Team": "evals", "Authorization": f"Bearer {_TOKEN}"}
    assert "Criterion: Names the bug." in body["input"]
    assert "the artifact" in body["input"]
    assert timeout == 120.0


def test_n_samples_are_averaged() -> None:
    post = FakeJsonPost([chat_payload("1"), chat_payload("0"), chat_payload("0.5")])

    assert _judge(post, _CHAT).score_criterion("c", "a", n=3) == 0.5
    assert len(post.calls) == 3


def test_a_failed_request_is_retried_then_scored() -> None:
    post = FakeJsonPost([JudgeError("HTTP 503: busy"), responses_payload("Score: 0.8")])

    assert _judge(post).score_criterion("c", "a") == 0.8
    assert len(post.calls) == 2


def test_an_off_format_answer_is_retried_then_reported() -> None:
    post = FakeJsonPost([responses_payload("The score is high.")])

    with pytest.raises(JudgeError, match=r"after 3 attempt\(s\): answered off-format"):
        _judge(post).score_criterion("c", "a")
    assert len(post.calls) == 3


def test_a_judge_error_names_the_model_and_endpoint_but_never_the_token() -> None:
    post = FakeJsonPost([JudgeError(f"HTTP 401: bad key {_TOKEN}")])

    with pytest.raises(JudgeError) as caught:
        _judge(post, retries=0).score_criterion("c", "a")

    message = str(caught.value)
    assert "judge 'gpt-x' on endpoint 'openai' gave no score after 1 attempt(s)" in message
    assert "[redacted]" in message
    assert _TOKEN not in message
    assert caught.value.__cause__ is None or _TOKEN not in str(caught.value.__cause__)


@pytest.mark.parametrize(
    "echoed", [_HEADER_SECRET, json.dumps(_HEADER_SECRET)], ids=["as-written", "json-escaped"]
)
def test_a_judge_error_never_carries_an_extra_header_value(echoed: str) -> None:
    post = FakeJsonPost([JudgeError(f"HTTP 400: unknown header X-Org-Key: {echoed}")])

    with pytest.raises(JudgeError) as caught:
        _judge(post, retries=0, headers={"X-Org-Key": _HEADER_SECRET}).score_criterion("c", "a")

    message = str(caught.value)
    assert "[redacted]" in message
    assert "org-" not in message


def test_an_off_format_answer_never_carries_an_extra_header_value() -> None:
    post = FakeJsonPost([responses_payload(f"The header was {_HEADER_SECRET}.")])

    with pytest.raises(JudgeError, match="answered off-format") as caught:
        _judge(post, retries=0, headers={"X-Org-Key": _HEADER_SECRET}).score_criterion("c", "a")

    assert "org-" not in str(caught.value)


def test_a_secret_with_a_run_of_whitespace_is_redacted_before_the_excerpt_collapses_it() -> None:
    spaced = "org  key-1234"
    failed = {"status": "failed", "error": {"message": f"bad header {spaced}"}}
    post = FakeJsonPost([failed])

    with pytest.raises(JudgeError, match="response failed") as caught:
        _judge(post, retries=0, headers={"X-Org-Key": spaced}).score_criterion("c", "a")

    assert "key-1234" not in str(caught.value)


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        (Endpoint("a", "anthropic", "https://x"), "speaks api = openai-responses or openai-chat"),
        (Endpoint("f", "openai-chat", "file:///etc/passwd"), "needs an http\\(s\\) base_url"),
    ],
)
def test_a_judge_refuses_an_endpoint_it_cannot_reach(endpoint: Endpoint, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _judge(FakeJsonPost([chat_payload("1")]), endpoint)


def test_negative_retries_are_refused() -> None:
    with pytest.raises(ValueError, match="retries must be >= 0, got -1"):
        _judge(FakeJsonPost([chat_payload("1")]), retries=-1)


def test_the_api_judge_has_no_cli_to_probe() -> None:
    assert ApiJudge.cli is None
    assert ApiJudge.name == "llm"


# --------------------------------------------------------------------------- #
# The real transport, against a local server
# --------------------------------------------------------------------------- #


def test_post_json_returns_the_response_object(server: FakeOpenAIServer) -> None:
    payload = post_json(
        f"{server.base_url}/responses", {"Authorization": "Bearer t"}, {"a": 1}, 5.0
    )

    assert payload == responses_payload("1")
    request = server.requests[0]
    assert (request.path, request.body) == ("/v1/responses", {"a": 1})
    assert request.headers["Authorization"] == "Bearer t"
    assert request.headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ((500, b'{"error": "boom"}'), r"HTTP 500: .*boom"),
        ((200, b"not json"), "answered with no JSON: not json"),
        ((200, b"[1, 2]"), "JSON that is not an object"),
    ],
)
def test_post_json_turns_a_bad_reply_into_a_judge_error(
    server: FakeOpenAIServer, reply: tuple[int, bytes], message: str
) -> None:
    server.replies.append(reply)

    with pytest.raises(JudgeError, match=message):
        post_json(f"{server.base_url}/chat/completions", {}, {}, 5.0)


def test_post_json_times_out(server: FakeOpenAIServer) -> None:
    server.delay = 1.0

    with pytest.raises(JudgeError, match="request failed"):
        post_json(f"{server.base_url}/responses", {}, {}, 0.1)


def test_post_json_reports_an_unreachable_server() -> None:
    with pytest.raises(JudgeError, match="request failed"):
        post_json("http://127.0.0.1:9/v1/responses", {}, {}, 2.0)


def test_an_api_judge_grades_end_to_end_over_http(server: FakeOpenAIServer) -> None:
    server.answer = "**Score:** 0.9"
    endpoint = Endpoint("local", "openai-responses", server.base_url, token_env="OAI")

    judge = build_api_judge(endpoint, "gpt-x", {"OAI": _TOKEN})

    assert judge.score_criterion("c", "a") == 0.9
    request = server.requests[0]
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.body["store"] is False
    assert json.dumps(request.body).count("Criterion: c") == 1


def test_an_http_error_echoing_a_headers_env_value_never_reaches_the_judge_error(
    server: FakeOpenAIServer,
) -> None:
    """Regression: the API judge redacted only its token, not ``headers_env`` values."""
    server.replies.extend([(401, b'{"error": "bad header X-Org-Key: org-key-1234"}')] * 3)
    endpoint = Endpoint("local", "openai-chat", server.base_url, token_env="OAI", headers_env="H")
    judge = build_api_judge(endpoint, "gpt-x", {"OAI": _TOKEN, "H": "X-Org-Key: org-key-1234"})

    with pytest.raises(JudgeError, match="HTTP 401") as caught:
        judge.score_criterion("c", "a")

    assert "org-key-1234" not in str(caught.value)
    assert server.requests[0].headers["X-Org-Key"] == "org-key-1234"


def test_a_secret_cut_by_the_excerpt_window_is_still_redacted(server: FakeOpenAIServer) -> None:
    """Regression: the error excerpt was taken before redaction, so a cut token's tail leaked."""
    secret = "sk-live-0123456789abcdefghijklmnopqrstuv"
    # The excerpt keeps the last 200 characters; this tail puts its cut inside the token.
    server.replies.append((401, f"invalid key {secret} {'x' * 180}".encode()))
    endpoint = Endpoint("local", "openai-chat", server.base_url, token_env="OAI")
    judge = ApiJudge(endpoint=endpoint, model="gpt-x", token=secret, retries=0)

    with pytest.raises(JudgeError, match="HTTP 401") as caught:
        judge.score_criterion("c", "a")

    assert secret[-12:] not in str(caught.value)


def test_a_token_that_is_not_valid_http_fails_without_quoting_it() -> None:
    """Regression: http.client's ValueError escaped the judge, quoting ``Bearer <token>``."""
    endpoint = Endpoint("local", "openai-chat", "http://127.0.0.1:9/v1", token_env="OAI")
    judge = ApiJudge(endpoint=endpoint, model="gpt-x", token="sk-one\nsk-two", retries=0)

    with pytest.raises(JudgeError, match="not valid HTTP") as caught:
        judge.score_criterion("c", "a")

    assert "sk-one" not in str(caught.value)
    assert "sk-two" not in str(caught.value)


# --------------------------------------------------------------------------- #
# Building the judge from an endpoint
# --------------------------------------------------------------------------- #


def test_build_api_judge_reads_the_token_and_extra_headers_now() -> None:
    endpoint = Endpoint(
        "openai", "openai-responses", "https://x/v1", token_env="OAI", headers_env="H"
    )

    judge = build_api_judge(endpoint, "gpt-x", {"OAI": _TOKEN, "H": "X-Team: evals\nX-Env: ci"})

    assert judge.model == "gpt-x"
    assert judge._headers == {
        "X-Team": "evals",
        "X-Env": "ci",
        "Authorization": f"Bearer {_TOKEN}",
    }


def test_build_api_judge_refuses_a_missing_token_before_any_call() -> None:
    with pytest.raises(EndpointError, match="OAI is unset or empty"):
        build_api_judge(_RESPONSES, "gpt-x", {})

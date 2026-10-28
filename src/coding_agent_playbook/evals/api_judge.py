"""The ``llm`` judge on an OpenAI-API endpoint: it grades over HTTPS, without the ``claude`` CLI.

:class:`~coding_agent_playbook.evals.judge.LLMJudge` drives the ``claude`` CLI,
which speaks only the Anthropic Messages API. When ``[evals.judge] endpoint``
names an ``openai-responses`` or ``openai-chat`` endpoint, ``build_judge``
builds an :class:`ApiJudge` instead: the same grading prompt, the same strict
answer parsing (:func:`~coding_agent_playbook.evals.judge.parse_score`), the
same sample averaging and the same bounded immediate retries, sent straight to
``<base_url>/responses`` or ``<base_url>/chat/completions`` with the standard
library. It has no CLI, so it reads no personal settings, and a record probes
no judge CLI version for it.

A request that fails (an HTTP error, a timeout, a body that is not a JSON
object, a refusal, an incomplete or empty answer, or an answer that is not one
number in ``[0, 1]``) raises :class:`~coding_agent_playbook.evals.judge.JudgeError`
after its retries. No error message carries the endpoint's token.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Final, Protocol

from coding_agent_playbook.evals.endpoints import (
    API_OPENAI_CHAT,
    API_OPENAI_RESPONSES,
    Endpoint,
    parse_header_lines,
    resolve_endpoint_headers,
    resolve_endpoint_token,
)
from coding_agent_playbook.evals.judge import (
    GRADING_PROMPT,
    Judge,
    JudgeError,
    grade_with_retries,
    parse_score,
)
from coding_agent_playbook.evals.run.secret_redaction import redact_secrets

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The endpoint APIs :class:`ApiJudge` speaks; ``anthropic`` stays with the CLI judge.
API_JUDGE_APIS: Final = (API_OPENAI_RESPONSES, API_OPENAI_CHAT)

#: Wall-clock bound (seconds) on one grading request, as for the CLI judge.
_DEFAULT_TIMEOUT: Final = 120.0

#: Extra attempts after a failed grading request (3 attempts in all), as for the CLI judge.
_DEFAULT_RETRIES: Final = 2

#: How much of a failed response to quote in a :class:`JudgeError`.
_EXCERPT_CHARS: Final = 200

#: The URL schemes a judge endpoint may use: never ``file:`` or another opener urllib knows.
_URL_SCHEMES: Final = ("https://", "http://")

type JsonObject = dict[str, Any]


class JsonPost(Protocol):
    """Sends one JSON ``POST`` and returns the decoded JSON object, or raises :class:`JudgeError`."""

    def __call__(
        self, url: str, headers: Mapping[str, str], body: JsonObject, timeout: float
    ) -> JsonObject: ...


def post_json(url: str, headers: Mapping[str, str], body: JsonObject, timeout: float) -> JsonObject:
    """POST ``body`` as JSON to ``url``; the response's JSON object, or :class:`JudgeError` saying why not.

    Example::

        post_json("https://api.openai.com/v1/responses", {"Authorization": "Bearer t"},
                  {"model": "gpt-6.1-terra", "input": "..."}, 120.0)  # {"output": [...], ...}
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise JudgeError(f"HTTP {exc.code}: {_excerpt(_error_body(exc))}") from exc
    except (urllib.error.URLError, OSError) as exc:  # TimeoutError is an OSError
        raise JudgeError(f"request failed: {exc}") from exc
    return _json_object(raw)


def _error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except OSError:
        return str(exc.reason)


def _json_object(raw: bytes) -> JsonObject:
    try:
        payload = json.loads(raw)
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        text = raw.decode("utf-8", errors="replace")
        raise JudgeError(f"answered with no JSON: {_excerpt(text)}") from exc
    if not isinstance(payload, dict):
        raise JudgeError(f"answered with JSON that is not an object: {_excerpt(str(payload))}")
    return payload


def grading_request(
    endpoint: Endpoint, model: str, prompt: str, *, reasoning_effort: str | None = None
) -> tuple[str, JsonObject]:
    """The URL and JSON body that ask ``endpoint`` to answer ``prompt`` with ``model``.

    ``openai-responses`` asks not to store the response (``store: false``): the
    artifact under grading is the eval's, not the provider's. ``max_output_tokens``
    is sent only when the endpoint sets it, so a reasoning model is never cut short.
    ``reasoning_effort`` (``[evals.judge]``) is sent only when set, as each API names it.

    Example::

        >>> grading_request(Endpoint("o", "openai-chat", "https://x/v1/"), "m", "p")[0]
        'https://x/v1/chat/completions'
    """
    base = endpoint.base_url.rstrip("/")
    limit = endpoint.max_output_tokens
    if endpoint.api == API_OPENAI_RESPONSES:
        body: JsonObject = {"model": model, "input": prompt, "store": False}
        if limit is not None:
            body["max_output_tokens"] = limit
        if reasoning_effort is not None:
            body["reasoning"] = {"effort": reasoning_effort}
        return f"{base}/responses", body
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if limit is not None:
        body["max_tokens"] = limit
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    return f"{base}/chat/completions", body


def answer_text(api: str, payload: JsonObject) -> str:
    """The text answer in an ``api`` response ``payload``; :class:`JudgeError` when there is none.

    Example::

        >>> answer_text("openai-chat", {"choices": [{"message": {"content": "0.5"}}]})
        '0.5'
    """
    if api == API_OPENAI_RESPONSES:
        return _responses_text(payload)
    return _chat_text(payload)


def _responses_text(payload: JsonObject) -> str:
    """The ``output_text`` parts of a Responses API payload's messages, joined."""
    status = payload.get("status")
    if status not in (None, "completed"):
        reason = payload.get("incomplete_details") or payload.get("error")
        raise JudgeError(f"response {status}: {_excerpt(json.dumps(reason))}")
    parts = _message_parts(payload)
    refusals = [str(part.get("refusal")) for part in parts if part.get("type") == "refusal"]
    if refusals:
        raise JudgeError(f"refused: {_excerpt(refusals[0])}")
    texts = [part["text"] for part in parts if _is_output_text(part)]
    if not texts:
        raise JudgeError(f"answered with no output text: {_excerpt(json.dumps(payload))}")
    return "".join(texts)


def _message_parts(payload: JsonObject) -> list[JsonObject]:
    """The content parts of every ``message`` item in a Responses API ``output``."""
    items = payload.get("output")
    messages = [i for i in items if _is_message(i)] if isinstance(items, list) else []
    return [
        part for item in messages for part in item.get("content") or [] if isinstance(part, dict)
    ]


def _is_message(item: object) -> bool:
    return isinstance(item, dict) and item.get("type") == "message"


def _is_output_text(part: JsonObject) -> bool:
    return part.get("type") == "output_text" and isinstance(part.get("text"), str)


def _chat_text(payload: JsonObject) -> str:
    """The first choice's message content in a Chat Completions payload."""
    choices = payload.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    if not isinstance(first, dict):
        raise JudgeError(f"answered with no choices: {_excerpt(json.dumps(payload))}")
    given = first.get("message")
    message: JsonObject = given if isinstance(given, dict) else {}
    if message.get("refusal"):
        raise JudgeError(f"refused: {_excerpt(str(message['refusal']))}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        reason = first.get("finish_reason")
        raise JudgeError(f"answered with no message content (finish_reason {reason!r})")
    return content


def _excerpt(text: str) -> str:
    """The last :data:`_EXCERPT_CHARS` of ``text``, whitespace-collapsed."""
    return " ".join(text.split())[-_EXCERPT_CHARS:]


class ApiJudge(Judge):
    """The ``llm`` judge on an ``openai-responses`` or ``openai-chat`` endpoint.

    The token goes in an ``Authorization: Bearer`` header, beside any extra
    ``headers``; ``post`` sends each request (:func:`post_json`, a named fake in
    tests). Every failed request is retried immediately up to ``retries`` times.

    Example::

        judge = ApiJudge(endpoint=openai, model="gpt-6.1-terra", token=key)
        judge.score_criterion("The review approves.", transcript, n=3)  # 0.0-1.0
    """

    name = "llm"
    accepts_model = True
    accepts_endpoint = True
    cli = None

    def __init__(
        self,
        *,
        endpoint: Endpoint,
        model: str,
        token: str,
        headers: Mapping[str, str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        retries: int = _DEFAULT_RETRIES,
        post: JsonPost = post_json,
        reasoning_effort: str | None = None,
    ) -> None:
        _check_endpoint(endpoint)
        if retries < 0:
            raise ValueError(f"ApiJudge retries must be >= 0, got {retries}")
        self.endpoint = endpoint
        self.model = model
        self._token = token
        self._headers = {**(headers or {}), "Authorization": f"Bearer {token}"}
        self._timeout = timeout
        self._retries = retries
        self._post = post
        self.reasoning_effort = reasoning_effort

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        """Average ``n`` independent gradings of ``criterion`` over ``artifact``."""
        samples = max(1, n)
        return sum(self._grade_once(criterion, artifact) for _ in range(samples)) / samples

    def _grade_once(self, criterion: str, artifact: Any) -> float:
        prompt = GRADING_PROMPT.format(criterion=criterion, artifact=str(artifact))
        url, body = grading_request(
            self.endpoint, self.model, prompt, reasoning_effort=self.reasoning_effort
        )
        who = f"judge {self.model!r} on endpoint {self.endpoint.name!r}"
        return grade_with_retries(lambda: self._attempt(url, body), self._retries + 1, who)

    def _attempt(self, url: str, body: JsonObject) -> float:
        """Send one request; its score, or :class:`JudgeError` saying why not (token redacted)."""
        try:
            text = answer_text(
                self.endpoint.api, self._post(url, self._headers, body, self._timeout)
            )
        except JudgeError as exc:
            # A fresh error, not a chained one: the original message may echo the token.
            raise JudgeError(redact_secrets(str(exc), [self._token])) from None
        score = parse_score(text)
        if score is None:
            answer = redact_secrets(_excerpt(text), [self._token])
            raise JudgeError(f"answered off-format (want one number in [0, 1]): {answer!r}")
        return score


def _check_endpoint(endpoint: Endpoint) -> None:
    if endpoint.api not in API_JUDGE_APIS:
        raise ValueError(
            f"ApiJudge speaks api = {' or '.join(API_JUDGE_APIS)}, but endpoint "
            f"{endpoint.name!r} has api = {endpoint.api!r}"
        )
    if not endpoint.base_url.startswith(_URL_SCHEMES):
        raise ValueError(
            f"endpoint {endpoint.name!r}: the judge needs an http(s) base_url, "
            f"got {endpoint.base_url!r}"
        )


def build_api_judge(
    endpoint: Endpoint, model: str, env: Mapping[str, str], *, reasoning_effort: str | None = None
) -> ApiJudge:
    """The ``llm`` judge on ``endpoint``, its token and extra headers read from ``env`` now.

    A missing token raises :class:`~coding_agent_playbook.evals.endpoints.EndpointError`
    (exit 2) before any paid call, as an endpoint target's route does.

    Example::

        build_api_judge(openai, "gpt-6.1-terra", os.environ).model  # "gpt-6.1-terra"
    """
    token = resolve_endpoint_token(endpoint, env)
    raw_headers = resolve_endpoint_headers(endpoint, env)
    headers = parse_header_lines(raw_headers, endpoint) if raw_headers is not None else {}
    return ApiJudge(
        endpoint=endpoint,
        model=model,
        token=token,
        headers=headers,
        reasoning_effort=reasoning_effort,
    )

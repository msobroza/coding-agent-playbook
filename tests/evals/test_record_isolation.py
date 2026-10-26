"""The credentials an isolated ``--record`` run needs (``record_isolation``, #329 ticket 02)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint
from coding_agent_playbook.evals.model_pins import RecordRefusedError
from coding_agent_playbook.evals.record_isolation import (
    API_KEY_VARIABLE,
    check_record_credentials,
    record_api_key,
)

_KEY = "fake-record-key"
_ENDPOINT = Endpoint("internal", "anthropic", "https://llm.internal.example", token_env="LLM_TOK")


def _check(
    env: dict[str, str],
    *,
    target: Endpoint | None = None,
    judge: Endpoint | None = None,
    harness: bool = True,
    uses_judge: bool = False,
) -> None:
    check_record_credentials(
        target_endpoint=target,
        judge_endpoint=judge,
        harness_isolated=harness,
        judge_isolated=uses_judge,
        env=env,
    )


def test_an_api_key_covers_the_harness_and_the_judge_without_endpoints() -> None:
    _check({API_KEY_VARIABLE: _KEY}, uses_judge=True)


def test_an_endpoint_token_covers_its_endpoint_without_an_api_key() -> None:
    _check({"LLM_TOK": "t0"}, target=_ENDPOINT, judge=_ENDPOINT, uses_judge=True)


def test_a_token_command_endpoint_is_left_to_the_route() -> None:
    by_command = Endpoint("cmd", "anthropic", "https://x", token_command=("print-token",))
    _check({}, target=by_command)


@pytest.mark.parametrize(
    ("env", "kwargs", "who"),
    [
        ({}, {}, "the harness runs on Anthropic's API"),
        ({API_KEY_VARIABLE: ""}, {}, "ANTHROPIC_API_KEY is unset or empty"),
        ({API_KEY_VARIABLE: _KEY}, {"target": _ENDPOINT}, "token_env LLM_TOK is unset"),
        ({"LLM_TOK": "t0"}, {"target": _ENDPOINT, "uses_judge": True}, "the judge runs on"),
    ],
)
def test_a_missing_credential_is_refused_naming_both_variables(
    env: dict[str, str], kwargs: dict[str, object], who: str
) -> None:
    with pytest.raises(RecordRefusedError) as refused:
        _check(env, **kwargs)  # type: ignore[arg-type]
    message = str(refused.value)
    assert who in message
    assert "ANTHROPIC_API_KEY" in message
    assert "token_env" in message
    assert _KEY not in message


def test_processes_that_run_no_cli_need_no_credential() -> None:
    _check({}, harness=False, uses_judge=False)


def test_an_endpoint_without_token_env_is_named() -> None:
    bare = Endpoint("bare", "anthropic", "https://x")
    with pytest.raises(RecordRefusedError, match="'bare', which sets no token_env"):
        _check({API_KEY_VARIABLE: _KEY}, target=bare)


def test_record_api_key_reads_the_variable_or_refuses_naming_it() -> None:
    assert record_api_key({API_KEY_VARIABLE: _KEY}) == _KEY
    with pytest.raises(RecordRefusedError, match="ANTHROPIC_API_KEY"):
        record_api_key({})

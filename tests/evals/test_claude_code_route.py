"""The argv and environment a Claude Code run gets on an endpoint (``claude_code_route``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint, EndpointError
from coding_agent_playbook.evals.run.claude_code_route import (
    ClaudeCodeRoute,
    claude_code_route,
    routed_env,
)

_TOKEN = "fake-endpoint-token"
_URL = "https://llm.internal.example"

#: An engine environment with the user's own Claude Code credentials and switches.
_PARENT_ENV = {
    "PATH": "/usr/bin",
    "HOME": "/home/dev",
    "ANTHROPIC_API_KEY": "fake-personal-key",
    "ANTHROPIC_BASE_URL": "https://personal.example",
    "ANTHROPIC_MODEL": "personal-model",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_OAUTH_TOKEN": "fake-oauth",
    "CLOUD_ML_REGION": "us-east5",
    "INTERNAL_LLM_TOKEN": _TOKEN,
    "PLAYBOOK_HOOK_UNATTENDED": "1",
}


def _endpoint(**overrides: object) -> Endpoint:
    fields: dict[str, object] = {
        "name": "internal",
        "api": "anthropic",
        "base_url": _URL,
        "token_env": "INTERNAL_LLM_TOKEN",
    }
    fields.update(overrides)
    return Endpoint(**fields)  # type: ignore[arg-type]


def _route(**overrides: object) -> ClaudeCodeRoute:
    return claude_code_route(
        _endpoint(**overrides), "internal-opus", small_model="internal-haiku", env=_PARENT_ENV
    )


def test_bearer_endpoint_env_is_isolated_and_carries_only_the_token() -> None:
    env = _route().child_env(_PARENT_ENV, Path("/scratch/claude-config"))
    assert env["ANTHROPIC_AUTH_TOKEN"] == _TOKEN
    assert env["CLAUDE_CONFIG_DIR"] == "/scratch/claude-config"
    for dropped in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLOUD_ML_REGION",
        "INTERNAL_LLM_TOKEN",
    ):
        assert dropped not in env, dropped
    assert (env["PATH"], env["HOME"], env["PLAYBOOK_HOOK_UNATTENDED"]) == (
        "/usr/bin",
        "/home/dev",
        "1",
    )
    assert env["DISABLE_TELEMETRY"] == "1"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["DISABLE_ERROR_REPORTING"] == "1"


def test_x_api_key_endpoint_sends_the_token_as_the_api_key_only() -> None:
    env = _route(auth_header="x-api-key").child_env(_PARENT_ENV, Path("/c"))
    assert env["ANTHROPIC_API_KEY"] == _TOKEN
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_declared_limits_and_headers_go_in_the_environment() -> None:
    parent = {**_PARENT_ENV, "LLM_HEADERS": "X-Team: evals"}
    route = claude_code_route(
        _endpoint(context_tokens=131072, max_output_tokens=8192, headers_env="LLM_HEADERS"),
        "m",
        env=parent,
    )
    env = route.child_env(parent, Path("/c"))
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "131072"
    assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8192"
    assert env["ANTHROPIC_CUSTOM_HEADERS"] == "X-Team: evals"
    assert "LLM_HEADERS" not in env


def test_limits_are_left_unset_when_not_declared() -> None:
    env = _route().child_env(_PARENT_ENV, Path("/c"))
    assert "CLAUDE_CODE_MAX_CONTEXT_TOKENS" not in env
    assert "ANTHROPIC_CUSTOM_HEADERS" not in env


def test_settings_argv_routes_the_base_url_and_models_without_the_token() -> None:
    flag, payload = _route().settings_argv()
    assert flag == "--settings"
    assert json.loads(payload) == {
        "env": {
            "ANTHROPIC_BASE_URL": _URL,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "internal-haiku",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "internal-opus",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "internal-opus",
        }
    }
    assert _TOKEN not in payload


def test_small_model_defaults_to_the_model() -> None:
    route = claude_code_route(_endpoint(), "internal-opus", env=_PARENT_ENV)
    assert json.loads(route.settings_argv()[1])["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == (
        "internal-opus"
    )


def test_token_stays_out_of_the_repr_and_is_redacted() -> None:
    route = _route()
    assert _TOKEN not in repr(route)
    assert route.redact(f"401 for {_TOKEN}") == "401 for [redacted]"


def test_missing_token_variable_fails_before_any_run() -> None:
    with pytest.raises(EndpointError, match=r"INTERNAL_LLM_TOKEN is unset or empty"):
        claude_code_route(_endpoint(), "m", env={})


def test_non_anthropic_endpoint_is_refused_with_the_opencode_hint() -> None:
    with pytest.raises(EndpointError, match=r"api = 'openai-chat'.*OpenCode target"):
        claude_code_route(_endpoint(api="openai-chat"), "m", env=_PARENT_ENV)


def test_routed_env_gives_a_fresh_empty_config_dir_and_removes_it() -> None:
    with routed_env(_route(), _PARENT_ENV) as env:
        assert env is not None
        config_dir = Path(env["CLAUDE_CONFIG_DIR"])
        assert config_dir.is_dir()
        assert list(config_dir.iterdir()) == []
    assert not config_dir.exists()


def test_routed_env_without_a_route_keeps_the_base() -> None:
    with routed_env(None, {"PATH": "/bin"}) as env:
        assert env == {"PATH": "/bin"}
    with routed_env(None, None) as inherited:
        assert inherited is None

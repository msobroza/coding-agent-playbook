"""The inline config and environment an OpenCode run gets on an endpoint (``opencode_route``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint, EndpointError
from coding_agent_playbook.evals.run.opencode_route import (
    PROVIDER_ID,
    TOKEN_VARIABLE,
    OpenCodeRoute,
    opencode_route,
    routed_opencode_env,
)

_TOKEN = "fake-endpoint-token"
_URL = "https://llm.internal.example/v1"

#: An engine environment with the user's own provider keys, OpenCode config and telemetry.
_PARENT_ENV = {
    "PATH": "/usr/bin",
    "HOME": "/home/dev",
    "ANTHROPIC_API_KEY": "fake-personal-key",
    "ANTHROPIC_BASE_URL": "https://personal.example",
    "OPENAI_API_KEY": "fake-openai-key",
    "OPENAI_BASE_URL": "https://personal-openai.example",
    "GROQ_API_KEY": "fake-groq-key",
    "AWS_BEARER_TOKEN_BEDROCK": "fake-bedrock",
    "OPENCODE_CONFIG": "/home/dev/my-opencode.json",
    "OPENCODE_CONFIG_DIR": "/home/dev/.opencode-extra",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example",
    "OTEL_EXPORTER_OTLP_HEADERS": "x=y",
    "XDG_CONFIG_HOME": "/home/dev/.config",
    "INTERNAL_LLM_TOKEN": _TOKEN,
    "PLAYBOOK_HOOK_UNATTENDED": "1",
}


def _endpoint(**overrides: object) -> Endpoint:
    fields: dict[str, object] = {
        "name": "internal",
        "api": "openai-chat",
        "base_url": _URL,
        "token_env": "INTERNAL_LLM_TOKEN",
        "context_tokens": 131072,
        "max_output_tokens": 8192,
    }
    fields.update(overrides)
    return Endpoint(**fields)  # type: ignore[arg-type]


def _route(env: dict[str, str] | None = None, **overrides: object) -> OpenCodeRoute:
    return opencode_route(
        _endpoint(**overrides), "my-org/coder-32b", env=_PARENT_ENV if env is None else env
    )


def _config(route: OpenCodeRoute) -> dict[str, object]:
    env = route.child_env(_PARENT_ENV, Path("/scratch/oc"))
    config: dict[str, object] = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    return config


def _provider(route: OpenCodeRoute) -> dict[str, object]:
    providers = _config(route)["provider"]
    assert isinstance(providers, dict)
    assert list(providers) == [PROVIDER_ID]
    provider: dict[str, object] = providers[PROVIDER_ID]
    return provider


@pytest.mark.parametrize(
    ("api", "npm"),
    [
        ("openai-chat", "@ai-sdk/openai-compatible"),
        ("openai-responses", "@ai-sdk/openai"),
        ("anthropic", "@ai-sdk/anthropic"),
    ],
)
def test_each_api_shape_gets_its_sdk_package_under_the_unique_provider(api: str, npm: str) -> None:
    provider = _provider(_route(api=api))
    assert provider["npm"] == npm
    assert PROVIDER_ID not in ("openai", "anthropic", "opencode")


def test_inline_config_enables_only_the_target_provider_with_its_model() -> None:
    config = _config(_route())
    model_ref = f"{PROVIDER_ID}/my-org/coder-32b"
    assert config["enabled_providers"] == [PROVIDER_ID]
    assert (config["model"], config["small_model"]) == (model_ref, model_ref)
    assert config["autoupdate"] is False
    provider = _provider(_route())
    assert provider["models"] == {
        "my-org/coder-32b": {
            "id": "my-org/coder-32b",
            "name": "my-org/coder-32b",
            "limit": {"context": 131072, "output": 8192},
            "cost": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        }
    }


def test_token_is_an_env_reference_never_the_value() -> None:
    route = _route()
    env = route.child_env(_PARENT_ENV, Path("/scratch/oc"))
    options = _provider(route)["options"]
    assert options == {"baseURL": _URL, "apiKey": "{env:" + TOKEN_VARIABLE + "}"}
    assert _TOKEN not in env["OPENCODE_CONFIG_CONTENT"]
    assert env[TOKEN_VARIABLE] == _TOKEN


def test_bearer_anthropic_endpoint_sends_the_token_as_auth_token() -> None:
    options = _provider(_route(api="anthropic"))["options"]
    assert options == {"baseURL": _URL, "authToken": "{env:" + TOKEN_VARIABLE + "}"}


def test_x_api_key_anthropic_endpoint_sends_the_token_as_api_key() -> None:
    options = _provider(_route(api="anthropic", auth_header="x-api-key"))["options"]
    assert options == {"baseURL": _URL, "apiKey": "{env:" + TOKEN_VARIABLE + "}"}


def test_small_model_is_declared_and_used_as_the_small_model() -> None:
    route = opencode_route(_endpoint(), "big", small_model="small", env=_PARENT_ENV)
    config = _config(route)
    assert config["small_model"] == f"{PROVIDER_ID}/small"
    models = _provider(route)["models"]
    assert isinstance(models, dict)
    assert sorted(models) == ["big", "small"]
    assert models["small"]["id"] == "small"


def test_undeclared_limits_are_left_out() -> None:
    route = _route(context_tokens=None, max_output_tokens=None)
    models = _provider(route)["models"]
    assert isinstance(models, dict)
    assert "limit" not in models["my-org/coder-32b"]


def test_one_declared_limit_leaves_the_other_at_opencode_default() -> None:
    models = _provider(_route(context_tokens=None))["models"]
    assert isinstance(models, dict)
    assert models["my-org/coder-32b"]["limit"] == {"context": 0, "output": 8192}


def test_model_ref_is_provider_qualified() -> None:
    assert _route().model_ref == f"{PROVIDER_ID}/my-org/coder-32b"


def test_child_env_is_isolated_from_the_users_config_keys_and_telemetry() -> None:
    env = _route().child_env(_PARENT_ENV, Path("/scratch/oc"))
    for dropped in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "GROQ_API_KEY",
        "AWS_BEARER_TOKEN_BEDROCK",
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_DIR",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "INTERNAL_LLM_TOKEN",
    ):
        assert dropped not in env, dropped
    assert env["XDG_CONFIG_HOME"] == str(Path("/scratch/oc/config"))
    assert env["XDG_DATA_HOME"] == str(Path("/scratch/oc/data"))
    assert env["XDG_STATE_HOME"] == str(Path("/scratch/oc/state"))
    assert env["OPENCODE_DISABLE_CLAUDE_CODE"] == "1"
    assert env["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
    assert env["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
    assert (env["PATH"], env["HOME"], env["PLAYBOOK_HOOK_UNATTENDED"]) == (
        "/usr/bin",
        "/home/dev",
        "1",
    )


def test_missing_token_variable_is_refused_naming_it() -> None:
    env = {k: v for k, v in _PARENT_ENV.items() if k != "INTERNAL_LLM_TOKEN"}
    with pytest.raises(EndpointError, match="INTERNAL_LLM_TOKEN is unset or empty"):
        _route(env=env)


@pytest.mark.parametrize("bad", ['fa"ke', "fa\\ke", "fa\nke", "fa\x01ke"])
def test_token_that_would_corrupt_the_inline_config_is_refused_naming_the_variable(
    bad: str,
) -> None:
    with pytest.raises(EndpointError) as excinfo:
        _route(env={**_PARENT_ENV, "INTERNAL_LLM_TOKEN": bad})
    message = str(excinfo.value)
    assert "INTERNAL_LLM_TOKEN" in message
    assert bad.strip() not in message


def test_token_command_token_is_checked_too_without_naming_a_variable() -> None:
    endpoint = _endpoint(token_env=None, token_command=("pass", "show", "llm"))
    with pytest.raises(EndpointError, match="token_command") as excinfo:
        opencode_route(endpoint, "m", env={}, run_command=lambda _argv: 'x"y')
    assert 'x"y' not in str(excinfo.value)


def test_extra_headers_are_parsed_into_the_provider_options_and_redacted() -> None:
    env = {**_PARENT_ENV, "LLM_HEADERS": "X-Team: evals\nX-Secret: s3cr3t-value"}
    route = _route(env=env, headers_env="LLM_HEADERS")
    options = _provider(route)["options"]
    assert isinstance(options, dict)
    assert options["headers"] == {"X-Team": "evals", "X-Secret": "s3cr3t-value"}
    assert "LLM_HEADERS" not in route.child_env(env, Path("/scratch/oc"))
    assert route.redact("got s3cr3t-value") == "got [redacted]"


def test_a_malformed_header_line_is_refused_naming_the_variable() -> None:
    env = {**_PARENT_ENV, "LLM_HEADERS": "no-colon-here"}
    with pytest.raises(EndpointError, match="LLM_HEADERS"):
        _route(env=env, headers_env="LLM_HEADERS")


def test_redact_replaces_the_token() -> None:
    assert _route().redact(f"401 for {_TOKEN}") == "401 for [redacted]"


def test_route_repr_holds_no_secret() -> None:
    assert _TOKEN not in repr(_route())


def test_routed_opencode_env_without_a_route_is_the_base_unchanged() -> None:
    with routed_opencode_env(None, {"PATH": "/bin"}) as env:
        assert env == {"PATH": "/bin"}


def test_routed_opencode_env_gives_fresh_scratch_xdg_dirs_removed_after() -> None:
    with routed_opencode_env(_route(), _PARENT_ENV) as env:
        assert env is not None
        config_home = Path(env["XDG_CONFIG_HOME"])
        assert config_home.is_dir()
        assert list(config_home.iterdir()) == []
        assert Path(env["XDG_DATA_HOME"]).is_dir()
    assert not config_home.exists()

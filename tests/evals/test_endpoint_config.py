"""``[evals.endpoints]`` and the endpoint keys of targets and the judge (spec #281 ticket 06)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.evals.target_config import parse_eval_settings

_ANTHROPIC = {
    "api": "anthropic",
    "base_url": "https://llm.internal.example",
    "token_env": "INTERNAL_LLM_TOKEN",
}
_OPENAI = {"api": "openai-chat", "base_url": "https://llm.internal.example/v1", "token_env": "T"}


def _committed(**endpoints: object) -> dict[str, object]:
    return {"endpoints": endpoints}


def test_endpoint_block_is_read_with_its_defaults() -> None:
    spec = {**_ANTHROPIC, "context_tokens": 200000, "max_output_tokens": 8192}
    settings = parse_eval_settings(
        {
            "endpoints": {"internal": spec},
            "targets": {
                "ic": {
                    "harness": "claude_code",
                    "endpoint": "internal",
                    "model": "internal-opus",
                    "small_model": "internal-haiku",
                }
            },
        },
        {},
    )
    target = settings.targets["ic"]
    assert target.endpoint is not None
    assert (target.endpoint.name, target.endpoint.api, target.endpoint.auth_header) == (
        "internal",
        "anthropic",
        "bearer",
    )
    assert (target.endpoint.context_tokens, target.endpoint.max_output_tokens) == (200000, 8192)
    assert target.endpoint.source == ".coding-agent-playbook.toml"
    assert target.small_model == "internal-haiku"


def test_local_file_may_add_the_token_part_to_a_committed_endpoint() -> None:
    committed = {
        "endpoints": {"internal": {"api": "anthropic", "base_url": "https://x"}},
        "targets": {"ic": {"harness": "claude_code", "endpoint": "internal", "model": "m"}},
    }
    local = {"endpoints": {"internal": {"token_command": "llm-token --print"}}}
    endpoint = parse_eval_settings(committed, local).targets["ic"].endpoint
    assert endpoint is not None
    assert endpoint.token_command == ("llm-token", "--print")
    assert endpoint.token_env is None
    assert endpoint.base_url == "https://x"


def test_local_file_may_declare_its_own_endpoint_and_targets_on_it() -> None:
    local = {
        "endpoints": {"mine": _ANTHROPIC},
        "targets": {"t": {"harness": "claude_code", "endpoint": "mine", "model": "m"}},
        "judge": {"endpoint": "mine", "model": "judge-m"},
    }
    settings = parse_eval_settings({}, local)
    assert settings.targets["t"].endpoint is not None
    assert settings.judge.endpoint is not None
    assert settings.judge.endpoint.name == "mine"


@pytest.mark.parametrize("key", ["token", "api_key", "password", "secret", "key"])
@pytest.mark.parametrize("in_local", [False, True])
def test_inline_secret_keys_are_refused_in_both_files(key: str, in_local: bool) -> None:
    evals = {"endpoints": {"e": {**_ANTHROPIC, key: "fake-value"}}}
    committed, local = ({}, evals) if in_local else (evals, {})
    with pytest.raises(ConfigError, match=rf"{key} would put a secret.*token_env"):
        parse_eval_settings(committed, local)


def test_inline_secret_keys_are_refused_on_targets_and_the_judge_too() -> None:
    with pytest.raises(ConfigError, match=r"\[evals\.targets\.t\] api_key would put a secret"):
        parse_eval_settings({"targets": {"t": {"harness": "x", "api_key": "v"}}}, {})
    with pytest.raises(ConfigError, match=r"\[evals\.judge\] token would put a secret"):
        parse_eval_settings({}, {"judge": {"token": "v"}})


@pytest.mark.parametrize(
    ("committed", "local", "message"),
    [
        (
            _committed(e={**_ANTHROPIC, "token_command": "x"}),
            {},
            r"\.coding-agent-playbook\.toml: \[evals\.endpoints\.e\] token_command is accepted "
            r"only in \.coding-agent-playbook\.local\.toml",
        ),
        (
            _committed(e=_ANTHROPIC),
            {"endpoints": {"e": {"base_url": "https://elsewhere"}}},
            r"local\.toml: \[evals\.endpoints\.e\] may add only \['token_command', 'token_env'\]"
            r".*got \['base_url'\]",
        ),
        (_committed(e={"api": "anthropic"}), {}, r"\[evals\.endpoints\.e\] needs base_url"),
        (_committed(e={**_ANTHROPIC, "api": "grpc"}), {}, r"api must be one of"),
        (_committed(e={**_ANTHROPIC, "base_url": "llm:80"}), {}, r"base_url must start with"),
        (_committed(e={**_ANTHROPIC, "token_env": "A-B"}), {}, r"token_env must name an env"),
        (_committed(e={**_ANTHROPIC, "auth_header": "basic"}), {}, r"auth_header must be one"),
        (
            _committed(e={**_OPENAI, "auth_header": "bearer"}),
            {},
            r"auth_header applies to api = 'anthropic' only",
        ),
        (_committed(e={**_ANTHROPIC, "context_tokens": 0}), {}, r"context_tokens must be an"),
        (_committed(e={**_ANTHROPIC, "retries": 3}), {}, r"unknown key\(s\) \['retries'\]"),
        (
            {},
            {"endpoints": {"e": {**_ANTHROPIC, "token_command": "x"}}},
            r"sets token_env and token_command; keep one",
        ),
    ],
)
def test_misread_endpoint_blocks_are_refused(
    committed: dict[str, object], local: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_eval_settings(committed, local)


def test_claude_code_target_on_a_non_anthropic_endpoint_points_to_opencode() -> None:
    committed = {
        "endpoints": {"oai": _OPENAI},
        "targets": {"t": {"harness": "claude_code", "endpoint": "oai", "model": "m"}},
    }
    with pytest.raises(ConfigError, match=r"Claude Code speaks only api = 'anthropic'.*opencode"):
        parse_eval_settings(committed, {})


def test_opencode_target_may_name_a_non_anthropic_endpoint() -> None:
    committed = {
        "endpoints": {"oai": _OPENAI},
        "targets": {"t": {"harness": "opencode", "endpoint": "oai", "model": "m"}},
    }
    endpoint = parse_eval_settings(committed, {}).targets["t"].endpoint
    assert endpoint is not None
    assert endpoint.api == "openai-chat"


def test_judge_on_a_non_anthropic_endpoint_points_to_opencode() -> None:
    committed = {"endpoints": {"oai": _OPENAI}, "judge": {"endpoint": "oai", "model": "m"}}
    with pytest.raises(ConfigError, match=r"\[evals\.judge\] the LLM judge.*opencode"):
        parse_eval_settings(committed, {})


@pytest.mark.parametrize(
    ("committed", "local", "message"),
    [
        (
            {"targets": {"t": {"harness": "claude_code", "endpoint": "ghost", "model": "m"}}},
            {},
            r"\[evals\.targets\.t\] endpoint 'ghost' is not declared",
        ),
        (
            {"targets": {"t": {"harness": "claude_code", "endpoint": "mine", "model": "m"}}},
            {"endpoints": {"mine": _ANTHROPIC}},
            r"\.coding-agent-playbook\.toml: \[evals\.targets\.t\] endpoint 'mine' is not declared",
        ),
        (
            {
                "endpoints": {"e": _ANTHROPIC},
                "targets": {"t": {"harness": "claude_code", "endpoint": "e"}},
            },
            {},
            r"\[evals\.targets\.t\] needs model = the id endpoint 'e' serves",
        ),
        (
            {"targets": {"t": {"harness": "claude_code", "small_model": "s"}}},
            {},
            r"\[evals\.targets\.t\] small_model needs an endpoint",
        ),
        (
            {"endpoints": {"e": _ANTHROPIC}, "judge": {"endpoint": "e"}},
            {},
            r"\[evals\.judge\] needs model = the id endpoint 'e' serves",
        ),
        (
            {"judge": {"endpoint": "mine", "model": "m"}},
            {"endpoints": {"mine": _ANTHROPIC}},
            r"\.coding-agent-playbook\.toml: \[evals\.judge\] endpoint 'mine' is not declared",
        ),
    ],
)
def test_endpoint_references_are_checked(
    committed: dict[str, object], local: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_eval_settings(committed, local)

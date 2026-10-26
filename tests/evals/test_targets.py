"""Eval target resolution: ``--target``, the variable, local default, committed default, built-in."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.targets import (
    BUILTIN_TARGET,
    TARGET_ENV_VAR,
    EvalSettings,
    EvalTarget,
    TargetError,
    lookup_target,
    resolve_target,
    runner_alias_target,
    target_selection,
)

_TARGETS = {
    name: EvalTarget(name, "claude_code", f"model-{name}", source="c.toml")
    for name in ("cli", "env", "local", "committed")
}
_ALL_SOURCES = EvalSettings(targets=_TARGETS, committed_default="committed", local_default="local")


def _resolved(settings: EvalSettings, cli: str | None = None, env: str | None = None) -> str:
    environ = {} if env is None else {TARGET_ENV_VAR: env}
    return resolve_target(settings, cli_value=cli, env=environ).name


def test_target_flag_wins_over_every_other_source() -> None:
    assert _resolved(_ALL_SOURCES, cli="cli", env="env") == "cli"


def test_environment_variable_wins_over_both_defaults() -> None:
    assert _resolved(_ALL_SOURCES, env="env") == "env"


def test_empty_environment_variable_counts_as_unset() -> None:
    assert _resolved(_ALL_SOURCES, env="") == "local"


def test_local_default_wins_over_committed_default() -> None:
    assert _resolved(_ALL_SOURCES) == "local"


def test_committed_default_applies_without_a_local_one() -> None:
    settings = EvalSettings(targets=_TARGETS, committed_default="committed")
    assert _resolved(settings) == "committed"


def test_nothing_configured_is_todays_behaviour() -> None:
    target = resolve_target(EvalSettings(), cli_value=None, env={})
    assert target == BUILTIN_TARGET
    assert (target.name, target.harness, target.model) == ("default", "claude_code", None)


def test_unknown_name_lists_the_configured_names() -> None:
    with pytest.raises(TargetError, match=r"'nope' \(from --target\).*cli, committed, env, local"):
        lookup_target(_ALL_SOURCES, "nope", source="--target")


def test_unknown_name_without_targets_says_none_are_configured() -> None:
    with pytest.raises(TargetError, match=r"\(none configured\)"):
        resolve_target(EvalSettings(), cli_value=None, env={TARGET_ENV_VAR: "nope"})


def test_shorthand_keeps_the_model_exactly_as_written() -> None:
    target = lookup_target(EvalSettings(), "claude_code:bedrock/claude:v1:0", source="--target")
    assert (target.harness, target.model) == ("claude_code", "bedrock/claude:v1:0")
    assert (target.name, target.source) == ("claude_code:bedrock/claude:v1:0", "--target")


@pytest.mark.parametrize("spec", [":model", "claude_code:"])
def test_shorthand_needs_both_parts(spec: str) -> None:
    with pytest.raises(TargetError, match="both parts non-empty"):
        lookup_target(EvalSettings(), spec, source="--target")


def test_selection_names_the_source_it_came_from() -> None:
    selected = target_selection(_ALL_SOURCES, cli_value=None, env={})
    assert selected == ("local", ".coding-agent-playbook.local.toml [evals] default")


def test_runner_alias_is_that_harness_without_a_model() -> None:
    target = runner_alias_target("opencode")
    assert (target.name, target.harness, target.model, target.source) == (
        "opencode",
        "opencode",
        None,
        "--runner",
    )


def test_display_model_names_the_harness_default() -> None:
    assert BUILTIN_TARGET.display_model == "(harness default)"
    assert _TARGETS["cli"].display_model == "model-cli"

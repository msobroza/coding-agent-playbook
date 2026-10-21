"""The committed ``prompts`` key that selects a prompt set (D76; prU L0-24)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.schema import ConfigError


def _config_data(**extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": {"name": "x", "kind": "python-library"},
        "engine": {"version": "0.1"},
        **extra,
    }


def test_without_a_prompts_key_the_prompt_set_is_v1_and_nothing_is_written() -> None:
    config = Config.from_dict(_config_data())
    assert config.prompt_set == "v1"
    assert "prompts" not in config.to_dict()


@pytest.mark.parametrize("prompt_set", ["v1", "v2"])
def test_a_prompts_key_selects_its_set_and_round_trips(prompt_set: str) -> None:
    config = Config.from_dict(_config_data(prompts=prompt_set))
    assert config.prompt_set == prompt_set
    assert config.to_dict()["prompts"] == prompt_set


@pytest.mark.parametrize("bad", ["v3", "V2", "", 2, ["v2"]])
def test_an_unknown_prompt_set_is_a_config_error_naming_the_file_and_the_sets(
    bad: object,
) -> None:
    with pytest.raises(ConfigError) as excinfo:
        Config.from_dict(_config_data(prompts=bad), source="c.toml")
    message = str(excinfo.value)
    assert message.startswith("c.toml: prompts must be ")
    assert '"v1"' in message
    assert '"v2"' in message

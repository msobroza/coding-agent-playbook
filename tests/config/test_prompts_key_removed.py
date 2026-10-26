"""The removed ``prompts`` key: a config that still sets it fails to load (ADR 0012, #300).

Prompt sets are gone and consumer repos always render the current text, so the
key that picked ``"v1"`` or ``"v2"`` is refused, naming the file that sets it,
instead of being silently ignored.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import ConfigFiles
from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.schema import PROMPTS_KEY_REMOVED, ConfigError
from coding_agent_playbook.detector.config_filenames import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.toml_writer import dump_toml
from tests.engine_version import ENGINE_VERSION

if TYPE_CHECKING:
    from pathlib import Path


def _config_data(**extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": {"name": "x", "kind": "python-library"},
        "engine": {"version": ENGINE_VERSION},
        **extra,
    }


def test_a_config_without_prompts_loads_and_writes_no_prompts_key() -> None:
    assert "prompts" not in Config.from_dict(_config_data()).to_dict()


@pytest.mark.parametrize("value", ["v1", "v2", "v3", "", 2, ["v2"]])
def test_any_prompts_value_is_refused_with_the_removal_message(value: object) -> None:
    with pytest.raises(ConfigError) as excinfo:
        Config.from_dict(_config_data(prompts=value), source="c.toml")
    assert str(excinfo.value) == f"c.toml: {PROMPTS_KEY_REMOVED}"


def test_the_message_says_why_the_key_went() -> None:
    assert "removed because consumer repos always get the current text" in PROMPTS_KEY_REMOVED
    assert "delete the 'prompts' line" in PROMPTS_KEY_REMOVED


@pytest.mark.parametrize("where", [CONFIG_FILENAME, CONFIG_LOCAL_FILENAME])
def test_loading_a_repo_names_the_file_that_sets_prompts(tmp_path: Path, where: str) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(dump_toml(_config_data()))
    other = {"prompts": "v2"}
    if where == CONFIG_FILENAME:
        (tmp_path / CONFIG_FILENAME).write_text(dump_toml(_config_data(**other)))
    else:
        (tmp_path / CONFIG_LOCAL_FILENAME).write_text(dump_toml(other))
    with pytest.raises(ConfigError, match=f"^{re.escape(where)}: retired key 'prompts'"):
        ConfigFiles(tmp_path).load()

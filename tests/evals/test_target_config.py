"""The ``[evals]`` table of the committed and the local config files (``evals.target_config``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.evals.target_config import load_eval_settings, parse_eval_settings
from coding_agent_playbook.evals.targets import JudgeSettings

if TYPE_CHECKING:
    from pathlib import Path

_COMMITTED = """\
[evals]
default = "claude-opus"
release = ["claude-opus"]

[evals.targets.claude-opus]
harness = "claude_code"
model = "claude-opus-5-5"
runs = 3
label = "Claude Opus"

[evals.judge]
model = "claude-opus-5-5"
samples = 3
"""

_LOCAL = """\
[evals]
default = "mine"

[evals.targets.mine]
harness = "opencode"
model = "my-org/coder-32b"

[evals.judge]
samples = 5
"""


def _repo(tmp_path: Path, committed: str | None = _COMMITTED, local: str | None = None) -> Path:
    if committed is not None:
        (tmp_path / ".coding-agent-playbook.toml").write_text(committed, encoding="utf-8")
    if local is not None:
        (tmp_path / ".coding-agent-playbook.local.toml").write_text(local, encoding="utf-8")
    return tmp_path


def test_committed_targets_are_read_with_their_file(tmp_path: Path) -> None:
    settings = load_eval_settings(_repo(tmp_path))
    target = settings.targets["claude-opus"]
    assert (target.harness, target.model, target.runs, target.label) == (
        "claude_code",
        "claude-opus-5-5",
        3,
        "Claude Opus",
    )
    assert target.source == ".coding-agent-playbook.toml"
    assert settings.committed_default == "claude-opus"
    assert settings.release == ("claude-opus",)
    assert settings.judge == JudgeSettings(model="claude-opus-5-5", samples=3)


def test_local_file_adds_targets_changes_default_and_overrides_judge_keys(tmp_path: Path) -> None:
    settings = load_eval_settings(_repo(tmp_path, local=_LOCAL))
    assert sorted(settings.targets) == ["claude-opus", "mine"]
    assert settings.targets["mine"].source == ".coding-agent-playbook.local.toml"
    assert (settings.committed_default, settings.local_default) == ("claude-opus", "mine")
    assert settings.judge == JudgeSettings(model="claude-opus-5-5", samples=5)


def test_no_config_files_are_the_zero_config_defaults(tmp_path: Path) -> None:
    settings = load_eval_settings(_repo(tmp_path, committed=None))
    assert settings.targets == {}
    assert settings.committed_default is None
    assert settings.judge == JudgeSettings()


@pytest.mark.parametrize(
    ("committed", "local", "message"),
    [
        ({"endpoints": {}}, {}, r"\.coding-agent-playbook\.toml: \[evals\] has unknown key"),
        ({}, {"release": []}, r"local\.toml: \[evals\] has unknown key\(s\) \['release'\]"),
        ({"targets": {"t": {"model": "m"}}}, {}, r"\[evals\.targets\.t\] needs harness"),
        ({"targets": {"t": {"harness": "x", "price": 1}}}, {}, r"unknown key\(s\) \['price'\]"),
        ({"targets": {"t": {"harness": "x", "runs": 0}}}, {}, r"runs must be an integer >= 1"),
        ({"targets": {"t": {"harness": "x", "runs": True}}}, {}, r"runs must be an integer"),
        ({"targets": {"t": {"harness": "x", "model": ""}}}, {}, r"model must be a non-empty"),
        ({"targets": {"a:b": {"harness": "x"}}}, {}, r"no ':'.*got 'a:b'"),
        ({"targets": "x"}, {}, r"\[evals\.targets\] must be a table, got 'x'"),
        ({"release": ["ghost"]}, {}, r"release names unknown target\(s\) \['ghost'\]"),
        ({"release": "ghost"}, {}, r"release must be a list of target names"),
        ({"default": "ghost"}, {}, r"unknown eval target 'ghost'"),
        ({"judge": {"samples": 0}}, {}, r"\[evals\.judge\] samples must be an integer >= 1"),
        ({"judge": {"temperature": 0}}, {}, r"\[evals\.judge\] has unknown key"),
        ("x", {}, r"\[evals\] must be a table, got 'x'"),
    ],
)
def test_misread_shapes_are_refused_naming_file_and_value(
    committed: object, local: object, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_eval_settings(committed, local)


def test_local_file_cannot_redefine_a_committed_target() -> None:
    committed = {"targets": {"t": {"harness": "claude_code"}}}
    local = {"targets": {"t": {"harness": "opencode"}}}
    with pytest.raises(ConfigError, match=r"redefines \['t'\].*another name"):
        parse_eval_settings(committed, local)


def test_committed_default_cannot_name_a_local_target() -> None:
    local = {"targets": {"mine": {"harness": "opencode"}}}
    with pytest.raises(ConfigError, match=r"unknown eval target 'mine'"):
        parse_eval_settings({"default": "mine"}, local)


def test_defaults_may_be_a_shorthand() -> None:
    settings = parse_eval_settings({"default": "opencode:my-org/coder"}, {})
    assert settings.committed_default == "opencode:my-org/coder"

"""Tests for FileSystemArtifactSource and FileSystemStateSource (SPEC §20.3)."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config import Config, ProjectMeta
from coding_agent_playbook.lockfile import LockEntry, Lockfile
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_PRIMARY = """\
schema_version = 1

[project]
name = "my-app"
kind = "python-application"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[user_choices]
banking_mode = false
"""

CONFIG_LOCAL_OVERRIDE = """\
[user_choices]
banking_mode = true
extra_dev_choice = "yes"
"""


def test_load_config_reads_primary_toml(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = source.load_config()
    assert config.schema_version == 1
    assert config.project.name == "my-app"
    assert config.project.kind == "python-application"
    assert config.engine_version == "0.1.0a0"
    assert config.user_choices == {"banking_mode": False}


def test_load_config_merges_local_overrides(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_OVERRIDE)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = source.load_config()
    assert config.user_choices == {
        "banking_mode": True,
        "extra_dev_choice": "yes",
    }


def test_load_config_missing_raises_fnf(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError, match=r"\.coding-agent-playbook\.toml"):
        source.load_config()


def test_save_config_emits_valid_toml(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="my-app", kind="python-application"),
        engine_version="0.1.0a0",
        user_choices={"banking_mode": True},
    )
    source.save_config(config)
    written = tmp_path / ".coding-agent-playbook.toml"
    assert written.is_file()
    with written.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["schema_version"] == 1
    assert parsed["project"]["name"] == "my-app"
    assert parsed["engine"]["version"] == "0.1.0a0"
    assert parsed["user_choices"]["banking_mode"] is True


def test_dump_toml_rejects_unsupported_scalar() -> None:
    from coding_agent_playbook.sources.filesystem import _dump_toml

    with pytest.raises(TypeError, match=r"does not support value of type"):
        _dump_toml({"weird": object()})


def test_dump_toml_rejects_nested_section_mapping() -> None:
    from coding_agent_playbook.sources.filesystem import _dump_toml

    with pytest.raises(TypeError, match=r"single-level mappings"):
        _dump_toml({"outer": {"inner": {"deep": 1}}})


def test_save_then_load_config_roundtrip(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    original = Config(
        schema_version=1,
        project=ProjectMeta(
            name="my-app",
            kind="python-application",
            description="An example app",
        ),
        engine_version="0.1.0a0",
        overlays_enabled=["playbook-rules-bnp"],
        adapters_enabled=["continue", "claude_code"],
        detector_cache={"python_version": "3.12"},
        user_choices={"banking_mode": True},
    )
    source.save_config(original)
    restored = source.load_config()
    assert restored == original


def test_load_lockfile_missing_returns_none(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    assert source.load_lockfile() is None


def test_save_then_load_lockfile_roundtrip(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    original = Lockfile(
        schema_version=1,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry(path=".continue/rules/a.md", sha256="aaa111", bytes=42),
            LockEntry(path=".claude/CLAUDE.md", sha256="bbb222", bytes=128),
        ],
    )
    source.save_lockfile(original)
    restored = source.load_lockfile()
    assert restored == original


def test_save_lockfile_emits_valid_toml(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    lockfile = Lockfile(
        schema_version=1,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry(path="AGENTS.md", sha256="abc", bytes=4),
        ],
    )
    source.save_lockfile(lockfile)
    written = tmp_path / ".coding-agent-playbook.lock"
    assert written.is_file()
    with written.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["schema_version"] == 1
    assert parsed["entries"][0]["path"] == "AGENTS.md"

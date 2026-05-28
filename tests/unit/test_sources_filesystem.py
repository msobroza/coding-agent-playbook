"""Tests for FileSystemArtifactSource and FileSystemStateSource (SPEC §20.3)."""

from __future__ import annotations

import importlib
import sys
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config import Config, ProjectMeta
from coding_agent_playbook.lockfile import LockEntry, Lockfile
from coding_agent_playbook.sources.filesystem import (
    FileSystemArtifactSource,
    FileSystemStateSource,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


RULE_MD_TEMPLATE = """\
---
id: {id}
name: {name}
description: {description}
scope: scoped
globs:
  - "**/*.py"
---
# {name}

Body.
"""


def _make_temp_package(
    tmp_path: Path,
    package_name: str,
    *,
    rules: dict[str, str] | None = None,
    prompts: dict[str, str] | None = None,
    skills: dict[str, str] | None = None,
) -> None:
    """Create a synthetic Python package on disk with resources/{rules,prompts,skills}.

    ``rules``/``prompts``/``skills`` map filename (e.g. ``"foo.md"``) to file body.
    For skills, the key is the skill directory name and the value is the SKILL body.
    """
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    resources_dir = pkg_dir / "resources"
    resources_dir.mkdir(exist_ok=True)
    if rules:
        rules_dir = resources_dir / "rules"
        rules_dir.mkdir(exist_ok=True)
        for filename, body in rules.items():
            (rules_dir / filename).write_text(body, encoding="utf-8")
    if prompts:
        prompts_dir = resources_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        for filename, body in prompts.items():
            (prompts_dir / filename).write_text(body, encoding="utf-8")
    if skills:
        skills_dir = resources_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for skill_name, body in skills.items():
            sk_dir = skills_dir / skill_name
            sk_dir.mkdir(exist_ok=True)
            (sk_dir / "SKILL.md").write_text(body, encoding="utf-8")
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
    # Clear any cached import so resources.files picks up the new tree.
    if package_name in sys.modules:
        importlib.reload(sys.modules[package_name])


@pytest.fixture
def temp_pkg_cleanup(tmp_path: Path) -> Iterator[None]:
    """Ensure sys.path / sys.modules are clean after each overlay test."""
    yield
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))
    for mod_name in list(sys.modules):
        if any(
            mod_name == prefix or mod_name.startswith(prefix + ".")
            for prefix in (
                "temp_overlay",
                "temp_overlay2",
                "temp_overlay_prompts",
                "temp_overlay_skills",
            )
        ):
            del sys.modules[mod_name]


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


def test_list_rules_walks_engine_package_resources(tmp_path: Path) -> None:
    # v1 of the engine ships zero rules (PR 13 adds them); confirm an empty
    # list is returned without raising.
    source = FileSystemArtifactSource(repo_root=tmp_path)
    rules = source.list_rules()
    assert rules == []


def test_list_rules_includes_overlay_packages(tmp_path: Path, temp_pkg_cleanup: None) -> None:
    _make_temp_package(
        tmp_path,
        "temp_overlay",
        rules={
            "foo.md": RULE_MD_TEMPLATE.format(id="foo", name="Foo rule", description="The foo"),
        },
    )
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_overlay"],
    )
    rules = source.list_rules()
    assert len(rules) == 1
    assert rules[0].frontmatter.id == "foo"
    assert rules[0].source_package == "temp_overlay"


def test_list_rules_includes_repo_local_playbook(tmp_path: Path) -> None:
    playbook_rules = tmp_path / "playbook" / "rules"
    playbook_rules.mkdir(parents=True)
    (playbook_rules / "bar.md").write_text(
        RULE_MD_TEMPLATE.format(id="bar", name="Bar rule", description="The bar"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    rules = source.list_rules()
    assert len(rules) == 1
    assert rules[0].frontmatter.id == "bar"
    assert rules[0].source_package == "<repo-local>"


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

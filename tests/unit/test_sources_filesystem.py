"""Tests for FileSystemArtifactSource and FileSystemStateSource (SPEC §20.3)."""

from __future__ import annotations

import importlib
import sys
import textwrap
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

PROMPT_MD_TEMPLATE = """\
---
id: {id}
name: {name}
description: {description}
slash: {id}
---
# {name}

Prompt body.
"""

SKILL_MD_TEMPLATE = """\
---
name: {name}
description: {description}
---
# {name}

Skill body.
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


def test_load_config_deep_merges_nested_dicts(tmp_path: Path) -> None:
    """Primary's detector_cache.frameworks is merged with override's, not
    replaced wholesale (code-quality review I3, coupled with C1's nested
    support)."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        textwrap.dedent("""
            schema_version = 1
            [project]
            name = "r"
            kind = "python-application"
            [engine]
            version = "0.1.0a0"
            [detector_cache]
            python_version = "3.12"
            [detector_cache.frameworks]
            fastapi = "0.110.0"
            pydantic = "2.9.2"
        """).strip()
    )
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(
        textwrap.dedent("""
            [detector_cache.frameworks]
            pydantic = "2.10.0"
            sqlalchemy = "2.0.40"
        """).strip()
    )
    config = FileSystemStateSource(repo_root=tmp_path).load_config()
    assert config.detector_cache["frameworks"] == {
        "fastapi": "0.110.0",  # from primary, preserved
        "pydantic": "2.10.0",  # overridden by local
        "sqlalchemy": "2.0.40",  # added by local
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


def test_dump_toml_rejects_mapping_deeper_than_two_levels() -> None:
    """Two levels of nesting (e.g. ``[detector_cache.frameworks]``) are
    accepted; deeper nesting must raise so a deeper schema fails loudly
    rather than silently producing ambiguous TOML."""
    from coding_agent_playbook.sources.filesystem import _dump_toml

    with pytest.raises(TypeError, match=r"at most 2-level nested mappings"):
        _dump_toml({"a": {"b": {"c": {"d": 1}}}})


def test_dump_toml_escapes_control_characters(tmp_path: Path) -> None:
    """Strings with control chars (\\x00, \\x08) must be \\uXXXX-escaped so
    the emitted TOML is valid (code-quality review I1)."""
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="r", kind="x", description="weird:\x00\x08"),
        engine_version="0.1.0a0",
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    source.save_config(config)
    # Must round-trip
    loaded = source.load_config()
    assert loaded.project.description == "weird:\x00\x08"


def test_save_then_load_config_roundtrip_with_nested_detector_cache(tmp_path: Path) -> None:
    """Config with a 2-level nested detector_cache.frameworks dict (the
    canonical SPEC §8.2 shape) must round-trip through TOML
    (code-quality review C1)."""
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="r", kind="python-application"),
        engine_version="0.1.0a0",
        detector_cache={
            "python_version": "3.12",
            "frameworks": {"fastapi": "0.110.0", "pydantic": "2.9.2"},
        },
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    source.save_config(config)
    assert source.load_config() == config


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


def test_filesystem_artifact_source_exposes_engine_package_property(tmp_path: Path) -> None:
    """``FileSystemArtifactSource.engine_package`` / ``overlay_packages`` are the
    canonical public read-only accessors.

    Reviewers flagged that ``commands/validate.py`` reaching into the private
    ``_engine_package`` / ``_overlay_packages`` attributes via ``getattr(...,
    default)`` would silently degrade if those names ever changed (overlay
    validation would just drop, with no test catching it). The fix exposes
    typed read-only properties; this test pins their contract so a rename
    requires updating both the property and its consumers together.
    """
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        engine_package="my_engine",
        overlay_packages=["a", "b"],
    )
    assert source.engine_package == "my_engine"
    assert source.overlay_packages == ("a", "b")


def test_filesystem_artifact_source_engine_package_is_read_only(tmp_path: Path) -> None:
    """Assigning to the public property must fail — the source's package
    membership is determined at construction and never mutated."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    with pytest.raises(AttributeError):
        source.engine_package = "other"  # type: ignore[misc]


def test_filesystem_artifact_source_overlay_packages_is_read_only(tmp_path: Path) -> None:
    """The overlay-packages accessor returns a tuple (not the internal list),
    so callers cannot append to it and mutate the source's walk order."""
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["pkg"],
    )
    assert isinstance(source.overlay_packages, tuple)
    with pytest.raises(AttributeError):
        source.overlay_packages = ("other",)  # type: ignore[misc]


def test_list_rules_walks_engine_package_resources(tmp_path: Path) -> None:
    # The engine ships rules under coding_agent_playbook/resources/rules/
    # (PR 13 onwards). Confirm the walker picks them up and tags them with
    # source_package="coding_agent_playbook".
    source = FileSystemArtifactSource(repo_root=tmp_path)
    rules = source.list_rules()
    engine_rules = [r for r in rules if r.source_package == "coding_agent_playbook"]
    assert engine_rules, "expected at least one engine-shipped rule"
    assert all(r.source_package == "coding_agent_playbook" for r in engine_rules)


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
    overlay_rules = [r for r in rules if r.source_package == "temp_overlay"]
    assert len(overlay_rules) == 1
    assert overlay_rules[0].frontmatter.id == "foo"


def test_dotted_directories_skipped_in_iter_md_files(tmp_path: Path) -> None:
    """Markdown files inside .venv/, .git/, etc. must not be picked up by
    the artifact walker (code-quality review M2)."""
    playbook_rules = tmp_path / "playbook" / "rules"
    playbook_rules.mkdir(parents=True)
    (playbook_rules / "real.md").write_text(
        RULE_MD_TEMPLATE.format(id="real", name="Real", description="Legit"),
        encoding="utf-8",
    )
    # Decoy: a markdown file inside a dotted directory that should be ignored.
    decoy_dir = playbook_rules / ".venv" / "site-packages" / "some_pkg"
    decoy_dir.mkdir(parents=True)
    (decoy_dir / "decoy.md").write_text(
        RULE_MD_TEMPLATE.format(id="decoy", name="Decoy", description="Should be skipped"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    rules = source.list_rules()
    repo_local_ids = [r.frontmatter.id for r in rules if r.source_package == "<repo-local>"]
    assert repo_local_ids == ["real"]


def test_list_rules_includes_repo_local_playbook(tmp_path: Path) -> None:
    playbook_rules = tmp_path / "playbook" / "rules"
    playbook_rules.mkdir(parents=True)
    (playbook_rules / "bar.md").write_text(
        RULE_MD_TEMPLATE.format(id="bar", name="Bar rule", description="The bar"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    rules = source.list_rules()
    repo_local_rules = [r for r in rules if r.source_package == "<repo-local>"]
    assert len(repo_local_rules) == 1
    assert repo_local_rules[0].frontmatter.id == "bar"


def test_list_prompts_walks_same_layout(tmp_path: Path, temp_pkg_cleanup: None) -> None:
    _make_temp_package(
        tmp_path,
        "temp_overlay_prompts",
        prompts={
            "gen.md": PROMPT_MD_TEMPLATE.format(
                id="gen", name="Generate", description="Make stuff"
            ),
        },
    )
    # repo-local prompts under playbook/prompts/
    repo_prompts = tmp_path / "playbook" / "prompts"
    repo_prompts.mkdir(parents=True)
    (repo_prompts / "local.md").write_text(
        PROMPT_MD_TEMPLATE.format(id="local", name="Local", description="Repo prompt"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_overlay_prompts"],
    )
    prompts = source.list_prompts()
    ids = {p.frontmatter.id for p in prompts}
    assert ids == {"gen", "local"}
    by_id = {p.frontmatter.id: p for p in prompts}
    assert by_id["gen"].source_package == "temp_overlay_prompts"
    assert by_id["local"].source_package == "<repo-local>"


def test_list_skills_constructs_from_directory(tmp_path: Path, temp_pkg_cleanup: None) -> None:
    _make_temp_package(
        tmp_path,
        "temp_overlay_skills",
        skills={
            "my-skill": SKILL_MD_TEMPLATE.format(name="My skill", description="Does things"),
        },
    )
    # Add a `scripts/` sibling dir to verify it gets surfaced on the Skill.
    scripts_dir = tmp_path / "temp_overlay_skills" / "resources" / "skills" / "my-skill" / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "helper.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_overlay_skills"],
    )
    skills = source.list_skills()
    assert len(skills) == 1
    skill = skills[0]
    assert skill.frontmatter["name"] == "My skill"
    assert skill.source_package == "temp_overlay_skills"
    assert skill.scripts_dir is not None
    assert skill.scripts_dir.name == "scripts"
    assert skill.references_dir is None


def test_list_eval_tasks_returns_empty_for_engine_only(tmp_path: Path) -> None:
    """The engine ships zero eval tasks in v1 (PR 13 adds them); confirm the
    method returns ``[]`` without raising. The full walk (overlay + repo-local)
    is covered in :mod:`tests.unit.test_filesystem_list_eval_tasks`."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    assert source.list_eval_tasks() == []


def test_resource_subdir_returns_none_for_missing_package() -> None:
    from coding_agent_playbook.sources.filesystem import _resource_subdir

    assert _resource_subdir("nonexistent_pkg_xyz_abc_999", "rules") is None


def test_iter_skills_skips_directories_without_skill_md(
    tmp_path: Path, temp_pkg_cleanup: None
) -> None:
    # Create a package with one valid skill dir and one bare dir (no SKILL.md).
    _make_temp_package(
        tmp_path,
        "temp_overlay_skills",
        skills={
            "good": SKILL_MD_TEMPLATE.format(name="Good", description="ok"),
        },
    )
    bare = tmp_path / "temp_overlay_skills" / "resources" / "skills" / "bare"
    bare.mkdir()
    (bare / "notes.txt").write_text("no SKILL here", encoding="utf-8")
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_overlay_skills"],
    )
    skills = source.list_skills()
    assert len(skills) == 1
    assert skills[0].frontmatter["name"] == "Good"


def test_list_skills_includes_repo_local_playbook_skills(tmp_path: Path) -> None:
    repo_local = tmp_path / "playbook" / "skills" / "local-skill"
    repo_local.mkdir(parents=True)
    (repo_local / "SKILL.md").write_text(
        SKILL_MD_TEMPLATE.format(name="Local skill", description="Repo-local"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    skills = source.list_skills()
    assert len(skills) == 1
    assert skills[0].source_package == "<repo-local>"


def test_dump_toml_rejects_nested_dict_in_list_of_tables() -> None:
    from coding_agent_playbook.sources.filesystem import _dump_toml

    with pytest.raises(TypeError, match=r"single-level mappings"):
        _dump_toml({"items": [{"key": {"deeper": 1}}]})


def test_entry_point_registers_filesystem_artifact_source() -> None:
    from importlib import metadata

    eps = metadata.entry_points(group="coding_agent_playbook.artifact_sources")
    by_name = {ep.name: ep for ep in eps}
    assert "filesystem" in by_name
    loaded = by_name["filesystem"].load()
    assert loaded is FileSystemArtifactSource


def test_entry_point_registers_filesystem_state_source() -> None:
    from importlib import metadata

    eps = metadata.entry_points(group="coding_agent_playbook.state_sources")
    by_name = {ep.name: ep for ep in eps}
    assert "filesystem" in by_name
    loaded = by_name["filesystem"].load()
    assert loaded is FileSystemStateSource


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

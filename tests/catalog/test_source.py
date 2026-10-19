"""Tests for FileSystemArtifactSource (SPEC §20.3)."""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.source import (
    FileSystemArtifactSource,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


RULE_MD_TEMPLATE = """\
---
id: {id}
name: {name}
description: {description}
scope: scoped
skill: python-coding
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


def test_filesystem_artifact_source_exposes_engine_package_property(tmp_path: Path) -> None:
    """``FileSystemArtifactSource.engine_package`` / ``overlay_packages`` are the
    canonical public read-only accessors.

    Reviewers flagged that ``validation/checks.py`` reaching into the private
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
    # The engine ships rules under catalog/core/rules/ (resolved through
    # catalog). Confirm the walker picks them up and tags them with
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
    non_engine = [p for p in prompts if p.source_package != "coding_agent_playbook"]
    ids = {p.frontmatter.id for p in non_engine}
    assert ids == {"gen", "local"}
    by_id = {p.frontmatter.id: p for p in non_engine}
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
    skills = [s for s in source.list_skills() if s.source_package == "temp_overlay_skills"]
    assert len(skills) == 1
    skill = skills[0]
    assert skill.frontmatter["name"] == "My skill"
    assert skill.source_package == "temp_overlay_skills"
    assert skill.scripts_dir is not None
    assert skill.scripts_dir.name == "scripts"
    assert skill.references_dir is None


def test_resource_subdir_returns_none_for_missing_package() -> None:
    from coding_agent_playbook.catalog.source import _resource_subdir

    assert _resource_subdir("nonexistent_pkg_xyz_abc_999", "rules") is None


@pytest.mark.parametrize("init", ["raise RuntimeError('boom')\n", "import cap_missing_dep\n"])
def test_resource_subdir_skips_a_package_that_fails_at_import(
    init: str, make_package: Callable[..., str]
) -> None:
    """Discovery skips it like a missing package (it used to crash with a traceback);
    the shared ``validation.preflight`` check is what names it and its error."""
    from coding_agent_playbook.catalog.source import _resource_subdir

    name = make_package("cap_raising_overlay", init=init, resources=True)

    assert _resource_subdir(name, "rules") is None
    assert _resource_subdir("", "rules") is None  # an empty name raises ValueError


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
    skills = [s for s in source.list_skills() if s.source_package == "temp_overlay_skills"]
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
    skills = [s for s in source.list_skills() if s.source_package == "<repo-local>"]
    assert len(skills) == 1
    assert skills[0].frontmatter["name"] == "Local skill"


def test_entry_point_registers_filesystem_artifact_source() -> None:
    from importlib import metadata

    eps = metadata.entry_points(group="coding_agent_playbook.artifact_sources")
    by_name = {ep.name: ep for ep in eps}
    assert "filesystem" in by_name
    loaded = by_name["filesystem"].load()
    assert loaded is FileSystemArtifactSource

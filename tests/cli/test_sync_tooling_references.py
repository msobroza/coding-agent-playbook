"""End-to-end ``playbook sync`` of the gated python-tooling member rules (specs/prS-skills-context.md 11.3).

``python-tooling`` has four ungated members (static checks, ruff lint, mypy and
ruff format), so the skill is written in every Python repo. Its other members follow
their gates: the two uv rules need a ``uv.lock`` (``package_manager: uv``). The Pydantic
boundaries rule moved to ``python-coding`` (prU D24, L0-15) and keeps its gate,
a declared ``pydantic`` dependency (``has_framework: ["pydantic"]``). Each test
syncs a synthetic repo with the ``claude_code`` adapter only and reads the rule
ids a skill holds as rule files.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands import sync as _sync

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["claude_code"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""
_SKILLS_DIR: Final = (".claude", "skills")
_TOOLING: Final = "python-tooling"
_UV_WORKFLOW: Final = "python-uv-workflow"
_PYDANTIC_BOUNDARIES: Final = "pydantic-boundaries"
#: python-tooling's ungated members, sorted: written in every Python repo.
_UNGATED: Final = ["mypy-type-checking", "python-static-checks", "ruff-format", "ruff-lint"]


def _python_repo(root: Path, make_synthetic_repo: Callable[..., Path], **extras: object) -> Path:
    """A fresh synthetic repo under ``root``; ``extras`` go to ``make_synthetic_repo``."""
    root.mkdir()
    return make_synthetic_repo(root, config_text=_CONFIG, **extras)


def _skill_rule_ids(repo: Path, skill_id: str) -> list[str]:
    """The sorted rule ids synced ``repo``'s ``skill_id`` holds as rule files; ``[]`` if unwritten."""
    rules = repo.joinpath(*_SKILLS_DIR, skill_id, "rules")
    if not rules.is_dir():
        return []
    return sorted(path.name.removesuffix(".md") for path in rules.iterdir())


def _synced_tooling_rule_ids(repo: Path) -> list[str]:
    """Sync ``repo`` and return the sorted rule ids ``python-tooling`` holds as rule files."""
    assert _sync.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0
    return _skill_rule_ids(repo, _TOOLING)


def test_python_tooling_exists_in_a_plain_python_repo(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """No framework and no uv.lock: the four ungated members alone write the skill."""
    repo = _python_repo(tmp_path / "plain", make_synthetic_repo)

    assert _synced_tooling_rule_ids(repo) == _UNGATED
    skill_md = repo.joinpath(*_SKILLS_DIR, _TOOLING, "SKILL.md")
    # The frontmatter folds the long description; compare its words.
    words = " ".join(skill_md.read_text(encoding="utf-8").split())
    assert "Covers linting, type checking, formatting." in words
    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "- Tool configuration and pyproject.toml: skill `python-tooling`" in agents_md


def test_uv_workflow_rule_only_in_uv_repos(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    uv_repo = _python_repo(tmp_path / "uv", make_synthetic_repo)
    (uv_repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    pip_repo = _python_repo(tmp_path / "pip", make_synthetic_repo)
    (pip_repo / "requirements.txt").write_text("httpx>=0.27\n", encoding="utf-8")

    assert _UV_WORKFLOW in _synced_tooling_rule_ids(uv_repo)
    assert _UV_WORKFLOW not in _synced_tooling_rule_ids(pip_repo)


def test_pydantic_boundaries_needs_declared_pydantic(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """R5-3: a FastAPI repo that gets Pydantic only transitively gets no Pydantic rule.

    The rule lives in python-coding now; the FastAPI rules in web-application, and
    python-tooling holds neither.
    """
    declared = _python_repo(
        tmp_path / "declared", make_synthetic_repo, pyproject_extras={"dependencies": ["pydantic"]}
    )
    transitive = _python_repo(
        tmp_path / "transitive", make_synthetic_repo, pyproject_extras={"dependencies": ["fastapi"]}
    )

    assert _PYDANTIC_BOUNDARIES not in _synced_tooling_rule_ids(declared)
    assert _PYDANTIC_BOUNDARIES in _skill_rule_ids(declared, "python-coding")
    assert _synced_tooling_rule_ids(transitive) == _UNGATED
    assert "fastapi-app-wiring" in _skill_rule_ids(transitive, "web-application")
    assert _PYDANTIC_BOUNDARIES not in _skill_rule_ids(transitive, "python-coding")

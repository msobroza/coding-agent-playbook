"""End-to-end ``playbook sync`` of the core skills in a synthetic repo (spec 6.10 items 7, C7).

Core ships ``python-coding``, ``python-testing``, ``python-tooling`` and
``ml-data``; each is written only while one of its member rules passes
``applies_if`` (ADR 0001). ``python-tooling``'s members are the two FastAPI rules,
so the skill follows the ``fastapi`` dependency in and out of the repo. The
"Where guidance lives" map in ``AGENTS.md`` names only skills a sync writes, so
it is absent when no enabled adapter has a native skill root.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import FileSystemStateSource
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_TOOLING = "python-tooling"

_CONFIG = """\
schema_version = 1
adapters_enabled = {adapters}
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
_SKILL_ADAPTERS = '["continue", "claude_code", "opencode", "shared_skills"]'


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=False)


def _set_dependencies(repo: Path, dependencies: str) -> None:
    """Rewrite the synthetic ``pyproject.toml`` with ``dependencies`` (a TOML array)."""
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "synthetic"\nrequires-python = ">=3.12"\n'
        f"dependencies = {dependencies}\n",
        encoding="utf-8",
    )


def _tooling_lock_paths(repo: Path) -> list[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return sorted(entry.path for entry in lockfile.entries if f"/{_TOOLING}/" in entry.path)


def test_python_tooling_follows_the_fastapi_dependency_in_and_out(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(
        tmp_path,
        config_text=_CONFIG.format(adapters=_SKILL_ADAPTERS),
        pyproject_extras={"dependencies": ["click"]},
    )
    assert _sync.run(_ns(repo)) == 0
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root / _TOOLING).exists()] == []
    assert (repo / NATIVE_SKILL_ROOTS[0] / "python-coding" / "SKILL.md").is_file()

    _set_dependencies(repo, '["click", "fastapi"]')
    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        references = sorted(p.name for p in (repo / root / _TOOLING / "references").iterdir())
        assert references == ["fastapi-app-wiring.md", "fastapi-error-boundaries.md"], root
    assert "skill `python-tooling`" in (repo / "AGENTS.md").read_text(encoding="utf-8")

    _set_dependencies(repo, '["click"]')
    assert _sync.run(_ns(repo)) == 0
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root / _TOOLING).exists()] == []
    assert _tooling_lock_paths(repo) == []
    assert "skill `python-tooling`" not in (repo / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("adapters", ["[]", '["continue"]'], ids=["agents-md-only", "continue"])
def test_agents_md_has_no_where_map_when_no_enabled_adapter_writes_skills(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], adapters: str
) -> None:
    """Regression (C7): the map listed core skills that no enabled adapter wrote anywhere."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters=adapters))

    assert _sync.run(_ns(repo)) == 0

    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Project context" in agents_md
    assert "## Where guidance lives" not in agents_md
    assert "skill `python-coding`" not in agents_md
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root).exists()] == []

"""``playbook sync`` never publishes tool caches a skill subtree picked up (SPEC §10.8).

Regression (PR #266 CI): CI runs ``ruff check .`` before pytest, and ruff plants a
``.ruff_cache/`` (with its own ``.gitignore``) next to every ``pyproject.toml`` it
finds, including web-application's ``examples/fastapi-hotel-api/``. Sync copied
that cache into every skills root; once fastapi left the repo the cache's
``.gitignore`` was never orphaned (a user/state file name), so
``.claude/skills/web-application/`` survived its skill on CI only.
"""

from __future__ import annotations

import argparse
import shutil
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.config.files import FileSystemStateSource

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_SKILL_ROOTS: Final = (".claude/skills", ".opencode/skills", ".agents/skills")
_CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]
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
#: What ruff, pytest, mypy, hypothesis and ``uv run`` leave next to an example's pyproject.
_TOOL_CACHE_FILES: Final = (
    "examples/app/.ruff_cache/.gitignore",
    "examples/app/.ruff_cache/CACHEDIR.TAG",
    "examples/app/.ruff_cache/0.17.0/17953856704063259531",
    "examples/app/.pytest_cache/v/cache/nodeids",
    "examples/app/.mypy_cache/3.12/app.data.json",
    "examples/app/.hypothesis/examples/ab/cd",
    "examples/app/.venv/pyvenv.cfg",
)


def _write_skill_with_tool_caches(repo: Path) -> Path:
    """A repo-local skill whose example holds its code plus every tool cache."""
    skill_dir = repo / "playbook" / "skills" / "hotel-api"
    files = {
        "SKILL.md": "---\nid: hotel-api\nname: hotel-api\ndescription: Hotel API\n---\nSee it.\n",
        "examples/app/pyproject.toml": '[project]\nname = "app"\n',
        "examples/app/main.py": "print('app')\n",
        **dict.fromkeys(_TOOL_CACHE_FILES, "cache\n"),
    }
    for rel, text in files.items():
        (skill_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill_dir / rel).write_text(text, encoding="utf-8")
    return skill_dir


def _sync(repo: Path) -> None:
    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0


def _lock_paths(repo: Path) -> list[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return sorted(entry.path for entry in lockfile.entries if "/hotel-api/" in entry.path)


def test_sync_copies_an_example_without_its_tool_caches(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG)
    _write_skill_with_tool_caches(repo)

    _sync(repo)

    for root in _SKILL_ROOTS:
        example = repo / root / "hotel-api" / "examples" / "app"
        assert sorted(p.name for p in example.iterdir()) == ["main.py", "pyproject.toml"], root
    assert not [path for path in _lock_paths(repo) if "cache" in path or ".venv" in path]


def test_a_removed_skill_leaves_no_directory_behind_despite_its_tool_caches(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG)
    skill_dir = _write_skill_with_tool_caches(repo)
    _sync(repo)

    shutil.rmtree(skill_dir)
    _sync(repo)

    for root in _SKILL_ROOTS:
        assert not (repo / root / "hotel-api").exists(), root
    assert _lock_paths(repo) == []

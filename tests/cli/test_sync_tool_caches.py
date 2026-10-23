"""``playbook sync`` never publishes tool caches a skill subtree picked up (SPEC §10.8).

Regression (PR #266 CI): CI runs ``ruff check .`` before pytest, and ruff plants a
``.ruff_cache/`` (with its own ``.gitignore``) next to every ``pyproject.toml`` it
finds, including web-application's ``examples/fastapi-hotel-api/``. Sync copied
that cache into every skills root; once fastapi left the repo the cache's
``.gitignore`` was never orphaned (any ``.gitignore`` was exempt by name), so
``.claude/skills/web-application/`` survived its skill on CI only.
"""

from __future__ import annotations

import argparse
import shutil
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.generated_output import source_files
from coding_agent_playbook.generated_output.source_files import SKIPPED_DIR_NAMES
from tests.cli.skill_sync_kit import SHARED_SKILLS_CONFIG, lock_entry_paths
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

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
_AUTHORED_FILES: Final = ("SKILL.md", "examples/app/main.py", "examples/app/pyproject.toml")


def _write_skill(repo: Path, *extra: str) -> Path:
    """A repo-local skill whose example holds its code plus each ``extra`` file."""
    skill_dir = repo / "playbook" / "skills" / "hotel-api"
    files = {
        "SKILL.md": "---\nid: hotel-api\nname: hotel-api\ndescription: Hotel API\n---\nSee it.\n",
        "examples/app/pyproject.toml": '[project]\nname = "app"\n',
        "examples/app/main.py": "print('app')\n",
        **dict.fromkeys(extra, "cache\n"),
    }
    for rel, text in files.items():
        (skill_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill_dir / rel).write_text(text, encoding="utf-8")
    return skill_dir


def _sync(repo: Path) -> None:
    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0


def _skill_lock_paths(repo: Path) -> set[str]:
    return {path for path in lock_entry_paths(repo) if "/hotel-api/" in path}


def _assert_skill_gone(repo: Path) -> None:
    for root in NATIVE_SKILL_ROOTS:
        assert not (repo / root / "hotel-api").exists(), root
    assert _skill_lock_paths(repo) == set()


def test_sync_copies_an_example_without_its_tool_caches(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=SHARED_SKILLS_CONFIG)
    _write_skill(repo, *_TOOL_CACHE_FILES)

    _sync(repo)

    for root in NATIVE_SKILL_ROOTS:
        example = repo / root / "hotel-api" / "examples" / "app"
        assert sorted(p.name for p in example.iterdir()) == ["main.py", "pyproject.toml"], root
    expected = {f"{root}/hotel-api/{rel}" for root in NATIVE_SKILL_ROOTS for rel in _AUTHORED_FILES}
    assert _skill_lock_paths(repo) == expected


def test_a_removed_skill_leaves_no_directory_behind_despite_its_tool_caches(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=SHARED_SKILLS_CONFIG)
    skill_dir = _write_skill(repo, *_TOOL_CACHE_FILES)
    _sync(repo)

    shutil.rmtree(skill_dir)
    _sync(repo)

    _assert_skill_gone(repo)


def test_a_removed_skill_whose_example_ships_a_gitignore_leaves_no_directory(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Regression (PR #266 CI): an owned ``.gitignore`` below the repo root was
    exempt from orphaning by its name, so it kept the removed skill's directory."""
    repo = make_synthetic_repo(tmp_path, config_text=SHARED_SKILLS_CONFIG)
    skill_dir = _write_skill(repo, "examples/app/.gitignore")
    _sync(repo)
    assert f"{NATIVE_SKILL_ROOTS[0]}/hotel-api/examples/app/.gitignore" in lock_entry_paths(repo)

    shutil.rmtree(skill_dir)
    _sync(repo)

    _assert_skill_gone(repo)


def test_sync_removes_the_tool_caches_an_earlier_engine_copied(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo synced before caches were skipped owns ``.ruff_cache/.gitignore``; the
    next sync orphans it with the rest of the cache, then the skill goes cleanly."""
    repo = make_synthetic_repo(tmp_path, config_text=SHARED_SKILLS_CONFIG)
    skill_dir = _write_skill(repo, *_TOOL_CACHE_FILES)
    with monkeypatch.context() as patch:  # the pre-fix engine: copy every file
        patch.setattr(source_files, "is_unauthored_path", lambda _relative: False)
        _sync(repo)
    assert any(".ruff_cache" in path for path in _skill_lock_paths(repo))

    _sync(repo)

    for root in NATIVE_SKILL_ROOTS:
        example = repo / root / "hotel-api" / "examples" / "app"
        assert not SKIPPED_DIR_NAMES.intersection(p.name for p in example.iterdir()), root
    shutil.rmtree(skill_dir)
    _sync(repo)
    _assert_skill_gone(repo)

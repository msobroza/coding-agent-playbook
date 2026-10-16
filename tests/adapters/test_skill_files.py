"""Tests for the skill-subtree copy rule shared by every skill writer (SPEC §10.8).

Regression for review finding 8: Python bytecode caches next to a skill's
scripts (written by ``pip install`` byte-compilation or an in-process import)
were synced into every consumer skill root and listed in the lockfile.
"""

from __future__ import annotations

from pathlib import Path, PurePath

import pytest

from coding_agent_playbook.adapters._skill_files import is_bytecode_cache, skill_subtree_files


@pytest.mark.parametrize(
    "relative",
    [
        "__pycache__/run.cpython-312.pyc",
        "__pycache__/run.cpython-312.opt-1.pyc",
        "__pycache__/notes.txt",  # anything inside a cache dir
        "sub/__pycache__/deep.cpython-313.pyc",
        "legacy.pyc",
        "optimized.pyo",
    ],
)
def test_is_bytecode_cache_flags_caches(relative: str) -> None:
    assert is_bytecode_cache(PurePath(relative))


@pytest.mark.parametrize(
    "relative",
    ["run.py", "run.pyi", "ext.pyd", ".hidden", ".env.example", "pyc-notes.md", "a.pyc.md"],
)
def test_is_bytecode_cache_keeps_everything_else(relative: str) -> None:
    # Conservative rule: only bytecode caches are skipped, never dot-files.
    assert not is_bytecode_cache(PurePath(relative))


def test_skill_subtree_files_skips_caches_and_returns_sorted_files(tmp_path: Path) -> None:
    for rel in ("run.py", "sub/deep.py", ".hidden", "__pycache__/run.cpython-312.pyc", "x.pyo"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x")

    names = [path.relative_to(tmp_path).as_posix() for path in skill_subtree_files(tmp_path)]

    assert names == [".hidden", "run.py", "sub/deep.py"]


def test_skill_subtree_files_judges_paths_relative_to_the_subtree(tmp_path: Path) -> None:
    """A source tree that itself sits under a ``__pycache__`` dir is still copied."""
    src = tmp_path / "__pycache__" / "scripts"
    src.mkdir(parents=True)
    (src / "run.py").write_bytes(b"print('hi')\n")

    assert skill_subtree_files(src) == [src / "run.py"]

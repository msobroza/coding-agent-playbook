"""Tests for the skill-subtree copy rule shared by every skill writer (SPEC §10.8).

``published_skill_files`` is that rule minus the files a failed ``applies_if``
withholds (prU D48, D58): the one list both skill writers copy.

Regression for review finding 8: Python bytecode caches next to a skill's
scripts (written by ``pip install`` byte-compilation or an in-process import)
were synced into every consumer skill root and listed in the lockfile.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path, PurePath

import pytest

from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.generated_output.source_files import (
    is_unauthored_path,
    published_skill_files,
    skill_subtree_files,
)


@pytest.mark.parametrize(
    "relative",
    [
        "__pycache__/run.cpython-312.pyc",
        "__pycache__/run.cpython-312.opt-1.pyc",
        "__pycache__/notes.txt",  # anything inside a cache dir
        "sub/__pycache__/deep.cpython-313.pyc",
        "legacy.pyc",
        "optimized.pyo",
        "app/.ruff_cache/.gitignore",  # ruff's, planted by `ruff check .` (PR #266 CI)
        ".ruff_cache/0.17.0/17953856704063259531",
        "app/.pytest_cache/v/cache/nodeids",
        ".mypy_cache/3.12/app.data.json",
        ".hypothesis/examples/ab/cd",
        "app/.venv/pyvenv.cfg",
    ],
)
def test_is_unauthored_path_flags_bytecode_tool_caches_and_venvs(relative: str) -> None:
    assert is_unauthored_path(PurePath(relative))


@pytest.mark.parametrize(
    "relative",
    [
        "run.py",
        "run.pyi",
        "ext.pyd",
        ".hidden",
        ".gitignore",
        ".env.example",
        "pyc-notes.md",
        "a.pyc.md",
        "app/main.py",
        "ruff_cache.md",
        "venv-notes.md",
    ],
)
def test_is_unauthored_path_keeps_authored_files(relative: str) -> None:
    # Conservative rule: only by-product directories and bytecode, never dot-files.
    assert not is_unauthored_path(PurePath(relative))


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


def _skill_with_examples(tmp_path: Path, *withheld: str) -> Skill:
    """A skill whose ``examples/`` holds ``app/main.py`` and ``cli/main.py``."""
    examples = tmp_path / "examples"
    for relative in ("app/main.py", "cli/main.py", "app/__pycache__/main.cpython-312.pyc"):
        (examples / relative).parent.mkdir(parents=True, exist_ok=True)
        (examples / relative).write_text("x = 1\n", encoding="utf-8")
    skill = Skill({"id": "x"}, "", None, None, "pkg", examples_dir=examples)
    return dataclasses.replace(skill, withheld_paths=withheld)


def test_published_skill_files_pairs_each_copyable_file_with_its_destination(
    tmp_path: Path,
) -> None:
    skill = _skill_with_examples(tmp_path)
    dst = tmp_path / "out" / "examples"

    pairs = published_skill_files(skill, "examples", dst)

    assert pairs == [
        (tmp_path / "examples" / "app" / "main.py", dst / "app" / "main.py"),
        (tmp_path / "examples" / "cli" / "main.py", dst / "cli" / "main.py"),
    ]


def test_published_skill_files_drops_what_a_failed_gate_withholds(tmp_path: Path) -> None:
    """prU D48, D58: the entry's path is skill-relative, so ``examples/cli`` covers cli/."""
    skill = _skill_with_examples(tmp_path, "examples/cli")

    pairs = published_skill_files(skill, "examples", tmp_path / "out")

    assert [src.relative_to(tmp_path).as_posix() for src, _ in pairs] == ["examples/app/main.py"]


def test_published_skill_files_is_empty_without_the_side_dir(tmp_path: Path) -> None:
    assert published_skill_files(_skill_with_examples(tmp_path), "scripts", tmp_path) == []

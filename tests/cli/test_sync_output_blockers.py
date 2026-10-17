"""Something in the way of sync output: named with exit 1, never a traceback (SPEC §12.2).

Regressions: a regular file (or a link to one) where an output directory goes
(``.claude/commands``, ``.continue``) made write-mode ``playbook sync`` crash
with a ``FileExistsError`` / ``NotADirectoryError`` traceback from ``mkdir``,
and a directory where an output file goes (``AGENTS.md/``) with an
``IsADirectoryError`` one. ``--check`` claimed sync would replace each of them,
which only the skill writer does, and only inside a skill directory (§10.8).
Write mode now stops naming the entry and leaves it alone; ``--check`` says the same.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _file_at_commands(repo: Path) -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").write_text("mine\n", encoding="utf-8")


def _link_to_a_file_at_commands(repo: Path) -> None:
    (repo / "NOTES.md").write_text("mine\n", encoding="utf-8")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to("../NOTES.md")


def _file_at_continue(repo: Path) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")


def _directory_at_agents_md(repo: Path) -> None:
    (repo / "AGENTS.md").mkdir()
    (repo / "AGENTS.md" / "mine.txt").write_text("mine\n", encoding="utf-8")


_CASES = {
    "file-at-commands": (
        _file_at_commands,
        ".claude/commands is not a directory, but sync writes generated files inside it",
        "Move or rename it (sync never deletes it)",
    ),
    "link-to-a-file-at-commands": (
        _link_to_a_file_at_commands,
        ".claude/commands is a symbolic link to ../NOTES.md, which is not a directory, "
        "but sync writes generated files inside it",
        "Re-point or remove the link",
    ),
    "file-at-continue": (
        _file_at_continue,
        ".continue is not a directory, but sync writes generated files inside it",
        "Move or rename it (sync never deletes it)",
    ),
    "directory-at-agents-md": (
        _directory_at_agents_md,
        "AGENTS.md is a directory, but sync writes a generated file at that path",
        "Move or rename it (sync never deletes it)",
    ),
}

_skip_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
_PARAMS = [pytest.param(name, marks=_skip_symlinks if "link" in name else ()) for name in _CASES]


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    (tmp_path / "repo").mkdir()
    return make_synthetic_repo(tmp_path / "repo", rules=[("style-guide", "Use spaces.\n")])


def _tree(repo: Path, names: tuple[str, ...]) -> dict[str, bytes | None]:
    """The user's entries this test planted, as bytes (``None`` for a directory)."""
    snapshot: dict[str, bytes | None] = {}
    for name in names:
        path = repo / name
        snapshot[name] = None if path.is_dir() else path.read_bytes()
    return snapshot


@pytest.mark.parametrize("case", _PARAMS)
def test_write_mode_names_what_is_in_the_way_and_leaves_it_alone(
    repo: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    plant, problem, remedy = _CASES[case]
    plant(repo)
    planted = (".claude/commands", ".continue", "AGENTS.md", "AGENTS.md/mine.txt")
    present = tuple(name for name in planted if (repo / name).exists())
    before = _tree(repo, present)

    assert _sync.execute(repo, git=FakeGitClient()) == 1

    assert capsys.readouterr().err.splitlines() == [
        f"error: {problem}",
        "error: playbook sync stopped before finishing.",
        f"error: {remedy}, then re-run 'playbook sync'.",
    ]
    assert _tree(repo, present) == before


@pytest.mark.parametrize("case", _PARAMS)
def test_check_names_what_is_in_the_way_and_promises_no_replacement(
    repo: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    plant, problem, remedy = _CASES[case]
    plant(repo)

    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1

    out = capsys.readouterr().out
    assert f"    Missing on disk: {problem}.\n    {remedy}, then run 'playbook sync'." in out
    assert "replaces it only" not in out

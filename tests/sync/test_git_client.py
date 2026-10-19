"""Tests for the read-only git interface (``coding_agent_playbook.sync.git_client``).

The real-git tests build throwaway repos in ``tmp_path`` (cheap, local) under
the ``hermetic_git_env`` fixture and are skipped when git is not on PATH.
Failure modes are exercised without patching :mod:`subprocess`: a missing
executable, a non-repository directory, and a stub executable that sleeps.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.sync.git_client import (
    GIT_TIMEOUT_SECONDS,
    GitClient,
    SubprocessGitClient,
)
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from pathlib import Path

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=10)


def _write(repo: Path, rel: str, text: str = "x\n") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


@pytest.fixture
def repo(tmp_path: Path, hermetic_git_env: None) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def test_clients_satisfy_the_protocol() -> None:
    clients: list[GitClient] = [SubprocessGitClient(), FakeGitClient()]
    assert len(clients) == 2
    assert GIT_TIMEOUT_SECONDS == 10.0


@needs_git
def test_tracked_paths_lists_only_tracked_candidates(repo: Path) -> None:
    _write(repo, "AGENTS.md")
    _write(repo, ".claude/CLAUDE.md")
    _write(repo, "untracked.md")
    _git(repo, "add", "AGENTS.md", ".claude/CLAUDE.md")
    tracked = SubprocessGitClient().tracked_paths(
        repo, ["AGENTS.md", ".claude/CLAUDE.md", "untracked.md", "missing.md"]
    )
    assert sorted(tracked or []) == [".claude/CLAUDE.md", "AGENTS.md"]


@needs_git
def test_tracked_paths_uses_literal_pathspecs(repo: Path) -> None:
    _write(repo, "we*ird.md")
    _write(repo, "weXird.md")
    _git(repo, "add", ".")
    client = SubprocessGitClient()
    assert client.tracked_paths(repo, ["we*ird.md"]) == ["we*ird.md"]
    assert client.tracked_paths(repo, ["we*"]) == []


@needs_git
def test_tracked_paths_ignore_case_returns_the_index_spelling(repo: Path) -> None:
    """Pathspecs are case-sensitive even under ``core.ignorecase``: the index entry
    ``Demo/x.py`` is invisible to ``demo/x.py`` unless asked with ``:(icase)``."""
    _write(repo, "Demo/x.py")
    _write(repo, "Demo/we*ird.py")
    _write(repo, "Demo/weXird.py")
    _git(repo, "add", ".")
    client = SubprocessGitClient()
    assert client.tracked_paths(repo, ["demo/x.py"]) == []
    assert client.tracked_paths(repo, ["demo/x.py"], ignore_case=True) == ["Demo/x.py"]
    # Still literal: ``*`` never globs.
    assert client.tracked_paths(repo, ["demo/we*ird.py"], ignore_case=True) == ["Demo/we*ird.py"]
    assert client.tracked_paths(repo, ["demo/we*"], ignore_case=True) == []


def test_tracked_paths_with_no_candidates_skips_git(tmp_path: Path) -> None:
    client = SubprocessGitClient(executable=str(tmp_path / "no-such-git"))
    assert client.tracked_paths(tmp_path, []) == []


@needs_git
def test_staged_paths_reports_added_and_modified(repo: Path) -> None:
    _write(repo, "a.md")
    _write(repo, "sub/b.md")
    _git(repo, "add", ".")
    assert sorted(SubprocessGitClient().staged_paths(repo) or []) == ["a.md", "sub/b.md"]


@needs_git
def test_staged_paths_excludes_staged_deletions(repo: Path) -> None:
    """``git rm --cached <output>`` (the documented migration) must not trip the guard."""
    _write(repo, "AGENTS.md")
    _write(repo, "keep.md")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--no-verify", "-m", "init")
    _git(repo, "rm", "-q", "--cached", "AGENTS.md")
    _write(repo, "keep.md", "changed\n")
    _git(repo, "add", "keep.md")
    assert SubprocessGitClient().staged_paths(repo) == ["keep.md"]


@needs_git
def test_staged_paths_are_relative_to_a_subdirectory_root(repo: Path) -> None:
    _write(repo, "outside.md")
    _write(repo, "app/AGENTS.md")
    _git(repo, "add", ".")
    assert SubprocessGitClient().staged_paths(repo / "app") == ["AGENTS.md"]


@needs_git
@pytest.mark.usefixtures("hermetic_git_env")
def test_not_a_repository_returns_none(tmp_path: Path) -> None:
    client = SubprocessGitClient()
    assert client.tracked_paths(tmp_path, ["AGENTS.md"]) is None
    assert client.staged_paths(tmp_path) is None


def test_missing_git_executable_returns_none(tmp_path: Path) -> None:
    client = SubprocessGitClient(executable=str(tmp_path / "no-such-git"))
    assert client.tracked_paths(tmp_path, ["AGENTS.md"]) is None
    assert client.staged_paths(tmp_path) is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell stub")
def test_timeout_returns_none(tmp_path: Path) -> None:
    slow_git = tmp_path / "slow-git"
    slow_git.write_text("#!/bin/sh\nexec sleep 5\n")
    slow_git.chmod(0o755)
    client = SubprocessGitClient(executable=str(slow_git), timeout=0.2)
    assert client.staged_paths(tmp_path) is None

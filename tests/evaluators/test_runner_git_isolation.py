"""Regression: the eval scratch repo never inherits the caller's repository location.

Git exports absolute ``GIT_DIR``/``GIT_INDEX_FILE`` to hooks run in a linked
worktree, and pre-commit passes them on to ``language: system`` hooks (the dev
``catalog-checks`` hook, or a consumer's ``playbook eval --run``). ``materialize``
runs ``git init``/``add -A``/``commit`` with ``cwd`` set to the scratch dir, so
with those variables inherited it committed the scratch tree onto the caller's
branch and overwrote the caller's index.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.runner import capture, materialize
from coding_agent_playbook.evals.task import EvalTask

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH"),
    pytest.mark.usefixtures("hermetic_git_env"),
]

_GIT_TIMEOUT_SECONDS = 30


def _git(cwd: Path, *args: str) -> str:
    """Run ``git <args>`` in ``cwd`` and return its stdout; raise on failure."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    ).stdout


def _linked_worktree(root: Path) -> Path:
    """Build a repo holding ``a`` and ``b`` and return a linked worktree of it."""
    main = root / "main"
    main.mkdir()
    _git(main, "init", "-q")
    (main / "a").write_text("a\n", encoding="utf-8")
    (main / "b").write_text("b\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", "base")
    worktree = root / "wt"
    _git(main, "worktree", "add", "-q", "-b", "wtb", str(worktree))
    return worktree


def _head_and_index(worktree: Path) -> tuple[str, str]:
    """The worktree's ``HEAD`` commit and its staged entries."""
    return _git(worktree, "rev-parse", "HEAD"), _git(worktree, "ls-files", "--stage")


def _task(task_dir: Path) -> EvalTask:
    """A task whose ``setup/`` holds one file and no ``pyproject.toml`` (no ``uv``)."""
    (task_dir / "setup").mkdir(parents=True)
    (task_dir / "setup" / "app.py").write_text("x = 1\n", encoding="utf-8")
    data = {
        "id": "t-git-isolation",
        "prompt_id": "refactor",
        "description": "scratch repo isolation",
        "gate": {"expr": "app", "bind": {"app": {"check": "file_exists", "path": "app.py"}}},
        "verdict": {"trial": "gate"},
    }
    return EvalTask.from_dict(data, source_path=task_dir / "task.toml", source_package="<test>")


def test_hook_git_env_does_not_redirect_the_scratch_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _linked_worktree(tmp_path)
    before = _head_and_index(worktree)
    gitdir = _git(worktree, "rev-parse", "--absolute-git-dir").strip()
    task = _task(tmp_path / "task")
    # What git exports to a hook running inside a linked worktree.
    monkeypatch.setenv("GIT_DIR", gitdir)
    monkeypatch.setenv("GIT_INDEX_FILE", f"{gitdir}/index")

    baseline = materialize(task, tmp_path / "scratch")
    (baseline.repo_root / "new.py").write_text("y = 2\n", encoding="utf-8")
    candidate = capture(baseline.repo_root, baseline, "transcript")

    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_INDEX_FILE")
    assert _head_and_index(worktree) == before
    assert (baseline.repo_root / ".git").is_dir()
    assert _git(baseline.repo_root, "rev-parse", "HEAD").strip() == baseline.commit
    assert candidate.changed_files == ["new.py"]

"""``SafeGit.commit_log``: a range's commits with their committer dates (specs/prK-hook-pack.md §F.4.2).

One hardened ``git log -z`` call over a real repository (isolated through the
hermetic git env), and the lazy ``GitPort`` delegating it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo
from coding_agent_playbook.hook_runtime.dispatch.ports import LazyGit
from coding_agent_playbook.hook_runtime.git.safe_git import GitError, LoggedCommit, SafeGit
from tests.hook_runtime.fakes import FakeGit
from tests.hook_runtime.guard_repo import GuardRepo

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc


def _safe_git(root: Path, real_proc: SubprocessProc) -> SafeGit:
    repo = find_repo(str(root))
    assert repo is not None
    return SafeGit(repo, proc=real_proc, env=dict(os.environ))


def test_commit_log_reads_committer_dates_and_messages(
    tmp_path: Path,
    real_git: Callable[..., str],
    real_proc: SubprocessProc,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "base", cwd=root)
    real_git("branch", "upstream", cwd=root)
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-01T09:00:00+02:00")
    real_git("commit", "-q", "--allow-empty", "-m", "fix: old", "-m", "body", cwd=root)
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-10-16T10:00:00+02:00")
    real_git("commit", "-q", "--allow-empty", "-m", "Add thing.", cwd=root)

    log = _safe_git(root, real_proc).commit_log("upstream..HEAD", limit=10)

    assert [(c.committed, c.message) for c in log] == [
        ("2026-10-16T10:00:00+02:00", "Add thing.\n"),
        ("2026-09-01T09:00:00+02:00", "fix: old\n\nbody\n"),
    ]
    assert all(len(c.sha) == 40 for c in log)
    assert len(_safe_git(root, real_proc).commit_log("upstream..HEAD", limit=1)) == 1


def test_commit_log_reads_each_commit_parents(
    tmp_path: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    """A merge lists both parents (first parent first): the cut-over plan reads the topology."""
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "base", cwd=root)
    real_git("checkout", "-q", "-b", "feat", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "feat: one", cwd=root)
    feat = real_git("rev-parse", "HEAD", cwd=root)
    real_git("checkout", "-q", "main", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "Main squash (#1)", cwd=root)
    main = real_git("rev-parse", "HEAD", cwd=root)
    real_git("checkout", "-q", "feat", cwd=root)
    real_git("merge", "-q", "--no-ff", "-m", "Merge branch 'main' into feat", "main", cwd=root)

    merge, one = _safe_git(root, real_proc).commit_log("main..HEAD", limit=10)

    assert (merge.parents, one.sha) == ((feat, main), feat)
    assert len(one.parents) == 1


def test_commit_log_refuses_an_option_shaped_range(
    tmp_path: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", cwd=root)

    with pytest.raises(GitError, match="refusing revision"):
        _safe_git(root, real_proc).commit_log("--output=/tmp/x", limit=10)


def test_lazy_git_delegates_the_commit_log(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    commit = LoggedCommit("c0ffee", "2026-10-16T10:00:00Z", "feat: x\n")
    fake = FakeGit(logs={"origin/main..HEAD": (commit,)})
    lazy = LazyGit(
        GuardRepo.create(tmp_path).repo, runtime_deps(git=fake), state=None, secret_paths=None
    )

    assert lazy.commit_log("origin/main..HEAD", limit=200) == (commit,)
    assert fake.calls == [("commit_log", ("origin/main..HEAD",))]

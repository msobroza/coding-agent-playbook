"""The per-dispatch git memo (specs/prK-lifecycle-hooks.md §D.5.3, review finding #4).

A default-tier Stop asked git the same questions up to five times (``rev-parse
HEAD^{tree}``, ``ls-files --others``, ``diff HEAD``, the ``cat-file`` of each
touched file): every stage and hook built its own view of one working tree.
The dispatcher's ``LazyGit`` now builds a memoizing ``SafeGit``, so each
distinct read spawns once per dispatch; the CLI twins keep one spawn per call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime._git_memo import MemoGit
from coding_agent_playbook.hook_runtime._ports import LazyGit
from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.git import GitTimeout, SafeGit
from coding_agent_playbook.hook_runtime.paths import find_repo
from tests.hook_runtime.fakes import FakeProc

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.event import RepoInfo

GIT = "/usr/bin/git"
TREE = b"4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
DIFF = b"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def _layout(tmp_path: Path) -> RepoInfo:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    (root / ".git").mkdir(parents=True)
    repo = find_repo(str(root))
    assert repo is not None
    return repo


def _proc() -> FakeProc:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "config", "--get-regexp"], returncode=1)  # no filter driver
    proc.script(["git", "rev-parse"], stdout=TREE)
    proc.script(["git", "ls-files"], stdout=b"new.py\x00")
    proc.script(["git", "diff"], stdout=DIFF)
    proc.script(["git", "cat-file"], stdout=b"HEAD:a.py missing\n")
    proc.script(["git", "add"], stdout=b"")
    proc.script(["git", "write-tree"], stdout=TREE)
    return proc


def _spawns(proc: FakeProc, subcommand: str) -> int:
    return sum(1 for call in proc.calls if subcommand in call.argv)


def _safe_git(repo: RepoInfo, proc: FakeProc, *, memoize: bool) -> SafeGit:
    kind = MemoGit if memoize else SafeGit
    return kind(repo, proc=proc, env={"PATH": "/usr/bin"})


def test_memoizing_git_spawns_each_distinct_read_once(tmp_path: Path) -> None:
    proc = _proc()
    git = _safe_git(_layout(tmp_path), proc, memoize=True)

    trees = {git.head_tree() for _ in range(3)}
    untracked = {git.ls_untracked() for _ in range(2)}
    added, worktree = git.diff_added(), git.diff_worktree("HEAD")
    blobs = [git.cat_head("a.py"), git.cat_head("a.py"), git.cat_head("b.py")]

    assert trees == {TREE.decode().strip()} and untracked == {("new.py",)}
    assert [line.text for line in added] == ["x = 2"] and worktree.paths == ("a.py",)
    assert blobs == [None, None, None]
    assert _spawns(proc, "rev-parse") == 1
    assert _spawns(proc, "ls-files") == 1
    assert _spawns(proc, "diff") == 1  # diff_added and diff_worktree("HEAD") share one argv
    assert [call.input for call in proc.calls if "cat-file" in call.argv] == [
        b"HEAD:a.py\n",
        b"HEAD:b.py\n",
    ]


def test_without_the_memo_every_call_spawns(tmp_path: Path) -> None:
    proc = _proc()
    git = _safe_git(_layout(tmp_path), proc, memoize=False)

    git.head_tree()
    git.head_tree()

    assert _spawns(proc, "rev-parse") == 2


def test_a_failed_read_is_not_memoized(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "config", "--get-regexp"], returncode=1)
    proc.script(["git", "cat-file"], timeout=True)
    git = _safe_git(_layout(tmp_path), proc, memoize=True)

    for _ in range(2):
        with pytest.raises(GitTimeout):
            git.cat_head("a.py")

    assert _spawns(proc, "cat-file") == 2


def test_temp_index_calls_are_never_memoized(tmp_path: Path) -> None:
    proc = _proc()
    git = _safe_git(_layout(tmp_path), proc, memoize=True)

    first, second = git.fingerprint(), git.fingerprint()

    assert first == second and first is not None
    assert _spawns(proc, "add") == 2
    assert _spawns(proc, "write-tree") == 2
    assert sum(1 for call in proc.calls if call.argv[-2:] == ("ls-files", "-z")) == 2
    assert _spawns(proc, "--others") == 1  # the untracked listing reads no temp index
    assert _spawns(proc, "rev-parse") == 1


def test_the_dispatch_git_port_memoizes(tmp_path: Path) -> None:
    proc = _proc()
    deps = RuntimeDeps(env={"PATH": "/usr/bin"}, proc=proc)
    git = LazyGit(_layout(tmp_path), deps, state=None, secret_paths=None)

    git.head_tree()
    git.ls_untracked()
    git.head_tree()
    git.ls_untracked()

    assert _spawns(proc, "rev-parse") == 1
    assert _spawns(proc, "ls-files") == 1

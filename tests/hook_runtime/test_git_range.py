"""``SafeGit``'s range queries: default branch, merge base, range diff, blob at a revision.

These serve the off-workstation twins (``playbook gate-scan``, ``playbook ci``;
specs/prK-hook-pack.md §E.2, §F.5) and, later, E.4 and F.1, which share the one
default-branch resolver (``origin/HEAD``, then ``main``, then ``master``). The
twins run in CI, where no state directory exists, so every query works on a
stateless ``SafeGit``. ``FakeProc`` rows pin the argv; ``real_git`` rows pin
the answers against real repositories.
"""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime._git_parse import (
    AddedLine,
    DiffLines,
    RemovedLine,
    parse_diff_lines,
)
from coding_agent_playbook.hook_runtime._ports import LazyGit
from coding_agent_playbook.hook_runtime.git import GitError, SafeGit
from coding_agent_playbook.hook_runtime.git_range import pick_default_branch
from coding_agent_playbook.hook_runtime.paths import find_repo
from tests.hook_runtime.fakes import FakeGit, FakeProc
from tests.hook_runtime.guard_repo import GuardRepo

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.proc import SubprocessProc

GIT = "/usr/bin/git"


def _fake_safe_git(tmp_path: Path, proc: FakeProc) -> SafeGit:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    (root / ".git").mkdir(parents=True)
    repo = find_repo(str(root))
    assert repo is not None
    return SafeGit(repo, proc=proc, env={"PATH": "/usr/bin"})


def _hardened_proc() -> FakeProc:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "config", "--get-regexp"], returncode=1)
    return proc


# --- parsing ---------------------------------------------------------------------------------


def test_parse_diff_lines_tracks_removed_lines_and_paths() -> None:
    patch = (
        b"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        b"@@ -2,2 +2 @@\n-x = 0\n--- not a header\n+x = 1\n"
        b"diff --git a/gone.yaml b/gone.yaml\n--- a/gone.yaml\n+++ /dev/null\n@@ -1 +0,0 @@\n-k: v\n"
        b"diff --git a/new.txt b/new.txt\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+hi\n"
    )

    lines = parse_diff_lines(patch)

    assert lines.added == (AddedLine("a.py", 2, "x = 1"), AddedLine("new.txt", 1, "hi"))
    assert lines.removed == (
        RemovedLine("a.py", 2, "x = 0"),
        RemovedLine("a.py", 3, "-- not a header"),
        RemovedLine("gone.yaml", 1, "k: v"),
    )
    assert lines.paths == ("a.py", "gone.yaml", "new.txt")


# --- default branch --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("refs", "expected"),
    [
        (["refs/heads/master", "refs/heads/main"], "main"),
        (["refs/heads/main", "refs/remotes/origin/main"], "origin/main"),
        (["refs/heads/master", "refs/remotes/origin/master"], "origin/master"),
        (["refs/heads/master"], "master"),
        (["refs/heads/trunk"], None),
        ([], None),
    ],
)
def test_pick_default_branch_prefers_main_then_master(
    refs: list[str], expected: str | None
) -> None:
    assert pick_default_branch(refs) == expected


def test_default_branch_reads_refs_without_filter_discovery(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "symbolic-ref"], returncode=1)
    proc.script(["git", "for-each-ref"], stdout=b"refs/heads/main\n")

    assert _fake_safe_git(tmp_path, proc).default_branch() == "main"
    assert proc.calls[0].argv[-1] == "refs/remotes/origin/HEAD"
    assert proc.calls[1].argv[3:5] == ("for-each-ref", "--format=%(refname)")
    assert not any("--get-regexp" in call.argv for call in proc.calls)


def _commit(real_git: Callable[..., str], root: Path, message: str) -> str:
    real_git("commit", "-q", "--allow-empty", "-m", message, cwd=root)
    return real_git("rev-parse", "HEAD", cwd=root)


@pytest.fixture
def branchy(tmp_path: Path, real_git: Callable[..., str]) -> Path:
    """A repo on branch ``work`` with ``master`` and ``main`` behind it."""
    root = Path(os.path.realpath(tmp_path)) / "branchy"
    root.mkdir()
    real_git("init", "-q", "-b", "work", cwd=root)
    _commit(real_git, root, "one")
    real_git("branch", "master", cwd=root)
    _commit(real_git, root, "two")
    real_git("branch", "main", cwd=root)
    _commit(real_git, root, "three")
    return root


def _stateless(root: Path, real_proc: SubprocessProc) -> SafeGit:
    repo = find_repo(str(root))
    assert repo is not None
    return SafeGit(repo, proc=real_proc, env=dict(os.environ))  # no StateStore: as in CI


def test_default_branch_prefers_origin_head(
    branchy: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    git = _stateless(branchy, real_proc)
    assert git.default_branch() == "main"

    real_git("update-ref", "refs/remotes/origin/trunk", "HEAD", cwd=branchy)
    real_git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk", cwd=branchy)

    assert git.default_branch() == "origin/trunk"


def test_merge_base_and_show_on_a_stateless_safe_git(
    branchy: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    (branchy / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")
    real_git("add", "pyproject.toml", cwd=branchy)
    head = _commit(real_git, branchy, "config")
    git = _stateless(branchy, real_proc)

    main = real_git("rev-parse", "main", cwd=branchy)
    assert git.merge_base("main", "HEAD") == main
    assert git.show(head, "pyproject.toml") == b"[tool.mypy]\nstrict = true\n"
    assert git.show("main", "pyproject.toml") is None
    diff = git.diff_range("main", "HEAD")
    assert diff.added == (
        AddedLine("pyproject.toml", 1, "[tool.mypy]"),
        AddedLine("pyproject.toml", 2, "strict = true"),
    )
    assert diff.paths == ("pyproject.toml",)


def test_merge_base_none_without_shared_history(
    branchy: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    real_git("checkout", "-q", "--orphan", "island", cwd=branchy)
    _commit(real_git, branchy, "unrelated")

    assert _stateless(branchy, real_proc).merge_base("main", "HEAD") is None


def test_merge_base_of_an_unknown_ref_raises(branchy: Path, real_proc: SubprocessProc) -> None:
    with pytest.raises(GitError, match="merge-base exited 128"):
        _stateless(branchy, real_proc).merge_base("no-such-branch", "HEAD")


# --- argv -------------------------------------------------------------------------------------


def test_diff_range_is_hardened_and_parsed(tmp_path: Path) -> None:
    proc = _hardened_proc()
    proc.script(["git", "diff"], stdout=b"--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n")

    lines = _fake_safe_git(tmp_path, proc).diff_range("abc123", "HEAD")

    assert lines == DiffLines(
        (AddedLine("a.py", 1, "b"),), (RemovedLine("a.py", 1, "a"),), ("a.py",)
    )
    assert proc.calls[-1].argv[3:] == (
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "abc123",
        "HEAD",
        "-U0",
        "--no-color",
        "-M",
        "--no-relative",
        "--src-prefix=a/",
        "--dst-prefix=b/",
    )


def test_show_reads_one_blob_at_a_revision(tmp_path: Path) -> None:
    proc = _hardened_proc()
    proc.script(["git", "cat-file", "--batch"], stdout=b"ab12 blob 3\nx=1\n")

    git = _fake_safe_git(tmp_path, proc)

    assert git.show("HEAD~1", "pyproject.toml") == b"x=1"
    assert proc.calls[-1].input == b"HEAD~1:pyproject.toml\n"
    assert git.show("HEAD", "bad\nname") is None


@pytest.mark.parametrize("rev", ["--output=/tmp/x", "-p", "", "a b", "HEAD:path", "a\nb"])
def test_option_like_or_malformed_revision_is_refused(tmp_path: Path, rev: str) -> None:
    proc = _hardened_proc()
    git = _fake_safe_git(tmp_path, proc)

    with pytest.raises(GitError, match="refusing revision"):
        git.diff_range(rev, "HEAD")
    with pytest.raises(GitError, match="refusing revision"):
        git.merge_base("HEAD", rev)
    assert not any("diff" in call.argv or "merge-base" in call.argv for call in proc.calls)


def test_diff_worktree_diffs_a_revision_against_the_working_tree(tmp_path: Path) -> None:
    proc = _hardened_proc()
    proc.script(["git", "diff"], stdout=b"--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n")

    lines = _fake_safe_git(tmp_path, proc).diff_worktree("HEAD")

    assert lines.added == (AddedLine("a.py", 1, "b"),)
    assert proc.calls[-1].argv[3:7] == ("diff", "--no-ext-diff", "--no-textconv", "HEAD")
    assert "-U0" in proc.calls[-1].argv


def _tar(members: dict[str, bytes], links: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in links.items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            archive.addfile(info)
    return buffer.getvalue()


def test_archive_to_skips_secrets_and_anything_leaving_the_export(tmp_path: Path) -> None:
    proc = _hardened_proc()
    members = {"src/a.py": b"x = 1\n", ".env": b"TOKEN=1\n", "../escape.txt": b"!"}
    proc.script(["git", "archive"], stdout=_tar(members, {"etc": "/etc/passwd"}))
    export = tmp_path / "export"
    export.mkdir()

    written = _fake_safe_git(tmp_path, proc).archive_to(
        "HEAD", str(export), skip=lambda r: r == ".env"
    )

    assert written == 1
    assert sorted(p.relative_to(export).as_posix() for p in export.rglob("*")) == [
        "src",
        "src/a.py",
    ]
    assert not (tmp_path / "escape.txt").exists()
    assert proc.calls[-1].argv[-3:] == ("archive", "--format=tar", "HEAD")


# --- ports -----------------------------------------------------------------------------------


def test_lazy_git_delegates_the_range_queries(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    fake = FakeGit(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): "abc"},
        range_diffs={("abc", "HEAD"): DiffLines(paths=("a.py",))},
        revision_blobs={("abc", "a.py"): b"x"},
    )
    lazy = LazyGit(
        GuardRepo.create(tmp_path).repo, runtime_deps(git=fake), state=None, secret_paths=None
    )

    answers = (
        lazy.default_branch(),
        lazy.merge_base("origin/main", "HEAD"),
        lazy.diff_range("abc", "HEAD").paths,
        lazy.show("abc", "a.py"),
        lazy.diff_worktree("HEAD").paths,
        lazy.archive_to("HEAD", str(tmp_path), skip=lambda rel: False),
    )

    assert answers == ("origin/main", "abc", ("a.py",), b"x", (), 0)
    assert [method for method, _ in fake.calls] == [
        "default_branch",
        "merge_base",
        "diff_range",
        "show",
        "diff_worktree",
        "archive_to",
    ]

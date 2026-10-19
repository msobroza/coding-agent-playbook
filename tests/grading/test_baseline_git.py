"""Tests for the bounded git reads behind a ``git:`` metrics baseline (prK §F.0.3 item 7).

``SubprocessBaselineGit`` takes its process runner as a constructor argument, so
these tests wrap the real ``subprocess.run`` in :class:`SpyGitRunner` instead of
patching :mod:`subprocess`. The repositories are real and live in ``tmp_path``
under ``hermetic_git_env``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.baseline_git import (
    BaselineGitError,
    GitTimeoutError,
    SubprocessBaselineGit,
    SubprocessGitRunner,
    changed_paths,
    clean_head_tree,
    parse_batch_output,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_TIMEOUT_S = 7.5
_NEWLINE_PATH = "odd\nname.py"


@dataclass
class SpyGitRunner:
    """Records each git argv and its timeout, then runs it with the real ``subprocess.run``.

    The git command named in ``timeout_on`` (``"rev-parse"``, ``"worktree remove"``)
    raises :class:`subprocess.TimeoutExpired` instead of running.
    """

    timeout_on: str | None = None
    calls: list[tuple[str, float | None]] = field(default_factory=list)
    argvs: list[list[str]] = field(default_factory=list)

    def __call__(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        rest = list(args[1:])
        while rest[:1] == ["-c"]:  # skip `-c key=value` options before the subcommand
            rest = rest[2:]
        command = " ".join(rest[:2]) if rest[0] == "worktree" else rest[0]
        self.calls.append((command, kwargs.get("timeout")))
        self.argvs.append(list(args))
        if command == self.timeout_on:
            raise subprocess.TimeoutExpired(list(args), kwargs.get("timeout") or 0)
        return subprocess.run(args, **kwargs)

    def commands(self, name: str) -> int:
        return sum(1 for command, _ in self.calls if command == name)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=30
    )
    return proc.stdout


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Two commits; the work tree then edits, adds and leaves files untracked.

    ``HEAD~1`` holds ``mod.py``, ``with space.py``, ``crlf.py`` and the newline
    path; ``HEAD`` adds ``later.py`` and edits ``mod.py``.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "with space.py").write_text("x = 1\n", encoding="utf-8")
    (root / "crlf.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    (root / _NEWLINE_PATH).write_text("y = 2\n", encoding="utf-8")
    _commit_all(root, "base")
    (root / "later.py").write_text("z = 3\n", encoding="utf-8")
    (root / "mod.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    _commit_all(root, "next")
    (root / "mod.py").write_text("def f():\n    return 3\n", encoding="utf-8")
    (root / "new.py").write_text("n = 4\n", encoding="utf-8")
    return root


def _show_or_none(root: Path, ref: str, rel: str) -> bytes | None:
    """The pre-batch per-file read: ``git show <ref>:<path>``, ``None`` when absent."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, check=False, timeout=30
    )
    return proc.stdout if proc.returncode == 0 else None


# --------------------------------------------------------------------------- #
# The batched read
# --------------------------------------------------------------------------- #


def test_batched_baseline_read_matches_per_file_show(repo: Path) -> None:
    spy = SpyGitRunner()
    paths = ["mod.py", "with space.py", "crlf.py", "later.py", "new.py", _NEWLINE_PATH]

    sources = SubprocessBaselineGit(_TIMEOUT_S, run=spy).read_sources(repo, "HEAD~1", paths)

    expected = {rel: _show_or_none(repo, "HEAD~1", rel) for rel in paths}
    assert sources == {rel: blob for rel, blob in expected.items() if blob is not None}
    assert set(sources) == {"mod.py", "with space.py", "crlf.py", _NEWLINE_PATH}
    assert spy.commands("cat-file") == 1
    # A newline cannot be framed in --batch input; only that path falls back.
    assert spy.commands("show") == 1


def test_read_sources_without_paths_runs_no_git(repo: Path) -> None:
    spy = SpyGitRunner()

    assert SubprocessBaselineGit(_TIMEOUT_S, run=spy).read_sources(repo, "HEAD", []) == {}
    assert spy.calls == []


def test_read_sources_outside_a_repository_raises(tmp_path: Path) -> None:
    with pytest.raises(BaselineGitError, match="cat-file"):
        SubprocessBaselineGit(_TIMEOUT_S).read_sources(tmp_path, "HEAD", ["a.py"])


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (b"0123 blob 3\nabc\n", {"a.py": b"abc"}),
        (b"HEAD:a.py missing\n", {}),
        (b"HEAD:a.py ambiguous\n", {}),
        (b"0123 tree 4\n\x00\x01\n\n\n", {}),
    ],
    ids=["blob", "missing", "ambiguous", "not-a-blob"],
)
def test_parse_batch_output(stdout: bytes, expected: dict[str, bytes]) -> None:
    assert parse_batch_output(stdout, ["a.py"]) == expected


@pytest.mark.parametrize("stdout", [b"", b"0123 blob\n", b"0123 blob x\n"])
def test_parse_batch_output_rejects_malformed_output(stdout: bytes) -> None:
    with pytest.raises(BaselineGitError, match="cat-file"):
        parse_batch_output(stdout, ["a.py"])


# --------------------------------------------------------------------------- #
# Timeouts
# --------------------------------------------------------------------------- #


def test_every_git_call_passes_configured_timeout(repo: Path, tmp_path: Path) -> None:
    spy = SpyGitRunner()
    git = SubprocessBaselineGit(_TIMEOUT_S, run=spy)
    worktree = tmp_path / "baseline-worktree"

    assert git.is_commit(repo, "HEAD") is True
    git.read_sources(repo, "HEAD", ["mod.py", _NEWLINE_PATH])
    git.add_worktree(repo, worktree, "HEAD~1")
    git.remove_worktree(repo, worktree)

    commands = {command for command, _ in spy.calls}
    assert commands == {"rev-parse", "cat-file", "show", "worktree add", "worktree remove"}
    assert {timeout for _, timeout in spy.calls} == {_TIMEOUT_S}
    assert not worktree.exists()


@pytest.mark.parametrize(
    ("command", "call"),
    [
        ("rev-parse", lambda git, root: git.is_commit(root, "HEAD")),
        ("cat-file", lambda git, root: git.read_sources(root, "HEAD", ["mod.py"])),
        ("worktree add", lambda git, root: git.add_worktree(root, root / "wt", "HEAD")),
    ],
    ids=["rev-parse", "cat-file", "worktree-add"],
)
def test_git_timeout_names_the_command_and_the_seconds(repo: Path, command: str, call: Any) -> None:
    git = SubprocessBaselineGit(_TIMEOUT_S, run=SpyGitRunner(timeout_on=command))

    with pytest.raises(GitTimeoutError) as excinfo:
        call(git, repo)

    assert f"git {command} timed out after 7.5s" in str(excinfo.value)
    assert "[metrics] git_timeout_s" in str(excinfo.value)


def test_worktree_remove_timeout_is_swallowed(repo: Path, tmp_path: Path) -> None:
    spy = SpyGitRunner(timeout_on="worktree remove")
    git = SubprocessBaselineGit(_TIMEOUT_S, run=spy)
    git.add_worktree(repo, tmp_path / "wt", "HEAD")

    git.remove_worktree(repo, tmp_path / "wt")

    assert spy.commands("worktree remove") == 1


# --------------------------------------------------------------------------- #
# Failures that are not timeouts
# --------------------------------------------------------------------------- #


def test_is_commit_is_false_for_an_unknown_ref(repo: Path) -> None:
    assert SubprocessBaselineGit(_TIMEOUT_S).is_commit(repo, "no-such-ref") is False


def test_add_worktree_failure_carries_git_stderr(repo: Path) -> None:
    with pytest.raises(BaselineGitError, match="no-such-ref"):
        SubprocessBaselineGit(_TIMEOUT_S).add_worktree(repo, repo.parent / "wt", "no-such-ref")


def test_missing_git_binary_is_a_baseline_git_error(repo: Path) -> None:
    git = SubprocessBaselineGit(_TIMEOUT_S, executable="definitely-not-git-xyz")

    with pytest.raises(BaselineGitError, match="definitely-not-git-xyz"):
        git.is_commit(repo, "HEAD")


# --------------------------------------------------------------------------- #
# The git runner behind --changed and the snapshot tree (prK §F.0.3 items 3-4)
# --------------------------------------------------------------------------- #


def test_changed_paths_lists_added_modified_and_untracked_files(repo: Path) -> None:
    (repo / "with space.py").unlink()  # a deletion is not a target
    spy = SpyGitRunner()

    since_parent = changed_paths(SubprocessGitRunner(repo, _TIMEOUT_S, run=spy), "HEAD~1")
    since_head = changed_paths(SubprocessGitRunner(repo, _TIMEOUT_S), "HEAD")

    assert since_parent == {"mod.py", "later.py", "new.py"}
    assert since_head == {"mod.py", "new.py"}
    assert [command for command, _ in spy.calls] == ["diff", "ls-files"]
    assert {timeout for _, timeout in spy.calls} == {_TIMEOUT_S}


def test_changed_paths_are_relative_to_the_runner_root(repo: Path) -> None:
    (repo / "pkg").mkdir()
    (repo / "pkg" / "inner.py").write_text("i = 1\n", encoding="utf-8")
    _commit_all(repo, "pkg")
    (repo / "pkg" / "inner.py").write_text("i = 2\n", encoding="utf-8")
    (repo / "pkg" / "fresh.py").write_text("f = 1\n", encoding="utf-8")

    assert changed_paths(SubprocessGitRunner(repo / "pkg", _TIMEOUT_S), "HEAD") == {
        "inner.py",
        "fresh.py",
    }


def test_runner_hardens_argv_against_fsmonitor_and_diff_drivers(repo: Path) -> None:
    spy = SpyGitRunner()

    changed_paths(SubprocessGitRunner(repo, _TIMEOUT_S, run=spy), "HEAD")

    diff, ls_files = spy.argvs
    assert diff[1:3] == ls_files[1:3] == ["-c", "core.fsmonitor=false"]
    assert {"--no-ext-diff", "--no-textconv", "--diff-filter=AMR", "-z"} <= set(diff)


def test_runner_timeout_names_the_command(repo: Path) -> None:
    runner = SubprocessGitRunner(repo, _TIMEOUT_S, run=SpyGitRunner(timeout_on="diff"))

    with pytest.raises(GitTimeoutError, match=r"git diff timed out after 7\.5s"):
        changed_paths(runner, "HEAD")


def test_runner_failure_carries_git_stderr(repo: Path) -> None:
    with pytest.raises(BaselineGitError, match=r"git diff failed: .*no-such-ref"):
        changed_paths(SubprocessGitRunner(repo, _TIMEOUT_S), "no-such-ref")


def test_clean_head_tree_only_for_a_clean_worktree(repo: Path) -> None:
    runner = SubprocessGitRunner(repo, _TIMEOUT_S)

    assert clean_head_tree(runner) is None  # mod.py edited, new.py untracked
    (repo / "new.py").unlink()
    _git(repo, "checkout", "--", "mod.py")

    assert clean_head_tree(runner) == _git(repo, "rev-parse", "HEAD^{tree}").strip()

"""``SafeGit`` and the temp-index fingerprint (specs/prK-lifecycle-hooks.md §D.5.3, D-7, D-8).

``.git/config`` and ``.gitattributes`` are agent-writable, so an unhardened
git call from a hook is an edit-to-exec escalation. The ``FakeProc`` rows pin
the exact argv and child env ``SafeGit`` builds; the ``real_git`` rows prove,
against a real repository whose clean filter touches a marker file, that no
runtime git call ever executes that filter, that the fingerprint never touches
the user's index, and that a secret file is never read into the object store.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo
from coding_agent_playbook.hook_runtime.git._fingerprint import _copy_index
from coding_agent_playbook.hook_runtime.git.safe_git import (
    HOT_PATH_TIMEOUT_S,
    STOP_TIMEOUT_S,
    AddedLine,
    Fingerprint,
    GitError,
    GitTimeout,
    SafeGit,
)
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.state.store import StateStore
from tests.hook_runtime.fakes import FakeProc

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo
    from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc

GIT = "/usr/bin/git"
FILTER_LISTING = b"file:.git/config\x00filter.lfs.clean\ngit-lfs clean -- %f\x00"
SECRETS = compile_globs([".env*", "*.pem"], platform="linux")


def _layout(tmp_path: Path) -> RepoInfo:
    """A repository on disk without git: just the ``.git`` dir find_repo needs."""
    root = Path(os.path.realpath(tmp_path)) / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    repo = find_repo(str(root))
    assert repo is not None
    return repo


def _fake_proc(version: bytes = b"git version 2.39.3 (Apple Git-146)\n") -> FakeProc:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=version)
    proc.script(["git", "config", "--get-regexp"], stdout=FILTER_LISTING)
    return proc


def _safe_git(repo: RepoInfo, proc: FakeProc, **kwargs: object) -> SafeGit:
    env = {"PATH": "/usr/bin", "HOME": "/home/dev"}
    return SafeGit(repo, proc=proc, env=env, **kwargs)  # type: ignore[arg-type]


# --- argv, env and timeouts (FakeProc) ------------------------------------------------------


def test_child_env_scrubbed_and_hardening_flags_prepended(tmp_path: Path) -> None:
    repo = _layout(tmp_path)
    proc = _fake_proc()
    proc.script(["git", "rev-parse"], stdout=b"4b825dc642cb6eb9a060e54bf8d69288fbee4904\n")
    proc.script(["git", "diff"], stdout=b"")
    hostile = {
        "PATH": "/usr/bin",
        "KEEP": "1",
        "GIT_DIR": "/evil",
        "GIT_WORK_TREE": "/evil",
        "GIT_INDEX_FILE": "/evil/index",
        "GIT_CONFIG_PARAMETERS": "'core.pager'='sh evil'",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "diff.external",
        "GIT_CONFIG_VALUE_0": "evil",
        "GIT_EXTERNAL_DIFF": "evil",
        "GIT_COMMON_DIR": "/evil",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }

    assert SafeGit(repo, proc=proc, env=hostile).diff_added() == ()

    diff = proc.calls[-1]
    assert diff.argv == (
        GIT,
        "-c",
        "core.fsmonitor=false",
        "-c",
        "filter.lfs.clean=",
        "-c",
        "filter.lfs.smudge=",
        "-c",
        "filter.lfs.process=",
        "-c",
        "filter.lfs.required=false",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "HEAD",
        "-U0",
        "--no-color",
        "-M",
        "--no-relative",
        "--src-prefix=a/",
        "--dst-prefix=b/",
    )
    assert diff.env == {
        "PATH": "/usr/bin",
        "KEEP": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "LC_ALL": "C",
    }
    assert diff.cwd == repo.worktree_root
    assert diff.timeout == HOT_PATH_TIMEOUT_S == 2.0
    discovery = next(call for call in proc.calls if "config" in call.argv)
    assert discovery.argv[1:3] == ("-c", "core.fsmonitor=false")
    assert not any(arg.startswith("filter.") for arg in discovery.argv)


def test_stop_timeout_is_five_seconds(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "ls-files"], stdout=b"a.txt\x00b c.txt\x00")

    untracked = _safe_git(_layout(tmp_path), proc, timeout_s=STOP_TIMEOUT_S).ls_untracked()

    assert untracked == ("a.txt", "b c.txt")
    assert proc.calls[-1].timeout == STOP_TIMEOUT_S == 5.0
    assert proc.calls[-1].argv[-3:] == ("--others", "--exclude-standard", "-z")


def test_timeout_raises_git_timeout(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "cat-file"], timeout=True)

    with pytest.raises(GitTimeout, match=r"cat-file.*2\.0"):
        _safe_git(_layout(tmp_path), proc).cat_head("a.py")


def test_failed_command_raises_git_error_with_its_first_stderr_line(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "ls-files"], returncode=128, stderr=b"fatal: bad index\nmore\n")

    with pytest.raises(GitError, match=r"ls-files exited 128: fatal: bad index$"):
        _safe_git(_layout(tmp_path), proc).ls_untracked()


def test_missing_git_raises_git_error(tmp_path: Path) -> None:
    with pytest.raises(GitError, match="git not found"):
        _safe_git(_layout(tmp_path), FakeProc()).ls_untracked()


def test_failed_filter_discovery_refuses_every_hardened_call(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "config", "--get-regexp"], returncode=3, stderr=b"fatal: bad config\n")

    git = _safe_git(_layout(tmp_path), proc)

    with pytest.raises(GitError, match="bad config"):
        git.ls_untracked()
    assert git.fingerprint() is None  # unknown, never a crash
    assert not any("ls-files" in call.argv for call in proc.calls)


def test_filter_name_that_cannot_be_neutralized_is_refused(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "config"], stdout=b"file:.git/config\x00filter.a=b.clean\nx\x00")

    with pytest.raises(GitError, match="cannot be neutralized"):
        _safe_git(_layout(tmp_path), proc).ls_untracked()


def test_no_filters_means_only_fsmonitor_is_overridden(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "config"], returncode=1)  # no match is not a failure
    proc.script(["git", "ls-files"], stdout=b"")

    _safe_git(_layout(tmp_path), proc).ls_untracked()

    assert proc.calls[-1].argv[:4] == (GIT, "-c", "core.fsmonitor=false", "ls-files")


# --- caches ----------------------------------------------------------------------------------


def test_filter_and_version_caches_skip_git_until_a_config_file_changes(tmp_path: Path) -> None:
    repo = _layout(tmp_path)
    store = StateStore.for_repo(repo)
    include = Path(repo.git_dir) / "extra.cfg"
    listing = FILTER_LISTING + b"file:.git/config\x00include.path\nextra.cfg\x00"
    executable = tmp_path / "bin" / "git"  # a real file: the version cache keys on its stat
    executable.parent.mkdir()
    executable.write_text("", encoding="utf-8")

    def run_once() -> list[tuple[str, ...]]:
        proc = FakeProc(programs={"git": str(executable)})
        proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
        proc.script(["git", "config"], stdout=listing)
        proc.script(["git", "ls-files"], stdout=b"")
        git = _safe_git(repo, proc, state=store)
        assert git.version() == (2, 39, 3)
        git.ls_untracked()
        assert "filter.lfs.clean=" in proc.calls[-1].argv
        return [call.argv for call in proc.calls]

    assert len(run_once()) == 3  # version, discovery, ls-files
    assert len(run_once()) == 1  # both cached
    include.write_text('[filter "x"]\n', encoding="utf-8")  # an include target appears
    assert len(run_once()) == 2  # rediscovered; the version cache still holds
    os.utime(Path(repo.git_dir) / "config", ns=(1, 1))
    assert len(run_once()) == 2


# --- parsing (FakeProc) ----------------------------------------------------------------------


def test_diff_added_parses_hunks_paths_and_deletions(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "rev-parse"], stdout=b"deadbeef\n")
    proc.script(
        ["git", "diff"],
        stdout=(
            b"diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
            b"@@ -3,0 +4,2 @@ def f():\n+x = 1\n+y = 2\n@@ -9 +11 @@\n-old\n+new\n"
            b'diff --git "a/d i/t\\"q.txt" "b/d i/t\\"q.txt"\n--- /dev/null\n'
            b'+++ "b/d i/t\\"q.txt"\t\n@@ -0,0 +1 @@\n+caf\\303\\251\n'
            b"diff --git a/gone.txt b/gone.txt\n--- a/gone.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
            b"diff --git a/bin.dat b/bin.dat\nBinary files a/bin.dat and b/bin.dat differ\n"
        ),
    )

    added = _safe_git(_layout(tmp_path), proc).diff_added()

    assert added == (
        AddedLine("src/a.py", 4, "x = 1"),
        AddedLine("src/a.py", 5, "y = 2"),
        AddedLine("src/a.py", 11, "new"),
        AddedLine('d i/t"q.txt', 1, "caf\\303\\251"),
    )


def test_diff_added_on_an_unborn_head_diffs_against_the_empty_tree(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "rev-parse"], returncode=1)
    proc.script(["git", "hash-object"], stdout=b"4b825dc642cb6eb9a060e54bf8d69288fbee4904\n")
    proc.script(["git", "diff"], stdout=b"")

    _safe_git(_layout(tmp_path), proc).diff_added()

    assert "4b825dc642cb6eb9a060e54bf8d69288fbee4904" in proc.calls[-1].argv


def test_cat_head_reads_one_blob_through_cat_file_batch(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "cat-file", "--batch"], stdout=b"abc123 blob 6\nline1\n\n")

    git = _safe_git(_layout(tmp_path), proc)

    assert git.cat_head("src/a.py") == b"line1\n"
    assert proc.calls[-1].input == b"HEAD:src/a.py\n"
    assert git.cat_head("bad\nname") is None


@pytest.mark.parametrize(
    "answer", [b"HEAD:a.py missing\n", b"abc123 tree 30\n" + b"x" * 30 + b"\n", b"garbage\n"]
)
def test_cat_head_is_none_for_a_path_absent_at_head(tmp_path: Path, answer: bytes) -> None:
    proc = _fake_proc()
    proc.script(["git", "cat-file"], stdout=answer)

    assert _safe_git(_layout(tmp_path), proc).cat_head("a.py") is None


def test_symbolic_ref_and_config_value_skip_filter_discovery(tmp_path: Path) -> None:
    """Neither query reads worktree content, so neither needs (or waits for) the filter flags."""
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "symbolic-ref"], stdout=b"main\n")
    proc.script(["git", "config", "--get", "user.email"], stdout=b"dev@corp.example\n")
    proc.script(["git", "config", "--get", "user.name"], returncode=1)
    git = _safe_git(_layout(tmp_path), proc)

    assert git.symbolic_ref("HEAD") == "main"
    assert git.config_value("user.email") == "dev@corp.example"
    assert git.config_value("user.name") is None
    assert proc.calls[0].argv[1:] == (
        "-c",
        "core.fsmonitor=false",
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
    )
    assert not any("--get-regexp" in call.argv for call in proc.calls)


def test_symbolic_ref_is_none_when_detached_or_absent(tmp_path: Path) -> None:
    proc = FakeProc(programs={"git": GIT})
    proc.script(["git", "symbolic-ref"], returncode=1)

    assert _safe_git(_layout(tmp_path), proc).symbolic_ref("refs/remotes/origin/HEAD") is None


def test_head_tree_is_none_on_an_unborn_branch(tmp_path: Path) -> None:
    proc = _fake_proc()
    proc.script(["git", "rev-parse"], returncode=1)

    assert _safe_git(_layout(tmp_path), proc).head_tree() is None
    assert proc.calls[-1].argv[-3:] == ("--verify", "--quiet", "HEAD^{tree}")


def test_stat_mode_fallback_below_git_2_26(tmp_path: Path) -> None:
    repo = _layout(tmp_path)
    (Path(repo.worktree_root) / "a.txt").write_text("x", encoding="utf-8")
    proc = _fake_proc(version=b"git version 2.25.1\n")
    proc.script(["git", "status"], stdout=b"1 .M N... 100644 100644 100644 aa bb a.txt\x00")

    dirty = _safe_git(repo, proc, timeout_s=STOP_TIMEOUT_S).fingerprint()

    assert dirty is not None
    assert (dirty.mode, dirty.tree_id, dirty.unchanged_vs_head) == ("stat", None, False)
    assert dirty.key.startswith("stat:")
    assert not any({"add", "write-tree"} & set(call.argv) for call in proc.calls)
    clean_proc = _fake_proc(version=b"git version 2.25.1\n")
    clean_proc.script(["git", "status"], stdout=b"")
    clean = _safe_git(repo, clean_proc).fingerprint()
    assert clean is not None and clean.unchanged_vs_head
    assert clean.key != dirty.key


def test_fingerprint_key_renders_tree_and_aux() -> None:
    assert (
        Fingerprint(tree_id="t" * 40, aux="", mode="tree", unchanged_vs_head=True).key == "t" * 40
    )
    with_aux = Fingerprint(tree_id="t" * 40, aux="a" * 64, mode="tree", unchanged_vs_head=False)
    assert with_aux.key == "t" * 40 + ":" + "a" * 12


# --- real git ----------------------------------------------------------------------------------


@pytest.fixture
def repo_with_filter(tmp_path: Path, real_git: Callable[..., str]) -> tuple[Path, Path]:
    """A committed repo whose ``*.txt`` clean/smudge filter touches ``marker``."""
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    marker = Path(os.path.realpath(tmp_path)) / "marker"
    real_git("init", "-q", cwd=root)
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    (root / "keep.py").write_text("x = 1\n", encoding="utf-8")
    real_git("add", "-A", cwd=root)
    real_git("commit", "-q", "-m", "init", cwd=root)
    (root / ".gitattributes").write_text("*.txt filter=evil\n", encoding="utf-8")
    command = f"sh -c 'touch {marker}; cat'"
    real_git("config", "filter.evil.clean", command, cwd=root)
    real_git("config", "filter.evil.smudge", command, cwd=root)
    real_git("config", "filter.evil.required", "true", cwd=root)
    return root, marker


def _real_safe_git(root: Path, real_proc: SubprocessProc, **kwargs: object) -> SafeGit:
    repo = find_repo(str(root))
    assert repo is not None
    return SafeGit(
        repo,
        proc=real_proc,
        env=dict(os.environ),
        state=StateStore.for_repo(repo),
        timeout_s=STOP_TIMEOUT_S,
        secret_paths=SECRETS,
        **kwargs,  # type: ignore[arg-type]
    )


def test_clean_filter_never_runs_for_fingerprint_diff_added_cat_head(
    repo_with_filter: tuple[Path, Path], real_proc: SubprocessProc
) -> None:
    root, marker = repo_with_filter
    (root / "a.txt").write_text("changed\n", encoding="utf-8")
    (root / "b.txt").write_text("new\n", encoding="utf-8")
    git = _real_safe_git(root, real_proc)

    fingerprint = git.fingerprint()
    added = git.diff_added()
    blob = git.cat_head("a.txt")

    assert fingerprint is not None and fingerprint.mode == "tree"
    assert AddedLine("a.txt", 1, "changed") in added
    assert blob == b"hello\n"
    assert not marker.exists()


def test_fingerprint_stable_across_git_add(
    tmp_path: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", cwd=root)
    (root / "a.py").write_text("a = 1\n", encoding="utf-8")
    real_git("add", "-A", cwd=root)
    real_git("commit", "-q", "-m", "init", cwd=root)
    (root / "a.py").write_text("a = 2\n", encoding="utf-8")
    (root / "b.py").write_text("b = 1\n", encoding="utf-8")
    git = _real_safe_git(root, real_proc)
    index_before = (root / ".git" / "index").read_bytes()

    before = git.fingerprint()
    assert (root / ".git" / "index").read_bytes() == index_before  # the user's index is untouched
    real_git("add", "-A", cwd=root)
    after = git.fingerprint()

    assert before is not None and after is not None
    assert before == after
    assert not before.unchanged_vs_head
    assert not list((Path(git.repo.git_dir) / "playbook-hooks" / "tmp").iterdir())


def test_temp_index_copy_keeps_the_index_mtime(tmp_path: Path) -> None:
    # Regression: test_fingerprint_stable_across_git_add failed in about 3% of
    # runs (4 of 150) because the temp copy got a fresh mtime. git re-hashes an
    # entry only when its mtime is not older than the index file's (the
    # racy-clean check), so a same-size rewrite in the last index write's tick
    # kept its stale blob. With the index mtime preserved: 0 of 150.
    source = tmp_path / "index"
    source.write_bytes(b"DIRC")
    os.utime(source, ns=(1_000_000_000, 2_000_000_000))

    _copy_index(source, tmp_path / "copy")
    _copy_index(tmp_path / "absent", tmp_path / "none")

    assert (tmp_path / "copy").read_bytes() == b"DIRC"
    assert os.stat(tmp_path / "copy").st_mtime_ns == 2_000_000_000
    assert not (tmp_path / "none").exists()  # no index: the fingerprint starts empty


def test_unchanged_vs_head_on_clean_tree(
    repo_with_filter: tuple[Path, Path], real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root, marker = repo_with_filter
    real_git("add", ".gitattributes", cwd=root)
    real_git("-c", "filter.evil.clean=cat", "commit", "-q", "-m", "attrs", cwd=root)
    marker.unlink(missing_ok=True)  # only the runtime's own calls are under test
    git = _real_safe_git(root, real_proc)

    clean = git.fingerprint()
    (root / "keep.py").write_text("x = 2\n", encoding="utf-8")
    dirty = git.fingerprint()

    assert clean is not None and clean.unchanged_vs_head
    assert clean.tree_id == git.head_tree()
    assert dirty is not None and not dirty.unchanged_vs_head
    assert not marker.exists()


def test_untracked_env_prod_changes_aux_without_reading_content(
    repo_with_filter: tuple[Path, Path], real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root, _marker = repo_with_filter
    git = _real_safe_git(root, real_proc)
    without = git.fingerprint()
    secret = root / ".env.prod"
    secret.write_text("API_TOKEN=s3cr3t-value\n", encoding="utf-8")
    secret.chmod(0)  # any read of it now fails: the fingerprint must only stat it
    try:
        with_secret = git.fingerprint()
    finally:
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert without is not None and with_secret is not None
    assert with_secret.tree_id == without.tree_id
    assert without.aux == "" and with_secret.aux != ""
    assert with_secret.key != without.key and not with_secret.unchanged_vs_head
    content_id = real_git("hash-object", ".env.prod", cwd=root)
    objects = Path(root / ".git" / "objects" / content_id[:2] / content_id[2:])
    assert not objects.exists()  # never hashed into the object store


def test_oversized_untracked_file_is_folded_into_aux(
    tmp_path: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "init", cwd=root)
    git = _real_safe_git(root, real_proc, max_file_bytes=10)
    (root / "model.pt").write_bytes(b"x" * 11)

    first = git.fingerprint()
    (root / "model.pt").write_bytes(b"y" * 12)
    second = git.fingerprint()

    assert first is not None and second is not None
    assert first.tree_id == second.tree_id == git.head_tree()
    assert first.aux and second.aux and first.aux != second.aux


def test_symbolic_ref_and_config_value_against_a_real_repo(
    tmp_path: Path, real_git: Callable[..., str], real_proc: SubprocessProc
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    real_git("init", "-q", "-b", "trunk", cwd=root)
    real_git("config", "user.email", "you@example.com", cwd=root)
    git = _real_safe_git(root, real_proc)

    assert git.symbolic_ref("HEAD") == "trunk"
    assert git.symbolic_ref("refs/remotes/origin/HEAD") is None
    assert git.config_value("user.email") == "you@example.com"
    assert git.config_value("playbook.unset") is None

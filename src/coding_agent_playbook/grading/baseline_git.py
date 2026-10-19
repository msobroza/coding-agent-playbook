"""Git reads for a ``git:<ref>`` metrics baseline, each bounded by a timeout (prK §F.0.3 item 7).

The metrics gate asks git four things: does the ref name a commit, what were
these files at the ref, and (for a suite baseline) add then remove a temporary
worktree. They live behind the :class:`BaselineGit` protocol so the gate takes
the client as a dependency and tests inject a named fake instead of patching
:mod:`subprocess`.

Every call is bounded by ``[metrics] git_timeout_s``: the Stop stages run the
gate inside a hook, where an unbounded ``git`` on a wedged repository (lock
contention, a network filesystem) would hang the agent. A timeout raises
:class:`GitTimeoutError`, which names the command and the bound; the CLI exits 2
on it. Only the cleanup ``worktree remove`` swallows it: the result is already
measured, and the worktree sits in a temp dir that is deleted anyway.

The file reads are one ``git cat-file --batch`` process instead of one
``git show`` per file. ``--batch`` frames its input by line, so a path that
contains a newline or a carriage return (``strbuf_getline`` strips a CR before
the LF) falls back to ``git show``.

``--changed`` and the ``--emit-measurements`` tree read the working tree
(``diff``, ``ls-files``, ``status``) through a :data:`GitRunner`: one callable
per repository root, so a hook can hand the gate its hardened ``SafeGit``
instead of :class:`SubprocessGitRunner` (prK §F.0.3 items 3-4).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from typing import TYPE_CHECKING, Any, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    #: ``git <args>`` at one repository root -> stdout. Raises
    #: :class:`BaselineGitError` on a failure, :class:`GitTimeoutError` past its bound.
    type GitRunner = Callable[[Sequence[str]], bytes]

#: Characters ``git cat-file --batch`` cannot carry in its line-framed input.
_UNFRAMEABLE = ("\n", "\r")

#: ``core.fsmonitor`` is repository config naming a program git runs on
#: worktree reads (``status``, ``diff``); the agent can write that config.
_NO_FSMONITOR: Final = ("-c", "core.fsmonitor=false")

#: What ``--changed`` measures: added, modified or renamed files (a deleted one
#: has nothing to measure). ``--relative`` keeps the names relative to the
#: runner's root, like ``ls-files``; external diff drivers and textconv never run.
_CHANGED_DIFF: Final = (
    "diff",
    "--name-only",
    "-z",
    "--relative",
    "--no-ext-diff",
    "--no-textconv",
    "-M",
    "--diff-filter=AMR",
)
_UNTRACKED: Final = ("ls-files", "--others", "--exclude-standard", "-z")


class BaselineGitError(Exception):
    """git could not answer: not a repository, git missing, or an unexpected failure.

    The message carries git's own stderr (or the OS error) for the CLI to quote.

    Example::

        >>> str(BaselineGitError("fatal: not a git repository"))
        'fatal: not a git repository'
    """


class GitTimeoutError(BaselineGitError):
    """A git call ran past ``[metrics] git_timeout_s``.

    Example::

        >>> str(GitTimeoutError("rev-parse", 10.0))
        'git rev-parse timed out after 10s; raise [metrics] git_timeout_s for a slow repository'
    """

    def __init__(self, command: str, timeout_s: float) -> None:
        super().__init__(
            f"git {command} timed out after {timeout_s:g}s; "
            "raise [metrics] git_timeout_s for a slow repository"
        )
        self.command = command
        self.timeout_s = timeout_s


class BaselineGit(Protocol):
    """The git queries a ``git:`` metrics baseline needs."""

    def is_commit(self, repo_root: Path, ref: str) -> bool:
        """True when ``ref`` resolves to a commit in ``repo_root``."""
        ...

    def read_sources(self, repo_root: Path, ref: str, rel_paths: Sequence[str]) -> dict[str, bytes]:
        """The blob at ``<ref>:<path>`` for each path that has one; absent paths are left out."""
        ...

    def add_worktree(self, repo_root: Path, worktree: Path, ref: str) -> None:
        """Check ``ref`` out, detached, into the new directory ``worktree``."""
        ...

    def remove_worktree(self, repo_root: Path, worktree: Path) -> None:
        """Remove ``worktree``; best effort, never raises."""
        ...


class SubprocessBaselineGit:
    """:class:`BaselineGit` over the ``git`` binary (arg lists, no shell), bounded by ``timeout_s``.

    Example::

        >>> git = SubprocessBaselineGit(10.0)
        >>> git.read_sources(Path("."), "HEAD", ["src/app.py"])  # doctest: +SKIP
        {'src/app.py': b'def main() -> None: ...'}
    """

    def __init__(
        self,
        timeout_s: float,
        *,
        run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        executable: str = "git",
    ) -> None:
        self._timeout_s = timeout_s
        self._run = run
        self._executable = executable

    def is_commit(self, repo_root: Path, ref: str) -> bool:
        """``git rev-parse --verify --quiet <ref>^{commit}`` exits 0."""
        args = ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]
        return self._git(args, repo_root).returncode == 0

    def read_sources(self, repo_root: Path, ref: str, rel_paths: Sequence[str]) -> dict[str, bytes]:
        """One ``cat-file --batch`` for every frameable path, ``git show`` for the rest."""
        batched = [rel for rel in rel_paths if not _is_unframeable(rel)]
        sources = self._cat_file_batch(repo_root, ref, batched) if batched else {}
        for rel in rel_paths:
            if _is_unframeable(rel):
                blob = self._show(repo_root, ref, rel)
                if blob is not None:
                    sources[rel] = blob
        return sources

    def add_worktree(self, repo_root: Path, worktree: Path, ref: str) -> None:
        """``git worktree add --detach``; raises :class:`BaselineGitError` with git's stderr."""
        proc = self._git(["worktree", "add", "--detach", str(worktree), ref], repo_root)
        if proc.returncode != 0:
            raise BaselineGitError(_stderr(proc))

    def remove_worktree(self, repo_root: Path, worktree: Path) -> None:
        """``git worktree remove --force``; a failure or timeout is ignored (cleanup only)."""
        with contextlib.suppress(BaselineGitError):
            self._git(["worktree", "remove", "--force", str(worktree)], repo_root)

    def _cat_file_batch(
        self, repo_root: Path, ref: str, rel_paths: Sequence[str]
    ) -> dict[str, bytes]:
        stdin = b"".join(os.fsencode(f"{ref}:{rel}") + b"\n" for rel in rel_paths)
        proc = self._git(["cat-file", "--batch"], repo_root, stdin=stdin)
        if proc.returncode != 0:
            raise BaselineGitError(f"git cat-file --batch failed: {_stderr(proc)}")
        return parse_batch_output(proc.stdout, rel_paths)

    def _show(self, repo_root: Path, ref: str, rel_path: str) -> bytes | None:
        """``git show <ref>:<path>``; ``None`` when the path is absent at ``ref``."""
        proc = self._git(["show", f"{ref}:{rel_path}"], repo_root)
        if proc.returncode == 0:
            return proc.stdout
        stderr = _stderr(proc)
        # "does not exist" / "exists on disk, but not in" => file absent at ref.
        if "does not exist" in stderr.lower() or "exists on disk" in stderr.lower():
            return None
        raise BaselineGitError(stderr)

    def _git(
        self, args: list[str], cwd: Path, *, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        """Run ``git <args>`` with the bound; timeouts and OS errors become typed errors."""
        return _run_git(self._run, self._executable, args, cwd, self._timeout_s, stdin=stdin)


class SubprocessGitRunner:
    """A :data:`GitRunner` over the ``git`` binary at ``repo_root``, bounded by ``timeout_s``.

    Every call disables ``core.fsmonitor``; a non-zero exit raises
    :class:`BaselineGitError` carrying git's stderr.

    Example::

        >>> runner = SubprocessGitRunner(Path("."), 10.0)
        >>> runner(["rev-parse", "HEAD"])  # doctest: +SKIP
        b'1f2e...\\n'
    """

    def __init__(
        self,
        repo_root: Path,
        timeout_s: float,
        *,
        run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        executable: str = "git",
    ) -> None:
        self._repo_root = repo_root
        self._timeout_s = timeout_s
        self._run = run
        self._executable = executable

    def __call__(self, args: Sequence[str]) -> bytes:
        """``git <args>``'s stdout; raises :class:`BaselineGitError` when git fails."""
        argv = [*_NO_FSMONITOR, *args]
        proc = _run_git(self._run, self._executable, argv, self._repo_root, self._timeout_s)
        if proc.returncode != 0:
            raise BaselineGitError(f"git {_command_label(args)} failed: {_stderr(proc)}")
        return proc.stdout


def changed_paths(git: GitRunner, ref: str) -> frozenset[str]:
    """Paths added, modified or renamed since ``ref``, plus untracked ones, relative to ``git``'s root.

    The working tree is compared, staged or not; ignored files are left out.

    Example::

        >>> changed_paths(SubprocessGitRunner(Path("."), 10.0), "HEAD")  # doctest: +SKIP
        frozenset({'src/app.py', 'src/new_module.py'})
    """
    changed = _split_z(git([*_CHANGED_DIFF, ref, "--"]))
    return frozenset(changed) | frozenset(_split_z(git(list(_UNTRACKED))))


def clean_head_tree(git: GitRunner) -> str | None:
    """``HEAD^{tree}`` when the worktree is clean (no change, no untracked file), else ``None``.

    A measurement snapshot names this tree, so a later run at the same commit
    can reuse it as its baseline (prK §F.0.3 item 4). Raises
    :class:`BaselineGitError` when git fails (an unborn ``HEAD`` included).

    Example::

        >>> clean_head_tree(SubprocessGitRunner(Path("."), 10.0))  # doctest: +SKIP
        '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
    """
    if git(["status", "--porcelain", "-z"]):
        return None
    return os.fsdecode(git(["rev-parse", "--verify", "HEAD^{tree}"])).strip()


def parse_batch_output(stdout: bytes, rel_paths: Sequence[str]) -> dict[str, bytes]:
    """Split ``git cat-file --batch`` output into ``{path: blob}``, in request order.

    Each request answers ``<oid> <type> <size>\\n<content>\\n`` or
    ``<name> missing\\n`` (``ambiguous`` likewise). A missing path, or one that
    is not a blob at the ref (a directory, a submodule), is left out: the gate
    treats it as all-new. Raises :class:`BaselineGitError` on output it cannot frame.

    Example::

        >>> parse_batch_output(b"1f2e blob 6\\nx = 1\\n\\nHEAD:b.py missing\\n", ["a.py", "b.py"])
        {'a.py': b'x = 1\\n'}
    """
    sources: dict[str, bytes] = {}
    pos = 0
    for rel in rel_paths:
        end = stdout.find(b"\n", pos)
        if end < 0:
            raise BaselineGitError(f"git cat-file --batch output ended before {rel!r}")
        found = _parse_batch_header(stdout[pos:end])
        pos = end + 1
        if found is None:
            continue
        kind, size = found
        if kind == b"blob":
            sources[rel] = stdout[pos : pos + size]
        pos += size + 1  # the content, then its terminating LF
    return sources


def _parse_batch_header(header: bytes) -> tuple[bytes, int] | None:
    """``(type, size)`` for a found object, ``None`` for ``missing`` / ``ambiguous``."""
    if header.endswith((b" missing", b" ambiguous")):
        return None
    parts = header.split(b" ")
    if len(parts) != 3 or not parts[2].isdigit():
        raise BaselineGitError(f"unexpected git cat-file --batch header {header!r}")
    return parts[1], int(parts[2])


def _is_unframeable(rel_path: str) -> bool:
    return any(char in rel_path for char in _UNFRAMEABLE)


def _run_git(
    run: Callable[..., subprocess.CompletedProcess[bytes]],
    executable: str,
    args: Sequence[str],
    cwd: Path,
    timeout_s: float,
    *,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """``<executable> <args>`` in ``cwd`` within ``timeout_s``; timeouts and OS errors become typed."""
    kwargs: dict[str, Any] = {"cwd": cwd, "capture_output": True, "check": False}
    try:
        return run([executable, *args], input=stdin, timeout=timeout_s, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise GitTimeoutError(_command_label(args), timeout_s) from exc
    except OSError as exc:
        raise BaselineGitError(f"cannot run {executable}: {exc}") from exc


def _split_z(stdout: bytes) -> list[str]:
    """NUL-framed git output (``-z``) as paths; undecodable bytes survive as surrogates."""
    return [os.fsdecode(name) for name in stdout.split(b"\0") if name]


def _command_label(args: Sequence[str]) -> str:
    """What a timeout names: ``rev-parse``, ``cat-file``, ``show``, ``worktree add``.

    Leading ``-c key=value`` options are skipped.
    """
    rest = list(args)
    while rest[:1] == ["-c"]:
        rest = rest[2:]
    return " ".join(rest[:2]) if rest[0] == "worktree" else rest[0]


def _stderr(proc: subprocess.CompletedProcess[bytes]) -> str:
    return os.fsdecode(proc.stderr).strip()

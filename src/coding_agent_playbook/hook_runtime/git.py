"""Every git call the hook runtime makes, hardened (specs/prK-lifecycle-hooks.md §D.5.3, D-7).

``.git/config`` and ``.gitattributes`` are agent-writable, and git runs code
they name: a ``filter.<name>.clean`` command runs on ``git add``, ``git diff``
and even ``git write-tree`` (verified on 2.39.3); ``core.fsmonitor`` names an
executable; ``diff.external`` and textconv drivers run on ``diff``. An
unhardened hook git call would turn an edit into code execution, so
:class:`SafeGit` is the only way the runtime runs git:

- filter drivers are discovered once (``_git_cache``) and neutralized with
  ``-c filter.<n>.clean= -c filter.<n>.smudge= -c filter.<n>.process=
  -c filter.<n>.required=false`` (the last one, beyond the spec's three, keeps
  a ``required`` driver from failing the call); if discovery fails, every
  hardened call is refused instead of run unprotected;
- ``-c core.fsmonitor=false`` always, ``--no-ext-diff --no-textconv`` on every
  ``diff`` / ``log`` / ``show``, and ``cat-file --batch`` for blob reads;
- the child env drops every variable that relocates the repository or
  injects config (``GIT_DIR``, ``GIT_CONFIG_PARAMETERS``, ``GIT_CONFIG_KEY_*``,
  ...) and forces ``GIT_OPTIONAL_LOCKS=0``, ``GIT_TERMINAL_PROMPT=0``,
  ``GIT_PAGER=cat`` and ``LC_ALL=C``;
- each call is bounded: 2 s on the hot path, 5 s in Stop stages; a timeout
  raises :class:`GitTimeout` for the failure policy.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.hook_runtime._git_argv import (
    FSMONITOR,
    child_env,
    first_line,
    subcommand,
    with_diff_flags,
)
from coding_agent_playbook.hook_runtime._git_parse import (
    AddedLine,
    parse_batch_blob,
    parse_diff_added,
    split_z,
)
from coding_agent_playbook.hook_runtime.git_log import LoggedCommit, LogPort, LogQueries
from coding_agent_playbook.hook_runtime.git_range import PATCH_FLAGS, RangePort, RangeQueries
from coding_agent_playbook.hook_runtime.proc import ProcTimeout

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.deps import ProcPort
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.proc import ProcResult
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "FINGERPRINT_MAX_FILE_BYTES",
    "HOT_PATH_TIMEOUT_S",
    "STOP_TIMEOUT_S",
    "AddedLine",
    "Fingerprint",
    "GitError",
    "GitPort",
    "GitTimeout",
    "LoggedCommit",
    "SafeGit",
]

#: Per-call bound on the hot path (pragma checks, the §E git guards).
HOT_PATH_TIMEOUT_S: Final = 2.0
#: Per-call bound inside Stop stages.
STOP_TIMEOUT_S: Final = 5.0
#: Untracked files above this are folded into the fingerprint by stat, never hashed.
FINGERPRINT_MAX_FILE_BYTES: Final = 5 * 1024 * 1024


class GitError(Exception):
    """A git call failed, git is missing, or it cannot be run safely."""


class GitTimeout(GitError):
    """A git call outlived its bound; the failure policy decides (§D.4)."""


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """The working tree's identity, as the Stop coordinator compares it (D-8).

    ``tree`` mode: ``tree_id`` is the temp-index tree, and ``aux`` hashes the
    stat of every excluded path (secret or oversized), ``""`` when none was.
    ``stat`` mode (git < 2.26): ``digest`` hashes ``git status`` plus per-path
    stat, and there is no tree id for the commit-policy cache.

    Example::

        >>> Fingerprint(tree_id="ab", aux="", mode="tree", unchanged_vs_head=True).key
        'ab'
    """

    tree_id: str | None
    aux: str
    mode: Literal["tree", "stat"]
    unchanged_vs_head: bool
    digest: str = ""

    @property
    def key(self) -> str:
        """``<tree_id>``, ``<tree_id>:<aux[:12]>``, or ``stat:<digest[:40]>``."""
        if self.tree_id is None:
            return f"stat:{self.digest[:40]}"
        return self.tree_id if not self.aux else f"{self.tree_id}:{self.aux[:12]}"


class GitPort(RangePort, LogPort, Protocol):
    """What handlers, the Stop coordinator and the CLI twins ask of git; ``FakeGit`` scripts it."""

    def head_tree(self) -> str | None: ...

    def fingerprint(self) -> Fingerprint | None: ...

    def diff_added(self) -> tuple[AddedLine, ...]: ...

    def cat_head(self, repo_rel: str) -> bytes | None: ...

    def ls_untracked(self) -> tuple[str, ...]: ...

    def symbolic_ref(self, ref: str) -> str | None: ...

    def config_value(self, key: str) -> str | None: ...


class SafeGit(RangeQueries, LogQueries):
    """Hardened git for one worktree; every call runs at its root through ``proc``.

    ``env`` is the hook process environment (scrubbed per call); ``state``
    holds the discovery caches and the temp index (``None``: no caches, a
    system temp dir, as in CI); ``secret_paths`` and ``max_file_bytes`` decide
    what the fingerprint folds in by stat. The revision queries come from
    ``git_range.RangeQueries``, the commit log from ``git_log.LogQueries``.

    Example::

        >>> git = SafeGit(repo, proc=deps.proc, env=deps.env, state=store)  # doctest: +SKIP
        >>> git.cat_head("src/app.py")
        b'...'
    """

    def __init__(
        self,
        repo: RepoInfo,
        *,
        proc: ProcPort,
        env: Mapping[str, str],
        state: StateStore | None = None,
        timeout_s: float = HOT_PATH_TIMEOUT_S,
        secret_paths: GlobSet | None = None,
        max_file_bytes: int = FINGERPRINT_MAX_FILE_BYTES,
        platform: str = sys.platform,
    ) -> None:
        self.repo = repo
        self.state = state
        self.timeout_s = timeout_s
        self.secret_paths = secret_paths
        self.max_file_bytes = max_file_bytes
        self.platform = platform
        self.env = child_env(env)
        self._proc = proc
        self._executable: str | None = None
        self._filter_flags: tuple[str, ...] | None = None
        self._filter_error: GitError | None = None
        self._version: tuple[int, int, int] | None = None

    # --- running -------------------------------------------------------------------------

    def run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult:
        """Run ``git <args>`` with every hardening flag; raises :class:`GitError`."""
        argv = [*self._filters(), *with_diff_flags(args)]
        return self.bare_run(argv, input=input, index_file=index_file, ok_codes=ok_codes)

    def bare_run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult:
        """Run ``git -c core.fsmonitor=false <args>`` without filter neutralization.

        Only for calls that read no worktree content: ``--version`` and the
        filter discovery itself, which must run before the filters are known.
        """
        env = self.env if index_file is None else {**self.env, "GIT_INDEX_FILE": index_file}
        command = subcommand(args)
        try:
            result = self._proc.run(
                [self.executable(), *FSMONITOR, *args],
                timeout=self.timeout_s,
                env=env,
                input=input,
                cwd=self.repo.worktree_root,
            )
        except ProcTimeout as exc:
            raise GitTimeout(f"git {command} exceeded its {exc.timeout} s timeout") from None
        except OSError as exc:
            raise GitError(f"cannot run git {command}: {exc.strerror}") from exc
        if result.returncode not in ok_codes:
            raise GitError(f"git {command} exited {result.returncode}: {first_line(result.stderr)}")
        return result

    def executable(self) -> str:
        """The git program on the hook's ``PATH``, resolved once per instance."""
        if self._executable is None:
            found = self._proc.which("git", path=self.env.get("PATH"))
            if found is None:
                raise GitError("git not found on PATH; hooks that need git cannot run")
            self._executable = found
        return self._executable

    def version(self) -> tuple[int, int, int]:
        """git's version, cached in ``<state>/cache/git-version`` per executable."""
        if self._version is None:
            from coding_agent_playbook.hook_runtime._git_cache import cached_version

            self._version = cached_version(self)
        return self._version

    def _filters(self) -> tuple[str, ...]:
        if self._filter_error is not None:
            raise self._filter_error
        if self._filter_flags is None:
            from coding_agent_playbook.hook_runtime._git_cache import filter_flags

            try:
                self._filter_flags = filter_flags(self)
            except GitError as exc:
                self._filter_error = exc
                raise
        return self._filter_flags

    # --- GitPort -------------------------------------------------------------------------

    def head_tree(self) -> str | None:
        """``HEAD^{tree}``, or ``None`` on an unborn branch."""
        result = self.run(["rev-parse", "--verify", "--quiet", "HEAD^{tree}"], ok_codes=(0, 1))
        tree = result.stdout.decode("ascii", errors="replace").strip()
        return tree if result.ok and tree else None

    def diff_added(self) -> tuple[AddedLine, ...]:
        """The lines the working tree adds over ``HEAD`` (the empty tree when unborn)."""
        base = "HEAD" if self.head_tree() is not None else self._empty_tree()
        result = self.run(["diff", base, *PATCH_FLAGS])
        return parse_diff_added(result.stdout)

    def cat_head(self, repo_rel: str) -> bytes | None:
        """The bytes of ``repo_rel`` at ``HEAD``, or ``None`` when absent there."""
        if not repo_rel or "\n" in repo_rel or "\x00" in repo_rel:
            return None
        result = self.run(["cat-file", "--batch"], input=f"HEAD:{repo_rel}\n".encode())
        return parse_batch_blob(result.stdout)

    def ls_untracked(self) -> tuple[str, ...]:
        """Untracked, non-ignored paths, repo-relative."""
        result = self.run(["ls-files", "--others", "--exclude-standard", "-z"])
        return split_z(result.stdout)

    def symbolic_ref(self, ref: str) -> str | None:
        """What ``ref`` points at, short (``HEAD`` -> ``main``); ``None`` if detached or absent."""
        result = self.bare_run(["symbolic-ref", "--quiet", "--short", ref], ok_codes=(0, 1))
        name = result.stdout.decode("utf-8", errors="replace").strip()
        return name if result.ok and name else None

    def config_value(self, key: str) -> str | None:
        """``git config --get <key>`` over git's own scopes, ``None`` when unset (no worktree read)."""
        result = self.bare_run(["config", "--get", key], ok_codes=(0, 1))
        value = result.stdout.decode("utf-8", errors="replace").strip()
        return value if result.ok else None

    def fingerprint(self) -> Fingerprint | None:
        """The working-tree fingerprint, or ``None`` when git cannot give one safely."""
        from coding_agent_playbook.hook_runtime._git_fingerprint import working_tree_fingerprint

        try:
            return working_tree_fingerprint(self)
        except (GitError, OSError):
            return None

    def _empty_tree(self) -> str:
        result = self.run(["hash-object", "-t", "tree", "--stdin"], input=b"")
        return result.stdout.decode("ascii").strip()

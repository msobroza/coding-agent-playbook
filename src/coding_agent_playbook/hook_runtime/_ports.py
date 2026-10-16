"""The repo-bound ports a dispatch builds on demand: git and the trust store (§D.9).

``RuntimeDeps.git`` and ``RuntimeDeps.trust`` are ``None`` in production: the
dispatcher learns the repository only from the payload. Both are built
lazily, because most events never touch them: an Edit or a non-git Bash call
must import no git module and spawn no process (D-6), and the user-local
trust file is read only when an external handler fires.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.hook_runtime._git_parse import DiffLines
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps, TrustPort
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.git import AddedLine, Fingerprint, GitPort, LoggedCommit
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = ["LazyGit", "open_trust_store"]


class LazyGit:
    """A ``GitPort`` that builds the hardened, memoizing ``MemoGit`` on its first call.

    Example::

        >>> git = LazyGit(repo, deps, state=store, secret_paths=cfg.secret_paths)  # doctest: +SKIP
        >>> git.head_tree()  # the first call imports git.py and spawns git
        '4b825dc6...'
    """

    def __init__(
        self,
        repo: RepoInfo,
        deps: RuntimeDeps,
        *,
        state: StateStore | None,
        secret_paths: GlobSet | None,
    ) -> None:
        self._repo = repo
        self._deps = deps
        self._state = state
        self._secret_paths = secret_paths
        self._git: GitPort | None = deps.git

    def _port(self) -> GitPort:
        if self._git is None:
            from coding_agent_playbook.hook_runtime._git_memo import MemoGit

            self._git = MemoGit(  # one dispatch, one snapshot: each distinct read spawns once
                self._repo,
                proc=self._deps.proc,
                env=self._deps.env,
                state=self._state,
                secret_paths=self._secret_paths,
                platform=self._deps.platform,
            )
        return self._git

    def head_tree(self) -> str | None:
        """See ``GitPort.head_tree``."""
        return self._port().head_tree()

    def fingerprint(self) -> Fingerprint | None:
        """See ``GitPort.fingerprint``."""
        return self._port().fingerprint()

    def diff_added(self) -> tuple[AddedLine, ...]:
        """See ``GitPort.diff_added``."""
        return self._port().diff_added()

    def cat_head(self, repo_rel: str) -> bytes | None:
        """See ``GitPort.cat_head``."""
        return self._port().cat_head(repo_rel)

    def ls_untracked(self) -> tuple[str, ...]:
        """See ``GitPort.ls_untracked``."""
        return self._port().ls_untracked()

    def symbolic_ref(self, ref: str) -> str | None:
        """See ``GitPort.symbolic_ref``."""
        return self._port().symbolic_ref(ref)

    def config_value(self, key: str) -> str | None:
        """See ``GitPort.config_value``."""
        return self._port().config_value(key)

    def default_branch(self) -> str | None:
        """See ``GitPort.default_branch``."""
        return self._port().default_branch()

    def merge_base(self, left: str, right: str) -> str | None:
        """See ``GitPort.merge_base``."""
        return self._port().merge_base(left, right)

    def diff_range(self, base: str, head: str) -> DiffLines:
        """See ``GitPort.diff_range``."""
        return self._port().diff_range(base, head)

    def show(self, rev: str, repo_rel: str) -> bytes | None:
        """See ``GitPort.show``."""
        return self._port().show(rev, repo_rel)

    def diff_worktree(self, base: str) -> DiffLines:
        """See ``GitPort.diff_worktree``."""
        return self._port().diff_worktree(base)

    def archive_to(self, rev: str, dest: str, *, skip: Callable[[str], bool]) -> int:
        """See ``GitPort.archive_to``."""
        return self._port().archive_to(rev, dest, skip=skip)

    def grep_word(self, word: str, roots: Sequence[str]) -> bool:
        """See ``GitPort.grep_word``."""
        return self._port().grep_word(word, roots)

    def rev_commit(self, rev: str) -> str | None:
        """See ``GitPort.rev_commit``."""
        return self._port().rev_commit(rev)

    def upstream(self) -> str | None:
        """See ``GitPort.upstream``."""
        return self._port().upstream()

    def unpushed_lines(self, upstream: str | None) -> DiffLines:
        """See ``GitPort.unpushed_lines``."""
        return self._port().unpushed_lines(upstream)

    def porcelain_status(self) -> tuple[tuple[str, str], ...]:
        """See ``GitPort.porcelain_status``."""
        return self._port().porcelain_status()

    def remote_urls(self) -> tuple[tuple[str, str], ...]:
        """See ``GitPort.remote_urls``."""
        return self._port().remote_urls()

    def commit_log(self, rev_range: str, *, limit: int) -> tuple[LoggedCommit, ...]:
        """See ``GitPort.commit_log``."""
        return self._port().commit_log(rev_range, limit=limit)


def open_trust_store(repo: RepoInfo, deps: RuntimeDeps) -> TrustPort | None:
    """``deps.trust``, else the user-local store of ``repo``; ``None`` when it cannot be used.

    A store resolving inside the repository grants nothing (``TrustStoreError``).

    Example::

        >>> open_trust_store(repo, deps)  # doctest: +SKIP
        <coding_agent_playbook.security.trust.TrustStore object at ...>
    """
    if deps.trust is not None:
        return deps.trust
    from coding_agent_playbook.security.trust import (
        TrustStore,
        TrustStoreError,
        default_trust_store_path,
    )

    path = default_trust_store_path(environ=deps.env, platform=deps.platform, home=Path(deps.home))
    try:
        return TrustStore(path, repo_root=Path(repo.worktree_root), now=deps.clock.time)
    except TrustStoreError:
        return None

"""The dispatch's git: ``SafeGit`` answering each distinct read once (specs/prK-lifecycle-hooks.md §D.5.3).

One dispatch is one snapshot of the working tree, yet each Stop stage and hook
asked git its own questions: a default-tier Stop spawned ``rev-parse
HEAD^{tree}`` and ``ls-files --others`` five times each, ``diff HEAD`` four
times and the same ``cat-file`` twice (24 git spawns, 11 distinct; review
finding #4). :class:`MemoGit` keeps the answer of every read-only call for the
life of the instance, and ``_ports.LazyGit`` builds one per dispatch.

- Only the read-only subcommands below are reused, keyed by their full argv,
  stdin and accepted exit codes; a temp-index call (the fingerprint's
  ``add`` / ``write-tree``) always spawns.
- A failed or timed-out call raises before anything is stored, so the next
  caller asks git again.
- The CLI twins keep plain ``SafeGit``: a command may change the tree between
  two of its own reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._git_argv import subcommand
from coding_agent_playbook.hook_runtime.git import SafeGit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.proc import ProcResult

__all__ = ["MEMOIZED_SUBCOMMANDS", "MemoGit", "memo_key"]

#: Subcommands that write neither the repository nor the user's index
#: (``GIT_OPTIONAL_LOCKS=0`` keeps ``status`` from refreshing it).
MEMOIZED_SUBCOMMANDS: Final = frozenset(
    {
        "cat-file",
        "diff",
        "for-each-ref",
        "grep",
        "log",
        "ls-files",
        "merge-base",
        "rev-parse",
        "status",
    }
)

type MemoKey = tuple[tuple[str, ...], bytes | None, tuple[int, ...]]


def memo_key(
    args: Sequence[str], *, input: bytes | None, index_file: str | None, ok_codes: tuple[int, ...]
) -> MemoKey | None:
    """The key a git call is memoized under, or ``None`` when it must always spawn.

    Example::

        >>> memo_key(["rev-parse", "HEAD"], input=None, index_file=None, ok_codes=(0,))
        (('rev-parse', 'HEAD'), None, (0,))
        >>> memo_key(["write-tree"], input=None, index_file="/tmp/i", ok_codes=(0,)) is None
        True
    """
    if index_file is not None or subcommand(args) not in MEMOIZED_SUBCOMMANDS:
        return None
    return (tuple(args), input, ok_codes)


class MemoGit(SafeGit):
    """``SafeGit`` whose read-only calls spawn once per instance (one dispatch).

    Example::

        >>> git = MemoGit(repo, proc=deps.proc, env=deps.env)  # doctest: +SKIP
        >>> git.head_tree() == git.head_tree()  # one ``rev-parse`` spawn
        True
    """

    def __init__(self, repo: RepoInfo, **options: Any) -> None:
        super().__init__(repo, **options)
        self._memo: dict[MemoKey, ProcResult] = {}

    def bare_run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult:
        """``SafeGit.bare_run``, answered from the memo when the same read already ran."""
        key = memo_key(args, input=input, index_file=index_file, ok_codes=ok_codes)
        if key is None:
            return super().bare_run(args, input=input, index_file=index_file, ok_codes=ok_codes)
        if key not in self._memo:
            self._memo[key] = super().bare_run(args, input=input, ok_codes=ok_codes)
        return self._memo[key]

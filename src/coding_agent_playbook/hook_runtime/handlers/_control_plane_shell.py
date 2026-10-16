"""control-plane-guard's Bash command rows (specs/prK-hook-pack.md §E.1, §B.4).

These rows judge what a command *runs*, not what it writes (write targets
are routed like file-tool paths):

- ``playbook sync`` under a pty allocator (``script``, ``expect``,
  ``unbuffer``) or with stdin from a pipe or a redirect denies: trust
  approvals happen only at an interactive sync, and these would answer its
  ``[y/N]`` prompts for the user (a speed bump);
- ``claude mcp add`` (and ``opencode mcp add``) asks, like adding a server
  to ``.mcp.json``;
- a write target that names the hook state dir through an expansion
  (``"$(git rev-parse --git-path playbook-hooks)/interpreter"``) cannot be
  resolved without running git, so its spelling alone denies.

A plain ``playbook sync`` passes. Shell parsing errs toward false negatives;
these are speed bumps, and the off-workstation twins are the control.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["command_verdict", "names_state_dir"]

_SYNC_PROGRAMS: Final = frozenset({"playbook", "coding-agent-playbook"})
_PTY_WRAPPERS: Final = frozenset({"script", "expect", "unbuffer"})
_MCP_CLIS: Final = frozenset({"claude", "opencode"})
#: ``playbook sync`` anywhere in a wrapper's arguments (``script -qc '...'``, ``spawn ...``).
_SYNC_TEXT: Final = re.compile(r"(?:^|[\s/'\"])(?:coding-agent-)?playbook\s+sync\b")


def command_verdict(segment: Segment, *, piped: bool) -> tuple[Decision, str] | None:
    """The ``(decision, rule)`` of one segment's own command, or ``None``.

    ``piped`` says the previous segment at the same depth pipes into this one.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> command_verdict(parse_shell("unbuffer playbook sync", "posix", "/r").segments[0],
        ...                 piped=False)
        (<Decision.DENY: 'deny'>, 'sync_wrapper')
    """
    argv = segment.argv
    if not argv:
        return None
    program = posixpath.basename(argv[0])
    if program in _PTY_WRAPPERS and _SYNC_TEXT.search(" ".join(argv[1:])):
        return Decision.DENY, "sync_wrapper"
    if program in _SYNC_PROGRAMS and _is_sync(argv) and (piped or _stdin_redirected(segment)):
        return Decision.DENY, "sync_stdin"
    if program in _MCP_CLIS and _adds_mcp_server(argv):
        return Decision.ASK, "mcp_add"
    return None


def names_state_dir(raw: str) -> bool:
    """Whether an unexpanded write target spells the hook state dir (``$(...)``, backticks).

    Example::

        >>> names_state_dir('$(git rev-parse --git-path playbook-hooks)/interpreter')
        True
    """
    return STATE_DIR_NAME in raw and ("$" in raw or "`" in raw)


def _is_sync(argv: Sequence[str]) -> bool:
    """Whether ``sync`` is an operand of ``playbook ...`` (option values may precede it)."""
    return "sync" in [arg for arg in argv[1:] if not arg.startswith("-")]


def _stdin_redirected(segment: Segment) -> bool:
    """A ``<``, ``<<``, ``<<<`` or ``<&`` redirect of stdin."""
    return any(r.op.startswith("<") and r.fd in (None, 0) for r in segment.redirects)


def _adds_mcp_server(argv: Sequence[str]) -> bool:
    """``<cli> mcp add|add-json|add-from-claude-desktop ...``."""
    words = list(argv[1:])
    if "mcp" not in words:
        return False
    following = words[words.index("mcp") + 1 : words.index("mcp") + 2]
    return bool(following) and following[0].startswith("add")

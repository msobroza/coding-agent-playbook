"""destructive-command-guard's native twin in ``.claude/settings.json`` (specs/prK-hook-pack.md §E.4).

While the guard is on, Claude Code also gets one ``permissions.deny``
``Bash(<prefix> *)`` row per literal destructive prefix
(``security.patterns.DESTRUCTIVE_NATIVE_PREFIXES``): Claude enforces them
itself, so they hold when the hook interpreter is missing or times out (a
hook then fails open). Only literal prefixes have a native form; the guard's
predicate rows (realpath'd ``rm`` targets, dirty-tree asks, protected-branch
globs) stay hook-only. The rows go through K3's managed-array merge: one lock
entry per string, user entries untouched, ours removed when the guard is off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters._secret_native import DENY_POINTER
from coding_agent_playbook.security.patterns import DESTRUCTIVE_NATIVE_PREFIXES

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = ["DESTRUCTIVE_COMMAND_GUARD", "destructive_native_rows"]

DESTRUCTIVE_COMMAND_GUARD: Final = "destructive-command-guard"


def destructive_native_rows(hooks: Iterable[ResolvedHook]) -> dict[str, tuple[str, ...]]:
    """``{"/permissions/deny": ("Bash(rm -rf / *)", ...)}`` while the guard is on, else ``{}``.

    Example::

        >>> destructive_native_rows([])
        {}
    """
    hook = next((h for h in hooks if h.id == DESTRUCTIVE_COMMAND_GUARD), None)
    if hook is None or "pre_tool_use" not in hook.handlers:
        return {}
    return {DENY_POINTER: tuple(f"Bash({prefix} *)" for prefix in DESTRUCTIVE_NATIVE_PREFIXES)}

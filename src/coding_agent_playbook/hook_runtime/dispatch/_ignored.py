"""The ``ignored`` decision line of a hook call the dispatcher leaves alone (specs/prU-core-python-skills.md D79).

A foreign payload (another harness reached us through ``.claude/settings.json``,
or our own harness reached us misconfigured) and an event outside git are
inert: exit 0, no output. Before D79 they were also invisible, so a real
Claude Code session with ``CLAUDE_PROJECT_DIR`` unset ran with every guard off
and nothing said so. Each such call now leaves one decision line, ids only
(D-10): ``decision: "ignored"``, ``rule_id`` the reason. ``playbook-hook
doctor`` summarizes them (``_doctor_ignored``).

A call outside git has no worktree state root, so its line goes to the
user-level state root beside the trust store
(``$XDG_STATE_HOME/coding-agent-playbook/playbook-hooks``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch._decision_log import DISPATCHER_ID, LogLine
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, StateStore

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps

__all__ = ["IGNORED", "NOT_A_REPO", "ignored_line", "user_state_root", "user_state_store"]

#: The ``decision`` of a call the dispatcher ignored.
IGNORED: Final = "ignored"
#: The reason of an event whose project dir is outside any git repository (K-12).
NOT_A_REPO: Final = "not_a_repo"
_DIR_MODE: Final = 0o700


def ignored_line(reason: str) -> LogLine:
    """The dispatcher's line for one ignored call; ``reason`` is a parser marker or ``not_a_repo``.

    Example::

        >>> ignored_line("timestamp").rule_id
        'timestamp'
    """
    return LogLine(hook_id=DISPATCHER_ID, rule_id=reason, decision=IGNORED, effective="none")


def user_state_store(deps: RuntimeDeps) -> StateStore | None:
    """The user-level state root for calls outside git, or ``None`` when it cannot be created.

    It sits beside the trust store, so it follows ``XDG_STATE_HOME``
    (Windows: ``LOCALAPPDATA``) and ``deps.home`` the same way.

    Example::

        >>> user_state_store(RuntimeDeps(env={"XDG_STATE_HOME": "/s"})).root  # doctest: +SKIP
        PosixPath('/s/coding-agent-playbook/playbook-hooks')
    """
    root = user_state_root(deps)
    try:
        os.makedirs(root.parent, mode=_DIR_MODE, exist_ok=True)
    except OSError:
        return None
    return StateStore(root, clock=deps.clock)


def user_state_root(deps: RuntimeDeps) -> Path:
    """Where :func:`user_state_store` lives, without creating anything (doctor reads it)."""
    from coding_agent_playbook.security.trust import default_trust_store_path  # cold path

    trust = default_trust_store_path(environ=deps.env, platform=deps.platform, home=Path(deps.home))
    return trust.parent / STATE_DIR_NAME

"""The ``session_start`` snapshot of the default branch, and the "HEAD moved" report (OQ-28).

``subagent_start`` is not a canonical event, so subagent-stop-verify compares
the default branch against the session's snapshot instead (coarser):
``sessions/<sha256(session_id)[:16]>/head_snapshot.json`` holds
``{"v": 1, "branch": "main", "commit": "<sha>"}``. This module is the shape and
the reader; without a snapshot the report is skipped. The report never
rewrites history: it only tells the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, session_key

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.state.session import SessionState

__all__ = ["HeadSnapshot", "head_moved_note", "head_snapshot_doc", "read_head_snapshot"]

_SHA: Final = re.compile(r"[0-9a-f]{40,64}")
_BRANCH_MAX_CHARS: Final = 200
_SHORT: Final = 8


@dataclass(frozen=True, slots=True)
class HeadSnapshot:
    """The default branch and its commit when the session started.

    Example::

        >>> HeadSnapshot.from_json({"v": 1, "branch": "main", "commit": "ab" * 20}).branch
        'main'
    """

    branch: str
    commit: str

    def to_json(self) -> dict[str, Any]:
        """The stored record."""
        return {"v": 1, "branch": self.branch, "commit": self.commit}

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> HeadSnapshot | None:
        """A stored snapshot, or ``None`` when absent or malformed."""
        branch, commit = document.get("branch"), document.get("commit")
        if document.get("v") != 1 or not isinstance(branch, str) or not isinstance(commit, str):
            return None
        if not 0 < len(branch) <= _BRANCH_MAX_CHARS or not _SHA.fullmatch(commit):
            return None
        return cls(branch, commit)


def head_snapshot_doc(session_id: str) -> str:
    """The state document of ``session_id``'s snapshot.

    Example::

        >>> head_snapshot_doc("abc")
        'sessions/ba7816bf8f01cfea/head_snapshot.json'
    """
    return f"sessions/{session_key(session_id)}/head_snapshot.json"


def read_head_snapshot(session: SessionState, session_id: str) -> HeadSnapshot | None:
    """The session's snapshot, ``None`` without one (or when stateless).

    Example: ``read_head_snapshot(ctx.session, ev.session_id)``.
    """
    try:
        return HeadSnapshot.from_json(session.store.read_json(head_snapshot_doc(session_id)))
    except (StateUnavailable, OSError):
        return None


def head_moved_note(session: SessionState, git: GitPort, session_id: str) -> str | None:
    """One user note when the snapshot's branch moved, once per new commit; else ``None``.

    Example::

        >>> head_moved_note(ctx.session, ctx.git, ev.session_id)  # doctest: +SKIP
        'Default branch "main" moved during this session (abababab -> cdcdcdcd); ...'
    """
    snapshot = read_head_snapshot(session, session_id)
    if snapshot is None:
        return None
    try:
        now = git.rev_commit(snapshot.branch)
    except Exception:  # a report only: no git, a timeout or a bad ref says nothing
        return None
    if now is None or now == snapshot.commit:
        return None
    if not session.once(f"head-moved:{snapshot.branch}:{now}"):
        return None
    return (
        f"Default branch {quote_data(snapshot.branch, 80)} moved during this session "
        f"({snapshot.commit[:_SHORT]} -> {now[:_SHORT]}); reported only, nothing was rewritten."
    )

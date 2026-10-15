"""The session's active playbook prompt: record shape and reader (specs/prK-hook-pack.md §E.0.4, OQ-45).

When the user starts a turn with a playbook slash command (``/review``), the
``user_prompt_submit`` dispatcher branch records which prompt is active, in
``sessions/<sha256(session_id)[:16]>/active_prompt.json``:

``{"v": 1, "slash": "review", "id": "review", "turn_id": "pr_17"}``

prompt-write-scope-guard and prompt-output-contract-on-stop both read it. K7
owns the writer (a dispatcher branch active whenever either hook is on, OQ-45);
this module is the shape and the reader only, so the Stop stage can be built
and tested first. No prompt text is ever stored (D-10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.state import StateUnavailable, session_key

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = ["RECORD_VERSION", "ActivePrompt", "active_prompt_doc", "read_active_prompt"]

RECORD_VERSION: Final = 1
_SLASH_MAX_CHARS: Final = 128


@dataclass(frozen=True, slots=True)
class ActivePrompt:
    """Which playbook prompt the user invoked, and in which turn (``None``: unknown).

    Example::

        >>> ActivePrompt("review", "review", "pr_17").current_for("pr_18")
        False
    """

    slash: str
    prompt_id: str
    turn_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        """The stored record."""
        return {
            "v": RECORD_VERSION,
            "slash": self.slash,
            "id": self.prompt_id,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> ActivePrompt | None:
        """A stored record, or ``None`` when absent, of another version or malformed."""
        slash, prompt_id, turn = document.get("slash"), document.get("id"), document.get("turn_id")
        if document.get("v") != RECORD_VERSION or not isinstance(turn, str | None):
            return None
        if not isinstance(slash, str) or not isinstance(prompt_id, str):
            return None
        return cls(slash, prompt_id, turn) if _short(slash) and _short(prompt_id) else None

    def current_for(self, turn_id: str | None) -> bool:
        """Whether the record still describes the turn ``turn_id`` (unknown on either side: yes)."""
        return self.turn_id is None or turn_id is None or self.turn_id == turn_id


def active_prompt_doc(session_id: str) -> str:
    """The state document of ``session_id``'s active-prompt record.

    Example::

        >>> active_prompt_doc("abc")
        'sessions/ba7816bf8f01cfea/active_prompt.json'
    """
    return f"sessions/{session_key(session_id)}/active_prompt.json"


def read_active_prompt(store: StateStore, session_id: str) -> ActivePrompt | None:
    """The session's active prompt, or ``None`` (no record, or the store is unusable).

    Example: ``read_active_prompt(ctx.session.store, ev.session_id)``.
    """
    try:
        document = store.read_json(active_prompt_doc(session_id))
    except (StateUnavailable, OSError):
        return None
    return ActivePrompt.from_json(document)


def _short(value: str) -> bool:
    return 0 < len(value) <= _SLASH_MAX_CHARS

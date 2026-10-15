"""The Stop coordinator's state: the stop chain and the last green tree (specs/prK-lifecycle-hooks.md §D.5.1, §D.6.1).

A **stop chain** is the run of Stops linked by ``stop_hook_active=true``
within one turn. It lives in ``sessions/<sid>/stop.json`` (a subagent's in
``sessions/<sid>/agents/<aid>/stop.json``, §D.5.6) as ``{turn_id, blocks,
last_blocked_fp, last_stage}``, and restarts on a new ``turn_id`` or when
``stop_hook_active`` is false. ``stop/last_green`` is worktree-level: the
fingerprint of the last tree every default stage passed on.

An unusable store reads as a fresh chain and a failed write returns
``False``: the coordinator then only reports, never blocks (§D.4), because a
budget it cannot count could block forever.
"""

from __future__ import annotations

import dataclasses
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.state import StateUnavailable, session_key

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "LAST_GREEN",
    "StopChain",
    "chain_document",
    "load_chain",
    "read_last_green",
    "save_chain",
    "write_last_green",
]

#: The worktree-level last-green fingerprint (§D.6.1 layout).
LAST_GREEN: Final = "stop/last_green"
_KEY_MAX: Final = 256


@dataclass(frozen=True, slots=True)
class StopChain:
    """One stop chain's budget state.

    Example::

        >>> StopChain(turn_id="t1").blocked("4b82", "lint").blocks
        1
    """

    turn_id: str | None = None
    blocks: int = 0
    last_blocked_fp: str | None = None
    last_stage: str = ""

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> StopChain:
        """A stored chain; a hand-edited or partial document reads field by field."""
        blocks = document.get("blocks")
        return cls(
            turn_id=_opt_str(document.get("turn_id")),
            blocks=blocks if type(blocks) is int and blocks > 0 else 0,
            last_blocked_fp=_opt_str(document.get("last_blocked_fp")),
            last_stage=_opt_str(document.get("last_stage")) or "",
        )

    def for_event(self, ev: CanonicalEvent) -> StopChain:
        """This chain, or a fresh one when ``ev`` starts a new chain (§D.5.1 block budget)."""
        active = ev.stop is not None and ev.stop.stop_hook_active
        return self if active and self.turn_id == ev.turn_id else StopChain(turn_id=ev.turn_id)

    def blocked(self, fingerprint: str | None, stage: str) -> StopChain:
        """The chain after one more block of ``fingerprint``, first red at ``stage``."""
        return dataclasses.replace(
            self, blocks=self.blocks + 1, last_blocked_fp=fingerprint, last_stage=stage
        )


def chain_document(session_id: str, agent_id: str | None = None) -> str:
    """The state path of the session's chain, or of subagent ``agent_id``'s (ids hashed).

    Example::

        >>> chain_document("abc")
        'sessions/ba7816bf8f01cfea/stop.json'
    """
    base = f"sessions/{session_key(session_id)}"
    return (
        f"{base}/stop.json"
        if agent_id is None
        else f"{base}/agents/{session_key(agent_id)}/stop.json"
    )


def load_chain(store: StateStore, document: str) -> StopChain:
    """The stored chain, or a fresh one when there is none or the store is unusable."""
    try:
        return StopChain.from_document(store.read_json(document))
    except StateUnavailable:
        return StopChain()


def save_chain(store: StateStore, document: str, chain: StopChain) -> bool:
    """Store ``chain``; ``False`` when the store cannot keep it (the gate must not block)."""
    try:
        store.write_json(document, dataclasses.asdict(chain))
    except StateUnavailable:
        return False
    return True


def read_last_green(store: StateStore) -> str | None:
    """The last all-green fingerprint key of this worktree, if any."""
    try:
        data = store.read_bytes(LAST_GREEN, limit=_KEY_MAX)
    except StateUnavailable:
        return None
    return (data or b"").decode("ascii", errors="replace").strip() or None


def write_last_green(store: StateStore, key: str) -> None:
    """Record ``key`` as the last all-green tree; silently skipped when stateless."""
    with suppress(StateUnavailable):
        store.replace_bytes(LAST_GREEN, f"{key}\n".encode("ascii", errors="replace"))


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None

"""The session's active playbook prompt, derived when a consumer needs it (specs/prK-hook-pack.md §E.3).

Which playbook prompt (slash command) the turn is running is shared state:
prompt-write-scope-guard enforces its write scope and
prompt-output-contract-on-stop checks its output contract. Neither needs a
``user_prompt_submit`` process for it (review finding #6, OQ-45):

- :func:`resolve_active_prompt` is what a consumer calls. The first call of a
  turn reads the transcript's turn-opening entry (``_prompt_boundary``): a
  ``/<slash>`` of a known playbook prompt is the active prompt, anything else
  is none. The answer is kept as the turn's record, so later calls of the
  same turn (Claude's ``prompt_id``) cost one small state read.
- ``pre_tool_use`` on the ``Skill`` tool (:func:`observe`, a dispatcher branch
  run while either consumer is enabled): the model ran a command itself, which
  opens no turn; a known ``tool_input.skill`` becomes the turn's record. An
  unknown skill leaves the record alone.

The record is ``sessions/<sha256(session_id)[:16]>/prompt.json``:

``{"v": 2, "slash": "review", "via": "prompt", "turn_id": "pr_17", "anchor": null}``

``slash`` is ``null`` for a turn with no playbook prompt. Without turn ids,
a Skill record carries ``anchor``, the transcript uuid of the turn's opening
entry, and lasts until a new entry opens a turn. Known slashes are the keys of
prompt-write-scope-guard's ``scopes`` and the rows of the ``prompts`` table
that carry an output contract (K6), both rendered at sync. No prompt text is
ever stored (D-10). Stdlib and ``hook_runtime`` only.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime._prompt_boundary import (
    last_prompt_boundary,
    slash_of_prompt,
)
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.state import StateUnavailable, session_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "ACTIVE_PROMPT_CONSUMERS",
    "RECORD_VERSION",
    "SCOPE_GUARD_ID",
    "SKILL_TOOL",
    "ActivePrompt",
    "TurnRecord",
    "active_prompt_document",
    "consumers_enabled",
    "known_slashes",
    "observe",
    "read_turn_record",
    "resolve_active_prompt",
    "slash_of_prompt",
    "write_turn_record",
]

#: The hook that enforces a prompt's write scope; its pre_tool_use config holds ``scopes``.
SCOPE_GUARD_ID: Final = "prompt-write-scope-guard"
#: The hooks that read the record (OQ-45): the Skill branch runs while any one is enabled.
ACTIVE_PROMPT_CONSUMERS: Final = (SCOPE_GUARD_ID, "prompt-output-contract-on-stop")
#: Claude Code's tool for a model-invoked command or skill.
SKILL_TOOL: Final = "Skill"
#: The stored record's shape version; a record of another version reads as none.
RECORD_VERSION: Final = 2
#: The guard_config table of output contracts (K6): its keys are slashes too.
_PROMPTS_TABLE: Final = "prompts"
_SLASH_MAX_CHARS: Final = 128

type Via = Literal["prompt", "skill"]


@dataclass(frozen=True, slots=True)
class ActivePrompt:
    """The playbook prompt a turn is running, how it started, and in which turn.

    ``turn_id`` is ``None`` when the harness gave no turn id.
    Example: ``ActivePrompt("review", "prompt", "pr_17")``.
    """

    slash: str
    via: Via
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """What the state remembers of one turn: its playbook prompt (``slash``; ``None``: none).

    Example::

        >>> TurnRecord(None, "prompt", "pr_18").active() is None
        True
    """

    slash: str | None
    via: Via
    turn_id: str | None = None
    anchor: str | None = None

    def active(self) -> ActivePrompt | None:
        """The active prompt this record names, if any."""
        return None if self.slash is None else ActivePrompt(self.slash, self.via, self.turn_id)

    def to_json(self) -> dict[str, Any]:
        """The stored record."""
        return {
            "v": RECORD_VERSION,
            "slash": self.slash,
            "via": self.via,
            "turn_id": self.turn_id,
            "anchor": self.anchor,
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> TurnRecord | None:
        """A stored record, or ``None`` when of another version or malformed."""
        slash, via = document.get("slash"), document.get("via")
        turn, anchor = document.get("turn_id"), document.get("anchor")
        if document.get("v") != RECORD_VERSION or via not in ("prompt", "skill"):
            return None
        if not all(isinstance(value, str | None) for value in (slash, turn, anchor)):
            return None
        if slash is not None and not 0 < len(slash) <= _SLASH_MAX_CHARS:
            return None
        return cls(slash, "skill" if via == "skill" else "prompt", turn, anchor)


def active_prompt_document(session_id: str) -> str:
    """The state path of ``session_id``'s record (the id hashed, never raw).

    Example::

        >>> active_prompt_document("abc")
        'sessions/ba7816bf8f01cfea/prompt.json'
    """
    return f"sessions/{session_key(session_id)}/prompt.json"


def read_turn_record(store: StateStore, session_id: str) -> TurnRecord | None:
    """The session's last turn record, or ``None``; one ``stat`` when there is none.

    A corrupt, hand-edited or unreadable record reads as none.
    Example: ``read_turn_record(store, "s1")`` -> ``TurnRecord('review', 'prompt', 'pr_17')``.
    """
    rel = active_prompt_document(session_id)
    if not os.path.exists(store.path(rel)):
        return None
    try:
        document = store.read_json(rel)
    except (StateUnavailable, OSError):
        return None
    return TurnRecord.from_json(document)


def write_turn_record(store: StateStore, session_id: str, record: TurnRecord) -> None:
    """Make ``record`` the session's turn record; silently skipped when stateless."""
    with suppress(StateUnavailable):
        store.write_json(active_prompt_document(session_id), record.to_json())


def resolve_active_prompt(
    ev: CanonicalEvent, cfg: GuardConfig, store: StateStore
) -> ActivePrompt | None:
    """The playbook prompt ``ev``'s turn runs, or ``None``; derived once per turn.

    Example::

        >>> resolve_active_prompt(edit_after_review, cfg, store)  # doctest: +SKIP
        ActivePrompt(slash='review', via='prompt', turn_id='pr_17')
    """
    record = read_turn_record(store, ev.session_id)
    if record is not None and ev.turn_id is not None and record.turn_id == ev.turn_id:
        return record.active()  # this turn is already resolved
    boundary = last_prompt_boundary(ev.transcript_path)
    anchor = None if boundary is None else boundary.uuid
    if record is not None and record.anchor is not None and record.anchor == anchor:
        return record.active()  # a Skill run in this turn, harness without turn ids
    slash = None if boundary is None else boundary.slash
    found = slash if slash is not None and slash in known_slashes(cfg) else None
    if ev.turn_id is not None:
        write_turn_record(store, ev.session_id, TurnRecord(found, "prompt", ev.turn_id))
    return None if found is None else ActivePrompt(found, "prompt", ev.turn_id)


def known_slashes(cfg: GuardConfig) -> frozenset[str]:
    """The slashes of the playbook prompts a consumer acts on: a write scope or an output contract.

    The ``prompts`` table lists every rendered prompt; one with an empty
    ``output_contract`` (and no scope) is not active, like any other prompt.

    Example::

        >>> sorted(known_slashes(cfg))  # doctest: +SKIP
        ['explain', 'generate-tests', 'review']
    """
    slashes: set[str] = set()
    guard = cfg.hooks.get(SCOPE_GUARD_ID)
    spec = None if guard is None else guard.handlers.get(EventName.PRE_TOOL_USE)
    if spec is not None:
        slashes.update(_keys(spec.config.get("scopes")))
    slashes.update(_contract_slashes(cfg.tables.get(_PROMPTS_TABLE)))
    return frozenset(slashes)


def consumers_enabled(hook_ids: Iterable[str]) -> bool:
    """Whether any hook that reads the record is among ``hook_ids`` (OQ-45).

    Example::

        >>> consumers_enabled(["prompt-output-contract-on-stop"])
        True
    """
    return any(hook_id in ACTIVE_PROMPT_CONSUMERS for hook_id in hook_ids)


def observe(ev: CanonicalEvent, cfg: GuardConfig, store: StateStore) -> None:
    """The dispatcher branch: a model-run ``Skill`` of a known prompt becomes the turn's record.

    Example::

        observe(ev, cfg, store)  # a Skill "review" records TurnRecord("review", "skill", turn)
    """
    if not consumers_enabled(cfg.hooks):
        return
    skill = _skill_of(ev)
    if skill is None or skill not in known_slashes(cfg):
        return
    anchor = None
    if ev.turn_id is None:  # no turn id to scope it: the transcript's turn entry does
        boundary = last_prompt_boundary(ev.transcript_path)
        anchor = None if boundary is None else boundary.uuid
    write_turn_record(store, ev.session_id, TurnRecord(skill, "skill", ev.turn_id, anchor))


def _skill_of(ev: CanonicalEvent) -> str | None:
    """The command a ``pre_tool_use`` ``Skill`` call runs, else ``None``."""
    if ev.name is not EventName.PRE_TOOL_USE or ev.tool is None or ev.tool.name != SKILL_TOOL:
        return None
    skill = ev.tool.raw_input.get("skill")
    return skill.strip().lstrip("/") if isinstance(skill, str) else None


def _contract_slashes(table: Any) -> list[str]:
    """The slashes of the ``prompts`` table whose row carries a non-empty ``output_contract``."""
    if not isinstance(table, Mapping):
        return []
    return [
        slash
        for slash, row in table.items()
        if isinstance(slash, str) and isinstance(row, Mapping) and row.get("output_contract")
    ]


def _keys(table: Any) -> list[str]:
    """The string keys of ``table`` when it is a mapping (anything else: none)."""
    return [key for key in table if isinstance(key, str)] if isinstance(table, Mapping) else []

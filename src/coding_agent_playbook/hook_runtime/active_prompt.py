"""The session's active playbook prompt: a dispatcher branch, not a hook (specs/prK-hook-pack.md §E.3).

Which playbook prompt (slash command) the session is running is shared state:
prompt-write-scope-guard enforces its write scope and
prompt-output-contract-on-stop checks its output contract. The record is
therefore kept by the dispatcher itself whenever **either** hook is enabled,
so disabling the guard never leaves the output-contract stage inert (OQ-45).

- ``user_prompt_submit``: a prompt that *starts* with ``/<slash>``, or the
  harness's command wrapper naming it (``<command-name>/<slash></command-name>``),
  records ``{slash, via}`` for a known playbook prompt; any other prompt clears
  the record. Uncertain detection records nothing (fail open).
- ``pre_tool_use`` on the ``Skill`` tool: the model ran a command itself, which
  fires no ``UserPromptSubmit``; a known ``tool_input.skill`` is recorded the
  same way. An unknown skill leaves the record alone.

The record is ``sessions/<sha256(session_id)[:16]>/prompt.json``:

``{"v": 1, "slash": "review", "via": "prompt", "turn_id": "pr_17"}``

It is deleted when cleared, so a reader with no active prompt pays one
``stat``. ``turn_id`` is the event's turn (Claude's ``prompt_id``) so the Stop
stage can ignore a record left over from another turn. Known slashes are the
keys of prompt-write-scope-guard's ``scopes`` and of the ``prompts`` table
(K6's output contracts), both rendered at sync. No prompt text is ever stored
(D-10). Stdlib and ``hook_runtime`` only.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.state import StateUnavailable, session_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.config import GuardConfig
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "ACTIVE_PROMPT_CONSUMERS",
    "RECORD_VERSION",
    "SCOPE_GUARD_ID",
    "SKILL_TOOL",
    "ActivePrompt",
    "active_prompt_document",
    "clear_active_prompt",
    "consumers_enabled",
    "known_slashes",
    "observe",
    "read_active_prompt",
    "record_active_prompt",
    "slash_of_prompt",
]

#: The hook that enforces a prompt's write scope; its pre_tool_use config holds ``scopes``.
SCOPE_GUARD_ID: Final = "prompt-write-scope-guard"
#: The hooks that read the record (OQ-45): the branch runs while any one is enabled.
ACTIVE_PROMPT_CONSUMERS: Final = (SCOPE_GUARD_ID, "prompt-output-contract-on-stop")
#: Claude Code's tool for a model-invoked command or skill.
SKILL_TOOL: Final = "Skill"
#: The stored record's shape version; a record of another version reads as none.
RECORD_VERSION: Final = 1
#: The guard_config table of output contracts (K6): its keys are slashes too.
_PROMPTS_TABLE: Final = "prompts"
#: Only the head of a prompt is searched for the command wrapper.
_SCAN_CHARS: Final = 4096
_SLASH_MAX_CHARS: Final = 128
_NAME: Final = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"
_RAW: Final = re.compile(rf"/({_NAME})(?:\s|$)")
_WRAPPER: Final = re.compile(rf"<command-name>\s*/?({_NAME})\s*</command-name>")


@dataclass(frozen=True, slots=True)
class ActivePrompt:
    """The playbook prompt a session is running, how it started, and in which turn.

    ``turn_id`` is ``None`` when the harness gave no turn id.

    Example::

        >>> ActivePrompt("review", "prompt", "pr_17").current_for("pr_18")
        False
    """

    slash: str
    via: Literal["prompt", "skill"]
    turn_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        """The stored record."""
        return {"v": RECORD_VERSION, "slash": self.slash, "via": self.via, "turn_id": self.turn_id}

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> ActivePrompt | None:
        """A stored record, or ``None`` when absent, of another version or malformed."""
        slash, via, turn = document.get("slash"), document.get("via"), document.get("turn_id")
        if document.get("v") != RECORD_VERSION or not isinstance(turn, str | None):
            return None
        if not isinstance(slash, str) or not 0 < len(slash) <= _SLASH_MAX_CHARS:
            return None
        if via == "prompt" or via == "skill":
            return cls(slash, via, turn)
        return None

    def current_for(self, turn_id: str | None) -> bool:
        """Whether the record still describes the turn ``turn_id`` (unknown on either side: yes)."""
        return self.turn_id is None or turn_id is None or self.turn_id == turn_id


def active_prompt_document(session_id: str) -> str:
    """The state path of ``session_id``'s record (the id hashed, never raw).

    Example::

        >>> active_prompt_document("abc")
        'sessions/ba7816bf8f01cfea/prompt.json'
    """
    return f"sessions/{session_key(session_id)}/prompt.json"


def read_active_prompt(store: StateStore, session_id: str) -> ActivePrompt | None:
    """The session's active prompt, or ``None``; one ``stat`` when there is none.

    A corrupt, hand-edited or unreadable record reads as none (fail open).

    Example::

        >>> read_active_prompt(store, "s1")  # doctest: +SKIP
        ActivePrompt(slash='review', via='prompt', turn_id='pr_17')
    """
    rel = active_prompt_document(session_id)
    if not os.path.exists(store.path(rel)):
        return None
    try:
        document = store.read_json(rel)
    except (StateUnavailable, OSError):
        return None
    return ActivePrompt.from_json(document)


def record_active_prompt(store: StateStore, session_id: str, prompt: ActivePrompt) -> None:
    """Make ``prompt`` the session's active prompt; silently skipped when stateless."""
    with suppress(StateUnavailable):
        store.write_json(active_prompt_document(session_id), prompt.to_json())


def clear_active_prompt(store: StateStore, session_id: str) -> None:
    """Forget the session's active prompt; silently skipped when stateless."""
    with suppress(StateUnavailable):
        store.remove(active_prompt_document(session_id))


def slash_of_prompt(text: str) -> str | None:
    """The slash a submitted prompt invokes, raw or inside the command wrapper; else ``None``.

    Only a prompt that *starts* with the command counts: ``please /review``
    is prose, not an invocation, and an unrecognized wrapper is no command.

    Example::

        >>> slash_of_prompt("/security-review src/app.py")
        'security-review'
        >>> slash_of_prompt("<command-name>/review</command-name>\\n<command-args></command-args>")
        'review'
        >>> slash_of_prompt("fix it") is None
        True
    """
    head = text[:_SCAN_CHARS].lstrip()
    raw = _RAW.match(head)
    if raw is not None:
        return raw.group(1)
    if not head.startswith("<command-"):
        return None
    wrapped = _WRAPPER.search(head)
    return wrapped.group(1) if wrapped is not None else None


def known_slashes(cfg: GuardConfig) -> frozenset[str]:
    """The slashes of the playbook prompts the consumers know (scopes, output contracts).

    Example::

        >>> sorted(known_slashes(cfg))  # doctest: +SKIP
        ['explain', 'generate-tests', 'review']
    """
    slashes: set[str] = set()
    guard = cfg.hooks.get(SCOPE_GUARD_ID)
    spec = None if guard is None else guard.handlers.get(EventName.PRE_TOOL_USE)
    if spec is not None:
        slashes.update(_keys(spec.config.get("scopes")))
    slashes.update(_keys(cfg.tables.get(_PROMPTS_TABLE)))
    return frozenset(slashes)


def consumers_enabled(hook_ids: Iterable[str]) -> bool:
    """Whether any hook that reads the record is among ``hook_ids`` (OQ-45).

    Example::

        >>> consumers_enabled(["prompt-output-contract-on-stop"])
        True
    """
    return any(hook_id in ACTIVE_PROMPT_CONSUMERS for hook_id in hook_ids)


def observe(ev: CanonicalEvent, cfg: GuardConfig, store: StateStore) -> None:
    """The dispatcher branch: record or clear the active prompt for ``ev``, before any hook runs.

    Example::

        observe(ev, cfg, store)  # a "/review" prompt records ActivePrompt("review", "prompt")
    """
    if not consumers_enabled(cfg.hooks):
        return
    if ev.name is EventName.USER_PROMPT_SUBMIT:
        slash = slash_of_prompt(ev.prompt or "")
        if slash is not None and slash in known_slashes(cfg):
            record_active_prompt(store, ev.session_id, ActivePrompt(slash, "prompt", ev.turn_id))
        else:
            clear_active_prompt(store, ev.session_id)
        return
    skill = _skill_of(ev)
    if skill is not None and skill in known_slashes(cfg):
        record_active_prompt(store, ev.session_id, ActivePrompt(skill, "skill", ev.turn_id))


def _skill_of(ev: CanonicalEvent) -> str | None:
    """The command a ``pre_tool_use`` ``Skill`` call runs, else ``None``."""
    if ev.name is not EventName.PRE_TOOL_USE or ev.tool is None or ev.tool.name != SKILL_TOOL:
        return None
    skill = ev.tool.raw_input.get("skill")
    return skill.strip().lstrip("/") if isinstance(skill, str) else None


def _keys(table: Any) -> list[str]:
    """The string keys of ``table`` when it is a mapping (anything else: none)."""
    return [key for key in table if isinstance(key, str)] if isinstance(table, Mapping) else []

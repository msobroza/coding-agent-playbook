"""Pipeline step 8: what a dispatch records after its one write (specs/prK-lifecycle-hooks.md §D.6).

Nothing here can change what the harness was told, so it all runs after the
write and never raises:

- the decision-log lines of the fan-out, and an ``override`` line when a
  post-tool event arrives for a tool call a guard asked about (the user said
  yes);
- the asked set: each attended ``ask`` on ``pre_tool_use`` marks its
  ``tool_use_id`` with the hook that asked;
- the session ledger on ``post_tool_use`` / ``post_tool_use_failure``: the
  paths the tool touched and the files a shell command wrote;
- deferred notes, pushed where Claude has no user-visible channel
  (``session_end``, ``pre_compact``);
- the bounded TTL sweep on ``session_start`` (and lazily on ``stop``).
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._decision_log import DISPATCHER_ID, LogLine, lines_for
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, Harness, ToolClass
from coding_agent_playbook.hook_runtime.ledger import Ledger
from coding_agent_playbook.hook_runtime.paths import normalize_path
from coding_agent_playbook.hook_runtime.state import StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime._decision_log import DecisionLog
    from coding_agent_playbook.hook_runtime._execute import Ran
    from coding_agent_playbook.hook_runtime.config import GuardConfig
    from coding_agent_playbook.hook_runtime.decision import CombinedResult
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.session import SessionState
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = ["PostWrite", "record_after_write"]

_POST_TOOL: Final = frozenset({EventName.POST_TOOL_USE, EventName.POST_TOOL_USE_FAILURE})
#: Claude events whose output no user sees: their notes wait for the next prompt.
_NO_NOTE_CHANNEL: Final = frozenset({EventName.SESSION_END, EventName.PRE_COMPACT})
_DECISION_LOG_FAILED: Final = "playbook-hook: the decision log could not be written"


@dataclass(frozen=True, slots=True, kw_only=True)
class PostWrite:
    """Everything step 8 reads: the event, its fan-out and the stores."""

    ev: CanonicalEvent
    cfg: GuardConfig
    ran: Sequence[Ran]
    combined: CombinedResult
    store: StateStore
    session: SessionState
    log: DecisionLog
    deps: RuntimeDeps


def record_after_write(post: PostWrite) -> list[str]:
    """Run step 8; returns the internal stderr notes (at most one per session each).

    Example::

        >>> record_after_write(PostWrite(ev=ev, cfg=cfg, ...))  # doctest: +SKIP
        []
    """
    notes: list[str] = []
    lines = lines_for(post.ran, post.combined.outcomes) + _overrides(post)
    if not post.log.write(lines) and post.session.once("note:decision_log"):
        notes.append(_DECISION_LOG_FAILED)
    _mark_asks(post)
    _ledger(post)
    _defer_notes(post)
    _sweep(post)
    return notes


def _overrides(post: PostWrite) -> list[LogLine]:
    tool = post.ev.tool
    if post.ev.name not in _POST_TOOL or tool is None or not tool.use_id:
        return []
    return [
        LogLine(hook_id=hook_id or DISPATCHER_ID, decision="override", effective="none")
        for hook_id in post.session.askers(tool.use_id)
    ]


def _mark_asks(post: PostWrite) -> None:
    tool = post.ev.tool
    if post.ev.name is not EventName.PRE_TOOL_USE or tool is None or not tool.use_id:
        return
    if post.combined.decision is not Decision.ASK:
        return
    for outcome in post.combined.outcomes:
        if outcome.effective is Decision.ASK:
            post.session.mark_asked(tool.use_id, outcome.hook_id)


def _ledger(post: PostWrite) -> None:
    ev, tool = post.ev, post.ev.tool
    if ev.name not in _POST_TOOL or tool is None:
        return
    writes = (*tool.write_paths, *_shell_writes(ev, tool, post.deps))
    if not tool.paths and not writes:
        return
    ledger = Ledger(
        post.store,
        ev.session_id,
        path_classes=post.cfg.path_classes,
        secret_paths=post.cfg.secret_paths,
        now=post.deps.clock.time,
        platform=post.deps.platform,
    )
    ledger.record_touch(
        event=ev.name, tool_class=tool.tool_class, tool=tool.name, paths=tool.paths, writes=writes
    )


def _shell_writes(ev: CanonicalEvent, tool: ToolCall, deps: RuntimeDeps) -> list[NormalizedPath]:
    """The files a shell command wrote, normalized; dynamic targets (``$X``) are unknowable."""
    if tool.tool_class is not ToolClass.SHELL or tool.command is None:
        return []
    from coding_agent_playbook.hook_runtime.shell import write_targets

    found: list[NormalizedPath] = []
    for segment in tool.command.segments:
        for target in write_targets(segment):
            if "$" in target or "`" in target:
                continue
            found.append(
                normalize_path(
                    target,
                    base=segment.cwd or ev.cwd,
                    repo=ev.repo,
                    home=deps.home,
                    platform=deps.platform,
                )
            )
    return found


def _defer_notes(post: PostWrite) -> None:
    if post.ev.harness is not Harness.CLAUDE_CODE or post.ev.name not in _NO_NOTE_CHANNEL:
        return
    for note in post.combined.user_notes:
        post.session.push_note(note)


def _sweep(post: PostWrite) -> None:
    name = post.ev.name
    if name is not EventName.SESSION_START and not (
        name is EventName.STOP and _sweep_due(post.store)
    ):
        return
    with suppress(StateUnavailable, OSError):
        post.store.sweep(ttl_days=post.cfg.state_ttl_days)


def _sweep_due(store: StateStore) -> bool:
    try:
        return store.sweep_due()
    except (StateUnavailable, OSError):
        return False

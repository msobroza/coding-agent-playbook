"""Shared pieces of the in-process dispatch tests (specs/prK-lifecycle-hooks.md §D.9).

The fixtures ``repo`` (a synced :class:`GuardRepo`), ``resolver`` (a
``FakeHandlerResolver``) and ``make_deps`` live in this directory's
``conftest.py``; these helpers build handlers and run one event.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch import run_event
from coding_agent_playbook.hook_runtime.event import EventName, Harness

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.harness import WireOutput
    from coding_agent_playbook.hook_runtime.registry import HandlerContext, HandlerFn
    from tests.hook_runtime.guard_repo import GuardRepo

PRE = EventName.PRE_TOOL_USE
POST = EventName.POST_TOOL_USE


def verdict(decision: Decision, reason: str = "", **extra: Any) -> HandlerFn:
    """A handler that always returns ``decision`` for its own hook."""

    def handler(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
        return HandlerResult(
            decision=decision, hook_id=ctx.hook.id, rule_id="r1", reason=reason, **extra
        )

    return handler


def boom(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
    """A handler with a bug."""
    raise RuntimeError("handler bug")


def dispatch(
    deps: RuntimeDeps,
    repo: GuardRepo,
    event: EventName = PRE,
    *,
    harness: Harness = Harness.CLAUDE_CODE,
    tool: str | None = "Bash",
    **fields: Any,
) -> WireOutput:
    """Run ``event`` (a canned ``tool`` call, plus payload ``fields``) through ``run_event``."""
    payload = repo.payload(event, tool=tool, **fields)
    return run_event(event, harness, payload, deps)


def body(wire: WireOutput) -> dict[str, Any]:
    """The rendered stdout object, ``{}`` when nothing was written."""
    parsed: dict[str, Any] = json.loads(wire.stdout) if wire.stdout else {}
    return parsed

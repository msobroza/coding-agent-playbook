"""local-audit-log: one structure-only line per tool call, prompt and session boundary (specs/prK-hook-pack.md §E.5).

Opt-in. Each event appends one line to ``<state>/audit-YYYY-MM.jsonl``
(outside the working tree, 0600, rotated at 5 MiB like the decision log)
through ``state.audit_log.append_activity``; :mod:`._activity_record` decides
what a line may hold (command structure, masked paths, prompt digests).

``ASYNC_SAFE = True``: the handler writes no output and decides nothing, so on
``post_tool_use`` it runs only in the one extra async ``PostToolUse`` dispatch
(``hook_runtime.routing``, OQ-19), and a ``Read`` costs no blocking interpreter
start. Its other events (``session_start``, ``user_prompt_submit``,
``post_tool_use_failure``, ``session_end``) ride their synchronous
registrations: OQ-19 allows async for ``PostToolUse`` only, and Claude's
``PostToolUse`` never fires for a failed call, whose exit status the failure
event carries.

``config``: ``chain`` adds the ``prev`` hash chain (corruption detection, not
tamper evidence, unless the org's shipper anchors the head), ``full_commands``
the redacted command text, ``retain_days`` (also ``[guardrails.audit]``) the
retention :func:`~coding_agent_playbook.hook_runtime.state.audit_log.prune_audit` applies at
session start, and ``pii`` (empty in the engine; an overlay lists detectors)
the PII category counts of a prompt. A write failure is an internal error:
``on_error: open``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers._activity_record import activity_record, fitted
from coding_agent_playbook.hook_runtime.handlers._pii_settings import (
    PII_CONFIG_KEY,
    PII_KEY,
    pii_settings,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.state.audit_log import append_activity, prune_audit

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = ["ASYNC_SAFE", "CONFIG_SCHEMA", "DEFAULT_RETAIN_DAYS", "activity_log"]

#: Writes no stdout and decides nothing: eligible for the async registration (OQ-19).
ASYNC_SAFE: Final = True
DEFAULT_RETAIN_DAYS: Final = 90
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "retain_days": ConfigKey("integer"),
    "chain": ConfigKey("boolean"),
    "full_commands": ConfigKey("boolean"),
    PII_KEY: PII_CONFIG_KEY,
}


#: Every event the hook may bind; ``post_tool_use`` is the async one.
_EVENTS: Final = (
    "session_start",
    "user_prompt_submit",
    "post_tool_use",
    "post_tool_use_failure",
    "session_end",
)


@register_hook_handler(
    "activity_log",
    events=_EVENTS,
    decisions=["none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="audit",
)
def activity_log(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Append ``ev``'s structure-only audit line; prune old month files at session start.

    Example: ``activity_log(post_bash_mysql, ctx)`` writes ``argv0 mysql`` and
    flag ``-p``, never the password, and returns ``None``.
    """
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    state = ctx.session.store.private_dir("")
    now = ctx.clock.time()
    if ev.name is EventName.SESSION_START:
        prune_audit(
            state,
            retain_days=config.integer("retain_days", DEFAULT_RETAIN_DAYS, minimum=1),
            now=now,
        )
    record = activity_record(
        ev,
        now=now,
        secret=ctx.cfg.secret_paths,
        platform=ctx.platform,
        full_commands=config.flag("full_commands", False),
        pii=pii_settings(ctx.config) if ev.prompt is not None else None,
    )
    append_activity(state, fitted(record), chain=config.flag("chain", False))
    return None

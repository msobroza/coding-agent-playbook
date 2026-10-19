"""command-convention-guard: a consumer's Bash convention rows; the engine ships none (specs/prK-hook-pack.md §E.4).

``pre_tool_use`` on shell calls, opt-in, a speed bump for convention (not
security). Rows come only from the consumer's ``[hooks.command-convention-guard]
rules``, a repo-local override or an overlay: ``{regex, decision, message}``
(``regex`` is the screened ``regex`` config kind; ``id`` is optional). Each
row's regex is searched in every segment as written, minus its ``NAME=value``
prefixes and the configured ``wrapper_prefixes`` (so ``proxy uv run mypy`` is
``uv run mypy``; runner wrappers such as ``uv run`` stay, since conventions are
usually about them):

- a ``deny`` row denies, its message carrying the corrected command;
- a ``warn`` row adds its message as context, once per session per row.

It never rewrites the command (L6): a user's own command-rewriting hook may
already rewrite input, and two rewriters on one call race. Without rows it returns
before reading the command, so it costs nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["CONFIG_SCHEMA", "ConventionRow", "command_convention_guard", "convention_rows"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"rules": ConfigKey("regex", "extend")}
_MESSAGE_CHARS: Final = 300
_DEFAULT_MESSAGE: Final = "This command breaks a convention of this repository."
_ASSIGNMENT: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_compiled: dict[str, re.Pattern[str] | None] = {}


@dataclass(frozen=True, slots=True)
class ConventionRow:
    """One compiled row: its id (``rules[<n>]`` when unnamed), regex, decision and message."""

    row_id: str
    pattern: re.Pattern[str]
    decision: Decision
    message: str


@register_hook_handler(
    "command_convention_guard",
    events=["pre_tool_use"],
    decisions=["deny", "context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def command_convention_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a command a ``deny`` row matches; warn once per session for a ``warn`` row.

    Example::

        >>> command_convention_guard(bash("uv run mypy"), ctx).reason  # doctest: +SKIP
        'Use uv run python -m mypy.'
    """
    rows = convention_rows(ctx.config.get("rules"))
    command = ev.tool.command if rows and ev.tool is not None else None
    if command is None:
        return None
    prefixes = [p.split() for p in ctx.cfg.shell.wrapper_prefixes if p.strip()]
    texts = [_written(segment, prefixes) for segment in command.segments if segment.raw_argv]
    matched = [row for row in rows if any(row.pattern.search(text) for text in texts)]
    denied = next((row for row in matched if row.decision is Decision.DENY), None)
    if denied is not None:
        return HandlerResult(
            decision=Decision.DENY,
            hook_id=ctx.hook.id,
            rule_id=denied.row_id,
            reason=denied.message,
        )
    warned = [row for row in matched if ctx.session.once(f"convention:{ctx.hook.id}:{row.row_id}")]
    if not warned:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT,
        hook_id=ctx.hook.id,
        rule_id=warned[0].row_id,
        context=tuple(row.message for row in warned),
    )


def convention_rows(rules: object) -> list[ConventionRow]:
    """The usable rows of ``config.rules``: a table with a compiling ``regex`` and a decision.

    A row with another decision, or a regex that does not compile, is left out
    (validate refuses both first: the decision by schema, the regex by
    ``screen_regex``).

    Example::

        >>> [r.row_id for r in convention_rows([{"regex": "^uv run mypy", "decision": "deny"}])]
        ['rules[0]']
    """
    rows: list[ConventionRow] = []
    for index, row in enumerate(rules if isinstance(rules, list | tuple) else ()):
        if not isinstance(row, dict):
            continue
        decision = {"deny": Decision.DENY, "warn": Decision.CONTEXT}.get(str(row.get("decision")))
        pattern = _pattern(row.get("regex"))
        if decision is None or pattern is None:
            continue
        row_id = row.get("id") if isinstance(row.get("id"), str) else f"rules[{index}]"
        rows.append(ConventionRow(str(row_id), pattern, decision, _message(row.get("message"))))
    return rows


def _written(segment: Segment, prefixes: Sequence[list[str]]) -> str:
    """``segment`` as written, without its env assignments and wrapper prefixes."""
    words = list(segment.raw_argv)
    while words and _ASSIGNMENT.match(words[0]):
        words.pop(0)
    longest_first = sorted(prefixes, key=len, reverse=True)
    while (found := next((p for p in longest_first if words[: len(p)] == p), None)) is not None:
        words = words[len(found) :]
    return " ".join(words)


def _pattern(source: Any) -> re.Pattern[str] | None:
    if not isinstance(source, str):
        return None
    if source not in _compiled:
        try:
            _compiled[source] = re.compile(source)
        except re.error:
            _compiled[source] = None
    return _compiled[source]


def _message(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return _DEFAULT_MESSAGE
    return clip(clean_text(value).strip(), _MESSAGE_CHARS)

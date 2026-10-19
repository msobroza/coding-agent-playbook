"""The advisory projection of a hook body (specs/prK-lifecycle-hooks.md §A.8, §C.4.1).

Every full-text guardrail target (Continue's ``30-guardrail-<id>.md``,
agent_harness's ``rules/30-guardrail-<id>.md``, a section of the
``playbook-guardrails`` skill) gets the same text: the rendered body plus **one**
enforcement line, so advice is never mistaken for enforcement (QC-10).

The line is static. It comes from the hook's *declared* ``supports`` crossed
with the §C.5.1 event reachability (:data:`HOOK_SUPPORT`, :data:`DEGRADED_EVENTS`),
never from the adapters a repo enables, so committed bytes do not vary with a
teammate's ``.local.toml``.

Always-loaded context gets one line per guardrail instead (D6,
specs/prS-skills-context.md 8.4.1): AGENTS.md's ``## Guardrails`` section, and
the Claude Code rules file for a hook Claude Code cannot run, hold
:func:`guardrails_section` over :func:`guardrail_line` of each hook's
:func:`guardrail_summary`. Stdlib-only, like the rest of ``hook_policy``.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.hook_schema import GUARDRAIL_SUMMARY_MAX_CHARS
from coding_agent_playbook.hook_policy.guardrails_skill import GUARDRAILS_SKILL_ID
from coding_agent_playbook.hook_policy.tables import DEGRADED_EVENTS, HOOK_SUPPORT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "ADAPTER_LABELS",
    "GUARDRAIL_SUMMARY_MAX_CHARS",
    "advisory_block",
    "advisory_text",
    "enforcement_line",
    "enforcement_targets",
    "guardrail_line",
    "guardrail_summary",
    "guardrails_section",
]

#: How the enforcement line names each hook-capable adapter.
ADAPTER_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {"claude_code": "Claude Code", "opencode": "OpenCode"}
)
_GUIDANCE: Final = "Everywhere else this is guidance: apply it yourself."
_NOT_ENFORCED: Final = "*Not enforced automatically; apply it yourself.*"

#: A code span, skipped so ``ruff check .`` ends no sentence, or a sentence end.
_SENTENCE_END: Final = re.compile(r"`[^`]*`|[.!?](?=\s|$)")
#: A Markdown (ATX) heading's opening ``#`` run: up to three spaces of indent, 1-6 ``#``.
_HEADING_PREFIX: Final = re.compile(r" {0,3}#{1,6}(?:\s+|$)")
#: The block quote and list item markers that open a line, nested ones included.
_BLOCK_MARKERS: Final = re.compile(r"^\s*(?:>\s*|[-*+]\s+|\d{1,9}[.)]\s+)+")
_ELLIPSIS: Final = "…"
_GUARDRAILS_PREFACE: Final = (
    "Lifecycle hooks enforce these on assistants that run them; on every other assistant, "
    f"follow them yourself. Skill `{GUARDRAILS_SKILL_ID}` has the full text of each one and "
    "where it is enforced."
)


def enforcement_targets(
    events: Iterable[str],
    supports: Iterable[str],
    *,
    support: Mapping[str, Mapping[str, frozenset[str]]] = HOOK_SUPPORT,
    degraded: Mapping[str, frozenset[str]] = DEGRADED_EVENTS,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(enforcing, checking)`` adapters, in :data:`HOOK_SUPPORT` order.

    An adapter in ``supports`` enforces when at least one declared event is
    natively reachable there and not degraded; it only *checks* when every
    reachable event is degraded (OpenCode's evidence-only Stop); it is in
    neither when no event is reachable. Unknown adapters and events are ignored.

    Example::

        >>> enforcement_targets(["stop"], ["claude_code", "opencode"])
        (('claude_code',), ('opencode',))
    """
    wanted = set(events)
    declared = set(supports)
    enforcing: list[str] = []
    checking: list[str] = []
    for adapter, row in support.items():
        reachable = wanted & set(row)
        if adapter not in declared or not reachable:
            continue
        weak = reachable <= degraded.get(adapter, frozenset())
        (checking if weak else enforcing).append(adapter)
    return tuple(enforcing), tuple(checking)


def enforcement_line(events: Iterable[str], supports: Iterable[str]) -> str:
    """The one italic line that says where a hook is enforced, checked, or neither.

    Example::

        >>> enforcement_line(["subagent_stop"], ["opencode"])
        '*Not enforced automatically; apply it yourself.*'
    """
    enforcing, checking = enforcement_targets(events, supports)
    parts: list[str] = []
    if enforcing:
        parts.append(f"Enforced by lifecycle hooks on: {_labels(enforcing)}")
    if checking:
        verb = "checked" if enforcing else "Checked"
        parts.append(f"{verb} (not blocked) on: {_labels(checking)}")
    if not parts:
        return _NOT_ENFORCED
    return f"*{'; '.join(parts)}. {_GUIDANCE}*"


def advisory_text(body: str, events: Iterable[str], supports: Iterable[str]) -> str:
    """The advisory rule's body: ``body`` (outer blank lines trimmed) plus its enforcement line.

    Example::

        >>> advisory_text("Ask first.\\n", ["pre_tool_use"], [])
        'Ask first.\\n\\n*Not enforced automatically; apply it yourself.*\\n'
    """
    prose = body.lstrip("\n").rstrip()
    return f"{prose}\n\n{enforcement_line(events, supports)}\n"


def advisory_block(name: str, text: str) -> str:
    """The ``hook_advisory`` markdown: a ``###`` heading over :func:`advisory_text` output.

    Example: ``advisory_block("Guard X", text)`` -> ``"### Guard X\\n\\n" + text``.
    """
    return f"### {name}\n\n{text}"


def _labels(adapters: Iterable[str]) -> str:
    return ", ".join(ADAPTER_LABELS.get(adapter, adapter) for adapter in adapters)


def guardrail_summary(summary: str, body: str) -> str:
    """The one-line guardrail text: ``summary``, else the body's first sentence, cut to 120.

    The fallback keeps a hook without an authored ``summary`` (an overlay or
    repo-local one) working unedited: its body's first sentence, its wrapped
    lines joined, cut at the last word boundary with ``…`` appended when it is
    longer than :data:`GUARDRAIL_SUMMARY_MAX_CHARS` (D6, P4-3). Headings are
    skipped and list or quote markers dropped, since the sentence becomes one
    list item of its own (:func:`_prose_line`).

    Example::

        >>> guardrail_summary("", "## Why\\n\\n- Ask first. Then act.")
        'Ask first.'
    """
    if summary:
        return summary
    return _cut_to_cap(_first_sentence(_prose_line(body)))


def _prose_line(body: str) -> str:
    """``body`` on one line, without heading lines and line-opening list or quote markers.

    Joined raw, ``## Why`` or ``- Do X.`` would lead the guardrail line with a
    marker. A body that is only headings keeps their text, so the line is never empty.
    """
    lines = [line for line in body.splitlines() if line.strip()]
    prose = [line for line in lines if not _HEADING_PREFIX.match(line)]
    kept = prose or [_HEADING_PREFIX.sub("", line, count=1) for line in lines]
    return " ".join(" ".join(_BLOCK_MARKERS.sub("", line, count=1) for line in kept).split())


def _first_sentence(text: str) -> str:
    """``text`` up to its first ``.``, ``!`` or ``?`` before a space or the end, else all of it."""
    for match in _SENTENCE_END.finditer(text):
        if not match.group().startswith("`"):
            return text[: match.end()]
    return text


def _cut_to_cap(sentence: str) -> str:
    """``sentence``, or its longest word-boundary prefix plus ``…`` within the cap.

    The prefix stops before an open code span; when that leaves no text (the
    sentence opens with an unclosed backtick), the cut is hard at the cap instead.
    """
    if len(sentence) <= GUARDRAIL_SUMMARY_MAX_CHARS:
        return sentence
    head = sentence[:GUARDRAIL_SUMMARY_MAX_CHARS]
    kept = head.rsplit(" ", 1)[0] if " " in head else head[:-1]
    if kept.count("`") % 2:  # an open code span would swallow the rest of the line
        kept = kept[: kept.rindex("`")]
    trimmed = kept.rstrip(" ,;:") or head[:-1].rstrip(" ,;:")
    return trimmed + _ELLIPSIS


def guardrail_line(hook_id: str, summary: str) -> str:
    """One AGENTS.md guardrail line (D6).

    Example: ``guardrail_line("x", "Ask first.")`` -> ``"- `x`: Ask first."``.
    """
    return f"- `{hook_id}`: {summary}"


def guardrails_section(lines: Iterable[tuple[str, str]]) -> str:
    """``## Guardrails``, the preface, then each ``(hook id, line)`` sorted by hook id.

    The preface says once what each line used to say on its own: hooks enforce
    these only where they run, and the skill holds the full text and where (QC-10).

    Example: ``guardrails_section([("x", guardrail_line("x", "Ask first."))])``.
    """
    ordered = sorted(lines, key=lambda pair: pair[0])
    listed = "\n".join(line for _, line in ordered)
    return f"## Guardrails\n\n{_GUARDRAILS_PREFACE}\n\n{listed}\n"

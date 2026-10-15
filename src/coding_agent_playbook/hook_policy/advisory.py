"""The advisory projection of a hook body (specs/prK-lifecycle-hooks.md §A.8, §C.4.1).

Every advisory target (AGENTS.md's Guardrails section, Continue's
``30-guardrail-<id>.md``, CLAUDE.md for hooks Claude Code cannot enforce) gets
the same text: the rendered body plus **one** enforcement line, so advice is
never mistaken for enforcement (QC-10).

The line is static. It comes from the hook's *declared* ``supports`` crossed
with the §C.5.1 event reachability (:data:`HOOK_SUPPORT`, :data:`DEGRADED_EVENTS`),
never from the adapters a repo enables, so committed bytes do not vary with a
teammate's ``.local.toml``. Stdlib-only, like the rest of ``hook_policy``.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_policy.tables import DEGRADED_EVENTS, HOOK_SUPPORT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "ADAPTER_LABELS",
    "advisory_block",
    "advisory_text",
    "enforcement_line",
    "enforcement_targets",
]

#: How the enforcement line names each hook-capable adapter.
ADAPTER_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {"claude_code": "Claude Code", "opencode": "OpenCode"}
)
_GUIDANCE: Final = "Everywhere else this is guidance: apply it yourself."
_NOT_ENFORCED: Final = "*Not enforced automatically; apply it yourself.*"


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

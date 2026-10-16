"""What both renderers share: field caps, default reasons, context items, JSON (§D.3.4, §D.3.5).

Renderers are the last line of defence for the output contract: every field
is cleaned and clipped to ``OutputCaps.FIELD_CHARS`` here even though
``combine`` already capped it, because a renderer may also be handed a
failure-policy result or a hand-built one (``simulate``, the watchdog).
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import OutputCaps, clean_text, clip
from coding_agent_playbook.hook_runtime.decision import Decision

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.decision import CombinedResult

#: Shown when a deny or ask arrives without a reason: the harness must say something.
DEFAULT_REASONS: Final[Mapping[Decision, str]] = MappingProxyType(
    {
        Decision.DENY: "Blocked by a playbook hook.",
        Decision.ASK: "A playbook hook asks you to confirm this action.",
    }
)


def field_text(text: str) -> str:
    """``text`` cleaned of control characters and clipped to one output field."""
    return clip(clean_text(text), OutputCaps.FIELD_CHARS)


def reason_text(combined: CombinedResult, decision: Decision) -> str:
    """The deny/ask reason to render, never empty."""
    return field_text(combined.reason.strip() or DEFAULT_REASONS[decision])


def context_items(combined: CombinedResult) -> tuple[str, ...]:
    """The advisory items to render for a CONTEXT decision, within one field's budget.

    A deny or ask the event cannot express falls to context; its reason lines
    are then the items, so the finding still reaches the model.
    """
    items = combined.context
    if not items and combined.decision in (Decision.DENY, Decision.ASK):
        items = tuple(line for line in combined.reason.splitlines() if line.strip())
    return _fit(tuple(field_text(item) for item in items), OutputCaps.FIELD_CHARS)


def dump(body: Mapping[str, object]) -> str:
    """One compact, ASCII-only JSON object and a newline: the whole stdout."""
    return json.dumps(body, ensure_ascii=True, separators=(",", ":")) + "\n"


def _fit(items: tuple[str, ...], budget: int) -> tuple[str, ...]:
    """The items that fit ``budget`` characters once joined with newlines; the last may be cut."""
    kept: list[str] = []
    used = 0
    for item in items:
        room = budget - used - (1 if kept else 0)
        if room <= 0:
            break
        kept.append(clip(item, room))
        used += len(kept[-1]) + (1 if len(kept) > 1 else 0)
    return tuple(kept)

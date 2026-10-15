"""What an overlay may not change when it overrides an earlier hook definition (H14).

Overlays may only add (specs/prK-lifecycle-hooks.md §A.6, lock L2): an overlay's
same-id definition replaces the earlier one, but must not swap a builtin
handler, disable a default-tier hook, drop an event, a tool class, ``deny`` or
``ask``, weaken ``on_error`` (``open`` < ``ask`` < ``deny``) or demote the tier.
Promoting to ``tier: default`` is allowed: it is how an overlay activates an
engine mechanism (K-11). It also may not clear ``mandatory`` (the §I invariant
"overlays only add").

Every check reads values as written and skips ones outside the vocabularies:
``classify_hook`` judges those, so these checks never raise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.hook_policy.tables import (
    HOOK_EVENTS,
    ON_ERROR_STRENGTH,
    TOOL_CLASS_NAMES,
)

if TYPE_CHECKING:
    from coding_agent_playbook.types import Hook, HookFrontmatter, HookHandler

#: The decisions an overlay may never drop: they are what makes a hook a guard.
_GUARD_DECISIONS = ("deny", "ask")


def bound_handler(frontmatter: HookFrontmatter, event: str) -> HookHandler | None:
    """The handler bound to ``event`` (``handlers[event]``, else ``handler``), or None.

    ``HookFrontmatter.handler_for`` raises on an unbound event (an H6 error);
    the merge must not, so it reads through this instead.

    Example: ``bound_handler(hook.frontmatter, "stop")``.
    """
    per_event = frontmatter.handlers.get(event)
    return per_event if per_event is not None else frontmatter.handler


def overlay_override_problems(earlier: Hook, later: Hook) -> list[str]:
    """Each way ``later`` (an overlay's definition) takes away from ``earlier``, as a phrase.

    Example::

        >>> overlay_override_problems(engine_hook, overlay_hook)  # doctest: +SKIP
        ["drops decision 'deny'"]
    """
    before, after = earlier.frontmatter, later.frontmatter
    return [
        *_swapped_builtins(before, after),
        *_disabled_default(before, after),
        *_dropped_events(before, after),
        *_dropped_tool_classes(before, after),
        *_dropped_decisions(before, after),
        *_weakened_on_error(before, after),
        *_demoted_tier(before, after),
        *_cleared_mandatory(earlier, later),
    ]


def _swapped_builtins(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    problems: list[str] = []
    for event in dict.fromkeys(before.events):
        old = bound_handler(before, event)
        if old is None or old.builtin is None or event not in after.events:
            continue  # unbound is H6; a dropped event is reported on its own
        new = bound_handler(after, event)
        if new is None or new.builtin != old.builtin:
            problems.append(
                f"replaces builtin {old.builtin!r} with {_handler_label(new)} on event {event!r}"
            )
    return problems


def _handler_label(handler: HookHandler | None) -> str:
    if handler is None:
        return "no handler"
    return "an external command" if handler.builtin is None else repr(handler.builtin)


def _disabled_default(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    if before.tier == "default" and before.enabled and not after.enabled:
        return ["sets enabled: false on a default-tier hook"]
    return []


def _dropped_events(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    return [f"drops event {e!r}" for e in dict.fromkeys(before.events) if e not in after.events]


def _dropped_tool_classes(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    problems: list[str] = []
    for event in dict.fromkeys(before.events):
        spec = HOOK_EVENTS.get(event)
        if spec is None or "tools" not in spec.matcher_fields or event not in after.events:
            continue
        lost = _tool_coverage(before, event) - _tool_coverage(after, event)
        problems.extend(
            f"drops tool class {tool!r} on event {event!r}"
            for tool in TOOL_CLASS_NAMES
            if tool in lost
        )
    return problems


def _tool_coverage(frontmatter: HookFrontmatter, event: str) -> frozenset[str]:
    """The tool classes ``event`` fires for: all of them without a tools or name filter."""
    matcher = frontmatter.matcher.get(event)
    if matcher is None or not (matcher.tools or matcher.tool_names):
        return frozenset(TOOL_CLASS_NAMES)
    return frozenset(matcher.tools)


def _dropped_decisions(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    return [
        f"drops decision {decision!r}"
        for decision in _GUARD_DECISIONS
        if decision in before.decisions and decision not in after.decisions
    ]


def _weakened_on_error(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    old, new = ON_ERROR_STRENGTH.get(before.on_error), ON_ERROR_STRENGTH.get(after.on_error)
    if old is None or new is None or new >= old:
        return []
    return [f"weakens on_error {before.on_error!r} to {after.on_error!r}"]


def _demoted_tier(before: HookFrontmatter, after: HookFrontmatter) -> list[str]:
    if before.tier == "default" and after.tier != "default":
        return [f"demotes tier 'default' to {after.tier!r}"]
    return []


def _cleared_mandatory(earlier: Hook, later: Hook) -> list[str]:
    if earlier.frontmatter.mandatory and not later.frontmatter.mandatory:
        return [f"clears mandatory set by overlay {earlier.source_package!r}"]
    return []

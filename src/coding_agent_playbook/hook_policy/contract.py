"""The per-hook trust contract: :func:`classify_hook` (specs/prK-lifecycle-hooks.md §B.5, lock L6).

``HookFrontmatter.from_mapping`` checks structure only (H1, H8); this module
judges the value domains, so ``playbook validate`` reports every problem of a
hook at once:

- H2 id pattern and directory name; H3 events; H4 matchers; H5 decisions;
- H6, H7, H13 handlers (:mod:`._contract_handlers`);
- H9 timeout; H10 ``on_error``; H11 ``supports``; H12 tier and ``mandatory``;
- H17 ``applies_if`` keys; H18 ``linked_rule``.

Three things are warnings, not errors (OQ-43): a tool class or event a listed
adapter cannot reach (degraded there), and a timeout above its event's deadline
cap (clamped). H14/H15 come from the layer merge, H19 from validate's body
check, and the checks across hooks and config from :mod:`.contract_set`.

Pure over one :class:`~coding_agent_playbook.types.Hook` and a
:class:`HookCheckContext`; stdlib-only at import (the detector, which pulls in
``packaging``, is imported only to judge an ``applies_if``).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from coding_agent_playbook._hook_schema import MATCHER_KEYS
from coding_agent_playbook._layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.hook_policy._contract_handlers import handler_findings
from coding_agent_playbook.hook_policy._findings import (
    Finding,
    HookIssue,
    did_you_mean,
    error,
    hook_location,
    seconds,
    warning,
)
from coding_agent_playbook.hook_policy.tables import (
    ENGINE_DEADLINE_CAP_MS,
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    HOOK_SUPPORT,
    MATCHER_VALUES,
    TOOL_CLASS_NAMES,
    EventSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.types import Hook, HookFrontmatter, HookMatcher

HOOK_ID_PATTERN: Final = "^[a-z0-9][a-z0-9-]{0,62}$"
#: The H9 bounds: every hook, and hooks on the tool and prompt events.
MAX_TIMEOUT_S: Final = 600
FAST_EVENT_TIMEOUT_S: Final = 30
FAST_EVENTS: Final = frozenset(
    {"pre_tool_use", "post_tool_use", "post_tool_use_failure", "user_prompt_submit"}
)

_HOOK_ID: Final = re.compile(HOOK_ID_PATTERN)
_DECISIONS: Final = ("deny", "ask", "context", "none")
_ON_ERRORS: Final = ("ask", "deny", "open")
_TIERS: Final = ("default", "opt-in", "overlay")


@dataclass(frozen=True)
class HookCheckContext:
    """What :func:`classify_hook` reads besides the hook itself.

    ``rule_ids`` is the merged rule set (H18); ``facts`` and ``repo_root`` judge
    ``applies_if`` (H17); ``definitions`` holds every layer's definition of each
    hook id, in layer order (H12). A hook is engine-sourced when its
    ``source_package`` equals ``engine_package`` exactly, so a bundled pack
    (``coding_agent_playbook.packs.*``) is an overlay.

    Example::

        >>> HookCheckContext().engine_package
        'coding_agent_playbook'
    """

    engine_package: str = ENGINE_PACKAGE
    rule_ids: frozenset[str] = frozenset()
    facts: Mapping[str, Any] = field(default_factory=dict)
    repo_root: Path = field(default_factory=Path)
    definitions: Mapping[str, tuple[Hook, ...]] = field(default_factory=dict)

    def is_engine(self, hook: Hook) -> bool:
        """True for a hook the engine package itself ships."""
        return hook.source_package == self.engine_package

    def is_overlay(self, hook: Hook) -> bool:
        """True for an overlay's hook (a bundled pack included): neither engine nor repo-local."""
        return not self.is_engine(hook) and hook.source_package != REPO_LOCAL_SOURCE


def classify_hook(hook: Hook, ctx: HookCheckContext) -> list[HookIssue]:
    """Every H2-H13/H17/H18 finding of ``hook``, located at its ``HOOK.md``; never raises.

    Example::

        >>> classify_hook(hook, HookCheckContext())  # doctest: +SKIP
        [HookIssue(severity='error', where='playbook/hooks/x/HOOK.md',
                   message='timeout 45 exceeds 30 s for tool and prompt events [...]')]
    """
    where = hook_location(hook)
    return [
        HookIssue(severity, where, message)
        for check in _CHECKS
        for severity, message in check(hook, ctx)
    ]


def _canonical_events(fm: HookFrontmatter) -> list[str]:
    """The declared events that are canonical, deduplicated (the others are H3's)."""
    return [event for event in dict.fromkeys(fm.events) if event in HOOK_EVENTS]


def _union(groups: Iterable[frozenset[str]]) -> frozenset[str]:
    return frozenset().union(*groups)


# --- H2, H3: id and events ----------------------------------------------------------


def _id_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    hook_id = hook.frontmatter.id
    directory = None if hook.hook_dir is None else hook.hook_dir.name
    if _HOOK_ID.fullmatch(hook_id) and directory in (None, hook_id):
        return
    suffix = "" if directory is None else f" and equal directory {directory!r}"
    yield error(f"id {hook_id!r} must match {HOOK_ID_PATTERN}{suffix}")


def _events_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    events = hook.frontmatter.events
    if not events:
        yield error("events: must list at least one canonical event")
    for event in dict.fromkeys(events):
        if events.count(event) > 1:
            yield error(f"events: {event!r} is listed more than once")
        if event not in HOOK_EVENTS:
            yield error(f"event {event!r} is not canonical; {_event_hint(event)}")


def _event_hint(value: str) -> str:
    """``did you mean 'pre_tool_use'?`` for a Claude name or near miss, else the allowed list."""
    squashed = re.sub(r"[^a-z]", "", value.lower())
    exact = [event for event in HOOK_EVENTS if event.replace("_", "") == squashed]
    close = exact or difflib.get_close_matches(value, list(HOOK_EVENTS), n=1)
    return f"did you mean {close[0]!r}?" if close else f"allowed: {', '.join(HOOK_EVENTS)}"


# --- H4: matchers -------------------------------------------------------------------


def _matcher_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    for event, entry in fm.matcher.items():
        label = f"matcher.{event}"
        if event not in fm.events:
            yield error(f"{label}: {event!r} is not in events {list(fm.events)!r}")
            continue
        spec = HOOK_EVENTS.get(event)
        if spec is not None:  # a non-canonical event is H3's
            yield from _matcher_entry(label, event, entry, spec, fm.supports)


def _matcher_entry(
    label: str, event: str, entry: HookMatcher, spec: EventSpec, supports: Sequence[str]
) -> Iterator[Finding]:
    for name in MATCHER_KEYS:
        values: list[str] = getattr(entry, name)
        if not values:
            continue
        if name not in spec.matcher_fields:
            allowed = ", ".join(sorted(spec.matcher_fields))
            hint = f"; allowed: {allowed}" if allowed else ""
            yield error(f"{label}.{name}: {name!r} is not valid for event {event!r}{hint}")
        else:
            check = _VALUE_CHECKS.get(name, _no_value_check)
            yield from check(f"{label}.{name}", values, supports)


#: Checks the values of one matcher field: ``(label, values, supports) -> findings``.
type _ValueCheck = Callable[[str, list[str], Sequence[str]], Iterator[Finding]]


def _no_value_check(label: str, values: list[str], supports: Sequence[str]) -> Iterator[Finding]:
    return iter(())


def _tool_class_check(label: str, values: list[str], supports: Sequence[str]) -> Iterator[Finding]:
    for tool in values:
        if tool == "other":
            yield error(f"{label}: tool class 'other' is runtime-only and cannot be authored")
        elif tool not in TOOL_CLASS_NAMES:
            allowed = ", ".join(TOOL_CLASS_NAMES)
            yield error(f"{label}: unknown tool class {tool!r}; allowed: {allowed}")
        else:
            for adapter in dict.fromkeys(supports):
                if TOOL_CLASS_NAMES[tool].get(adapter) == ():  # no such tool there (OpenCode mcp)
                    yield warning(
                        f"{label}: tool class {tool!r} is unsupported on adapter {adapter!r} "
                        "(degraded there)"
                    )


def _regex_check(label: str, values: list[str], supports: Sequence[str]) -> Iterator[Finding]:
    for pattern in values:
        try:
            re.compile(pattern)
        except re.error as exc:
            yield error(f"{label}: regex {pattern!r} does not compile: {exc}")


def _glob_check(label: str, values: list[str], supports: Sequence[str]) -> Iterator[Finding]:
    for glob in values:
        if not _is_relative_glob(glob):
            yield error(f"{label}: glob {glob!r} must be a non-empty relative pattern without '..'")


def _is_relative_glob(glob: str) -> bool:
    """Repo-relative: no root, no drive, no ``..`` segment (either separator)."""
    if not glob.strip() or glob.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", glob):
        return False
    return ".." not in re.split(r"[/\\]", glob)


def _vocabulary_check(field_name: str) -> _ValueCheck:
    """A check that every value of ``field_name`` is in its closed vocabulary (``sources``)."""
    allowed = MATCHER_VALUES[field_name]

    def check(label: str, values: list[str], supports: Sequence[str]) -> Iterator[Finding]:
        for value in values:
            if value not in allowed:
                shown = ", ".join(sorted(allowed))
                yield error(f"{label}: unknown value {value!r}; allowed: {shown}")

    return check


_VALUE_CHECKS: Final[Mapping[str, _ValueCheck]] = {
    "tools": _tool_class_check,
    "tool_names": _regex_check,
    "command": _regex_check,
    "paths": _glob_check,
    **{field_name: _vocabulary_check(field_name) for field_name in MATCHER_VALUES},
}


# --- H5, H9, H10: decisions, timeout, on_error --------------------------------------


def _decisions_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    if not fm.decisions:
        yield error(f"decisions: must list at least one of {', '.join(_DECISIONS)}")
    events = _canonical_events(fm)
    reachable = _union(HOOK_EVENTS[event].decisions for event in events)
    # The Literal-typed field holds whatever the author wrote, 'allow' included.
    for decision in dict.fromkeys(cast("list[str]", fm.decisions)):
        if decision == "allow":
            yield error(
                "decision 'allow' is never permitted: it would bypass the harness permission system"
            )
        elif decision not in _DECISIONS:
            yield error(f"decision {decision!r} is not one of {', '.join(_DECISIONS)}")
        elif events and decision not in reachable:
            yield error(
                f"decision {decision!r} is not valid for any declared event {events!r}; "
                f"they allow: {', '.join(sorted(reachable))}"
            )


def _timeout_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    shown = seconds(fm.timeout)
    if not 0 < fm.timeout <= MAX_TIMEOUT_S:
        yield error(f"timeout {shown} must be > 0 and <= {MAX_TIMEOUT_S} seconds")
        return
    events = _canonical_events(fm)
    fast = [event for event in events if event in FAST_EVENTS]
    if fast and fm.timeout > FAST_EVENT_TIMEOUT_S:
        yield error(
            f"timeout {shown} exceeds {FAST_EVENT_TIMEOUT_S} s for tool and prompt events {fast!r}"
        )
        return
    for event in events:
        cap = seconds(ENGINE_DEADLINE_CAP_MS[event] / 1000)
        if fm.timeout * 1000 > ENGINE_DEADLINE_CAP_MS[event]:
            yield warning(
                f"timeout {shown} exceeds the {cap} s deadline cap of event {event!r}; "
                f"it is clamped to {cap} s"
            )


def _on_error_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    if fm.on_error not in _ON_ERRORS:
        yield error(f"on_error {fm.on_error!r} is not one of {', '.join(_ON_ERRORS)}")
        return
    events = _canonical_events(fm)
    allowed = _union(HOOK_EVENTS[event].on_error_allowed for event in events)
    if events and fm.on_error not in allowed:
        yield error(
            f"on_error {fm.on_error!r} is not valid for any declared event {events!r}; "
            f"they allow: {', '.join(sorted(allowed))}"
        )
    if fm.on_error == "deny" and not ctx.is_overlay(hook):
        yield error("on_error 'deny' (fail-closed) is reserved for overlay hooks")


# --- H6, H7, H13: handlers ----------------------------------------------------------


def _handlers_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    yield from handler_findings(hook, engine_sourced=ctx.is_engine(hook))


# --- H11, H12: supports, tier, mandatory --------------------------------------------


def _supports_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    capable = ", ".join(sorted(HOOK_CAPABLE_ADAPTERS))
    if not fm.supports:
        yield error(f"supports: must list at least one of {capable}")
    events = _canonical_events(fm)
    for adapter in dict.fromkeys(fm.supports):
        reachable = HOOK_SUPPORT.get(adapter)
        if reachable is None:
            yield error(f"supports: adapter {adapter!r} cannot enforce hooks; allowed: {capable}")
        elif events and not any(event in reachable for event in events):
            yield error(f"no declared event of hook {fm.id!r} is reachable on adapter {adapter!r}")
        else:
            for event in events:
                if event not in reachable:
                    yield warning(
                        f"event {event!r} is not supported by adapter {adapter!r} (degraded)"
                    )


def _tier_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    fm = hook.frontmatter
    if fm.tier not in _TIERS:
        yield error(f"tier {fm.tier!r} is not one of {', '.join(_TIERS)}")
    elif fm.tier == "overlay" and not _may_carry_overlay_tier(hook, ctx):
        yield error(
            "tier 'overlay' is reserved for engine mechanisms; an overlay's own hook uses "
            "'default' or 'opt-in'"
        )
    if fm.mandatory and not ctx.is_overlay(hook):
        yield error("mandatory: true is reserved for overlay hooks")
    if fm.mandatory and not fm.enabled:
        yield error("mandatory: true requires enabled: true")


def _may_carry_overlay_tier(hook: Hook, ctx: HookCheckContext) -> bool:
    """An engine mechanism, or an overlay's same-id override of one (shipping its config)."""
    if ctx.is_engine(hook):
        return True
    definitions = ctx.definitions.get(hook.frontmatter.id, ())
    return ctx.is_overlay(hook) and any(ctx.is_engine(other) for other in definitions)


# --- H17, H18: applies_if, linked_rule ----------------------------------------------


def _applies_if_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    applies_if = hook.frontmatter.applies_if
    if not applies_if:
        return
    # Imported here: detector imports packaging, and hook_policy stays stdlib-only at import.
    from coding_agent_playbook.detector import evaluate_predicate

    facts = cast("Facts", dict(ctx.facts))
    # One key at a time: evaluate_predicate stops at the first false key, so an
    # unknown key after it would otherwise pass.
    for key, value in applies_if.items():
        try:
            evaluate_predicate({key: value}, facts, repo_root=ctx.repo_root)
        except ValueError as exc:
            yield error(f"applies_if: {exc}")


def _linked_rule_check(hook: Hook, ctx: HookCheckContext) -> Iterator[Finding]:
    rule_id = hook.frontmatter.linked_rule
    if rule_id is None or rule_id in ctx.rule_ids:
        return
    yield error(
        f"linked_rule {rule_id!r} not found in the merged rule set"
        f"{did_you_mean(rule_id, ctx.rule_ids)}"
    )


_CHECKS: Final[tuple[Callable[[Hook, HookCheckContext], Iterable[Finding]], ...]] = (
    _id_check,
    _events_check,
    _matcher_check,
    _decisions_check,
    _handlers_check,
    _timeout_check,
    _on_error_check,
    _supports_check,
    _tier_check,
    _applies_if_check,
    _linked_rule_check,
)

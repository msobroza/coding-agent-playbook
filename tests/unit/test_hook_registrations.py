"""The Claude Code registration planner (specs/prK-lifecycle-hooks.md §C.2.1, §C.2.2, §D.4).

``plan_registrations`` turns enabled hooks into one registration per harness
event (L3), with ``SessionStart`` always present once any registration exists;
``to_claude_group`` renders the closed key set; the matcher union is an exact
sorted list, ``*``, or an anchored regex; and the §D.4 formula keeps every
registration timeout at least a second above its event's watchdog deadline.
"""

from __future__ import annotations

import dataclasses
import math
import re
import sys
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookMatcher
from coding_agent_playbook.hook_registrations import (
    BOOTSTRAP_DEADLINE_MS,
    STOP_COORDINATOR_ID,
    DeclaredMember,
    HookRegistration,
    RegistrationTimeoutError,
    checked_registration_timeout_s,
    claude_command,
    claude_settings_projection,
    coordinator_budget_s,
    deadlines_ms,
    matcher_union,
    plan_registrations,
    registration_timeout_s,
    resolved_deadlines_ms,
    to_claude_group,
)
from coding_agent_playbook.hook_runtime.stop.stages import DEFAULT_BUDGET_S
from coding_agent_playbook.hooks.resolution.resolved import ResolvedHandler
from coding_agent_playbook.hooks.resolution.tables import (
    ENGINE_DEADLINE_CAP_MS,
    HOOK_EVENTS,
    HOOK_SUPPORT,
)
from tests.engine_modules import engine_module
from tests.hook_samples import hook_frontmatter, resolved_hook
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

_PROJECT_ROOT = "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
#: Claude reads a matcher made only of these characters as an exact list (§C.2.2).
_EXACT_LIST = re.compile(r"[A-Za-z0-9_\- ,|]+")


def _claude_matches(matcher: str | None, tool: str) -> bool:
    """A model of Claude's matcher semantics: omitted/``*``, exact list, else unanchored regex."""
    if matcher is None or matcher == "*":
        return True
    if _EXACT_LIST.fullmatch(matcher):
        return tool in {part.strip() for part in matcher.split("|")}
    return re.search(matcher, tool) is not None


def _matcher(**fields: list[str]) -> HookMatcher:
    return HookMatcher(**fields)


def _group(reg: HookRegistration) -> dict[str, Any]:
    return to_claude_group(reg)


def _handler(reg: HookRegistration) -> dict[str, Any]:
    (handler,) = to_claude_group(reg)["hooks"]
    return dict(handler)


def _by_event(regs: list[HookRegistration]) -> dict[str, HookRegistration]:
    return {reg.event: reg for reg in regs}


# --- the matcher union (§C.2.2) -----------------------------------------------------


def test_matcher_exact_sorted_list_edit_never_matches_notebookedit() -> None:
    union = matcher_union("pre_tool_use", [_matcher(tools=["write", "edit"])])

    assert union == "Edit|MultiEdit|Write"
    assert _claude_matches(union, "Edit")
    assert not _claude_matches(union, "NotebookEdit")


def test_matcher_union_sorts_and_dedupes_across_members() -> None:
    union = matcher_union(
        "post_tool_use",
        [_matcher(tools=["shell", "edit"]), _matcher(tools=["edit"], tool_names=["Agent"])],
    )

    assert union == "Agent|Bash|Edit|MultiEdit|PowerShell"


def test_matcher_star_when_member_matches_every_tool() -> None:
    union = matcher_union("pre_tool_use", [_matcher(tools=["shell"]), HookMatcher(paths=["x/**"])])

    assert union == "*"


def test_matcher_widens_to_star_when_no_known_tool_is_named() -> None:
    # The union is a pre-filter: an unknown class (validate rejects it, H4) never narrows it.
    assert matcher_union("pre_tool_use", [_matcher(tools=["teleport"])]) == "*"


def test_matcher_anchored_when_mcp_present() -> None:
    union = matcher_union("pre_tool_use", [_matcher(tools=["mcp", "edit"])])

    assert union == "^(?:Edit|MultiEdit|mcp__.*)$"
    assert _claude_matches(union, "mcp__github__create_issue")
    assert _claude_matches(union, "Edit")
    assert not _claude_matches(union, "NotebookEdit")
    assert not _claude_matches(union, "xmcp__y")


def test_matcher_anchored_for_a_regex_tool_name() -> None:
    union = matcher_union("pre_tool_use", [_matcher(tool_names=["mcp__github__.*"])])

    assert union == "^(?:mcp__github__.*)$"


def test_subagent_stop_union_anchored_on_colon_or_omitted() -> None:
    plain = matcher_union("subagent_stop", [HookMatcher(agent_types=["review", "Explore"])])
    scoped = matcher_union("subagent_stop", [HookMatcher(agent_types=["acme:audit", "review"])])
    open_member = matcher_union(
        "subagent_stop", [HookMatcher(agent_types=["review"]), HookMatcher()]
    )

    assert plain == "Explore|review"
    assert scoped == "^(?:acme:audit|review)$"
    assert _claude_matches(scoped, "acme:audit")
    assert not _claude_matches(scoped, "acme:auditor")
    assert open_member is None


def test_subagent_stop_anchored_union_escapes_regex_metacharacters() -> None:
    union = matcher_union("subagent_stop", [HookMatcher(agent_types=["acme:v1.2"])])

    assert union == r"^(?:acme:v1\.2)$"


def test_pre_compact_trigger_union_or_omitted() -> None:
    manual = matcher_union("pre_compact", [HookMatcher(triggers=["manual"])])
    both = matcher_union(
        "pre_compact", [HookMatcher(triggers=["manual"]), HookMatcher(triggers=["auto"])]
    )
    unfiltered = matcher_union("pre_compact", [HookMatcher(triggers=["auto"]), HookMatcher()])

    assert (manual, both, unfiltered) == ("manual", None, None)


@pytest.mark.parametrize("event", ["session_start", "user_prompt_submit", "stop", "session_end"])
def test_matcher_omitted_on_events_without_a_matcher(event: str) -> None:
    assert matcher_union(event, [HookMatcher(sources=["startup"])]) is None


# --- the plan: one registration per event (L3) --------------------------------------


def test_one_registration_per_event_fanout() -> None:
    hooks = [
        resolved_hook("guard-a", matcher={"pre_tool_use": {"tools": ["shell"]}}),
        resolved_hook("guard-b", matcher={"pre_tool_use": {"tools": ["edit"]}}),
    ]

    regs = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT))

    assert regs["pre_tool_use"].members == ("guard-a", "guard-b")
    assert matcher_union("pre_tool_use", regs["pre_tool_use"].matchers) == (
        "Bash|Edit|MultiEdit|PowerShell"
    )
    assert list(regs) == ["session_start", "pre_tool_use"]


def test_session_start_registered_whenever_any_registration() -> None:
    regs = plan_registrations([resolved_hook(events=("stop",))], "claude_code", HOOK_SUPPORT)

    assert [reg.event for reg in regs] == ["session_start", "stop"]
    assert regs[0].members == ()
    assert regs[0].artifact_id == "registration:session_start"


@pytest.mark.parametrize("consumer", ["prompt-write-scope-guard", "prompt-output-contract-on-stop"])
def test_active_prompt_consumer_registers_no_user_prompt_submit(consumer: str) -> None:
    """Finding #6: the consumers resolve the prompt from the transcript; no per-prompt process."""
    hooks = [resolved_hook(consumer, events=("stop",) if "stop" in consumer else ("pre_tool_use",))]
    deadlines = deadlines_ms(hooks)

    regs = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT, deadlines=deadlines))

    assert "user_prompt_submit" not in regs
    assert "user_prompt_submit" not in deadlines
    assert next(iter(regs)) == "session_start"


def test_user_prompt_submit_registered_for_a_member_that_binds_it() -> None:
    hooks = [resolved_hook("pii-guard", events=("user_prompt_submit",), supports=("claude_code",))]

    regs = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT))

    assert list(regs) == ["session_start", "user_prompt_submit"]
    assert regs["user_prompt_submit"].members == ("pii-guard",)


def test_user_prompt_submit_not_registered_without_a_consumer() -> None:
    hooks = [resolved_hook("guard-a")]

    regs = plan_registrations(hooks, "claude_code", HOOK_SUPPORT)

    assert [reg.event for reg in regs] == ["session_start", "pre_tool_use"]
    assert "user_prompt_submit" not in deadlines_ms(hooks)


def test_no_hooks_no_registrations() -> None:
    assert plan_registrations([], "claude_code", HOOK_SUPPORT) == []


def test_unreachable_event_not_registered_on_adapter() -> None:
    support = MappingProxyType({"tiny": MappingProxyType({"stop": frozenset({"deny"})})})
    hook = resolved_hook(events=("stop", "subagent_stop"), supports=("tiny",))

    regs = plan_registrations([hook], "tiny", support)

    assert [reg.event for reg in regs] == ["stop"]  # no session_start: unreachable on tiny


def test_hook_not_supporting_the_adapter_is_not_a_member() -> None:
    hooks = [resolved_hook("only-opencode", supports=("opencode",))]

    assert plan_registrations(hooks, "claude_code", HOOK_SUPPORT) == []


def test_registrations_follow_canonical_event_order() -> None:
    hook = resolved_hook(events=("session_end", "stop", "pre_tool_use"))

    regs = plan_registrations([hook], "claude_code", HOOK_SUPPORT)

    assert [reg.event for reg in regs] == ["session_start", "pre_tool_use", "stop", "session_end"]


# --- the §D.4 timeout formula -------------------------------------------------------


@pytest.mark.parametrize("event", list(HOOK_EVENTS))
def test_registration_timeout_covers_deadline(event: str) -> None:
    hooks = [resolved_hook(events=(event,), timeout=29.5), resolved_hook("b", events=(event,))]
    deadlines = deadlines_ms(hooks)

    (reg,) = [r for r in plan_registrations(hooks, "claude_code", HOOK_SUPPORT) if r.event == event]

    assert reg.deadline_ms == deadlines[event]
    assert reg.timeout_s == math.ceil(deadlines[event] / 1000) + 2
    assert reg.timeout_s * 1000 >= reg.deadline_ms + 1000
    assert _handler(reg)["timeout"] == reg.timeout_s


def test_deadline_caps_and_sum() -> None:
    hooks = [
        resolved_hook("a", events=("pre_tool_use", "post_tool_use"), timeout=2.5),
        resolved_hook("b", events=("pre_tool_use",), timeout=29.0),
        resolved_hook("c", events=("post_tool_use",), timeout=1.25),
    ]

    deadlines = deadlines_ms(hooks)

    assert deadlines["pre_tool_use"] == ENGINE_DEADLINE_CAP_MS["pre_tool_use"]  # 31.5 s capped
    assert deadlines["post_tool_use"] == 3750
    assert list(deadlines) == ["session_start", "pre_tool_use", "post_tool_use"]
    assert deadlines["session_start"] == BOOTSTRAP_DEADLINE_MS


def test_session_start_deadline_sums_its_members() -> None:
    deadlines = deadlines_ms([resolved_hook(events=("session_start",), timeout=3.5)])

    assert deadlines == {"session_start": 3500}


def test_no_hooks_no_deadlines() -> None:
    assert deadlines_ms([]) == {}


def test_stop_deadline_default_budget_3s() -> None:
    hooks = [resolved_hook(events=("stop", "subagent_stop"), timeout=20.0)]

    deadlines = deadlines_ms(hooks)

    assert DEFAULT_BUDGET_S == 3.0
    assert deadlines["stop"] == deadlines["subagent_stop"] == 3000
    regs = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT))
    assert regs["stop"].timeout_s == 5


def test_stop_deadline_adds_execution_stages_and_caps() -> None:
    hooks = [resolved_hook(events=("stop",))]

    assert deadlines_ms(hooks, stop_budget_s=4.0, execution_timeouts_s=(60.0, 30.5))["stop"] == (
        94_500
    )
    assert (
        deadlines_ms(hooks, execution_timeouts_s=(900.0,))["stop"]
        == (ENGINE_DEADLINE_CAP_MS["stop"])
    )


def test_coordinator_budget_read_from_its_merged_config() -> None:
    coordinator = resolved_hook(STOP_COORDINATOR_ID, events=("stop",), config={"budget_s": 7.5})
    other = resolved_hook("other", events=("stop",), config={"budget_s": 99})

    assert coordinator_budget_s([other, coordinator]) == 7.5
    assert coordinator_budget_s([other]) == DEFAULT_BUDGET_S


def test_resolved_deadlines_take_the_coordinator_budget_and_every_hook() -> None:
    coordinator = resolved_hook(STOP_COORDINATOR_ID, events=("stop",), config={"budget_s": 7.5})
    elsewhere = resolved_hook("guard-y", timeout=3.0, supports=("opencode",))
    hooks = [resolved_hook(timeout=2.0), elsewhere, coordinator]

    assert resolved_deadlines_ms(hooks) == {
        "session_start": BOOTSTRAP_DEADLINE_MS,
        "pre_tool_use": 5000,
        "stop": 7500,
    }


@pytest.mark.parametrize("bad", [True, "3", -1, 0])
def test_coordinator_budget_ignores_a_bad_value(bad: object) -> None:
    hook = resolved_hook(STOP_COORDINATOR_ID, events=("stop",), config={"budget_s": bad})

    assert coordinator_budget_s([hook]) == DEFAULT_BUDGET_S


def test_registration_timeout_formula() -> None:
    assert [registration_timeout_s(ms) for ms in (1, 1000, 1001, 30_000)] == [3, 3, 4, 32]


def test_checked_timeout_rejects_a_deadline_the_harness_would_cut() -> None:
    with pytest.raises(RegistrationTimeoutError) as caught:
        checked_registration_timeout_s("stop", 3000, formula=lambda _ms: 3)

    assert "stop" in str(caught.value)
    assert "3000" in str(caught.value)


def test_plan_uses_given_deadlines_over_every_hook() -> None:
    # The deadline is per event over every resolved hook (guard_config's), so an
    # OpenCode-only member still widens the Claude registration timeout.
    hooks = [
        resolved_hook("claude", timeout=2.0),
        resolved_hook("opencode-only", timeout=10.0, supports=("opencode",)),
    ]

    regs = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT))

    assert regs["pre_tool_use"].members == ("claude",)
    assert regs["pre_tool_use"].deadline_ms == 12_000
    assert regs["pre_tool_use"].timeout_s == 14


# --- the rendered group: closed key set, exact command (§C.2.1) ---------------------


def test_command_string_exact() -> None:
    assert claude_command("pre_tool_use") == (
        f'sh "{_PROJECT_ROOT}/.claude/hooks/playbook/launch.sh" '
        "dispatch pre_tool_use --harness claude_code"
    )
    assert claude_command("user_prompt_submit", strict=True) == (
        f'sh "{_PROJECT_ROOT}/.claude/hooks/playbook/launch.sh" --strict-launch '
        "dispatch user_prompt_submit --harness claude_code"
    )


def test_status_message_only_on_stop_and_subagent_stop() -> None:
    hook = resolved_hook(events=tuple(HOOK_EVENTS))

    regs = plan_registrations([hook], "claude_code", HOOK_SUPPORT)

    with_status = {reg.event for reg in regs if "statusMessage" in _handler(reg)}
    assert with_status == {"stop", "subagent_stop"}
    assert _handler(_by_event(regs)["stop"])["statusMessage"] == "playbook: verifying before stop"


def test_group_keys_closed_set_no_if_async_args_onfailure_by_default() -> None:
    hook = resolved_hook(events=tuple(HOOK_EVENTS), on_error="ask")

    for reg in plan_registrations([hook], "claude_code", HOOK_SUPPORT):
        group = _group(reg)
        assert set(group) <= {"matcher", "hooks"}
        assert len(group["hooks"]) == 1
        handler = _handler(reg)
        allowed = {"type", "command", "timeout"} | (
            {"statusMessage"} if reg.event in {"stop", "subagent_stop"} else set()
        )
        assert set(handler) == allowed, reg.event
        assert handler["type"] == "command"


def test_group_matcher_key_only_when_a_matcher_exists() -> None:
    hook = resolved_hook(
        events=("pre_tool_use", "stop"), matcher={"pre_tool_use": {"tools": ["read"]}}
    )

    regs = _by_event(plan_registrations([hook], "claude_code", HOOK_SUPPORT))

    assert _group(regs["pre_tool_use"])["matcher"] == "Read"
    assert "matcher" not in _group(regs["stop"])
    assert list(_group(regs["pre_tool_use"])) == ["matcher", "hooks"]


def test_strict_mode_renders_onfailure_and_strict_launch() -> None:
    hooks = [
        resolved_hook("pii", events=("user_prompt_submit",), on_error="deny"),
        resolved_hook("ledger", events=("user_prompt_submit",), on_error="open"),
    ]

    (reg,) = [
        r
        for r in plan_registrations(hooks, "claude_code", HOOK_SUPPORT)
        if r.event == "user_prompt_submit"
    ]
    handler = _handler(reg)

    assert reg.strict
    assert handler["onFailure"] == "block"
    assert "--strict-launch dispatch user_prompt_submit" in handler["command"]


def test_strict_mode_needs_a_deny_member() -> None:
    hook = resolved_hook(events=("user_prompt_submit",), on_error="open")

    regs = _by_event(plan_registrations([hook], "claude_code", HOOK_SUPPORT))

    assert not regs["user_prompt_submit"].strict
    assert "onFailure" not in _handler(regs["user_prompt_submit"])


def test_strict_mode_never_on_pre_tool_use_without_opt_in() -> None:
    hooks = [resolved_hook(on_error="deny")]

    default = _by_event(plan_registrations(hooks, "claude_code", HOOK_SUPPORT))
    opted = _by_event(
        plan_registrations(hooks, "claude_code", HOOK_SUPPORT, strict_pre_tool_use=True)
    )

    assert not default["pre_tool_use"].strict
    assert "--strict-launch" not in _handler(default["pre_tool_use"])["command"]
    assert opted["pre_tool_use"].strict
    assert _handler(opted["pre_tool_use"])["onFailure"] == "block"


def test_strict_mode_never_on_events_that_clamp_on_error_to_open() -> None:
    hook = resolved_hook(events=("stop", "post_tool_use"), on_error="deny")

    regs = plan_registrations([hook], "claude_code", HOOK_SUPPORT)

    assert not any(reg.strict for reg in regs)


# --- the debug projection used by `playbook render --format hook_claude_settings` ---


def test_declared_member_clamps_on_error_and_drops_unknown_names() -> None:
    fm = hook_frontmatter(
        events=["pre_tool_use", "stop", "PreToolUse"],
        on_error="ask",
        supports=["claude_code", "cursor"],
    )

    member = DeclaredMember.from_frontmatter(fm)

    assert member.events == ("pre_tool_use", "stop")
    assert member.on_error == {"pre_tool_use": "ask", "stop": "open"}
    assert member.supports == ("claude_code",)
    assert member.matcher["stop"] == HookMatcher()


def test_claude_settings_projection_shape() -> None:
    fm = hook_frontmatter(matcher={"pre_tool_use": {"tools": ["edit"]}}, timeout=2)

    projection = claude_settings_projection([DeclaredMember.from_frontmatter(fm)])

    assert list(projection["hooks"]) == ["SessionStart", "PreToolUse"]
    (group,) = projection["hooks"]["PreToolUse"]
    assert group["matcher"] == "Edit|MultiEdit"
    assert group["hooks"][0]["timeout"] == 4
    assert projection["hooks"]["SessionStart"][0]["hooks"][0]["command"].endswith(
        "dispatch session_start --harness claude_code"
    )


def test_claude_settings_projection_empty_when_claude_code_not_supported() -> None:
    fm = hook_frontmatter(supports=["opencode"])

    assert claude_settings_projection([DeclaredMember.from_frontmatter(fm)]) == {"hooks": {}}


def test_hook_registrations_imports_only_the_stdlib() -> None:
    # Sync-time but stdlib-only: no yaml/jinja2, and not the artifacts modules types.py
    # split into (artifacts/frontmatter.py imports yaml at module top).
    loaded = new_modules_after("import coding_agent_playbook.hook_registrations")

    foreign = [
        name
        for name in loaded
        if not name.startswith("coding_agent_playbook")
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    for artifact in ("frontmatter", "rule", "prompt", "skill", "hook"):
        assert engine_module(f"coding_agent_playbook.artifacts.{artifact}") not in loaded
    assert engine_module("coding_agent_playbook.renderer") not in loaded


# --- handler routes: the decision sink and OQ-19's async registration ----------------

_EVERY_EVENT = tuple(HOOK_EVENTS)
_BOTH = ("claude_code", "opencode")


def _bound(
    hook_id: str,
    builtin: str,
    *,
    events: tuple[str, ...],
    decisions: tuple[str, ...] = ("none",),
    timeout: float = 1.0,
) -> ResolvedHook:
    """A hook binding ``builtin`` on every event (as the audit HOOK.md files do)."""
    hook = resolved_hook(hook_id, events=events, timeout=timeout, on_error="open", supports=_BOTH)
    handlers = {event: ResolvedHandler("builtin", name=builtin) for event in events}
    return dataclasses.replace(hook, decisions=decisions, handlers=handlers)


def _sink() -> ResolvedHook:
    return _bound("guard-decision-log", "decision_log", events=_EVERY_EVENT, timeout=5.0)


def _audit(decisions: tuple[str, ...] = ("none",), builtin: str = "activity_log") -> ResolvedHook:
    events = ("session_start", "post_tool_use", "post_tool_use_failure")
    return _bound("local-audit-log", builtin, events=events, decisions=decisions, timeout=2.0)


def test_sink_hook_has_no_registration_and_no_deadline_share() -> None:
    guard = resolved_hook("guard-x", supports=_BOTH)

    for adapter in ("claude_code", "opencode"):
        with_sink = plan_registrations([guard, _sink()], adapter, HOOK_SUPPORT)
        assert with_sink == plan_registrations([guard], adapter, HOOK_SUPPORT)
        assert plan_registrations([_sink()], adapter, HOOK_SUPPORT) == []
    assert deadlines_ms([guard, _sink()]) == deadlines_ms([guard])
    assert deadlines_ms([_sink()]) == {}
    assert resolved_deadlines_ms([_sink()]) == {}


def test_async_group_only_for_none_only_async_safe_hook() -> None:
    regs = plan_registrations([_audit()], "claude_code", HOOK_SUPPORT)
    with_context = plan_registrations([_audit(("context", "none"))], "claude_code", HOOK_SUPPORT)
    other_builtin = plan_registrations([_audit(builtin="guard_x")], "claude_code", HOOK_SUPPORT)

    assert [(r.event, r.asynchronous) for r in regs] == [
        ("session_start", False),
        ("post_tool_use", True),
        ("post_tool_use_failure", False),
    ]
    assert regs[1].members == ("local-audit-log",)
    assert regs[1].artifact_id == "registration:post_tool_use:async"
    for sync_only in (with_context, other_builtin):
        assert not any(r.asynchronous for r in sync_only)
        assert _by_event(sync_only)["post_tool_use"].members == ("local-audit-log",)


def test_async_member_leaves_the_sync_post_tool_use_registration_unchanged() -> None:
    lint = resolved_hook("lint-q", events=("post_tool_use",), timeout=3.0, supports=_BOTH)

    alone = _by_event(plan_registrations([lint], "claude_code", HOOK_SUPPORT))
    regs = plan_registrations([lint, _audit()], "claude_code", HOOK_SUPPORT)
    sync = [r for r in regs if r.event == "post_tool_use" and not r.asynchronous]
    background = [r for r in regs if r.asynchronous]

    assert sync == [alone["post_tool_use"]]
    assert to_claude_group(sync[0]) == to_claude_group(alone["post_tool_use"])
    assert deadlines_ms([lint, _audit()])["post_tool_use"] == deadlines_ms([lint])["post_tool_use"]
    (extra,) = background
    assert regs.index(extra) == regs.index(sync[0]) + 1  # canonical position, after the sync one
    assert extra.deadline_ms == sync[0].deadline_ms


def test_async_group_renders_the_async_key_and_flag() -> None:
    (extra,) = [r for r in plan_registrations([_audit()], "claude_code") if r.asynchronous]

    group = to_claude_group(extra)

    assert extra.deadline_ms == ENGINE_DEADLINE_CAP_MS["post_tool_use"]  # no sync member
    assert group == {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": claude_command("post_tool_use", asynchronous=True),
                "timeout": registration_timeout_s(extra.deadline_ms),
                "async": True,
            }
        ],
    }
    assert group["hooks"][0]["command"].endswith(
        "dispatch post_tool_use --harness claude_code --async"
    )
    assert "onFailure" not in group["hooks"][0]


def test_declared_sink_projects_to_nothing() -> None:
    fm = hook_frontmatter(
        id="guard-decision-log",
        events=list(_EVERY_EVENT),
        handler={"builtin": "decision_log"},
        decisions=["none"],
        on_error="open",
    )

    assert claude_settings_projection([DeclaredMember.from_frontmatter(fm)]) == {"hooks": {}}

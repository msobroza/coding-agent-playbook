"""The OpenCode V1 shim's ``REG`` (specs/prK-lifecycle-hooks.md §C.3.2 "REG construction", §D.4).

``to_opencode_reg`` turns a registration plan into the one JSON object the shim
template embeds: a key per OpenCode-reachable event with a member (never
``pre_compact``), ``session_start`` whenever any key exists, ``tools`` as the
sorted V1 names of the members' tool classes and ``tool_names`` (``"*"`` for an
unfiltered member), and ``timeout_ms`` from the deadlines ``guard_config.json``
gets over every enabled hook. Every string in it is closed vocabulary.
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookMatcher
from coding_agent_playbook.hook_registrations import (
    OPENCODE_REG_EVENTS,
    OPENCODE_V1_TOOLS,
    STOP_COORDINATOR_ID,
    HookRegistration,
    RegistrationTimeoutError,
    opencode_reg_json,
    plan_opencode_reg,
    plan_registrations,
    resolved_deadlines_ms,
    to_opencode_reg,
)
from coding_agent_playbook.hook_runtime.harness.opencode import NATIVE_TOOL_NAMES
from coding_agent_playbook.hooks.resolution.tables import (
    HOOK_EVENTS,
    HOOK_SUPPORT,
    TOOL_CLASS_NAMES,
)
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

_OPENCODE = ("opencode",)
_BOTH = ("claude_code", "opencode")


def _on_opencode(hook_id: str = "guard-x", **kwargs: Any) -> ResolvedHook:
    return resolved_hook(hook_id, supports=_OPENCODE, **kwargs)


def _tools_for(event: str, **matcher: list[str]) -> object:
    reg = plan_opencode_reg([_on_opencode(events=(event,), matcher={event: matcher})])
    return reg[event]["tools"]


def _reg(event: str, *matchers: HookMatcher, deadline_ms: int = 2_000) -> HookRegistration:
    return HookRegistration(
        event=event,
        members=("guard-x",),
        deadline_ms=deadline_ms,
        timeout_s=4,
        matchers=matchers,
    )


def _strings(value: object) -> Iterator[str]:
    """Every string in a JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# --- tools: tool classes and tool_names over the closed V1 table ---------------------


@pytest.mark.parametrize(
    ("tool_class", "expected"),
    [
        ("shell", ["bash"]),
        ("edit", ["apply_patch", "edit"]),
        ("write", ["apply_patch", "write"]),
        ("read", ["read"]),
        ("search", ["glob", "grep"]),
        ("web", ["webfetch", "websearch"]),
        ("subagent", ["task"]),
        ("notebook_edit", []),
        ("mcp", []),
    ],
)
def test_to_opencode_reg_maps_tool_classes_to_v1_names(
    tool_class: str, expected: list[str]
) -> None:
    assert _tools_for("pre_tool_use", tools=[tool_class]) == expected


def test_to_opencode_reg_unions_and_sorts_across_members() -> None:
    hooks = [
        _on_opencode(hook_id, events=("post_tool_use",), matcher={"post_tool_use": {"tools": [c]}})
        for hook_id, c in (("a", "write"), ("b", "edit"), ("c", "shell"))
    ]

    assert plan_opencode_reg(hooks)["post_tool_use"]["tools"] == [
        "apply_patch",
        "bash",
        "edit",
        "write",
    ]


def test_to_opencode_reg_star_when_member_matches_every_tool() -> None:
    narrow = _on_opencode("narrow", matcher={"pre_tool_use": {"tools": ["shell"]}})
    paths_only = _on_opencode("paths-only", matcher={"pre_tool_use": {"paths": ["src/**"]}})

    assert plan_opencode_reg([narrow, paths_only])["pre_tool_use"]["tools"] == "*"
    assert plan_opencode_reg([_on_opencode()])["pre_tool_use"]["tools"] == "*"


def test_to_opencode_reg_star_when_a_tool_registration_has_no_matcher() -> None:
    # A hand-built registration without matchers filters nothing, like Claude's omitted matcher.
    assert to_opencode_reg([_reg("pre_tool_use")])["pre_tool_use"]["tools"] == "*"


def test_to_opencode_reg_drops_notebook_edit_and_mcp_classes() -> None:
    assert _tools_for("pre_tool_use", tools=["notebook_edit", "mcp", "shell"]) == ["bash"]
    # The key stays: the event is registered, it just selects no OpenCode tool.
    assert _tools_for("post_tool_use", tools=["mcp"]) == []


def test_to_opencode_reg_unknown_tool_class_never_narrows_the_prefilter() -> None:
    # validate rejects an unknown class (H4); were one to reach here, every tool is forwarded.
    assert _tools_for("pre_tool_use", tools=["teleport", "shell"]) == "*"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("Agent", ["task"]),
        ("Task", ["task"]),
        ("task", ["task"]),
        ("Bash", ["bash"]),
        ("Web.*", ["webfetch", "websearch"]),
        ("apply_patch", ["apply_patch"]),
        ("Edit", ["edit"]),
        ("Skill|TodoWrite", ["skill", "todowrite"]),
        ("mcp__github__.*", []),
        ("mcp__.*", []),
        ("(unclosed", []),
    ],
)
def test_to_opencode_reg_tool_names_select_from_closed_v1_table(
    pattern: str, expected: list[str]
) -> None:
    assert _tools_for("pre_tool_use", tool_names=[pattern]) == expected


def test_to_opencode_reg_tool_names_fullmatch_not_search() -> None:
    # The dispatcher fullmatches tool_names (hook_runtime._selection), so "Edit" is not "edit*".
    assert _tools_for("pre_tool_use", tool_names=["Edi"]) == []


def test_to_opencode_reg_unions_tool_classes_and_tool_names() -> None:
    assert _tools_for("pre_tool_use", tools=["read"], tool_names=["Agent"]) == ["read", "task"]


def test_closed_v1_vocabulary_covers_every_name_the_shim_can_forward() -> None:
    # The tool-class column (apply_patch included) plus the shim's renamed tools, nothing else.
    column = {name for row in TOOL_CLASS_NAMES.values() for name in row["opencode"]}

    assert column | set(NATIVE_TOOL_NAMES.values()) == OPENCODE_V1_TOOLS


# --- events -------------------------------------------------------------------------------


def test_opencode_reg_events_match_hook_support() -> None:
    assert set(OPENCODE_REG_EVENTS) == set(HOOK_SUPPORT["opencode"])
    assert "pre_compact" not in OPENCODE_REG_EVENTS
    assert list(OPENCODE_REG_EVENTS) == [e for e in HOOK_EVENTS if e in OPENCODE_REG_EVENTS]


@pytest.mark.parametrize(
    "event",
    ["pre_compact", "subagent_stop", "user_prompt_submit", "post_tool_use_failure", "session_end"],
)
def test_to_opencode_reg_never_emits_pre_compact_or_unreachable_events(event: str) -> None:
    # Even when handed another harness's plan, an event the shim cannot reach is dropped.
    every_event = resolved_hook(events=tuple(HOOK_EVENTS), supports=_BOTH)
    claude_plan = plan_registrations([every_event], "claude_code")

    assert event not in to_opencode_reg(claude_plan)
    assert to_opencode_reg([_reg(event)]) == {}
    assert plan_opencode_reg([_on_opencode(events=(event,))]) == {}


def test_to_opencode_reg_keys_follow_canonical_order() -> None:
    hook = _on_opencode(events=("stop", "post_tool_use", "pre_tool_use"))

    assert list(plan_opencode_reg([hook])) == [
        "session_start",
        "pre_tool_use",
        "post_tool_use",
        "stop",
    ]


def test_to_opencode_reg_adds_session_start_whenever_any_key() -> None:
    planned = plan_opencode_reg([_on_opencode(events=("stop",))])
    hand_built = to_opencode_reg([_reg("stop")])

    assert planned == {"session_start": {"timeout_ms": 4000}, "stop": {"timeout_ms": 5000}}
    # No bootstrap registration given: the bootstrap deadline (2 s) sets its timeout.
    assert hand_built["session_start"] == {"timeout_ms": 4000}


def test_to_opencode_reg_non_tool_events_carry_no_tools_key() -> None:
    hook = _on_opencode(events=("session_start", "stop"))

    assert all(set(entry) == {"timeout_ms"} for entry in plan_opencode_reg([hook]).values())


def test_to_opencode_reg_empty_when_no_member_supports_opencode() -> None:
    claude_only = resolved_hook(events=("pre_tool_use", "stop"), supports=("claude_code",))

    assert plan_opencode_reg([claude_only]) == {}
    assert plan_opencode_reg([]) == {}
    assert to_opencode_reg([]) == {}


def test_to_opencode_reg_memberless_registrations_alone_give_nothing() -> None:
    bootstrap = HookRegistration(event="session_start", members=(), deadline_ms=2_000, timeout_s=4)
    idle = HookRegistration(event="stop", members=(), deadline_ms=3_000, timeout_s=5)

    assert to_opencode_reg([bootstrap, idle]) == {}


# --- timeouts (§D.4) ------------------------------------------------------------------------


def test_to_opencode_reg_timeout_covers_guard_config_deadline() -> None:
    hooks = [
        resolved_hook("claude-guard", timeout=20.0),
        _on_opencode("opencode-guard", timeout=2.0),
        resolved_hook("briefing", events=("session_start",), timeout=5.0),
        resolved_hook(STOP_COORDINATOR_ID, events=("stop",), config={"budget_s": 7.5}),
        _on_opencode("stop-sweep", events=("stop",), timeout=1.0),
    ]
    deadlines = resolved_deadlines_ms(hooks)

    reg = plan_opencode_reg(hooks)

    assert set(reg) == {"session_start", "pre_tool_use", "stop"}
    for event, entry in reg.items():
        assert entry["timeout_ms"] >= deadlines[event] + 1000, event
    # Deadlines sum every enabled hook, not only the OpenCode members: 22 s, 5 s, 7.5 s.
    assert reg["pre_tool_use"]["timeout_ms"] == 24_000
    assert reg["session_start"]["timeout_ms"] == 7_000
    assert reg["stop"]["timeout_ms"] == 10_000


def test_to_opencode_reg_timeout_is_the_registration_timeout_in_ms() -> None:
    regs = plan_registrations([_on_opencode(timeout=29.5)], "opencode")

    reg = to_opencode_reg(regs)

    assert {e: entry["timeout_ms"] for e, entry in reg.items()} == {
        r.event: r.timeout_s * 1000 for r in regs
    }


def test_to_opencode_reg_rejects_a_timeout_that_would_cut_the_watchdog() -> None:
    too_short = HookRegistration(event="stop", members=("x",), deadline_ms=9_000, timeout_s=9)

    with pytest.raises(RegistrationTimeoutError, match="stop"):
        to_opencode_reg([too_short])


# --- serialization: deterministic, closed vocabulary ----------------------------------------


def _default_pack() -> list[ResolvedHook]:
    tool_events = ("pre_tool_use", "post_tool_use")
    return [
        resolved_hook(
            "guard-generated-outputs",
            matcher={"pre_tool_use": {"tools": ["edit", "write", "notebook_edit", "shell"]}},
            supports=_BOTH,
        ),
        resolved_hook(
            "secrets-guard",
            events=tool_events,
            matcher={e: {"tools": ["read", "search"], "paths": ["**/.env"]} for e in tool_events},
            supports=_BOTH,
            timeout=3.0,
        ),
        resolved_hook(
            "agent-watch",
            events=("pre_tool_use",),
            matcher={"pre_tool_use": {"tool_names": ["Agent", "mcp__github__.*"]}},
            supports=_BOTH,
        ),
        resolved_hook("stop-sweep", events=("stop",), supports=_BOTH),
        resolved_hook("briefing", events=("session_start",), supports=_BOTH, timeout=4.0),
    ]


def test_to_opencode_reg_json_is_deterministic() -> None:
    hooks = _default_pack()
    expected = opencode_reg_json(plan_opencode_reg(hooks))
    shuffler = random.Random(20261015)

    for _ in range(10):
        shuffled = hooks[:]
        shuffler.shuffle(shuffled)
        assert opencode_reg_json(plan_opencode_reg(shuffled)) == expected
    assert expected == json.dumps(
        json.loads(expected), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def test_opencode_reg_json_is_compact_and_key_sorted() -> None:
    reg = to_opencode_reg([_reg("stop"), _reg("pre_tool_use", HookMatcher(tools=["write"]))])

    assert opencode_reg_json(reg) == (
        '{"pre_tool_use":{"timeout_ms":4000,"tools":["apply_patch","write"]},'
        '"session_start":{"timeout_ms":4000},"stop":{"timeout_ms":4000}}'
    )


def test_to_opencode_reg_contains_only_closed_vocabulary() -> None:
    hooks = [
        *_default_pack(),
        _on_opencode(
            "evil</script>`${x}`",
            matcher={"pre_tool_use": {"tool_names": ["Bash", "*/;alert(1)//"], "paths": ["*/x"]}},
        ),
    ]
    vocabulary = {*OPENCODE_REG_EVENTS, *OPENCODE_V1_TOOLS, "*", "timeout_ms", "tools"}

    reg = plan_opencode_reg(hooks)
    dumped = opencode_reg_json(reg)

    assert set(_strings(reg)) <= vocabulary
    for authored in ("guard-generated-outputs", "evil", "alert", "mcp__github__", "**/.env", "*/x"):
        assert authored not in dumped

"""The dispatch pipeline's failure policy and selection, in-process (specs/prK-lifecycle-hooks.md §D.3.2, §D.4).

Every test runs the real ``run_event`` against a synced fixture repository with
a real state store, handlers injected through ``FakeHandlerResolver`` and every
process behind ``FakeProc`` (fixtures in ``conftest.py``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.dispatch.registry import (
    HANDLER_ATTR,
    HandlerDeclaration,
    Untrusted,
)
from coding_agent_playbook.hook_runtime.harness.wire import DENY_EXIT
from tests.hook_runtime.dispatch_kit import POST, body, boom, dispatch, verdict
from tests.hook_runtime.guard_repo import hook_record

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext, HandlerFn
    from tests.hook_runtime.fakes import FakeHandlerResolver
    from tests.hook_runtime.guard_repo import GuardRepo


# --- the failure classes ---------------------------------------------------------------


def test_raising_guard_asks_attended_and_denies_unattended(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a", on_error="ask"))
    resolver.handlers["guard-a"] = boom

    attended = dispatch(make_deps(), repo)
    unattended = dispatch(make_deps(CI="true"), repo)

    specific = body(attended)["hookSpecificOutput"]
    assert specific["permissionDecision"] == "ask"
    assert "Playbook guard guard-a failed internally" in specific["permissionDecisionReason"]
    assert attended.exit_code == 0
    assert unattended.exit_code == DENY_EXIT
    assert unattended.stderr.startswith("Needs user confirmation; unattended run, so denied: ")
    assert [line["decision"] for line in repo.decisions()] == ["degraded", "degraded"]


def test_strict_overlay_guard_denies_on_failure(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-s", on_error="deny", source_package="acme_rules"))
    resolver.handlers["guard-s"] = boom

    assert dispatch(make_deps(), repo).exit_code == DENY_EXIT


def _declaring(reason: str) -> HandlerFn:
    """:func:`boom`, carrying a declaration whose ``failure_reason`` is ``reason``."""

    def handler(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
        return boom(ev, ctx)

    declaration = HandlerDeclaration(
        name="guard_s",
        module=__name__,
        events=frozenset({EventName.USER_PROMPT_SUBMIT}),
        decisions=frozenset({Decision.DENY}),
        config_schema={},
        failure_reason=reason,
        fn=handler,
    )
    setattr(handler, HANDLER_ATTR, declaration)
    return handler


def test_declared_failure_reason_replaces_the_generic_one(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    """pii-prompt-guard's ``FAILURE_REASON``: a strict prompt guard blocks with its own text."""
    record = hook_record(
        "guard-s",
        events=["user_prompt_submit"],
        decisions=["deny", "none"],
        on_error="deny",
        source_package="acme_rules",
    )
    repo.install(record)
    resolver.handlers["guard-s"] = _declaring("PII guard error; resubmit or use the override")

    wire = dispatch(make_deps(), repo, EventName.USER_PROMPT_SUBMIT, tool=None, prompt="hi")

    assert body(wire) == {
        "decision": "block",
        "reason": "PII guard error; resubmit or use the override",
    }
    assert wire.exit_code == 0
    assert [line["decision"] for line in repo.decisions()] == ["degraded"]


def test_raising_quality_hook_is_none_plus_exactly_one_note_per_session(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("lint-q", events=["post_tool_use"], on_error="open"))
    resolver.handlers["lint-q"] = boom

    first = dispatch(make_deps(), repo, POST, tool="Edit")
    second = dispatch(make_deps(), repo, POST, tool="Edit")

    assert body(first) == {
        "systemMessage": "lint-q skipped: internal error — run playbook-hook doctor"
    }
    assert second.stdout == ""
    assert first.exit_code == second.exit_code == 0


def test_config_fault_asks_once_per_session_then_none(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    # No guard_config.json at all: sync never ran in this worktree.
    first, second, third = (dispatch(make_deps(), repo) for _ in range(3))

    assert body(first)["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "guard configuration is missing or changed" in first.stdout
    assert "permissionDecision" not in second.stdout
    assert "degraded this session" in body(second)["systemMessage"]
    assert third.stdout == ""
    assert [line["rule_id"] for line in repo.decisions()] == [
        "config_fault:missing",
        "config_fault:missing",
    ]


def test_config_fault_on_a_quiet_event_is_one_note(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a"))
    repo.write_lock("0" * 64)  # guard_config.json changed since sync

    first = dispatch(make_deps(), repo, EventName.STOP, tool=None)
    second = dispatch(make_deps(), repo, EventName.STOP, tool=None)

    assert "digest_mismatch" in body(first)["systemMessage"]
    assert second.stdout == ""


def test_undeclared_decision_is_contract_violation(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-c", decisions=["context", "none"]))
    resolver.handlers["guard-c"] = verdict(Decision.DENY, "not allowed to deny")

    wire = dispatch(make_deps(), repo)

    assert body(wire)["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "not allowed to deny" not in wire.stdout
    assert [line["decision"] for line in repo.decisions()] == ["contract_violation"]


def test_a_non_result_return_value_is_a_contract_violation(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-c"))
    resolver.handlers["guard-c"] = lambda ev, ctx: "deny"  # type: ignore[assignment,return-value]

    dispatch(make_deps(), repo)

    assert [line["decision"] for line in repo.decisions()] == ["contract_violation"]


def test_unresolvable_handler_is_an_internal_error(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-x"))  # nothing scripted: resolution fails

    wire = dispatch(make_deps(), repo)

    assert "Playbook guard guard-x failed internally" in wire.stdout


def test_untrusted_handler_is_skipped_with_one_note_per_session(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("ext-a"))
    resolver.handlers["ext-a"] = Untrusted("no user approval")

    first = dispatch(make_deps(), repo)
    second = dispatch(make_deps(), repo)

    assert "ext-a skipped: not trusted on this machine (no user approval)" in first.stdout
    assert first.exit_code == 0
    assert second.stdout == ""
    assert [line["decision"] for line in repo.decisions()] == ["untrusted", "untrusted"]


# --- selection and ordering ------------------------------------------------------------


def test_first_guard_deny_short_circuits_remaining_handlers(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a", priority=10), hook_record("guard-b", priority=20))
    resolver.handlers["guard-a"] = verdict(Decision.DENY, "rm -rf is blocked")
    resolver.handlers["guard-b"] = boom

    wire = dispatch(make_deps(), repo)

    assert wire.exit_code == DENY_EXIT
    assert wire.stderr == "rm -rf is blocked\n"
    assert resolver.calls == [("guard-a", "pre_tool_use")]


def test_ask_and_context_accumulate(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a", priority=10), hook_record("guard-b", priority=20))
    resolver.handlers["guard-a"] = verdict(Decision.ASK, "sure?")
    resolver.handlers["guard-b"] = verdict(Decision.DENY, "no")

    assert dispatch(make_deps(), repo).exit_code == DENY_EXIT
    assert resolver.calls == [("guard-a", "pre_tool_use"), ("guard-b", "pre_tool_use")]


def test_selection_order_is_class_rank_priority_id(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(
        hook_record("quality-first", priority=1, on_error="open"),
        hook_record("guard-z", priority=30),
        hook_record("guard-b", priority=20),
        hook_record("guard-a", priority=20),
    )
    for hook_id in ("quality-first", "guard-z", "guard-b", "guard-a"):
        resolver.handlers[hook_id] = verdict(Decision.NONE)

    dispatch(make_deps(), repo)

    assert [hook for hook, _ in resolver.calls] == [
        "guard-a",
        "guard-b",
        "guard-z",
        "quality-first",
    ]


@pytest.mark.parametrize(
    ("matcher", "tool", "selected"),
    [
        ({"tools": ["edit"]}, "Edit", True),
        ({"tools": ["edit"]}, "Bash", False),
        ({"tool_names": ["Ed.*"]}, "Edit", True),
        # tools and tool_names are one OR-ed dimension (§A.2): either selects the call.
        ({"tools": ["edit"], "tool_names": ["Skill"]}, "Edit", True),
        ({"tools": ["edit"], "tool_names": ["Skill"]}, "Skill", True),
        ({"tools": ["edit"], "tool_names": ["Skill"]}, "Bash", False),
        ({"paths": ["src/**"]}, "Edit", True),
        ({"paths": ["docs/**"]}, "Edit", False),
        ({"command": [r"\bls\b"]}, "Bash", True),
        ({"command": [r"\bls\b"]}, "Edit", False),
        ({"tools": ["shell"], "command": ["^git "]}, "Bash", False),
    ],
)
def test_matcher_dimensions_are_anded(
    repo: GuardRepo,
    resolver: FakeHandlerResolver,
    make_deps: Callable[..., RuntimeDeps],
    matcher: dict[str, list[str]],
    tool: str,
    selected: bool,
) -> None:
    repo.install(hook_record("guard-m", matcher={"pre_tool_use": matcher}))
    resolver.handlers["guard-m"] = verdict(Decision.NONE)

    dispatch(make_deps(), repo, tool=tool)

    assert bool(resolver.calls) is selected


def test_hook_not_supporting_the_harness_is_not_selected(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-c", supports=["claude_code"]))
    resolver.handlers["guard-c"] = verdict(Decision.DENY)

    wire = dispatch(make_deps(), repo, harness=Harness.OPENCODE)

    assert resolver.calls == []
    assert json.loads(wire.stdout)["decision"] == "none"


def test_hooks_disable_env_skips_non_mandatory_only(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(
        hook_record("guard-a"),
        hook_record("guard-m", mandatory=True, source_package="acme_rules"),
    )
    resolver.handlers["guard-a"] = verdict(Decision.DENY)
    resolver.handlers["guard-m"] = verdict(Decision.NONE)
    deps = make_deps(PLAYBOOK_HOOKS_DISABLE="guard-a,guard-m")

    first = dispatch(deps, repo)
    second = dispatch(make_deps(PLAYBOOK_HOOKS_DISABLE="guard-a,guard-m"), repo)

    assert [hook for hook, _ in resolver.calls] == ["guard-m", "guard-m"]
    assert body(first)["systemMessage"] == (
        "Playbook hook guard-a is off this session (PLAYBOOK_HOOKS_DISABLE)."
    )
    assert second.stdout == ""
    escapes = [line for line in repo.decisions() if line["decision"] == "escape"]
    assert [line["escape"] for line in escapes] == ["PLAYBOOK_HOOKS_DISABLE"]


def test_playbook_hooks_off_writes_nothing_and_exits_0(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a"))
    resolver.handlers["guard-a"] = verdict(Decision.DENY)
    deps = make_deps(PLAYBOOK_HOOKS="off")

    wire = dispatch(deps, repo)
    dispatch(make_deps(PLAYBOOK_HOOKS="off"), repo)

    assert (wire.stdout, wire.stderr, wire.exit_code) == ("", "", 0)
    assert deps.out is not None and deps.out.getvalue() == ""  # type: ignore[attr-defined]
    assert resolver.calls == []
    assert [(line["decision"], line["escape"]) for line in repo.decisions()] == [
        ("escape", "PLAYBOOK_HOOKS")
    ]


def test_hatch_with_a_wrong_value_has_no_effect(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a"))
    resolver.handlers["guard-a"] = verdict(Decision.DENY)

    assert dispatch(make_deps(PLAYBOOK_HOOKS="OFF"), repo).exit_code == DENY_EXIT


# --- matcher dimensions of the non-tool events -------------------------------------------


def _matcher(**dims: Any) -> Any:
    from coding_agent_playbook.artifacts.path_globs import compile_globs
    from coding_agent_playbook.hook_runtime.config.hook_records import MatcherSpec

    return MatcherSpec(paths=compile_globs(dims.pop("paths", ()), platform="linux"), **dims)


@pytest.mark.parametrize(
    ("event", "fields", "dims", "accepted"),
    [
        (EventName.SESSION_START, {"source": "resume"}, {"sources": ("startup",)}, False),
        (EventName.SESSION_START, {"source": "startup"}, {"sources": ("startup",)}, True),
        (EventName.PRE_COMPACT, {"source": "auto"}, {"triggers": ("manual",)}, False),
        (EventName.SUBAGENT_STOP, {"agent_type": "Explore"}, {"agent_types": ("Explore",)}, True),
        (EventName.STOP, {}, {"tools": ("shell",)}, True),
    ],
)
def test_non_tool_matchers(
    event: EventName, fields: dict[str, Any], dims: dict[str, Any], accepted: bool
) -> None:
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.selection import matcher_accepts

    ev = CanonicalEvent(
        name=event,
        harness=Harness.CLAUDE_CODE,
        session_id="s",
        cwd="/r",
        project_dir="/r",
        **fields,
    )

    assert matcher_accepts(_matcher(**dims), ev) is accepted


@pytest.mark.parametrize(
    "dims",
    [{"tools": ("not_a_class",)}, {"tool_names": ("([",)}, {"command": ("([",)}],
)
def test_invalid_matcher_values_never_match(
    repo: GuardRepo,
    resolver: FakeHandlerResolver,
    make_deps: Callable[..., RuntimeDeps],
    dims: dict[str, list[str]],
) -> None:
    repo.install(
        hook_record("guard-m", matcher={"pre_tool_use": {k: list(v) for k, v in dims.items()}})
    )
    resolver.handlers["guard-m"] = verdict(Decision.DENY)

    dispatch(make_deps(), repo, tool="Bash")

    assert resolver.calls == []


def test_a_result_is_attributed_to_the_hook_that_ran(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult

    repo.install(hook_record("guard-a"))
    resolver.handlers["guard-a"] = lambda ev, ctx: HandlerResult(
        decision=Decision.DENY, hook_id="someone-else", reason="no"
    )

    dispatch(make_deps(), repo)

    assert [line["hook_id"] for line in repo.decisions()] == ["guard-a"]

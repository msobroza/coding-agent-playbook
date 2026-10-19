"""Tests for the one home of the hook event, tool-class and support tables.

specs/prK-lifecycle-hooks.md §A.2 (event and tool-class tables), §A.11 (one home),
§C.1.2 and §C.5.1 (per-adapter support matrix).
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath
from typing import get_args

from coding_agent_playbook import hook_policy
from coding_agent_playbook.artifacts.hook_schema import (
    MATCHER_KEYS,
    HookDecision,
    HookEvent,
    HookOnError,
    ToolClass,
)
from coding_agent_playbook.hook_policy import (
    ADVISORY_RULE_PREFIX,
    DEGRADED_EVENTS,
    ENGINE_DEADLINE_CAP_MS,
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    HOOK_SCRIPTS_DIR,
    HOOK_SUPPORT,
    MATCHER_VALUES,
    ON_ERROR_STRENGTH,
    TOOL_CLASS_NAMES,
)
from coding_agent_playbook.hook_runtime.decision import EVENT_DECISIONS
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.harness import CLAUDE_EVENT_NAMES
from coding_agent_playbook.hook_runtime.policy import (
    ENGINE_DEADLINE_CAP_MS as RUNTIME_DEADLINE_CAP_MS,
)
from coding_agent_playbook.hook_runtime.policy import ON_ERROR_ALLOWED
from tests.import_probe import new_modules_after


def test_hook_events_match_hook_event_literal() -> None:
    # Same members *and* order: renderers append new event keys in canonical
    # event order (§C.2.2), so the table order is part of the contract.
    assert tuple(HOOK_EVENTS) == get_args(HookEvent)


def test_event_specs_use_only_canonical_vocabularies() -> None:
    decisions = set(get_args(HookDecision))
    on_errors = set(get_args(HookOnError))
    for event, spec in HOOK_EVENTS.items():
        assert spec.decisions <= decisions, event
        assert "none" in spec.decisions, event
        assert spec.on_error_allowed <= on_errors, event
        assert "open" in spec.on_error_allowed, event
        assert spec.matcher_fields <= set(MATCHER_KEYS), event


def test_every_matcher_field_belongs_to_some_event() -> None:
    used = {name for spec in HOOK_EVENTS.values() for name in spec.matcher_fields}
    assert used == set(MATCHER_KEYS)


def test_claude_names_are_unique_pascal_case() -> None:
    names = [spec.claude_name for spec in HOOK_EVENTS.values()]
    assert len(set(names)) == len(names)
    assert all(name[0].isupper() and "_" not in name for name in names)


def test_event_table_matches_a2() -> None:
    pre = HOOK_EVENTS["pre_tool_use"]
    assert pre.claude_name == "PreToolUse"
    assert pre.decisions == {"deny", "ask", "context", "none"}
    assert pre.on_error_allowed == {"ask", "deny", "open"}
    assert pre.matcher_fields == {"tools", "tool_names", "paths", "command"}
    assert HOOK_EVENTS["user_prompt_submit"].on_error_allowed == {"deny", "open"}
    assert HOOK_EVENTS["pre_compact"].decisions == {"none"}
    assert HOOK_EVENTS["subagent_stop"].matcher_fields == {"agent_types"}
    assert HOOK_EVENTS["stop"].matcher_fields == frozenset()


def test_tool_class_names_match_tool_class_literal() -> None:
    assert tuple(TOOL_CLASS_NAMES) == get_args(ToolClass)
    # 'other' is the runtime-only bucket (H4): never authorable, never tabled.
    assert "other" not in TOOL_CLASS_NAMES


def test_tool_class_names_cover_the_hook_capable_adapters() -> None:
    for tool_class, names in TOOL_CLASS_NAMES.items():
        assert set(names) == HOOK_CAPABLE_ADAPTERS, tool_class
    assert TOOL_CLASS_NAMES["shell"]["claude_code"] == ("Bash", "PowerShell")
    assert TOOL_CLASS_NAMES["subagent"]["opencode"] == ("task",)
    # No OpenCode tool exists for these classes: validate warns, check says degraded.
    assert TOOL_CLASS_NAMES["mcp"]["opencode"] == ()
    assert TOOL_CLASS_NAMES["notebook_edit"]["opencode"] == ()


def test_hook_support_is_canonical_and_decisions_are_event_subsets() -> None:
    assert set(HOOK_SUPPORT) == HOOK_CAPABLE_ADAPTERS
    for adapter, events in HOOK_SUPPORT.items():
        for event, decisions in events.items():
            assert event in HOOK_EVENTS, (adapter, event)
            assert decisions <= HOOK_EVENTS[event].decisions, (adapter, event)
            assert decisions, (adapter, event)


def test_degraded_events_are_reachable_events() -> None:
    assert set(DEGRADED_EVENTS) == HOOK_CAPABLE_ADAPTERS
    for adapter, events in DEGRADED_EVENTS.items():
        assert events <= set(HOOK_SUPPORT[adapter]), adapter


def test_claude_code_supports_every_event() -> None:
    support = HOOK_SUPPORT["claude_code"]
    assert tuple(support) == get_args(HookEvent)
    for event, spec in HOOK_EVENTS.items():
        assert support[event] == spec.decisions, event
    assert DEGRADED_EVENTS["claude_code"] == frozenset()


def test_opencode_support_matches_c5_matrix() -> None:
    assert dict(HOOK_SUPPORT["opencode"]) == {
        # ask has no OpenCode primitive and degrades to deny (§D.3.6).
        "pre_tool_use": frozenset({"deny", "ask", "context", "none"}),
        "post_tool_use": frozenset({"context", "none"}),
        "session_start": frozenset({"context", "none"}),
        "stop": frozenset({"deny", "context", "none"}),
    }
    assert DEGRADED_EVENTS["opencode"] == {"session_start", "stop"}


def test_on_error_strength_orders_open_ask_deny() -> None:
    assert set(ON_ERROR_STRENGTH) == set(get_args(HookOnError))
    assert ON_ERROR_STRENGTH["open"] < ON_ERROR_STRENGTH["ask"] < ON_ERROR_STRENGTH["deny"]


def test_deadline_caps_match_d4() -> None:
    assert tuple(ENGINE_DEADLINE_CAP_MS) == tuple(HOOK_EVENTS)
    assert dict(ENGINE_DEADLINE_CAP_MS) == {
        "session_start": 15_000,
        "user_prompt_submit": 30_000,
        "pre_tool_use": 30_000,
        "post_tool_use": 60_000,
        "post_tool_use_failure": 30_000,
        "stop": 595_000,
        "subagent_stop": 595_000,
        "pre_compact": 30_000,
        "session_end": 8_000,
    }


def test_matcher_values_are_closed_vocabularies_of_their_fields() -> None:
    assert dict(MATCHER_VALUES) == {
        "sources": frozenset({"startup", "resume", "clear", "compact", "fork"}),
        "triggers": frozenset({"manual", "auto"}),
    }
    assert set(MATCHER_VALUES) <= set(MATCHER_KEYS)


def test_constants() -> None:
    assert ADVISORY_RULE_PREFIX == "guardrail-"
    path = PurePosixPath(HOOK_SCRIPTS_DIR)
    assert not path.is_absolute()
    assert path.parts == (".coding-agent-playbook", "hooks", "scripts")


def test_tables_are_read_only() -> None:
    for table in (
        HOOK_EVENTS,
        TOOL_CLASS_NAMES,
        HOOK_SUPPORT,
        DEGRADED_EVENTS,
        ON_ERROR_STRENGTH,
        ENGINE_DEADLINE_CAP_MS,
        MATCHER_VALUES,
    ):
        assert not hasattr(table, "__setitem__")
    assert not hasattr(HOOK_SUPPORT["opencode"], "__setitem__")


def test_package_facade_exports_every_table() -> None:
    assert set(hook_policy.__all__) >= {
        "ADVISORY_RULE_PREFIX",
        "DEGRADED_EVENTS",
        "EventSpec",
        "HOOK_CAPABLE_ADAPTERS",
        "HOOK_EVENTS",
        "HOOK_SCRIPTS_DIR",
        "HOOK_SUPPORT",
        "ON_ERROR_STRENGTH",
        "TOOL_CLASS_NAMES",
    }


def test_hook_policy_imports_only_the_stdlib() -> None:
    # Sync-time but stdlib-only (§A.6): no yaml/jinja2, and not types.py, which
    # imports yaml at module top. Since K2 it also reads the import-light runtime
    # tables and handler registry it shares with the dispatcher (one source each).
    loaded = new_modules_after("import coding_agent_playbook.hook_policy")

    ours = [name for name in loaded if name.startswith("coding_agent_playbook")]
    foreign = [
        name
        for name in loaded
        if name not in ours and name.split(".")[0] not in sys.stdlib_module_names
    ]
    # Not detector (packaging) nor config.tables.hooks: the effective view imports
    # evaluate_predicate when it runs, and the config types only for typing.
    assert ours == [
        "coding_agent_playbook.artifacts",
        "coding_agent_playbook.artifacts.hook_schema",
        "coding_agent_playbook.catalog",
        "coding_agent_playbook.catalog.layers",
        "coding_agent_playbook.hook_policy",
        "coding_agent_playbook.hook_policy._contract_handlers",
        "coding_agent_playbook.hook_policy._findings",
        "coding_agent_playbook.hook_policy.advisory",
        "coding_agent_playbook.hook_policy.contract",
        "coding_agent_playbook.hook_policy.contract_set",
        "coding_agent_playbook.hook_policy.effective",
        # GUARDRAILS_SKILL_ID, named by the AGENTS.md Guardrails preface (D6)
        "coding_agent_playbook.hook_policy.guardrails_skill",
        "coding_agent_playbook.hook_policy.handler_catalog",
        "coding_agent_playbook.hook_policy.labels",
        "coding_agent_playbook.hook_policy.lint_codes",  # a linked rule's lint_codes (K7)
        "coding_agent_playbook.hook_policy.merge",
        "coding_agent_playbook.hook_policy.override_rules",
        "coding_agent_playbook.hook_policy.resolved",
        "coding_agent_playbook.hook_policy.tables",
        "coding_agent_playbook.hook_runtime",
        "coding_agent_playbook.hook_runtime._event_memo",  # HandlerContext.memo (K7)
        "coding_agent_playbook.hook_runtime.config",
        "coding_agent_playbook.hook_runtime.config.keys",
        "coding_agent_playbook.hook_runtime.decision",
        "coding_agent_playbook.hook_runtime.event",
        "coding_agent_playbook.hook_runtime.harness",
        "coding_agent_playbook.hook_runtime.paths",
        "coding_agent_playbook.hook_runtime.policy",
        "coding_agent_playbook.hook_runtime.registry",
        # H21's wrapper-prefix rule, one source with the dispatcher's env check
        "coding_agent_playbook.hook_runtime.wrapper_policy",
    ]
    assert foreign == []


def test_event_decision_and_deadline_tables_have_one_source() -> None:
    # The runtime owns these tables (§D.3.5, §D.4); hook_policy derives its
    # string-keyed views from them, so the two can never drift apart.
    assert list(HOOK_EVENTS) == [event.value for event in EventName]
    for event in EventName:
        spec = HOOK_EVENTS[event.value]
        assert spec.decisions == {decision.value for decision in EVENT_DECISIONS[event]}
        assert spec.on_error_allowed == set(ON_ERROR_ALLOWED[event])
        assert spec.claude_name == CLAUDE_EVENT_NAMES[event]
        assert ENGINE_DEADLINE_CAP_MS[event.value] == RUNTIME_DEADLINE_CAP_MS[event]

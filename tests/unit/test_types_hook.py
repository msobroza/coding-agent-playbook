"""Tests for the Hook frontmatter structure: H1 (keys, required, types) and H8.

specs/prK-lifecycle-hooks.md §A.2 (schema) and §A.3 (dataclasses). Value
domains (H2-H13) are ``hook_policy.classify_hook``'s job and are tested there;
round trips and the advisory envelope live in test_types_hook_roundtrip.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.types import (
    Hook,
    HookFrontmatter,
    HookHandler,
    HookMatcher,
    HookSchemaError,
)
from tests.hook_samples import HOOK_WHERE, hook_frontmatter, hook_mapping, write_hook_md

if TYPE_CHECKING:
    from pathlib import Path

BLANKS_MD = """\
---
id: guard-x
name: Guard X
description: Deny x.
tier: default
events: [pre_tool_use]
decisions: [deny, none]
timeout: 2
on_error: ask
supports: [claude_code]
handler:
  builtin: guard_x
  args:
  config:
handlers:
matcher:
  pre_tool_use:
    tools:
version:
enabled:
mandatory:
priority:
applies_if:
linked_rule:
tags:
summary:
---
"""


def _schema_error(data: dict[str, Any]) -> HookSchemaError:
    with pytest.raises(HookSchemaError) as caught:
        HookFrontmatter.from_mapping(data, where=HOOK_WHERE)
    assert caught.value.where == HOOK_WHERE
    assert str(caught.value).startswith(f"{HOOK_WHERE}: ")
    return caught.value


# --- HookFrontmatter.from_mapping: structure (H1) -------------------------------


def test_from_mapping_builds_nested_handler_and_matcher() -> None:
    fm = hook_frontmatter(
        events=["pre_tool_use", "stop"],
        handler=None,
        handlers={
            "pre_tool_use": {"builtin": "gate_guard:pre_edit", "config": {"rows": ["a"]}},
            "stop": {"command": "python", "script": "scripts/gate.py", "args": ["-v"]},
        },
        matcher={"pre_tool_use": {"tools": ["edit"], "paths": ["src/**"]}},
        applies_if={"languages": ["python"]},
        linked_rule="python-error-handling",
    )

    assert fm.handler is None
    assert fm.handlers == {
        "pre_tool_use": HookHandler(builtin="gate_guard:pre_edit", config={"rows": ["a"]}),
        "stop": HookHandler(command="python", script="scripts/gate.py", args=["-v"]),
    }
    assert fm.matcher == {"pre_tool_use": HookMatcher(tools=["edit"], paths=["src/**"])}
    assert fm.applies_if == {"languages": ["python"]}
    assert fm.linked_rule == "python-error-handling"
    assert (fm.version, fm.enabled, fm.mandatory, fm.priority, fm.tags) == (1, True, False, 50, [])


def test_from_mapping_keeps_value_domains_for_classify_hook() -> None:
    # H1 is structure only: a non-canonical event or decision is a *value*
    # problem that classify_hook reports with every other issue of the hook.
    fm = hook_frontmatter(events=["PreToolUse"], decisions=["allow"], tier="core")

    assert (fm.events, fm.decisions, fm.tier) == (["PreToolUse"], ["allow"], "core")


@pytest.mark.parametrize(
    ("data", "field", "key", "allowed"),
    [
        (
            hook_mapping(colour="red"),
            "colour",
            "colour",
            "id, name, description, summary, version, tier",
        ),
        (
            hook_mapping(handler={"builtin": "x", "retries": 3}),
            "handler.retries",
            "retries",
            "builtin, command, script, args, config",
        ),
        (
            hook_mapping(handler=None, handlers={"pre_tool_use": {"builtin": "x", "env": {}}}),
            "handlers.pre_tool_use.env",
            "env",
            "builtin, command, script, args, config",
        ),
        (
            hook_mapping(matcher={"pre_tool_use": {"glob": ["*.py"]}}),
            "matcher.pre_tool_use.glob",
            "glob",
            "tools, tool_names, paths, command, sources, triggers, agent_types",
        ),
    ],
    ids=["top", "handler", "handlers", "matcher"],
)
def test_from_mapping_unknown_key_names_key_and_allowed_set(
    data: dict[str, Any], field: str, key: str, allowed: str
) -> None:
    error = _schema_error(data)

    assert (error.field, error.value) == (field, key)
    assert f"unknown key '{key}'; allowed: {allowed}" in str(error)


@pytest.mark.parametrize(
    "key",
    ["id", "name", "description", "tier", "events", "decisions", "timeout", "on_error", "supports"],
)
def test_from_mapping_missing_required_key_names_field(key: str) -> None:
    data = hook_mapping()
    del data[key]

    error = _schema_error(data)

    assert error.field == key
    assert f"{key}: missing required key" in str(error)


@pytest.mark.parametrize(
    ("overrides", "field", "value", "expected"),
    [
        ({"timeout": "2s"}, "timeout", "2s", "a number of seconds"),
        ({"timeout": True}, "timeout", True, "a number of seconds"),
        ({"priority": True}, "priority", True, "an integer"),
        ({"version": 1.5}, "version", 1.5, "an integer"),
        ({"events": "pre_tool_use"}, "events", "pre_tool_use", "a list of strings"),
        ({"tags": [1]}, "tags", [1], "a list of strings"),
        ({"enabled": "yes"}, "enabled", "yes", "a boolean"),
        ({"name": None}, "name", None, "a string"),
        ({"id": 7}, "id", 7, "a string"),
        ({"handler": "guard_x"}, "handler", "guard_x", "a mapping"),
        ({"applies_if": ["x"]}, "applies_if", ["x"], "a mapping"),
        ({"handler": {"builtin": 3}}, "handler.builtin", 3, "a string"),
        ({"handler": {"builtin": "x", "args": "-v"}}, "handler.args", "-v", "a list of strings"),
        (
            {"matcher": {"pre_tool_use": {"tools": "edit"}}},
            "matcher.pre_tool_use.tools",
            "edit",
            "a list of strings",
        ),
        ({"matcher": {"pre_tool_use": ["edit"]}}, "matcher.pre_tool_use", ["edit"], "a mapping"),
        ({"matcher": {1: {}}}, "matcher", 1, "an event name"),
    ],
)
def test_from_mapping_wrong_type_names_value_and_expected(
    overrides: dict[str, Any], field: str, value: object, expected: str
) -> None:
    error = _schema_error(hook_mapping(**overrides))

    assert (error.field, error.value) == (field, value)
    assert error.expected == expected
    assert f"{field}: expected {expected}, got {value!r}" in str(error)


def test_from_mapping_rejects_a_non_mapping() -> None:
    error = _schema_error(["id", "guard-x"])  # type: ignore[arg-type]

    assert error.field == "frontmatter"
    assert "expected a mapping" in str(error)


# --- summary: the one-line guardrail (specs/prS-skills-context.md 8.4.1, 8.6) ---------

_SUMMARY_SHAPE = "a single line of 1-120 characters without '{{' or '{%'"


def _summary_error(summary: object) -> HookSchemaError:
    error = _schema_error(hook_mapping(summary=summary))
    assert (error.field, error.value, error.expected) == ("summary", summary, _SUMMARY_SHAPE)
    assert f"summary: expected {_SUMMARY_SHAPE}, got {summary!r}" in str(error)
    return error


def test_summary_longer_than_120_chars_is_a_schema_error() -> None:
    _summary_error("Never run destructive commands " + "x" * 120)


@pytest.mark.parametrize(
    "summary",
    ["Ask first.\nThen act.", "Ask first.\n", "Ask\rfirst."],
    ids=["lf", "trailing", "cr"],
)
def test_multiline_summary_is_a_schema_error(summary: str) -> None:
    _summary_error(summary)


@pytest.mark.parametrize("summary", ["Run {{ tool }} first.", "{% if x %}Ask.{% endif %}"])
def test_templated_summary_is_a_schema_error(summary: str) -> None:
    _summary_error(summary)


@pytest.mark.parametrize("summary", ["   ", 7, ["Ask first."]], ids=["blank", "int", "list"])
def test_blank_or_non_string_summary_is_a_schema_error(summary: object) -> None:
    _summary_error(summary)


def test_summary_of_120_chars_is_kept_as_written() -> None:
    summary = "Ask first. " + "y" * 109

    assert len(summary) == 120
    assert hook_frontmatter(summary=summary).summary == summary


def test_absent_blank_or_empty_summary_defaults_to_empty() -> None:
    """``""`` is the default ``Hook.to_dict`` writes, so it must read back as no summary."""
    assert hook_frontmatter().summary == ""
    assert hook_frontmatter(summary=None).summary == ""
    assert hook_frontmatter(summary="").summary == ""


@pytest.mark.parametrize("key", ["type", "url", "async", "updated_input"])
def test_from_mapping_contract_keys_get_contract_message(key: str) -> None:
    error = _schema_error(hook_mapping(handler={"builtin": "x", key: "v"}))

    assert (error.field, error.value) == (f"handler.{key}", key)
    assert "HTTP/async/rewrite handlers are not part of the hook contract (SPEC §17.1)" in str(
        error
    )


@pytest.mark.parametrize("key", ["prompt", "model", "headers"])
def test_contract_keys_are_rejected_at_the_top_level_too(key: str) -> None:
    error = _schema_error(hook_mapping(**{key: "v"}))

    assert error.field == key
    assert "not part of the hook contract" in str(error)


# --- defaults and coercion ---------------------------------------------------


def test_blank_yaml_values_coerce_to_defaults(tmp_path: Path) -> None:
    fm = Hook.from_markdown(write_hook_md(tmp_path, BLANKS_MD), "<repo-local>").frontmatter

    assert (fm.version, fm.enabled, fm.mandatory, fm.priority) == (1, True, False, 50)
    assert (fm.handlers, fm.applies_if, fm.tags, fm.linked_rule) == ({}, {}, [], None)
    assert fm.summary == ""
    assert fm.handler == HookHandler(builtin="guard_x")
    assert fm.matcher == {"pre_tool_use": HookMatcher()}


def test_blank_matcher_entry_is_an_empty_matcher() -> None:
    assert hook_frontmatter(matcher={"pre_tool_use": None}).matcher == {
        "pre_tool_use": HookMatcher()
    }


def test_constructor_none_coercion() -> None:
    fm = HookFrontmatter(
        id="guard-x",
        name="Guard X",
        description="Deny x.",
        tier="default",
        events=["pre_tool_use"],
        decisions=["deny"],
        timeout=2.0,
        on_error="ask",
        supports=["claude_code"],
        handlers=None,  # type: ignore[arg-type]
        version=None,  # type: ignore[arg-type]
        enabled=None,  # type: ignore[arg-type]
        mandatory=None,  # type: ignore[arg-type]
        priority=None,  # type: ignore[arg-type]
        matcher=None,  # type: ignore[arg-type]
        applies_if=None,  # type: ignore[arg-type]
        tags=None,  # type: ignore[arg-type]
    )

    assert (fm.version, fm.enabled, fm.mandatory, fm.priority) == (1, True, False, 50)
    assert (fm.handlers, fm.matcher, fm.applies_if, fm.tags) == ({}, {}, {}, [])
    assert HookHandler(args=None, config=None) == HookHandler()  # type: ignore[arg-type]
    assert HookMatcher(tools=None, paths=None) == HookMatcher()  # type: ignore[arg-type]


def test_int_timeout_becomes_float() -> None:
    parsed = hook_frontmatter(timeout=2)
    built = HookFrontmatter(
        id="x",
        name="X",
        description="x",
        tier="default",
        events=["stop"],
        decisions=["none"],
        timeout=3,
        on_error="open",
        supports=["claude_code"],
    )

    assert (parsed.timeout, type(parsed.timeout)) == (2.0, float)
    assert (built.timeout, type(built.timeout)) == (3.0, float)
    assert hook_frontmatter(timeout=1.5).timeout == 1.5


# --- handlers ----------------------------------------------------------------


def test_handler_for_returns_shared_or_per_event_handler() -> None:
    shared = hook_frontmatter(events=["pre_tool_use", "stop"])
    split = hook_frontmatter(
        events=["pre_tool_use", "stop"],
        handler=None,
        handlers={"pre_tool_use": {"builtin": "g:pre_edit"}, "stop": {"builtin": "g"}},
    )

    assert shared.handler_for("stop") == shared.handler_for("pre_tool_use") == shared.handler
    assert split.handler_for("pre_tool_use") == HookHandler(builtin="g:pre_edit")
    assert split.handler_for("stop") == HookHandler(builtin="g")


def test_handler_for_unbound_event_names_hook_and_event() -> None:
    fm = hook_frontmatter(handler=None, handlers={"stop": {"builtin": "g"}})

    with pytest.raises(HookSchemaError, match=r"hook 'guard-x': handlers: .*'pre_tool_use'"):
        fm.handler_for("pre_tool_use")


def test_handler_is_external() -> None:
    assert not HookHandler(builtin="guard_x").is_external
    assert HookHandler(command="python", script="scripts/check.py").is_external

"""Tests for the Hook round trips (§A.4), markdown loading and advisory envelope (§A.8).

specs/prK-lifecycle-hooks.md §A.3, §A.4 and §A.8.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.hook_schema import HookHandler, HookSchemaError
from tests.hook_samples import (
    GUARD_GENERATED_OUTPUTS_MD,
    HOOK_WHERE,
    hook_frontmatter,
    write_hook_md,
)


def _hook(body: str = "Do not edit x.\n", **overrides: Any) -> Hook:
    return Hook(
        frontmatter=hook_frontmatter(**overrides),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=Path("/repo/playbook/hooks/guard-x/HOOK.md"),
        source_package="<repo-local>",
    )


# --- round trips (§A.4) ------------------------------------------------------


@pytest.mark.parametrize(
    "hook",
    [
        Hook(
            frontmatter=hook_frontmatter(),
            body="Advice.\n",
            template_body="Advice.\n",
            is_templated=False,
            source_path=None,
            source_package="coding_agent_playbook",
        ),
        Hook(
            frontmatter=hook_frontmatter(
                events=["post_tool_use"],
                decisions=["context", "none"],
                on_error="open",
                handler={"command": "python", "script": "scripts/pii.py", "args": ["-n", "5"]},
                matcher={"post_tool_use": {"tools": ["edit"], "paths": ["**/*.sql"]}},
                linked_rule="pii-handling",
            ),
            body="rendered\n",
            template_body="{{ x }}\n",
            is_templated=True,
            source_path=Path("/pkg/resources/hooks/data/guard-x/HOOK.md.j2"),
            source_package="playbook_rules_bnp",
            scripts_dir=Path("/pkg/resources/hooks/data/guard-x/scripts"),
        ),
    ],
    ids=["builtin-no-path", "external-with-scripts"],
)
def test_hook_dict_roundtrip_identity(hook: Hook) -> None:
    assert Hook.from_dict(hook.to_dict()) == hook


def test_to_dict_serializes_paths_as_strings() -> None:
    data = _hook().to_dict()

    assert data["source_path"] == "/repo/playbook/hooks/guard-x/HOOK.md"
    assert data["scripts_dir"] is None
    assert data["frontmatter"]["handler"] == {
        "builtin": "guard_x",
        "command": None,
        "script": None,
        "args": [],
        "config": {},
    }


def test_markdown_roundtrip_equal_frontmatter_and_template_body(tmp_path: Path) -> None:
    first = Hook.from_markdown(
        write_hook_md(tmp_path, GUARD_GENERATED_OUTPUTS_MD), "coding_agent_playbook"
    )
    again_path = tmp_path / "again" / "HOOK.md"
    again_path.parent.mkdir()
    again_path.write_text(first.to_markdown(), encoding="utf-8")

    again = Hook.from_markdown(again_path, "coding_agent_playbook")

    assert again.frontmatter == first.frontmatter
    assert again.template_body == first.template_body
    assert first.frontmatter.handler == HookHandler(
        builtin="guard_generated_outputs", config={"extra_protected": []}
    )


def test_to_mapping_drops_empty_values_recursively() -> None:
    fm = hook_frontmatter(
        events=["pre_tool_use", "stop"],
        matcher={"pre_tool_use": {"tools": ["edit"]}, "stop": None},
        handler={"builtin": "guard_x", "config": {"extra_protected": []}},
    )

    mapping = fm.to_mapping()

    assert mapping["handler"] == {"builtin": "guard_x", "config": {"extra_protected": []}}
    # An empty matcher entry stays: dropping it would not round-trip equal.
    assert mapping["matcher"] == {"pre_tool_use": {"tools": ["edit"]}, "stop": {}}
    assert {"handlers", "applies_if", "linked_rule", "tags"}.isdisjoint(mapping)
    assert (mapping["enabled"], mapping["mandatory"]) == (True, False)
    assert HookFrontmatter.from_mapping(mapping, where=HOOK_WHERE) == fm


def test_summary_round_trips_and_an_empty_one_is_dropped(tmp_path: Path) -> None:
    """D6: a hook without ``summary`` serializes byte-identically to the days before the field."""
    with_summary = hook_frontmatter(summary="Ask first.")
    without = hook_frontmatter()

    assert with_summary.to_mapping()["summary"] == "Ask first."
    assert HookFrontmatter.from_mapping(with_summary.to_mapping(), where=HOOK_WHERE) == with_summary
    assert "summary" not in without.to_mapping()
    first = Hook.from_markdown(
        write_hook_md(tmp_path, GUARD_GENERATED_OUTPUTS_MD), "coding_agent_playbook"
    )
    assert "summary" not in first.to_markdown()
    assert Hook.from_dict(first.to_dict()) == first


def test_to_mapping_compacts_per_event_handlers() -> None:
    fm = hook_frontmatter(handler=None, handlers={"pre_tool_use": {"builtin": "g"}})

    assert fm.to_mapping()["handlers"] == {"pre_tool_use": {"builtin": "g"}}
    assert "handler" not in fm.to_mapping()


# --- from_markdown -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "id: guard-x\n",
        "---\nid: guard-x\n",
        "---\nid: [unclosed\n---\n",
        "---\n- a list\n---\n",
    ],
    ids=["no-fence", "unterminated", "bad-yaml", "not-a-mapping"],
)
def test_from_markdown_wraps_bad_fence_and_bad_yaml_in_hook_schema_error(
    tmp_path: Path, text: str
) -> None:
    path = write_hook_md(tmp_path, text)

    with pytest.raises(HookSchemaError) as caught:
        Hook.from_markdown(path, "<repo-local>")

    assert (caught.value.where, caught.value.field) == (str(path), "frontmatter")


def test_from_markdown_reports_schema_errors_against_the_file(tmp_path: Path) -> None:
    path = write_hook_md(tmp_path, GUARD_GENERATED_OUTPUTS_MD.replace("timeout: 2", "timeout: 2s"))

    with pytest.raises(HookSchemaError, match=r"timeout: expected a number of seconds, got '2s'"):
        Hook.from_markdown(path, "<repo-local>")


def test_from_markdown_sets_is_templated_scripts_dir_and_hook_dir(tmp_path: Path) -> None:
    path = write_hook_md(tmp_path, GUARD_GENERATED_OUTPUTS_MD, name="HOOK.md.j2", scripts=True)

    hook = Hook.from_markdown(path, "playbook_rules_bnp")

    assert hook.is_templated
    assert hook.source_path == path
    assert hook.hook_dir == path.parent
    assert hook.scripts_dir == path.parent / "scripts"
    assert hook.source_package == "playbook_rules_bnp"
    assert hook.body == hook.template_body
    assert hook.template_body.startswith("Files that begin")


def test_from_markdown_without_scripts(tmp_path: Path) -> None:
    hook = Hook.from_markdown(write_hook_md(tmp_path, GUARD_GENERATED_OUTPUTS_MD), "<repo-local>")

    assert (hook.is_templated, hook.scripts_dir) == (False, None)


def test_hook_dir_is_none_without_a_source_path() -> None:
    assert Hook.from_dict({**_hook().to_dict(), "source_path": None}).hook_dir is None


# --- the advisory-rule envelope (§A.8) ---------------------------------------


@pytest.mark.parametrize("body", ["", "  \n\n"])
def test_to_advisory_rule_is_none_for_blank_body(body: str) -> None:
    assert _hook(body).to_advisory_rule() is None


def test_to_advisory_rule_envelope() -> None:
    hook = _hook("Do not edit x.\n", tags=["protect"], applies_if={"languages": ["python"]})

    rule = hook.to_advisory_rule()

    assert rule is not None
    fm = rule.frontmatter
    assert (fm.id, fm.name, fm.description) == (
        "guardrail-guard-x",
        "Guardrail: Guard X",
        "Deny x.",
    )
    assert (fm.priority, fm.scope, fm.globs, fm.applies_if) == (30, "always", [], {})
    assert (rule.body, rule.template_body) == ("Do not edit x.\n", "Do not edit x.\n")
    assert not rule.is_templated  # the body is already rendered
    assert (rule.source_path, rule.source_package) == (hook.source_path, "<repo-local>")


def test_to_advisory_rule_scopes_to_the_matcher_paths() -> None:
    hook = _hook(
        events=["pre_tool_use", "post_tool_use"],
        matcher={
            "pre_tool_use": {"tools": ["edit"], "paths": ["src/**", "*.sql"]},
            "post_tool_use": {"paths": ["*.sql", "db/**"]},
        },
    )

    rule = hook.to_advisory_rule()

    assert rule is not None
    assert (rule.frontmatter.scope, rule.frontmatter.globs) == (
        "scoped",
        ["src/**", "*.sql", "db/**"],
    )

"""What an overlay may not change when it overrides a hook (H14, specs/prK-lifecycle-hooks.md §A.6).

Overlays may only add: driven through ``merge_hook_layers``, an overlay's
same-id definition replaces the earlier one but may not swap a builtin, disable
a default-tier hook, drop an event, a tool class, ``deny`` or ``ask``, weaken
``on_error``, demote the tier or clear ``mandatory``. Each refusal is an H14
``HookViolation`` naming the overlay, the hook id and what was taken away.
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.hooks.resolution.merge import HookViolation, merge_hook_layers
from tests.hook_samples import sample_hook

ENGINE = "coding_agent_playbook"
OVERLAY = "acme_rules"


def _messages(violations: list[HookViolation]) -> list[str]:
    return [violation.message for violation in violations]


def test_overlay_frontmatter_replaces_by_id() -> None:
    engine = sample_hook(ENGINE, name="Engine name", tier="opt-in")
    overlay = sample_hook(OVERLAY, name="Overlay name", tier="default", mandatory=True)

    merged, violations = merge_hook_layers([engine, overlay])

    assert violations == []
    assert merged.source_package == OVERLAY
    assert merged.frontmatter.name == "Overlay name"
    assert merged.frontmatter.mandatory is True


def test_overlay_cannot_swap_builtin() -> None:
    engine = sample_hook(ENGINE)
    overlay = sample_hook(OVERLAY, handler={"builtin": "guard_other"})

    _, violations = merge_hook_layers([engine, overlay])

    assert _messages(violations) == [
        "overlay 'acme_rules' override of 'guard-x' replaces builtin 'guard_x' "
        "with 'guard_other' on event 'pre_tool_use'"
    ]
    assert violations[0].rule == "H14"
    assert violations[0].hook_id == "guard-x"


def test_overlay_cannot_swap_builtin_for_an_external_command() -> None:
    engine = sample_hook(ENGINE)
    overlay = sample_hook(OVERLAY, handler={"command": "python", "script": "scripts/x.py"})

    _, violations = merge_hook_layers([engine, overlay])

    assert _messages(violations) == [
        "overlay 'acme_rules' override of 'guard-x' replaces builtin 'guard_x' "
        "with an external command on event 'pre_tool_use'"
    ]


def test_overlay_cannot_disable_default_tiersample_hook() -> None:
    _, violations = merge_hook_layers([sample_hook(ENGINE), sample_hook(OVERLAY, enabled=False)])

    assert _messages(violations) == [
        "overlay 'acme_rules' override of 'guard-x' sets enabled: false on a default-tier hook"
    ]


def test_overlay_may_disable_an_opt_insample_hook() -> None:
    engine = sample_hook(ENGINE, tier="opt-in")

    _, violations = merge_hook_layers([engine, sample_hook(OVERLAY, tier="opt-in", enabled=False)])

    assert violations == []


_TOOLS = {"pre_tool_use": {"tools": ["shell", "edit"]}}


@pytest.mark.parametrize(
    ("earlier", "later", "problem"),
    [
        (
            {"events": ["pre_tool_use", "stop"]},
            {"events": ["pre_tool_use"]},
            "drops event 'stop'",
        ),
        (
            {"matcher": _TOOLS},
            {"matcher": {"pre_tool_use": {"tools": ["shell"]}}},
            "drops tool class 'edit' on event 'pre_tool_use'",
        ),
        (
            {"decisions": ["deny", "ask", "none"]},
            {"decisions": ["ask", "none"]},
            "drops decision 'deny'",
        ),
        (
            {"decisions": ["deny", "ask", "none"]},
            {"decisions": ["deny", "none"]},
            "drops decision 'ask'",
        ),
    ],
)
def test_overlay_cannot_drop_event_tool_class_deny_or_ask(
    earlier: dict[str, Any], later: dict[str, Any], problem: str
) -> None:
    _, violations = merge_hook_layers(
        [sample_hook(ENGINE, **earlier), sample_hook(OVERLAY, **later)]
    )

    assert _messages(violations) == [f"overlay 'acme_rules' override of 'guard-x' {problem}"]


def test_narrowing_a_match_all_matcher_drops_every_other_tool_class() -> None:
    later = sample_hook(OVERLAY, matcher={"pre_tool_use": {"tools": ["shell", "web"]}})

    _, violations = merge_hook_layers([sample_hook(ENGINE), later])

    dropped = ["edit", "write", "notebook_edit", "read", "search", "subagent", "mcp"]
    assert _messages(violations) == [
        f"overlay 'acme_rules' override of 'guard-x' drops tool class {tool!r} "
        "on event 'pre_tool_use'"
        for tool in dropped
    ]


def test_a_name_only_matcher_covers_no_tool_class() -> None:
    # tools: [] with tool_names set matches by name only, so narrowing it drops no class.
    engine = sample_hook(ENGINE, matcher={"pre_tool_use": {"tool_names": ["mcp__github__.*"]}})
    later = sample_hook(OVERLAY, matcher={"pre_tool_use": {"tools": ["mcp"]}})

    assert merge_hook_layers([engine, later])[1] == []


def test_overlay_may_widen_tool_classes_and_decisions() -> None:
    engine = sample_hook(ENGINE, matcher=_TOOLS, decisions=["deny", "none"])
    overlay = sample_hook(
        OVERLAY,
        matcher={"pre_tool_use": {"tools": ["shell", "edit", "write"]}},
        decisions=["deny", "ask", "context", "none"],
        events=["pre_tool_use", "post_tool_use"],
    )

    _, violations = merge_hook_layers([engine, overlay])

    assert violations == []


@pytest.mark.parametrize(("earlier", "later"), [("deny", "ask"), ("ask", "open"), ("deny", "open")])
def test_overlay_cannot_weaken_on_error(earlier: str, later: str) -> None:
    hooks = [sample_hook(ENGINE, on_error=earlier), sample_hook(OVERLAY, on_error=later)]

    _, violations = merge_hook_layers(hooks)

    assert _messages(violations) == [
        f"overlay 'acme_rules' override of 'guard-x' weakens on_error {earlier!r} to {later!r}"
    ]


def test_overlay_may_strengthen_on_error() -> None:
    hooks = [sample_hook(ENGINE, on_error="open"), sample_hook(OVERLAY, on_error="deny")]

    assert merge_hook_layers(hooks)[1] == []


@pytest.mark.parametrize(
    ("earlier", "later", "demoted"),
    [
        ("opt-in", "default", False),
        ("overlay", "default", False),
        ("default", "default", False),
        ("opt-in", "overlay", False),
        ("default", "opt-in", True),
        ("default", "overlay", True),
    ],
)
def test_overlay_may_promote_but_not_demote_tier(earlier: str, later: str, demoted: bool) -> None:
    _, violations = merge_hook_layers(
        [sample_hook(ENGINE, tier=earlier), sample_hook(OVERLAY, tier=later)]
    )

    expected = [f"overlay 'acme_rules' override of 'guard-x' demotes tier 'default' to {later!r}"]
    assert _messages(violations) == (expected if demoted else [])


def test_overlay_cannot_clear_mandatory() -> None:
    first = sample_hook("acme_base", mandatory=True)

    _, violations = merge_hook_layers([first, sample_hook(OVERLAY, mandatory=False)])

    assert _messages(violations) == [
        "overlay 'acme_rules' override of 'guard-x' clears mandatory set by overlay 'acme_base'"
    ]


def test_overlay_violations_compare_against_the_merged_earlier_layers() -> None:
    engine = sample_hook(ENGINE, decisions=["deny", "none"])
    first = sample_hook("acme_base", decisions=["deny", "ask", "none"])
    second = sample_hook(OVERLAY, decisions=["deny", "none"])

    _, violations = merge_hook_layers([engine, first, second])

    assert _messages(violations) == [
        "overlay 'acme_rules' override of 'guard-x' drops decision 'ask'"
    ]

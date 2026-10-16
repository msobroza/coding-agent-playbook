"""The per-adapter hook label set of ``playbook check`` (specs/prK-lifecycle-hooks.md §A.8, §C.5.1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_policy import HOOK_SUPPORT, adapter_label
from tests.hook_samples import resolved_hook

CLAUDE = HOOK_SUPPORT["claude_code"]
OPENCODE = HOOK_SUPPORT["opencode"]


def test_enforced_when_every_declared_event_is_native() -> None:
    hook = resolved_hook(events=("pre_tool_use", "stop"), supports=("claude_code",))

    assert adapter_label(hook, "claude_code", CLAUDE) == "enforced"


def test_degraded_when_a_reachable_event_is_evidence_only() -> None:
    hook = resolved_hook(events=("stop",), supports=("claude_code", "opencode"))

    assert adapter_label(hook, "opencode", OPENCODE) == "degraded"
    assert adapter_label(hook, "claude_code", CLAUDE) == "enforced"


def test_degraded_when_a_declared_event_is_unreachable() -> None:
    """OQ-43: one reachable event is enough to register; the rest is a weaker cell."""
    hook = resolved_hook(events=("pre_tool_use", "session_end"), supports=("opencode",))

    assert adapter_label(hook, "opencode", OPENCODE) == "degraded"


@pytest.mark.parametrize("tool_class", ["mcp", "notebook_edit"])
def test_degraded_on_a_tool_class_the_harness_lacks(tool_class: str) -> None:
    hook = resolved_hook(
        matcher={"pre_tool_use": {"tools": [tool_class, "shell"]}},
        supports=("claude_code", "opencode"),
    )

    assert adapter_label(hook, "opencode", OPENCODE) == "degraded"
    assert adapter_label(hook, "claude_code", CLAUDE) == "enforced"


def test_advisory_where_the_hook_is_not_rendered_natively() -> None:
    hook = resolved_hook(supports=("claude_code",))

    assert adapter_label(hook, "continue", {}) == "advisory"
    assert adapter_label(hook, "agents_md", {}) == "advisory"
    assert adapter_label(hook, "opencode", OPENCODE) == "advisory"


def test_an_adapter_without_hook_support_never_enforces() -> None:
    """The adapter class's ``hook_support`` decides: OpenCode before K4 renders nothing."""
    hook = resolved_hook(supports=("opencode",))

    assert adapter_label(hook, "opencode", {}) == "advisory"


def test_dash_when_nothing_is_rendered_for_the_adapter() -> None:
    hook = resolved_hook(body="", supports=("claude_code",))

    assert hook.advisory is None
    assert adapter_label(hook, "agents_md", {}) == "—"
    assert adapter_label(hook, "claude_code", CLAUDE) == "enforced"


def test_no_reachable_event_falls_back_to_the_advisory_label() -> None:
    hook = resolved_hook(events=("subagent_stop",), supports=("opencode",))

    assert adapter_label(hook, "opencode", OPENCODE) == "advisory"

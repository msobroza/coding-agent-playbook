"""The two hook formats of ``render_for`` (specs/prK-lifecycle-hooks.md §C.4.1).

``hook_advisory`` is the markdown every advisory target shares: a ``###``
heading, the rendered body, and one **static** enforcement line computed from
the declared ``supports`` and §C.5 event reachability, never from the adapters
a repo enables. ``hook_claude_settings`` is the debug JSON projection of the
hook's Claude registrations. Kept apart from ``test_renderer.py`` (file budget).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.hook_policy import advisory_text, enforcement_line
from coding_agent_playbook.renderer import BUILTIN_FORMATS, render_for
from tests.hook_samples import hook_frontmatter

_SOURCE = Path("playbook/hooks/guard-x/HOOK.md")
_GUIDANCE = "Everywhere else this is guidance: apply it yourself."


def _advisory(body: str = "Never hand-edit generated files.\n", **frontmatter: Any) -> str:
    mapping = hook_frontmatter(**frontmatter).to_mapping()
    return render_for(_SOURCE, body, "hook_advisory", frontmatter=mapping)


def test_hook_formats_are_builtin() -> None:
    assert {"hook_advisory", "hook_claude_settings"} <= BUILTIN_FORMATS


def test_hook_advisory_shape() -> None:
    out = _advisory("\nNever hand-edit generated files.  \n\n", name="Guard generated outputs")

    assert out == (
        "### Guard generated outputs\n\n"
        "Never hand-edit generated files.\n\n"
        f"*Enforced by lifecycle hooks on: Claude Code. {_GUIDANCE}*\n"
    )


@pytest.mark.parametrize(
    ("events", "supports", "line"),
    [
        (
            ["pre_tool_use"],
            ["opencode", "claude_code"],
            f"*Enforced by lifecycle hooks on: Claude Code, OpenCode. {_GUIDANCE}*",
        ),
        (["stop"], ["opencode"], f"*Checked (not blocked) on: OpenCode. {_GUIDANCE}*"),
        (["subagent_stop"], ["opencode"], "*Not enforced automatically; apply it yourself.*"),
        (
            ["stop"],
            ["claude_code", "opencode"],
            "*Enforced by lifecycle hooks on: Claude Code; checked (not blocked) on: OpenCode. "
            f"{_GUIDANCE}*",
        ),
    ],
    ids=["enforced", "checked_not_blocked", "not_enforced", "enforced_and_checked"],
)
def test_hook_advisory_enforcement_line_variants(
    events: list[str], supports: list[str], line: str
) -> None:
    out = _advisory(events=events, supports=supports)

    assert out.endswith(f"\n\n{line}\n")
    assert enforcement_line(events, supports) == line


def test_enforcement_line_counts_an_adapter_with_one_native_event_as_enforcing() -> None:
    # OpenCode stop is evidence-only, but its pre_tool_use half is enforced.
    assert enforcement_line(["pre_tool_use", "stop"], ["opencode"]) == (
        f"*Enforced by lifecycle hooks on: OpenCode. {_GUIDANCE}*"
    )


def test_enforcement_line_ignores_unknown_adapters_and_events() -> None:
    assert enforcement_line(["PreToolUse"], ["cursor", "claude_code"]) == (
        "*Not enforced automatically; apply it yourself.*"
    )


def test_advisory_text_is_the_block_without_its_heading() -> None:
    text = advisory_text("Body.\n", ["pre_tool_use"], ["claude_code"])

    assert _advisory("Body.\n") == f"### Guard X\n\n{text}"


def test_hook_claude_settings_projection() -> None:
    mapping = hook_frontmatter(
        events=["pre_tool_use", "stop"],
        matcher={"pre_tool_use": {"tools": ["shell", "read"]}},
        timeout=2.5,
    ).to_mapping()

    out = render_for(_SOURCE, "ignored body\n", "hook_claude_settings", frontmatter=mapping)
    projection = json.loads(out)

    assert out.endswith("}\n")
    assert list(projection) == ["hooks"]
    assert list(projection["hooks"]) == ["SessionStart", "PreToolUse", "Stop"]
    pre = projection["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "Bash|PowerShell|Read"
    assert pre["hooks"][0]["timeout"] == 5
    assert pre["hooks"][0]["command"].endswith("dispatch pre_tool_use --harness claude_code")
    assert projection["hooks"]["Stop"][0]["hooks"][0]["statusMessage"]


def test_hook_claude_settings_rejects_a_malformed_frontmatter() -> None:
    with pytest.raises(ValueError, match="timeout"):
        render_for(
            _SOURCE,
            "",
            "hook_claude_settings",
            frontmatter={**hook_frontmatter().to_mapping(), "timeout": "2s"},
        )

"""control-plane-guard's pure verdict seams (specs/prK-hook-pack.md §E.1).

The handler tests drive whole edits through ``simulate``; these pin the edge
cases of each pure function directly: JSONC stripping, the settings and MCP
diffs, the ``[metrics]`` direction table, the local-config policy keys, the
pre-commit id baseline, ``hooks:`` frontmatter blocks and the Bash rows.
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_json import (
    load_json_object,
    mcp_verdict,
    opencode_verdict,
    settings_verdict,
    strip_jsonc,
)
from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_shell import command_verdict
from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_text import (
    hooks_block,
    precommit_verdict,
)
from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_toml import (
    local_policy_overrides,
    metrics_loosened,
    toml_verdict,
)
from coding_agent_playbook.hook_runtime.shell.parse import parse_shell
from coding_agent_playbook.lockfile.canonical_json import element_sha256

DENY, ASK, NONE = Decision.DENY, Decision.ASK, Decision.NONE
_GROUP = {"matcher": "Bash", "hooks": [{"type": "command", "command": "launch.sh pre"}]}
_MANAGED = [("json:/hooks/PreToolUse", element_sha256(_GROUP))]


def test_strip_jsonc_keeps_strings_and_drops_comments_and_trailing_commas() -> None:
    text = '{\n  "url": "http://x/*y*/", // tail\n  /* block */ "q": "a\\"//b",\n  "l": [1, 2,],\n}'

    assert load_json_object(text, jsonc=True) == {"url": "http://x/*y*/", "q": 'a"//b', "l": [1, 2]}
    assert strip_jsonc('"a,]"') == '"a,]"'


@pytest.mark.parametrize("text", ["[1, 2]", "{broken", "", "null"])
def test_non_object_or_broken_json_is_none(text: str) -> None:
    assert load_json_object(text) is None


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ({"hooks": {"PreToolUse": [_GROUP]}}, {"hooks": {"PreToolUse": [{}, _GROUP]}}, NONE),
        ({"hooks": {"PreToolUse": [_GROUP]}}, {"hooks": {}}, DENY),
        ({}, {"hooks": {}}, NONE),  # never present: nothing managed to remove
        ({"env": {"A": "1"}}, {}, DENY),
        ({}, {"enableAllProjectMcpServers": True}, DENY),
        ({"disableAllHooks": True}, {"disableAllHooks": False}, NONE),
        (
            {"permissions": {"defaultMode": "plan"}},
            {"permissions": {"defaultMode": "default"}},
            NONE,
        ),
        ({}, {"enabledPlugins": {"p@m": True}}, ASK),
        ({"enabledPlugins": {"p@m": False}}, {"enabledPlugins": {"p@m": False}}, NONE),
        ({}, {"extraKnownMarketplaces": {"m": {}}}, ASK),
        ({}, {"enabledMcpjsonServers": ["docs"]}, ASK),
        ({"disabledMcpjsonServers": ["docs"]}, {"disabledMcpjsonServers": []}, ASK),
        ({"permissions": {"allow": ["a", "b"]}}, {"permissions": {"allow": ["a"]}}, NONE),
    ],
)
def test_settings_verdict_rows(before: Any, after: Any, expected: Decision) -> None:
    assert settings_verdict(before, after, _MANAGED) is expected


def test_mcp_and_opencode_enabling_a_server_asks() -> None:
    off: dict[str, Any] = {"mcpServers": {"x": {"disabled": True}}}
    on: dict[str, Any] = {"mcpServers": {"x": {}}}
    oc_off, oc_on = {"mcp": {"x": {"enabled": False}}}, {"mcp": {"x": {"enabled": True}}}

    assert mcp_verdict(off, on) is ASK
    assert mcp_verdict(on, off) is NONE
    assert opencode_verdict(oc_off, oc_on) is ASK
    assert opencode_verdict({"plugin": ["a", "b"]}, {"plugin": ["a"]}) is NONE


@pytest.mark.parametrize(
    ("before", "after", "loosened"),
    [
        ({"mode": "regression"}, {"mode": "both"}, False),
        ({"mode": "both"}, {"mode": "regression"}, True),
        ({"strict": False}, {"strict": True}, False),
        (
            {"regression": {"cov": {"max_worsening": 2}}},
            {"regression": {"cov": {"max_worsening": 1}}},
            False,
        ),
        ({}, {"regression": {"cov": {"max_worsening": 0}}}, False),
        ({"thresholds": {"cc": {"fail": 20}}}, {"thresholds": {"cc": {"fail": 15}}}, True),
        ({"exclude": ["a", "b"]}, {"exclude": ["a"]}, False),
        ({"exclude": ["a"]}, {"exclude": ["a", "b"]}, True),
        ({"select": ["cc"]}, {"select": ["cc", "mi"]}, False),
        ({"select": ["cc", "mi"]}, {"select": ["cc"]}, True),
        ({"test_cmd": ["pytest"]}, {"test_cmd": ["true"]}, True),
        ({}, {}, False),
        ({}, {"strict": True}, False),
        ({"strict": True}, 5, True),  # a malformed table: any change is unknown
    ],
)
def test_metrics_direction_table(before: Any, after: Any, loosened: bool) -> None:
    assert metrics_loosened(before, after) is loosened


def test_local_toml_any_policy_key_change_denies() -> None:
    assert toml_verdict(None, "[metrics]\nstrict = true\n", local=True) is DENY
    assert toml_verdict(None, '[project]\nname = "x"\n', local=True) is NONE
    assert toml_verdict("[broken", "x = 1\n", local=False) is ASK


def test_local_policy_overrides_lists_set_policy_keys() -> None:
    doc = {"hooks": {}, "engine": {"version": "1"}, "links": {"other": 1}, "project": {}}

    assert local_policy_overrides(doc) == ["hooks", "engine.version"]


def test_precommit_baseline_stands_in_for_an_absent_file() -> None:
    assert precommit_verdict(None, "repos: []\n", ["playbook-sync-check"]) is DENY
    assert precommit_verdict(None, "- id: playbook-sync-check\n", ["playbook-sync-check"]) is NONE
    assert precommit_verdict("- id: ruff\n", "repos: []\n", ["playbook-x"]) is NONE


@pytest.mark.parametrize(
    ("text", "block"),
    [
        ("---\nhooks:\n- matcher: x\nname: y\n---\n", "hooks:\n- matcher: x"),
        ('---\n"hooks": {}\n---\n', '"hooks": {}'),
        ("hooks: {}\n", None),  # no frontmatter
        ("---\nname: x\n---\nhooks: {}\n", None),  # body, not frontmatter
    ],
)
def test_hooks_block(text: str, block: str | None) -> None:
    assert hooks_block(text) == block


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat answers | playbook --repo-root . sync", (DENY, "sync_stdin")),
        ("yes | playbook check", None),
        ("claude mcp add-json docs '{}'", (ASK, "mcp_add")),
        ("script -q out.log ls", None),
    ],
)
def test_command_rows(command: str, expected: tuple[Decision, str] | None) -> None:
    segments = parse_shell(command, "posix", "/r").segments
    piped = [False, *(s.pipes_to_next for s in segments[:-1])]

    found = [command_verdict(s, piped=p) for s, p in zip(segments, piped, strict=True)]

    assert [v for v in found if v is not None] == ([expected] if expected else [])

"""Scoped drift of managed ``.claude/settings.json`` elements (specs/prK-lifecycle-hooks.md §C.2.6)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.adapters._settings_drift import (
    managed_entry_drift,
    settings_document,
    stray_launcher_edited,
)
from coding_agent_playbook.adapters.claude_settings import (
    CLAUDE_SETTINGS_PATH,
    SettingsMergeError,
    parse_settings,
    scoped_lock_entry,
)
from coding_agent_playbook.lockfile import DriftItem, ScopedUnreadable

_LAUNCH = 'sh "$D/.claude/hooks/playbook/launch.sh" dispatch stop --harness claude_code'
_GROUP = {"hooks": [{"type": "command", "command": _LAUNCH, "timeout": 5}]}
_STOP = scoped_lock_entry(
    CLAUDE_SETTINGS_PATH, "/hooks/Stop", _GROUP, artifact_id="registration:stop"
)
_ALLOW = scoped_lock_entry(
    CLAUDE_SETTINGS_PATH,
    "/permissions/allow",
    "Bash(playbook check)",
    artifact_id="permission:allow:Bash(playbook check)",
)


def test_a_present_element_is_clean_whatever_its_key_order() -> None:
    reordered = {"hooks": [{"timeout": 5, "command": _LAUNCH, "type": "command"}]}
    doc = {"model": "x", "hooks": {"Stop": [{"hooks": []}, reordered]}}

    assert managed_entry_drift(doc, [_STOP]) == []


def test_a_hand_edited_group_is_edited() -> None:
    edited = {"hooks": [{"type": "command", "command": _LAUNCH, "timeout": 1}]}

    drift = managed_entry_drift({"hooks": {"Stop": [edited]}}, [_STOP])

    assert drift == [DriftItem(CLAUDE_SETTINGS_PATH, "managed_edited", pointer="/hooks/Stop")]
    assert drift[0].line() == "managed entry edited: .claude/settings.json#/hooks/Stop"


@pytest.mark.parametrize(
    "doc",
    [
        {},
        {"hooks": {}},
        {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}},
        {"hooks": {"Stop": "not an array"}},
    ],
)
def test_a_deleted_group_is_missing(doc: object) -> None:
    drift = managed_entry_drift(doc, [_STOP])

    assert drift == [DriftItem(CLAUDE_SETTINGS_PATH, "managed_missing", pointer="/hooks/Stop")]
    assert drift[0].line() == "managed entry missing: .claude/settings.json#/hooks/Stop"


def test_managed_strings_are_missing_never_edited() -> None:
    doc = {"permissions": {"allow": ["Bash(git status)"]}}

    missing = DriftItem(CLAUDE_SETTINGS_PATH, "managed_missing", pointer="/permissions/allow")
    assert managed_entry_drift(doc, [_ALLOW]) == [missing]
    assert managed_entry_drift({"permissions": {"allow": ["Bash(playbook check)"]}}, [_ALLOW]) == []


def test_whole_file_entries_are_not_judged_here() -> None:
    whole = scoped_lock_entry("AGENTS.md", "", "x", artifact_id="")
    whole.scope = ""

    assert managed_entry_drift({}, [whole]) == []


def test_parse_settings_is_strict_and_reads_absence_as_empty() -> None:
    assert parse_settings(None) == {}
    assert parse_settings("  \n") == {}
    assert parse_settings('{"a": 1}') == {"a": 1}
    with pytest.raises(SettingsMergeError) as caught:
        parse_settings('{"a": 1, "a": 2}')
    assert str(caught.value).startswith(".claude/settings.json:1:")


def test_settings_document_reports_what_claude_rejects_as_unreadable() -> None:
    assert settings_document(None, CLAUDE_SETTINGS_PATH) == {}
    with pytest.raises(ScopedUnreadable) as caught:
        settings_document(b'{"a": 1, "a": 2}', CLAUDE_SETTINGS_PATH)
    assert caught.value.detail.startswith("line 1, col ")


def test_stray_launcher_edited_only_for_hook_arrays() -> None:
    launcher_only = _GROUP

    assert stray_launcher_edited("/hooks/Stop", [launcher_only], ["new"], frozenset({"old"}))
    assert not stray_launcher_edited("/hooks/Stop", [launcher_only], ["old"], frozenset({"old"}))
    assert not stray_launcher_edited("/permissions/allow", [launcher_only], ["new"], frozenset())

"""Claude Code native hook emission (specs/prK-lifecycle-hooks.md §C.1.2, §C.2, §C.4.2).

The adapter merges one managed group per event into ``.claude/settings.json``
(read from the input root, written to the output root, as ``sync --check``
does with its empty scratch dir), writes the committed launcher, and degrades
only the hooks it cannot enforce into ``CLAUDE.md``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters._claude_hooks import CLAUDE_HEARTBEAT_LINE, REMEDIATION_ALLOW
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.claude_settings import CLAUDE_SETTINGS_PATH, SettingsMergeError
from coding_agent_playbook.hook_policy import HOOK_SUPPORT
from coding_agent_playbook.hook_registrations import (
    LAUNCHER_PATH,
    claude_command,
    registration_timeout_s,
    render_claude_launcher,
)
from coding_agent_playbook.hooks_config import HooksConfig
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.types import Rule, RuleFrontmatter
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook

_ON = HooksConfig(enabled=True)
_BRIEFING = "session-start-playbook-briefing"


def _rule(body: str = "Use type hints.\n") -> Rule:
    fm = RuleFrontmatter(id="typing", name="Typing", description="d", scope="always")
    return Rule(fm, body, body, False, None, "test")


def _sync(
    out: Path,
    hooks: Sequence[ResolvedHook] = (),
    *,
    source: Path | None = None,
    prior: Lockfile | None = None,
    cfg: HooksConfig | None = _ON,
    rules: Sequence[Rule] = (),
) -> tuple[ClaudeCodeAdapter, list[Path]]:
    """One adapter pass as sync drives it: begin_sync, rules, hooks, finalize."""
    adapter = ClaudeCodeAdapter()
    adapter.begin_sync(source or out, prior, hooks_config=cfg)
    written = [path for rule in rules for path in adapter.write_rule(rule, out)]
    written += [path for hook in hooks for path in adapter.write_hook(hook, out)]
    return adapter, written + adapter.finalize(out)


def _lock(adapter: ClaudeCodeAdapter) -> Lockfile:
    return Lockfile(2, "0", "", entries=adapter.managed_lock_entries())


def _settings(root: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((root / CLAUDE_SETTINGS_PATH).read_text("utf-8"))
    return loaded


def test_class_declares_hook_support_shared_settings_and_the_launcher_dir() -> None:
    assert ClaudeCodeAdapter.hook_support == HOOK_SUPPORT["claude_code"]
    assert ClaudeCodeAdapter.shared_outputs == (CLAUDE_SETTINGS_PATH,)
    assert ".claude/hooks/playbook/" in ClaudeCodeAdapter.output_locations
    # Co-owned with the user: never inside a location the leftover policy may delete in.
    assert not any(
        CLAUDE_SETTINGS_PATH.startswith(loc) or loc == CLAUDE_SETTINGS_PATH
        for loc in ClaudeCodeAdapter.output_locations
    )


def test_creates_settings_when_absent(tmp_path: Path) -> None:
    _, written = _sync(tmp_path, [resolved_hook()])

    settings = tmp_path / CLAUDE_SETTINGS_PATH
    assert settings in written
    text = settings.read_text("utf-8")
    assert text.startswith('{\n  "hooks": {\n') and text.endswith("}\n")
    hooks = _settings(tmp_path)["hooks"]
    assert list(hooks) == ["SessionStart", "PreToolUse"]
    handler = hooks["PreToolUse"][0]["hooks"][0]
    assert hooks["PreToolUse"][0]["matcher"] == "*"
    assert handler == {
        "type": "command",
        "command": claude_command("pre_tool_use"),
        "timeout": registration_timeout_s(2000),
    }


def test_hooks_only_repo_registers_without_rules(tmp_path: Path) -> None:
    _, written = _sync(tmp_path, [resolved_hook()])

    assert sorted(written) == sorted([tmp_path / CLAUDE_SETTINGS_PATH, tmp_path / LAUNCHER_PATH])
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_second_sync_noop_returns_no_settings_path(tmp_path: Path) -> None:
    first, _ = _sync(tmp_path, [resolved_hook()])
    before = (tmp_path / CLAUDE_SETTINGS_PATH).read_bytes()

    second, written = _sync(tmp_path, [resolved_hook()], prior=_lock(first))

    assert tmp_path / CLAUDE_SETTINGS_PATH not in written
    assert (tmp_path / CLAUDE_SETTINGS_PATH).read_bytes() == before
    # The sync summary's counts (§C.1.5) come from the merge each pass ran.
    assert first.settings_merge is not None and second.settings_merge is not None
    assert (first.settings_merge.updated, first.settings_merge.removed) == (2, 0)
    assert (second.settings_merge.changed, second.settings_merge.updated) == (False, 0)
    assert ClaudeCodeAdapter().settings_merge is None


def test_disabling_last_hook_strips_groups_and_never_unlinks(tmp_path: Path) -> None:
    settings = tmp_path / CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True)
    settings.write_text('{\n  "model": "opus"\n}\n', encoding="utf-8")
    first, _ = _sync(tmp_path, [resolved_hook()])

    _, written = _sync(tmp_path, [], prior=_lock(first))

    assert settings in written
    assert settings.read_text("utf-8") == '{\n  "model": "opus"\n}\n'


def test_disabling_hooks_leaves_an_empty_object_not_a_deleted_file(tmp_path: Path) -> None:
    first, _ = _sync(tmp_path, [resolved_hook()])

    _sync(tmp_path, [], prior=_lock(first), cfg=HooksConfig(enabled=False))

    assert _settings(tmp_path) == {}


def test_merges_base_from_input_root_into_output_root(tmp_path: Path) -> None:
    source, out = tmp_path / "repo", tmp_path / "scratch"
    base = source / CLAUDE_SETTINGS_PATH
    base.parent.mkdir(parents=True)
    base.write_text('{\n    "env": {"A": "1"}\n}\n', encoding="utf-8")
    out.mkdir()

    _, written = _sync(out, [resolved_hook()], source=source)

    assert written and all(path.is_relative_to(out) for path in written)
    assert base.read_text("utf-8") == '{\n    "env": {"A": "1"}\n}\n'
    merged = _settings(out)
    assert merged["env"] == {"A": "1"}
    assert "PreToolUse" in merged["hooks"]


_USER_TEXT = """\
{
    "permissions": {"deny": ["Read(./.env)"]},
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "~/rtk.sh"}]}
        ]
    }
}
"""


def test_user_keys_and_user_groups_byte_stable(tmp_path: Path) -> None:
    settings = tmp_path / CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True)
    settings.write_text(_USER_TEXT, encoding="utf-8")

    first, _ = _sync(tmp_path, [resolved_hook()])
    merged = settings.read_text("utf-8")
    second, written = _sync(tmp_path, [resolved_hook()], prior=_lock(first))

    assert '    "permissions": {"deny": ["Read(./.env)"]},\n' in merged
    assert '{"matcher": "Bash", "hooks": [{"type": "command", "command": "~/rtk.sh"}]}' in merged
    pre_tool_use = _settings(tmp_path)["hooks"]["PreToolUse"]
    assert pre_tool_use[0]["matcher"] == "Bash"  # the user's group keeps its index
    assert settings not in written
    assert settings.read_text("utf-8") == merged
    _, off = _sync(tmp_path, [], prior=_lock(second))
    assert settings in off
    assert json.loads(settings.read_text("utf-8")) == json.loads(_USER_TEXT)


def test_managed_lock_entries_include_noop_groups(tmp_path: Path) -> None:
    first, _ = _sync(tmp_path, [resolved_hook()])

    second, written = _sync(tmp_path, [resolved_hook()], prior=_lock(first))

    assert tmp_path / CLAUDE_SETTINGS_PATH not in written
    entries = second.managed_lock_entries()
    assert [(e.scope, e.artifact_id) for e in entries] == [
        ("json:/hooks/SessionStart", "registration:session_start"),
        ("json:/hooks/PreToolUse", "registration:pre_tool_use"),
    ]
    assert {(e.path, e.kind, e.adapter) for e in entries} == {
        (CLAUDE_SETTINGS_PATH, "runtime", "claude_code")
    }
    assert entries == first.managed_lock_entries()


def test_registration_timeouts_follow_every_hooks_deadline(tmp_path: Path) -> None:
    """guard_config.json holds one deadline per event for all harnesses (§D.4)."""
    claude = resolved_hook("guard-a", timeout=2.0)
    elsewhere = resolved_hook("guard-b", timeout=3.0, supports=("opencode",))

    _sync(tmp_path, [claude, elsewhere])

    handler = _settings(tmp_path)["hooks"]["PreToolUse"][0]["hooks"][0]
    assert handler["timeout"] == registration_timeout_s(5000)


def test_launcher_written_with_line1_sentinel_and_cleaned_when_stale(tmp_path: Path) -> None:
    first, _ = _sync(tmp_path, [resolved_hook()])
    launcher = tmp_path / LAUNCHER_PATH
    assert launcher.read_bytes() == render_claude_launcher().encode("utf-8")
    assert launcher.read_text("utf-8").splitlines()[0] == sentinel_line("hash")

    adapter, written = _sync(tmp_path, [], prior=_lock(first))

    assert launcher not in written
    assert adapter.stale_outputs({p.resolve() for p in written}, tmp_path) == [launcher]
    adapter.cleanup_stale({p.resolve() for p in written}, tmp_path)
    assert not launcher.exists()
    assert (tmp_path / CLAUDE_SETTINGS_PATH).is_file()


def test_settings_json_never_reported_stale(tmp_path: Path) -> None:
    _sync(tmp_path, [resolved_hook()])

    adapter = ClaudeCodeAdapter()

    assert tmp_path / CLAUDE_SETTINGS_PATH not in adapter.stale_outputs(set(), tmp_path)


def test_unenforced_hook_advisory_goes_to_claude_md(tmp_path: Path) -> None:
    elsewhere = resolved_hook("guard-b", name="Guard B", supports=("opencode",))

    _, written = _sync(tmp_path, [elsewhere, resolved_hook()])

    claude_md = (tmp_path / ".claude" / "CLAUDE.md").read_text("utf-8")
    assert tmp_path / ".claude" / "CLAUDE.md" in written
    assert (
        "## Guardrail: Guard B\n\nAdvice.\n\n*Enforced by lifecycle hooks on: OpenCode."
        in claude_md
    )
    assert "Guard X" not in claude_md  # enforced natively: nothing to advise


def test_heartbeat_line_only_with_briefing_hook(tmp_path: Path) -> None:
    briefing = resolved_hook(_BRIEFING, events=("session_start",))
    _sync(tmp_path / "plain", [resolved_hook()])
    _sync(tmp_path / "solo", [briefing])
    _sync(tmp_path / "rules", [briefing], rules=[_rule()])

    assert not (tmp_path / "plain" / ".claude" / "CLAUDE.md").exists()
    solo = (tmp_path / "solo" / ".claude" / "CLAUDE.md").read_text("utf-8")
    assert solo.endswith(f"generated by coding-agent-playbook.\n\n{CLAUDE_HEARTBEAT_LINE}\n")
    with_rules = (tmp_path / "rules" / ".claude" / "CLAUDE.md").read_text("utf-8")
    assert with_rules.endswith(f"Use type hints.\n\n---\n\n{CLAUDE_HEARTBEAT_LINE}\n")
    assert with_rules.count(CLAUDE_HEARTBEAT_LINE) == 1


def test_heartbeat_needs_the_briefing_enforced_on_claude(tmp_path: Path) -> None:
    briefing = resolved_hook(_BRIEFING, events=("session_start",), supports=("opencode",))

    _sync(tmp_path, [briefing])

    assert CLAUDE_HEARTBEAT_LINE not in (tmp_path / ".claude" / "CLAUDE.md").read_text("utf-8")


@pytest.mark.parametrize("cfg", [None, _ON, HooksConfig(enabled=False)])
def test_rules_only_output_byte_identical(tmp_path: Path, cfg: HooksConfig | None) -> None:
    plain = ClaudeCodeAdapter()
    plain.write_rule(_rule(), tmp_path / "plain")
    expected = plain.finalize(tmp_path / "plain")
    out = tmp_path / "out"
    broken = out / CLAUDE_SETTINGS_PATH
    broken.parent.mkdir(parents=True)
    broken.write_text("{ // not JSON\n", encoding="utf-8")

    _, written = _sync(out, rules=[_rule()], cfg=cfg)

    assert written == [out / ".claude" / "CLAUDE.md"]
    assert written[0].read_bytes() == expected[0].read_bytes()
    assert broken.read_text("utf-8") == "{ // not JSON\n"  # never read, never rewritten
    assert not (out / LAUNCHER_PATH).exists()


def test_remediation_allow_opt_in_only_fixed_list(tmp_path: Path) -> None:
    opted = HooksConfig(enabled=True, render_remediation_allow=True)
    settings = tmp_path / "on" / CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True)
    settings.write_text('{"permissions": {"allow": ["Bash(git status)"]}}\n', encoding="utf-8")

    adapter, _ = _sync(tmp_path / "on", [resolved_hook()], cfg=opted)
    _sync(tmp_path / "off", [resolved_hook()])

    allow = _settings(tmp_path / "on")["permissions"]["allow"]
    assert allow == ["Bash(git status)", *REMEDIATION_ALLOW]
    assert not any("pytest" in cmd or "mypy" in cmd for cmd in REMEDIATION_ALLOW)
    assert "permissions" not in _settings(tmp_path / "off")
    allow_scopes = [
        e for e in adapter.managed_lock_entries() if e.scope == "json:/permissions/allow"
    ]
    assert len(allow_scopes) == len(REMEDIATION_ALLOW)


def test_invalid_settings_raise_and_write_nothing(tmp_path: Path) -> None:
    settings = tmp_path / CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True)
    settings.write_text('{"a": 1,}\n', encoding="utf-8")
    adapter = ClaudeCodeAdapter()
    adapter.begin_sync(tmp_path, None, hooks_config=_ON)
    adapter.write_hook(resolved_hook(), tmp_path)

    with pytest.raises(SettingsMergeError, match=r"^\.claude/settings\.json:1:"):
        adapter.finalize(tmp_path)

    assert settings.read_text("utf-8") == '{"a": 1,}\n'

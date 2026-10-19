"""``playbook check`` with hooks: the Hooks block and scoped drift (specs/prK-lifecycle-hooks.md §A.8, §C.2.6).

The Hooks block labels every on hook per enabled adapter (``enforced`` /
``degraded`` / ``advisory`` / ``—``) and gives every off hook its reason. The
Drift section judges a co-owned ``settings.json`` element by element (scoped
lock entries), never by whole-file hash, and reports a lost exec bit.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.claude_settings import CLAUDE_SETTINGS_PATH
from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.hooks_config import HooksConfig
from coding_agent_playbook.lockfile.model import LockEntry, Lockfile, compute_hash
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from tests.hook_samples import resolved_hook, write_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

_HOOKS_ON = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode"]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[hooks]
enabled = true
"""


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), refresh=False)


def _section(out: str, title: str) -> list[str]:
    lines = out.splitlines()
    start = lines.index(f"=== {title} ===")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("===")), None)
    return lines[start + 1 : end]


def _report(repo: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert _check.run(_ns(repo)) == 0  # a diagnostic: always exit 0
    return capsys.readouterr().out


# --- the Hooks block -------------------------------------------------------------------

#: The engine pack's hooks shipped so far (Tracks K5-K10), in check's sorted order.
_ENGINE_PACK = (
    "block-precommit-bypass",
    "clean-code-metrics-nonregression",
    "command-convention-guard",
    "commit-message-convention",
    "control-plane-guard",
    "coverage-diff-gate",
    "dependency-allowlist-guard",
    "destructive-command-guard",
    "docstring-nonregression",
    "error-handling-lint-feedback",
    "eval-task-authoring-lint",
    "exfil-channel-guard",
    "gate-weakening-guard",
    "git-commit-push-policy-guard",
    "guard-decision-log",
    "guard-eval-fixtures",
    "guard-generated-outputs",
    "local-audit-log",
    "ml-unsafe-deserialization-guard",
    "network-egress-guard",
    "notebook-output-hygiene",
    "pii-prompt-guard",
    "post-edit-ruff-format",
    "precompact-checkpoint",
    "prompt-output-contract-on-stop",
    "prompt-write-scope-guard",
    "pytest-conventions-feedback",
    "resync-on-detector-input-change",
    "secret-content-guard",
    "secrets-path-guard",
    "sensitive-data-read-guard",
    "session-start-playbook-briefing",
    "skill-nudge",
    "stop-ci-parity-gate",
    "stop-diff-sweep",
    "stop-drift-and-orphan-gate",
    "subagent-stop-verify",
    "taint-escalation",
    "tests-with-source-nudge",
    "toolchain-missing-hint",
    "typing-lint-feedback",
    "validate-then-sync-on-canonical-edit",
)
_OPT_IN_SKIP = (
    "    [✗] {hook_id} (skipped: tier 'opt-in' is not in [hooks] tiers ['default'] and "
    "[hooks] enable does not name it)"
)


#: The §E.5 overlay-tier mechanisms (K9): inert until an overlay promotes them.
_OVERLAY_SKIP = (
    "    [✗] {hook_id} (skipped: tier 'overlay' is activated only by an overlay "
    "promoting the hook to tier: default)"
)


def _off(hook_ids: tuple[str, ...]) -> list[str]:
    return [f"    [✗] {hook_id} (skipped: hooks are off)" for hook_id in hook_ids]


def test_hooks_block_labels_per_adapter(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    hooks_dir = repo / "playbook" / "hooks"
    write_hook(hooks_dir, "guard-x")
    write_hook(hooks_dir, "guard-quiet", body="")
    write_hook(hooks_dir, "guard-y", tier="opt-in")

    lines = _section(_report(repo, capsys), "Hooks")

    assert lines == [
        "  [hooks]: on",
        "  Hooks (30 on / 45 total):",
        # The engine pack (Track K5): OpenCode has no notebook tool, so guard-generated-outputs
        # is degraded there; control-plane-guard matches no notebook edit. OpenCode's Stop is
        # evidence-only (§C.3.6), so every Stop-stage hook is degraded there (K6).
        "    [✓] block-precommit-bypass (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        "    [✓] clean-code-metrics-nonregression (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        _OPT_IN_SKIP.format(hook_id="command-convention-guard"),
        # K10: commitizen on the shared shell parse, on both harnesses.
        "    [✓] commit-message-convention (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        "    [✓] control-plane-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        _OPT_IN_SKIP.format(hook_id="coverage-diff-gate"),
        # K8: the Bash guards run in the shared shell dispatcher on both harnesses.
        "    [✓] dependency-allowlist-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        "    [✓] destructive-command-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        # K10: a Stop stage plus its post-edit bucket; OpenCode's Stop is evidence-only.
        "    [✓] docstring-nonregression (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        # K7: a rule-linked lint hook has no body (its rule carries the practice).
        "    [✓] error-handling-lint-feedback (agents_md: —, claude_code: enforced, "
        "continue: —, opencode: enforced)",
        "    [✓] eval-task-authoring-lint (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        # K8: its remote snapshot rides OpenCode's experimental session_start: degraded there.
        "    [✓] exfil-channel-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] gate-weakening-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] git-commit-push-policy-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        # K9: the decision sink has no body; OpenCode reaches only some of its events.
        "    [✓] guard-decision-log (agents_md: —, claude_code: enforced, continue: —, "
        "opencode: degraded)",
        _OPT_IN_SKIP.format(hook_id="guard-eval-fixtures"),
        "    [✓] guard-generated-outputs (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] guard-quiet (agents_md: —, claude_code: enforced, continue: —, opencode: —)",
        "    [✓] guard-x (agents_md: advisory, claude_code: enforced, continue: advisory, "
        "opencode: advisory)",
        _OPT_IN_SKIP.format(hook_id="guard-y"),
        _OPT_IN_SKIP.format(hook_id="local-audit-log"),
        # K7: the synthetic repo has no ML stack, so the linked rule (and the guard) is off.
        "    [✗] ml-unsafe-deserialization-guard (skipped: linked rule "
        "'ml-serialization-security' not applicable)",
        _OVERLAY_SKIP.format(hook_id="network-egress-guard"),
        _OPT_IN_SKIP.format(hook_id="notebook-output-hygiene"),
        # K9: an overlay-tier mechanism ships inert; no [hooks] switch turns it on (K-11).
        _OVERLAY_SKIP.format(hook_id="pii-prompt-guard"),
        # K7: the shared post-edit ruff pipeline, on both hook-capable harnesses.
        "    [✓] post-edit-ruff-format (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        _OPT_IN_SKIP.format(hook_id="precompact-checkpoint"),
        _OPT_IN_SKIP.format(hook_id="prompt-output-contract-on-stop"),
        # Claude Code only (K7): the native read-only constraints cover OpenCode.
        "    [✓] prompt-write-scope-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: advisory)",
        # The synthetic repo detects no pytest: the linked rule, and so the hook, is off.
        "    [✗] pytest-conventions-feedback (skipped: linked rule 'pytest' not applicable)",
        "    [✓] resync-on-detector-input-change (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: enforced)",
        # K8: OpenCode has no notebook tool and forwards no MCP call; its Stop is evidence-only.
        "    [✓] secret-content-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] secrets-path-guard (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        _OVERLAY_SKIP.format(hook_id="sensitive-data-read-guard"),
        # No advisory body (a hookless harness has no heartbeat); OpenCode's session_start
        # rides an experimental API and its Stop is evidence-only (§C.3.6): degraded.
        "    [✓] session-start-playbook-briefing (agents_md: —, claude_code: enforced, "
        "continue: —, opencode: degraded)",
        # spec 8.5: no body, so no advisory; edit and write are reachable on both harnesses.
        "    [✓] skill-nudge (agents_md: —, claude_code: enforced, continue: —, opencode: enforced)",
        "    [✓] stop-ci-parity-gate (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] stop-diff-sweep (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] stop-drift-and-orphan-gate (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        _OPT_IN_SKIP.format(hook_id="subagent-stop-verify"),
        _OPT_IN_SKIP.format(hook_id="taint-escalation"),
        "    [✓] tests-with-source-nudge (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        # OpenCode has no tool-failure event (OQ-43): reachable, but weaker.
        "    [✓] toolchain-missing-hint (agents_md: advisory, claude_code: enforced, "
        "continue: advisory, opencode: degraded)",
        "    [✓] typing-lint-feedback (agents_md: —, claude_code: enforced, continue: —, "
        "opencode: enforced)",
        "    [✓] validate-then-sync-on-canonical-edit (agents_md: advisory, "
        "claude_code: enforced, continue: advisory, opencode: enforced)",
    ]


def test_hooks_block_when_the_table_is_absent(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    write_hook(repo / "playbook" / "hooks", "guard-x")

    lines = _section(_report(repo, capsys), "Hooks")

    assert lines == [
        "  [hooks]: off — no [hooks] table (add [hooks] enabled = true or re-run 'playbook init')",
        "  Hooks (0 on / 43 total):",
        *_off(_ENGINE_PACK[:17]),
        "    [✗] guard-x (skipped: hooks are off)",
        *_off(_ENGINE_PACK[17:]),
    ]


def test_hooks_block_when_hooks_are_switched_off_or_unreadable(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "off").mkdir()
    (tmp_path / "bad").mkdir()
    off = make_synthetic_repo(tmp_path / "off", config_text=_HOOKS_ON.replace("true", "false"))
    bad = make_synthetic_repo(tmp_path / "bad", config_text=_HOOKS_ON + "tiers = 3\n")

    off_lines = _section(_report(off, capsys), "Hooks")
    bad_lines = _section(_report(bad, capsys), "Hooks")

    assert off_lines == [
        "  [hooks]: off — [hooks] enabled is not true",
        "  Hooks (0 on / 42 total):",
        *_off(_ENGINE_PACK),
    ]
    assert bad_lines[-1] == "  [hooks] cannot be read; run 'playbook validate'."
    assert bad_lines[0].startswith("  ✗ [hooks] tiers")


# --- scoped drift ----------------------------------------------------------------------


def _synced_settings(repo: Path) -> Path:
    """Render one managed group into ``settings.json`` and record its scoped entries."""
    settings = repo / CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text('{\n  "permissions": {"allow": ["Bash(ls)"]}\n}\n', encoding="utf-8")
    adapter = ClaudeCodeAdapter()
    adapter.begin_sync(repo, None, hooks_config=HooksConfig(enabled=True))
    adapter.write_hook(resolved_hook(), repo)
    adapter.finalize(repo)
    lock = Lockfile(2, "0", "", entries=adapter.managed_lock_entries())
    FileSystemStateSource(repo_root=repo).save_lockfile(lock)
    return settings


def _edit_timeout(settings: Path) -> None:
    doc = json.loads(settings.read_text("utf-8"))
    doc["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 1
    settings.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _delete_group(settings: Path) -> None:
    doc = json.loads(settings.read_text("utf-8"))
    del doc["hooks"]["PreToolUse"]
    settings.write_text(json.dumps(doc), encoding="utf-8")


def _break_json(settings: Path) -> None:
    settings.write_text(settings.read_text("utf-8").replace("{", "{ // c\n", 1), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            _edit_timeout,
            ["  managed entry edited: .claude/settings.json#/hooks/PreToolUse"],
            id="managed_entry_edited",
        ),
        pytest.param(
            _delete_group,
            ["  managed entry missing: .claude/settings.json#/hooks/PreToolUse"],
            id="managed_entry_missing",
        ),
        pytest.param(
            _break_json,
            ["  unreadable: .claude/settings.json (line 1, col 3: invalid JSON: "],
            id="invalid_json_unreadable",
        ),
    ],
)
def test_scoped_drift(
    mutate: Callable[[Path], None],
    expected: list[str],
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    mutate(_synced_settings(repo))

    lines = _section(_report(repo, capsys), "Drift")

    assert [line[: len(want)] for line, want in zip(lines, expected, strict=True)] == expected
    assert not any("hash mismatch" in line for line in lines)


def test_user_permission_edit_not_drift(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    settings = _synced_settings(repo)
    doc = json.loads(settings.read_text("utf-8"))
    doc["permissions"]["allow"].append("Bash(git status)")
    doc["model"] = "opus"
    doc["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "./mine.sh"}]}]
    settings.write_text(json.dumps(doc, indent=4, sort_keys=True), encoding="utf-8")

    lines = _section(_report(repo, capsys), "Drift")

    assert lines == ["  All on-disk files match generated output."]


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_executable_mode_drift(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    script = repo / ".coding-agent-playbook" / "hooks" / "scripts" / "guard-x" / "check.sh"
    script.parent.mkdir(parents=True)
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o644)
    entry = LockEntry(
        ".coding-agent-playbook/hooks/scripts/guard-x/check.sh",
        compute_hash(b"#!/bin/sh\n"),
        10,
        kind="hook",
        artifact_id="guard-x",
        executable=True,
    )
    FileSystemStateSource(repo_root=repo).save_lockfile(Lockfile(2, "0", "", entries=[entry]))

    drifted = _section(_report(repo, capsys), "Drift")
    script.chmod(0o755)
    clean = _section(_report(repo, capsys), "Drift")

    assert drifted == [
        "  mode mismatch: .coding-agent-playbook/hooks/scripts/guard-x/check.sh "
        "(expected executable)"
    ]
    assert clean == ["  All on-disk files match generated output."]


def test_scoped_drift_on_a_path_that_cannot_be_read_is_one_line(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    settings = _synced_settings(repo)
    settings.unlink()
    settings.mkdir()

    lines = _section(_report(repo, capsys), "Drift")

    assert len(lines) == 1
    assert lines[0].startswith("  unreadable: .claude/settings.json (")


def test_an_absent_settings_file_reports_each_entry_missing(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HOOKS_ON)
    _synced_settings(repo).unlink()

    lines = _section(_report(repo, capsys), "Drift")

    assert lines == [
        "  managed entry missing: .claude/settings.json#/hooks/SessionStart",
        "  managed entry missing: .claude/settings.json#/hooks/PreToolUse",
    ]

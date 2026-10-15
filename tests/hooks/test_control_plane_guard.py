"""control-plane-guard: stop the agent disabling or rewriting its own guardrails (specs/prK-hook-pack.md §E.1).

Every case runs the shipped ``HOOK.md`` (beside guard-generated-outputs, as a
consumer has them) through ``playbook-hook simulate pre_tool_use`` against a
synced fixture repo. File-tool edits are simulated in memory and the file is
diffed before and after; Bash writes onto control-plane files are a speed
bump. The ``cpg_*`` goldens pin parse, verdict and wire for both harnesses.
``FakeProc`` fails the test on any spawn: the guard never runs git or playbook.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._canonical_json import element_sha256
from coding_agent_playbook.hook_runtime.canary import DEFAULT_CANARIES, run_canaries
from coding_agent_playbook.hook_runtime.config import CONFIG_FAULT_REASON, GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from tests.hook_runtime.fakes import FakeProc
from tests.hooks.pack_repo import PackRepo, rows_of, with_scope

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase

    type Payload = Callable[[str, str, str], HookPayloadCase]
    type Deps = Callable[..., RuntimeDeps]

HOOK_ID = "control-plane-guard"
GGO = "guard-generated-outputs"
REASON = "Guardrail configuration is user-owned; ask the user to change it."
_LAUNCH = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/playbook/launch.sh pre_tool_use'
_MANAGED = {
    "matcher": "Edit|Write|Bash",
    "hooks": [{"type": "command", "command": _LAUNCH, "timeout": 10}],
}
_USER_HOOK = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user"}]}
_SETTINGS: dict[str, Any] = {
    "model": "sonnet",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "hooks": {"PreToolUse": [_MANAGED, _USER_HOOK]},
}
_CONFIG = """\
schema_version = 1
adapters_enabled = ["claude_code", "opencode"]
overlays_enabled = ["acme_rules"]

[project]
name = "demo"
description = "A demo"

[engine]
version = "0.1.0a0"

[links]
allowed_domains = ["docs.python.org"]

[hooks]
enabled = true

[metrics]
mode = "regression"
fail_on_breach = true

[metrics.regression.coverage]
max_worsening = 0
"""
_OPENCODE = """\
{
  // project config; "//" inside a string is data
  "plugin": ["opencode-helper"],
  "mcp": {
    "docs": {"type": "local", "command": ["npx", "docs-mcp"], "enabled": true},
  },
}
"""
_PRECOMMIT = """\
repos:
  - repo: local
    hooks:
      - id: playbook-sync-check
        name: playbook sync --check
        entry: playbook sync --check
        language: system
      - id: ruff
        name: ruff
        entry: ruff check
        language: system
"""
_SKILL = "---\nname: notes\ndescription: Take notes\n---\nWrite notes.\n"
_FILES = {
    ".claude/settings.json": json.dumps(_SETTINGS, indent=2) + "\n",
    ".coding-agent-playbook.toml": _CONFIG,
    ".mcp.json": json.dumps({"mcpServers": {"docs": {"command": "npx"}}}, indent=2) + "\n",
    "opencode.jsonc": _OPENCODE,
    ".pre-commit-config.yaml": _PRECOMMIT,
    ".claude/skills/notes/SKILL.md": _SKILL,
    ".claude/hooks/playbook/launch.sh": "#!/bin/sh\n",
    "src/app.py": "x = 1\n",
}
_ROWS = [
    *rows_of((".claude/hooks/playbook/launch.sh", "runtime", "", "")),
    with_scope(
        rows_of((".claude/settings.json", "runtime", "registration:pre_tool_use", ""))[0],
        "json:/hooks/PreToolUse",
        element_sha256(_MANAGED),
    ),
]


def _synced(repo: PackRepo, **kwargs: Any) -> PackRepo:
    for rel, text in _FILES.items():
        repo.write(rel, text)
    repo.install_pack([GGO, HOOK_ID], rows=_ROWS, **kwargs)
    return repo


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """The synced fixture tree with guard-generated-outputs and control-plane-guard on."""
    return _synced(pack_repo)


def _golden(repo: PackRepo, deps: RuntimeDeps, case: HookPayloadCase) -> SimulateReport:
    """Simulate ``case`` relocated into ``repo``; its decision, reason and wire must match."""
    report = repo.simulate(repo.relocate(case), deps, harness=Harness(case.harness))
    expected = case.expected["result"]
    combined = report.trace.combined
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == case.wire()
    return report


def _path(repo: PackRepo, target: str) -> str:
    return target if os.path.isabs(target) else str(repo.root / target)


def _write(repo: PackRepo, deps: RuntimeDeps, target: str, content: str, **env: str) -> Any:
    tool_input = {"file_path": _path(repo, target), "content": content}
    return repo.simulate(repo.tool_payload("Write", tool_input), deps, env=env)


def _edit(repo: PackRepo, deps: RuntimeDeps, target: str, old: str, new: str) -> Any:
    tool_input = {"file_path": _path(repo, target), "old_string": old, "new_string": new}
    return repo.simulate(repo.tool_payload("Edit", tool_input), deps)


def _bash(repo: PackRepo, deps: RuntimeDeps, command: str, **env: str) -> Any:
    return repo.simulate(repo.tool_payload("Bash", {"command": command}), deps, env=env)


def _verdict(report: SimulateReport) -> tuple[str, str]:
    """``(decision, rule_id)`` of control-plane-guard; ``("none", "")`` when it passed."""
    mine = [d for d in report.to_json()["decisions"] if d["hook_id"] == HOOK_ID]
    if not mine or mine[0]["decision"] == "none":
        return ("none", "")
    return (mine[0]["decision"], mine[0]["rule_id"])


def _settings_with(**changes: Any) -> str:
    return json.dumps({**_SETTINGS, **changes}, indent=2) + "\n"


# --- settings ----------------------------------------------------------------------------


def test_removing_playbook_hook_entry_denied(repo: PackRepo, deps: Deps) -> None:
    removed = _settings_with(hooks={"PreToolUse": [_USER_HOOK]})

    assert _verdict(_write(repo, deps(), ".claude/settings.json", removed)) == ("deny", "settings")
    changed = _edit(repo, deps(), ".claude/settings.json", "pre_tool_use", "pre_tool_use --noop")
    assert _verdict(changed) == ("deny", "settings")


def test_adding_user_hook_passes(repo: PackRepo, deps: Deps) -> None:
    mine = {"matcher": "", "hooks": [{"type": "command", "command": "say done"}]}
    added = _settings_with(hooks={"PreToolUse": [_MANAGED, _USER_HOOK, mine], "Stop": [mine]})

    report = _write(repo, deps(), ".claude/settings.json", added)

    assert report.trace.combined.decision is Decision.NONE


def test_env_pythonpath_denied(repo: PackRepo, deps: Deps) -> None:
    env = '"model": "sonnet",\n  "env": {"PYTHONPATH": "/tmp/evil"},'

    report = _edit(repo, deps(), ".claude/settings.json", '"model": "sonnet",', env)

    assert _verdict(report) == ("deny", "settings")


def test_disable_all_hooks_denied(repo: PackRepo, deps: Deps, hook_payload: Payload) -> None:
    case = hook_payload("claude_code", "pre_tool_use", "cpg_edit_settings_disable_all_hooks")

    assert _verdict(_golden(repo, deps(), case)) == ("deny", "settings")


def test_bypass_permissions_default_mode_denied(repo: PackRepo, deps: Deps) -> None:
    mode = '"defaultMode": "bypassPermissions",\n    "allow": ['

    report = _edit(repo, deps(), ".claude/settings.json", '"allow": [', mode)

    assert _verdict(report) == ("deny", "settings")


def test_new_permissions_allow_asks(repo: PackRepo, deps: Deps) -> None:
    allow = '"Bash(ls:*)",\n      "Bash(curl:*)"'

    report = _edit(repo, deps(), ".claude/settings.json", '"Bash(ls:*)"', allow)

    assert _verdict(report) == ("ask", "settings")


def test_mcp_json_server_added_asks(repo: PackRepo, deps: Deps, hook_payload: Payload) -> None:
    case = hook_payload("claude_code", "pre_tool_use", "cpg_write_mcp_json_server")

    assert _verdict(_golden(repo, deps(), case)) == ("ask", "mcp")
    same_server = json.dumps({"mcpServers": {"docs": {"command": "uvx"}}})
    assert _verdict(_write(repo, deps(), ".mcp.json", same_server)) == ("none", "")


def test_opencode_jsonc_plugin_added_asks(
    repo: PackRepo, deps: Deps, hook_payload: Payload
) -> None:
    case = hook_payload("opencode", "pre_tool_use", "cpg_edit_opencode_jsonc_plugin")

    report = _golden(repo, deps(), case)

    assert _verdict(report) == ("ask", "opencode_config")
    comment = _edit(repo, deps(), "opencode.jsonc", "// project config", "// our config")
    assert _verdict(comment) == ("none", "")


def test_model_key_change_passes(repo: PackRepo, deps: Deps) -> None:
    report = _edit(repo, deps(), ".claude/settings.json", '"sonnet"', '"opus"')

    assert report.trace.combined.decision is Decision.NONE


def test_user_config_dir_settings_guarded(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    user_dir = tmp_path / "claude-config"
    target = str(user_dir / "settings.json")
    env = {"CLAUDE_CONFIG_DIR": str(user_dir)}

    off = _write(repo, deps(), target, '{"disableAllHooks": true}\n', **env)
    model = _write(repo, deps(), target, '{"model": "opus"}\n', **env)

    assert _verdict(off) == ("deny", "settings")
    assert _verdict(model) == ("none", "")


def test_main_checkout_settings_local_disable_all_hooks_denied(
    tmp_path: Path, deps: Deps, real_git: Callable[..., str]
) -> None:
    main = tmp_path / "main"
    main.mkdir()
    real_git("init", "-q", cwd=main)
    (main / "README.md").write_text("demo\n", encoding="utf-8")
    real_git("add", "README.md", cwd=main)
    real_git("commit", "-q", "-m", "init", cwd=main)
    real_git("worktree", "add", "-q", str(tmp_path / "wt"), cwd=main)
    worktree = _synced(PackRepo(Path(os.path.realpath(tmp_path / "wt"))))
    target = os.path.realpath(main) + "/.claude/settings.local.json"

    report = _write(worktree, deps(), target, '{"disableAllHooks": true}\n')

    assert _verdict(report) == ("deny", "settings")


# --- hook carriers -----------------------------------------------------------------------


def test_new_fnmatch_py_under_hook_dir_denied(repo: PackRepo, deps: Deps) -> None:
    shadow = _write(repo, deps(), ".coding-agent-playbook/hooks/fnmatch.py", "def x(): ...\n")
    launcher_dir = _write(repo, deps(), ".claude/hooks/playbook/extra.sh", "#!/bin/sh\n")
    existing = _write(repo, deps(), ".claude/hooks/playbook/launch.sh", "#!/bin/sh\n")

    assert _verdict(shadow) == ("deny", "hook_artifact")
    assert _verdict(launcher_dir) == ("deny", "hook_artifact")
    # An existing generated file is guard-generated-outputs' to deny, not this guard's.
    assert _verdict(existing) == ("none", "")
    assert existing.trace.combined.decision is Decision.DENY


def test_hooks_frontmatter_added_to_user_skill_asks(repo: PackRepo, deps: Deps) -> None:
    hooks = "description: Take notes\nhooks:\n  PreToolUse:\n    - matcher: Bash\n"
    skill = ".claude/skills/notes/SKILL.md"

    added = _edit(repo, deps(), skill, "description: Take notes\n", hooks)
    body = _edit(repo, deps(), skill, "Write notes.", "Write short notes.")
    command = _write(repo, deps(), ".claude/commands/go.md", f"---\n{hooks}---\nGo.\n")

    assert _verdict(added) == ("ask", "frontmatter_carrier")
    assert _verdict(body) == ("none", "")
    assert _verdict(command) == ("ask", "frontmatter_carrier")


@pytest.mark.parametrize(
    "target",
    [
        ".opencode/plugins/evil.js",
        ".opencode/tool/run.ts",
        ".claude/skills/notes/.claude-plugin/plugin.json",
        "tools/hooks/hooks.json",
    ],
)
def test_new_opencode_plugin_file_asks(repo: PackRepo, deps: Deps, target: str) -> None:
    report = _write(repo, deps(), target, "export default {}\n")

    assert _verdict(report) == ("ask", "plugin_carrier")


def test_playbook_hooks_source_edit_asks(repo: PackRepo, deps: Deps) -> None:
    report = _write(repo, deps(), "playbook/hooks/mine/HOOK.md", "---\nid: mine\n---\n")

    assert _verdict(report) == ("ask", "hook_source")


def test_extra_paths_config_adds_denied_rows(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    extra = {"extra_paths": ["compliance/", "~/.config/acme/"]}
    repo = _synced(pack_repo, per_hook={HOOK_ID: extra})
    home = os.path.realpath(tmp_path / "home")

    in_repo = _write(repo, deps(), "compliance/policy.yaml", "mode: off\n")
    user = _write(repo, deps(home=home), f"{home}/.config/acme/policy.yaml", "mode: off\n")

    assert _verdict(in_repo) == ("deny", "extra")
    assert _verdict(user) == ("deny", "extra")


# --- the playbook config (TOML) ---------------------------------------------------------


def _config_edit(repo: PackRepo, deps: Deps, old: str, new: str) -> tuple[str, str]:
    return _verdict(_edit(repo, deps(), ".coding-agent-playbook.toml", old, new))


def test_overlay_dropped_from_overlays_enabled_asks(repo: PackRepo, deps: Deps) -> None:
    dropped = _config_edit(repo, deps, '["acme_rules"]', "[]")
    added = _config_edit(repo, deps, '["acme_rules"]', '["acme_rules", "more"]')

    assert dropped == ("ask", "config")
    assert added == ("none", "")


def test_allowed_domains_addition_asks(repo: PackRepo, deps: Deps) -> None:
    more = '["docs.python.org", "paste.example"]'

    assert _config_edit(repo, deps, '["docs.python.org"]', more) == ("ask", "config")
    assert _config_edit(repo, deps, '["docs.python.org"]', "[]") == ("none", "")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("enabled = true", "enabled = false"),
        (
            "enabled = true",
            'enabled = true\n\n[hooks.commit_convention]\ncutover_date = "2020-01-01"',
        ),
        ("[metrics]", '[guardrails.secrets]\nallow_paths = ["*"]\n\n[metrics]'),
    ],
    ids=["switch-off", "cutover-date", "guardrails"],
)
def test_any_hooks_table_edit_denied(repo: PackRepo, deps: Deps, old: str, new: str) -> None:
    assert _config_edit(repo, deps, old, new) == ("deny", "config")


def test_local_toml_overlays_enabled_empty_denied(repo: PackRepo, deps: Deps) -> None:
    local = ".coding-agent-playbook.local.toml"

    cleared = _write(repo, deps(), local, "overlays_enabled = []\n")
    project = _write(repo, deps(), local, '[project]\ndescription = "mine"\n')

    assert _verdict(cleared) == ("deny", "local_config")
    assert _verdict(project) == ("none", "")


def test_project_description_passes(repo: PackRepo, deps: Deps) -> None:
    assert _config_edit(repo, deps, '"A demo"', '"Another demo"') == ("none", "")


def test_toml_broken_after_edit_asks(repo: PackRepo, deps: Deps) -> None:
    assert _config_edit(repo, deps, "[project]", "[project") == ("ask", "config")


def test_metrics_unknown_direction_counts_as_loosening(repo: PackRepo, deps: Deps) -> None:
    last = "max_worsening = 0\n"  # tables are appended after the config's last line
    weights = f"{last}\n[metrics.weights]\ncyclomatic_complexity = 2.0\n"
    threshold = f"{last}\n[metrics.thresholds.cyclomatic_complexity]\nfail = 20\n"

    assert _config_edit(repo, deps, last, weights) == ("ask", "config")
    assert _config_edit(repo, deps, "max_worsening = 0", "max_worsening = 5") == ("ask", "config")
    assert _config_edit(repo, deps, "fail_on_breach = true", "fail_on_breach = false")[0] == "ask"
    # Provably stricter changes pass: a new gate, the strictest mode.
    assert _config_edit(repo, deps, last, threshold) == ("none", "")
    assert _config_edit(repo, deps, '"regression"', '"both"') == ("none", "")


# --- pre-commit ---------------------------------------------------------------------------


def test_removing_playbook_precommit_hook_denied(repo: PackRepo, deps: Deps) -> None:
    commented = _edit(
        repo, deps(), ".pre-commit-config.yaml", "- id: playbook-sync-check", "# - id: x"
    )
    rewritten = _write(repo, deps(), ".pre-commit-config.yaml", "repos: []\n")

    assert _verdict(commented) == ("deny", "precommit")
    assert _verdict(rewritten) == ("deny", "precommit")


def test_other_precommit_edit_passes(repo: PackRepo, deps: Deps) -> None:
    report = _edit(repo, deps(), ".pre-commit-config.yaml", "entry: ruff check", "entry: ruff")

    assert _verdict(report) == ("none", "")


# --- Bash ---------------------------------------------------------------------------------


def test_echo_into_interpreter_pin_denied(repo: PackRepo, deps: Deps) -> None:
    proc = FakeProc()
    pin = 'echo /tmp/py > "$(git rev-parse --git-path playbook-hooks)/interpreter"'

    dynamic = _bash(repo, deps(proc=proc), pin)
    literal = _bash(repo, deps(), "echo /tmp/py > .git/playbook-hooks/interpreter")
    machine = _write(repo, deps(), ".git/playbook-hooks/machine.json", "{}\n")

    assert _verdict(dynamic) == ("deny", "state")
    assert _verdict(literal) == ("deny", "state")
    assert _verdict(machine) == ("deny", "state")
    assert proc.calls == []  # the git-path substitution is recognized, never run


def test_write_to_trust_store_denied(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    state = tmp_path / "xdg-state"
    trust = str(state / "coding-agent-playbook" / "trust.json")
    env = {"XDG_STATE_HOME": str(state)}

    written = _write(repo, deps(), trust, "{}\n", **env)
    copied = _bash(repo, deps(), f"cp /tmp/forged.json {trust}", **env)

    assert _verdict(written) == ("deny", "trust_store")
    assert _verdict(copied) == ("deny", "trust_store")


@pytest.mark.parametrize(
    "command",
    [
        "yes | playbook sync",
        "playbook sync < answers.txt",
        "playbook sync <<< y",
        "unbuffer playbook sync",
        "expect -c 'spawn playbook sync'",
        "script -qc 'uv run playbook sync' /dev/null",
        "bash -c 'printf y | coding-agent-playbook sync'",
    ],
)
def test_script_wrapped_and_piped_sync_denied(repo: PackRepo, deps: Deps, command: str) -> None:
    decision, rule = _verdict(_bash(repo, deps(), command))

    assert (decision, rule in ("sync_wrapper", "sync_stdin")) == ("deny", True)


def test_script_wrapped_sync_golden(repo: PackRepo, deps: Deps, hook_payload: Payload) -> None:
    case = hook_payload("claude_code", "pre_tool_use", "cpg_bash_script_wrapped_sync")

    assert _verdict(_golden(repo, deps(), case)) == ("deny", "sync_wrapper")


@pytest.mark.parametrize(
    "command",
    [
        "playbook sync",
        "uv run playbook sync",
        "playbook sync --check | tail -5",
        "playbook sync 2>&1 | tee sync.log",
        "cat .claude/settings.json",
    ],
)
def test_plain_playbook_sync_passes(repo: PackRepo, deps: Deps, command: str) -> None:
    assert _bash(repo, deps(), command).trace.combined.decision is Decision.NONE


def test_claude_mcp_add_asks(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps(), "claude mcp add docs -- npx -y docs-mcp")

    assert _verdict(report) == ("ask", "mcp_add")
    assert _verdict(_bash(repo, deps(), "claude mcp list")) == ("none", "")


def test_bash_c_wrapped_settings_write_denied(
    repo: PackRepo, deps: Deps, hook_payload: Payload
) -> None:
    case = hook_payload("claude_code", "pre_tool_use", "cpg_bash_c_settings_write")

    assert _verdict(_golden(repo, deps(), case)) == ("deny", "settings")
    teed = _bash(repo, deps(), "echo x | tee -a .coding-agent-playbook.toml")
    assert _verdict(teed) == ("deny", "config")


# --- policy -------------------------------------------------------------------------------


def test_reason_is_the_single_user_owned_line(repo: PackRepo, deps: Deps) -> None:
    reports = [
        _write(repo, deps(), ".claude/settings.json", '{"disableAllHooks": true}'),
        _write(repo, deps(), ".mcp.json", '{"mcpServers": {"x": {"command": "x"}}}'),
        _bash(repo, deps(), "yes | playbook sync"),
    ]

    for report in reports:
        assert report.trace.combined.reason == REASON


def test_unsimulatable_edit_asks(repo: PackRepo, deps: Deps, hook_payload: Payload) -> None:
    missing = _edit(repo, deps(), ".claude/settings.json", "no such text", "x")
    case = hook_payload("opencode", "pre_tool_use", "cpg_apply_patch_settings")

    assert _verdict(missing) == ("ask", "settings")
    # OpenCode has no ask primitive: the ask reaches the wire as a deny.
    assert _verdict(_golden(repo, deps(), case)) == ("ask", "settings")


def test_ordinary_edit_and_bash_pass_without_spawning(repo: PackRepo, deps: Deps) -> None:
    proc = FakeProc()

    edit = _edit(repo, deps(proc=proc), "src/app.py", "x = 1", "x = 2")
    bash = _bash(repo, deps(proc=proc), "ls -la && echo done > notes.txt")

    assert edit.trace.combined.decision is Decision.NONE
    assert bash.trace.combined.decision is Decision.NONE
    assert proc.calls == []


def test_corrupt_guard_config_hash_asks_once_per_session(
    repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    config = repo.root / GUARD_CONFIG_REL
    config.write_bytes(config.read_bytes().replace(b'"extra_paths":[]', b'"extra_paths":[ ]'))
    payload = repo.tool_payload("Write", {"file_path": _path(repo, ".mcp.json"), "content": "{}"})
    state = tmp_path / "state"
    state.mkdir()

    first = repo.simulate(payload, deps(), state=state)
    second = repo.simulate(payload, deps(), state=state)

    assert (first.trace.combined.decision, first.trace.combined.reason) == (
        Decision.ASK,
        CONFIG_FAULT_REASON,
    )
    assert second.trace.combined.decision is Decision.NONE


def test_heartbeat_canary_disable_all_hooks_denies(repo: PackRepo, deps: Deps) -> None:
    canaries = [canary for canary in DEFAULT_CANARIES if canary.hook_id == HOOK_ID]
    before = (repo.root / ".claude/settings.json").read_bytes()

    [result] = run_canaries(canaries, repo_root=str(repo.root), deps=deps(state=repo.store()))

    assert (result.name, result.ok, result.decision) == (
        "settings-disable-all-hooks",
        True,
        Decision.DENY,
    )
    assert (repo.root / ".claude/settings.json").read_bytes() == before
    assert {line["canary"] for line in repo.decisions()} == {True}


def test_canary_row_writes_disable_all_hooks_into_settings() -> None:
    [row] = [canary for canary in DEFAULT_CANARIES if canary.hook_id == HOOK_ID]
    tool_input = row.fields["tool_input"]

    assert (row.expect, row.fields["tool_name"]) == (Decision.DENY, "Write")
    assert tool_input["file_path"] == ".claude/settings.json"
    assert json.loads(tool_input["content"]) == {"disableAllHooks": True}

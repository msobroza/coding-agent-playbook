"""guard-generated-outputs: deny hand-edits to generated files (specs/prK-hook-pack.md §E.1).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
pre_tool_use`` (the exact dispatch pipeline) against a synced fixture repo
whose ``guard_config.json`` is rendered by the real ``render_guard_config``.
The ``ggo_*`` golden payloads (both harnesses) pin the parse, the handler's
reason and the rendered wire at once. ``FakeProc`` fails the test on any
spawn: the deny path runs no subprocess.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._sentinel import SENTINEL, sentinel_line
from coding_agent_playbook.hook_runtime.canary import DEFAULT_CANARIES, run_canaries
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.pin import write_machine_pins
from coding_agent_playbook.hook_runtime.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.state import StateStore
from tests.hook_runtime.fakes import FakeProc
from tests.hook_runtime.guard_repo import hook_record
from tests.hooks.pack_repo import PackRepo, rows_of, with_scope

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase

    type Payload = Callable[[str, str, str], HookPayloadCase]

HOOK_ID = "guard-generated-outputs"
TAIL = "then run playbook validate && playbook sync"
_HTML = sentinel_line("html")
_ROWS = rows_of(
    (".claude/CLAUDE.md", "composite", "", ""),
    ("AGENTS.md", "composite", "", ""),
    (".claude/skills/demo/SKILL.md", "skill", "demo", "<repo-local>"),
    (".claude/skills/demo/scripts/run.py", "skill", "demo", "<repo-local>"),
    (".continue/rules/30-python-typing.md", "rule", "python-typing", "coding_agent_playbook"),
    (".opencode/command/review.md", "prompt", "review", "coding_agent_playbook"),
    ("docs/legacy.md", "", "", ""),
    (".claude/hooks/playbook/launch.sh", "runtime", "", ""),
)
_SETTINGS_ROW = with_scope(
    rows_of((".claude/settings.json", "runtime", "registration:pre_tool_use", ""))[0],
    "json:/hooks/PreToolUse",
    "ab" * 32,
)
_FILES = {
    ".claude/CLAUDE.md": f"{_HTML}\n# Rules\n",
    "AGENTS.md": f"{_HTML}\n# Agents\n",
    ".claude/skills/demo/SKILL.md": "---\nname: demo\ndescription: Demo\n---\nNo sentinel here.\n",
    ".claude/skills/demo/scripts/run.py": "print('demo')\n",
    ".continue/rules/30-python-typing.md": f"{_HTML}\nTyping.\n",
    ".opencode/command/review.md": f"{_HTML}\nReview.\n",
    "docs/legacy.md": "Rendered by an engine that predates provenance.\n",
    ".claude/hooks/playbook/launch.sh": "#!/bin/sh\n",
    ".claude/settings.json": '{"hooks": {}}\n',
    ".claude/commands/review.md": f"---\ndisallowed-tools: Edit\n---\n{_HTML}\nReview.\n",
    ".claude/commands/notes.md": f"# Notes\nLines like `{_HTML}` are generated.\n",
    "renderer.py": f'SENTINEL = "{SENTINEL}"\n',
}


def _synced(repo: PackRepo, **kwargs: Any) -> PackRepo:
    for rel, text in _FILES.items():
        repo.write(rel, text)
    repo.install_pack([HOOK_ID], rows=[*_ROWS, _SETTINGS_ROW], **kwargs)
    return repo


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """The synced fixture tree with guard-generated-outputs on."""
    return _synced(pack_repo)


def _golden(repo: PackRepo, deps: RuntimeDeps, case: HookPayloadCase, **env: str) -> SimulateReport:
    """Simulate ``case`` relocated into ``repo``; its decision, reason and wire must match."""
    harness = Harness(case.harness)
    report = repo.simulate(repo.relocate(case), deps, harness=harness, env=env)
    expected = case.expected["result"]
    combined = report.trace.combined
    assert (combined.decision.value, combined.reason) == (
        expected["decision"],
        expected.get("reason", ""),
    )
    assert report.trace.wire == case.wire()
    return report


def _edit(repo: PackRepo, deps: RuntimeDeps, rel: str, **env: str) -> SimulateReport:
    tool_input = {"file_path": str(repo.root / rel), "old_string": "a", "new_string": "b"}
    return repo.simulate(repo.tool_payload("Edit", tool_input), deps, env=env)


def _bash(repo: PackRepo, deps: RuntimeDeps, command: str) -> SimulateReport:
    return repo.simulate(repo.tool_payload("Bash", {"command": command}), deps)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


def test_edit_claude_md_denied_reason_names_playbook_rules(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    report = _golden(
        repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_edit_claude_md")
    )

    reason = report.trace.combined.reason
    assert "generated from rules; edit playbook/rules/<id> (ids: playbook check)" in reason
    assert [d["hook_id"] for d in report.to_json()["decisions"]] == [HOOK_ID]


def test_skill_md_and_script_denied_via_lockfile_without_sentinel(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    _golden(repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_multiedit_skill_md"))
    write = {"file_path": str(repo.root / ".claude/skills/demo/scripts/run.py"), "content": "x\n"}

    report = repo.simulate(repo.tool_payload("Write", write), deps())

    assert _decision(report) is Decision.DENY
    assert 'Edit its source "playbook/skills/demo" instead' in report.trace.combined.reason


def test_dot_Claude_case_variant_denied_on_darwin(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    # On a case-sensitive host the variant is its own file; on darwin it is the same one.
    repo.write(".Claude/CLAUDE.md", f"{_HTML}\n# Rules\n")
    darwin = deps(platform="darwin")

    report = _edit(repo, darwin, ".Claude/CLAUDE.md")
    bash = _bash(repo, darwin, "sed -i s/a/b/ .Claude/CLAUDE.md")  # targets fold too

    assert _decision(report) is Decision.DENY
    assert report.trace.combined.reason.startswith('".Claude/CLAUDE.md" is generated')
    assert _decision(bash) is Decision.DENY


def test_new_command_file_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    report = _golden(
        repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_write_new_command")
    )

    assert report.trace.wire.stdout == ""


def test_file_quoting_sentinel_literal_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    assert _decision(_edit(repo, deps(), "renderer.py")) is Decision.NONE
    assert _decision(_edit(repo, deps(), ".claude/commands/notes.md")) is Decision.NONE


def test_bash_redirect_into_agents_md_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    _golden(
        repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_bash_redirect_agents_md")
    )


def test_cp_from_generated_file_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    _golden(repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_bash_cp_from_generated"))


def test_hatch_in_env_prefix_ignored_hook_env_hatch_honored(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    case = hook_payload("claude_code", "pre_tool_use", "ggo_bash_sed_env_prefix")
    _golden(repo, deps(), case)

    hatched = repo.simulate(repo.relocate(case), deps(), env={"PLAYBOOK_ALLOW_GENERATED_EDIT": "1"})

    assert _decision(hatched) is Decision.NONE


def test_hatch_set_by_a_settings_file_is_ignored(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(".claude/settings.json", '{"env": {"PLAYBOOK_ALLOW_GENERATED_EDIT": "1"}}\n')

    report = _edit(repo, deps(), "AGENTS.md", PLAYBOOK_ALLOW_GENERATED_EDIT="1")

    assert _decision(report) is Decision.DENY


def test_guard_config_edit_says_ask_the_user_without_remediation(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    report = _golden(
        repo, deps(), hook_payload("claude_code", "pre_tool_use", "ggo_edit_guard_config")
    )

    reason = report.trace.combined.reason
    assert "ask the user" in reason
    assert "playbook sync" not in reason and "playbook validate" not in reason
    assert _decision(_edit(repo, deps(), ".claude/hooks/playbook/launch.sh")) is Decision.DENY


def test_command_with_frontmatter_and_body_sentinel_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _edit(repo, deps(), ".claude/commands/review.md")

    assert _decision(report) is Decision.DENY
    assert "Edit the canonical source under playbook/" in report.trace.combined.reason


def test_settings_json_scoped_entries_left_to_control_plane_guard(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    assert _decision(_edit(repo, deps(), ".claude/settings.json")) is Decision.NONE


@pytest.mark.parametrize(
    "command",
    [
        "playbook sync",
        "playbook init",
        "git checkout -- AGENTS.md .claude/CLAUDE.md",
        "git restore --source=HEAD AGENTS.md",
        "uv run playbook sync && git restore AGENTS.md",
    ],
)
def test_restore_commands_pass(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str
) -> None:
    assert _decision(_bash(repo, deps(), command)) is Decision.NONE


def test_restore_commands_extend_but_their_redirects_stay_checked(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    config = {HOOK_ID: {"restore_commands": ["tee"]}}
    repo = _synced(pack_repo, per_hook=config)

    assert _decision(_bash(repo, deps(), "playbook render | tee AGENTS.md")) is Decision.NONE
    assert _decision(_bash(repo, deps(), "playbook sync > AGENTS.md")) is Decision.DENY


def test_repo_local_vs_engine_source_remediation(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    engine = _edit(repo, deps(), ".continue/rules/30-python-typing.md").trace.combined.reason
    local = _edit(repo, deps(), ".claude/skills/demo/scripts/run.py").trace.combined.reason

    assert 'from rule "python-typing" (source "coding_agent_playbook")' in engine
    assert "Add a same-id override under playbook/rules/ (repo-local wins" in engine
    assert 'from skill "demo" (source "<repo-local>")' in local
    assert 'Edit its source "playbook/skills/demo" instead' in local


def test_v1_lockfile_entry_gets_generic_reason(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    reason = _edit(repo, deps(), "docs/legacy.md").trace.combined.reason

    assert reason.splitlines() == [
        '"docs/legacy.md" is generated by playbook sync; hand edits are overwritten.',
        "Edit the canonical source under playbook/ (or add a same-id override there),",
        TAIL,
    ]


@pytest.mark.parametrize("case", ["ggo_edit_agents_md", "ggo_apply_patch_command"])
def test_opencode_edit_and_apply_patch_targets_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, case: str
) -> None:
    report = _golden(repo, deps(), hook_payload("opencode", "pre_tool_use", case))

    assert report.trace.wire.exit_code == 10


@pytest.mark.parametrize(
    ("harness", "case"),
    [
        ("claude_code", "ggo_edit_claude_md"),
        ("claude_code", "ggo_multiedit_skill_md"),
        ("claude_code", "ggo_bash_redirect_agents_md"),
        ("claude_code", "ggo_edit_guard_config"),
        ("opencode", "ggo_apply_patch_command"),
    ],
)
def test_deny_reason_at_most_4_lines(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, harness: str, case: str
) -> None:
    report = _golden(repo, deps(), hook_payload(harness, "pre_tool_use", case))

    reason = report.trace.combined.reason
    assert 1 <= len(reason.splitlines()) <= 4
    assert all(len(line) <= 160 for line in reason.splitlines())
    assert reason.endswith(TAIL) is (case != "ggo_edit_guard_config")


def test_deny_path_spawns_no_subprocess(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    proc = FakeProc()

    report = _bash(repo, deps(proc=proc), "sed -i s/a/b/ .claude/CLAUDE.md AGENTS.md")

    assert _decision(report) is Decision.DENY
    assert proc.calls == []


def test_internal_error_asks_and_denies_headless(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    """Guard failure class (§E.0.5): a broken config asks, and an unattended run denies."""
    pack_repo.write("AGENTS.md", f"{_HTML}\n")
    broken = {
        "kind": "builtin",
        "name": "guard_generated_outputs",
        "config": {"extra_protected": 3},
    }
    pack_repo.install(hook_record(HOOK_ID, decisions=("deny", "ask", "none"), handler=broken))
    tool_input = {"file_path": str(pack_repo.root / "AGENTS.md"), "content": "x\n"}
    payload = pack_repo.tool_payload("Write", tool_input)

    attended = pack_repo.simulate(payload, deps())
    headless = pack_repo.simulate(payload, deps(), env={UNATTENDED_ENV_VAR: "1"})

    assert _decision(attended) is Decision.ASK
    assert _decision(headless) is Decision.DENY


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("ls -la src", Decision.NONE),
        ("git status && pytest -q | tail -5", Decision.NONE),
        ("echo x > AGENTS.md", Decision.ASK),
    ],
)
def test_command_without_write_target_exits_before_reading_its_rules(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str, expected: Decision
) -> None:
    """Finding #8: no segment writes anything, so the guard stops before its config and targets.

    A malformed ``restore_commands`` is the witness: only a writing command reaches it (and asks).
    """
    pack_repo.write("AGENTS.md", f"{_HTML}\n")
    broken = {
        "kind": "builtin",
        "name": "guard_generated_outputs",
        "config": {"restore_commands": 3},
    }
    pack_repo.install(hook_record(HOOK_ID, decisions=("deny", "ask", "none"), handler=broken))

    assert _decision(_bash(pack_repo, deps(), command)) is expected


def test_installed_overlay_resource_denied_via_machine_json(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo = _synced(pack_repo, packages=("coding_agent_playbook", "acme_rules"))
    installed = tmp_path / "site-packages" / "acme_rules" / "resources"
    (installed / "rules").mkdir(parents=True)
    (installed / "rules" / "sql.md").write_text("Use bind parameters.\n", encoding="utf-8")
    write_machine_pins(
        tools={},
        engine_version="0",
        resource_roots={"pkg:acme_rules/resources": str(installed)},
        git_dir=str(repo.root / ".git"),
    )
    tool_input = {"file_path": str(installed / "rules" / "sql.md"), "content": "x\n"}

    report = repo.simulate(repo.tool_payload("Write", tool_input), deps())

    assert _decision(report) is Decision.DENY
    lines = report.trace.combined.reason.splitlines()
    assert "installed engine or overlay resource" in lines[0]
    assert lines[1].startswith("Add a same-id override under playbook/{rules,prompts,skills}/")


def test_heartbeat_canary_edit_lockfile_denies(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    canaries = [canary for canary in DEFAULT_CANARIES if canary.hook_id == HOOK_ID]
    store = StateStore(repo.state_root)

    [result] = run_canaries(canaries, repo_root=str(repo.root), deps=deps(state=store))

    assert (result.name, result.ok, result.decision) == ("edit-lockfile", True, Decision.DENY)
    lines = repo.decisions()
    assert lines and {line["canary"] for line in lines} == {True}
    assert {line["decision"] for line in lines} == {"canary"}


def test_canary_rows_name_their_guard() -> None:
    [row] = [canary for canary in DEFAULT_CANARIES if canary.hook_id == HOOK_ID]

    assert row.expect is Decision.DENY
    assert dataclasses.asdict(row)["fields"]["tool_input"]["file_path"] == (
        ".coding-agent-playbook.lock"
    )

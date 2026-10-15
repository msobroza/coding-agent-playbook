"""``playbook sync`` makes hooks live (specs/prK-lifecycle-hooks.md §C.1.3, §C.2.5, §C.2.6, §B.6).

With ``[hooks] enabled``, one sync writes the managed ``settings.json`` groups,
the launcher, ``guard_config.json`` and the copied scripts; a second sync
changes nothing. ``settings.json`` is co-owned: merged against the real file in
every mode (``--check`` renders into an empty scratch dir), never gitignored,
never staged-flagged, never whole-file locked, never deleted. Every §C.2.6
drift row behaves as tabled.
"""

from __future__ import annotations

import json
import os
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.adapters._destructive_native import (
    DESTRUCTIVE_COMMAND_GUARD,
    destructive_native_rows,
)
from coding_agent_playbook.adapters._secret_native import SECRETS_PATH_GUARD, secret_native_rows
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import Lockfile, compute_hash
from tests.cli.hook_repo import (
    CONFIG,
    GUARD_CONFIG,
    LAUNCHER,
    SCRIPT,
    SCRIPT_BYTES,
    SETTINGS,
    hook_deps,
    make_hook_repo,
    set_hooks_table,
    tree,
)
from tests.fakes import FakeGitClient, FakePinWriter
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

# The sample hooks bind the builtin guard_x, which validate (H6) resolves
# through the handler registry: install it as a real entry point.
pytestmark = pytest.mark.usefixtures("sample_hook_handlers")

_NOTICE = "hooks available: add [hooks] enabled = true or re-run playbook init"


#: The Claude events the engine pack registers (Track K5: the briefing, the guards,
#: the source-changed hooks and the ``drift`` Stop stage; K7: the active-prompt
#: record of prompt-write-scope-guard, a member-less ``UserPromptSubmit``, and
#: toolchain-missing-hint's ``PostToolUseFailure``).
ENGINE_PACK_EVENTS = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
]


def _guard() -> Any:
    """secrets-path-guard as sync resolves it here: no extra globs or allowed paths."""
    return resolved_hook(SECRETS_PATH_GUARD, config={})


def _native_rows() -> dict[str, tuple[str, ...]]:
    """The K8 native twins on here: secrets-path-guard's rows, then destructive-command-guard's."""
    rows = dict(secret_native_rows([_guard()]))
    for pointer, extra in destructive_native_rows(
        [resolved_hook(DESTRUCTIVE_COMMAND_GUARD)]
    ).items():
        rows[pointer] = (*rows.get(pointer, ()), *extra)
    return rows


def _sync_repo(repo: Path, tmp_path: Path, **kwargs: Any) -> int:
    kwargs.setdefault("git", FakeGitClient())
    kwargs.setdefault("hook_deps", hook_deps(tmp_path / "state"))
    return _sync.execute(repo, **kwargs)


def _settings(repo: Path) -> Any:
    return json.loads((repo / SETTINGS).read_text(encoding="utf-8"))


def _write_settings(repo: Path, doc: Any, *, indent: int = 2) -> None:
    (repo / SETTINGS).write_text(json.dumps(doc, indent=indent) + "\n", encoding="utf-8")


def _lock_entries(repo: Path) -> list[Any]:
    text = (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    return Lockfile.from_dict(tomllib.loads(text)).entries


@pytest.fixture
def synced(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> Path:
    """A hook repo after one write-mode sync (its output already read off capsys)."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()
    return repo


def test_absent_hooks_table_is_byte_identical_and_prints_notice(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    pins = FakePinWriter()
    (tmp_path / "plain").mkdir()
    plain = make_synthetic_repo(tmp_path / "plain", config_text=CONFIG)
    with_hooks = make_hook_repo(tmp_path / "hooks", make_synthetic_repo, hooks_table=None)

    assert _sync_repo(plain, tmp_path) == 0
    assert _sync_repo(with_hooks, tmp_path, hook_deps=hook_deps(tmp_path / "s", pins=pins)) == 0

    captured = capsys.readouterr()
    assert captured.out.count(_NOTICE) == 2
    assert captured.err == ""
    outputs = {rel: data for rel, data in tree(with_hooks).items() if not rel.startswith("play")}
    assert outputs == tree(plain)
    assert pins.calls == []


def test_first_sync_writes_every_hook_output(synced: Path) -> None:
    doc = _settings(synced)
    assert list(doc["hooks"]) == ENGINE_PACK_EVENTS
    assert (synced / LAUNCHER).is_file()
    config = json.loads((synced / GUARD_CONFIG).read_bytes())
    # The engine pack's default-tier hooks (Tracks K5, K6), K7's feedback hooks and K8's
    # secret, Bash, dependency and exfil guards, and K9's guard-decision-log (a sink: no
    # registration); guard-eval-fixtures, command-convention-guard, taint-escalation and
    # local-audit-log are opt-in, and the fixture detects no pytest (its lint hook is off).
    assert sorted(config["hooks"]) == [
        "block-precommit-bypass",
        "clean-code-metrics-nonregression",
        "control-plane-guard",
        "dependency-allowlist-guard",
        "destructive-command-guard",
        "error-handling-lint-feedback",
        "eval-task-authoring-lint",
        "exfil-channel-guard",
        "gate-weakening-guard",
        "git-commit-push-policy-guard",
        "guard-decision-log",
        "guard-ext",
        "guard-generated-outputs",
        "guard-x",
        "post-edit-ruff-format",
        "prompt-write-scope-guard",
        "resync-on-detector-input-change",
        "secret-content-guard",
        "secrets-path-guard",
        "session-start-playbook-briefing",
        "stop-ci-parity-gate",
        "stop-diff-sweep",
        "stop-drift-and-orphan-gate",
        "toolchain-missing-hint",
        "typing-lint-feedback",
        "validate-then-sync-on-canonical-edit",
    ]
    assert (synced / SCRIPT).read_bytes() == SCRIPT_BYTES
    if os.name == "posix":
        assert (synced / SCRIPT).stat().st_mode & 0o100
    assert (synced / ".continue" / "rules" / "30-guardrail-guard-x.md").is_file()
    assert "## Guardrails" in (synced / "AGENTS.md").read_text(encoding="utf-8")


def test_templated_body_renders_and_advisory_false_suppresses_it(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo, external=False)
    hook_dir = repo / "playbook" / "hooks" / "protect" / "guard-x"
    text = (hook_dir / "HOOK.md").read_text(encoding="utf-8")
    (hook_dir / "HOOK.md").unlink()
    (hook_dir / "HOOK.md.j2").write_text(
        text.replace("Advice.", "Guard {{ project_name }}."), encoding="utf-8"
    )
    guardrail = repo / ".continue" / "rules" / "30-guardrail-guard-x.md"

    assert _sync_repo(repo, tmp_path) == 0
    assert "Guard synthetic." in (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "Guard synthetic." in guardrail.read_text(encoding="utf-8")

    set_hooks_table(repo, "[hooks]\nenabled = true\nadvisory = false\n")
    assert _sync_repo(repo, tmp_path) == 0
    assert "Guardrails" not in (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert not guardrail.exists()
    assert list(_settings(repo)["hooks"]) == ENGINE_PACK_EVENTS


def test_enabled_second_sync_writes_nothing(synced: Path, tmp_path: Path) -> None:
    before = tree(synced)
    settings_mtime = (synced / SETTINGS).stat().st_mtime_ns

    assert _sync_repo(synced, tmp_path) == 0

    assert tree(synced) == before
    assert (synced / SETTINGS).stat().st_mtime_ns == settings_mtime
    assert _sync_repo(synced, tmp_path, check=True) == 0


_USER_SETTINGS = """\
{
    "permissions": {
        "allow": ["Bash(make test)"]
    },
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook"}]}
        ]
    },
    "model": "opus"
}
"""


def test_user_keys_and_user_groups_byte_stable_across_syncs(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    (repo / ".claude").mkdir()
    (repo / SETTINGS).write_text(_USER_SETTINGS, encoding="utf-8")

    assert _sync_repo(repo, tmp_path) == 0
    first = (repo / SETTINGS).read_text(encoding="utf-8")
    assert _sync_repo(repo, tmp_path) == 0

    assert (repo / SETTINGS).read_text(encoding="utf-8") == first
    # K8's native deny rows join the user's permissions object after the user's own key.
    assert '        "allow": ["Bash(make test)"],\n' in first
    assert '{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook"}]}' in first
    # The user's last member keeps its bytes; the native denyRead twin is appended after it.
    assert '    "model": "opus",\n    "sandbox": {' in first
    assert len(_settings(repo)["hooks"]["PreToolUse"]) == 2


def test_check_merges_against_real_settings_not_empty_scratch(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    (repo / ".claude").mkdir()
    (repo / SETTINGS).write_text(_USER_SETTINGS, encoding="utf-8")
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 0
    assert "No drift detected." in capsys.readouterr().out


def _edit_permissions(repo: Path) -> None:
    """The user's own key of the co-owned object (the managed deny rows stay)."""
    doc = _settings(repo)
    doc["permissions"]["allow"] = ["Bash(ls)"]
    _write_settings(repo, doc)


def _reformat(repo: Path) -> None:
    _write_settings(repo, _settings(repo), indent=4)


def _add_user_group(repo: Path) -> None:
    doc = _settings(repo)
    doc["hooks"]["PreToolUse"].append({"matcher": "Edit", "hooks": [{"type": "command"}]})
    _write_settings(repo, doc)


def _edit_managed_group(repo: Path) -> None:
    doc = _settings(repo)
    doc["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] += 30
    _write_settings(repo, doc)


def _delete_managed_group(repo: Path) -> None:
    doc = _settings(repo)
    del doc["hooks"]["PreToolUse"]
    _write_settings(repo, doc)


def _disable_hooks(repo: Path) -> None:
    set_hooks_table(repo, '[hooks]\nenabled = true\ndisable = ["guard-x", "guard-ext"]\n')


def _invalid_json(repo: Path) -> None:
    (repo / SETTINGS).write_text('{"hooks": {,}}\n', encoding="utf-8")


def _remove_launcher(repo: Path) -> None:
    (repo / LAUNCHER).unlink()


@pytest.mark.parametrize(
    ("edit", "code", "shown"),
    [
        pytest.param(_edit_permissions, 0, "No drift", id="user_edited_permissions_clean"),
        pytest.param(_reformat, 0, "No drift", id="reformatted_clean"),
        pytest.param(_add_user_group, 0, "No drift", id="user_group_added_clean"),
        pytest.param(_edit_managed_group, 1, SETTINGS, id="managed_group_edited_drift"),
        pytest.param(_delete_managed_group, 1, SETTINGS, id="managed_group_deleted_drift"),
        pytest.param(_disable_hooks, 1, SETTINGS, id="hook_disabled_group_on_disk_drift"),
        pytest.param(_invalid_json, 1, "Cannot verify", id="invalid_json_exit1"),
        pytest.param(_remove_launcher, 1, LAUNCHER, id="launcher_missing_drift"),
    ],
)
def test_check_drift_rows(
    edit: Callable[[Path], None],
    code: int,
    shown: str,
    synced: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    edit(synced)
    before = tree(synced)

    assert _sync_repo(synced, tmp_path, check=True) == code

    captured = capsys.readouterr()
    assert shown in captured.out + captured.err
    assert "Traceback" not in captured.err
    assert tree(synced) == before


def test_disable_strips_groups_keeps_settings_deletes_pristine_guard_config_and_scripts(
    synced: Path, tmp_path: Path
) -> None:
    set_hooks_table(synced, "[hooks]\nenabled = false\n")

    assert _sync_repo(synced, tmp_path) == 0

    assert _settings(synced) == {}
    for rel in (GUARD_CONFIG, SCRIPT, LAUNCHER):
        assert not (synced / rel).exists(), rel
    assert all(entry.path != SETTINGS for entry in _lock_entries(synced))


def test_lockfile_has_scoped_settings_entries_and_no_whole_file_entry(synced: Path) -> None:
    entries = _lock_entries(synced)

    scopes = sorted(entry.scope for entry in entries if entry.path == SETTINGS)
    hook_scopes = [scope for scope in scopes if scope.startswith("json:/hooks/")]
    assert hook_scopes == sorted(f"json:/hooks/{event}" for event in ENGINE_PACK_EVENTS)
    # The K8 native twins: one scoped entry per managed string.
    rows = _native_rows()
    assert sorted(set(scopes) - set(hook_scopes)) == sorted(f"json:{p}" for p in rows)
    assert len(scopes) - len(hook_scopes) == sum(len(strings) for strings in rows.values())
    by_path = {entry.path: entry for entry in entries if entry.is_whole_file}
    config = by_path[GUARD_CONFIG]
    assert (config.kind, config.adapter) == ("runtime", "")
    assert config.sha256 == compute_hash((synced / GUARD_CONFIG).read_bytes())
    script = by_path[SCRIPT]
    assert (script.kind, script.artifact_id, script.source) == ("hook", "guard-ext", "<repo-local>")
    assert script.executable is (os.name == "posix")


def test_commit_false_never_gitignores_settings_json(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    git = FakeGitClient(tracked={SETTINGS})

    assert _sync_repo(repo, tmp_path, git=git) == 0

    ignored = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"/{SETTINGS}" not in ignored
    assert f"/{LAUNCHER}" in ignored
    assert "still tracked by git" not in capsys.readouterr().err
    assert _sync_repo(repo, tmp_path, git=git, check=True) == 0


def test_check_staged_never_flags_settings_json(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = FakeGitClient(staged=[SETTINGS])
    flagged = FakeGitClient(staged=[SETTINGS, GUARD_CONFIG])

    assert _sync_repo(synced, tmp_path, git=clean, check_staged=True) == 0
    assert _sync_repo(synced, tmp_path, git=flagged, check_staged=True) == 1

    out = capsys.readouterr().out
    assert f"  {GUARD_CONFIG}\n" in out
    assert f"  {SETTINGS}\n" not in out


def test_summary_lines_counts_and_hand_edit_warning(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    out = capsys.readouterr().out
    # guard-x, guard-ext and the engine pack's twenty-four default-tier hooks on here (seven
    # protect, the Stop coordinator, two of its stage hooks, block-precommit-bypass (K6),
    # post-edit-ruff-format, prompt-write-scope-guard, the error-handling and typing lint
    # hooks, toolchain-missing-hint (K7), the three secret hooks, the two Bash guards and the
    # dependency and exfil guards (K8), guard-decision-log (K9)); pytest's is off (no pytest
    # detected), and so is the ML deserialization guard (no ML stack); the opt-in ones
    # (guard-eval-fixtures, three K6 Stop hooks, the notebook hook, command-convention-guard,
    # taint-escalation, local-audit-log, precompact-checkpoint) are skipped, as is the inert
    # overlay-tier pii-prompt-guard (K9). The briefing, the
    # two lint hooks and the decision sink have no advisory body, so Continue gets four fewer;
    # the sink registers nothing, so the managed entries are unchanged. The member-less UserPromptSubmit group
    # is one entry, toolchain-missing-hint's PostToolUseFailure another, and each native
    # deny row (secrets and destructive prefixes) one more.
    native = sum(len(rows) for rows in _native_rows().values())
    assert "✓ Hooks: 26 enabled, 12 skipped (" in out
    assert "claude_code: 26 enforced" in out
    assert "continue: 22 advisory" in out
    updated = f"{6 + native} managed entries updated, 0 removed (user keys untouched)"
    assert f"✓ {SETTINGS}: {updated}" in out

    _edit_managed_group(repo)
    assert _sync_repo(repo, tmp_path) == 0
    assert "managed entry was edited by hand; restored" in capsys.readouterr().err

    (repo / ".coding-agent-playbook.lock").unlink()  # a teammate's clone: no prior entry
    _edit_managed_group(repo)
    assert _sync_repo(repo, tmp_path) == 0
    assert "edited by hand" not in capsys.readouterr().err


def test_invalid_settings_json_stops_write_mode_before_any_write(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (synced / "AGENTS.md").unlink()
    _invalid_json(synced)
    before = tree(synced)

    assert _sync_repo(synced, tmp_path) == 1

    err = capsys.readouterr().err
    assert f"error: {SETTINGS}:1:" in err
    assert "Traceback" not in err
    assert tree(synced) == before


def test_guard_config_protects_exactly_the_lockfile_rows(synced: Path) -> None:
    """The §E.0.5 ``protected`` table mirrors the lockfile (Track K5): no render at run time."""
    config = json.loads((synced / GUARD_CONFIG).read_bytes())
    table = config["protected"]
    columns = ("path", "kind", "artifact_id", "source", "scope")
    rows = [tuple(row[c] for c in columns) for row in table["entries"]]
    # guard_config.json and the copied scripts are written after the table is rendered;
    # both sit under the hook-artifact dir, which protects them as a whole.
    expected = sorted(
        tuple(getattr(entry, c) for c in columns)
        for entry in _lock_entries(synced)
        if not entry.path.startswith(".coding-agent-playbook/hooks/")
    )

    assert sorted(rows) == expected
    assert all("sha256" in row for row in table["entries"] if row["scope"])
    assert ".coding-agent-playbook/hooks/" in table["hook_artifacts"]
    assert ".claude/commands/" in table["output_dirs"] and "AGENTS.md" in table["output_dirs"]
    assert table["resource_roots"] == ["pkg:coding_agent_playbook/resources"]
    assert config["sentinel"].startswith("AUTOGENERATED by coding-agent-playbook")


def test_write_mode_pins_resource_roots_in_machine_json(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    pins = FakePinWriter()

    assert _sync_repo(repo, tmp_path, hook_deps=hook_deps(tmp_path / "state", pins=pins)) == 0

    import coding_agent_playbook

    engine = os.path.join(os.path.dirname(coding_agent_playbook.__file__), "resources")
    assert pins.resource_roots == {"pkg:coding_agent_playbook/resources": engine}


def test_guard_config_precommit_ids_follow_the_repo_config(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """Both modes scan the real repo's pre-commit config (Track K5): --check sees an edit."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    precommit = repo / ".pre-commit-config.yaml"
    precommit.write_text("repos:\n  - hooks:\n      - id: playbook-sync-check\n", encoding="utf-8")

    assert _sync_repo(repo, tmp_path) == 0
    config = json.loads((repo / GUARD_CONFIG).read_bytes())
    assert config["precommit"] == {"playbook_hook_ids": ["playbook-sync-check"]}
    assert config["control_plane"]["settings"] == [SETTINGS, ".claude/settings.local.json"]
    assert _sync_repo(repo, tmp_path, check=True) == 0

    precommit.write_text("repos: []\n", encoding="utf-8")
    assert _sync_repo(repo, tmp_path, check=True) == 1

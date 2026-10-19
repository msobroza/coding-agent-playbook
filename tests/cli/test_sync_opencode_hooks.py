"""``playbook sync`` renders the OpenCode V1 shim (specs/prK-lifecycle-hooks.md §C.0, §C.3, §B.6).

With ``[hooks] enabled`` and a hook that supports ``opencode``, one sync writes
``.opencode/plugins/playbook-hooks.js`` with a whole-file ``kind = "runtime"``
lock entry; a second sync rewrites identical bytes. The shim is deleted once no
hook needs it, a hand edit is ``--check`` drift, and a since-disabled
``opencode`` adapter's pristine shim goes through the lockfile leftover policy.
Every other file under ``.opencode/plugin(s)/`` belongs to the user. Write mode
asks for an OpenCode restart whenever the shim's bytes change (V1 has no plugin
hot reload), never for a ``guard_config.json``-only change and never in a check.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_registrations import OPENCODE_SHIM_PATH
from coding_agent_playbook.lockfile.model import Lockfile, compute_hash
from tests.cli.hook_repo import (
    CONFIG,
    GUARD_CONFIG,
    HOOKS_ON,
    LAUNCHER,
    hook_deps,
    make_hook_repo,
    tree,
)
from tests.fakes import FakeGitClient
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

# The sample hooks bind builtins that validate (H6) resolves through the
# handler registry: install them as real entry points.
pytestmark = pytest.mark.usefixtures("sample_hook_handlers")

_USER_PLUGIN = ".opencode/plugins/other.js"
_WITHOUT_OPENCODE = CONFIG.replace('"claude_code", "opencode"]', '"claude_code"]')


def _sync_repo(repo: Path, tmp_path: Path, **kwargs: Any) -> int:
    kwargs.setdefault("git", FakeGitClient())
    kwargs.setdefault("hook_deps", hook_deps(tmp_path / "state"))
    return _sync.execute(repo, **kwargs)


def _opencode_repo(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, hooks_table: str | None = HOOKS_ON
) -> Path:
    """The K3 hook repo plus ``guard-oc``, a ``pre_tool_use`` hook OpenCode enforces."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo, hooks_table=hooks_table)
    hooks_dir = repo / "playbook" / "hooks"
    write_hook(
        hooks_dir, "guard-oc", supports=["claude_code", "opencode"], handler={"builtin": "guard_y"}
    )
    return repo


def _set_config(repo: Path, text: str) -> None:
    (repo / ".coding-agent-playbook.toml").write_text(text, encoding="utf-8")


def _lock_entries(repo: Path) -> dict[str, Any]:
    text = (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    entries = Lockfile.from_dict(tomllib.loads(text)).entries
    return {entry.path: entry for entry in entries if entry.is_whole_file}


@pytest.fixture
def synced(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> Path:
    """An OpenCode hook repo after one write-mode sync (its output read off capsys)."""
    repo = _opencode_repo(tmp_path, make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()
    return repo


def test_sync_hooks_on_writes_opencode_shim_with_runtime_lock_entry(synced: Path) -> None:
    shim = synced / OPENCODE_SHIM_PATH
    entries = _lock_entries(synced)

    assert shim.read_text(encoding="utf-8").split("\n", 1)[0] == sentinel_line("slash")
    entry = entries[OPENCODE_SHIM_PATH]
    assert (entry.kind, entry.adapter, entry.artifact_id, entry.source) == (
        "runtime",
        "opencode",
        "",
        "",
    )
    assert entry.sha256 == compute_hash(shim.read_bytes())
    launcher = entries[LAUNCHER]  # §B.6: the launcher is runtime plumbing too
    assert (launcher.kind, launcher.adapter, launcher.artifact_id) == ("runtime", "claude_code", "")
    ignored = (synced / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"/{OPENCODE_SHIM_PATH}" in ignored  # [output] commit = false: regenerated per clone


def test_second_sync_rewrites_identical_shim(synced: Path, tmp_path: Path) -> None:
    before = tree(synced)

    assert _sync_repo(synced, tmp_path) == 0

    assert tree(synced) == before
    assert _sync_repo(synced, tmp_path, check=True) == 0


def test_sync_hooks_off_removes_shim(synced: Path, tmp_path: Path) -> None:
    user_plugin = synced / _USER_PLUGIN
    user_plugin.write_text(f"{sentinel_line('slash')}\nexport default {{}}\n", encoding="utf-8")
    _set_config(synced, f"{CONFIG}\n[hooks]\nenabled = false\n")

    assert _sync_repo(synced, tmp_path) == 0

    assert not (synced / OPENCODE_SHIM_PATH).exists()
    assert user_plugin.is_file()
    assert OPENCODE_SHIM_PATH not in _lock_entries(synced)
    assert _sync_repo(synced, tmp_path, check=True) == 0


def test_sync_check_reports_hand_edited_shim_as_drift(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shim = synced / OPENCODE_SHIM_PATH
    shim.write_text(shim.read_text(encoding="utf-8") + "// tweak\n", encoding="utf-8")
    before = tree(synced)

    assert _sync_repo(synced, tmp_path, check=True) == 1

    assert OPENCODE_SHIM_PATH in capsys.readouterr().out
    assert tree(synced) == before


def test_sync_check_reports_shim_left_after_hooks_turn_off(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_config(synced, f"{CONFIG}\n[hooks]\nenabled = false\n")

    assert _sync_repo(synced, tmp_path, check=True) == 1

    assert OPENCODE_SHIM_PATH in capsys.readouterr().out
    assert (synced / OPENCODE_SHIM_PATH).is_file()


def test_sync_without_hooks_table_keeps_opencode_tree_byte_identical(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    (tmp_path / "plain").mkdir()
    plain = make_synthetic_repo(tmp_path / "plain", config_text=CONFIG)
    with_hooks = _opencode_repo(tmp_path, make_synthetic_repo, hooks_table=None)

    assert _sync_repo(plain, tmp_path) == 0
    assert _sync_repo(with_hooks, tmp_path) == 0

    def opencode(repo: Path) -> dict[str, bytes]:
        return {rel: data for rel, data in tree(repo).items() if rel.startswith(".opencode/")}

    assert opencode(with_hooks) == opencode(plain)
    assert not (with_hooks / ".opencode" / "plugins").exists()


def test_disabled_opencode_adapter_leftover_policy_deletes_pristine_shim(
    synced: Path, tmp_path: Path
) -> None:
    user_plugin = synced / _USER_PLUGIN
    user_plugin.write_text("export default {}\n", encoding="utf-8")
    _set_config(synced, f"{_WITHOUT_OPENCODE}\n{HOOKS_ON}")

    assert _sync_repo(synced, tmp_path) == 0

    assert not (synced / OPENCODE_SHIM_PATH).exists()
    assert user_plugin.is_file()  # pruning never removes the user's plugins dir
    assert OPENCODE_SHIM_PATH not in _lock_entries(synced)


def test_disabled_opencode_adapter_keeps_a_hand_edited_shim(synced: Path, tmp_path: Path) -> None:
    shim = synced / OPENCODE_SHIM_PATH
    edited = shim.read_text(encoding="utf-8") + "// mine\n"
    shim.write_text(edited, encoding="utf-8")
    _set_config(synced, f"{_WITHOUT_OPENCODE}\n{HOOKS_ON}")

    assert _sync_repo(synced, tmp_path) == 0

    assert shim.read_text(encoding="utf-8") == edited
    assert OPENCODE_SHIM_PATH in _lock_entries(synced)  # carried: still owned, never committable


# --- §C.1.5 / §C.3.2 "Reload behavior": V1 has no plugin hot reload -----------------

_RESTART = f"! {OPENCODE_SHIM_PATH} changed: restart OpenCode to load it"
_UNLOAD = f"! {OPENCODE_SHIM_PATH} removed: restart OpenCode to unload it"


def _narrow_guard_oc(repo: Path) -> None:
    """Rewrite ``guard-oc`` to match shell calls only: its REG ``tools`` change."""
    write_hook(
        repo / "playbook" / "hooks",
        "guard-oc",
        supports=["claude_code", "opencode"],
        handler={"builtin": "guard_y"},
        matcher={"pre_tool_use": {"tools": ["shell"]}},
    )


def test_first_sync_prints_restart_notice_beside_hook_summary(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _opencode_repo(tmp_path, make_synthetic_repo)

    assert _sync_repo(repo, tmp_path) == 0
    lines = capsys.readouterr().out.splitlines()
    assert _sync_repo(repo, tmp_path) == 0

    hooks_line = next(i for i, line in enumerate(lines) if line.startswith("✓ Hooks:"))
    assert lines.index(_RESTART) > hooks_line
    assert "restart OpenCode" not in capsys.readouterr().out  # identical bytes: no restart


def test_reg_change_prints_restart_notice(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shim = synced / OPENCODE_SHIM_PATH
    before = shim.read_bytes()
    _narrow_guard_oc(synced)

    assert _sync_repo(synced, tmp_path) == 0

    assert shim.read_bytes() != before
    assert _RESTART in capsys.readouterr().out.splitlines()


def test_guard_config_only_change_prints_no_restart_notice(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shim, guard = synced / OPENCODE_SHIM_PATH, synced / GUARD_CONFIG
    shim_before, guard_before = shim.read_bytes(), guard.read_bytes()
    _set_config(synced, f"{CONFIG}\n{HOOKS_ON}state_ttl_days = 14\n")

    assert _sync_repo(synced, tmp_path) == 0

    assert guard.read_bytes() != guard_before  # the dispatcher reads it per call
    assert shim.read_bytes() == shim_before
    assert "restart OpenCode" not in capsys.readouterr().out


def test_shim_removal_prints_unload_notice(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_config(synced, f"{CONFIG}\n[hooks]\nenabled = false\n")

    assert _sync_repo(synced, tmp_path) == 0

    assert _UNLOAD in capsys.readouterr().out.splitlines()


def test_sync_check_never_prints_restart_notice(
    synced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _narrow_guard_oc(synced)
    staged = FakeGitClient(staged=[OPENCODE_SHIM_PATH])

    assert _sync_repo(synced, tmp_path, check=True) == 1
    assert _sync_repo(synced, tmp_path, git=staged, check_staged=True) == 1

    assert "restart OpenCode" not in capsys.readouterr().out

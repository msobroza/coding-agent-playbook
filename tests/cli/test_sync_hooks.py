"""``playbook sync`` and the other context-building commands with hooks (prK §A.5, §B.5, §P P8).

A malformed ``HOOK.md`` stays fail-loud wherever a ``SyncContext`` is built
(sync, check, render, eval), but as one ``error:`` line and exit 2, never a
traceback, and before anything is written. A well-formed hook that breaks the
trust contract (H2-H21) is refused by sync's validate gate: ``FAIL`` lines and
the abort line on stderr, exit 1, nothing written. A ``[hooks]`` table in
``.local.toml`` is ignored, and only warned about (§B.1).
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import Lockfile
from tests.fakes import FakeGitClient, pre_gate_validate

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]
    HookFactory = Callable[..., Path]


@pytest.mark.parametrize(
    "command",
    [["sync"], ["sync", "--check"], ["check"], ["render", "guard-x"], ["eval", "--list"]],
)
def test_malformed_hook_prints_error_not_traceback(
    command: list[str],
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    bad = make_hook(repo / "playbook" / "hooks", "guard-x", timeout="2s")

    code = main([*command, "--repo-root", str(repo)])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.splitlines() == [
        f"error: {bad}: timeout: expected a number of seconds, got '2s'"
    ]
    assert "Traceback" not in captured.out + captured.err


def test_sync_with_malformed_hook_prints_error_not_traceback(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    make_hook(repo / "playbook" / "hooks", "guard-x", marker="HOOK.md")
    make_hook(repo / "playbook" / "hooks", "guard-x", marker="HOOK.md.j2")
    before = sorted(path.relative_to(repo) for path in repo.rglob("*"))

    code = main(["sync", "--repo-root", str(repo)])

    assert code == 2
    assert "both HOOK.md and HOOK.md.j2" in capsys.readouterr().err
    assert sorted(path.relative_to(repo) for path in repo.rglob("*")) == before


def test_sync_with_a_valid_hook_still_syncs(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, make_hook: HookFactory
) -> None:
    # K1 resolves hooks but renders none (K3): a well-formed hook changes nothing.
    repo = make_synthetic_repo(tmp_path)
    make_hook(repo / "playbook" / "hooks", "guard-x")

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / "AGENTS.md").is_file()


_ABORT_LINE = "playbook sync aborted; no files were written."


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (repo-relative posix path -> bytes)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("check", [False, True], ids=["write", "check"])
def test_sync_aborts_on_hook_contract_error_and_writes_nothing(
    check: bool,
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    if check:
        assert _sync.execute(repo, git=FakeGitClient()) == 0
    bad = make_hook(repo / "playbook" / "hooks", "guard-x", on_error="deny")
    before = _tree(repo)
    capsys.readouterr()

    assert _sync.execute(repo, check=check, git=FakeGitClient()) == 1

    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        f"FAIL {bad}: on_error 'deny' (fail-closed) is reserved for overlay hooks",
        "validation failed with 1 error(s)",
        _ABORT_LINE,
    ]
    assert "drift" not in captured.out.lower()  # the gate fires before any render
    assert _tree(repo) == before


def test_sync_only_warns_on_local_toml_hooks_table(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    local = repo / ".coding-agent-playbook.local.toml"
    local.write_text("[hooks]\nenabled = false\n", encoding="utf-8")

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    assert capsys.readouterr().err.splitlines() == [
        f"warning: {local}: hooks.enabled: [hooks] and [guardrails] are read from the "
        "committed config only, so these local values are ignored; move them to the "
        "committed config or delete them"
    ]
    assert (repo / "AGENTS.md").is_file()


def test_sync_prints_hook_warnings_and_proceeds(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    hook = make_hook(
        repo / "playbook" / "hooks",
        "guard-x",
        events=["session_start"],
        decisions=["context"],
        on_error="open",
        timeout=20,
    )

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    assert capsys.readouterr().err.splitlines() == [
        f"warning: {hook}: timeout 20 exceeds the 15 s deadline cap of event 'session_start'; "
        "it is clamped to 15 s"
    ]


def _lock_entries(repo: Path) -> list[dict[str, object]]:
    text = (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    return [entry.to_dict() for entry in Lockfile.from_dict(tomllib.loads(text)).entries]


def test_repo_without_hooks_syncs_byte_identically(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same repo synced through the hook-aware gate and through no gate at all
    # (an engine older than it): K1 renders nothing for hooks, so not one byte moves.
    gated, ungated = tmp_path / "a" / "repo", tmp_path / "b" / "repo"
    for root in (gated, ungated):
        root.mkdir(parents=True)
        make_synthetic_repo(root, rules=[("house-style", "Body.\n")])

    assert _sync.execute(gated, git=FakeGitClient()) == 0
    assert _sync.execute(ungated, git=FakeGitClient(), validate=pre_gate_validate) == 0

    assert capsys.readouterr().err == ""
    lockfile = ".coding-agent-playbook.lock"
    gated_tree, ungated_tree = _tree(gated), _tree(ungated)
    assert gated_tree.pop(lockfile) and ungated_tree.pop(lockfile)
    assert gated_tree == ungated_tree
    assert _lock_entries(gated) == _lock_entries(ungated)
    assert not any(path.startswith(".coding-agent-playbook/") for path in gated_tree)

"""``playbook sync`` and the other context-building commands with hooks (prK §A.5, §P P8c).

A malformed ``HOOK.md`` stays fail-loud wherever a ``SyncContext`` is built
(sync, check, render, eval), but as one ``error:`` line and exit 2, never a
traceback, and before anything is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import sync as _sync
from tests.fakes import FakeGitClient

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
